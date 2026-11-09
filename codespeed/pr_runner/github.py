"""The two GitHub API calls the PR runner makes, with the site's token:
commenting on the pull request and, optionally, waking a workflow."""
from urllib.parse import quote

from django.conf import settings

from codespeed.github_api import api, repo_slug
from codespeed.models import Project

from .git import PullRequestError


def repo_path(project):
    """``/repos/<owner>/<name>`` for a project hosted on GitHub."""
    slug = None
    if project.repo_type == Project.GITHUB:
        slug = repo_slug(project.repo_path)
    if slug is None:
        raise PullRequestError(
            '%s is not set up as a GitHub project.' % project.name)
    return '/repos/%s/%s' % slug


def post_comment(project, number, body):
    """Comment on the pull request and return the comment's URL."""
    data = api('POST', '%s/issues/%d/comments' % (repo_path(project), number),
               token=settings.PR_RUNNER_GITHUB_TOKEN, data={'body': body})
    return data.get('html_url', '')


def dispatch_workflow(runner, run):
    """Wake a GitHub Actions hosted runner for one run.

    The workflow is told only which run to pick up. It fetches the details
    through the runner API with its own token, so nothing that matters
    travels in workflow inputs, which anyone who can see the run can read.
    """
    owner, _, name = runner.workflow_repo.partition('/')
    api('POST', '/repos/%s/%s/actions/workflows/%s/dispatches' % (
        quote(owner, safe=''), quote(name, safe=''),
        quote(runner.workflow_file, safe='')),
        token=settings.PR_RUNNER_GITHUB_TOKEN,
        data={'ref': runner.workflow_ref, 'inputs': {'run_id': str(run.pk)}})
