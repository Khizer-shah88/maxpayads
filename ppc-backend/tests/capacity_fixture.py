"""LOCAL ONLY benchmark entrypoint: real app/middleware, no production data.

Only health and configured portal checks are meaningful here. Database access
raises, and Redis is an in-memory counter. This is NOT a whole-stack benchmark.
Run: uvicorn tests.capacity_fixture:app --host 127.0.0.1 --port 8000 --no-access-log
"""
from collections import Counter
from contextlib import asynccontextmanager

from app.main import app
from app.config import settings
from app import database
from app.cache import redis_client
from app.middleware import domain_access_middleware


class NoDatabase:
    def __getattr__(self, name):
        raise RuntimeError('The local capacity fixture cannot access a database')


class LocalRedis:
    def __init__(self):
        self.counts = Counter()

    async def evalsha(self, sha, count, key, ttl):
        self.counts[key] += 1
        return self.counts[key]


@asynccontextmanager
async def local_lifespan(app):
    yield


settings.PORTAL_HOSTNAMES = 'localhost,127.0.0.1,portal.example'
database.get_database = lambda: NoDatabase()
domain_access_middleware.get_database = database.get_database
redis_client.redis_client = LocalRedis()
app.router.lifespan_context = local_lifespan
