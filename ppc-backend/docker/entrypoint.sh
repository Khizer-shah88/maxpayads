#!/bin/bash
set -e

MONGODB_URL="${MONGODB_URL:-mongodb://localhost:27017}"
REDIS_URL="${REDIS_URL:-redis://localhost:6379}"

# ── Wait for MongoDB ──────────────────────────────────────────────────────────
wait_for_mongo() {
    echo "Waiting for MongoDB..."
    until python -c "
import sys, pymongo
try:
    c = pymongo.MongoClient('$MONGODB_URL', serverSelectionTimeoutMS=3000)
    c.admin.command('ping')
except Exception:
    sys.exit(1)
" 2>/dev/null; do
        sleep 2
    done
    echo "MongoDB connected"
}

# ── Wait for Redis ────────────────────────────────────────────────────────────
wait_for_redis() {
    echo "Waiting for Redis..."
    until python -c "
import sys, redis
try:
    r = redis.from_url('$REDIS_URL', socket_connect_timeout=3)
    r.ping()
except Exception:
    sys.exit(1)
" 2>/dev/null; do
        sleep 2
    done
    echo "Redis connected"
}

# ── Determine if we are running as API server or Celery worker ────────────────
FIRST_ARG="${1:-}"

if [ "$FIRST_ARG" = "celery" ]; then
    # Celery workers also need MongoDB + Redis but RabbitMQ is their broker
    wait_for_mongo
    wait_for_redis
    echo "Starting Celery: $*"
    exec "$@"
fi

# ── API server: only needs MongoDB + Redis ────────────────────────────────────
# RabbitMQ is only used by Celery workers for background tasks.
# The API server connects to it lazily when tasks are dispatched - no need
# to wait for it at startup. This was the cause of the startup hang.
wait_for_mongo
wait_for_redis

if [ "${SKIP_INIT:-false}" = "true" ]; then
    echo "--- Skipping database seeding (SKIP_INIT=true) ---"
else
    echo "--- Seeding database ---"
    python scripts/seed_admin.py     2>&1 | grep -v "^$" | tail -3
    python scripts/seed_campaigns.py 2>&1 | grep -v "^$" | tail -4
    python app/seed/seed_smartlink_structures.py 2>&1 | grep -v "^$" | tail -4
    echo "Database ready"

    if [ ! -f "app/ml/models/fraud_model.pkl" ]; then
        echo "--- Training fraud model ---"
        python scripts/train_fraud_model.py 2>&1 | tail -3
    fi
fi

echo "--- Starting FastAPI ---"
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers "${WEB_CONCURRENCY:-6}" \
    --proxy-headers \
    --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}" \
    --log-level warning \
    --no-access-log \
    --backlog 8192 \
    --timeout-keep-alive 75
