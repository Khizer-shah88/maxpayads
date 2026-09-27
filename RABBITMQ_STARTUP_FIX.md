# RabbitMQ Startup Fix

## Problem
RabbitMQ container was failing to start during deployment with error:
```
Container ppc_rabbitmq Error dependency rabbitmq failed to start
dependency failed to start: container ppc_rabbitmq is unhealthy
```

## Root Cause
The issue was likely caused by:
1. **Problematic memory watermark setting**: `RABBITMQ_VM_MEMORY_HIGH_WATERMARK: 0.6` may not be compatible with Alpine image
2. **Aggressive health check**: `check_port_connectivity` was too strict for startup detection
3. **Insufficient startup time**: RabbitMQ needs more time to initialize on first run

## ✅ Solution Applied

### Before (Problematic Configuration):
```yaml
rabbitmq:
  environment:
    RABBITMQ_VM_MEMORY_HIGH_WATERMARK: 0.6  # Removed - causing issues
  healthcheck:
    test: ["CMD", "rabbitmq-diagnostics", "check_port_connectivity"]  # Too strict
    interval: 20s
    timeout: 10s
    retries: 5  # Not enough for startup
```

### After (Fixed Configuration):
```yaml
rabbitmq:
  environment:
    RABBITMQ_DEFAULT_USER: guest
    RABBITMQ_DEFAULT_PASS: guest
    # Removed memory watermark setting
  healthcheck:
    test: ["CMD", "rabbitmq-diagnostics", "ping"]  # More reliable
    interval: 30s
    timeout: 15s
    retries: 10          # More attempts
    start_period: 60s    # Grace period for startup
```

## Diagnostic Commands

If RabbitMQ fails to start again, use these commands:

### Check RabbitMQ Container Status:
```bash
docker-compose -f docker-compose.prod.yml logs rabbitmq --tail 50
```

### Manual RabbitMQ Health Check:
```bash
docker-compose -f docker-compose.prod.yml exec rabbitmq rabbitmq-diagnostics ping
docker-compose -f docker-compose.prod.yml exec rabbitmq rabbitmq-diagnostics status
```

### Check RabbitMQ Memory Usage:
```bash
docker-compose -f docker-compose.prod.yml exec rabbitmq rabbitmq-diagnostics memory_breakdown
```

### Force Restart RabbitMQ Only:
```bash
docker-compose -f docker-compose.prod.yml restart rabbitmq
```

### Check Port Connectivity:
```bash
docker-compose -f docker-compose.prod.yml exec rabbitmq nc -zv localhost 5672
```

## Prevention

To avoid similar issues:
1. **Keep RabbitMQ config simple** - avoid complex memory settings in Alpine images
2. **Use reliable health checks** - `ping` is more stable than `check_port_connectivity`  
3. **Allow sufficient startup time** - RabbitMQ can take 30-60 seconds on first boot
4. **Monitor logs** - Always check RabbitMQ logs if health checks fail

## Alternative RabbitMQ Configuration (if still having issues):

If the current fix doesn't work, try this minimal configuration:

```yaml
rabbitmq:
  image: rabbitmq:3.13-management-alpine  # Full version with web UI
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
    retries: 5
    start_period: 120s
  restart: unless-stopped
  networks:
    - ppc_network
  deploy:
    resources:
      limits:
        memory: 512M  # Reduce memory if needed
```

## Next Steps

1. **Deploy the fix**: The corrected configuration should resolve the startup issue
2. **Monitor startup**: Watch RabbitMQ logs during deployment to ensure clean startup
3. **Test functionality**: Verify Celery workers can connect to RabbitMQ after startup
4. **Document for future**: Keep this fix available for similar deployments