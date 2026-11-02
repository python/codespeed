# -*- coding: utf-8 -*-

import os.path

from django.conf import settings
from django.urls import include, re_path
from django.views.generic import RedirectView
from django.contrib import admin

admin.autodiscover()

from . import views

urlpatterns = [
    re_path(r'^admin/', admin.site.urls),
    re_path(r'^home/geomean/json/$', views.gethomegeomeandata,
            name='gethomegeomeandata'),
    re_path(r'^', include('codespeed.urls')),
]

if settings.DEBUG:
    # needed for development server
    from django.contrib.staticfiles.urls import staticfiles_urlpatterns
    urlpatterns += staticfiles_urlpatterns()
