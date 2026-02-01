#!/usr/bin/env python3
"""
Supervisor for Baekho Bot System
=================================
Manages "main_bot.py and monitor.py to ensure both run together.
If either script crashes, both are terminated.

Author: Baekho Bot System
Version: 1.0.0
For: Raspberry Pi 4
"""

import subprocess
import sys
import os
import time
import signal
import threading
from datetime import datetime

class BotSupervisor:
    def __init__(self):
        self.mainbot_process = None
        self.monitor_process = None
        self.running = False
        self.mainbot_output = []
        self.monitor_output = []
        
    def start_bots(self):
        """Start both bots as subprocesses"""
        print("=" * 60)
        print("🤖 BAEKHO BOT SUPERVISOR")
        print("=" * 60)
        print(f"Starting at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        # Start mainbot.py
        print("🚀 Starting Main Bot...")
        self.mainbot_process = subprocess.Popen(
            [sys.executable, "main_bot.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        # Start monitor.py
        print("📊 Starting System Monitor...")
        self.monitor_process = subprocess.Popen(
            [sys.executable, "monitor.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        self.running = True
        
        # Start output readers
        self.mainbot_thread = threading.Thread(
            target=self.read_output,
            args=(self.mainbot_process, "MAINBOT", self.mainbot_output)
        )
        self.monitor_thread = threading.Thread(
            target=self.read_output,
            args=(self.monitor_process, "MONITOR", self.monitor_output)
        )
        
        self.mainbot_thread.daemon = True
        self.monitor_thread.daemon = True
        self.mainbot_thread.start()
        self.monitor_thread.start()
        
        # Start status monitor
        self.status_thread = threading.Thread(target=self.monitor_status)
        self.status_thread.daemon = True
        self.status_thread.start()
        
        print("\n✅ Both bots are now running!")
        print("📺 Output from both bots will appear below:")
        print("-" * 60)
        
        # Wait for both processes
        try:
            while self.running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n\n🛑 Supervisor interrupted by user")
            self.shutdown()
    
    def read_output(self, process, prefix, output_list):
        """Read and display output from a process"""
        try:
            for line in iter(process.stdout.readline, ''):
                if line:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    formatted_line = f"[{timestamp}] [{prefix}] {line.rstrip()}"
                    output_list.append(formatted_line)
                    print(formatted_line)
        except Exception as e:
            print(f"[ERROR] Error reading output from {prefix}: {e}")
    
    def monitor_status(self):
        """Monitor the status of both bots"""
        while self.running:
            time.sleep(1)
            
            # Check mainbot status
            if self.mainbot_process and self.mainbot_process.poll() is not None:
                print("\n⚠️ MAINBOT has stopped!")
                self.shutdown()
                break
                
            # Check monitor status
            if self.monitor_process and self.monitor_process.poll() is not None:
                print("\n⚠️ MONITOR has stopped!")
                self.shutdown()
                break
    
    def shutdown(self):
        """Shutdown both bots gracefully"""
        if not self.running:
            return
            
        print("\n" + "=" * 60)
        print("🛑 SHUTTING DOWN BOTS...")
        print("=" * 60)
        
        self.running = False
        
        # Terminate mainbot
        if self.mainbot_process and self.mainbot_process.poll() is None:
            print("Terminating Main Bot...")
            try:
                self.mainbot_process.terminate()
                self.mainbot_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print("Main Bot didn't terminate gracefully, forcing kill...")
                self.mainbot_process.kill()
            except Exception as e:
                print(f"Error terminating Main Bot: {e}")
        
        # Terminate monitor
        if self.monitor_process and self.monitor_process.poll() is None:
            print("Terminating System Monitor...")
            try:
                self.monitor_process.terminate()
                self.monitor_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print("System Monitor didn't terminate gracefully, forcing kill...")
                self.monitor_process.kill()
            except Exception as e:
                print(f"Error terminating System Monitor: {e}")
        
        print("\n✅ Both bots have been terminated.")
        print(f"Shutdown at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Exit supervisor
        sys.exit(0)
    
    def signal_handler(self, signum, frame):
        """Handle termination signals"""
        print(f"\n📶 Received signal {signum}, shutting down...")
        self.shutdown()

def main():
    # Check if required files exist
    required_files = ["main_bot.py", "monitor.py", "config.txt"]
    missing_files = []
    
    for file in required_files:
        if not os.path.exists(file):
            missing_files.append(file)
    
    if missing_files:
        print("❌ ERROR: Missing required files:")
        for file in missing_files:
            print(f"   - {file}")
        print("\nPlease ensure all files are in the same directory.")
        sys.exit(1)
    
    # Create and run supervisor
    supervisor = BotSupervisor()
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, supervisor.signal_handler)
    signal.signal(signal.SIGTERM, supervisor.signal_handler)
    
    try:
        supervisor.start_bots()
    except Exception as e:
        print(f"\n❌ SUPERVISOR ERROR: {e}")
        supervisor.shutdown()

if __name__ == "__main__":
    main()