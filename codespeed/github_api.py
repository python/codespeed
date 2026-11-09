"""A small GitHub REST client for sign-in and the PR runner.

It is kept apart from ``codespeed.commits.github``, which caches every
response for a month. That suits immutable commits but is wrong for team
memberships and pull requests, which may change.
"""
import json
import logging
import re
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

API_ROOT = 'https://api.github.com'
API_VERSION = '2022-11-28'
USER_AGENT = 'codespeed'
TIMEOUT = 10 

_REPO_RE = re.compile(
    r'^https?://github\.com/(?P<owner>[\w.-]+)/(?P<name>[\w.-]+?)(\.git)?/?$'
)


class GitHubError(Exception):
    """A GitHub call failed. status is None when GitHub was unreachable."""

    def __init__(self, status, message):
        super().__init__('GitHub API error (%s): %s' % (status, message))
        self.status = status
        self.message = message


def send(request):
    """Send a prepared request and return the decoded JSON body, or None."""
    try:
        with urlopen(request, timeout=TIMEOUT) as response:
            body = response.read()
    except HTTPError as e:
        try:
            message = json.loads(e.read()).get('message', e.reason)
        except (ValueError, AttributeError):
            message = e.reason
        raise GitHubError(e.code, message) from None
    except OSError as e:  # URLError, timeouts, connection resets
        raise GitHubError(None, str(e)) from None
    if not body:
        return None
    try:
        return json.loads(body)
    except ValueError:
        raise GitHubError(None, 'response was not JSON') from None


def api(method, path, token=None, data=None, params=None):
    """Call https://api.github.com<path> and return the decoded JSON."""
    if not path.startswith('/'):
        raise ValueError('path must start with "/": %r' % path)
    url = API_ROOT + path
    if params:
        url += '?' + urlencode(params)
    headers = {
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': API_VERSION,
        'User-Agent': USER_AGENT,
    }
    if token:
        headers['Authorization'] = 'Bearer %s' % token
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers['Content-Type'] = 'application/json'
    return send(Request(url, data=body, headers=headers, method=method))


def repo_slug(repo_url):
    m = _REPO_RE.match(repo_url or '')
    if not m:
        return None
    return m.group('owner'), m.group('name')
