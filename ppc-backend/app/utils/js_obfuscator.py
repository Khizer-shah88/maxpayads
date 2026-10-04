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
        quote = match.group(1)
        content = match.group(2)
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
    Basic JavaScript minification:
    - Remove comments
    - Remove extra whitespace
    - Remove newlines
    """
    # Remove single-line comments (but not URLs)
    js_code = re.sub(r'(?<!:)//[^\n]*', '', js_code)
    
    # Remove multi-line comments
    js_code = re.sub(r'/\*.*?\*/', '', js_code, flags=re.DOTALL)
    
    # Remove leading/trailing whitespace from each line
    lines = [line.strip() for line in js_code.split('\n')]
    js_code = ' '.join(lines)
    
    # Collapse multiple spaces
    js_code = re.sub(r'\s+', ' ', js_code)
    
    # Remove spaces around operators and punctuation
    js_code = re.sub(r'\s*([=+\-*/<>!&|{}()\[\];,:])\s*', r'\1', js_code)
    
    # Remove spaces after keywords (if, for, while, etc.)
    js_code = re.sub(r'\b(if|for|while|function|return|var|let|const)\s+', r'\1 ', js_code)
    
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
        aggressive: If True, use heavy obfuscation. If False, just minify.
    
    Returns:
        Obfuscated/minified JavaScript code
    """
    try:
        if not js_code or not js_code.strip():
            return js_code
        
        # Step 1: Minify (always)
        minified = _minify_js(js_code)
        
        if not aggressive:
            return minified
        
        # Step 2: Obfuscate strings
        obfuscated = _obfuscate_strings(minified)
        
        # Step 3: Wrap in eval layer
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
        aggressive: If True, use heavy obfuscation. If False, just minify.
    
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
            obfuscated = obfuscate_javascript(script_content, aggressive=aggressive)
            
            return f'<script>{obfuscated}</script>'
        
        # Find and replace all inline script tags
        pattern = r'<script(?:\s+[^>]*)?>(.+?)</script>'
        html = re.sub(pattern, replace_script, html, flags=re.DOTALL | re.IGNORECASE)
        
        return html
    
    except Exception as e:
        logger.error(f"HTML JavaScript obfuscation failed: {e}")
        return html


def minify_html(html: str) -> str:
    """
    Basic HTML minification (optional enhancement).
    Removes unnecessary whitespace while preserving functionality.
    """
    try:
        # Remove comments (except IE conditional comments)
        html = re.sub(r'<!--(?!\[if).*?-->', '', html, flags=re.DOTALL)
        
        # Remove whitespace between tags
        html = re.sub(r'>\s+<', '><', html)
        
        # Collapse multiple spaces
        html = re.sub(r'\s{2,}', ' ', html)
        
        return html.strip()
    
    except Exception as e:
        logger.warning(f"HTML minification failed: {e}")
        return html
