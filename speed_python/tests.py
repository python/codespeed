"""Tests for the speed.python.org specific views.

Run with: python manage.py test codespeed speed_python
"""
import json
import os
from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from codespeed.models import (Project, Benchmark, Revision, Branch, Executable,
                              Environment, Result)


DUMMY_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}}
SITE_DIR = os.path.dirname(os.path.abspath(__file__))
# The test settings belong to sample_project; render this site's templates instead.
SITE_TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [os.path.join(SITE_DIR, 'templates')],
    'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
    ]},
}]


@override_settings(
    ROOT_URLCONF='speed_python.urls',
    TEMPLATES=SITE_TEMPLATES,
    CACHES=DUMMY_CACHE,
    HOME_GEOMEAN_SERIES=[{'executable': 'myexe', 'environment': 'env1'}])
class TestHomeGeomean(TestCase):

    def setUp(self):
        self.env = Environment.objects.create(name='env1')
        self.project = Project.objects.create(name='proj', default_branch='main')
        self.branch = Branch.objects.create(name='main', project=self.project)
        self.exe = Executable.objects.create(name='myexe', project=self.project)
        self.b1 = Benchmark.objects.create(name='b1')
        self.b2 = Benchmark.objects.create(name='b2')
        now = timezone.now()
        runs = [
            # days ago, {benchmark: value}
            (45, {self.b1: 9.0, self.b2: 9.0}),   # outside the window
            (20, {self.b1: 1.0, self.b2: 4.0}),   # first in window: baseline
            (10, {self.b1: 2.0, self.b2: 2.0}),   # geomean of 2.0 and 0.5 -> 1.0
            (5, {self.b1: 0.5}),                  # b2 missing: only b1 counts
        ]
        for i, (days_ago, values) in enumerate(runs):
            rev = Revision.objects.create(
                commitid='c%d' % i, branch=self.branch, project=self.project,
                date=now - timedelta(days=days_ago))
            for bench, value in values.items():
                Result.objects.create(value=value, revision=rev, executable=self.exe,
                                      benchmark=bench, environment=self.env)

    def get(self):
        response = self.client.get(reverse('gethomegeomeandata'))
        self.assertEqual(response.status_code, 200)
        return json.loads(response.content.decode())

    def test_series_normalised_to_first_revision_in_window(self):
        data = self.get()
        self.assertEqual(data['days'], 30)
        self.assertEqual(len(data['series']), 1)
        series = data['series'][0]
        self.assertEqual(series['label'], 'myexe @ env1')
        self.assertEqual(series['executable'], self.exe.id)
        self.assertEqual(series['environment'], self.env.id)
        self.assertEqual(series['branch'], 'main')
        self.assertEqual(series['baseline_commitid'], 'c1')
        self.assertEqual([p[2] for p in series['points']], ['c1', 'c2', 'c3'])
        self.assertEqual([p[1] for p in series['points']], [1.0, 1.0, 0.5])
        self.assertEqual([p[3] for p in series['points']], [2, 2, 1])

    def test_branch_filter(self):
        other = Branch.objects.create(name='other', project=self.project)
        rev = Revision.objects.create(commitid='x', branch=other, project=self.project,
                                      date=timezone.now())
        Result.objects.create(value=100.0, revision=rev, executable=self.exe,
                              benchmark=self.b1, environment=self.env)
        commits = [p[2] for p in self.get()['series'][0]['points']]
        self.assertNotIn('x', commits)

    @override_settings(HOME_GEOMEAN_SERIES=[
        {'executable': 'myexe', 'environment': 'env1', 'branch': 'main'},
        {'executable': 'nope', 'environment': 'env1'},
        {'executable': 'myexe', 'environment': 'nope'}])
    def test_unknown_entries_are_skipped(self):
        data = self.get()
        self.assertEqual([s['label'] for s in data['series']], ['myexe @ env1'])

    @override_settings(HOME_GEOMEAN_SERIES=[])
    def test_unconfigured(self):
        self.assertEqual(self.get()['series'], [])

    def test_home_page_embeds_the_chart(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('id="geomean-plot"', response.content.decode())
        self.assertIn(reverse('gethomegeomeandata'), response.content.decode())
