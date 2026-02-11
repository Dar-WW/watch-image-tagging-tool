#!/bin/bash
# Memory-limited wrapper for batch_predict.py
# Usage: ./scripts/batch_predict_limited.sh [batch_predict.py args]

# Set memory limit to 8GB (8 * 1024 * 1024 KB)
# Adjust this value based on your system's available RAM
MEMORY_LIMIT_GB=16
MEMORY_LIMIT_KB=$((MEMORY_LIMIT_GB * 1024 * 1024))

echo "=================================================="
echo "Running batch_predict.py with memory limit: ${MEMORY_LIMIT_GB}GB"
echo "=================================================="

# Check if ulimit is available (Unix/Mac systems)
if command -v ulimit &> /dev/null; then
    echo "Setting memory limit using ulimit..."

    # Set virtual memory limit (data segment size)
    ulimit -v $MEMORY_LIMIT_KB 2>/dev/null

    # Set resident set size limit (physical memory)
    ulimit -m $MEMORY_LIMIT_KB 2>/dev/null

    # Display current limits
    echo "Current memory limits:"
    echo "  Virtual memory (ulimit -v): $(ulimit -v) KB"
    echo "  RSS memory (ulimit -m): $(ulimit -m) KB"
    echo ""
else
    echo "Warning: ulimit not available, running without memory limits"
    echo ""
fi

# Run batch_predict.py with all passed arguments
python3 scripts/batch_predict.py "$@"

exit_code=$?
echo ""
echo "=================================================="
echo "batch_predict.py exited with code: $exit_code"
echo "=================================================="

exit $exit_code
