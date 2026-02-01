"""
WATCHDOG SUPERVISOR - Ensures both bots go offline if one fails
===============================================================
Monitors both mainbot.py and monitor.py processes and ensures
they both go offline if either one fails.

Author: Baekho Bot System
Version: 1.0.0
"""

import subprocess
import time
import signal
import sys
import os
from datetime import datetime
import threading
import json

class BotSupervisor:
    def __init__(self):
        self.mainbot_process = None
        self.monitor_process = None
        self.running = False
        self.restart_attempts = {}
        self.max_restart_attempts = 3
        self.restart_delay = 5  # seconds
        
    def start_bot(self, script_name):
        """Start a bot process."""
        try:
            print(f"🚀 Starting {script_name}...")
            
            if script_name == "mainbot":
                cmd = [sys.executable, "main_bot.py"]
                self.mainbot_process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    universal_newlines=True
                )
                return self.mainbot_process
                
            elif script_name == "monitor":
                cmd = [sys.executable, "monitor.py"]
                self.monitor_process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    universal_newlines=True
                )
                return self.monitor_process
                
        except Exception as e:
            print(f"❌ Error starting {script_name}: {e}")
            return None
    
    def monitor_output(self, process, bot_name):
        """Monitor bot output in a separate thread."""
        def read_output():
            while process and process.poll() is None:
                try:
                    line = process.stdout.readline()
                    if line:
                        timestamp = datetime.now().strftime('%H:%M:%S')
                        print(f"[{timestamp}] [{bot_name}] {line.strip()}")
                except:
                    break
                    
            # Read remaining output
            try:
                stdout, stderr = process.communicate(timeout=1)
                if stdout:
                    timestamp = datetime.now().strftime('%H:%M:%S')
                    print(f"[{timestamp}] [{bot_name}] [EXIT] {stdout.strip()}")
                if stderr:
                    timestamp = datetime.now().strftime('%H:%M:%S')
                    print(f"[{timestamp}] [{bot_name}] [ERROR] {stderr.strip()}")
            except:
                pass
        
        thread = threading.Thread(target=read_output, daemon=True)
        thread.start()
    
    def check_process_status(self):
        """Check if both processes are running."""
        mainbot_alive = self.mainbot_process and self.mainbot_process.poll() is None
        monitor_alive = self.monitor_process and self.monitor_process.poll() is None
        
        status = {
            'mainbot': mainbot_alive,
            'monitor': monitor_alive,
            'timestamp': datetime.now().isoformat()
        }
        
        return status
    
    def shutdown_all(self, reason="Supervisor shutdown"):
        """Shutdown all bot processes."""
        print(f"\n🛑 Shutting down all bots: {reason}")
        
        if self.mainbot_process and self.mainbot_process.poll() is None:
            print("🛑 Stopping mainbot...")
            try:
                self.mainbot_process.terminate()
                self.mainbot_process.wait(timeout=5)
            except:
                try:
                    self.mainbot_process.kill()
                except:
                    pass
            print("✅ Mainbot stopped")
        
        if self.monitor_process and self.monitor_process.poll() is None:
            print("🛑 Stopping monitor...")
            try:
                self.monitor_process.terminate()
                self.monitor_process.wait(timeout=5)
            except:
                try:
                    self.monitor_process.kill()
                except:
                    pass
            print("✅ Monitor stopped")
        
        self.running = False
    
    def restart_bot(self, bot_name):
        """Restart a failed bot."""
        if bot_name not in self.restart_attempts:
            self.restart_attempts[bot_name] = 0
        
        if self.restart_attempts[bot_name] >= self.max_restart_attempts:
            print(f"❌ Max restart attempts ({self.max_restart_attempts}) reached for {bot_name}")
            self.shutdown_all(f"{bot_name} failed too many times")
            return False
        
        self.restart_attempts[bot_name] += 1
        print(f"🔄 Restarting {bot_name} (attempt {self.restart_attempts[bot_name]}/{self.max_restart_attempts})...")
        
        # Clean up old process
        if bot_name == "mainbot" and self.mainbot_process:
            try:
                self.mainbot_process.kill()
            except:
                pass
        elif bot_name == "monitor" and self.monitor_process:
            try:
                self.monitor_process.kill()
            except:
                pass
        
        # Start new process
        time.sleep(self.restart_delay)
        
        if bot_name == "mainbot":
            self.mainbot_process = self.start_bot("mainbot")
            if self.mainbot_process:
                self.monitor_output(self.mainbot_process, "MAINBOT")
        elif bot_name == "monitor":
            self.monitor_process = self.start_bot("monitor")
            if self.monitor_process:
                self.monitor_output(self.monitor_process, "MONITOR")
        
        return True
    
    def run(self):
        """Main supervisor loop."""
        print("=" * 60)
        print("🦮 BAEKHO BOT SUPERVISOR")
        print("=" * 60)
        print("Starting both bots with automatic failure handling...")
        print(f"Max restart attempts: {self.max_restart_attempts}")
        print("=" * 60)
        
        self.running = True
        self.restart_attempts = {'mainbot': 0, 'monitor': 0}
        
        # Start both bots
        print("\n🚀 Initial bot startup...")
        self.mainbot_process = self.start_bot("mainbot")
        self.monitor_process = self.start_bot("monitor")
        
        if self.mainbot_process:
            self.monitor_output(self.mainbot_process, "MAINBOT")
        if self.monitor_process:
            self.monitor_output(self.monitor_process, "MONITOR")
        
        print("\n✅ Both bots started. Monitoring...")
        print("Press Ctrl+C to shutdown all bots gracefully.")
        print("-" * 60)
        
        # Main monitoring loop
        last_status_check = time.time()
        status_check_interval = 10  # seconds
        
        try:
            while self.running:
                time.sleep(1)
                
                # Check status periodically
                current_time = time.time()
                if current_time - last_status_check >= status_check_interval:
                    status = self.check_process_status()
                    
                    if not status['mainbot'] and self.mainbot_process:
                        print(f"❌ Mainbot process failed! Exit code: {self.mainbot_process.poll()}")
                        self.shutdown_all("Mainbot process failed")
                        break
                    
                    if not status['monitor'] and self.monitor_process:
                        print(f"❌ Monitor process failed! Exit code: {self.monitor_process.poll()}")
                        self.shutdown_all("Monitor process failed")
                        break
                    
                    last_status_check = current_time
                
                # Quick check for immediate failures
                if self.mainbot_process and self.mainbot_process.poll() is not None:
                    print(f"❌ Mainbot exited unexpectedly! Exit code: {self.mainbot_process.poll()}")
                    self.shutdown_all("Mainbot exited unexpectedly")
                    break
                
                if self.monitor_process and self.monitor_process.poll() is not None:
                    print(f"❌ Monitor exited unexpectedly! Exit code: {self.monitor_process.poll()}")
                    self.shutdown_all("Monitor exited unexpectedly")
                    break
        
        except KeyboardInterrupt:
            print("\n🛑 Supervisor interrupted by user")
            self.shutdown_all("User interrupt")
        
        except Exception as e:
            print(f"❌ Supervisor error: {e}")
            self.shutdown_all(f"Supervisor error: {e}")
        
        finally:
            print("\n" + "=" * 60)
            print("👋 Supervisor shutdown complete")
            print("=" * 60)

def signal_handler(sig, frame):
    """Handle interrupt signals."""
    print("\n🛑 Received shutdown signal")
    sys.exit(0)

if __name__ == "__main__":
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create and run supervisor
    supervisor = BotSupervisor()
    supervisor.run()