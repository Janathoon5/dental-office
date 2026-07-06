release: python manage.py migrate && python manage.py collectstatic --noinput
web: gunicorn dental_office.wsgi --log-file -
