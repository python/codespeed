"""Benchmark a pull request on demand.

A signed-in member queues a run from the "PR Runner" tab. Benchmark machines
pull work from that queue over a small token-authenticated API, upload
results through the ordinary ``/result/add/json/`` endpoint, and report
back; Codespeed then posts a comparison to the pull request.

Nothing here knows how a machine builds or benchmarks anything. That keeps
the queue usable from a cron job, a systemd service, a CI system or a GitHub
Actions workflow alike. See ``documentation/pr-runner.md``.
"""
from functools import wraps

from django.conf import settings
from django.http import Http404

# Reasons a user may not start a run, for the page to explain
SIGN_IN = 'sign-in'
STALE = 'stale'
FORBIDDEN = 'forbidden'


def enabled():
    return bool(settings.PR_RUNNER_ENABLED)


def feature_required(view):
    """404 unless the site has turned the PR runner on."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not enabled():
            raise Http404
        return view(request, *args, **kwargs)
    return wrapper


def start_refusal(user):
    """Why `user` may not start runs, or None when they may.

    Two ways in: the ``codespeed.add_prrun`` permission, for local accounts
    an administrator trusts, or a GitHub sign-in whose team check is recent.
    Signing in with GitHub already required membership of an allowed team;
    the freshness rule bounds how long a removal from that team takes to
    bite.
    """
    from codespeed.github_auth import is_fresh
    from codespeed.models import GitHubAccount

    if not user.is_authenticated:
        return SIGN_IN
    if not user.is_active:
        return FORBIDDEN
    if user.has_perm('codespeed.add_prrun'):
        return None
    account = GitHubAccount.objects.filter(user=user).first()
    if account is None:
        return FORBIDDEN
    if not is_fresh(account):
        return STALE
    return None
