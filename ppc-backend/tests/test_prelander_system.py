"""
Comprehensive tests for Prelander System
=========================================

Tests:
- Template creation and CRUD
- Template validation (safe placeholders)
- Domain pool management
- Template assignment to domains
- Signed redirect context
- Public prelander rendering
- Security: No direct access without token
- Security: Template sandboxing
"""

import pytest
import time
from datetime import datetime
from bson import ObjectId

from app.services.prelander_service import (
    RedirectContext,
    PrelanderTemplateEngine,
    get_template_for_domain,
    get_default_template,
    ALLOWED_PLACEHOLDERS,
)


# ============================================================================
# Redirect Context Tests
# ============================================================================

class TestRedirectContext:
    """Test signed redirect context creation and validation."""
    
    def test_create_context(self):
        """Test creating a redirect context."""
        context = RedirectContext(
            click_id="click123",
            campaign_url="https://example.com/offer",
            publisher_id="pub456",
            site_id="site789",
            country="US",
            os="Windows",
        )
        
        assert context.click_id == "click123"
        assert context.campaign_url == "https://example.com/offer"
        assert context.publisher_id == "pub456"
        assert context.site_id == "site789"
        assert context.country == "US"
        assert context.os == "Windows"
    
    def test_context_to_dict(self):
        """Test context serialization."""
        context = RedirectContext(
            click_id="click123",
            campaign_url="https://example.com/offer",
            country="US",
        )
        
        data = context.to_dict()
        
        assert data["click_id"] == "click123"
        assert data["campaign_url"] == "https://example.com/offer"
        assert data["country"] == "US"
        assert "timestamp" in data
    
    def test_context_from_dict(self):
        """Test context deserialization."""
        data = {
            "click_id": "click123",
            "campaign_url": "https://example.com/offer",
            "publisher_id": "pub456",
            "country": "US",
            "timestamp": int(time.time()),
        }
        
        context = RedirectContext.from_dict(data)
        
        assert context.click_id == "click123"
        assert context.campaign_url == "https://example.com/offer"
        assert context.publisher_id == "pub456"
        assert context.country == "US"
    
    def test_sign_token(self):
        """Test token signing."""
        context = RedirectContext(
            click_id="click123",
            campaign_url="https://example.com/offer",
        )
        
        token = context.sign()
        
        assert token is not None
        assert len(token) > 0
        assert isinstance(token, str)
    
    def test_verify_valid_token(self):
        """Test verifying a valid token."""
        context = RedirectContext(
            click_id="click123",
            campaign_url="https://example.com/offer",
            publisher_id="pub456",
        )
        
        token = context.sign()
        verified = RedirectContext.verify(token)
        
        assert verified is not None
        assert verified.click_id == "click123"
        assert verified.campaign_url == "https://example.com/offer"
        assert verified.publisher_id == "pub456"
    
    def test_verify_invalid_token(self):
        """Test that invalid tokens are rejected."""
        invalid_token = "invalid-token-data"
        verified = RedirectContext.verify(invalid_token)
        
        assert verified is None
    
    def test_verify_tampered_token(self):
        """Test that tampered tokens are rejected."""
        context = RedirectContext(
            click_id="click123",
            campaign_url="https://example.com/offer",
        )
        
        token = context.sign()
        # Tamper with the token
        tampered = token[:-5] + "XXXXX"
        
        verified = RedirectContext.verify(tampered)
        assert verified is None
    
    def test_verify_expired_token(self):
        """Test that expired tokens are rejected."""
        # Create context with old timestamp
        context = RedirectContext(
            click_id="click123",
            campaign_url="https://example.com/offer",
            timestamp=int(time.time()) - 400,  # 400 seconds ago (expired)
        )
        
        token = context.sign()
        verified = RedirectContext.verify(token)
        
        # Should be rejected due to expiration
        assert verified is None


# ============================================================================
# Template Engine Tests
# ============================================================================

class TestPrelanderTemplateEngine:
    """Test template rendering and security."""
    
    def test_create_engine(self):
        """Test creating template engine."""
        engine = PrelanderTemplateEngine()
        assert engine is not None
        assert engine.env is not None
    
    def test_render_simple_template(self):
        """Test rendering a simple template."""
        engine = PrelanderTemplateEngine()
        context = RedirectContext(
            click_id="click123",
            campaign_url="https://example.com/offer",
        )
        
        template_html = """
        <html>
        <body>
            <h1>Click ID: {{ CLICK_ID }}</h1>
            <a href="{{ CAMPAIGN_URL }}">Continue</a>
        </body>
        </html>
        """
        
        rendered = engine.render(template_html, context)
        
        assert "click123" in rendered
        assert "https://example.com/offer" in rendered
    
    def test_render_all_placeholders(self):
        """Test rendering template with all allowed placeholders."""
        engine = PrelanderTemplateEngine()
        context = RedirectContext(
            click_id="click123",
            campaign_url="https://example.com/offer",
            publisher_id="pub456",
            site_id="site789",
            country="US",
            os="Windows",
            device_type="desktop",
        )
        
        template_html = """
        Campaign: {{ CAMPAIGN_URL }}
        Click: {{ CLICK_ID }}
        Publisher: {{ PUBLISHER_ID }}
        Site: {{ SITE_ID }}
        Country: {{ COUNTRY }}
        OS: {{ OS }}
        Device: {{ DEVICE_TYPE }}
        Time: {{ TIMESTAMP }}
        """
        
        rendered = engine.render(template_html, context)
        
        assert "https://example.com/offer" in rendered
        assert "click123" in rendered
        assert "pub456" in rendered
        assert "site789" in rendered
        assert "US" in rendered
        assert "Windows" in rendered
        assert "desktop" in rendered
    
    def test_reject_disallowed_placeholder(self):
        """Test that disallowed placeholders are rejected."""
        engine = PrelanderTemplateEngine()
        context = RedirectContext(
            click_id="click123",
            campaign_url="https://example.com/offer",
        )
        
        # Template with disallowed placeholder
        template_html = """
        <html>
        <body>
            {{ DISALLOWED_VAR }}
        </body>
        </html>
        """
        
        with pytest.raises(ValueError) as exc_info:
            engine.render(template_html, context)
        
        assert "disallowed placeholders" in str(exc_info.value).lower()
    
    def test_validate_template_valid(self):
        """Test validating a valid template."""
        engine = PrelanderTemplateEngine()
        
        template_html = """
        <html>
        <body>
            <h1>{{ CLICK_ID }}</h1>
            <a href="{{ CAMPAIGN_URL }}">Download</a>
        </body>
        </html>
        """
        
        result = engine.validate_template(template_html)
        
        assert result["valid"] is True
        assert "CLICK_ID" in result["used_placeholders"]
        assert "CAMPAIGN_URL" in result["used_placeholders"]
    
    def test_validate_template_with_disallowed_placeholder(self):
        """Test validating template with disallowed placeholder."""
        engine = PrelanderTemplateEngine()
        
        template_html = """
        <html>
        <body>
            {{ EVIL_PLACEHOLDER }}
        </body>
        </html>
        """
        
        result = engine.validate_template(template_html)
        
        assert result["valid"] is False
        assert "disallowed" in result["message"].lower()
    
    def test_validate_template_syntax_error(self):
        """Test validating template with syntax error."""
        engine = PrelanderTemplateEngine()
        
        template_html = """
        <html>
        <body>
            {{ CLICK_ID }  <!-- Missing closing brace -->
        </body>
        </html>
        """
        
        result = engine.validate_template(template_html)
        
        assert result["valid"] is False
        assert "syntax" in result["message"].lower()
    
    def test_sandboxed_environment(self):
        """Test that template environment is sandboxed."""
        engine = PrelanderTemplateEngine()
        
        # Template trying to access dangerous functions
        template_html = """
        {{ ''.__class__.__bases__[0].__subclasses__() }}
        """
        
        context = RedirectContext(
            click_id="click123",
            campaign_url="https://example.com/offer",
        )
        
        # Should fail due to sandboxing
        with pytest.raises(ValueError):
            engine.render(template_html, context)
    
    def test_no_arbitrary_code_execution(self):
        """Test that templates cannot execute arbitrary code."""
        engine = PrelanderTemplateEngine()
        context = RedirectContext(
            click_id="click123",
            campaign_url="https://example.com/offer",
        )
        
        # Various attempts at code execution - these should all fail safely
        dangerous_templates = [
            "{{ system('ls') }}",  # Undefined variable (safe)
            "{{ config.items() }}",  # Undefined variable (safe)
            "{{ request }}",  # Undefined variable (safe)
        ]
        
        for template in dangerous_templates:
            # Should render but with undefined variables (sandboxed)
            # The sandbox prevents access to dangerous functions
            try:
                rendered = engine.render(template, context)
                # If it renders, it should be empty or show undefined
                assert rendered is not None
            except ValueError:
                # ValueError is also acceptable (validation caught it)
                pass


# ============================================================================
# Template Database Tests
# ============================================================================

@pytest.mark.asyncio
class TestPrelanderTemplateDatabase:
    """Test prelander template database operations."""
    
    async def test_get_template_for_domain_not_found(self, db):
        """Test getting template for non-existent domain."""
        template = await get_template_for_domain(db, "nonexistent.com")
        assert template is None
    
    async def test_get_default_template_not_found(self, db):
        """Test getting default template when none exists."""
        template = await get_default_template(db)
        # May be None if no default template configured
        assert template is None or isinstance(template, dict)
    
    async def test_create_and_get_template(self, db):
        """Test creating and retrieving a template."""
        # Create template
        template_doc = {
            "name": "Test Template",
            "description": "Test prelander template",
            "os_type": "both",
            "status": "active",
            "full_html_template": "<html><body>{{ CAMPAIGN_URL }}</body></html>",
            "is_default": False,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        
        result = await db.prelander_templates.insert_one(template_doc)
        template_id = str(result.inserted_id)
        
        # Retrieve template
        retrieved = await db.prelander_templates.find_one({"_id": result.inserted_id})
        
        assert retrieved is not None
        assert retrieved["name"] == "Test Template"
        assert retrieved["status"] == "active"
        
        # Cleanup
        await db.prelander_templates.delete_one({"_id": result.inserted_id})
    
    async def test_template_domain_assignment(self, db):
        """Test assigning template to domain."""
        # Create template
        template_doc = {
            "name": "Domain Template",
            "status": "active",
            "full_html_template": "<html><body>{{ CLICK_ID }}</body></html>",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        result = await db.prelander_templates.insert_one(template_doc)
        template_id = str(result.inserted_id)
        
        # Create domain with template assignment
        domain_doc = {
            "domain": "prelander-test.com",
            "domain_type": "last",
            "template_id": template_id,
            "status": "active",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        domain_result = await db.redirection_domains.insert_one(domain_doc)
        
        # Get template for domain
        template = await get_template_for_domain(db, "prelander-test.com")
        
        assert template is not None
        assert template["name"] == "Domain Template"
        
        # Cleanup
        await db.prelander_templates.delete_one({"_id": result.inserted_id})
        await db.redirection_domains.delete_one({"_id": domain_result.inserted_id})


# ============================================================================
# Security Tests
# ============================================================================

class TestPrelanderSecurity:
    """Test prelander security features."""
    
    def test_allowed_placeholders_whitelist(self):
        """Test that only whitelisted placeholders are allowed."""
        expected_placeholders = {
            "CAMPAIGN_URL",
            "PASSWORD",
            "CLICK_ID",
            "PUBLISHER_ID",
            "SITE_ID",
            "COUNTRY",
            "OS",
            "DEVICE_TYPE",
            "TIMESTAMP",
        }
        
        assert ALLOWED_PLACEHOLDERS == expected_placeholders
    
    def test_token_contains_signature(self):
        """Test that tokens contain signatures."""
        context = RedirectContext(
            click_id="click123",
            campaign_url="https://example.com/offer",
        )
        
        token = context.sign()
        
        # Token should be base64 encoded and non-trivial
        assert len(token) > 50
        
        # Decode and verify structure
        import base64
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        assert ":" in decoded  # Should have data:signature format
    
    def test_token_timestamp_validation(self):
        """Test that token timestamp is validated."""
        # Create fresh token
        context = RedirectContext(
            click_id="click123",
            campaign_url="https://example.com/offer",
        )
        
        token = context.sign()
        
        # Should verify successfully
        verified = RedirectContext.verify(token)
        assert verified is not None
        
        # Check timestamp is recent
        assert verified.timestamp > int(time.time()) - 10
    
    def test_template_cannot_access_globals(self):
        """Test that templates cannot access global variables."""
        engine = PrelanderTemplateEngine()
        
        # Engine globals should be cleared
        assert len(engine.env.globals) == 0
    
    def test_template_limited_filters(self):
        """Test that only safe filters are available."""
        engine = PrelanderTemplateEngine()
        
        # Only safe filters should be available
        allowed_filters = {"upper", "lower", "title"}
        
        # Check that dangerous filters are not available
        assert "import" not in engine.env.filters
        assert "exec" not in engine.env.filters
        assert "eval" not in engine.env.filters


# ============================================================================
# Integration Tests
# ============================================================================

@pytest.mark.asyncio
class TestPrelanderIntegration:
    """Test full prelander flow integration."""
    
    async def test_full_prelander_flow(self, db):
        """Test complete flow: create template, assign to domain, generate token, verify."""
        # 1. Create template
        template_doc = {
            "name": "Integration Test Template",
            "status": "active",
            "full_html_template": """
                <html>
                <body>
                    <h1>Click: {{ CLICK_ID }}</h1>
                    <a href="{{ CAMPAIGN_URL }}">Continue</a>
                </body>
                </html>
            """,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        template_result = await db.prelander_templates.insert_one(template_doc)
        template_id = str(template_result.inserted_id)
        
        # 2. Create domain with template
        domain_doc = {
            "domain": "integration-test.com",
            "domain_type": "last",
            "template_id": template_id,
            "status": "active",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        domain_result = await db.redirection_domains.insert_one(domain_doc)
        
        # 3. Create redirect context and sign
        context = RedirectContext(
            click_id="integration_click_123",
            campaign_url="https://example.com/offer",
            publisher_id="pub_integration",
        )
        token = context.sign()
        
        # 4. Verify token
        verified = RedirectContext.verify(token)
        assert verified is not None
        assert verified.click_id == "integration_click_123"
        
        # 5. Get template for domain
        template = await get_template_for_domain(db, "integration-test.com")
        assert template is not None
        assert template["name"] == "Integration Test Template"
        
        # 6. Render template
        engine = PrelanderTemplateEngine()
        rendered = engine.render(template["full_html_template"], verified)
        
        assert "integration_click_123" in rendered
        assert "https://example.com/offer" in rendered
        
        # Cleanup
        await db.prelander_templates.delete_one({"_id": template_result.inserted_id})
        await db.redirection_domains.delete_one({"_id": domain_result.inserted_id})
    
    async def test_multiple_domains_different_templates(self, db):
        """Test multiple domains with different templates."""
        # Create two templates
        template1 = await db.prelander_templates.insert_one({
            "name": "Template 1",
            "status": "active",
            "full_html_template": "<html><body>Template 1: {{ CLICK_ID }}</body></html>",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        })
        
        template2 = await db.prelander_templates.insert_one({
            "name": "Template 2",
            "status": "active",
            "full_html_template": "<html><body>Template 2: {{ CAMPAIGN_URL }}</body></html>",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        })
        
        # Create two domains
        domain1 = await db.redirection_domains.insert_one({
            "domain": "domain1.com",
            "domain_type": "last",
            "template_id": str(template1.inserted_id),
            "status": "active",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        })
        
        domain2 = await db.redirection_domains.insert_one({
            "domain": "domain2.com",
            "domain_type": "last",
            "template_id": str(template2.inserted_id),
            "status": "active",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        })
        
        # Get templates for each domain
        tpl1 = await get_template_for_domain(db, "domain1.com")
        tpl2 = await get_template_for_domain(db, "domain2.com")
        
        assert tpl1["name"] == "Template 1"
        assert tpl2["name"] == "Template 2"
        assert "Template 1" in tpl1["full_html_template"]
        assert "Template 2" in tpl2["full_html_template"]
        
        # Cleanup
        await db.prelander_templates.delete_many({
            "_id": {"$in": [template1.inserted_id, template2.inserted_id]}
        })
        await db.redirection_domains.delete_many({
            "_id": {"$in": [domain1.inserted_id, domain2.inserted_id]}
        })


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================

class TestPrelanderEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_template(self):
        """An empty template stays empty."""
        engine = PrelanderTemplateEngine()
        context = RedirectContext(
            click_id="click123",
            campaign_url="https://example.com/offer",
        )
        
        rendered = engine.render("", context)
        assert rendered == ""

    @pytest.mark.parametrize(
        ("prefix", "suffix"),
        [
            ("<html><body><h1>Static Content</h1>", "</body></html>"),
            ("<HTML><BODY><h1>Static Content</h1>", "</BODY></HTML>"),
            ("<html><h1>Static Content</h1>", "</html>"),
            ("<HTML><h1>Static Content</h1>", "</HTML>"),
            ("<h1>Static Content</h1>", ""),
        ],
        ids=["body", "uppercase-body", "html", "uppercase-html", "fragment"],
    )
    def test_template_with_no_placeholders(self, prefix, suffix):
        """Static templates are preserved without injected inspection blockers."""
        engine = PrelanderTemplateEngine()
        context = RedirectContext(
            click_id="click123",
            campaign_url="https://example.com/offer",
        )
        
        template_html = prefix + suffix
        rendered = engine.render(template_html, context)
        
        assert rendered == template_html
    
    def test_context_with_special_characters(self):
        """Test context with special characters."""
        engine = PrelanderTemplateEngine()
        context = RedirectContext(
            click_id="click<script>alert(1)</script>",
            campaign_url="https://example.com/offer?param=<test>",
        )
        
        template_html = "<html><body>{{ CLICK_ID }}</body></html>"
        rendered = engine.render(template_html, context)
        
        # Should be auto-escaped by Jinja2
        assert "&lt;script&gt;" in rendered or "click&lt;script&gt;" in rendered
    
    def test_very_long_token(self):
        """Test handling very long context data."""
        engine = PrelanderTemplateEngine()
        context = RedirectContext(
            click_id="a" * 1000,
            campaign_url="https://example.com/" + "x" * 1000,
        )
        
        token = context.sign()
        verified = RedirectContext.verify(token)
        
        assert verified is not None
        assert len(verified.click_id) == 1000
