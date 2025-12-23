#!/bin/bash
# Stop all Watch Image Tagging Tool services

echo "🛑 Stopping Watch Image Tagging Tool services..."
docker-compose down

echo "✅ All services stopped"
echo ""
echo "💡 To start again, run: ./start.sh"
