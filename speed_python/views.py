"""Views specific to speed.python.org."""
import json
import logging
import math
from datetime import timedelta

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_GET

from codespeed.models import Branch, Environment, Executable, Result

logger = logging.getLogger(__name__)

# Length of the window shown by the home page geometric mean trend
HOME_GEOMEAN_DAYS = 30

# Results arrive a few times a day at most, so the home page trend can be
# cached rather than recomputed on every visit.
HOME_GEOMEAN_CACHE_SECONDS = 60 * 60


def _resolve_geomean_series(spec):
    exes = Executable.objects.filter(name=spec.get('executable'))
    if spec.get('project'):
        exes = exes.filter(project__name=spec['project'])

    exe = exes.select_related('project').first()
    env = Environment.objects.filter(name=spec.get('environment')).first()
    if exe is None or env is None:
        return None

    branch_name = spec.get('branch') or exe.project.default_branch
    branch = Branch.objects.filter(project=exe.project, name=branch_name).first()
    if branch is None:
        return None

    return exe, env, branch


@cache_page(HOME_GEOMEAN_CACHE_SECONDS)
@require_GET
def gethomegeomeandata(request):
    """Geometric mean of all benchmarks per revision, for the home page trend.

    For each configured series the values are normalised to the earliest
    revision inside the window, so every line starts at 1.0 and a value of
    0.95 means "5% faster than at the start of the window". Only benchmarks
    present in both that first revision and the revision at hand are used, so
    a benchmark that fails on one run does not move the line.
    """
    days = HOME_GEOMEAN_DAYS
    since = timezone.now() - timedelta(days=days)
    data = {'days': days, 'series': []}

    for spec in getattr(settings, 'HOME_GEOMEAN_SERIES', None) or []:
        resolved = _resolve_geomean_series(spec)
        if resolved is None:
            logger.warning("HOME_GEOMEAN_SERIES entry %r matches no "
                           "executable, environment or branch", spec)
            continue
        exe, env, branch = resolved

        rows = Result.objects.filter(
            executable=exe, environment=env, revision__branch=branch,
            revision__date__gte=since, value__gt=0,
        ).values_list('revision_id', 'revision__date', 'revision__commitid',
                      'benchmark_id', 'value')

        by_rev = {}
        for rev_id, date, commitid, bench_id, value in rows:
            entry = by_rev.setdefault(
                rev_id, {'date': date, 'commitid': commitid, 'values': {}})
            entry['values'][bench_id] = value
        revisions = sorted(by_rev.values(), key=lambda r: r['date'])

        points = []
        if revisions:
            baseline = revisions[0]['values']
            for rev in revisions:
                common = [b for b in rev['values'] if b in baseline]
                if not common:
                    continue
                logs = [math.log(rev['values'][b] / baseline[b]) for b in common]
                ratio = math.exp(sum(logs) / len(logs))
                points.append([rev['date'].strftime('%Y/%m/%d %H:%M:%S %z'),
                               round(ratio, 4), rev['commitid'], len(common)])

        data['series'].append({
            'label': '%s @ %s' % (exe.name, env.name),
            'executable': exe.id,
            'environment': env.id,
            'branch': branch.name,
            'baseline_commitid': revisions[0]['commitid'] if revisions else None,
            'points': points,
        })

    return HttpResponse(json.dumps(data), content_type='application/json')
