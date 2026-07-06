release: python manage.py migrate
web: python manage.py collectstatic --noinput && gunicorn dental_office.wsgi --log-file -
