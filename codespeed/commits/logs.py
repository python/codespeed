# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

import datetime
import logging

logger = logging.getLogger(__name__)


def get_scm(project):
    if project.repo_type == project.SUBVERSION:
        from .subversion import getlogs, updaterepo
    elif project.repo_type == project.MERCURIAL:
        from .mercurial import Mercurial
        return Mercurial(project)
    elif project.repo_type == project.GIT:
        from .git import getlogs, updaterepo
    elif project.repo_type == project.GITHUB:
        from .github import getlogs, updaterepo  # noqa: F401
    else:
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
        scm.update_repo(project)

    logs = scm.get_logs(rev, startrev)

    # Remove last log because the startrev log shouldn't be shown
    if len(logs) > 1 and logs[-1].get('commitid') == startrev.commitid:
        logs.pop()

    return logs


def _get_commit_date(project, commit_id):
    scm = get_scm(project)
    if scm is None:
        return None

    return scm.get_commit_date(commit_id)


def get_commit_date(project, commit_id):
    date = _get_commit_date(project, commit_id)
    if date is not None:
        return date

    if project.repo_type not in (project.NO_LOGS, ""):
        logger.warning("Failed to get the date of the commit %r of project %s",
                       commit_id, project.get_repo_type_display())
    return datetime.datetime.today()
