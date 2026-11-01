# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

import datetime
import logging

from .exceptions import CommitLogError

logger = logging.getLogger(__name__)


class FunctionBackend:
    """Adapter giving the function-based backends (GitHub, Subversion) the
    same interface as the Mercurial and Git classes."""

    def __init__(self, project, module):
        self.project = project
        self.module = module

    def update_repo(self, update=True):
        # These backends talk to a remote service; there is no clone to
        # create, so only "update" means anything.
        if update:
            return self.module.updaterepo(self.project)

    def get_logs(self, endrev, startrev):
        return self.module.getlogs(endrev, startrev)

    def get_commit_date(self, commit_id):
        lookup = getattr(self.module, 'get_commit_date', None)
        if lookup is None:
            return None  # not supported; callers fall back to today's date
        return lookup(self.project, commit_id)


def get_scm(project):
    """Return a backend object for the project, or None if logs are off.

    Every backend has update_repo(update), get_logs(endrev, startrev) and
    get_commit_date(commit_id).
    """
    if project.repo_type == project.MERCURIAL:
        from .mercurial import Mercurial
        return Mercurial(project)
    elif project.repo_type == project.GIT:
        from .git import Git
        return Git(project)
    elif project.repo_type == project.GITHUB:
        from . import github
        return FunctionBackend(project, github)
    elif project.repo_type == project.SUBVERSION:
        from . import subversion
        return FunctionBackend(project, subversion)
    return None


def get_logs(rev, startrev, update=False):
    logs = []
    project = rev.branch.project

    scm = get_scm(project)
    if scm is None:
        if project.repo_type not in (project.NO_LOGS, ""):
            logger.warning("Don't know how to retrieve logs from %s project",
                           project.get_repo_type_display())
        return logs

    if update:
        scm.update_repo()

    logs = scm.get_logs(rev, startrev)

    # Remove last log because the startrev log shouldn't be shown
    if len(logs) > 1 and logs[-1].get('commitid') == startrev.commitid:
        logs.pop()

    return logs


def _get_commit_date(project, commit_id):
    scm = get_scm(project)
    if scm is None:
        return None

    try:
        return scm.get_commit_date(commit_id)
    except CommitLogError as e:
        # A missing clone or unknown commit must not break result submission
        logger.warning("Could not get the date of commit %r of project %s: %s",
                       commit_id, project, e)
        return None


def get_commit_date(project, commit_id):
    date = _get_commit_date(project, commit_id)
    if date is not None:
        return date

    if project.repo_type not in (project.NO_LOGS, ""):
        logger.warning("Failed to get the date of the commit %r of project %s",
                       commit_id, project.get_repo_type_display())
    return datetime.datetime.today()
