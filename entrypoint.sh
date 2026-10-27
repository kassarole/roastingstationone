#!/usr/bin/env bash
set -e

echo "Waiting for postgres..."
until python -c "import psycopg, os; psycopg.connect(os.environ['DATABASE_URL'])" 2>/dev/null; do
  sleep 1
done
python manage.py makemigrations roasts --noinput
python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py createsuperuser --noinput 2>/dev/null || true

exec "$@"
