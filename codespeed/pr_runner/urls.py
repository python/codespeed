from django.urls import re_path

from . import api, views

urlpatterns = [
    re_path(r'^pr-runner/$', views.index, name='pr-runner'),
    re_path(r'^pr-runner/new/$', views.create, name='pr-run-create'),
    re_path(r'^pr-runner/(?P<run_id>\d+)/$', views.detail, name='pr-run'),
    re_path(r'^pr-runner/(?P<run_id>\d+)/cancel/$', views.cancel,
            name='pr-run-cancel'),
    # For benchmark machines
    re_path(r'^pr-runner/api/claim/$', api.claim, name='pr-runner-claim'),
    re_path(r'^pr-runner/api/runs/(?P<run_id>\d+)/$', api.update,
            name='pr-runner-update'),
]
