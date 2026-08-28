# Max Pay Ads — Production Deployment Runbook

Full-stack platform: Next.js frontend + FastAPI backend + MongoDB + Redis +
RabbitMQ + Celery worker/beat, fronted by nginx and Cloudflare.

## What is production ready here

The repo is organized for one fresh server bootstrap and one repeatable deploy
command:

1. Bootstrap the Ubuntu host as `root` once.
2. Use a `deploy` user for all app changes.
3. Keep secrets and certificates outside git.
4. Deploy with `docker compose -f docker-compose.prod.yml up -d --build`.

## Target host

Ubuntu 22.04 or 24.04 LTS on a VPS with enough headroom for the stack. The
existing production compose file assumes Docker Compose v2.

## Domains

| Domain | Role |
|--------|------|
| `maxpayads.com` | Admin and publisher dashboard |
| `browsmac.org` | Anchor/redirect domain (`ad.js`) |
| `clickspot.icu` | Click tracking (`/click`, `/go`) |
| `clickfilesetup.info` | Windows prelander (`/d/{slug}`) |
| `rydestudio.info` | Mac prelander (`/d/{slug}`) |

## Files you must provide

1. `deployment/.env.production`
2. `deployment/certs/origin.crt` and `deployment/certs/origin.key`
3. `ppc-backend/GeoLite2-Country.mmdb`

The deploy script checks all three and aborts early if one is missing.

## Fresh server bootstrap

Start by logging in as `root` with the client's SSH access, then run:

```bash
ssh root@YOUR_SERVER_IP 'bash -s' < deployment/1-server-setup.sh
```

That script creates a `deploy` user, enables the firewall, and installs Docker
plus the Compose v2 plugin. After it finishes, reconnect as `deploy`.

## First deployment

Copy the repository to the server, including the deployment folder, but keep
the secret files local to the server if you already created them there:

```bash
rsync -az --exclude node_modules --exclude .next --exclude venv \
  ./ deploy@YOUR_SERVER_IP:/home/deploy/maxpayads/
```

Then place these files on the server:

```bash
scp deployment/.env.production deploy@YOUR_SERVER_IP:/home/deploy/maxpayads/
scp deployment/certs/origin.crt deploy@YOUR_SERVER_IP:/home/deploy/maxpayads/deployment/certs/
scp deployment/certs/origin.key deploy@YOUR_SERVER_IP:/home/deploy/maxpayads/deployment/certs/
scp ppc-backend/GeoLite2-Country.mmdb deploy@YOUR_SERVER_IP:/home/deploy/maxpayads/ppc-backend/
```

Install the origin certificate and verify it:

```bash
ssh deploy@YOUR_SERVER_IP
cd /home/deploy/maxpayads
bash deployment/3-setup-ssl.sh
```

Run the production deploy:

```bash
bash deployment/2-deploy.sh
```

## CI/CD with GitHub Actions

Add these repository secrets:

| Secret | Purpose |
|--------|---------|
| `SERVER_HOST` | VPS hostname or IP |
| `SERVER_USER` | Usually `deploy` |
| `SERVER_SSH_KEY` | Private SSH key for GitHub Actions |

If you store them in a GitHub Environment instead of repository secrets, use the `production` environment because the deploy workflow reads that environment.

Recommended flow:

1. Use the root password once to create the server user.
2. Add a dedicated SSH key for GitHub Actions.
3. Push to `main` to run CI.
4. Trigger deploy from GitHub Actions after CI passes.

## Verify

```bash
docker compose -f docker-compose.prod.yml ps
curl -sSf http://localhost/health
docker compose -f docker-compose.prod.yml logs -f fastapi
```

The public entry points are:

1. `https://vertexmonetize.com`
2. `https://vertexmonetize.com/admin/auth`

## Day-2 operations

| Task | Command |
|------|---------|
| Logs | `docker compose -f docker-compose.prod.yml logs -f` |
| Restart | `docker compose -f docker-compose.prod.yml restart` |
| Stop | `docker compose -f docker-compose.prod.yml down` |
| Redeploy | `bash deployment/2-deploy.sh` |

## Notes

- Keep `deployment/.env.production`, `deployment/certs/origin.*`, and
  `ppc-backend/GeoLite2-Country.mmdb` out of git.
- The repo includes development-only compose files, but the production path
  uses only `docker-compose.prod.yml`.
