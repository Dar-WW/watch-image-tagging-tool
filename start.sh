#!/bin/bash
# Unified startup script for Watch Image Tagging Tool

set -e

echo "🚀 Starting Watch Image Tagging Tool..."
echo ""

# Check if docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Error: Docker is not running. Please start Docker Desktop."
    exit 1
fi

# Build prediction server (first time or after code changes)
echo "📦 Building prediction server..."
docker-compose build prediction-server

# Start all services
echo "▶️  Starting services..."
docker-compose up -d

# Wait for services to be ready
echo "⏳ Waiting for services to start..."
sleep 5

# Check health
echo ""
echo "🏥 Checking service health..."
if curl -s http://localhost:9090/health > /dev/null; then
    echo "✅ Prediction Server: Running (http://localhost:9090)"
else
    echo "⚠️  Prediction Server: Not responding yet (may need more time)"
fi

if curl -s http://localhost:8200 > /dev/null; then
    echo "✅ Label Studio: Running (http://localhost:8200)"
else
    echo "⚠️  Label Studio: Not responding yet (may need more time)"
fi

echo ""
echo "🎉 Setup complete!"
echo ""
echo "📍 Access points:"
echo "   Label Studio UI:    http://localhost:8200"
echo "   Prediction Server:  http://localhost:9090"
echo "   API Documentation:  http://localhost:9090/docs"
echo ""
echo "📝 Useful commands:"
echo "   View logs:       docker-compose logs -f"
echo "   Stop services:   docker-compose down"
echo "   Restart:         docker-compose restart"
echo ""
