# -*- coding: utf-8 -*-
# Django settings for a Codespeed project.
import os

DEBUG = True
TEMPLATE_DEBUG = DEBUG

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

ADMIN_MEDIA_PREFIX = '/static/admin/'

# XXX Set SECRET_KEY in local_settings.py
#with open(os.path.join(BASEDIR, 'secret_key')) as f:
#    SECRET_KEY = f.read().strip()
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")

TEMPLATE_LOADERS = (
    'django.template.loaders.filesystem.Loader',
    'django.template.loaders.app_directories.Loader',
)

MIDDLEWARE = (
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
)

if DEBUG:
    import traceback
    import logging

    # Define a class that logs unhandled errors
    class LogUncatchedErrors:
        def __init__(self, get_response):
            self.get_response = get_response

        def __call__(self, request):
            return self.get_response(request)

        def process_exception(self, request, exception):
            logging.error("Unhandled Exception on request for %s\n%s" %
                                 (request.build_absolute_uri(),
                                  traceback.format_exc()))
    # And add it to the middleware classes
    MIDDLEWARE += ('speed_python.settings.LogUncatchedErrors',)

    # set shown level of logging output to debug
    logging.basicConfig(level=logging.DEBUG)

ROOT_URLCONF = '{0}.urls'.format(TOPDIR)

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASEDIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.debug',
                'django.template.context_processors.i18n',
                'django.template.context_processors.media',
                'django.template.context_processors.static',
                'django.template.context_processors.request',
            ],
        },
    },
]

INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.admin',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'codespeed',
    'gunicorn',
)

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASEDIR, "sitestatic")
STATICFILES_DIRS = (
    os.path.join(BASEDIR, 'static'),
)

# Codespeed settings that can be overwritten here.
from codespeed.settings import *
