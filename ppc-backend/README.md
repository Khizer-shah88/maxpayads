# Max Pay Ads Platform

A complete CPC advertising network — click tracking, fraud detection, traffic routing, publisher management, and analytics. Built with FastAPI + MongoDB + Redis + RabbitMQ + Next.js.

## Architecture

| Component | Tech | Purpose |
|-----------|------|---------|
| API Server | FastAPI | REST API, click tracking, ad serving |
| Database | MongoDB 7 | Clicks, publishers, campaigns, fraud logs |
| Cache | Redis 7 | Rate limiting, stats caching, session tokens |
| Queue | RabbitMQ + Celery | Background fraud detection, earnings calc |
| ML | Scikit-learn (Isolation Forest) | Anomaly-based fraud scoring |
| Frontend | Next.js 14, Tailwind CSS | Admin + Publisher dashboards, public site |

## Click Flow

```
Click → Fraud Check (inline) → Resolve Publisher/Website → Campaign Match
     → GEO Rules → Device/OS Rules → Landing Page → Final Redirect (<50ms)
     → Background: ML fraud check + CPC calc + earnings update
```

## Quick Start (Local Development)

### Prerequisites
- Python 3.11+, Node.js 18+
- MongoDB, Redis, RabbitMQ (or use Docker)

### 1. Start infrastructure
```bash
cd ppc-backend/docker
docker-compose up -d mongodb redis rabbitmq
```

### 2. Backend setup
```bash
cd ppc-backend
cp .env.example .env          # Edit with your settings
pip install -r requirements.txt

python scripts/seed_admin.py        # Create admin (admin@maxpayads.com / Admin@123456)
python scripts/seed_campaigns.py    # Sample campaigns + routing rules
python scripts/train_fraud_model.py # Train ML fraud model

uvicorn app.main:app --reload --port 8000
```

### 3. Celery worker (separate terminal)
```bash
cd ppc-backend
celery -A app.tasks.celery_app worker --loglevel=info
```

### 4. Frontend setup
```bash
cd ppc-frontend
npm install
npm run dev    # http://localhost:3000
```

### 5. Access
| URL | Purpose |
|-----|---------|
| http://localhost:3000 | Public site + dashboards |
| http://localhost:8000/docs | API documentation (Swagger) |
| http://localhost:8000/redoc | API documentation (ReDoc) |

### Default admin login
- Email: `admin@maxpayads.com`
- Password: `Admin@123456`

## Full Docker Deployment

```bash
cd ppc-backend/docker
docker-compose up -d
```

Services: FastAPI (8000), MongoDB (27017), Redis (6379), RabbitMQ (5672/15672), Celery worker (4 threads), Celery beat (scheduled tasks), Nginx (80).

### Reset all data (clean start)
```bash
cd ppc-backend/docker
bash reset-volumes.sh
```

## Project Structure

### Backend (`ppc-backend/`)
```
app/
├── main.py                    # FastAPI entry point
├── config.py, database.py     # Configuration & DB connection
├── routers/                   # API endpoints (7 routers)
│   ├── auth_router.py         #   Login, register, JWT refresh
│   ├── click_router.py        #   /click endpoint + click data export
│   ├── admin_router.py        #   Dashboard, publisher mgmt, records, CSV
│   ├── publisher_router.py    #   Publisher dashboard, websites, profile
│   ├── campaign_router.py     #   Campaign CRUD, GEO/device rules
│   ├── withdrawal_router.py   #   Withdrawal requests + admin actions
│   └── analytics_router.py    #   Platform analytics + trends
├── services/                  # Business logic
│   ├── fraud_service.py       #   6-layer fraud detection
│   ├── traffic_router.py      #   GEO + device routing engine
│   ├── cpc_engine.py          #   CPC pricing (100+ countries)
│   ├── earnings_service.py    #   Publisher earnings calculation
│   └── ...
├── ml/                        # Isolation Forest fraud model
├── tasks/                     # Celery background tasks
├── routing_engine/            # Click destination routing
└── middleware/                # Auth, rate limiting, request logging
```

### Frontend (`ppc-frontend/`)
```
app/
├── page.tsx                   # Public landing page
├── publishers/page.tsx        # Publisher info page
├── docs/page.tsx              # Documentation page
├── contact/page.tsx           # Contact page
├── (auth)/                    # Login + Register
├── admin/                     # Admin dashboard (8 pages)
│   ├── dashboard, campaigns, publishers, clicks
│   ├── cpc, fraud, withdrawals, records
└── publisher/                 # Publisher dashboard (4 pages)
    ├── dashboard, ad-units, reports, withdrawals
```

## Key API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/register` | Publisher signup |
| POST | `/auth/login` | JWT authentication |
| GET | `/click?pub={id}&site={id}` | Click tracking + redirect |
| GET | `/ad.js?pub={id}&site={id}` | Ad embed JavaScript |
| GET | `/admin/dashboard` | Platform-wide stats |
| GET | `/admin/records` | Publisher records with date filtering |
| GET | `/admin/records/export-csv` | Export all records as CSV |
| GET | `/publisher/dashboard` | Publisher stats (auto-refresh) |
| POST | `/campaigns` | Create campaign |
| POST | `/campaigns/{id}/geo-rules` | Add GEO routing rule |
| POST | `/withdrawals` | Request payout |

## Fraud Detection

Six-layer protection:
1. **Bot UA** — blocks Selenium, Puppeteer, curl, and 30+ bot signatures
2. **Datacenter IP** — blocks AWS, GCP, Azure, DigitalOcean, and 50+ CIDR ranges
3. **Rate Limit** — max 10 clicks per IP per minute
4. **Duplicate Click** — same IP + publisher blocked for 10 minutes
5. **ML Anomaly** — Isolation Forest model (8 features, threshold 0.65)
6. **Custom Rules** — extensible rule engine

Checks 1-4 run inline before redirect. Check 5 runs in background via Celery.

## CPC Pricing

Priority: Publisher custom CPC > Country override > Default country table > Device modifier > Global default ($0.05).

Earnings formula: `CPC × revenue_share` (default 80%).

## Environment Variables

See [`.env.example`](.env.example) for all configuration options.
