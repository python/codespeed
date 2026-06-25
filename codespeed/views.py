# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

import json
import logging
import os
import subprocess

import django
from django.conf import settings
from django.urls import reverse
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.http import HttpResponse, Http404, HttpResponseBadRequest, \
    HttpResponseNotFound, StreamingHttpResponse
from django.db.models import F
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.generic.base import TemplateView

from .auth import basic_auth_required
from .models import (Environment, Report, Project, Revision, Result,
                     Executable, Benchmark, Branch)
from .views_data import (get_default_environment, getbaselineexecutables,
                         getdefaultexecutable, getcomparisonexes,
                         get_benchmark_results, get_num_revs_and_benchmarks,
                         get_stats_with_defaults)
from .results import save_result, create_report_if_enough_data
from . import commits
from .validators import validate_results_request
from .images import gen_image_from_results

logger = logging.getLogger(__name__)


def no_environment_error(request):
    admin_url = reverse('admin:codespeed_environment_changelist')
    return render(request, 'codespeed/nodata.html', {
        'message': ('You need to configure at least one Environment. '
                    'Please go to the '
                    '<a href="%s">admin interface</a>' % admin_url)
    })


def no_default_project_error(request):
    admin_url = reverse('admin:codespeed_project_changelist')
    return render(request, 'codespeed/nodata.html', {
        'message': ('You need to configure at least one one Project as '
                    'default (checked "Track changes" field).<br />'
                    'Please go to the '
                    '<a href="%s">admin interface</a>' % admin_url)
    })


def no_executables_error(request):
    return render(request, 'codespeed/nodata.html', {
        'message': 'There needs to be at least one executable'
    })


def no_data_found(request):
    return render(request, 'codespeed/nodata.html', {
        'message': 'No data found'
    })


class HomeView(TemplateView):
    template_name = "home.html"

    def get_context_data(self, **kwargs):
        context = super(HomeView, self).get_context_data(**kwargs)
        context['show_reports'] = settings.SHOW_REPORTS
        context['show_historical'] = settings.SHOW_HISTORICAL
        historical_settings = ['SHOW_HISTORICAL', 'DEF_BASELINES', 'DEF_EXECUTABLES']
        if not all(getattr(settings, var) for var in historical_settings):
            context['show_historical'] = False
            return context

        try:
            baseline_exe = Executable.objects.get(
                name=settings.DEF_BASELINES[0]['executable'])
            context['baseline'] = baseline_exe
            def_name = settings.DEF_EXECUTABLES[0]['name']
            def_project = Project.objects.get(name=settings.DEF_EXECUTABLES[0]['project'])
            default_exe = Executable.objects.get(name=def_name,
                                                 project=def_project,
                                                )
            context['default_exe'] = default_exe
            return context
        except Exception as e:
            print('exception', e)
            context['show_historical'] = False
            return context


@require_GET
@xframe_options_exempt
def embed_comparison(request):
    """Frame-exempt page rendering only the baseline-comparison
    for embedding on pypy.org"""
    context = {}
    try:
        context['baseline'] = Executable.objects.get(
            name=settings.DEF_BASELINES[0]['executable'])
        def_name = settings.DEF_EXECUTABLES[0]['name']
        def_project = Project.objects.get(name=settings.DEF_EXECUTABLES[0]['project'])
        context['default_exe'] = Executable.objects.get(
            name=def_name, project=def_project)
    except Exception as e:
        logger.error('embed_comparison: %s', e)
    return render(request, 'embed_comparison.html', context)


@require_GET
def gethistoricaldata(request):
    data = {'results': {}, 'benchmarks': []}
    env = Environment.objects.all()
    if settings.DEF_ENVIRONMENT:
        env = env.get(name=settings.DEF_ENVIRONMENT)
    else:
        env = env.first()

    # Fetch Baseline data, filter by executable
    baseline_results = []
    for b in settings.DEF_BASELINES:
        baseline_exe = Executable.objects.get(
            name=b['executable'])
        tag=b['revision']
        rev = Revision.objects.filter(branch__project=baseline_exe.project, tag=tag)
        if len(rev) < 1:
            return HttpResponse(json.dumps(
                f"Could not find {tag=} for {b['executable']} in database")
            )
        rev0 = rev[0]
        resname = '{} {}'.format(b['executable'], rev0.tag)
        baseline_results.append((resname, Result.objects.filter(
            executable=baseline_exe, revision=rev0, environment=env,
            benchmark__source='legacy')))
        if not baseline_results[-1][1]:
            logger.error('Could not find results for {} rev="{}" env="{}"'.format(
                    baseline_exe, rev0, env))

    default_results = {}
    all_taggedrevs = []
    for executable in settings.DEF_EXECUTABLES[::-1]:
        _def_name = executable['name']
        _def_project = Project.objects.get(name=executable['project'])
        _default_exe = Executable.objects.get(name=_def_name, project=_def_project)
        _default_branch = Branch.objects.get(
            name=_default_exe.project.default_branch,
            project=_default_exe.project)

        # Fetch tagged revisions for executable
        default_taggedrevs = Revision.objects.filter(
                branch=_default_branch
            ).exclude(tag="").order_by('date')
        all_taggedrevs += default_taggedrevs
        for rev in default_taggedrevs:
            # Filter to legacy only; pyperformance history can get its own panel later
            res = Result.objects.filter(
                executable=_default_exe, revision=rev, environment=env,
                benchmark__source='legacy')
            if not res:
                logger.info("no results for '%s' '%s' '%s'" % (str(_default_exe), str(rev), str(env)))
                continue
            default_results[rev.tag] = res
    data['tagged_revs'] = [rev.tag for rev in all_taggedrevs if rev.tag in default_results]
    # Fetch data for latest results
    executable = settings.DEF_EXECUTABLES[0]
    def_name = executable['name']
    def_project = Project.objects.get(name=executable['project'])
    default_exe = Executable.objects.get(name=def_name, project=def_project)
    default_branch = Branch.objects.get(
            name=default_exe.project.default_branch,
            project=default_exe.project)
    revs = Revision.objects.filter(
        branch=default_branch).order_by('-date')[:100]
    default_lastrev = None
    for rev in revs:
        default_lastrev = rev
        if default_lastrev.results.filter(executable=default_exe, environment=env):
            break
        default_lastrev = None
    if default_lastrev is not None:
        default_results['latest'] = Result.objects.filter(
            executable=default_exe, revision=default_lastrev, environment=env,
            benchmark__source='legacy')

    # Collect data
    benchmarks = []
    # Collate first baseline and all the default_results
    resset = baseline_results[0][1]
    resname = baseline_results[0][0]
    data['baseline'] = resname
    for res in resset:
        if res == 0:
            continue
        benchmarks.append(res.benchmark.name)
        data['results'][res.benchmark.name] = {resname: res.value}
        for rev_name in default_results:
            val = 0
            for default_res in default_results[rev_name]:
                if default_res.benchmark.name == res.benchmark.name:
                    val = default_res.value
                data['results'][res.benchmark.name][rev_name] = val
    # Collate other baseline
    for resname, resset in baseline_results[1:]:
        for res in resset:
            if res == 0:
                continue
            if not res.benchmark.name in data['results']:
                continue
            data['results'][res.benchmark.name][resname] = res.value
        data['tagged_revs'].insert(0, resname)
    benchmarks.sort()
    data['benchmarks'] = benchmarks
    return HttpResponse(json.dumps(data))


def _normalize_exe_key(key):
    """Normalize old + separator to : for backwards URL compatibility."""
    return key.replace('+', ':')


def _parse_ben_param(ben_val):
    """Parse the ben= query parameter. Returns a queryset/list or None for 'all'.

    Accepts: 'all', source slugs ('legacy', 'pyperformance', 'legacy,pyperformance'),
    or comma-separated numeric IDs (legacy behaviour).
    """
    if not ben_val or ben_val == 'all':
        return None  # caller interprets None as "all benchmarks"
    parts = [p for p in ben_val.split(',') if p]
    source_vals = {sv for sv, _ in Benchmark.S_TYPES}
    if parts and all(p in source_vals for p in parts):
        return list(Benchmark.objects.filter(source__in=parts))
    result = []
    for i in parts:
        try:
            result.append(Benchmark.objects.get(id=int(i)))
        except (Benchmark.DoesNotExist, ValueError):
            pass
    return result


@require_GET
def getcomparisondata(request):
    executables, exekeys = getcomparisonexes()

    requested_exes = None
    if 'exe' in request.GET:
        requested_exes = set(
            _normalize_exe_key(i) for i in request.GET['exe'].split(",")
            if i and _normalize_exe_key(i) in exekeys
        )

    benchmarks = Benchmark.objects.all()
    if 'ben' in request.GET:
        result = _parse_ben_param(request.GET['ben'])
        if result is not None:
            benchmarks = benchmarks.filter(id__in=[b.id for b in result])

    environments = Environment.objects.all()

    compdata = {}
    compdata['error'] = "Unknown error"
    suite_versions = {}  # exe_key -> env_id -> sorted list of unique non-empty versions
    for proj in executables:
        for exe in executables[proj]:
            if requested_exes is not None and exe['key'] not in requested_exes:
                continue
            compdata[exe['key']] = {}
            suite_versions[exe['key']] = {}
            for env in environments:
                compdata[exe['key']][env.id] = {}

                # Load all results for this env/executable/revision in a
                # dict for fast lookup
                rows = Result.objects.filter(
                    environment=env,
                    executable=exe['executable'],
                    revision=exe['revision'],
                ).values_list('benchmark', 'value', 'suite_version')

                results = {}
                env_versions = set()
                for bench_id, value, sv in rows:
                    results[bench_id] = value
                    if sv:
                        env_versions.add(sv)

                for bench in benchmarks:
                    compdata[exe['key']][env.id][bench.id] = results.get(
                        bench.id, None)
                suite_versions[exe['key']][env.id] = sorted(env_versions)

    compdata['suite_versions'] = suite_versions
    compdata['error'] = "None"

    return HttpResponse(json.dumps(compdata))


@require_GET
def comparison(request):
    data = request.GET

    # Configuration of default parameters
    enviros = Environment.objects.all()
    if not enviros:
        return no_environment_error(request)
    checkedenviros = get_default_environment(enviros, data)

    if not len(Project.objects.filter(track=True)):
        return no_default_project_error(request)

    # Check whether there exist appropiate executables
    if not getdefaultexecutable():
        return no_executables_error(request)

    executables, exekeys = getcomparisonexes()
    checkedexecutables = []
    if 'exe' in data:
        for i in data['exe'].split(","):
            if not i:
                continue
            i = _normalize_exe_key(i)
            if i in exekeys:
                checkedexecutables.append(i)
    elif hasattr(settings, 'COMP_EXECUTABLES') and settings.COMP_EXECUTABLES:
        for exe, rev in settings.COMP_EXECUTABLES:
            try:
                exe = Executable.objects.get(name=exe)
                key = str(exe.id) + ":"
                if rev == "L":
                    key += rev
                else:
                    rev = Revision.objects.get(commitid=rev)
                    key += str(rev.id)
                key += ":%s" % (exe.project.default_branch)
                if key in exekeys:
                    checkedexecutables.append(key)
                else:
                    #TODO: log
                    pass
            except Executable.DoesNotExist:
                #TODO: log
                pass
            except Revision.DoesNotExist:
                #TODO: log
                pass
    if not checkedexecutables:
        if hasattr(settings, 'DEF_EXECUTABLES') and settings.DEF_EXECUTABLES:
            for exe_spec in settings.DEF_EXECUTABLES:
                try:
                    proj = Project.objects.get(name=exe_spec['project'])
                    exe = Executable.objects.get(name=exe_spec['name'], project=proj)
                    for key in exekeys:
                        if key.startswith(str(exe.id) + ":L:"):
                            checkedexecutables.append(key)
                            break
                except (Executable.DoesNotExist, Project.DoesNotExist):
                    pass
        if (not checkedexecutables and
                hasattr(settings, 'DEF_BASELINES') and settings.DEF_BASELINES):
            baselines = getbaselineexecutables()
            for base_spec in settings.DEF_BASELINES:
                for base in baselines:
                    if base['key'] == "none":
                        continue
                    if (base['executable'].name == base_spec['executable'] and
                            base['revision'].commitid == base_spec['revision']):
                        if base['key'] in exekeys:
                            checkedexecutables.append(base['key'])
                        break
    if not checkedexecutables:
        checkedexecutables = exekeys

    benchmarks = {}
    bench_units = {}
    for source_val, source_label in Benchmark.S_TYPES:
        qs = Benchmark.objects.filter(source=source_val)
        if not qs.exists():
            continue
        benchmarks[source_label] = qs
        for unit in qs.values_list('units_title', flat=True).distinct():
            unit_qs = qs.filter(units_title=unit)
            ids = [b.id for b in unit_qs]
            if unit in bench_units:
                bench_units[unit][0].extend(ids)
            else:
                units = unit_qs[0].units
                lessisbetter = (unit_qs[0].lessisbetter and
                                ' (less is better)' or ' (more is better)')
                bench_units[unit] = [ids, lessisbetter, units]
    checkedbenchmarks = []
    if 'ben' in data:
        checkedbenchmarks = _parse_ben_param(data['ben'])
        if checkedbenchmarks is None:
            checkedbenchmarks = list(Benchmark.objects.all())
    if not checkedbenchmarks:
        checkedbenchmarks = Benchmark.objects.filter(default_on_comparison=True)

    charts = ['normal bars', 'stacked bars', 'relative bars']
    # Don't show relative charts as an option if there is only one executable
    # Relative charts need normalization
    if len(executables) == 1:
        charts.remove('relative bars')

    selectedchart = charts[0]
    if 'chart' in data and data['chart'] in charts:
        selectedchart = data['chart']
    elif hasattr(settings, 'CHART_TYPE') and settings.CHART_TYPE in charts:
        selectedchart = settings.CHART_TYPE

    selectedbaseline = "none"
    if 'bas' in data:
        bas = _normalize_exe_key(data['bas'])
        if bas in exekeys:
            selectedbaseline = bas
        elif '@' in bas and bas.split('@')[0] in exekeys:
            selectedbaseline = bas  # cross-env baseline: {exe_key}@{env_id}
        # else: bas=none or unrecognised — skip NORMALIZATION default below
    elif (len(exekeys) > 1 and hasattr(settings, 'NORMALIZATION') and
            settings.NORMALIZATION):
        try:
            # TODO: Avoid calling twice getbaselineexecutables
            selectedbaseline = getbaselineexecutables()[1]['key']
            # Uncheck exe used for normalization
            try:
                checkedexecutables.remove(selectedbaseline)
            except ValueError:
                pass  # The selected baseline was not checked
        except:
            pass  # Keep "none" as default baseline

    if selectedbaseline == "none" and 'bas' not in data:
        if hasattr(settings, 'DEF_EXECUTABLES') and settings.DEF_EXECUTABLES:
            try:
                exe_spec = settings.DEF_EXECUTABLES[0]
                proj = Project.objects.get(name=exe_spec['project'])
                exe = Executable.objects.get(name=exe_spec['name'], project=proj)
                for key in exekeys:
                    if key.startswith(str(exe.id) + ":L:") and key in checkedexecutables:
                        selectedbaseline = key
                        break
            except (Executable.DoesNotExist, Project.DoesNotExist):
                pass

    selecteddirection = False
    if ('hor' in data and data['hor'] == "true" or
        hasattr(settings, 'CHART_ORIENTATION') and
            settings.CHART_ORIENTATION == 'horizontal'):
        selecteddirection = True

    return render(request, 'codespeed/comparison.html', {
        'checkedexecutables': checkedexecutables,
        'checkedbenchmarks': checkedbenchmarks,
        'checkedenviros': checkedenviros,
        'executables': executables,
        'benchmarks': benchmarks,
        'bench_units': json.dumps(bench_units),
        'enviros': enviros,
        'charts': charts,
        'selectedbaseline': selectedbaseline,
        'selectedchart': selectedchart,
        'selecteddirection': selecteddirection
    })

def get_setting(name, default = None):
    if hasattr(settings, name):
        return getattr(settings, name)
    else:
        return default


@require_GET
def gettimelinedata(request):
    data = request.GET

    timeline_list = {'error': 'None', 'timelines': []}

    executable_ids = data.get('exe', '').split(',')

    executables = []
    for i in executable_ids:
        if not i:
            continue
        try:
            executables.append(Executable.objects.get(id=int(i)))
        except Executable.DoesNotExist:
            pass

    if not executables:
        timeline_list['error'] = "No executables selected"
        return HttpResponse(json.dumps(timeline_list))

    environments = []
    for env_id in data.get('env', '').split(',')[:2]:
        if not env_id:
            continue
        try:
            environments.append(get_object_or_404(Environment, id=int(env_id)))
        except (ValueError, Http404):
            pass
    if not environments:
        timeline_list['error'] = "No environment selected"
        return HttpResponse(json.dumps(timeline_list))

    number_of_revs, benchmarks = get_num_revs_and_benchmarks(data)

    baseline_rev = None
    baseline_exe = None
    if data.get('base') not in (None, 'none', 'undefined'):
        exe_id, rev_id = data['base'].split(":")
        baseline_rev = Revision.objects.get(id=rev_id)
        baseline_exe = Executable.objects.get(id=exe_id)

    next_benchmarks = data.get('nextBenchmarks', False)
    if next_benchmarks is not False:
        next_benchmarks = int(next_benchmarks)

    resp = StreamingHttpResponse(stream_timeline(baseline_exe, baseline_rev, benchmarks, data,
                                                 environments, executables, number_of_revs,
                                                 next_benchmarks),
                                 content_type='application/json')
    return resp


def stream_timeline(baseline_exe, baseline_rev, benchmarks, data, environments, executables,
                    number_of_revs, next_benchmarks):
    yield '{"timelines": ['
    num_results = {"results": 0}
    num_benchmark = 0
    transmitted_benchmarks = 0
    timeline_grid_paging = get_setting('TIMELINE_GRID_PAGING', 10)

    for bench in benchmarks:
        if transmitted_benchmarks + 1 > timeline_grid_paging:
            # don't send more results than configured
            break

        num_benchmark += 1

        if not next_benchmarks or num_benchmark > next_benchmarks:
            result = get_timeline_for_benchmark(baseline_exe, baseline_rev, bench, environments,
                                                executables, number_of_revs, num_results)
            if result != "":
                transmitted_benchmarks += 1
                yield result

    if not next_benchmarks or (next_benchmarks < len(benchmarks)
                               and transmitted_benchmarks > 0):
        next_page = ', "nextBenchmarks": ' + str(num_benchmark)
    else:
        next_page = ', "nextBenchmarks": false'

    if next_benchmarks:
        not_first = ', "first": false'
    else:
        not_first = ', "first": true'

    if num_results['results'] == 0 and data['ben'] != 'show_none' and not next_benchmarks:
        yield ']' + not_first + next_page + ', "error":"No data found for the selected options"}\n'
    else:
        yield ']' + not_first + next_page + ', "error":"None"}\n'


def get_timeline_for_benchmark(baseline_exe, baseline_rev, bench, environments, executables,
                               number_of_revs, num_results):
    lessisbetter = bench.lessisbetter and ' (less is better)' or ' (more is better)'
    timeline = {
        'benchmark': bench.name,
        'benchmark_id': bench.id,
        'benchmark_description': bench.description,
        'data_type': bench.data_type,
        'units': bench.units,
        'lessisbetter': lessisbetter,
        'branches': {},
        'baseline': "None",
        'environments': [{'id': env.id, 'name': env.name} for env in environments],
    }
    append = False
    for branch in Branch.objects.filter(
            project__track=True, name=F('project__default_branch')):
        for environment in environments:
            for executable in executables:
                if executable.project != branch.project:
                    continue

                resultquery = Result.objects.filter(
                    benchmark=bench,
                    environment=environment,
                    executable=executable,
                    revision__branch=branch,
                ).select_related(
                    "revision"
                ).order_by('-revision__date')[:number_of_revs]
                if not len(resultquery):
                    continue
                timeline['branches'].setdefault(branch.name, {})

                results = []
                for res in resultquery:
                    if bench.data_type == 'M':
                        q1, q3, val_max, val_min = get_stats_with_defaults(res)
                        results.append([
                            res.revision.date.strftime('%Y/%m/%d %H:%M:%S %z'),
                            res.value, val_max, q3, q1, val_min,
                            res.revision.get_short_commitid(), res.revision.tag, branch.name,
                            res.suite_version,
                        ])
                    else:
                        std_dev = ""
                        if res.std_dev is not None:
                            std_dev = res.std_dev
                        results.append([
                            res.revision.date.strftime('%Y/%m/%d %H:%M:%S %z'),
                            res.value, std_dev,
                            res.revision.get_short_commitid(), res.revision.tag, branch.name,
                            res.suite_version,
                        ])
                # Key is "exe_id:env_id" so multiple environments render as separate series
                timeline['branches'][branch.name][f"{executable.id}:{environment.id}"] = results
                append = True
    if baseline_rev is not None and append:
        try:
            baselinevalue = Result.objects.get(
                executable=baseline_exe,
                benchmark=bench,
                revision=baseline_rev,
                environment=environments[0],
            ).value
        except Result.DoesNotExist:
            timeline['baseline'] = "None"
        else:
            results = []
            for branch in timeline['branches']:
                for key in timeline['branches'][branch]:
                    if len(timeline['branches'][branch][key]) > len(results):
                        results = timeline['branches'][branch][key]
            end = results[0][0]
            start = results[len(results) - 1][0]
            timeline['baseline'] = [
                [str(start), baselinevalue],
                [str(end), baselinevalue]
            ]
    if append:
        old_num_results = num_results['results']
        json_str = json.dumps(timeline)
        num_results['results'] = old_num_results + len(timeline)

        if old_num_results > 0:
            return "," + json_str
        else:
            return json_str
    else:
        return ""


@require_GET
def timeline(request):
    data = request.GET

    # Configuration of default parameters #
    # Default Environment
    enviros = Environment.objects.all()
    if not enviros:
        return no_environment_error(request)
    defaultenviro = get_default_environment(enviros, data)
    if 'env' in data:
        defaultenvironments = get_default_environment(enviros, data, multi=True)[:2]
    else:
        defaultenvironments = defaultenviro  # already respects DEF_ENVIRONMENT

    # Default Project
    defaultproject = Project.objects.filter(track=True)
    if not len(defaultproject):
        return no_default_project_error(request)
    else:
        defaultproject = defaultproject[0]

    checkedexecutables = []
    if 'exe' in data:
        for i in data['exe'].split(","):
            if not i:
                continue
            try:
                checkedexecutables.append(Executable.objects.get(id=int(i)))
            except Executable.DoesNotExist:
                pass

    if not checkedexecutables:
        if hasattr(settings, 'DEF_EXECUTABLES') and settings.DEF_EXECUTABLES:
            for def_exe in settings.DEF_EXECUTABLES:
                try:
                    proj = Project.objects.get(name=def_exe['project'])
                    checkedexecutables.append(
                        Executable.objects.get(name=def_exe['name'], project=proj))
                except (Project.DoesNotExist, Executable.DoesNotExist):
                    pass
    if not checkedexecutables:
        checkedexecutables = Executable.objects.filter(project__track=True)

    if not len(checkedexecutables):
        return no_executables_error(request)

    # TODO: we need branches for all tracked projects
    branch_list = [
        branch.name for branch in Branch.objects.filter(project=defaultproject)]
    branch_list.sort()

    defaultbranch = ""
    if defaultproject.default_branch in branch_list:
        defaultbranch = defaultproject.default_branch
    if data.get('bran') in branch_list:
        defaultbranch = data.get('bran')

    baseline = getbaselineexecutables()
    defaultbaseline = None
    if len(baseline) > 1:
        defaultbaseline = str(baseline[1]['executable'].id) + "+"
        defaultbaseline += str(baseline[1]['revision'].id)
    if "base" in data and data['base'] != "undefined":
        try:
            defaultbaseline = data['base']
        except ValueError:
            pass

    lastrevisions = [10, 15, 50, 200]
    defaultlast = settings.DEF_TIMELINE_LIMIT
    if 'revs' in data and data['revs']:
        try:
            revs_int = int(data['revs'])
        except ValueError:
            revs_int = None
        if revs_int is not None:
            if revs_int not in lastrevisions:
                lastrevisions.append(revs_int)
            defaultlast = revs_int

    benchmarks = Benchmark.objects.all()

    defaultbenchmark = "grid"
    if not len(benchmarks):
        return no_data_found(request)
    elif len(benchmarks) == 1:
        defaultbenchmark = benchmarks[0]
    elif hasattr(settings, 'DEF_BENCHMARK') and settings.DEF_BENCHMARK is not None:
        if settings.DEF_BENCHMARK in ['grid', 'show_none']:
            defaultbenchmark = settings.DEF_BENCHMARK
        else:
            try:
                defaultbenchmark = Benchmark.objects.get(
                    name=settings.DEF_BENCHMARK)
            except Benchmark.DoesNotExist:
                pass
    elif len(benchmarks) >= get_setting('TIMELINE_GRID_LIMIT', 30):
        defaultbenchmark = 'show_none'

    if 'ben' in data and data['ben'] != defaultbenchmark:
        if data['ben'] == "show_none":
            defaultbenchmark = data['ben']
        else:
            defaultbenchmark = get_object_or_404(Benchmark, name=data['ben'])

    if 'equid' in data:
        defaultequid = data['equid']
    else:
        defaultequid = "off"
    if 'quarts' in data:
        defaultquarts = data['quarts']
    else:
        defaultquarts = "on"
    if 'extr' in data:
        defaultextr = data['extr']
    else:
        defaultextr = "on"

    # Information for template
    if defaultbenchmark in ['grid', 'show_none']:
        pagedesc = None
    else:
        pagedesc = "Results timeline for the '%s' benchmark (project %s)" % \
            (defaultbenchmark, defaultproject)
    executables = {}
    for proj in Project.objects.filter(track=True):
        executables[proj] = Executable.objects.filter(project=proj)
    use_median_bands = hasattr(settings, 'USE_MEDIAN_BANDS') and settings.USE_MEDIAN_BANDS
    return render(request, 'codespeed/timeline.html', {
        'pagedesc': pagedesc,
        'checkedexecutables': checkedexecutables,
        'defaultbaseline': defaultbaseline,
        'baseline': baseline,
        'defaultbenchmark': defaultbenchmark,
        'defaultenvironment': defaultenviro,
        'defaultenvironments': defaultenvironments,
        'lastrevisions': lastrevisions,
        'defaultlast': defaultlast,
        'executables': executables,
        'benchmarks': benchmarks,
        'environments': enviros,
        'branch_list': branch_list,
        'defaultbranch': defaultbranch,
        'defaultequid': defaultequid,
        'defaultquarts': defaultquarts,
        'defaultextr': defaultextr,
        'use_median_bands': use_median_bands,
    })


@require_GET
def getchangestable(request):
    executable = get_object_or_404(Executable, pk=request.GET.get('exe'))
    environment = get_object_or_404(Environment, pk=request.GET.get('env'))
    try:
        trendconfig = int(request.GET.get('tre'))
    except TypeError:
        raise Http404()
    selectedrev = get_object_or_404(Revision, commitid=request.GET.get('rev'),
                                    branch__project=executable.project)
    prevrev = Revision.objects.filter(
        branch=selectedrev.branch,
        date__lt=selectedrev.date,
    ).order_by('-date').first()
    if prevrev:
        try:
            summary = Report.objects.get(
                revision=prevrev,
                executable=executable,
                environment=environment).item_description
        except Report.DoesNotExist:
            summary = ''
        prevrev = {
            'desc': str(prevrev),
            'rev': prevrev.commitid,
            'short_rev': prevrev.get_short_commitid(),
            'summary': summary,
        }
    else:
        prevrev = None

    nextrev = Revision.objects.filter(
        branch=selectedrev.branch,
        date__gt=selectedrev.date,
    ).order_by('date').first()
    if nextrev:
        try:
            summary = Report.objects.get(
                revision=nextrev,
                executable=executable,
                environment=environment).item_description
        except Report.DoesNotExist:
            summary = ''
        nextrev = {
            'desc': str(nextrev),
            'rev': nextrev.commitid,
            'short_rev': nextrev.get_short_commitid(),
            'summary': summary,
        }
    else:
        nextrev = None

    report, created = Report.objects.get_or_create(
        executable=executable, environment=environment, revision=selectedrev
    )
    tablelist = report.get_changes_table(trendconfig)

    if not len(tablelist):
        return HttpResponse('<table id="results" class="tablesorter" '
                            'style="height: 232px;"></table>'
                            '<p class="errormessage">No results for this '
                            'parameters</p>')

    return render(request, 'codespeed/changes_data.html', {
        'tablelist': tablelist,
        'trendconfig': trendconfig,
        'rev': selectedrev,
        'exe': executable,
        'env': environment,
        'prev': prevrev,
        'next': nextrev,
    })


@require_GET
def changes(request):
    data = request.GET

    # Configuration of default parameters
    defaultchangethres = 3.0
    defaulttrendthres = 4.0
    if (hasattr(settings, 'CHANGE_THRESHOLD') and
            settings.CHANGE_THRESHOLD is not None):
        defaultchangethres = settings.CHANGE_THRESHOLD
    if (hasattr(settings, 'TREND_THRESHOLD') and
            settings.TREND_THRESHOLD is not None):
        defaulttrendthres = settings.TREND_THRESHOLD

    defaulttrend = 10
    trends = [5, 10, 20, 50, 100]
    if 'tre' in data and int(data['tre']) in trends:
        defaulttrend = int(data['tre'])

    enviros = Environment.objects.all()
    if not enviros:
        return no_environment_error(request)
    defaultenv = get_default_environment(enviros, data)

    if not len(Project.objects.filter(track=True)):
        return no_default_project_error(request)

    defaultexecutable = getdefaultexecutable()
    if not defaultexecutable:
        return no_executables_error(request)

    if "exe" in data:
        try:
            defaultexecutable = Executable.objects.get(id=int(data['exe']))
        except Executable.DoesNotExist:
            pass
        except ValueError:
            pass

    baseline = getbaselineexecutables()
    defaultbaseline = "+"
    if len(baseline) > 1:
        defaultbaseline = str(baseline[1]['executable'].id) + "+"
        defaultbaseline += str(baseline[1]['revision'].id)
    if "base" in data and data['base'] != "undefined":
        try:
            defaultbaseline = data['base']
        except ValueError:
            pass

    # Information for template
    revlimit = 20
    executables = {}
    revisionlists = {}
    projectlist = []
    for proj in Project.objects.filter(track=True):
        executables[proj] = Executable.objects.filter(project=proj)
        projectlist.append(proj)
        branch = Branch.objects.get(name=proj.default_branch, project=proj)
        revisionlists[proj.name] = list(Revision.objects.filter(
            branch=branch
        ).order_by('-date')[:revlimit])
    # Get lastest revisions for this project and it's "default" branch
    lastrevisions = revisionlists.get(defaultexecutable.project.name)
    if not len(lastrevisions):
        return no_data_found(request)
    selectedrevision = lastrevisions[0]

    if "rev" in data:
        commitid = data['rev']
        try:
            selectedrevision = Revision.objects.get(
                commitid__startswith=commitid, branch=branch
            )
            if selectedrevision not in revisionlists[selectedrevision.project.name]:
                revisionlists[selectedrevision.project.name].append(selectedrevision)
        except Revision.DoesNotExist:
            selectedrevision = lastrevisions[0]
    # This variable is used to know when the newly selected executable
    # belongs to another project (project changed) and then trigger the
    # repopulation of the revision selection selectbox
    projectmatrix = {}
    for proj in executables:
        for e in executables[proj]:
            projectmatrix[e.id] = e.project.name
    projectmatrix = json.dumps(projectmatrix)

    all_commitids = [rev.commitid for revisions in revisionlists.values() for rev in revisions]
    env_has_results = {}
    for env in enviros:
        has = set(Result.objects.filter(
            environment=env,
            revision__commitid__in=all_commitids,
        ).values_list('revision__commitid', flat=True).distinct())
        env_has_results[str(env.id)] = list(has)
    env_has_results = json.dumps(env_has_results)

    for project, revisions in revisionlists.items():
        revisionlists[project] = [
            (str(rev), rev.commitid) for rev in revisions
        ]
    revisionlists = json.dumps(revisionlists)

    pagedesc = "Report of %s performance changes for commit %s on branch %s" % \
        (defaultexecutable, selectedrevision.commitid, selectedrevision.branch)
    return render(request, 'codespeed/changes.html', {
        'pagedesc': pagedesc,
        'defaultenvironment': defaultenv,
        'defaultexecutable': defaultexecutable,
        'selectedrevision': selectedrevision,
        'defaulttrend': defaulttrend,
        'defaultchangethres': defaultchangethres,
        'defaulttrendthres': defaulttrendthres,
        'environments': enviros,
        'executables': executables,
        'projectmatrix': projectmatrix,
        'revisionlists': revisionlists,
        'env_has_results': env_has_results,
        'trends': trends,
    })


@require_GET
def reports(request):
    context = {}

    context['reports'] = \
        Report.objects.order_by('-revision__date')[:10]

    context['significant_reports'] = Report.objects.filter(
        colorcode__in=('red', 'green')
    ).order_by('-revision__date')[:10]

    return render(request, 'codespeed/reports.html', context)


@require_GET
def displaylogs(request):
    rev = get_object_or_404(Revision, pk=request.GET.get('revisionid'))
    logs = []
    logs.append(
        {
            'date': str(rev.date), 'author': rev.author,
            'author_email': '', 'message': rev.message,
            'short_commit_id': rev.get_short_commitid(),
            'commitid': rev.commitid
        }
    )
    error = False
    try:
        startrev = Revision.objects.filter(
            branch=rev.branch
        ).filter(date__lt=rev.date).order_by('-date')[:1]
        if not len(startrev):
            startrev = rev
        else:
            startrev = startrev[0]

        remotelogs = commits.get_logs(rev, startrev)
        if len(remotelogs):
            try:
                if remotelogs[0]['error']:
                    error = remotelogs[0]['message']
            except KeyError:
                pass  # no errors
            logs = remotelogs
        else:
            error = 'No logs found'
    except commits.exceptions.CommitLogError as e:
        logger.error('Unhandled exception displaying logs for %s: %s',
                     rev, e, exc_info=True)
        error = str(e)

    # Add commit browsing url to logs
    project = rev.branch.project
    for log in logs:
        log['commit_browse_url'] = project.commit_browsing_url.format(**log)

    return render(
        request,
        'codespeed/changes_logs.html',
        {
            'error': error, 'logs': logs,
            'show_email_address': settings.SHOW_AUTHOR_EMAIL_ADDRESS
        })


@csrf_exempt
@require_POST
@basic_auth_required('results')
def add_result(request):
    response, error = save_result(request.POST)
    if error:
        logger.error("Could not save result: " + response)
        return HttpResponseBadRequest(response)
    else:
        create_report_if_enough_data(response[0], response[1], response[2])
        return HttpResponse("Result data saved successfully", status=202)


@csrf_exempt
@require_POST
@basic_auth_required('results')
def add_json_results(request):
    if not request.POST.get('json'):
        return HttpResponseBadRequest("No key 'json' in POST payload")
    data = json.loads(request.POST['json'])
    logger.info("add_json_results request with %d entries." % len(data))

    unique_reports = set()
    for (i, result) in enumerate(data):
        logger.debug("add_json_results: save item %d." % i)
        response, error = save_result(result, update_repo=(i==0))
        if error:
            logger.debug(
                "add_json_results: could not save item %d because %s" % (
                    i, response))
            return HttpResponseBadRequest(response)
        else:
            unique_reports.add(response)

    for rep in unique_reports:
        create_report_if_enough_data(rep[0], rep[1], rep[2])

    return HttpResponse("All result data saved successfully", status=202)

def django_has_content_type():
    return (django.VERSION[0] > 1 or
            (django.VERSION[0] == 1 and django.VERSION[1] >= 6))


@require_GET
def makeimage(request):
    data = request.GET

    try:
        validate_results_request(data)
    except ValidationError as err:
        return HttpResponseBadRequest(str(err))

    try:
        result_data = get_benchmark_results(data)
    except ObjectDoesNotExist as err:
        return HttpResponseNotFound(str(err))

    image_data = gen_image_from_results(
                    result_data,
                    int(data['width']) if 'width' in data else None,
                    int(data['height']) if 'height' in data else None)

    if django_has_content_type():
        response = HttpResponse(content=image_data, content_type='image/png')
    else:
        response = HttpResponse(content=image_data, mimetype='image/png')

    response['Content-Length'] = len(image_data)
    response['Content-Disposition'] = 'attachment; filename=image.png'


def _get_current_commit():
    try:
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'],
            cwd=repo_root,
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return None

_CURRENT_COMMIT = _get_current_commit()


def about(request):
    return render(request, 'about.html', {'commit': _CURRENT_COMMIT})

    return response
