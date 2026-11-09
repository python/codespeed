"""Find a pull request's commit with git alone.

GitHub publishes every pull request as ``refs/pull/<n>/head``, and keeps
``refs/pull/<n>/merge`` only while the pull request is open and merges
cleanly. One ``git ls-remote`` therefore tells us whether the pull request
is open and which commit it is at, with no API token and no rate limit.
"""
import os
import re
import subprocess

from codespeed.github_api import repo_slug
from codespeed.models import Project

SHA_RE = re.compile(r'^[0-9a-f]{40}$')
TIMEOUT = 30
_PR_URL_RE = re.compile(
    r'^https?://github\.com/(?P<owner>[\w.-]+)/(?P<name>[\w.-]+)/pull/(?P<n>\d+)')


class PullRequestError(Exception):
    """Something about the pull request that the requester should be told."""


def repository_url(project):
    """The project's GitHub clone URL, or an error for other projects."""
    slug = None
    if project.repo_type == Project.GITHUB:
        slug = repo_slug(project.repo_path)
    if slug is None:
        raise PullRequestError(
            '%s is not set up as a GitHub project.' % project.name)
    return 'https://github.com/%s/%s' % slug


def parse_number(project, text):
    """The pull request number in "123", "#123" or a pull request URL."""
    text = (text or '').strip()
    m = _PR_URL_RE.match(text)
    if m:
        if (m.group('owner'), m.group('name')) != repo_slug(project.repo_path):
            return None
        return int(m.group('n'))
    text = text.lstrip('#')
    if text.isdigit() and len(text) <= 9 and int(text) > 0:
        return int(text)
    return None


def ls_remote(url, refs):
    """``{ref: sha}`` for the refs the remote has among `refs`."""
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', LC_ALL='C')
    try:
        done = subprocess.run(
            ['git', 'ls-remote', '--', url] + list(refs),
            capture_output=True, text=True, timeout=TIMEOUT, env=env)
    except FileNotFoundError:
        raise PullRequestError('git is not installed on this server.') from None
    except subprocess.TimeoutExpired:
        raise PullRequestError('GitHub did not answer in time.') from None
    if done.returncode:
        raise PullRequestError(
            'Could not reach the repository: %s' % done.stderr.strip()[-200:])
    found = {}
    for line in done.stdout.splitlines():
        sha, _, ref = line.partition('\t')
        if SHA_RE.match(sha) and ref:
            found[ref] = sha
    return found


def pull_request_head(project, number):
    """The commit an open pull request is at right now."""
    head = 'refs/pull/%d/head' % number
    merge = 'refs/pull/%d/merge' % number
    refs = ls_remote(repository_url(project), [head, merge])
    if head not in refs:
        raise PullRequestError('There is no pull request #%d.' % number)
    if merge not in refs:
        raise PullRequestError(
            'Pull request #%d is closed, or does not merge cleanly into %s.'
            % (number, project.default_branch))
    return refs[head]
