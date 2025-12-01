#!/bin/bash
# Setup script for Watch Image Tagging Tool
# Creates a virtual environment and installs dependencies

set -e  # Exit on error

echo "🔧 Setting up Watch Image Tagging Tool..."
echo ""

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 is not installed!"
    echo ""
    echo "Please install Python 3.9 or higher first:"
    echo "  macOS:   brew install python@3.9"
    echo "  Windows: Download from https://www.python.org/downloads/"
    echo "  Linux:   sudo apt install python3.9 python3.9-venv python3-pip"
    echo ""
    echo "See README.md for detailed installation instructions."
    exit 1
fi

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
required_version="3.9"

# Simple version check (comparing major.minor)
current_version=$(echo $python_version | cut -d. -f1,2)
if [ "$(printf '%s\n' "$required_version" "$current_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "❌ Error: Python $python_version is installed, but version $required_version or higher is required."
    echo ""
    echo "Please upgrade Python. See README.md for instructions."
    exit 1
fi

echo "✓ Found Python $python_version"

# Create virtual environment
if [ -d "venv" ]; then
    echo "⚠️  Virtual environment already exists. Skipping creation."
else
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    echo "✓ Virtual environment created"
fi

# Activate virtual environment
echo "🔄 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

echo ""
echo "✅ Setup complete!"
echo ""
echo "To use the tagging tool:"
echo "  1. Activate the virtual environment:"
echo "     source venv/bin/activate"
echo ""
echo "  2. Run the app:"
echo "     ./run_app.sh"
echo ""
echo "  Or simply run: ./run_app.sh (it will auto-activate venv)"
echo ""
