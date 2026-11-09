"""The "PR Runner" tab: queue a run, and watch the ones in flight."""
from django.contrib import messages
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from codespeed.github_auth import login_enabled
from codespeed.models import Benchmark, Executable, PRRun, PRRunner, Project

from . import feature_required, git, queue, report, start_refusal

RECENT_RUNS = 50


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _form_context():
    runners = list(PRRunner.objects.filter(enabled=True).select_related(
        'environment').prefetch_related('executables').order_by(
        'environment__name'))
    offered = {exe.pk for runner in runners for exe in runner.executables.all()}
    # Only projects with something to run are worth choosing between; with
    # no runners yet, list every GitHub project so the page is not blank.
    projects = Project.objects.filter(repo_type=Project.GITHUB).order_by('name')
    if offered:
        projects = projects.filter(executables__in=offered).distinct()
    return {
        'runners': [{
            'runner': runner,
            'executables': ','.join(
                str(exe.pk) for exe in runner.executables.all()),
        } for runner in runners],
        'projects': projects,
        'executables': Executable.objects.filter(pk__in=offered).order_by('name'),
        'benchmarks': Benchmark.objects.order_by('name').values_list(
            'name', flat=True).distinct(),
    }


@feature_required
@require_GET
def index(request):
    queue.expire_stale_runs()
    refusal = start_refusal(request.user)
    context = {
        'runs': PRRun.objects.select_related(
            'runner__environment', 'executable', 'project')[:RECENT_RUNS],
        'refusal': refusal,
        'can_start': refusal is None,
        'login_enabled': login_enabled(),
    }
    if refusal is None:
        context.update(_form_context())
    return render(request, 'codespeed/pr_runner/index.html', context)


@feature_required
@require_GET
def detail(request, run_id):
    queue.expire_stale_runs()
    run = get_object_or_404(PRRun.objects.select_related(
        'runner__environment', 'executable', 'project'), pk=run_id)
    data = report.comparison(run)
    if data:
        for row in data['rows']:
            row['base_text'] = report.format_value(row['base'], row['units'])
            row['head_text'] = report.format_value(row['head'], row['units'])
            row['speedup_text'] = report.format_speedup(row['speedup'])
        data['geomean_text'] = report.format_speedup(data['geomean'])
        # Regressions first, then improvements, then everything unremarkable
        data['rows'].sort(key=lambda row: (
            not row['significant'], row['speedup'] if row['significant'] else 0,
            row['name']))
    try:
        repo = git.repository_url(run.project)
    except git.PullRequestError:
        repo = None
    return render(request, 'codespeed/pr_runner/detail.html', {
        'run': run,
        'comparison': data,
        'repo': repo,
        'can_cancel': run.is_active and start_refusal(request.user) is None,
    })


@feature_required
@require_POST
def create(request):
    if start_refusal(request.user) is not None:
        return HttpResponseForbidden('You may not start runs.')
    post = request.POST
    project = get_object_or_404(Project, pk=_int(post.get('project')))
    pr_number = git.parse_number(project, post.get('pull_request'))
    executable = Executable.objects.filter(
        pk=_int(post.get('executable'))).first()
    runner_ids = [pk for pk in map(_int, post.getlist('runner')) if pk]
    runners = list(PRRunner.objects.filter(
        pk__in=runner_ids).select_related('environment'))
    benchmarks = post.getlist('benchmark') if post.get('suite') == 'subset' else []

    try:
        if pr_number is None:
            raise queue.RunError(
                'Enter a pull request number, or paste its URL.')
        if executable is None:
            raise queue.RunError('Choose an executable.')
        if post.get('suite') == 'subset' and not benchmarks:
            raise queue.RunError('Choose at least one benchmark.')
        runs = queue.request_runs(
            request.user, project, pr_number, runners, executable,
            benchmarks=benchmarks, reuse_base=bool(post.get('reuse_base')))
    except queue.RunError as e:
        messages.error(request, str(e))
        return redirect('pr-runner')

    failed = [run for run in runs if run.status == PRRun.FAILED]
    for run in failed:
        messages.error(request, 'Run %d on %s: %s' % (
            run.pk, run.runner, run.message))
    queued = len(runs) - len(failed)
    if queued:
        messages.success(request, 'Queued %d run%s for #%d.' % (
            queued, '' if queued == 1 else 's', runs[0].pr_number))
    if len(runs) == 1:
        return redirect(runs[0])
    return redirect('pr-runner')


@feature_required
@require_POST
def cancel(request, run_id):
    if start_refusal(request.user) is not None:
        return HttpResponseForbidden('You may not cancel runs.')
    run = get_object_or_404(PRRun, pk=run_id)
    if queue.cancel(run, request.user):
        messages.success(request, 'Run %d cancelled.' % run.pk)
    else:
        messages.error(request, 'Run %d had already finished.' % run.pk)
    return redirect(run)
