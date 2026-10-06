# View-Source Redirect - Deployment Checklist

## Pre-Deployment Verification

### ✅ Code Quality Checks

- [x] Syntax validation passed
  ```bash
  python3 -m py_compile ppc-backend/app/middleware/view_source_redirect_middleware.py
  python3 -m py_compile ppc-backend/app/main.py
  ```

- [x] Import statements correct
- [x] Middleware order verified (ViewSourceRedirectMiddleware is first)
- [x] No breaking changes introduced
- [x] Backward compatibility maintained

### ✅ Files Created/Modified

**Created (5 files):**
- [x] `ppc-backend/app/middleware/view_source_redirect_middleware.py`
- [x] `ppc-backend/tests/test_view_source_redirect.py`
- [x] `ppc-backend/verify_view_source_redirect.py`
- [x] `VIEW_SOURCE_PROTECTION.md`
- [x] `VIEW_SOURCE_REDIRECT_IMPLEMENTATION_SUMMARY.md`

**Modified (1 file):**
- [x] `ppc-backend/app/main.py`

### ✅ Testing

- [x] Syntax checks passed
- [ ] Unit tests run (requires pytest in environment)
- [ ] Verification script run (optional if no Python deps available)
- [ ] Manual curl tests performed

## Deployment Steps

### 1. Staging Environment

#### Step 1.1: Deploy Code
```bash
# Pull latest code
cd /path/to/maxpayads
git pull origin main

# Restart backend service
docker-compose restart backend
# OR
systemctl restart ppc-backend
```

#### Step 1.2: Verify Deployment
```bash
# Check service is running
docker-compose ps backend
# OR
systemctl status ppc-backend

# Check logs for startup
docker-compose logs -f backend | grep -i "application startup complete"
```

#### Step 1.3: Test Functionality
```bash
# Test 1: View-source request (should return 301)
curl -I -H "Purpose: view-source" http://staging-domain.com/p/render

# Expected output:
# HTTP/1.1 301 Moved Permanently
# Location: http://staging-domain.com/p/render

# Test 2: Normal request (should return 200)
curl -I http://staging-domain.com/p/render

# Expected output:
# HTTP/1.1 200 OK
```

#### Step 1.4: Monitor Logs
```bash
# Watch for view-source detections
docker-compose logs -f backend | grep "View-source request detected"

# Check for errors
docker-compose logs -f backend | grep -i error
```

### 2. Production Environment

#### Step 2.1: Pre-Production Checklist
- [ ] Staging tests passed
- [ ] No errors in staging logs
- [ ] Performance acceptable (< 1ms overhead)
- [ ] Backward compatibility confirmed
- [ ] Team notified of deployment

#### Step 2.2: Deploy to Production
```bash
# Backup current configuration
docker-compose exec backend python -m app.utils.backup_config

# Pull latest code
git pull origin main

# Restart backend with zero-downtime if possible
docker-compose up -d --no-deps --build backend
# OR
systemctl reload ppc-backend
```

#### Step 2.3: Verify Production
```bash
# Test view-source redirect
curl -I -H "Purpose: view-source" https://production-domain.com/p/render

# Test normal traffic
curl -I https://production-domain.com/p/render

# Monitor logs
docker-compose logs -f backend | grep "View-source"
```

#### Step 2.4: Post-Deployment Monitoring
```bash
# Monitor for 30 minutes
watch -n 30 'docker-compose logs --tail=100 backend | grep -c "View-source request detected"'

# Check error rate
docker-compose logs --since 30m backend | grep -i error | wc -l

# Check normal traffic still flowing
docker-compose logs --since 30m backend | grep "GET /p/render" | head -20
```

## Verification Tests

### Test 1: Purpose Header Detection
```bash
curl -v -H "Purpose: view-source" https://your-domain.com/p/render 2>&1 | grep "HTTP/"
# Should see: HTTP/1.1 301 Moved Permanently
```

### Test 2: X-Purpose Header Detection
```bash
curl -v -H "X-Purpose: view-source" https://your-domain.com/d/test 2>&1 | grep "HTTP/"
# Should see: HTTP/1.1 301 Moved Permanently
```

### Test 3: Referer Detection
```bash
curl -v -H "Referer: view-source:https://example.com" https://your-domain.com/p/render 2>&1 | grep "HTTP/"
# Should see: HTTP/1.1 301 Moved Permanently
```

### Test 4: Normal Request Pass-Through
```bash
curl -v https://your-domain.com/p/render 2>&1 | grep "HTTP/"
# Should see: HTTP/1.1 200 OK (or appropriate response)
```

### Test 5: Query Parameter Preservation
```bash
curl -v -H "Purpose: view-source" "https://your-domain.com/p/render?token=abc123&os=windows" 2>&1 | grep "Location:"
# Should see: Location: https://your-domain.com/p/render?token=abc123&os=windows
```

### Test 6: Cache Headers
```bash
curl -v -H "Purpose: view-source" https://your-domain.com/p/render 2>&1 | grep -i "cache-control"
# Should see: Cache-Control: no-cache, no-store, must-revalidate
```

## Monitoring Setup

### Set Up Alerts (Optional)

#### High Frequency of View-Source Attempts
```bash
# Alert if more than 100 view-source attempts in 5 minutes
if [ $(docker-compose logs --since 5m backend | grep -c "View-source request detected") -gt 100 ]; then
    echo "HIGH: Unusual view-source activity" | mail -s "View-Source Alert" admin@domain.com
fi
```

#### Error Rate Increase
```bash
# Alert if error rate spikes
ERRORS=$(docker-compose logs --since 5m backend | grep -i error | wc -l)
if [ $ERRORS -gt 50 ]; then
    echo "HIGH: Error rate increased after deployment" | mail -s "Error Alert" admin@domain.com
fi
```

### Dashboard Metrics

Add to monitoring dashboard:
1. **View-Source Redirect Count** - Hourly/Daily
2. **Detection Method Breakdown** - Pie chart
3. **Top Targeted Paths** - Bar chart
4. **Response Time P95** - Line chart
5. **Error Rate** - Line chart

### Log Retention

Ensure logs are retained for analysis:
```bash
# Rotate logs but keep 30 days
docker-compose exec backend python -m app.utils.setup_log_rotation
```

## Rollback Plan

### If Issues Detected

#### Step 1: Identify Issue
```bash
# Check error logs
docker-compose logs --since 10m backend | grep -i error

# Check if normal traffic affected
docker-compose logs --since 10m backend | grep "GET /p/render" | grep -v "301"
```

#### Step 2: Quick Rollback
```bash
# Option A: Disable middleware via environment variable (if implemented)
docker-compose exec backend env DISABLE_VIEW_SOURCE_REDIRECT=true

# Option B: Git rollback
git revert HEAD
docker-compose restart backend

# Option C: Previous version
git checkout <previous-commit-hash>
docker-compose up -d --no-deps --build backend
```

#### Step 3: Verify Rollback
```bash
# Verify normal traffic restored
curl -I https://your-domain.com/p/render
# Should return 200

# Check logs for errors
docker-compose logs --tail=50 backend
```

## Post-Deployment Actions

### Day 1
- [ ] Monitor logs every 2 hours
- [ ] Check error rates
- [ ] Verify normal traffic unaffected
- [ ] Document any view-source attempts

### Week 1
- [ ] Daily log review
- [ ] Compile statistics on view-source attempts
- [ ] Analyze detection method distribution
- [ ] Review performance metrics

### Week 2+
- [ ] Weekly review of view-source patterns
- [ ] Optimize detection methods if needed
- [ ] Update documentation with findings
- [ ] Consider additional security layers

## Performance Baseline

### Before Deployment
```bash
# Measure current response time
ab -n 1000 -c 10 https://your-domain.com/p/render
```

### After Deployment
```bash
# Compare response time (should be < 1ms difference)
ab -n 1000 -c 10 https://your-domain.com/p/render
```

### Expected Results
- Response time increase: < 1ms
- Error rate: No increase
- Throughput: No decrease
- CPU usage: < 1% increase
- Memory usage: No significant change

## Documentation Updates

- [ ] Update internal wiki with new feature
- [ ] Add to security documentation
- [ ] Update deployment runbook
- [ ] Add to incident response procedures
- [ ] Document in architecture diagrams

## Team Communication

### Pre-Deployment Email Template
```
Subject: View-Source Redirect Middleware Deployment

Team,

We will be deploying a new security feature: View-Source Redirect Middleware

What: Server-side protection against view-source requests
When: [Date/Time]
Duration: ~5 minutes downtime (if any)
Impact: None expected for normal users
Risk: Low

What to watch:
- View-source attempts will be logged
- Normal traffic should be unaffected
- Performance impact < 1ms

Rollback plan: Available if issues detected

Questions? Contact [Your Name]
```

### Post-Deployment Email Template
```
Subject: View-Source Redirect Deployment Complete

Team,

View-Source Redirect Middleware has been successfully deployed.

Status: ✅ Deployed and Verified
Time: [Deployment Time]
Issues: None

Initial Metrics (first hour):
- View-source redirects: [count]
- Normal requests: [count]
- Error rate: [rate]
- Performance impact: < 1ms

Monitoring: Active for next 48 hours

Documentation: VIEW_SOURCE_PROTECTION.md

Thanks!
```

## Success Criteria

Deployment is considered successful when:

- [ ] ✅ All tests pass (6/6)
- [ ] ✅ No increase in error rate
- [ ] ✅ Performance impact < 1ms
- [ ] ✅ Normal traffic unaffected
- [ ] ✅ View-source requests properly redirected
- [ ] ✅ Logs showing successful detections
- [ ] ✅ No rollback needed for 24 hours
- [ ] ✅ Team notified of success

## Completion

**Deployed By**: _______________  
**Date**: _______________  
**Environment**: [ ] Staging [ ] Production  
**Status**: [ ] Success [ ] Rolled Back [ ] Issues (document below)

**Issues/Notes**:
_____________________________________________________________________________
_____________________________________________________________________________
_____________________________________________________________________________

**Sign-off**: _______________

---

**Document Version**: 1.0  
**Last Updated**: October 6, 2026  
**Next Review**: After deployment completion
