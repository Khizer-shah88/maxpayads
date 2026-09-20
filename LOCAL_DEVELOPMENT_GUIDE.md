# 🚀 Max Pay Ads - Local Development Setup

This guide will help you run the complete Max Pay Ads platform locally with both frontend and backend services.

## Prerequisites

- **Docker** and **Docker Compose** installed
- **Git** for cloning the repository
- At least **4GB RAM** and **10GB free disk space**

## Quick Start

### 1. Setup Environment Variables

Create the backend environment file:
```bash
cp ppc-backend/.env.example ppc-backend/.env
```

Edit `ppc-backend/.env` and set at minimum:
```env
# Required: Change this to a secure random string
SECRET_KEY=your_super_secret_key_here_at_least_32_characters_long

# Optional: Change admin credentials
ADMIN_EMAIL=admin@maxpayads.com
ADMIN_PASSWORD=Admin@123456
ADMIN_NAME=Super Admin
```

### 2. Start All Services

```bash
# Start everything in the background
docker-compose up --build -d

# View logs for all services
docker-compose logs -f

# Or view logs for specific services
docker-compose logs -f fastapi   # Backend logs
docker-compose logs -f nextjs    # Frontend logs
docker-compose logs -f nginx     # Proxy logs
```

### 3. Wait for Services to Start

The initial startup takes **2-3 minutes** because:
- Database seeding (admin user, sample campaigns, templates)
- ML fraud detection model training
- Next.js build process

You can monitor progress with:
```bash
# Check container status
docker-compose ps

# Watch FastAPI startup
docker-compose logs -f fastapi

# Watch Next.js build
docker-compose logs -f nextjs
```

### 4. Access the Application

Once all services are running:

- **Admin Panel**: http://localhost/admin
- **Publisher Panel**: http://localhost/publisher  
- **API Documentation**: http://localhost:8000/docs
- **RabbitMQ Management**: http://localhost:15672 (guest/guest)

**Login Credentials:**
- Email: `admin@maxpayads.com`
- Password: `Admin@123456`

## 🔧 Development Commands

### Managing Services

```bash
# Stop all services
docker-compose down

# Stop and remove all data (fresh start)
docker-compose down -v

# Restart a specific service
docker-compose restart fastapi

# Rebuild and restart
docker-compose up --build -d

# View service status
docker-compose ps
```

### Debugging

```bash
# Access container shells
docker exec -it ppc_fastapi bash
docker exec -it ppc_nextjs sh
docker exec -it ppc_mongodb mongosh

# View detailed logs
docker-compose logs --tail=100 fastapi
docker-compose logs --since=10m nextjs

# Test health endpoints
curl http://localhost/health          # Through nginx
curl http://localhost:8000/health     # Direct FastAPI
curl http://localhost:3000            # Direct Next.js
```

### Database Operations

```bash
# Connect to MongoDB
docker exec -it ppc_mongodb mongosh

# MongoDB commands:
use ppc_network
db.users.find()
db.campaigns.find()
db.publishers.find()

# Redis operations
docker exec -it ppc_redis redis-cli
redis> keys *
redis> get some_key
```

## 📁 Service Architecture

The local environment includes:

| Service | Port | Purpose |
|---------|------|---------|
| **nginx** | 80 | Reverse proxy and SSL termination |
| **nextjs** | 3000 | Frontend (Next.js) |
| **fastapi** | 8000 | Backend API (FastAPI) |
| **mongodb** | 27017 | Database |
| **redis** | 6379 | Cache and sessions |
| **rabbitmq** | 5672, 15672 | Message queue + management UI |
| **celery_worker** | - | Background task processor |
| **celery_beat** | - | Scheduled task scheduler |

## 🔍 Troubleshooting

### Common Issues

**1. "Port already in use" errors:**
```bash
# Check what's using the port
sudo lsof -i :80
sudo lsof -i :3000
sudo lsof -i :8000

# Stop the blocking service or change ports in docker-compose.yml
```

**2. "Cannot connect to Docker daemon":**
```bash
# Start Docker service
sudo systemctl start docker
# Or on macOS: restart Docker Desktop
```

**3. Services taking too long to start:**
```bash
# Check resource usage
docker stats

# Increase Docker memory limit if needed
# Docker Desktop -> Settings -> Resources -> Memory (4GB minimum)
```

**4. FastAPI not responding:**
```bash
# Check if database seeding is still running
docker-compose logs fastapi | tail -20

# Check database connections
docker exec ppc_fastapi curl http://localhost:8000/health
```

**5. Next.js build failures:**
```bash
# Clear Next.js cache and rebuild
docker-compose down
docker system prune -f
docker-compose up --build -d
```

### Health Check Commands

Use these commands to verify everything is working:

```bash
# Test all endpoints
curl http://localhost/health                    # Nginx -> FastAPI
curl http://localhost/api/admin/campaigns       # API through nginx
curl http://localhost:3000                      # Next.js direct
curl http://localhost:8000/docs                 # FastAPI docs

# Test database connections
docker exec ppc_fastapi python -c "
from app.database import connect_db
import asyncio
asyncio.run(connect_db())
print('MongoDB: Connected!')
"

docker exec ppc_fastapi python -c "
from app.cache.redis_client import connect_redis
import asyncio
asyncio.run(connect_redis())
print('Redis: Connected!')
"
```

## 🎯 Source Deterrent System (Active Locally)

The source deterrent system is **enabled by default** in local development:

- **Test with**: Right-click → "View Source" or `Ctrl+U` / `Cmd+U`
- **Expected behavior**: Source view tabs redirect to the rendered page
- **Disable**: Set `ENABLE_SOURCE_DETERRENT=false` in `ppc-frontend/.env.local`

## 🚀 Production vs Development

Key differences from production:

| Feature | Local Development | Production |
|---------|------------------|------------|
| SSL/HTTPS | HTTP only | Full SSL with Cloudflare |
| Initialization | Full database seeding | `SKIP_INIT=true` for fast startup |
| Domains | `localhost` only | Multiple domains (prelander, tracking, etc.) |
| Entry Guard | Disabled | Domain-based access control |
| Resource Limits | No limits | Memory/CPU limits enforced |

## 📚 Next Steps

Once the local environment is running:

1. **Explore Admin Panel**: Create campaigns, manage publishers
2. **API Development**: Use http://localhost:8000/docs for API testing  
3. **Frontend Development**: Next.js files in `ppc-frontend/`
4. **Backend Development**: FastAPI files in `ppc-backend/`
5. **Database Schema**: Check MongoDB collections in the admin panel

## 🆘 Getting Help

If you encounter issues:

1. Check this troubleshooting guide
2. Review service logs with `docker-compose logs [service]`
3. Verify all containers are healthy with `docker-compose ps`
4. Run the diagnostic script: `./deployment-debug.sh`

The complete platform should be accessible at **http://localhost** within 3-5 minutes of startup!