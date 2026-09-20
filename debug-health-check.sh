#!/bin/bash

# Debug script to diagnose health check issues
echo "=== HEALTH CHECK DIAGNOSTIC ==="
echo "Time: $(date)"
echo ""

echo "=== Container Status ==="
docker compose -f docker-compose.prod.yml ps
echo ""

echo "=== Network Info ==="
docker network ls | grep ppc
echo ""

echo "=== nginx Container Logs (last 20 lines) ==="
docker logs ppc_nginx --tail 20
echo ""

echo "=== FastAPI Container Logs (last 10 lines) ==="
docker logs ppc_fastapi --tail 10
echo ""

echo "=== nginx Configuration Test ==="
docker exec ppc_nginx nginx -t
echo ""

echo "=== Direct FastAPI Health Check ==="
if docker exec ppc_fastapi curl -f http://localhost:8000/health 2>/dev/null; then
    echo "✅ FastAPI health check: OK"
else
    echo "❌ FastAPI health check: FAILED"
fi
echo ""

echo "=== nginx -> FastAPI Proxy Test ==="
if docker exec ppc_nginx curl -f http://fastapi:8000/health 2>/dev/null; then
    echo "✅ nginx -> FastAPI proxy: OK"
else
    echo "❌ nginx -> FastAPI proxy: FAILED"
fi
echo ""

echo "=== External Health Check Test ==="
if curl -f http://localhost/health 2>/dev/null; then
    echo "✅ External health check: OK"
else
    echo "❌ External health check: FAILED"
    echo "Testing with verbose output:"
    curl -v http://localhost/health || echo "Curl failed"
fi
echo ""

echo "=== nginx Access Logs (last 5 lines) ==="
docker exec ppc_nginx tail -5 /var/log/nginx/access.log 2>/dev/null || echo "No access logs found"
echo ""

echo "=== nginx Error Logs (last 5 lines) ==="
docker exec ppc_nginx tail -5 /var/log/nginx/error.log 2>/dev/null || echo "No error logs found"
echo ""

echo "=== Docker DNS Resolution Test ==="
docker exec ppc_nginx nslookup fastapi || echo "DNS resolution failed"
echo ""