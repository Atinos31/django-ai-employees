#!/usr/bin/env sh
# Production start script (used by the Procfile on Railway).
set -e

# 1. Database: apply any new migrations
python manage.py migrate --noinput

# 2. Static files: collect and compress them for WhiteNoise
python manage.py collectstatic --noinput

# 3. Knowledge base: (re)load the company documents into ChromaDB.
#    Runs at start, not at build, because the Railway Volume that stores
#    ChromaDB is only guaranteed to be mounted while the service runs.
#    A failure here must not take the shop down, so it only warns.
python manage.py build_knowledge_base \
    || echo "WARNING: knowledge base build failed; the shop still works without it"

# 4. Web server. One worker (Railway volumes rule out replicas); threads
#    handle concurrent requests. Each open staff dashboard holds a thread for
#    its live stream (at most 4, see support/dashboard_views.py), so 12
#    threads leave room for customers. Agent chains can take ~30 seconds,
#    hence the long timeout.
exec gunicorn dj_ai_employee_main.wsgi \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers 1 \
    --threads 12 \
    --timeout 300 \
    --access-logfile -
