"""The life of a run: requested, claimed by a runner, reported, finished."""
import logging
import re
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from codespeed.github_api import GitHubError
from codespeed.models import Benchmark, PRRun, PRRunner, Result

from . import git, github, report

logger = logging.getLogger(__name__)

# A base commit counts as already benchmarked when it has at least this share
# of the results a typical revision has; runs drop the odd benchmark.
BASE_MIN_COVERAGE = 0.8
# Benchmark names end up in a runner's configuration, so keep them plain
_BENCHMARK_RE = re.compile(r'^[\w.+\-]+$')


class RunError(Exception):
    """A request that cannot be queued; the text is shown to the requester."""


def requester_name(user):
    account = getattr(user, 'github_account', None)
    return account.login if account else user.get_username()


def request_runs(user, project, pr_number, runners, executable,
                 benchmarks=(), reuse_base=True):
    """Queue one run per runner and return them.

    The pull request's current commit is pinned here, with one
    ``git ls-remote`` against GitHub, so the runs stay on that commit however
    the pull request moves afterwards. The merge base is left to the runner,
    which has a clone to work it out from.
    """
    if not runners:
        raise RunError('Choose at least one environment.')
    if executable.project_id != project.pk:
        raise RunError('That executable belongs to another project.')
    if not pr_number:
        raise RunError('Enter a pull request number.')

    benchmarks = sorted(set(benchmarks))
    for name in benchmarks:
        if not _BENCHMARK_RE.match(name):
            raise RunError('"%s" is not a usable benchmark name.' % name)
    known = set(Benchmark.objects.filter(
        name__in=benchmarks).values_list('name', flat=True))
    unknown = [name for name in benchmarks if name not in known]
    if unknown:
        raise RunError('Unknown benchmark: %s.' % ', '.join(unknown))

    try:
        head_sha = git.pull_request_head(project, pr_number)
    except git.PullRequestError as e:
        raise RunError(str(e)) from None

    benchmark_text = ','.join(benchmarks)
    for runner in runners:
        if not runner.enabled:
            raise RunError('%s is not accepting runs.' % runner)
        if not runner.executables.filter(pk=executable.pk).exists():
            raise RunError('%s cannot build %s.' % (runner, executable))
        duplicate = runner.runs.filter(
            project=project, pr_number=pr_number, head_sha=head_sha,
            executable=executable, benchmarks=benchmark_text,
            status__in=PRRun.ACTIVE).first()
        if duplicate:
            raise RunError(
                'Run %d is already benchmarking this commit on %s.' % (
                    duplicate.pk, runner))

    limit = settings.PR_RUNNER_MAX_ACTIVE_PER_USER
    active = PRRun.objects.filter(
        requested_by=user, status__in=PRRun.ACTIVE).count()
    if active + len(runners) > limit:
        raise RunError(
            'You can have at most %d runs queued or running; you have %d.' % (
                limit, active))

    with transaction.atomic():
        runs = [PRRun.objects.create(
            runner=runner, project=project, executable=executable,
            pr_number=pr_number, head_sha=head_sha,
            base_branch=project.default_branch,
            benchmarks=benchmark_text, reuse_base=reuse_base,
            requested_by=user, requested_by_login=requester_name(user),
        ) for runner in runners]

    for run in runs:
        logger.info('%s queued PR run %d: #%d %s on %s', run.requested_by_login,
                    run.pk, pr_number, head_sha, run.runner)
        notify_runner(run)
    return runs


def notify_runner(run):
    """Tell the runner there is work, where it does not poll for itself."""
    runner = run.runner
    if runner.backend != PRRunner.GITHUB_ACTIONS:
        return
    try:
        github.dispatch_workflow(runner, run)
    except (GitHubError, git.PullRequestError) as e:
        logger.warning('Could not dispatch PR run %d: %s', run.pk, e)
        _finish(run, PRRun.FAILED, [PRRun.QUEUED],
                'Could not start the workflow: %s' % e)
        run.refresh_from_db()


def _finish(run, status, expected, message=''):
    """Move a run to a final state, unless something else got there first."""
    return PRRun.objects.filter(pk=run.pk, status__in=expected).update(
        status=status, finished_at=timezone.now(), message=message[:500])


def expire_stale_runs():
    """Fail running jobs whose runner went quiet.

    Called lazily from the page and the API, so no scheduler is needed.
    """
    cutoff = timezone.now() - timedelta(seconds=settings.PR_RUNNER_STALE_SECONDS)
    return PRRun.objects.filter(
        status=PRRun.RUNNING, heartbeat_at__lt=cutoff
    ).update(status=PRRun.FAILED, finished_at=timezone.now(),
             message='The runner stopped reporting.')


def cancel(run, user):
    done = _finish(run, PRRun.CANCELLED, PRRun.ACTIVE,
                   'Cancelled by %s.' % requester_name(user))
    if done:
        logger.info('%s cancelled PR run %d', requester_name(user), run.pk)
    return bool(done)


def base_is_benchmarked(run):
    """Whether the base commit already has results worth reusing."""
    if not run.base_sha:
        return False
    base = Result.objects.filter(
        revision__commitid=run.base_sha,
        revision__branch__project=run.project,
        executable=run.executable, environment=run.runner.environment)
    names = set(run.benchmark_list)
    if names:
        have = set(base.filter(benchmark__name__in=names).values_list(
            'benchmark__name', flat=True))
        return have == names

    count = base.count()
    if not count:
        return False
    # Compare against the newest other revision on the branch, the way
    # create_report_if_enough_data() judges whether a run is complete.
    latest = Result.objects.filter(
        revision__branch__project=run.project,
        revision__branch__name=run.base_branch,
        executable=run.executable, environment=run.runner.environment,
    ).exclude(revision__commitid=run.base_sha).order_by(
        '-revision__date').values_list('revision_id', flat=True).first()
    if latest is None:
        return True
    typical = Result.objects.filter(
        revision_id=latest, executable=run.executable,
        environment=run.runner.environment).count()
    return count >= BASE_MIN_COVERAGE * typical


def claim(runner, run_id=None):
    """Hand the runner its oldest queued run, or the one it asks for.

    A machine benchmarks one thing at a time, so nothing is handed out while
    it still has a run in progress.
    """
    expire_stale_runs()
    now = timezone.now()
    PRRunner.objects.filter(pk=runner.pk).update(last_seen=now)
    if runner.runs.filter(status=PRRun.RUNNING).exists():
        return None
    queued = runner.runs.filter(status=PRRun.QUEUED).order_by('id')
    if run_id is not None:
        queued = queued.filter(pk=run_id)
    for pk in list(queued.values_list('pk', flat=True)[:5]):
        # The conditional update is the lock: only one caller sees 1
        claimed = PRRun.objects.filter(pk=pk, status=PRRun.QUEUED).update(
            status=PRRun.RUNNING, started_at=now, heartbeat_at=now,
            message='Picked up by the runner.')
        if claimed:
            return PRRun.objects.select_related(
                'runner__environment', 'project', 'executable').get(pk=pk)
    return None


def job(run, run_url):
    """What a runner needs to know to do the work.

    No base commit yet: the runner finds the merge base in its clone and
    reports it, and the answer tells it whether that commit needs building.
    """
    return {
        'id': run.pk,
        'url': run_url,
        'project': run.project.name,
        'repository': run.project.repo_path,
        'environment': run.runner.environment.name,
        'executable': run.executable.name,
        'pr_number': run.pr_number,
        'head_sha': run.head_sha,
        'head_branch': run.head_branch,
        'base_branch': run.base_branch,
        'reuse_base': run.reuse_base,
        'benchmarks': run.benchmarks,
    }


def record_base(run, base_sha):
    """Note the merge base the runner found; returns whether to skip it.

    The first report wins. A runner that changes its mind mid-run would
    leave results filed under one commit and a report reading another.
    """
    if run.base_sha and run.base_sha != base_sha:
        return None
    if not run.base_sha:
        PRRun.objects.filter(pk=run.pk, base_sha='').update(base_sha=base_sha)
        run.refresh_from_db(fields=['base_sha'])
    return run.reuse_base and base_is_benchmarked(run)


def heartbeat(run, message='', log_url=''):
    fields = {'heartbeat_at': timezone.now()}
    if message:
        fields['message'] = message[:500]
    if log_url:
        fields['log_url'] = log_url
    now = fields['heartbeat_at']
    PRRunner.objects.filter(pk=run.runner_id).update(last_seen=now)
    return PRRun.objects.filter(pk=run.pk, status=PRRun.RUNNING).update(**fields)


def fail(run, message):
    return bool(_finish(run, PRRun.FAILED, [PRRun.RUNNING],
                        message or 'The runner reported a failure.'))


def complete(run, run_url):
    """Close a run the runner says is done, and tell the pull request.

    The runner's word is checked against what it uploaded: with no results
    for the pull request's commit there is nothing to report, so the run
    fails instead.
    """
    if not run.base_sha:
        return fail(run, 'The runner never reported the base commit.')
    data = report.comparison(run)
    if data is None:
        return fail(run, 'The runner finished without uploading results.')
    if not _finish(run, PRRun.COMPLETED, [PRRun.RUNNING],
                   'Geometric mean: %s.' % report.format_speedup(
                       data['geomean'])):
        return False

    if settings.PR_RUNNER_COMMENT and settings.PR_RUNNER_GITHUB_TOKEN:
        try:
            url = github.post_comment(
                run.project, run.pr_number,
                report.markdown(run, data, run_url))
        except (GitHubError, git.PullRequestError) as e:
            # The results are in and the page shows them; a lost comment is
            # not worth failing the run for.
            logger.warning('Could not comment on #%d for PR run %d: %s',
                           run.pr_number, run.pk, e)
        else:
            PRRun.objects.filter(pk=run.pk).update(comment_url=url)
    return True
