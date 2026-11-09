from django.urls import include, re_path

from codespeed import github_auth, views
from codespeed.feeds import LatestEntries, LatestSignificantEntries

urlpatterns = [
    re_path(r'^$', views.HomeView.as_view(), name='home'),
    re_path(r'^about/$', views.about, name='about'),
    # RSS for reports
    re_path(r'^feeds/latest/$', LatestEntries(), name='latest-results'),
    re_path(r'^feeds/latest_significant/$', LatestSignificantEntries(),
        name='latest-significant-results'),
]

urlpatterns += [
    re_path(r'^historical/json/$', views.gethistoricaldata, name='gethistoricaldata'),
    re_path(r'^reports/$', views.reports, name='reports'),
    re_path(r'^changes/$', views.changes, name='changes'),
    re_path(r'^changes/table/$', views.getchangestable, name='getchangestable'),
    re_path(r'^changes/logs/$', views.displaylogs, name='displaylogs'),
    re_path(r'^timeline/$', views.timeline, name='timeline'),
    re_path(r'^timeline/json/$', views.gettimelinedata, name='gettimelinedata'),
    re_path(r'^comparison/$', views.comparison, name='comparison'),
    re_path(r'^comparison/json/$', views.getcomparisondata, name='getcomparisondata'),
    re_path(r'^makeimage/$', views.makeimage, name='makeimage'),
]

urlpatterns += [
    # URLs for adding results
    re_path(r'^result/add/json/$', views.add_json_results, name='add-json-results'),
    re_path(r'^result/add/$', views.add_result, name='add-result'),
]

urlpatterns += [
    # Sign in with GitHub
    re_path(r'^accounts/github/login/$', github_auth.github_login,
            name='github-login'),
    re_path(r'^accounts/github/callback/$', github_auth.github_callback,
            name='github-callback'),
    re_path(r'^accounts/logout/$', github_auth.sign_out, name='sign-out'),
]

urlpatterns += [
    # Benchmarking pull requests on demand; 404s unless PR_RUNNER_ENABLED
    re_path(r'^', include('codespeed.pr_runner.urls')),
]
