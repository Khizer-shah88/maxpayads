"""
Prelander template favicon support.

The admin adds a favicon to a prelander template either as a URL or as a full
<link rel="icon"> snippet (the docs spell example hosts with anti-scam
brackets: https://example[.]com/...). The favicon must:

- pass validation in the create/update schema and be stored fetchable
  (brackets cleaned, https added, href extracted from a pasted snippet),
- reach every rendering surface the template drives (the /d page payload,
  server-side rendered full-HTML documents),
- never break rendering when absent or invalid.
"""
import pytest

from app.schemas.prelander_template_schema import PrlanderTemplateCreate
from app.services.prelander_service import (
    find_favicon_urls,
    normalize_favicon_url,
    favicon_link_html,
    PrelanderTemplateEngine,
    RedirectContext,
)


BRACKET_URL = "https://example[.]com/66c503d081b2f012369fc5d2/674000d6c0a42d41f8c331be_dropbox-2-logo-png-transparent.png?v=2"
SNIPPET = (
    '<link\n  rel="icon"\n  type="image/png"\n'
    f'  href="{BRACKET_URL}"\n>'
)


def test_bracket_notation_is_normalized_to_a_fetchable_url():
    assert normalize_favicon_url(BRACKET_URL) == BRACKET_URL.replace('[.]', '.')


def test_bare_hostname_becomes_https():
    assert normalize_favicon_url("example.com/a.png") == "https://example.com/a.png"


def test_full_link_snippet_is_reduced_to_its_href():
    assert normalize_favicon_url(SNIPPET) == BRACKET_URL.replace('[.]', '.')


def test_invalid_or_missing_favicon_is_dropped():
    assert normalize_favicon_url(None) is None
    assert normalize_favicon_url("") is None
    assert normalize_favicon_url("   ") is None
    # http:// is not acceptable on public prelander domains
    assert normalize_favicon_url("http://example.com/a.png") is None


def test_find_favicon_urls_finds_rel_icon_variants():
    html = (
        '<link rel="shortcut icon" href="/a.ico">'
        '<link REL="Icon" href="/b.png">'
        '<link rel="stylesheet" href="/c.css">'
    )
    assert find_favicon_urls(html) == ["/a.ico", "/b.png"]


def test_schema_accepts_snippet_and_stores_clean_url():
    tpl = PrlanderTemplateCreate(name="Fav Template", favicon_url=SNIPPET)
    assert tpl.favicon_url == BRACKET_URL.replace('[.]', '.')


def test_schema_allows_no_favicon():
    tpl = PrlanderTemplateCreate(name="No Fav Template")
    assert tpl.favicon_url is None


def test_full_html_render_preserves_the_admin_favicon_link():
    tpl = (
        '<!DOCTYPE html><html><head><title>T</title>'
        f'{SNIPPET}</head><body><a href="{{Campaign_URL}}">go</a></body></html>'
    )
    ctx = RedirectContext(click_id="c1", campaign_url="https://camp.example", os="windows")
    out = PrelanderTemplateEngine().render(tpl, ctx)
    assert 'rel="icon"' in out
    assert BRACKET_URL.replace('[.]', '.') in out


def test_favicon_link_html_builder():
    assert favicon_link_html("https://example.com/a.png") == (
        '<link rel="icon" type="image/png" href="https://example.com/a.png">'
    )
    assert favicon_link_html(None) == ""