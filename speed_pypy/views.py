"""Views specific to speed.pypy.org."""
import logging

from django.conf import settings
from django.shortcuts import render
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.http import require_GET

from codespeed.models import Executable, Project

logger = logging.getLogger(__name__)


@require_GET
@xframe_options_exempt
def embed_comparison(request):
    """Frame-exempt page rendering only the baseline-comparison
    for embedding on pypy.org"""
    context = {}
    try:
        context['baseline'] = Executable.objects.get(
            name=settings.DEF_BASELINES[0]['executable'])
        def_name = settings.DEF_EXECUTABLES[0]['name']
        def_project = Project.objects.get(name=settings.DEF_EXECUTABLES[0]['project'])
        context['default_exe'] = Executable.objects.get(
            name=def_name, project=def_project)
    except Exception as e:
        logger.error('embed_comparison: %s', e)
    return render(request, 'embed_comparison.html', context)
