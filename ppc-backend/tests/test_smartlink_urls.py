"""Public link generation and click compatibility without MongoDB or Redis."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.routers import admin_router, click_router
from app.services import domain_service, smartlink_signing
from app.services.smartlink_service import generate_smartlink
from app.services.smartlink_parser import generate_smartlink_with_structure
from app.utils import public_id_utils


PUB = "PUB_TEST1234"
SITE = "SITE_TEST1234"


@pytest.fixture
def public_ids(monkeypatch):
    monkeypatch.setattr(public_id_utils, "get_publisher_public_id", AsyncMock(return_value=PUB))
    monkeypatch.setattr(public_id_utils, "get_website_public_id", AsyncMock(return_value=SITE))


@pytest.mark.parametrize("website_id, expected", [(None, {"pub": [PUB]}), ("website", {"pub": [PUB], "site": [SITE]})])
async def test_service_generates_only_identifiers(public_ids, website_id, expected):
    link = await generate_smartlink(None, "publisher", website_id, "https://anchor.example/")
    assert urlsplit(link).path == "/click"
    assert parse_qs(urlsplit(link).query) == expected
    assert link == await generate_smartlink(None, "publisher", website_id, "https://anchor.example/")


@pytest.mark.parametrize("use_public_ids", [True, False])
async def test_service_without_saved_structures(public_ids, use_public_ids):
    database = SimpleNamespace(
        smartlink_structures=SimpleNamespace(find_one=AsyncMock(return_value=None)),
    )
    referrer = "https://example.com/page?source=email&offer=a+b#details"
    link = await generate_smartlink(
        database, "publisher", "website", "https://anchor.example/",
        use_public_ids=use_public_ids, referrer=referrer,
        custom_params={"campaign": "summer / sale"},
    )
    assert link.startswith("https://anchor.example/click?")
    assert "ref=https%3A%2F%2Fexample.com%2Fpage%3F" in link
    assert parse_qs(urlsplit(link).query) == {
        "pub": [PUB if use_public_ids else "publisher"],
        "site": [SITE if use_public_ids else "website"],
        "ref": [referrer],
        "campaign": ["summer / sale"],
    }


@pytest.mark.parametrize("selection", ["default", "active", "explicit"])
@pytest.mark.parametrize("include_website", [True, False])
async def test_structure_generation_preserves_configuration(selection, include_website):
    structure = {
        "name": "Custom", "publisher_param": "tag", "website_param": "sid",
        "include_website": include_website,
        "extra_params": [{"key": "source", "value": "email / newsletter"}],
    }
    find_one = AsyncMock(side_effect=[None, structure] if selection == "active" else [structure])
    database = SimpleNamespace(smartlink_structures=SimpleNamespace(find_one=find_one))
    structure_id = "507f1f77bcf86cd799439011" if selection == "explicit" else None
    link = await generate_smartlink_with_structure(
        database, PUB, SITE, structure_id=structure_id,
        domain="https://anchor.example/", extra_params={"ref": "https://example.com/page"},
    )
    expected = {"tag": [PUB], "source": ["email / newsletter"], "ref": ["https://example.com/page"]}
    if include_website:
        expected["sid"] = [SITE]
    assert urlsplit(link).path == "/click"
    assert parse_qs(urlsplit(link).query) == expected
    if selection == "explicit":
        assert str(find_one.call_args.args[0]["_id"]) == structure_id
    elif selection == "active":
        assert find_one.call_args.args[0] == {"status": "active"}
    else:
        find_one.assert_awaited_once_with({"is_default": True, "status": "active"})


@pytest.mark.parametrize("publisher_type, site_count", [("manual", 0), ("registered", 2), ("registered", 0)])
async def test_admin_links_follow_publisher_type(public_ids, monkeypatch, publisher_type, site_count):
    async def sites():
        for index in range(site_count):
            yield {"_id": f"website-{index}", "public_id": f"{SITE}_{index}"}

    database = SimpleNamespace(
        publishers=SimpleNamespace(find_one=AsyncMock(return_value={"publisher_type": publisher_type})),
        smartlink_structures=SimpleNamespace(find_one=AsyncMock(return_value=None)),
        websites=SimpleNamespace(find=Mock(side_effect=lambda _: sites())),
    )
    monkeypatch.setattr(domain_service, "resolve_domain_url", AsyncMock(return_value="https://anchor.example/"))
    result = await admin_router.admin_get_publisher_smartlink(
        "publisher", structure_id=None, db=database, current_user={}
    )
    if publisher_type == "manual":
        assert result["smartlink"] == f"https://anchor.example/click?pub={PUB}"
        assert result["website_smartlinks"] == []
        database.websites.find.assert_not_called()
    elif site_count:
        assert result["smartlink"] == result["website_smartlinks"][0]["smartlink"]
        assert len(result["website_smartlinks"]) == site_count
        for index, entry in enumerate(result["website_smartlinks"]):
            assert parse_qs(urlsplit(entry["smartlink"]).query) == {"pub": [PUB], "site": [f"{SITE}_{index}"]}
    else:
        assert result["smartlink"] is None
        assert result["website_smartlinks"] == []


@pytest.mark.parametrize("site", [None, SITE])
@pytest.mark.parametrize("signature", ["absent", "valid", "invalid"])
async def test_click_accepts_clean_and_existing_signed_links(monkeypatch, site, signature):
    monkeypatch.setattr(smartlink_signing, "hash_required", lambda: False)
    monkeypatch.setitem(smartlink_signing._SECRET_CACHE, "secret", "smartlink-test-secret")
    context = SimpleNamespace(
        destination_url="https://destination.example/", referrer_suppression=False,
        prelander_auth_token=None,
    )
    make_context = Mock(return_value=context)
    pipeline = AsyncMock()
    monkeypatch.setattr(click_router, "context_from_request", make_context)
    monkeypatch.setattr(click_router, "resolve_redirect", pipeline)
    app = FastAPI()
    app.include_router(click_router.router)
    app.dependency_overrides[click_router.get_db] = lambda: None
    app.dependency_overrides[click_router.get_redis_client] = lambda: None
    params = {"pub": PUB}
    if site:
        params["site"] = site
    if signature != "absent":
        params.update(smartlink_signing.signed_link_params(PUB, site))
        if signature == "invalid":
            params["hmac"] = "invalid"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/click", params=params)
    if signature == "invalid":
        assert response.status_code == 403
        pipeline.assert_not_awaited()
    else:
        assert response.status_code == 302
        assert response.headers["location"] == context.destination_url
        assert make_context.call_args.args[1:] == (PUB, site)
        pipeline.assert_awaited_once()
