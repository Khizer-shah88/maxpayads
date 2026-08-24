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

# ── Wait for RabbitMQ ─────────────────────────────────────────────────────────
wait_for_rabbitmq() {
    echo "Waiting for RabbitMQ..."
    RABBIT_HOST=$(echo "$RABBITMQ_URL" | sed -E 's|.*@([^:/]+).*|\1|')
    RABBIT_PORT=$(echo "$RABBITMQ_URL" | sed -E 's|.*:([0-9]+)/.*|\1|')
    RABBIT_PORT=${RABBIT_PORT:-5672}
    until python -c "
import sys, socket
try:
    s = socket.create_connection(('$RABBIT_HOST', $RABBIT_PORT), timeout=3)
    s.close()
except Exception as e:
    sys.exit(1)
" 2>/dev/null; do
        sleep 2
    done
    echo "RabbitMQ connected"
}

wait_for_mongo
wait_for_redis
wait_for_rabbitmq

# ── Seed and start (only for API server, not workers) ─────────────────────────
# Check first argument to determine if we're running as API or worker
FIRST_ARG="${1:-}"

if [ "$FIRST_ARG" = "celery" ]; then
    # Celery worker/beat — just exec the command
    echo "Starting Celery: $*"
    exec "$@"
fi

# ── API server: seed database and train model ─────────────────────────────────
echo "--- Seeding database ---"
python scripts/seed_admin.py    2>&1 | grep -v "^$" | tail -3
python scripts/seed_campaigns.py 2>&1 | grep -v "^$" | tail -4
echo "Database ready"

# Train ML model if not present
if [ ! -f "app/ml/models/fraud_model.pkl" ]; then
    echo "--- Training fraud model ---"
    python scripts/train_fraud_model.py 2>&1 | tail -3
fi

echo "--- Starting FastAPI ---"
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 4 \
    --log-level info
