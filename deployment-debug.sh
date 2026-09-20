#!/bin/bash

# Enhanced deployment diagnostic script
echo "========================================="
echo "  Max Pay Ads — Deployment Diagnostic"
echo "========================================="
echo "Time: $(date)"
echo ""

echo "=== Environment Check ==="
echo "PWD: $(pwd)"
echo "Docker version: $(docker --version)"
echo "Docker Compose version: $(docker compose --version)"
echo "Available memory: $(free -h | grep 'Mem:' || echo 'free command not available')"
echo "Available disk: $(df -h . | tail -1 || echo 'df command failed')"
echo ""

echo "=== Configuration Files ==="
echo "nginx.prod.conf exists: $([ -f nginx.prod.conf ] && echo 'YES' || echo 'NO')"
echo "docker-compose.prod.yml exists: $([ -f docker-compose.prod.yml ] && echo 'YES' || echo 'NO')"
echo "ppc-backend/.env exists: $([ -f ppc-backend/.env ] && echo 'YES' || echo 'NO')"
echo ""

echo "=== Docker Compose Validation ==="
if docker compose -f docker-compose.prod.yml config >/dev/null 2>&1; then
  echo "✅ docker-compose.prod.yml: VALID"
else
  echo "❌ docker-compose.prod.yml: INVALID"
  docker compose -f docker-compose.prod.yml config 2>&1
fi
echo ""

echo "=== Container Status ==="
docker compose -f docker-compose.prod.yml ps
echo ""

echo "=== Network Information ==="
echo "Docker networks:"
docker network ls | grep -E "(NETWORK|ppc|bridge)"
echo ""
echo "nginx network connectivity:"
docker exec ppc_nginx ping -c 1 fastapi 2>/dev/null && echo "✅ nginx can reach fastapi" || echo "❌ nginx cannot reach fastapi"
docker exec ppc_nginx ping -c 1 nextjs 2>/dev/null && echo "✅ nginx can reach nextjs" || echo "❌ nginx cannot reach nextjs"
echo ""

echo "=== nginx Status ==="
echo "nginx configuration test:"
docker exec ppc_nginx nginx -t 2>&1
echo ""
echo "nginx processes:"
docker exec ppc_nginx ps aux | grep nginx || echo "Cannot check nginx processes"
echo ""
echo "nginx listening ports:"
docker exec ppc_nginx netstat -tlnp 2>/dev/null | grep nginx || echo "Cannot check nginx ports"
echo ""

echo "=== FastAPI Status ==="
echo "FastAPI container health:"
container_status=$(docker inspect ppc_fastapi --format='{{.State.Status}}' 2>/dev/null || echo 'UNKNOWN')
echo "Container status: $container_status"

if [ "$container_status" = "running" ]; then
  echo ""
  echo "FastAPI processes:"
  docker exec ppc_fastapi ps aux | grep -E "(python|uvicorn)" || echo "No Python/uvicorn processes found"
  echo ""
  echo "FastAPI listening ports:"
  docker exec ppc_fastapi netstat -tlnp 2>/dev/null | grep :8000 || echo "Port 8000 not listening"
  echo ""
  echo "FastAPI environment variables:"
  docker exec ppc_fastapi env | grep -E "(SKIP_INIT|MONGODB_URL|REDIS_URL)" || echo "Cannot read environment"
  echo ""
  echo "FastAPI direct health test:"
  direct_health=$(docker exec ppc_fastapi curl -s -m 5 http://localhost:8000/health 2>/dev/null || echo 'FAILED')
  echo "Direct health response: $direct_health"
  echo ""
  echo "FastAPI recent logs (last 20 lines):"
  docker logs ppc_fastapi --tail 20
else
  echo "Container not running, showing logs:"
  docker logs ppc_fastapi --tail 30
fi
echo ""

echo "=== Proxy Chain Test ==="
echo "Testing the full request chain..."

# Test 1: Direct FastAPI access
if [ "$container_status" = "running" ]; then
  echo "1. FastAPI direct (inside container):"
  docker exec ppc_fastapi curl -s -m 5 http://localhost:8000/health 2>/dev/null && echo "   ✅ SUCCESS" || echo "   ❌ FAILED"
  
  echo "2. nginx -> FastAPI (docker network):"
  docker exec ppc_nginx curl -s -m 5 http://fastapi:8000/health 2>/dev/null && echo "   ✅ SUCCESS" || echo "   ❌ FAILED"
  
  echo "3. External -> nginx (host network):"
  curl -s -m 5 http://localhost/health 2>/dev/null && echo "   ✅ SUCCESS" || echo "   ❌ FAILED"
  
  echo "4. External -> nginx (with verbose errors):"
  curl -v -m 5 http://localhost/health 2>&1 | head -20
else
  echo "FastAPI container not running, skipping proxy tests"
fi
echo ""

echo "=== Service Dependencies ==="
echo "MongoDB health:"
docker exec ppc_mongodb mongosh --eval "db.adminCommand('ping')" 2>/dev/null && echo "✅ MongoDB: OK" || echo "❌ MongoDB: FAILED"

echo "Redis health:"
docker exec ppc_redis redis-cli ping 2>/dev/null && echo "✅ Redis: OK" || echo "❌ Redis: FAILED"

echo "RabbitMQ health:"
docker exec ppc_rabbitmq rabbitmq-diagnostics check_port_connectivity 2>/dev/null && echo "✅ RabbitMQ: OK" || echo "❌ RabbitMQ: FAILED"
echo ""

echo "=== Log Analysis ==="
echo "Recent nginx access logs (last 5 lines):"
docker exec ppc_nginx tail -5 /var/log/nginx/access.log 2>/dev/null || echo "No nginx access logs found"
echo ""
echo "Recent nginx error logs (last 5 lines):"
docker exec ppc_nginx tail -5 /var/log/nginx/error.log 2>/dev/null || echo "No nginx error logs found"
echo ""

echo "========================================="
echo "  Diagnostic Complete"
echo "========================================="