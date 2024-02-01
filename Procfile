release: python manage.py migrate
web: gunicorn -c gunicorn.conf.py speed_python.wsgi:application -w 4
