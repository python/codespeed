from datetime import datetime, timedelta
import copy
import json

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from codespeed.models import (Project, Benchmark, Revision, Branch, Executable,
                              Environment, Result, Report)


@override_settings(ALLOW_ANONYMOUS_POST=True)
class TestAddResult(TestCase):

    def setUp(self):
        self.path = reverse('add-result')
        self.e = Environment.objects.create(name='Dual Core',
                                            cpu='Core 2 Duo 8200')
        temp = datetime.today()
        self.cdate = datetime(
            temp.year, temp.month, temp.day,
            temp.hour, temp.minute, temp.second)
        self.data = {
            'commitid': '23',
            'branch': 'default',
            'project': 'MyProject',
            'executable': 'myexe O3 64bits',
            'benchmark': 'float',
            'environment': 'Dual Core',
            'result_value': 456,
            'source': 'legacy',
        }

    def test_add_correct_result(self):
        """Add correct result data"""
        response = self.client.post(self.path, self.data)

        # Check that we get a success response
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.content.decode(), "Result data saved successfully")

        # Check that the data was correctly saved
        e = Environment.objects.get(name='Dual Core')
        b = Benchmark.objects.get(name='float')
        self.assertEqual(b.source, "legacy")
        self.assertEqual(b.units, "seconds")
        self.assertEqual(b.lessisbetter, True)
        p = Project.objects.get(name='MyProject')
        branch = Branch.objects.get(name='default', project=p)
        r = Revision.objects.get(commitid='23', branch=branch)
        i = Executable.objects.get(name='myexe O3 64bits')
        res = Result.objects.get(
            revision=r,
            executable=i,
            benchmark=b,
            environment=e
        )
        self.assertTrue(res.value, 456)

    def test_add_non_default_result(self):
        """Add result data with non-mandatory options"""
        modified_data = copy.deepcopy(self.data)
        revision_date = self.cdate - timedelta(minutes=2)
        modified_data['revision_date'] = revision_date
        result_date = self.cdate + timedelta(minutes=2)
        modified_data['result_date'] = result_date
        modified_data['std_dev'] = 1.11111
        modified_data['max'] = 2
        modified_data['min'] = 1.0
        response = self.client.post(self.path, modified_data)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.content.decode(), "Result data saved successfully")
        e = Environment.objects.get(name='Dual Core')
        p = Project.objects.get(name='MyProject')
        branch = Branch.objects.get(name='default', project=p)
        r = Revision.objects.get(commitid='23', branch=branch)

        # Tweak the resolution down to avoid failing over very slight differences:
        self.assertEqual(r.date, timezone.make_aware(revision_date))

        i = Executable.objects.get(name='myexe O3 64bits')
        b = Benchmark.objects.get(name='float')
        res = Result.objects.get(
            revision=r,
            executable=i,
            benchmark=b,
            environment=e
        )
        self.assertEqual(res.date, timezone.make_aware(result_date))
        self.assertEqual(res.std_dev, 1.11111)
        self.assertEqual(res.val_max, 2)
        self.assertEqual(res.val_min, 1)

    def test_bad_environment(self):
        """Should return 400 when environment does not exist"""
        bad_name = '10 Core'
        self.data['environment'] = bad_name
        response = self.client.post(self.path, self.data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content.decode(),
                         "Environment " + bad_name + " not found")
        self.data['environment'] = 'Dual Core'

    def test_empty_argument(self):
        """Should respond 400 when a POST request has an empty argument"""
        for key in self.data:
            if key == 'source':  # optional, defaults to 'legacy'
                continue
            backup = self.data[key]
            self.data[key] = ""
            response = self.client.post(self.path, self.data)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(
                response.content.decode(),
                'Value for key "' + key + '" empty in request')
            self.data[key] = backup

    def test_missing_argument(self):
        """Should respond 400 when a POST request is missing an argument"""
        for key in list(self.data):
            if key == 'source':  # optional, defaults to 'legacy'
                continue
            backup = self.data[key]
            del self.data[key]
            response = self.client.post(self.path, self.data)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(
                response.content.decode(),
                'Key "' + key + '" missing from request')
            self.data[key] = backup

    def test_report_is_not_created(self):
        """Should not create a report when adding a single result"""
        self.client.post(self.path, self.data)
        number_of_reports = len(Report.objects.all())
        # After adding one result for one revision, there should be no reports
        self.assertEqual(number_of_reports, 0)

    def test_report_is_created(self):
        """Should create a report when adding a result for two revisions"""
        # First result does not create report
        self.client.post(self.path, self.data)

        modified_data = copy.deepcopy(self.data)
        modified_data['commitid'] = "23233"
        # Second result should trigger report creation
        self.client.post(self.path, modified_data)
        number_of_reports = len(Report.objects.all())
        self.assertEqual(number_of_reports, 1)

    def test_submit_data_with_none_timestamp(self):
        """Should add a default revision date when timestamp is None"""
        modified_data = copy.deepcopy(self.data)
        modified_data['revision_date'] = 'None'
        response = self.client.post(self.path, modified_data)
        self.assertEqual(response.status_code, 202)

    def test_add_result_with_no_project(self):
        """Should add a revision with the project"""
        modified_data = copy.deepcopy(self.data)
        modified_data['project'] = "My new project"
        modified_data['executable'] = "My new executable"
        response = self.client.post(self.path, modified_data)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(
            response.content.decode(), "Result data saved successfully")

    def test_suite_version_is_saved(self):
        """suite_version in the payload should be stored on the Result"""
        modified_data = copy.deepcopy(self.data)
        modified_data['suite_version'] = '2.3.1'
        self.client.post(self.path, modified_data)
        res = Result.objects.get(
            revision__commitid='23',
            benchmark__name='float',
        )
        self.assertEqual(res.suite_version, '2.3.1')

    def test_suite_version_defaults_to_empty(self):
        """Omitting suite_version should store an empty string"""
        self.client.post(self.path, self.data)
        res = Result.objects.get(
            revision__commitid='23',
            benchmark__name='float',
        )
        self.assertEqual(res.suite_version, '')

    def test_source_set_on_new_benchmark(self):
        """source in the payload should be set on an auto-created Benchmark"""
        modified_data = copy.deepcopy(self.data)
        modified_data['benchmark'] = 'newbench'
        modified_data['source'] = 'pyperformance'
        self.client.post(self.path, modified_data)
        b = Benchmark.objects.get(name='newbench')
        self.assertEqual(b.source, 'pyperformance')

    def test_source_defaults_to_legacy(self):
        """A payload without a source creates a 'legacy' Benchmark"""
        modified_data = copy.deepcopy(self.data)
        del modified_data['source']
        response = self.client.post(self.path, modified_data)
        self.assertEqual(response.status_code, 202)
        b = Benchmark.objects.get(name='float')
        self.assertEqual(b.source, 'legacy')

    def test_same_name_different_source_are_distinct(self):
        """The same name in a different suite is a separate Benchmark"""
        self.client.post(self.path, self.data)
        modified_data = copy.deepcopy(self.data)
        modified_data['source'] = 'pyperformance'
        self.client.post(self.path, modified_data)

        legacy = Benchmark.objects.get(name='float', source='legacy')
        pyperf = Benchmark.objects.get(name='float', source='pyperformance')
        self.assertNotEqual(legacy.pk, pyperf.pk)
        self.assertEqual(legacy.results.count(), 1)
        self.assertEqual(pyperf.results.count(), 1)

    def test_invalid_source_rejected(self):
        """An unknown source is rejected instead of creating a bogus row"""
        modified_data = copy.deepcopy(self.data)
        modified_data['source'] = 'bogus'
        response = self.client.post(self.path, modified_data)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Benchmark.objects.filter(name='float').exists())

    def test_sentinel_value_rejected(self):
        """A failed-run sentinel value is rejected"""
        modified_data = copy.deepcopy(self.data)
        modified_data['result_value'] = 1000000
        response = self.client.post(self.path, modified_data)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Result.objects.filter(benchmark__name='float').exists())


@override_settings(ALLOW_ANONYMOUS_POST=True)
class TestAddJSONResults(TestCase):

    def setUp(self):
        self.path = reverse('add-json-results')
        self.e = Environment(name='bigdog', cpu='Core 2 Duo 8200')
        self.e.save()
        temp = datetime.today()
        self.cdate = datetime(
            temp.year, temp.month, temp.day, temp.hour, temp.minute,
            temp.second)

        self.data = [
            {'commitid': '123',
             'project': 'pypy',
             'branch': 'default',
             'executable': 'pypy-c',
             'benchmark': 'Richards',
             'environment': 'bigdog',
             'result_value': 456,
             'source': 'legacy'},
            {'commitid': '456',
             'project': 'pypy',
             'branch': 'default',
             'executable': 'pypy-c',
             'benchmark': 'Richards',
             'environment': 'bigdog',
             'result_value': 457,
             'source': 'legacy'},
            {'commitid': '456',
             'project': 'pypy',
             'branch': 'default',
             'executable': 'pypy-c',
             'benchmark': 'Richards2',
             'environment': 'bigdog',
             'result_value': 34,
             'source': 'legacy'},
            {'commitid': '789',
             'project': 'pypy',
             'branch': 'default',
             'executable': 'pypy-c',
             'benchmark': 'Richards',
             'environment': 'bigdog',
             'result_value': 458,
             'source': 'legacy'},
        ]

    def test_get_returns_405(self):
        response = self.client.get(self.path,
                                   {'json': json.dumps(self.data)})

        self.assertEqual(response.status_code, 405)

    def test_add_correct_results(self):
        """Should add all results when the request data is valid"""
        response = self.client.post(self.path,
                                    {'json': json.dumps(self.data)})

        # Check that we get a success response
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.content.decode(),
                         "All result data saved successfully")

        # Check that the data was correctly saved
        e = Environment.objects.get(name='bigdog')
        b = Benchmark.objects.get(name='Richards')
        self.assertEqual(b.source, "legacy")
        self.assertEqual(b.units, "seconds")
        self.assertEqual(b.lessisbetter, True)
        p = Project.objects.get(name='pypy')
        branch = Branch.objects.get(name='default', project=p)
        r = Revision.objects.get(commitid='123', branch=branch)
        i = Executable.objects.get(name='pypy-c')
        res = Result.objects.get(
            revision=r,
            executable=i,
            benchmark=b,
            environment=e
        )
        self.assertTrue(res.value, 456)
        resdate = res.date.strftime("%Y%m%dT%H%M%S")
        selfdate = self.cdate.strftime("%Y%m%dT%H%M%S")
        self.assertTrue(resdate, selfdate)

        r = Revision.objects.get(commitid='456', branch=branch)
        res = Result.objects.get(
            revision=r,
            executable=i,
            benchmark=b,
            environment=e
        )
        self.assertTrue(res.value, 457)

        r = Revision.objects.get(commitid='789', branch=branch)
        res = Result.objects.get(
            revision=r,
            executable=i,
            benchmark=b,
            environment=e
        )
        self.assertTrue(res.value, 458)

    def test_bad_environment(self):
        """Add result associated with non-existing environment.
           Only change one item in the list.
        """
        data = self.data[0]
        bad_name = 'bigdog1'
        data['environment'] = bad_name
        response = self.client.post(self.path,
                                    {'json': json.dumps(self.data)})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.content.decode(), "Environment " + bad_name + " not found")
        data['environment'] = 'bigdog'

    def test_empty_argument(self):
        '''Should return 400 when making a request with an empty argument'''
        data = self.data[1]
        for key in data:
            if key == 'source':  # optional, defaults to 'legacy'
                continue
            backup = data[key]
            data[key] = ""
            response = self.client.post(self.path,
                                        {'json': json.dumps(self.data)})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(
                response.content.decode(),
                'Value for key "' + key + '" empty in request')
            data[key] = backup

    def test_missing_argument(self):
        '''Should return 400 when making a request with a missing argument'''
        data = self.data[2]
        for key in list(data):
            if key == 'source':  # optional, defaults to 'legacy'
                continue
            backup = data[key]
            del data[key]
            response = self.client.post(self.path,
                                        {'json': json.dumps(self.data)})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(
                response.content.decode(), 'Key "' + key + '" missing from request')
            data[key] = backup

    def test_report_is_created(self):
        '''Should create a report when adding json results for two revisions
        plus a third revision with one result less than the last one'''
        response = self.client.post(self.path,
                                    {'json': json.dumps(self.data)})

        # Check that we get a success response
        self.assertEqual(response.status_code, 202)

        number_of_reports = len(Report.objects.all())
        # After adding 4 result for 3 revisions, only 2 reports should be created
        # The third revision will need an extra result for Richards2 in order
        # to trigger report creation
        self.assertEqual(number_of_reports, 1)


class TestTimeline(TestCase):
    fixtures = ["timeline_tests.json"]

    def test_fixture(self):
        """Test the loaded fixture data
        """
        env = Environment.objects.filter(name="Dual Core")
        self.assertEqual(len(env), 1)
        benchmarks = Benchmark.objects.filter(name="float")
        self.assertEqual(len(benchmarks), 1)
        self.assertEqual(benchmarks[0].units, "seconds")
        results = benchmarks[0].results.all()
        self.assertEqual(len(results), 8)

    def test_timeline(self):
        path = reverse('timeline')
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        responsedata = response.content.decode()
        self.assertIn('My Own Title\n: Timeline', responsedata)

    def test_makeimage(self):
        response = self.client.get(reverse('makeimage'), {
            'env': 'Dual Core', 'proj': 'MyProject', 'branch': 'master',
            'exe': 'myexe O3 64bits', 'ben': 'float'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')
        self.assertTrue(response.content.startswith(b'\x89PNG'))

    def test_makeimage_bad_request(self):
        response = self.client.get(reverse('makeimage'), {'env': 'Dual Core'})
        self.assertEqual(response.status_code, 400)

    def test_gettimelinedata(self):
        """Test that gettimelinedata returns correct timeline data
        """
        path = reverse('gettimelinedata')
        data = {
            "exe": "1,2",
            "base": "2:4",
            "ben": "float",
            "env": "1",
            "revs": "2"
        }
        response = self.client.get(path, data)
        self.assertEqual(response.status_code, 200)
        responsedata = json.loads(response.getvalue().decode())

        self.assertEqual(
            responsedata['error'], "None", "there should be no errors")
        self.assertEqual(
            len(responsedata['timelines']), 1, "there should be 1 benchmark")
        self.assertEqual(
            len(responsedata['timelines'][0]['branches']),
            2,
            "there should be 2 branches")
        self.assertEqual(
            len(responsedata['timelines'][0]['branches']['default']),
            1,
            "there should be 1 timeline for master")
        self.assertEqual(
            len(responsedata['timelines'][0]['branches']['master']['1:1']),
            2,
            "There are 2 datapoints")
        self.assertEqual(
            responsedata['timelines'][0]['branches']['master']['1:1'][1],
            ['2011/04/13 17:04:22 +0000', 2000.0, 1.11111, '2', '', 'master', ''])

    def test_no_source_fold_with_one_source(self):
        """A single source shows a flat benchmark list and no fold header"""
        response = self.client.get(reverse('timeline'))
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context['grid_revisions'])
        self.assertNotContains(response, 'class="togglefold">Legacy</a>')
        self.assertContains(response, 'grid_revisions: null')

    def test_source_fold_with_several_sources(self):
        Benchmark.objects.create(name='float', source='pyperformance')
        response = self.client.get(reverse('timeline'))
        self.assertContains(response, 'class="togglefold">Legacy</a>')
        self.assertContains(response, 'class="togglefold">PyPerformance</a>')

    @override_settings(TIMELINE_GRID_REVISIONS=25)
    def test_grid_revisions_setting(self):
        response = self.client.get(reverse('timeline'))
        self.assertEqual(response.context['grid_revisions'], 25)
        self.assertIn(25, response.context['lastrevisions'])
        self.assertContains(response, 'grid_revisions: 25')


class TestComparison(TestCase):
    fixtures = ["timeline_tests.json"]

    def setUp(self):
        self.path = reverse('comparison')
        self.dual = Environment.objects.get(name='Dual Core')
        self.quad = Environment.objects.create(name='Quad Core')

    def checked_env_names(self, response):
        return sorted(e.name for e in response.context['checkedenviros'])

    def test_all_environments_checked_by_default(self):
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.checked_env_names(response),
                         ['Dual Core', 'Quad Core'])

    @override_settings(COMP_ENVIRONMENTS_DEFAULT='default',
                       DEF_ENVIRONMENT='Quad Core')
    def test_only_default_environment_checked(self):
        response = self.client.get(self.path)
        self.assertEqual(self.checked_env_names(response), ['Quad Core'])
        # Permalinks still select several environments
        response = self.client.get(
            self.path, {'env': '%d,%d' % (self.dual.id, self.quad.id)})
        self.assertEqual(self.checked_env_names(response),
                         ['Dual Core', 'Quad Core'])

    def test_benchmarks_grouped_by_units_with_one_source(self):
        response = self.client.get(self.path)
        self.assertEqual(list(response.context['benchmarks']), ['Time'])
        self.assertContains(response, 'class="togglefold">Time</a>')

    def test_benchmarks_grouped_by_source_with_several_sources(self):
        Benchmark.objects.create(name='float', source='pyperformance')
        response = self.client.get(self.path)
        self.assertEqual(list(response.context['benchmarks']),
                         ['Legacy', 'PyPerformance'])


@override_settings(ALLOW_ANONYMOUS_POST=True)
class TestReports(TestCase):

    def setUp(self):
        Environment.objects.create(name='Dual Core', cpu='Core 2 Duo 8200')
        self.data = {
            'commitid': 'abcd1',
            'branch': 'master',
            'project': 'MyProject',
            'executable': 'myexe O3 64bits',
            'benchmark': 'float',
            'environment': 'Dual Core',
            'result_value': 200,
            'source': 'legacy',
        }
        resp = self.client.post(reverse('add-result'),
                                self.data)
        self.assertEqual(resp.status_code, 202)
        self.data['commitid'] = "abcd2"
        self.data['result_value'] = 150
        self.client.post(reverse('add-result'), self.data)
        self.assertEqual(resp.status_code, 202)

    def test_reports(self):
        response = self.client.get(reverse('reports'))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Latest Results', content)
        self.assertIn('Latest Significant Results', content)
        self.assertIn(self.data['commitid'], content)

    def test_reports_post_returns_405(self):
        response = self.client.post(reverse('reports'), {})

        self.assertEqual(response.status_code, 405)


class TestFeeds(TestCase):

    def test_latest_result_feed(self):
        response = self.client.get(reverse('latest-results'))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('<atom:link ', content)
