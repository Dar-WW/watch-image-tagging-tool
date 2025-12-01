#!/bin/bash
# Launch script for Watch Image Tagging Tool

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Activate virtual environment if it exists
if [ -d "$SCRIPT_DIR/venv" ]; then
    echo "🔄 Activating virtual environment..."
    source "$SCRIPT_DIR/venv/bin/activate"
fi

# Change to tagging directory and run app
cd "$SCRIPT_DIR/tagging"
streamlit run app.py
