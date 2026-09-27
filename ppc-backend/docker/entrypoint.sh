#!/bin/bash
set -e

MONGODB_URL="${MONGODB_URL:-mongodb://localhost:27017}"
REDIS_URL="${REDIS_URL:-redis://localhost:6379}"
RABBITMQ_URL="${CELERY_BROKER_URL:-amqp://guest:guest@localhost:5672//}"

# ── Wait for MongoDB ──────────────────────────────────────────────────────────
wait_for_mongo() {
    echo "Waiting for MongoDB..."
    until python -c "
import sys, pymongo
try:
    c = pymongo.MongoClient('$MONGODB_URL', serverSelectionTimeoutMS=3000)
    c.admin.command('ping')
except Exception as e:
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
except Exception as e:
    sys.exit(1)
" 2>/dev/null; do
        sleep 2
    done
    echo "Redis connected"
}

# ── Wait for RabbitMQ (AMQP-level check, not just TCP) ───────────────────────
# TCP port open does NOT mean the broker is ready to accept AMQP connections.
# Use kombu to do a real AMQP handshake — same library Celery uses.
wait_for_rabbitmq() {
    echo "Waiting for RabbitMQ (AMQP ready)..."
    until python -c "
import sys
try:
    from kombu import Connection
    with Connection('$RABBITMQ_URL', connect_timeout=5) as conn:
        conn.ensure_connection(max_retries=1, timeout=5)
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; do
        sleep 3
    done
    echo "RabbitMQ connected"
}

wait_for_mongo
wait_for_redis
wait_for_rabbitmq

# ── Determine if we are running as API server or Celery worker ────────────────
FIRST_ARG="${1:-}"

if [ "$FIRST_ARG" = "celery" ]; then
    echo "Starting Celery: $*"
    exec "$@"
fi

# ── API server ────────────────────────────────────────────────────────────────
if [ "${SKIP_INIT:-false}" = "true" ]; then
    echo "--- Skipping database seeding (SKIP_INIT=true) ---"
else
    echo "--- Seeding database ---"
    python scripts/seed_admin.py    2>&1 | grep -v "^$" | tail -3
    python scripts/seed_campaigns.py 2>&1 | grep -v "^$" | tail -4
    python app/seed/seed_smartlink_structures.py 2>&1 | grep -v "^$" | tail -4
    echo "Database ready"

    if [ ! -f "app/ml/models/fraud_model.pkl" ]; then
        echo "--- Training fraud model ---"
        python scripts/train_fraud_model.py 2>&1 | tail -3
    fi
fi

echo "--- Starting FastAPI ---"
# NOTE: --loop and --http flags are NOT compatible with --workers (multi-process).
# uvicorn[standard] already installs uvloop + httptools and uses them automatically
# per worker process. Do not set --loop/--http here.
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 16 \
    --log-level warning \
    --no-access-log \
    --backlog 4096 \
    --timeout-keep-alive 10
