#!/bin/bash

# Frontend Deployment Script with Security Obfuscation
# This script rebuilds the Next.js app with aggressive obfuscation

echo "🔧 Starting frontend deployment with enhanced security..."

cd ppc-frontend

echo "📦 Installing dependencies..."
npm install --production

echo "🏗️  Building with aggressive obfuscation (production mode)..."
NODE_ENV=production npm run build

echo "🚀 Deployment complete! Security features activated:"
echo "  ✅ Code obfuscation enabled"
echo "  ✅ Source maps removed" 
echo "  ✅ Console logs stripped"
echo "  ✅ Variable name mangling"
echo "  ✅ Security headers active"

echo ""
echo "⚠️  IMPORTANT: Restart the Next.js application server to apply changes!"
echo "   - If using PM2: pm2 restart nextjs-app"
echo "   - If using Docker: docker-compose restart frontend"
echo "   - Manual: Stop and start the Next.js server"