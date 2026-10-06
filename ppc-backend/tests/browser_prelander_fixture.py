"""Local browser-test app: real prelander routes, in-memory Redis/database.

Never mount this fixture in the deployed application. It deliberately exposes
a test-only session issuer so the browser test needs no production credentials.
"""
import os
from types import SimpleNamespace

from bson import ObjectId
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse

from app.config import settings
from app.dependencies import get_db
from app.routers import prelander_router as routes
from app.services import prelander_auth_service as auth
from test_prelander_auth import FakeRedis
from test_publisher_stats_actions import Collection

settings.PRELANDER_COOKIE_SECURE = False  # loopback HTTP test server only
settings.PORTAL_HOSTNAMES = "127.0.0.1"
redis = FakeRedis()
campaign_id, html_id, builtin_id = ObjectId(), ObjectId(), ObjectId()
offer_url = "https://offer.example/selected?click=browser-test"
domain = {"domain": "localhost", "domain_type": "prelander", "status": "active", "template_id": str(html_id)}
db = SimpleNamespace(
    redirection_domains=Collection([domain]),
    campaigns=Collection([{"_id": campaign_id, "name": "Browser fixture", "default_offer_url": "https://wrong.example/"}]),
    prelander_templates=Collection([
        {"_id": html_id, "status": "active", "name": "Browser HTML", "full_html_template":
         '<!doctype html><html><head><title>Browser fixture prelander</title></head>'
         '<body><h1>Authorized prelander</h1><a id="continue" href="{Campaign_URL}">Continue</a>'
         '<script>window.templateScriptRan = true</script></body></html>'},
        {"_id": builtin_id, "status": "active", "name": "Browser built-in", "title": "Built-in prelander", "os_type": "windows"},
    ]),
    landing_pages=Collection(), system_settings=Collection(), direct_links=Collection(),
)
routes.get_redis_safe = lambda: redis
app = FastAPI()
app.include_router(routes.router)
app.dependency_overrides[get_db] = lambda: db


@app.middleware("http")
async def log_session_gate(request: Request, call_next):
    response = await call_next(request)
    if request.url.path in ("/prelander/session-check", "/prelander/claim"):
        session = await auth.validate_prelander_session(request.cookies.get(auth.PL_SESSION_COOKIE), redis)
        print(f"gate={request.url.path} status={response.status_code} host={request.headers.get('host')} "
              f"cookie={bool(request.cookies.get(auth.PL_SESSION_COOKIE))} session_host={session.prelander_host if session else None}", flush=True)
    return response


@app.get("/domain-access")
async def domain_access(request: Request):
    # Host-role lookup is a fixture boundary; routing/authentication is real.
    return {"role": "prelander" if request.headers.get("host", "").split(":")[0] == "localhost" else "portal"}


@app.get("/browser-test/start")
async def start(request: Request, variant: str = "html"):
    domain["template_id"] = str(html_id if variant == "html" else builtin_id)
    session = await auth.create_authorization(
        "browser-test", "browser-test-slug", "127.0.0.1", request.headers.get("user-agent", ""), redis,
        prelander_host="localhost", campaign_id=str(campaign_id), offer_url=offer_url,
        publisher_id="publisher-test", os="windows",
    )
    token = await auth.mint_handoff(session, redis, target_host="localhost")
    port = os.environ["PRELANDER_BROWSER_PORT"]
    return RedirectResponse(f"http://localhost:{port}/_auth/{token}", status_code=302)


@app.post("/browser-test/revoke")
async def revoke(request: Request):
    sid = request.cookies.get(auth.PL_SESSION_COOKIE)
    if sid:
        await redis.delete(auth._pl_session_key(sid))
    return {"ok": True}


@app.get("/browser-test/health")
async def health():
    return {"ok": True}
