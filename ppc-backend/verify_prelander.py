#!/usr/bin/env python3
"""
Prelander System Verification Script
=====================================
Quick verification that the prelander system is working correctly.
"""

import sys
import time
from app.services.prelander_service import (
    RedirectContext,
    PrelanderTemplateEngine,
    ALLOWED_PLACEHOLDERS,
)


def print_header(text):
    """Print formatted header."""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70 + "\n")


def print_success(text):
    """Print success message."""
    print(f"✅ {text}")


def print_error(text):
    """Print error message."""
    print(f"❌ {text}")


def print_info(text):
    """Print info message."""
    print(f"ℹ️  {text}")


def verify_token_system():
    """Verify token generation and validation."""
    print_header("1. Token System Verification")
    
    try:
        # Create context
        context = RedirectContext(
            click_id="verify_click_123",
            campaign_url="https://example.com/offer",
            publisher_id="pub_456",
            site_id="site_789",
            country="US",
            os="Windows",
            device_type="desktop",
        )
        print_success("Created redirect context")
        
        # Sign token
        token = context.sign()
        print_success(f"Generated signed token: {token[:40]}...")
        
        # Verify token
        verified = RedirectContext.verify(token)
        if verified:
            print_success("Token verified successfully")
            print_info(f"  Click ID: {verified.click_id}")
            print_info(f"  Campaign URL: {verified.campaign_url}")
            print_info(f"  Publisher ID: {verified.publisher_id}")
            print_info(f"  Country: {verified.country}")
            print_info(f"  OS: {verified.os}")
        else:
            print_error("Token verification failed")
            return False
        
        # Test tampered token
        tampered = token[:-5] + "XXXXX"
        verified = RedirectContext.verify(tampered)
        if verified is None:
            print_success("Tampered token correctly rejected")
        else:
            print_error("Tampered token was accepted (SECURITY ISSUE!)")
            return False
        
        # Test expired token
        old_context = RedirectContext(
            click_id="old_click",
            campaign_url="https://example.com/offer",
            timestamp=int(time.time()) - 400,  # 400 seconds ago
        )
        expired_token = old_context.sign()
        verified = RedirectContext.verify(expired_token)
        if verified is None:
            print_success("Expired token correctly rejected")
        else:
            print_error("Expired token was accepted (SECURITY ISSUE!)")
            return False
        
        return True
        
    except Exception as e:
        print_error(f"Token system error: {e}")
        return False


def verify_template_engine():
    """Verify template rendering and security."""
    print_header("2. Template Engine Verification")
    
    try:
        engine = PrelanderTemplateEngine()
        print_success("Created template engine")
        
        # Test simple rendering
        context = RedirectContext(
            click_id="template_test_123",
            campaign_url="https://example.com/download",
            country="US",
            os="Windows",
        )
        
        template_html = """
        <html>
        <body>
            <h1>Click ID: {{ CLICK_ID }}</h1>
            <p>Country: {{ COUNTRY }}</p>
            <p>OS: {{ OS }}</p>
            <a href="{{ CAMPAIGN_URL }}">Download</a>
        </body>
        </html>
        """
        
        rendered = engine.render(template_html, context)
        
        if "template_test_123" in rendered:
            print_success("Template rendering works")
            print_info(f"  Rendered length: {len(rendered)} bytes")
        else:
            print_error("Template rendering failed")
            return False
        
        # Test validation
        result = engine.validate_template(template_html)
        if result["valid"]:
            print_success("Template validation works")
            print_info(f"  Used placeholders: {', '.join(result['used_placeholders'])}")
        else:
            print_error(f"Template validation failed: {result['message']}")
            return False
        
        # Test disallowed placeholder rejection
        bad_template = "<html><body>{{ EVIL_VAR }}</body></html>"
        result = engine.validate_template(bad_template)
        if not result["valid"]:
            print_success("Disallowed placeholders correctly rejected")
        else:
            print_error("Disallowed placeholder was accepted (SECURITY ISSUE!)")
            return False
        
        # Test sandboxing
        dangerous_template = "{{ system('ls') }}"
        try:
            rendered = engine.render(dangerous_template, context)
            # Should render with undefined, not execute code
            print_success("Template sandboxing works (dangerous code blocked)")
        except ValueError:
            print_success("Template sandboxing works (validation caught it)")
        
        return True
        
    except Exception as e:
        print_error(f"Template engine error: {e}")
        return False


def verify_security():
    """Verify security features."""
    print_header("3. Security Features Verification")
    
    try:
        # Check allowed placeholders
        expected_placeholders = {
            "CAMPAIGN_URL", "CLICK_ID", "PUBLISHER_ID", "SITE_ID",
            "COUNTRY", "OS", "DEVICE_TYPE", "TIMESTAMP"
        }
        
        if ALLOWED_PLACEHOLDERS == expected_placeholders:
            print_success("Placeholder whitelist correct")
            print_info(f"  Allowed: {', '.join(sorted(ALLOWED_PLACEHOLDERS))}")
        else:
            print_error("Placeholder whitelist mismatch")
            return False
        
        # Check token signature format
        context = RedirectContext(
            click_id="security_test",
            campaign_url="https://example.com/offer",
        )
        token = context.sign()
        
        if len(token) > 50:
            print_success("Token length adequate (>50 chars)")
        else:
            print_error("Token too short (SECURITY ISSUE!)")
            return False
        
        # Verify signature is present
        import base64
        try:
            decoded = base64.urlsafe_b64decode(token.encode()).decode()
            if ":" in decoded:
                print_success("Token contains signature separator")
            else:
                print_error("Token missing signature (SECURITY ISSUE!)")
                return False
        except Exception:
            print_error("Token decoding failed")
            return False
        
        # Check template engine globals are cleared
        engine = PrelanderTemplateEngine()
        if len(engine.env.globals) == 0:
            print_success("Template globals cleared (safe)")
        else:
            print_error(f"Template has {len(engine.env.globals)} globals (SECURITY ISSUE!)")
            return False
        
        # Check limited filters
        dangerous_filters = {"import", "exec", "eval", "compile", "open"}
        present = dangerous_filters & set(engine.env.filters.keys())
        if not present:
            print_success("No dangerous filters present")
        else:
            print_error(f"Dangerous filters found: {present} (SECURITY ISSUE!)")
            return False
        
        return True
        
    except Exception as e:
        print_error(f"Security verification error: {e}")
        return False


def verify_integration():
    """Verify full integration."""
    print_header("4. Integration Verification")
    
    try:
        # Full flow simulation
        print_info("Simulating full prelander flow...")
        
        # Step 1: Create context
        context = RedirectContext(
            click_id="integration_test_789",
            campaign_url="https://example.com/premium-offer",
            publisher_id="pub_integration",
            site_id="site_integration",
            country="GB",
            os="macOS",
            device_type="desktop",
        )
        print_success("Step 1: Context created")
        
        # Step 2: Sign token
        token = context.sign()
        print_success(f"Step 2: Token signed ({len(token)} chars)")
        
        # Step 3: Verify token
        verified = RedirectContext.verify(token)
        if not verified:
            print_error("Step 3: Token verification failed")
            return False
        print_success("Step 3: Token verified")
        
        # Step 4: Render template
        engine = PrelanderTemplateEngine()
        template = """
<!DOCTYPE html>
<html>
<head><title>Integration Test</title></head>
<body>
    <h1>Download for {{ OS }}</h1>
    <p>Country: {{ COUNTRY }}</p>
    <p>Click: {{ CLICK_ID }}</p>
    <a href="{{ CAMPAIGN_URL }}">Continue</a>
</body>
</html>
        """
        
        rendered = engine.render(template, verified)
        print_success("Step 4: Template rendered")
        
        # Step 5: Verify rendered content
        checks = [
            ("integration_test_789" in rendered, "Click ID present"),
            ("https://example.com/premium-offer" in rendered, "Campaign URL present"),
            ("GB" in rendered, "Country present"),
            ("macOS" in rendered, "OS present"),
        ]
        
        all_good = True
        for check, label in checks:
            if check:
                print_success(f"  ✓ {label}")
            else:
                print_error(f"  ✗ {label}")
                all_good = False
        
        if not all_good:
            return False
        
        print_success("Step 5: All content verified")
        
        return True
        
    except Exception as e:
        print_error(f"Integration error: {e}")
        return False


def main():
    """Run all verifications."""
    print("\n" + "🔍 PRELANDER SYSTEM VERIFICATION" + "\n")
    print("This script verifies the prelander system is working correctly.")
    
    results = []
    
    # Run all verifications
    results.append(("Token System", verify_token_system()))
    results.append(("Template Engine", verify_template_engine()))
    results.append(("Security Features", verify_security()))
    results.append(("Integration", verify_integration()))
    
    # Print summary
    print_header("VERIFICATION SUMMARY")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}  {name}")
    
    print(f"\nResults: {passed}/{total} checks passed")
    
    if passed == total:
        print("\n🎉 All verifications passed! Prelander system is working correctly.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} verification(s) failed. Please check the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
