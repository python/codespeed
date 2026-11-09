"""Sign in with GitHub.

The OAuth web flow is small enough to do by hand, and doing so keeps the
footprint to one model and three views. Only people who pass the membership
check get an account; everyone else is turned away before a user row exists.

The access token is used for that one check and then dropped. It is never
stored, so there is nothing to leak or to revoke.
"""
import logging
import secrets
from datetime import timedelta
from urllib.parse import quote, urlencode
from urllib.request import Request

from django.conf import settings
from django.contrib.auth import get_user_model, login, logout
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from . import github_api
from .github_api import GitHubError
from .models import GitHubAccount

logger = logging.getLogger(__name__)

AUTHORIZE_URL = 'https://github.com/login/oauth/authorize'
TOKEN_URL = 'https://github.com/login/oauth/access_token'
SESSION_KEY = 'github_oauth'
# read:org lets us see the user's membership of teams in a private org
# listing. It grants no write access to anything.
SCOPE = 'read:org'
USERNAME_PREFIX = 'github-'
AUTH_BACKEND = 'django.contrib.auth.backends.ModelBackend'


def login_enabled():
    return bool(settings.GITHUB_LOGIN_CLIENT_ID and
                settings.GITHUB_LOGIN_CLIENT_SECRET)


def is_fresh(account):
    """Whether the account's membership check is recent enough to act on."""
    max_age = timedelta(seconds=settings.GITHUB_LOGIN_RECHECK_SECONDS)
    return account.verified_at >= timezone.now() - max_age


def _safe_next(request, url):
    if url and url_has_allowed_host_and_scheme(
            url, allowed_hosts={request.get_host()},
            require_https=request.is_secure()):
        return url
    return reverse('home')


def _callback_url(request):
    return request.build_absolute_uri(reverse('github-callback'))


def _denied(request, message, status):
    return render(request, 'codespeed/signin_denied.html',
                  {'message': message}, status=status)


def exchange_code(code, redirect_uri):
    """Trade the one-time code from GitHub for a user access token."""
    body = urlencode({
        'client_id': settings.GITHUB_LOGIN_CLIENT_ID,
        'client_secret': settings.GITHUB_LOGIN_CLIENT_SECRET,
        'code': code,
        'redirect_uri': redirect_uri,
    }).encode()
    data = github_api.send(Request(TOKEN_URL, data=body, method='POST', headers={
        'Accept': 'application/json',
        'User-Agent': github_api.USER_AGENT,
    }))
    token = (data or {}).get('access_token')
    if not token:
        # GitHub answers 200 with an "error" key for a bad or reused code
        raise GitHubError(400, (data or {}).get('error_description',
                                                'no access token returned'))
    return token


def is_allowed(github_login, token):
    """Whether this GitHub user may sign in.

    Fails closed: with no teams and no users configured, nobody gets in.
    """
    allowed_users = {u.lower() for u in settings.GITHUB_LOGIN_ALLOWED_USERS}
    if github_login.lower() in allowed_users:
        return True
    for team in settings.GITHUB_LOGIN_ALLOWED_TEAMS:
        org, _, slug = team.partition('/')
        path = '/orgs/%s/teams/%s/memberships/%s' % (
            quote(org, safe=''), quote(slug, safe=''),
            quote(github_login, safe=''))
        try:
            membership = github_api.api('GET', path, token=token)
        except GitHubError as e:
            if e.status == 404:  # not a member, or the team is not visible
                continue
            raise
        if membership and membership.get('state') == 'active':
            return True
    return False


def _sign_in_account(profile):
    """Return the Django user for a verified GitHub profile, or None.

    Accounts are keyed on GitHub's numeric id, never on the login name:
    logins can be renamed and reused, and a GitHub user who happens to be
    called "admin" must not land in a local account of the same name.
    """
    github_id = int(profile['id'])
    account = GitHubAccount.objects.select_related('user').filter(
        github_id=github_id).first()
    if account is None:
        User = get_user_model()
        username = '%s%d' % (USERNAME_PREFIX, github_id)
        if User.objects.filter(username=username).exists():
            logger.error('Cannot create %s: a local user has that name',
                         username)
            return None
        user = User(username=username)
        user.set_unusable_password()
        user.save()
        account = GitHubAccount(user=user, github_id=github_id)
    elif not account.user.is_active:
        return None

    avatar = profile.get('avatar_url') or ''
    account.login = profile['login']
    account.name = (profile.get('name') or '')[:255]
    account.avatar_url = avatar if avatar.startswith('https://') else ''
    account.verified_at = timezone.now()
    account.save()
    return account.user


@require_GET
def github_login(request):
    if not login_enabled():
        raise Http404
    state = secrets.token_urlsafe(32)
    request.session[SESSION_KEY] = {
        'state': state,
        'next': _safe_next(request, request.GET.get('next')),
    }
    return redirect(AUTHORIZE_URL + '?' + urlencode({
        'client_id': settings.GITHUB_LOGIN_CLIENT_ID,
        'redirect_uri': _callback_url(request),
        'scope': SCOPE,
        'state': state,
        'allow_signup': 'false',
    }))


@require_GET
def github_callback(request):
    if not login_enabled():
        raise Http404
    # The state ties this callback to the browser that started the flow.
    # Popping it makes each one usable once.
    saved = request.session.pop(SESSION_KEY, None)
    state = request.GET.get('state', '')
    if not saved or not constant_time_compare(saved['state'], state):
        return _denied(
            request, 'That sign-in attempt expired. Please try again.', 400)
    code = request.GET.get('code')
    if request.GET.get('error') or not code:
        return _denied(request, 'Sign-in was cancelled on GitHub.', 400)

    try:
        token = exchange_code(code, _callback_url(request))
        profile = github_api.api('GET', '/user', token=token)
        allowed = is_allowed(profile['login'], token)
    except (GitHubError, KeyError, TypeError) as e:
        logger.warning('GitHub sign-in failed: %s', e)
        return _denied(
            request, 'GitHub could not confirm your account just now. '
                     'Please try again in a moment.', 502)

    if not allowed:
        logger.info('Refused sign-in for GitHub user %s', profile['login'])
        return _denied(
            request, 'Signed in to GitHub as %s, but that account is not in '
                     'a team allowed to use this site.' % profile['login'],
            403)

    user = _sign_in_account(profile)
    if user is None:
        return _denied(request, 'This account has been disabled here.', 403)
    login(request, user, backend=AUTH_BACKEND)
    logger.info('GitHub user %s signed in', profile['login'])
    return redirect(saved['next'])


@require_POST
def sign_out(request):
    logout(request)
    return redirect(_safe_next(request, request.POST.get('next')))
