from django import template

from codespeed.github_auth import login_enabled
from codespeed.models import GitHubAccount

register = template.Library()


@register.inclusion_tag('codespeed/account_widget.html', takes_context=True)
def account_widget(context):
    """The sign-in button, or who is signed in, for the page header.

    Renders nothing for anonymous visitors unless GitHub sign-in is configured.
    """
    request = context.get('request')
    user = getattr(request, 'user', None)
    account = None
    if user is not None and user.is_authenticated:
        account = GitHubAccount.objects.filter(user=user).first()
    else:
        user = None
    return {
        'login_enabled': login_enabled(),
        'user': user,
        'account': account,
        'next': request.get_full_path() if request else '/',
    }
