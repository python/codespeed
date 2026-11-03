"""Tests for the speed.pypy.org specific views.

Run with: python manage.py test codespeed speed_pypy --settings=codespeed.tests.settings
"""
import os

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from codespeed.models import Executable, Project

SITE_DIR = os.path.dirname(os.path.abspath(__file__))
# The test settings are site independent; render this site's templates instead.
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
    ROOT_URLCONF='speed_pypy.urls',
    TEMPLATES=SITE_TEMPLATES,
    DEF_BASELINES=[{'executable': 'cpython', 'revision': '3.12.4'}],
    DEF_EXECUTABLES=[{'name': 'pypy3.11-jit-64', 'project': 'PyPy3.11'}])
class TestEmbedComparison(TestCase):

    def setUp(self):
        cpython = Project.objects.create(name='CPython', default_branch='main')
        pypy = Project.objects.create(name='PyPy3.11', default_branch='main')
        Executable.objects.create(name='cpython', project=cpython)
        Executable.objects.create(name='pypy3.11-jit-64', project=pypy)

    def test_renders_frame_exempt(self):
        response = self.client.get(reverse('embed-comparison'))
        self.assertEqual(response.status_code, 200)
        # Served inside an iframe on pypy.org, so clickjacking protection is off
        self.assertNotIn('X-Frame-Options', response)
        self.assertEqual(response.context['default_exe'].name, 'pypy3.11-jit-64')


@override_settings(ROOT_URLCONF='speed_pypy.urls', TEMPLATES=SITE_TEMPLATES)
class TestDownloadDb(TestCase):

    def test_requires_staff(self):
        response = self.client.get(reverse('admin-download-db'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response['Location'])

    def test_staff_gets_sqlite_file(self):
        User.objects.create_user('admin', 'a@example.com', 'pw', is_staff=True)
        self.client.login(username='admin', password='pw')
        response = self.client.get(reverse('admin-download-db'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment', response['Content-Disposition'])
