from django import template
from django.utils.timesince import timesince

from codespeed import pr_runner

register = template.Library()


@register.simple_tag
def pr_runner_enabled():
    return pr_runner.enabled()


@register.filter
def ago(value):
    return '%s ago' % timesince(value, depth=1)
