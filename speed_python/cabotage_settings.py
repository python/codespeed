# -*- coding: utf-8 -*-

import environ

from speed_python.settings import *

env = environ.Env()

# Note: This is imported by the main settings file, so only changes to
# what's there need to be included here.

DEBUG = TEMPLATE_DEBUG = False

# TODO: configure via "DATABASE_URL" env var
DATABASES = {"default": env.db()}

ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost").split(",")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")


ADMINS = (
    (
        os.environ.get("CODESPEED_ADMIN_TEAM_NAME", "Codespeed"),
        os.environ.get("CODESPEED_ADMIN_TEAM_EMAIL", "codespeed@example.com"),
    ),
)

SERVER_EMAIL = os.environ.get("DJANGO_SERVER_EMAIL", "noreply@example.com")

DEFAULT_FROM_EMAIL = os.environ.get("DJANGO_DEFAULT_FROM_EMAIL", "noreply@example.com")

MANAGERS = ADMINS

COMPRESS_ENABLED = True

MIDDLEWARE = MIDDLEWARE + ['whitenoise.middleware.WhiteNoiseMiddleware']
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

_DATA_ROOT = os.environ.get("DJANGO_DATA_ROOT", "/srv/data")
MEDIA_ROOT = _DATA_ROOT + "/media"
STATIC_ROOT = _DATA_ROOT + "/site_media/static"
REPOSITORY_BASE_PATH = _DATA_ROOT + "/repos/"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "filters": {},
    "handlers": {
        "console": {
            "level": "INFO",
            "filters": [],
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
        "mail_admins": {
            "level": "ERROR",
            "class": "django.utils.log.AdminEmailHandler",
            "filters": [],
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "propagate": True,
        },
        "myproject.custom": {
            "handlers": ["console", "mail_admins"],
            "level": "INFO",
            "filters": [],
        },
    },
}
