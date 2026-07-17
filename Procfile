# Process definitions for Railway / Heroku-style platforms.
# web and worker MUST deploy from the SAME image/commit so the application
# version matches across both.
web: flask db upgrade && gunicorn --chdir /app wsgi:app -b 0.0.0.0:${PORT:-80} --workers 4 --timeout 120
worker: rq worker --url ${REDIS_URL} --with-scheduler ${CAMPAIGN_QUEUE:-campaigns} default
release: flask db upgrade
