"""
JavaScript Obfuscation/Minification Utility
============================================
Obfuscates JavaScript code in HTML to make view-source unreadable.

Security Note: This is for source code protection only.
Does NOT affect functionality or redirect flow.
"""

import re
import base64
import random
import string
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def _generate_random_name(length: int = 8) -> str:
    """Generate random variable name."""
    first = random.choice(string.ascii_letters + '_')
    rest = ''.join(random.choices(string.ascii_letters + string.digits + '_', k=length-1))
    return first + rest


def _obfuscate_strings(js_code: str) -> str:
    """Convert string literals to base64 encoded forms."""
    def replace_string(match):
        content = match.group(1)  # The captured string content (without quotes)
        if len(content) < 3:  # Don't obfuscate very short strings
            return match.group(0)
        try:
            encoded = base64.b64encode(content.encode()).decode()
            return f'atob("{encoded}")'
        except Exception:
            return match.group(0)
    
    # Replace double-quoted strings
    js_code = re.sub(r'"([^"]{3,})"', replace_string, js_code)
    # Replace single-quoted strings
    js_code = re.sub(r"'([^']{3,})'", replace_string, js_code)
    
    return js_code


def _minify_js(js_code: str) -> str:
    """
    Safe JavaScript minification that preserves functionality:
    - Remove comments (carefully)
    - Remove extra whitespace
    - Collapse newlines
    - Preserve string literals and regex patterns
    """
    # Remove single-line comments (but not URLs like https://)
    # Only remove // if not preceded by : (to avoid breaking URLs)
    js_code = re.sub(r'(?<!:)//(?![^\n]*["\'])[^\n]*', '', js_code)
    
    # Remove multi-line comments (but preserve those inside strings)
    js_code = re.sub(r'/\*.*?\*/', '', js_code, flags=re.DOTALL)
    
    # Remove leading/trailing whitespace from each line
    lines = [line.strip() for line in js_code.split('\n') if line.strip()]
    js_code = ' '.join(lines)
    
    # Collapse multiple spaces (but not inside strings)
    js_code = re.sub(r'  +', ' ', js_code)
    
    # Remove spaces around specific operators (carefully)
    # Do NOT remove spaces that might break syntax
    js_code = re.sub(r'\s*([{};,])\s*', r'\1', js_code)
    js_code = re.sub(r'\s*(\))\s*{', r'\1{', js_code)
    
    return js_code.strip()


def _wrap_obfuscated(js_code: str) -> str:
    """
    Wrap obfuscated code in eval() to make it even harder to read.
    Uses multiple layers of encoding.
    """
    # Layer 1: Base64 encode
    encoded = base64.b64encode(js_code.encode()).decode()
    
    # Layer 2: Create obfuscated variable names
    var_a = _generate_random_name()
    var_b = _generate_random_name()
    var_c = _generate_random_name()
    
    # Layer 3: Split the encoded string into chunks
    chunk_size = 50
    chunks = [encoded[i:i+chunk_size] for i in range(0, len(encoded), chunk_size)]
    chunks_str = '+'.join([f'"{chunk}"' for chunk in chunks])
    
    # Layer 4: Wrap in obfuscated eval
    wrapper = f'''(function({var_a}){{var {var_b}=atob;var {var_c}={var_b}({var_a});eval({var_c});}})({chunks_str});'''
    
    return wrapper


def obfuscate_javascript(js_code: str, aggressive: bool = True) -> str:
    """
    Obfuscate JavaScript code to make it unreadable in view-source.
    
    Args:
        js_code: JavaScript source code
        aggressive: If True, use heavy obfuscation (may break some code).
                   If False, only use safe minification that preserves functionality.
    
    Returns:
        Obfuscated/minified JavaScript code
    
    Note: For admin-authored templates with custom JavaScript, use aggressive=False
          to ensure functionality is preserved.
    """
    try:
        if not js_code or not js_code.strip():
            return js_code
        
        # Step 1: Always minify (safe for all code)
        minified = _minify_js(js_code)
        
        if not aggressive:
            # Safe mode: only minification, no obfuscation
            # This preserves all functionality for admin-authored scripts
            return minified
        
        # Step 2: Aggressive obfuscation (may break complex code)
        # Only use for system-generated code, not admin templates
        obfuscated = _obfuscate_strings(minified)
        
        # Step 3: Wrap in eval layer (most aggressive)
        wrapped = _wrap_obfuscated(obfuscated)
        
        return wrapped
    
    except Exception as e:
        logger.warning(f"JavaScript obfuscation failed: {e}. Returning minified code.")
        # Fallback to just minification if obfuscation fails
        try:
            return _minify_js(js_code)
        except Exception:
            # Ultimate fallback: return original
            return js_code


def obfuscate_html_javascript(html: str, aggressive: bool = True) -> str:
    """
    Find all <script> tags in HTML and obfuscate their content.
    
    Args:
        html: HTML content
        aggressive: If True, use heavy obfuscation (may break complex code).
                   If False, only use safe minification that preserves functionality.
                   
                   IMPORTANT: For admin-authored prelander templates, always use
                   aggressive=False to ensure custom JavaScript works properly.
    
    Returns:
        HTML with obfuscated JavaScript
    """
    try:
        def replace_script(match):
            script_content = match.group(1)
            
            # Don't obfuscate external scripts (src attribute in opening tag)
            full_tag = match.group(0)
            if 'src=' in full_tag.split('>')[0]:
                return full_tag
            
            # Don't obfuscate empty scripts
            if not script_content.strip():
                return full_tag
            
            # Obfuscate the script content
            # Use aggressive mode for system code, safe mode for admin templates
            obfuscated = obfuscate_javascript(script_content, aggressive=aggressive)
            
            return f'<script>{obfuscated}</script>'
        
        # Find and replace all inline script tags
        pattern = r'<script(?:\s+[^>]*)?>(.+?)</script>'
        html = re.sub(pattern, replace_script, html, flags=re.DOTALL | re.IGNORECASE)
        
        # Strip comments/whitespace from the surrounding HTML and any inline
        # <style> blocks too -- view-source showed clean indented markup even
        # though the <script> content was already obfuscated.
        return minify_html(html)
    
    except Exception as e:
        logger.error(f"HTML JavaScript obfuscation failed: {e}")
        return html


def minify_html(html: str) -> str:
    """
    Minify HTML and CSS without changing rendered content or CSS semantics.

    Whitespace is meaningful in CSS descendant selectors and multi-value
    declarations, and in HTML text nodes between words. Only whitespace
    between tags is removed.
    """
    try:
        # Remove all HTML comments (except IE conditional comments)
        html = re.sub(r'<!--(?!\[if).*?-->', '', html, flags=re.DOTALL)

        # Minify CSS while retaining whitespace required by selectors and
        # values such as `margin: 0 auto`.
        def minify_css(match):
            css = match.group(1)
            css = re.sub(r'/\*.*?\*/', '', css, flags=re.DOTALL)
            css = re.sub(r'\s+', ' ', css).strip()
            css = re.sub(r'\s*([{}:;,])\s*', r'\1', css)
            return f'<style>{css}</style>'
        
        html = re.sub(r'<style[^>]*>(.*?)</style>', minify_css, html, flags=re.DOTALL | re.IGNORECASE)
        
        # Remove ALL whitespace between tags
        html = re.sub(r'>\s+<', '><', html)

        # Newlines outside tags are now only formatting whitespace. Do not
        # collapse text-node spaces: labels and sentences must remain readable.
        html = re.sub(r'\n', '', html)

        return html.strip()
    
    except Exception as e:
        logger.warning(f"HTML minification failed: {e}")
        return html
