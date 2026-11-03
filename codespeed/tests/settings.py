"""Django settings for running the Codespeed test suite.

Site independent: no site package is involved, so the suite exercises the
``codespeed`` app on its own. Site packages such as ``speed_python`` run their
tests under these settings too and override what they need per test case.

Usage::

    python manage.py test codespeed speed_python --settings=codespeed.tests.settings
"""
import os

from codespeed.settings import *  # noqa: F401,F403

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))

DEBUG = False

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'
SECRET_KEY = 'test-secret-key-not-for-production'
USE_TZ = True
TIME_ZONE = 'UTC'
USE_I18N = False

INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.admin',
    'django.contrib.staticfiles',
    'codespeed',
)

MIDDLEWARE = (
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
)

ROOT_URLCONF = 'codespeed.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        # Site-style template overrides the tests check for
        'DIRS': [os.path.join(TESTS_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

STATIC_URL = '/static/'

# Codespeed clones repositories here when commit logs are requested.
REPOSITORY_BASE_PATH = '/tmp/codespeed-test-repos'

CACHES = {
    'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'},
}
