#!/bin/bash
# Test prediction server with a sample request

echo "Testing prediction server..."
echo ""

# Health check
echo "1. Health check:"
curl -s http://localhost:9090/health | python3 -m json.tool
echo ""

# Version info
echo "2. Version info:"
curl -s http://localhost:9090/version | python3 -m json.tool
echo ""

# Sample prediction request
echo "3. Sample prediction request:"
curl -s -X POST http://localhost:9090/predict \
  -H "Content-Type: application/json" \
  -d '{
    "data": {
      "image": "/data/local-files/?d=PATEK_nab_001/PATEK_nab_001_01_face_q3.jpg"
    },
    "meta": {
      "task_id": 1
    }
  }' | python3 -m json.tool

echo ""
echo "Done!"
