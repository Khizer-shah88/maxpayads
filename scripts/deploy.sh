#!/bin/bash

# Deployment script for MaxPayAds Backend
# Run this script on your server to deploy the latest code

set -e  # Exit on any error

echo "🚀 MaxPayAds Backend Deployment"
echo "================================"
echo ""

# Check if we're in the right directory
if [ ! -f "requirements.txt" ] && [ ! -f "../requirements.txt" ]; then
    echo "❌ Error: Not in the backend directory"
    echo "Please run this script from the ppc-backend directory"
    exit 1
fi

# Navigate to backend directory if we're in scripts
if [ -f "../requirements.txt" ]; then
    cd ..
fi

echo "📁 Current directory: $(pwd)"
echo ""

# Pull latest code
echo "📥 Pulling latest code from GitHub..."
git fetch origin
git pull origin main

if [ $? -ne 0 ]; then
    echo "❌ Git pull failed. Please check your repository."
    exit 1
fi

echo "✅ Code updated"
echo ""

# Check if virtual environment exists
if [ -d "venv" ]; then
    echo "🐍 Activating virtual environment..."
    source venv/bin/activate
    
    echo "📦 Installing/updating dependencies..."
    pip install -r requirements.txt --quiet
    echo "✅ Dependencies updated"
else
    echo "⚠️  No virtual environment found, skipping dependency install"
fi

echo ""

# Restart backend service
echo "🔄 Restarting backend service..."

# Try PM2 first
if command -v pm2 &> /dev/null; then
    echo "Using PM2..."
    pm2 restart ppc-backend
    if [ $? -eq 0 ]; then
        echo "✅ Backend restarted with PM2"
        pm2 logs ppc-backend --lines 20
        exit 0
    fi
fi

# Try systemd
if command -v systemctl &> /dev/null; then
    echo "Using systemd..."
    sudo systemctl restart ppc-backend
    if [ $? -eq 0 ]; then
        echo "✅ Backend restarted with systemd"
        sudo systemctl status ppc-backend --no-pager
        exit 0
    fi
fi

# Try docker-compose
if command -v docker-compose &> /dev/null; then
    echo "Using docker-compose..."
    docker-compose restart backend
    if [ $? -eq 0 ]; then
        echo "✅ Backend restarted with docker-compose"
        docker-compose logs backend --tail=20
        exit 0
    fi
fi

echo "⚠️  Could not automatically restart the backend"
echo "Please restart manually using one of these commands:"
echo "  - pm2 restart ppc-backend"
echo "  - sudo systemctl restart ppc-backend"
echo "  - docker-compose restart backend"
