#!/bin/bash

# Production Build Verification Script
# Verifies that the production build has proper source code protection

set -e

echo "🔍 Verifying Production Build Security..."
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ERRORS=0
WARNINGS=0

# Check if we're in the correct directory
if [ ! -f "docker-compose.yml" ]; then
    echo -e "${RED}❌ Error: Must run from project root${NC}"
    exit 1
fi

# 1. Check for source maps in Next.js build
echo "📦 Checking for source maps..."
FRONTEND_DIR="ppc-frontend/.next"

if [ -d "$FRONTEND_DIR" ]; then
    SOURCE_MAPS=$(find "$FRONTEND_DIR" -name "*.map" 2>/dev/null | wc -l)
    if [ "$SOURCE_MAPS" -gt 0 ]; then
        echo -e "${RED}❌ FAIL: Found $SOURCE_MAPS source map files${NC}"
        find "$FRONTEND_DIR" -name "*.map" | head -5
        ERRORS=$((ERRORS + 1))
    else
        echo -e "${GREEN}✅ PASS: No source maps found${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  WARNING: Frontend build directory not found (.next)${NC}"
    echo "   Run 'cd ppc-frontend && npm run build' first"
    WARNINGS=$((WARNINGS + 1))
fi

echo ""

# 2. Check Next.js config for productionBrowserSourceMaps
echo "⚙️  Checking Next.js configuration..."
CONFIG_FILE="ppc-frontend/next.config.js"

if [ -f "$CONFIG_FILE" ]; then
    if grep -q "productionBrowserSourceMaps.*false" "$CONFIG_FILE"; then
        echo -e "${GREEN}✅ PASS: productionBrowserSourceMaps explicitly disabled${NC}"
    else
        echo -e "${RED}❌ FAIL: productionBrowserSourceMaps not explicitly set to false${NC}"
        ERRORS=$((ERRORS + 1))
    fi
    
    if grep -q "devtool.*false" "$CONFIG_FILE"; then
        echo -e "${GREEN}✅ PASS: Webpack devtool disabled${NC}"
    else
        echo -e "${YELLOW}⚠️  WARNING: Webpack devtool not explicitly disabled${NC}"
        WARNINGS=$((WARNINGS + 1))
    fi
else
    echo -e "${RED}❌ FAIL: Next.js config not found${NC}"
    ERRORS=$((ERRORS + 1))
fi

echo ""

# 3. Check for obfuscation utility
echo "🔐 Checking obfuscation utilities..."
OBFUSCATOR_FILE="ppc-backend/app/utils/js_obfuscator.py"

if [ -f "$OBFUSCATOR_FILE" ]; then
    echo -e "${GREEN}✅ PASS: JS obfuscator found${NC}"
    
    # Check if obfuscator has key functions
    if grep -q "def obfuscate_html_javascript" "$OBFUSCATOR_FILE"; then
        echo -e "${GREEN}✅ PASS: obfuscate_html_javascript function exists${NC}"
    else
        echo -e "${RED}❌ FAIL: obfuscate_html_javascript function not found${NC}"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo -e "${RED}❌ FAIL: JS obfuscator not found${NC}"
    ERRORS=$((ERRORS + 1))
fi

echo ""

# 4. Check nginx compression configuration
echo "🗜️  Checking nginx compression..."
NGINX_FILE="nginx.conf"

if [ -f "$NGINX_FILE" ]; then
    if grep -q "gzip on" "$NGINX_FILE"; then
        echo -e "${GREEN}✅ PASS: Gzip compression enabled${NC}"
    else
        echo -e "${YELLOW}⚠️  WARNING: Gzip compression not enabled${NC}"
        WARNINGS=$((WARNINGS + 1))
    fi
    
    if grep -q "brotli" "$NGINX_FILE"; then
        echo -e "${GREEN}✅ INFO: Brotli compression configuration present${NC}"
    else
        echo -e "${YELLOW}⚠️  INFO: Brotli compression not configured (optional)${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  WARNING: nginx.conf not found${NC}"
    WARNINGS=$((WARNINGS + 1))
fi

echo ""

# 5. Check prelander router obfuscation
echo "🔒 Checking prelander obfuscation implementation..."
PRELANDER_PUBLIC_ROUTER="ppc-backend/app/routers/prelander_public_router.py"

if [ -f "$PRELANDER_PUBLIC_ROUTER" ]; then
    if grep -q "obfuscate_html_javascript" "$PRELANDER_PUBLIC_ROUTER"; then
        echo -e "${GREEN}✅ PASS: Prelander router uses obfuscation${NC}"
    else
        echo -e "${RED}❌ FAIL: Prelander router does not use obfuscation${NC}"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo -e "${RED}❌ FAIL: Prelander public router not found${NC}"
    ERRORS=$((ERRORS + 1))
fi

echo ""

# 6. Check for sensitive data in frontend build
echo "🕵️  Checking for sensitive data patterns..."

if [ -d "$FRONTEND_DIR" ]; then
    # Check for common sensitive patterns (API keys, secrets, etc.)
    SENSITIVE_PATTERNS=(
        "mongodb://"
        "postgresql://"
        "mysql://"
        "redis://"
        "SECRET_KEY"
        "API_KEY"
        "PRIVATE_KEY"
        "password.*="
        "token.*="
    )
    
    FOUND_SENSITIVE=0
    for pattern in "${SENSITIVE_PATTERNS[@]}"; do
        if grep -r -i "$pattern" "$FRONTEND_DIR" 2>/dev/null | grep -v ".map" > /dev/null; then
            echo -e "${RED}❌ FAIL: Found potentially sensitive pattern: $pattern${NC}"
            ERRORS=$((ERRORS + 1))
            FOUND_SENSITIVE=1
        fi
    done
    
    if [ $FOUND_SENSITIVE -eq 0 ]; then
        echo -e "${GREEN}✅ PASS: No obvious sensitive data patterns found${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  WARNING: Cannot check for sensitive data (build not found)${NC}"
    WARNINGS=$((WARNINGS + 1))
fi

echo ""

# 7. Summary
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 VERIFICATION SUMMARY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✅ All checks passed!${NC}"
    echo ""
    echo "The production build has proper source code protection:"
    echo "  • No source maps exposed"
    echo "  • Obfuscation enabled"
    echo "  • Compression configured"
    echo "  • No sensitive data in build"
    exit 0
elif [ $ERRORS -eq 0 ]; then
    echo -e "${YELLOW}⚠️  $WARNINGS warning(s) found${NC}"
    echo ""
    echo "Build is acceptable but could be improved."
    exit 0
else
    echo -e "${RED}❌ $ERRORS error(s) and $WARNINGS warning(s) found${NC}"
    echo ""
    echo "Please fix the errors before deploying to production."
    exit 1
fi
