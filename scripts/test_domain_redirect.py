#!/usr/bin/env python3
"""
Test script to check if inter domain redirect is working
Run this to verify the backend is handling requests correctly
"""

import requests
import sys

def test_inter_domain(domain):
    """Test if an inter domain redirects properly"""
    
    print(f"\n🔍 Testing domain: {domain}")
    print("=" * 60)
    
    # Test HTTP
    try:
        url = f"http://{domain}/"
        print(f"\n1. Testing HTTP: {url}")
        response = requests.get(url, allow_redirects=False, timeout=5)
        print(f"   Status: {response.status_code}")
        print(f"   Headers: {dict(response.headers)}")
        
        if response.status_code in (301, 302, 303, 307, 308):
            print(f"   ✓ Redirects to: {response.headers.get('Location')}")
        elif response.status_code == 404:
            print(f"   ✗ Returns 404 - Backend not handling this domain")
        elif response.status_code == 200:
            print(f"   ✓ Returns 200 - Check response body")
            print(f"   Body preview: {response.text[:200]}")
        else:
            print(f"   ? Unexpected status: {response.status_code}")
            
    except requests.exceptions.RequestException as e:
        print(f"   ✗ Request failed: {e}")
    
    # Test HTTPS
    try:
        url = f"https://{domain}/"
        print(f"\n2. Testing HTTPS: {url}")
        response = requests.get(url, allow_redirects=False, timeout=5, verify=False)
        print(f"   Status: {response.status_code}")
        
        if response.status_code in (301, 302, 303, 307, 308):
            print(f"   ✓ Redirects to: {response.headers.get('Location')}")
        elif response.status_code == 404:
            print(f"   ✗ Returns 404 - Backend not handling this domain")
        elif response.status_code == 200:
            print(f"   ✓ Returns 200")
        else:
            print(f"   ? Unexpected status: {response.status_code}")
            
    except requests.exceptions.RequestException as e:
        print(f"   ✗ Request failed: {e}")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_domain_redirect.py <domain>")
        print("Example: python test_domain_redirect.py check3.clicklyspot.icu")
        sys.exit(1)
    
    domain = sys.argv[1]
    test_inter_domain(domain)
    
    print("\n📋 Troubleshooting:")
    print("   1. If you see 404: Backend is not running or Nginx is not passing requests")
    print("   2. If you see connection error: Domain DNS not pointing to server")
    print("   3. If you see redirect: ✓ Working correctly!")
    print("   4. If you see 200: Domain might not be configured as inter type in DB")
