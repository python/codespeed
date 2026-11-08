#!/usr/bin/env python
import os
import sys

SITES = ('speed_python', 'speed_pypy')


def default_settings(repo_root):
    configured = [site for site in SITES
                  if os.path.exists(os.path.join(repo_root, site, 'local_settings.py'))]
    if len(configured) == 1:
        return configured[0] + '.settings'
    return 'speed_python.settings'


if __name__ == "__main__":
    os.environ.setdefault(
        "DJANGO_SETTINGS_MODULE",
        default_settings(os.path.dirname(os.path.abspath(__file__))))

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
