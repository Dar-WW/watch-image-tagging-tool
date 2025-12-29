#!/bin/bash
# Startup script for Watch Image Tagging Tool

set -e

echo "🚀 Starting Watch Image Tagging Tool..."
echo ""

# Check if docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Error: Docker is not running. Please start Docker Desktop."
    exit 1
fi

# Start Label Studio
echo "▶️  Starting Label Studio..."
docker-compose up -d

# Wait for service to be ready
echo "⏳ Waiting for Label Studio to start..."
sleep 5

# Check health
echo ""
echo "🏥 Checking service health..."
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
echo ""
echo "📝 Useful commands:"
echo "   View logs:       docker-compose logs -f"
echo "   Stop services:   ./stop.sh (or docker-compose down)"
echo "   Restart:         docker-compose restart"
echo ""
echo "💡 For batch prediction, use:"
echo "   python scripts/batch_predict.py"
echo ""
