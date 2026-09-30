#!/bin/bash

# Fix Docker container conflict and redeploy
echo "Cleaning up stuck containers..."

# Remove the stuck celery_beat containers
docker rm -f ppc_celery_beat 2>/dev/null || true
docker rm -f c64ff7225c48f8a71fe28e113502b8ade1afb58d036586ed3ee3eca8c834904b 2>/dev/null || true
docker rm -f f04aea027403_ppc_celery_beat 2>/dev/null || true

# Remove any other stuck containers
docker ps -a | grep 'ppc_celery_beat' | awk '{print $1}' | xargs -r docker rm -f

echo "Containers cleaned. Restarting services..."

# Restart all services
cd /home/khizershah/Downloads/maxpayads/maxpayads
docker compose down
docker compose up -d --build

echo "Deployment complete!"
