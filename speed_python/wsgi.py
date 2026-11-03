# This is used for staging & production
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "speed_python.settings")

from django.core.wsgi import get_wsgi_application  # noqa: E402
application = get_wsgi_application()
