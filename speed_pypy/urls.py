# -*- coding: utf-8 -*-

from django.conf import settings
from django.urls import include, re_path
from django.contrib import admin

from codespeed import admin_views

urlpatterns = [
    re_path(r'^admin/download-db/$', admin_views.download_db, name='admin-download-db'),
    re_path(r'^admin/', admin.site.urls),
    re_path(r'^', include('codespeed.urls'))
]

if settings.DEBUG:
    # needed for development server
    from django.contrib.staticfiles.urls import staticfiles_urlpatterns
    urlpatterns += staticfiles_urlpatterns()
