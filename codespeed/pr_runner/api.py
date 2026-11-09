"""The API benchmark machines use to take and report on runs.

Two calls, both authenticated with the runner's own bearer token:

``POST /pr-runner/api/claim/``
    Take the next queued run. Answers 200 with the job as JSON, or 204 when
    there is nothing to do. ``run_id`` asks for one particular run.

``POST /pr-runner/api/runs/<id>/``
    Report on a run this runner claimed: ``status`` is ``running`` (a
    heartbeat, with an optional progress ``message``), ``completed`` or
    ``failed``. ``base_sha`` reports the merge base once the runner has
    worked it out; the answer then carries ``skip_base``. The answer always
    says whether the run was cancelled meanwhile, so the machine can stop
    early.

Results themselves go to ``/result/add/json/`` as they always have.
"""
import json

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from codespeed.models import PRRun, PRRunner

from . import feature_required, queue
from .git import SHA_RE

_validate_url = URLValidator(schemes=['http', 'https'])


def _error(status, message):
    return JsonResponse({'error': message}, status=status)


def _runner(request):
    scheme, _, token = request.META.get('HTTP_AUTHORIZATION', '').partition(' ')
    if scheme.lower() != 'bearer':
        return None
    return PRRunner.for_token(token.strip())


def _payload(request):
    if request.content_type == 'application/json':
        try:
            data = json.loads(request.body or b'{}')
        except ValueError:
            return None
        return data if isinstance(data, dict) else None
    return request.POST


def _run_url(request, run):
    return request.build_absolute_uri(run.get_absolute_url())


@csrf_exempt
@require_POST
@feature_required
def claim(request):
    runner = _runner(request)
    if runner is None:
        return _error(401, 'Unknown or disabled runner token.')
    data = _payload(request)
    if data is None:
        return _error(400, 'The body is not a JSON object.')
    run_id = data.get('run_id')
    if run_id in (None, ''):
        run_id = None
    else:
        try:
            run_id = int(run_id)
        except (TypeError, ValueError):
            return _error(400, 'run_id is not a number.')

    run = queue.claim(runner, run_id)
    if run is None:
        return HttpResponse(status=204)
    return JsonResponse(queue.job(run, _run_url(request, run)))


@csrf_exempt
@require_POST
@feature_required
def update(request, run_id):
    runner = _runner(request)
    if runner is None:
        return _error(401, 'Unknown or disabled runner token.')
    # A run that belongs to another runner looks the same as no run at all
    run = PRRun.objects.select_related(
        'runner__environment', 'project', 'executable'
    ).filter(pk=run_id, runner=runner).first()
    if run is None:
        return _error(404, 'No such run for this runner.')
    data = _payload(request)
    if data is None:
        return _error(400, 'The body is not a JSON object.')

    status = data.get('status')
    message = str(data.get('message') or '')
    log_url = str(data.get('log_url') or '')
    if log_url:
        try:
            _validate_url(log_url)
        except ValidationError:
            return _error(400, 'log_url is not an http(s) URL.')
        if len(log_url) > 200:
            return _error(400, 'log_url is too long.')
    if status not in (PRRun.RUNNING, PRRun.COMPLETED, PRRun.FAILED):
        return _error(400, 'status must be running, completed or failed.')
    base_sha = str(data.get('base_sha') or '')
    if base_sha and not SHA_RE.match(base_sha):
        return _error(400, 'base_sha is not a full commit id.')

    skip_base = None
    if run.status == PRRun.RUNNING:
        queue.heartbeat(run, message if status == PRRun.RUNNING else '',
                        log_url)
        if base_sha:
            skip_base = queue.record_base(run, base_sha)
            if skip_base is None:
                return _error(409, 'Run %d already has base %s.' % (
                    run.pk, run.base_sha))
        if status == PRRun.COMPLETED:
            queue.complete(run, _run_url(request, run))
        elif status == PRRun.FAILED:
            queue.fail(run, message)
        run.refresh_from_db()
    elif run.status != PRRun.CANCELLED:
        # Finished, timed out or never claimed: the runner is out of step
        return _error(409, 'Run %d is %s.' % (run.pk, run.status))

    answer = {
        'status': run.status,
        'cancelled': run.status == PRRun.CANCELLED,
    }
    if skip_base is not None:
        answer['skip_base'] = skip_base
    return JsonResponse(answer)
