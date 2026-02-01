#!/bin/bash
# Startup script for Baekho Bot System
# Place this in the same directory as supervisor.py

echo "========================================"
echo "🤖 Baekho Bot System Startup"
echo "========================================"
echo "Starting at: $(date)"
echo

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "❌ ERROR: Python 3 is not installed!"
    exit 1
fi

# Check for required files
if [ ! -f "supervisor.py" ]; then
    echo "❌ ERROR: supervisor.py not found!"
    echo "Please ensure supervisor.py is in this directory."
    exit 1
fi

if [ ! -f "mainbot.py" ]; then
    echo "❌ ERROR: mainbot.py not found!"
    exit 1
fi

if [ ! -f "monitor.py" ]; then
    echo "❌ ERROR: monitor.py not found!"
    exit 1
fi

if [ ! -f "config.txt" ]; then
    echo "❌ ERROR: config.txt not found!"
    exit 1
fi

# Install required packages if needed
echo "🔍 Checking Python packages..."
REQUIRED_PACKAGES=("discord.py" "psutil")
for package in "${REQUIRED_PACKAGES[@]}"; do
    python3 -c "import ${package%%==*}" 2>/dev/null
    if [ $? -ne 0 ]; then
        echo "📦 Installing $package..."
        pip3 install $package
    fi
done

# Check if supervisor is already running
if pgrep -f "supervisor.py" > /dev/null; then
    echo "⚠️ Supervisor is already running!"
    echo "Please stop it first with: ./stop.sh"
    exit 1
fi

# Start the supervisor
echo "🚀 Starting supervisor..."
python3 supervisor.py

# If we get here, supervisor exited
echo
echo "========================================"
echo "🤖 Baekho Bot System Stopped"
echo "Stopped at: $(date)"
echo "========================================"