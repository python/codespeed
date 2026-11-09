"""Compare a pull request's results with its base, for the page and the
comment posted to the pull request."""
import math
import re

from django.conf import settings

from codespeed.models import Result

_UNSAFE = re.compile(r'[^\w.+\-]')


def comparison(run):
    """Base against pull request, benchmark by benchmark.

    Returns None while the pull request has no results. ``speedup`` is
    oriented so that above 1 always means the pull request is better,
    whichever way the benchmark's units run.
    """
    def results(commitid):
        found = Result.objects.filter(
            revision__commitid=commitid,
            revision__branch__project=run.project,
            executable=run.executable,
            environment=run.runner.environment,
        ).select_related('benchmark')
        names = run.benchmark_list
        if names:
            found = found.filter(benchmark__name__in=names)
        return {r.benchmark_id: r for r in found}

    head = results(run.head_sha)
    if not head:
        return None
    base = results(run.base_sha) if run.base_sha else {}

    threshold = getattr(settings, 'CHANGE_THRESHOLD', None) or 3.0
    rows, missing = [], []
    for benchmark_id, new in head.items():
        benchmark = new.benchmark
        old = base.get(benchmark_id)
        if old is None or old.value <= 0 or new.value <= 0:
            missing.append(benchmark.name)
            continue
        if benchmark.lessisbetter:
            speedup = old.value / new.value
        else:
            speedup = new.value / old.value
        change = (new.value - old.value) / old.value * 100
        rows.append({
            'name': benchmark.name,
            'units': benchmark.units,
            'base': old.value,
            'head': new.value,
            'change': change,
            'speedup': speedup,
            'significant': abs(change) >= threshold,
            'better': speedup > 1,
        })
    rows.sort(key=lambda row: row['name'])

    geomean = None
    if rows:
        geomean = math.exp(
            sum(math.log(row['speedup']) for row in rows) / len(rows))
    significant = [row for row in rows if row['significant']]
    return {
        'rows': rows,
        'missing': sorted(missing),
        'geomean': geomean,
        'threshold': threshold,
        'faster': sum(1 for row in significant if row['better']),
        'slower': sum(1 for row in significant if not row['better']),
        'unchanged': len(rows) - len(significant),
    }


def format_value(value, units):
    if units in ('seconds', 's'):
        for factor, unit in ((1, 's'), (1e-3, 'ms'), (1e-6, 'us')):
            if value >= factor:
                return '%.3g %s' % (value / factor, unit)
        return '%.3g ns' % (value / 1e-9)
    return '%.4g %s' % (value, units)


def format_speedup(speedup):
    if speedup is None:
        return 'n/a'
    if round(speedup, 2) == 1:
        return 'no change'
    if speedup > 1:
        return '%.2fx faster' % speedup
    return '%.2fx slower' % (1 / speedup)


def _code(text):
    """`text` as inline code. Names and labels arrive from uploads, so
    anything that could break out of the code span or the table is dropped."""
    return '`%s`' % _UNSAFE.sub('?', text)


def _table(rows):
    lines = ['| Benchmark | Base | PR | Change |', '|:--|--:|--:|:--|']
    for row in rows:
        lines.append('| %s | %s | %s | %s |' % (
            _code(row['name']),
            format_value(row['base'], row['units']),
            format_value(row['head'], row['units']),
            format_speedup(row['speedup'])))
    return '\n'.join(lines)


def markdown(run, data, run_url):
    """The comment posted to the pull request."""
    out = [
        '### Benchmark results: %s on %s' % (
            _code(run.executable.name), _code(run.runner.environment.name)),
        '',
        'Comparing %s with its merge base %s on %s.' % (
            run.head_sha, run.base_sha, _code(run.base_branch)),
        '',
    ]
    if not data['rows']:
        out.append('The base commit has no results to compare against.')
    else:
        out.append(
            '**Geometric mean: %s** across %d benchmarks: %d faster, '
            '%d slower, %d within %g%%.' % (
                format_speedup(data['geomean']), len(data['rows']),
                data['faster'], data['slower'], data['unchanged'],
                data['threshold']))
        # Regressions first: they are what a reviewer needs to see
        significant = sorted(
            (row for row in data['rows'] if row['significant']),
            key=lambda row: row['speedup'])
        rest = [row for row in data['rows'] if not row['significant']]
        if significant:
            out += ['', _table(significant)]
        if rest:
            out += ['', '<details>',
                    '<summary>%d within %g%%</summary>' % (
                        len(rest), data['threshold']),
                    '', _table(rest), '', '</details>']
    if data['missing']:
        out += ['', 'No base result for: %s.' % ', '.join(
            _code(name) for name in data['missing'])]
    out += ['', '[Full results](%s), requested by %s.' % (
        run_url, _UNSAFE.sub('', run.requested_by_login) or 'an administrator')]
    return '\n'.join(out)
