#!/bin/bash
# Reset all Docker volumes (MongoDB, Redis, RabbitMQ)
# WARNING: This will delete ALL data. Use only for fresh starts.

echo "⚠  This will delete ALL data (MongoDB, Redis, RabbitMQ)."
read -p "Are you sure? (y/N): " confirm

if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
    echo "Cancelled."
    exit 0
fi

echo "Stopping containers..."
docker-compose down

echo "Removing volumes..."
docker volume rm docker_mongodb_data docker_redis_data docker_rabbitmq_data 2>/dev/null || true

echo "Starting fresh..."
docker-compose up -d

echo ""
echo "Volumes reset. Run these to seed data:"
echo "  docker-compose exec fastapi python scripts/seed_admin.py"
echo "  docker-compose exec fastapi python scripts/seed_campaigns.py"
echo "  docker-compose exec fastapi python scripts/train_fraud_model.py"
echo ""
echo "Done."
