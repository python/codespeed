# -*- coding: utf-8 -*-
# Django settings for a Codespeed project.
import os

from codespeed.settings import *
WEBSITE_NAME = "PyPy's Speed Center" # This name will be used in the reports RSS feed

DEBUG = True

BASEDIR = os.path.abspath(os.path.dirname(__file__))
TOPDIR = os.path.split(BASEDIR)[1]

#: The directory which should contain checked out source repositories:
REPOSITORY_BASE_PATH = os.path.join(BASEDIR, "repos")

ADMINS = (
    # ('Your Name', 'your_email@domain.com'),
)

MANAGERS = ADMINS
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASEDIR, 'data.db'),
    }
}

DEFAULT_AUTO_FIELD='django.db.models.AutoField'

TIME_ZONE = 'America/Chicago'

LANGUAGE_CODE = 'en-us'

SITE_ID = 1

USE_I18N = False

MEDIA_ROOT = os.path.join(BASEDIR, "media")

MEDIA_URL = '/media/'

SECRET_KEY = 'as%n_m#)^vee2pe91^^@c))sl7^c6t-9r8n)_69%)2yt+(la2&'


MIDDLEWARE = (
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
)

ROOT_URLCONF = '{0}.urls'.format(TOPDIR)


TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASEDIR, 'templates')],
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

INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.admin',
    'django.contrib.staticfiles',
    'codespeed',
)


STATIC_URL = '/static/'
STATIC_URL = 'https://speed.pypy.org/static/'
STATIC_ROOT = os.path.join(BASEDIR, "sitestatic")
STATICFILES_DIRS = (
    os.path.join(BASEDIR, 'static'),
)

SHOW_REPORTS = False
SHOW_HISTORICAL = True
DEF_BASELINES = [
                 {'executable': 'cpython', 'revision': '3.11.15'},
                ]
DEF_EXECUTABLES = [
                   {'name': 'pypy3.12-jit-64', 'project': 'PyPy3.12'},
                   {'name': 'pypy3.11-jit-64', 'project': 'PyPy3.11'},
                  ]
DEF_ENVIRONMENT = 'benchmarker2'
CHART_ORIENTATION = 'horizontal'
DEF_BENCHMARK = 'grid'


from .local_settings import *
