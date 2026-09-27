# Deployment Retry Commands

## 🚨 RabbitMQ Issue Fixed - Ready to Retry

The RabbitMQ startup issue has been resolved. Here are the commands to retry deployment:

### Method 1: Quick Fix Deployment
```bash
# Stop all services first
docker-compose -f docker-compose.prod.yml down

# Remove any problematic containers
docker-compose -f docker-compose.prod.yml rm -f rabbitmq

# Start with fresh deployment
docker-compose -f docker-compose.prod.yml up -d --build
```

### Method 2: Staged Deployment (Safer)
```bash
# Stop all services
docker-compose -f docker-compose.prod.yml down

# Start infrastructure services first
docker-compose -f docker-compose.prod.yml up -d mongodb redis rabbitmq

# Wait for services to be healthy (check every 30 seconds)
watch 'docker-compose -f docker-compose.prod.yml ps'

# Once healthy, start application services
docker-compose -f docker-compose.prod.yml up -d fastapi celery_worker celery_beat nextjs nginx
```

### Method 3: Manual RabbitMQ First
```bash
# Stop everything
docker-compose -f docker-compose.prod.yml down

# Start just RabbitMQ to verify it works
docker-compose -f docker-compose.prod.yml up -d rabbitmq

# Check RabbitMQ logs
docker-compose -f docker-compose.prod.yml logs -f rabbitmq

# If RabbitMQ is healthy, start everything else
docker-compose -f docker-compose.prod.yml up -d
```

## Monitor Deployment

### Check Service Status:
```bash
docker-compose -f docker-compose.prod.yml ps
```

### Check RabbitMQ Specifically:
```bash
docker-compose -f docker-compose.prod.yml logs rabbitmq --tail 20
```

### Check All Logs:
```bash
docker-compose -f docker-compose.prod.yml logs -f
```

## Verification Commands

Once deployment is successful:

### 1. Health Check:
```bash
curl -f https://your-domain.com/health
```

### 2. Service Status:
```bash
docker stats --no-stream --format "table {{.Container}}\t{{.MemUsage}}\t{{.CPUPerc}}"
```

### 3. Application Test:
```bash
# Test a simple page load
curl -I https://your-domain.com/

# Test click endpoint  
curl "https://your-domain.com/click?pub=PUB_TEST&site=SITE_TEST"
```

## If Still Having Issues

### RabbitMQ Alternative Config:
If RabbitMQ still fails, temporarily use this minimal config in docker-compose.prod.yml:

```yaml
rabbitmq:
  image: rabbitmq:3.12-alpine  # Use older stable version
  container_name: ppc_rabbitmq
  volumes:
    - rabbitmq_data:/var/lib/rabbitmq
  environment:
    RABBITMQ_DEFAULT_USER: guest
    RABBITMQ_DEFAULT_PASS: guest
  healthcheck:
    test: ["CMD", "rabbitmq-diagnostics", "status"]
    interval: 60s
    timeout: 30s
    retries: 3
    start_period: 120s
  restart: unless-stopped
  networks:
    - ppc_network
  deploy:
    resources:
      limits:
        memory: 512M
```

### Emergency Rollback:
If the deployment continues to fail:
```bash
# Quick rollback to previous working version
docker-compose -f docker-compose.prod.yml down
mv docker-compose.prod.yml.backup docker-compose.prod.yml
docker-compose -f docker-compose.prod.yml up -d
```

## Expected Success Output:
```
Container ppc_mongodb Running
Container ppc_redis Running  
Container ppc_rabbitmq Running
Container ppc_fastapi Running
Container ppc_celery Running
Container ppc_celery_beat Running
Container ppc_nextjs Running
Container ppc_nginx Running
```

The fixed configuration should now allow RabbitMQ to start successfully! 🚀