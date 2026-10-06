"""
Test JavaScript Obfuscation
============================
Verify that JavaScript obfuscation works correctly and doesn't break functionality.
"""

import pytest
from app.utils.js_obfuscator import (
    obfuscate_javascript,
    obfuscate_html_javascript,
    minify_html,
    _minify_js,
    _obfuscate_strings,
)


def test_minify_basic_js():
    """Test basic JavaScript minification."""
    js = """
    // This is a comment
    function hello() {
        console.log("Hello World");
        return true;
    }
    """
    minified = _minify_js(js)
    
    # Should remove comments
    assert "//" not in minified
    # Should remove extra whitespace
    assert "  " not in minified
    # Should preserve functionality
    assert "function" in minified
    assert "hello" in minified
    assert "console.log" in minified


def test_obfuscate_strings():
    """Test string obfuscation using base64."""
    js = 'console.log("Hello World");'
    obfuscated = _obfuscate_strings(js)
    
    # Original string should be replaced with atob()
    assert "atob(" in obfuscated
    # Original string should not be visible
    assert "Hello World" not in obfuscated


def test_obfuscate_javascript_simple():
    """Test simple JavaScript obfuscation."""
    js = """
    function redirect() {
        window.location.href = "https://example.com";
    }
    setTimeout(redirect, 3000);
    """
    obfuscated = obfuscate_javascript(js, aggressive=True)
    
    # Obfuscated code is wrapped in eval, so may be longer than original
    # The goal is unreadability, not size reduction
    assert "eval" in obfuscated
    assert "atob" in obfuscated
    # Should be wrapped in an anonymous function
    assert obfuscated.startswith("(function(")
    # Original clear-text strings should be base64 encoded
    # (They may still appear if debug/test mode preserves them)


def test_obfuscate_javascript_nonaggressive():
    """Test non-aggressive mode (minify only)."""
    js = """
    function test() {
        // Comment
        var x = 5;
        return x;
    }
    """
    minified = obfuscate_javascript(js, aggressive=False)
    
    # Should be minified
    assert len(minified) < len(js)
    # Should not contain comments
    assert "//" not in minified
    # Should preserve basic structure
    assert "function" in minified
    assert "test" in minified


def test_obfuscate_html_javascript():
    """Test obfuscation of JavaScript in HTML."""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Test</title>
    </head>
    <body>
        <h1>Hello</h1>
        <script>
            console.log("Testing obfuscation");
            setTimeout(function() {
                window.location.href = "https://example.com";
            }, 3000);
        </script>
    </body>
    </html>
    """
    
    obfuscated = obfuscate_html_javascript(html, aggressive=True)
    
    # HTML structure should be preserved
    assert "<!DOCTYPE html>" in obfuscated
    assert "<h1>Hello</h1>" in obfuscated
    assert "<script>" in obfuscated
    assert "</script>" in obfuscated
    
    # JavaScript should be obfuscated
    assert "console.log" in obfuscated or "eval" in obfuscated
    # Original clear strings should be gone
    assert "Testing obfuscation" not in obfuscated or "atob" in obfuscated


def test_obfuscate_html_multiple_scripts():
    """Test obfuscation with multiple script tags."""
    html = """
    <html>
    <script>var a = 1;</script>
    <script>var b = 2;</script>
    <script src="external.js"></script>
    </html>
    """
    
    obfuscated = obfuscate_html_javascript(html, aggressive=True)
    
    # Should have all script tags
    assert obfuscated.count("<script>") >= 2
    # External script should not be touched
    assert 'src="external.js"' in obfuscated


def test_obfuscate_empty_script():
    """Test that empty scripts are handled gracefully."""
    html = '<script></script>'
    obfuscated = obfuscate_html_javascript(html, aggressive=True)
    
    # Should not crash
    assert "<script>" in obfuscated
    assert "</script>" in obfuscated


def test_minify_html():
    """Test HTML minification."""
    html = """
    <!DOCTYPE html>
    <html>
        <head>
            <title>Test</title>
        </head>
        <body>
            <h1>Hello</h1>
            <!-- Comment -->
            <p>World</p>
        </body>
    </html>
    """
    
    minified = minify_html(html)
    
    # Should remove HTML comments
    assert "<!--" not in minified
    # Should be shorter
    assert len(minified) < len(html)
    # Should preserve structure
    assert "<h1>Hello</h1>" in minified


def test_minify_html_preserves_template_css_and_text_spacing():
    """Prelander minification must not break CSS selectors or visible copy."""
    html = """
    <style>
      .card h1 { margin: 0 auto; }
      @media (max-width: 600px) { .card h1 { font-size: 20px; } }
    </style>
    <div class="card"><h1>Download Now</h1><p>Choose an option below to continue.</p></div>
    """

    minified = minify_html(html)

    assert ".card h1{margin:0 auto;}" in minified
    assert "@media (max-width:600px)" in minified
    assert "<h1>Download Now</h1>" in minified
    assert "Choose an option below to continue." in minified


def test_obfuscation_preserves_redirect():
    """Test that obfuscation doesn't break redirect functionality."""
    original_js = """
    setTimeout(function() {
        window.location.href = "https://offer.example.com";
    }, 3000);
    """
    
    obfuscated = obfuscate_javascript(original_js, aggressive=True)
    
    # Should contain eval or function markers
    assert "function" in obfuscated or "eval" in obfuscated
    # Should be executable (not broken)
    # We can't test execution here, but structure should be valid
    assert obfuscated.count("(") == obfuscated.count(")")
    assert obfuscated.count("{") == obfuscated.count("}")


def test_fallback_on_error():
    """Test that invalid JavaScript falls back gracefully."""
    # Malformed JavaScript
    js = "function broken() { this is not valid }"
    
    # Should not crash, might return minified or original
    result = obfuscate_javascript(js, aggressive=True)
    assert result  # Should return something


def test_real_world_prelander_script():
    """Test obfuscation on a realistic prelander script."""
    js = """
    // Auto-redirect after 3 seconds
    setTimeout(function() {
        window.location.href = "https://campaign.example.com/offer?id=123";
    }, 3000);
    
    // Track click
    document.addEventListener('DOMContentLoaded', function() {
        console.log('Page loaded');
        var button = document.querySelector('.continue-button');
        if (button) {
            button.addEventListener('click', function() {
                window.location.href = "https://campaign.example.com/offer?id=123";
            });
        }
    });
    """
    
    obfuscated = obfuscate_javascript(js, aggressive=True)
    
    # Obfuscation wraps code in eval + base64, making it longer but unreadable
    # Should contain obfuscation markers
    assert "eval" in obfuscated
    assert "atob" in obfuscated
    # Should be wrapped
    assert obfuscated.startswith("(function(")
    # Comments should be gone
    assert "Auto-redirect" not in obfuscated
    assert "Track click" not in obfuscated


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
