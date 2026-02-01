#!/bin/bash
# Stop script for Baekho Bot System

echo "🤖 Stopping Baekho Bot System..."

# Find and kill supervisor
SUPERVISOR_PID=$(pgrep -f "supervisor.py")
if [ ! -z "$SUPERVISOR_PID" ]; then
    echo "🛑 Killing supervisor (PID: $SUPERVISOR_PID)..."
    kill $SUPERVISOR_PID
    sleep 2
    
    # Force kill if still running
    if ps -p $SUPERVISOR_PID > /dev/null; then
        echo "⚠️ Supervisor didn't stop gracefully, forcing..."
        kill -9 $SUPERVISOR_PID
    fi
fi

# Kill any remaining bot processes
pkill -f "mainbot.py"
pkill -f "monitor.py"

echo "✅ All bot processes have been stopped."