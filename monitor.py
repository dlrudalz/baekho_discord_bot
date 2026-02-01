"""
Raspberry Pi System Health Monitor for Baekho Bot
=================================================
Monitors CPU temperature, memory usage, registry file size, and disk usage
in real-time and sends critical alerts to the Discord admin via Baekho bot DM.

Author: Baekho Bot System
Version: 1.0.0
For: Raspberry Pi 4 (4GB RAM) with Cana Kit 32GB MicroSD
"""

# =============================================================================
# IMPORTS AND DEPENDENCIES
# =============================================================================

import discord
from discord.ext import commands, tasks
import os
import json
import asyncio
import time
import psutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# =============================================================================
# CONFIGURATION
# =============================================================================

# Read bot configuration from config.txt file (same as main bot)
config = {}
try:
    with open('config.txt', 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                config[key.strip()] = value.strip()
except FileNotFoundError:
    print("❌ ERROR: Configuration file 'config.txt' not found!")
    print("   Please create config.txt with your bot settings.")
    exit(1)

# Extract configuration values
TOKEN = config.get('TOKEN')
ADMIN_USER_ID = int(config.get('ADMIN_USER_ID', '0'))
GUILD_ID = int(config.get('GUILD_ID', '0'))

# System monitoring thresholds
# CPU Temperature thresholds for Raspberry Pi 4
CPU_TEMP_WARNING = 70.0  # °C - Warning threshold
CPU_TEMP_CRITICAL = 80.0 # °C - Critical threshold (Pi 4 starts throttling at 80°C)

# Memory usage thresholds (4GB RAM)
MEMORY_WARNING = 85.0  # % - Warning threshold
MEMORY_CRITICAL = 95.0 # % - Critical threshold

# Registry file size thresholds (registered_users.json)
JSON_SIZE_WARNING = 5 * 1024 * 1024  # 5 MB - Warning threshold
JSON_SIZE_CRITICAL = 10 * 1024 * 1024  # 10 MB - Critical threshold

# Disk usage thresholds (32GB MicroSD)
DISK_WARNING = 85.0  # % - Warning threshold
DISK_CRITICAL = 95.0 # % - Critical threshold

# Monitoring intervals (in seconds)
MONITOR_INTERVAL = 30  # 5 minutes for regular checks
CRITICAL_MONITOR_INTERVAL = 60  # 1 minute when in critical state
ALERT_COOLDOWN = 900  # 15 minutes between repeated alerts for same issue

# =============================================================================
# BOT SETUP
# =============================================================================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# =============================================================================
# SYSTEM MONITORING FUNCTIONS
# =============================================================================

def get_cpu_temperature():
    """
    Get CPU temperature for Raspberry Pi.
    Returns temperature in Celsius.
    """
    try:
        # Method 1: Read from thermal zone (most reliable for Raspberry Pi)
        temp_path = "/sys/class/thermal/thermal_zone0/temp"
        if os.path.exists(temp_path):
            with open(temp_path, 'r') as f:
                temp = float(f.read().strip()) / 1000.0
            return temp
        
        # Method 2: Try vcgencmd command
        try:
            temp_output = subprocess.check_output(['vcgencmd', 'measure_temp']).decode()
            temp = float(temp_output.replace("temp=", "").replace("'C\n", ""))
            return temp
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
        
        # Method 3: Try alternative thermal zone
        for zone in range(5):
            temp_path = f"/sys/class/thermal/thermal_zone{zone}/temp"
            if os.path.exists(temp_path):
                with open(temp_path, 'r') as f:
                    temp = float(f.read().strip()) / 1000.0
                return temp
        
        print("⚠️ Could not read CPU temperature")
        return 0.0
        
    except Exception as e:
        print(f"❌ Error reading CPU temperature: {e}")
        return 0.0

def get_memory_usage():
    """
    Get memory usage statistics.
    Returns percentage used and details.
    """
    try:
        memory = psutil.virtual_memory()
        return {
            'percent': memory.percent,
            'used_gb': memory.used / (1024**3),
            'total_gb': memory.total / (1024**3),
            'available_gb': memory.available / (1024**3)
        }
    except Exception as e:
        print(f"❌ Error reading memory usage: {e}")
        return {'percent': 0, 'used_gb': 0, 'total_gb': 4.0, 'available_gb': 0}

def get_disk_usage():
    """
    Get disk usage statistics for root filesystem.
    Returns percentage used and details.
    """
    try:
        disk = psutil.disk_usage('/')
        return {
            'percent': disk.percent,
            'used_gb': disk.used / (1024**3),
            'total_gb': disk.total / (1024**3),
            'free_gb': disk.free / (1024**3)
        }
    except Exception as e:
        print(f"❌ Error reading disk usage: {e}")
        return {'percent': 0, 'used_gb': 0, 'total_gb': 32.0, 'free_gb': 0}

def get_json_file_size():
    """
    Get the size of registered_users.json file.
    Returns size in bytes.
    """
    try:
        json_file = 'registered_users.json'
        if os.path.exists(json_file):
            size = os.path.getsize(json_file)
            return size
        else:
            return 0
    except Exception as e:
        print(f"❌ Error reading JSON file size: {e}")
        return 0

def get_system_uptime():
    """
    Get system uptime in human-readable format.
    """
    try:
        with open('/proc/uptime', 'r') as f:
            uptime_seconds = float(f.readline().split()[0])
        
        # Convert to human readable format
        days = int(uptime_seconds // 86400)
        hours = int((uptime_seconds % 86400) // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        
        return f"{days}d {hours}h {minutes}m"
    except:
        return "Unknown"

def get_cpu_usage():
    """
    Get CPU usage percentage.
    """
    try:
        return psutil.cpu_percent(interval=1)
    except:
        return 0.0

def check_temperature_status(temp):
    """Check temperature status and return level and message."""
    if temp >= CPU_TEMP_CRITICAL:
        return "CRITICAL", f"🔥 CPU Temperature: {temp:.1f}°C (CRITICAL - Throttling may occur!)"
    elif temp >= CPU_TEMP_WARNING:
        return "WARNING", f"⚠️ CPU Temperature: {temp:.1f}°C (WARNING)"
    else:
        return "NORMAL", f"✅ CPU Temperature: {temp:.1f}°C"

def check_memory_status(mem_percent):
    """Check memory status and return level and message."""
    if mem_percent >= MEMORY_CRITICAL:
        return "CRITICAL", f"🚨 Memory Usage: {mem_percent:.1f}% (CRITICAL - Near maximum!)"
    elif mem_percent >= MEMORY_WARNING:
        return "WARNING", f"⚠️ Memory Usage: {mem_percent:.1f}% (WARNING)"
    else:
        return "NORMAL", f"✅ Memory Usage: {mem_percent:.1f}%"

def check_disk_status(disk_percent):
    """Check disk status and return level and message."""
    if disk_percent >= DISK_CRITICAL:
        return "CRITICAL", f"🚨 Disk Usage: {disk_percent:.1f}% (CRITICAL - Running out of space!)"
    elif disk_percent >= DISK_WARNING:
        return "WARNING", f"⚠️ Disk Usage: {disk_percent:.1f}% (WARNING)"
    else:
        return "NORMAL", f"✅ Disk Usage: {disk_percent:.1f}%"

def check_json_status(json_size):
    """Check JSON file status and return level and message."""
    json_size_mb = json_size / (1024 * 1024)
    if json_size >= JSON_SIZE_CRITICAL:
        return "CRITICAL", f"🚨 Registry File: {json_size_mb:.2f} MB (CRITICAL - Too large!)"
    elif json_size >= JSON_SIZE_WARNING:
        return "WARNING", f"⚠️ Registry File: {json_size_mb:.2f} MB (WARNING)"
    else:
        return "NORMAL", f"✅ Registry File: {json_size_mb:.2f} MB"

# =============================================================================
# ALERT MANAGEMENT
# =============================================================================

# Track last alert times to avoid spamming
last_alert_times = {
    'cpu_temp': 0,
    'memory': 0,
    'disk': 0,
    'json': 0
}

# Track current alert states
current_alerts = {
    'cpu_temp': False,
    'memory': False,
    'disk': False,
    'json': False
}

async def send_system_alert(alert_type, message, level, details=None):
    """
    Send system alert to admin via DM.
    
    Args:
        alert_type: Type of alert ('cpu_temp', 'memory', 'disk', 'json')
        message: Alert message
        level: Alert level ('CRITICAL', 'WARNING', 'NORMAL')
        details: Additional details dict
    """
    global last_alert_times, current_alerts
    
    current_time = time.time()
    
    # Check if we should send an alert (cooldown period)
    if current_time - last_alert_times[alert_type] < ALERT_COOLDOWN and current_alerts[alert_type]:
        # Already alerted recently and still in alert state
        return
    
    # Get admin user
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        print("❌ Guild not found for sending alert")
        return
    
    admin = guild.get_member(ADMIN_USER_ID)
    if not admin:
        print(f"❌ Admin user not found: {ADMIN_USER_ID}")
        return
    
    try:
        # Create alert embed
        color_map = {
            'CRITICAL': discord.Color.red(),
            'WARNING': discord.Color.gold(),
            'NORMAL': discord.Color.green()
        }
        
        embed = discord.Embed(
            title=f"🚨 **SYSTEM ALERT: {level}**",
            description=f"**{message}**\n\n**System**: Raspberry Pi 4 (4GB RAM)",
            color=color_map.get(level, discord.Color.red()),
            timestamp=datetime.now(timezone.utc)
        )
        
        # Add details if provided
        if details:
            for key, value in details.items():
                if isinstance(value, float):
                    value = f"{value:.2f}"
                embed.add_field(name=key, value=value, inline=True)
        
        # Add system info
        embed.add_field(name="🕐 Time", value=f"<t:{int(current_time)}:T>", inline=True)
        embed.add_field(name="📅 Date", value=f"<t:{int(current_time)}:D>", inline=True)
        
        # Send DM to admin
        dm_channel = await admin.create_dm()
        await dm_channel.send(embed=embed)
        
        print(f"📢 Sent {level} alert to admin: {message}")
        
        # Update alert tracking
        last_alert_times[alert_type] = current_time
        current_alerts[alert_type] = (level in ['CRITICAL', 'WARNING'])
        
    except Exception as e:
        print(f"❌ Error sending system alert: {e}")

async def send_system_status_update():
    """
    Send periodic system status update to admin.
    Only sends if there are active alerts.
    """
    # Check if any alerts are active
    has_active_alerts = any(current_alerts.values())
    if not has_active_alerts:
        return
    
    # Get system metrics
    cpu_temp = get_cpu_temperature()
    memory_info = get_memory_usage()
    disk_info = get_disk_usage()
    json_size = get_json_file_size()
    
    # Check statuses
    temp_status, temp_msg = check_temperature_status(cpu_temp)
    mem_status, mem_msg = check_memory_status(memory_info['percent'])
    disk_status, disk_msg = check_disk_status(disk_info['percent'])
    json_status, json_msg = check_json_status(json_size)
    
    # Count active alerts
    alert_count = sum([
        1 for status in [temp_status, mem_status, disk_status, json_status] 
        if status in ['CRITICAL', 'WARNING']
    ])
    
    if alert_count > 0:
        # Create status update embed
        embed = discord.Embed(
            title="📊 **System Status Update**",
            description=f"**Active Alerts**: {alert_count}\n"
                      f"**Last Check**: <t:{int(time.time())}:R>",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        
        # Add metrics
        embed.add_field(name="🌡️ CPU Temperature", value=f"{cpu_temp:.1f}°C", inline=True)
        embed.add_field(name="💾 Memory Usage", value=f"{memory_info['percent']:.1f}%", inline=True)
        embed.add_field(name="💿 Disk Usage", value=f"{disk_info['percent']:.1f}%", inline=True)
        
        embed.add_field(name="📁 Registry Size", value=f"{json_size/(1024*1024):.2f} MB", inline=True)
        embed.add_field(name="⏱️ Uptime", value=get_system_uptime(), inline=True)
        embed.add_field(name="⚡ CPU Usage", value=f"{get_cpu_usage():.1f}%", inline=True)
        
        # Add alert status
        status_fields = [
            ("CPU Temp", temp_status),
            ("Memory", mem_status),
            ("Disk", disk_status),
            ("Registry", json_status)
        ]
        
        status_text = ""
        for name, status in status_fields:
            emoji = "🔴" if status == "CRITICAL" else "🟡" if status == "WARNING" else "🟢"
            status_text += f"{emoji} {name}: {status}\n"
        
        embed.add_field(name="📋 Status Summary", value=status_text, inline=False)
        
        # Send to admin
        try:
            guild = bot.get_guild(GUILD_ID)
            if guild:
                admin = guild.get_member(ADMIN_USER_ID)
                if admin:
                    dm_channel = await admin.create_dm()
                    await dm_channel.send(embed=embed)
                    print(f"📊 Sent system status update to admin ({alert_count} active alerts)")
        except Exception as e:
            print(f"❌ Error sending status update: {e}")

# =============================================================================
# MONITORING TASK
# =============================================================================

@tasks.loop(seconds=MONITOR_INTERVAL)
async def monitor_system():
    """
    Main system monitoring task.
    Checks all metrics and sends alerts if needed.
    """
    try:
        print(f"🔍 Running system check at {datetime.now().strftime('%H:%M:%S')}")
        
        # Get all system metrics
        cpu_temp = get_cpu_temperature()
        memory_info = get_memory_usage()
        disk_info = get_disk_usage()
        json_size = get_json_file_size()
        
        # Check each metric and send alerts
        await check_and_alert_cpu(cpu_temp)
        await check_and_alert_memory(memory_info)
        await check_and_alert_disk(disk_info)
        await check_and_alert_json(json_size)
        
        # Send status update if monitoring interval is long
        if MONITOR_INTERVAL >= 300:  # 5 minutes or more
            await send_system_status_update()
        
        # Adjust monitoring interval based on alert state
        has_critical = any([
            check_temperature_status(cpu_temp)[0] == "CRITICAL",
            check_memory_status(memory_info['percent'])[0] == "CRITICAL",
            check_disk_status(disk_info['percent'])[0] == "CRITICAL",
            check_json_status(json_size)[0] == "CRITICAL"
        ])
        
        if has_critical and monitor_system.seconds != CRITICAL_MONITOR_INTERVAL:
            print("⚠️ Critical state detected, increasing monitoring frequency")
            monitor_system.change_interval(seconds=CRITICAL_MONITOR_INTERVAL)
        elif not has_critical and monitor_system.seconds != MONITOR_INTERVAL:
            print("✅ Returning to normal monitoring frequency")
            monitor_system.change_interval(seconds=MONITOR_INTERVAL)
            
    except Exception as e:
        print(f"❌ Error in monitor_system task: {e}")
        import traceback
        traceback.print_exc()

async def check_and_alert_cpu(cpu_temp):
    """Check CPU temperature and send alert if needed."""
    status, message = check_temperature_status(cpu_temp)
    
    if status in ['CRITICAL', 'WARNING']:
        details = {
            "Current Temp": f"{cpu_temp:.1f}°C",
            "Warning Threshold": f"{CPU_TEMP_WARNING}°C",
            "Critical Threshold": f"{CPU_TEMP_CRITICAL}°C",
            "Status": status
        }
        await send_system_alert('cpu_temp', message, status, details)
    elif status == 'NORMAL' and current_alerts['cpu_temp']:
        # Was in alert state, now back to normal
        await send_system_alert('cpu_temp', f"✅ CPU Temperature back to normal: {cpu_temp:.1f}°C", 'NORMAL')
        current_alerts['cpu_temp'] = False

async def check_and_alert_memory(memory_info):
    """Check memory usage and send alert if needed."""
    status, message = check_memory_status(memory_info['percent'])
    
    if status in ['CRITICAL', 'WARNING']:
        details = {
            "Used": f"{memory_info['used_gb']:.1f} GB",
            "Total": f"{memory_info['total_gb']:.1f} GB",
            "Available": f"{memory_info['available_gb']:.1f} GB",
            "Usage %": f"{memory_info['percent']:.1f}%",
            "Warning Threshold": f"{MEMORY_WARNING}%",
            "Critical Threshold": f"{MEMORY_CRITICAL}%",
            "Status": status
        }
        await send_system_alert('memory', message, status, details)
    elif status == 'NORMAL' and current_alerts['memory']:
        # Was in alert state, now back to normal
        await send_system_alert('memory', f"✅ Memory usage back to normal: {memory_info['percent']:.1f}%", 'NORMAL')
        current_alerts['memory'] = False

async def check_and_alert_disk(disk_info):
    """Check disk usage and send alert if needed."""
    status, message = check_disk_status(disk_info['percent'])
    
    if status in ['CRITICAL', 'WARNING']:
        details = {
            "Used": f"{disk_info['used_gb']:.1f} GB",
            "Total": f"{disk_info['total_gb']:.1f} GB",
            "Free": f"{disk_info['free_gb']:.1f} GB",
            "Usage %": f"{disk_info['percent']:.1f}%",
            "Warning Threshold": f"{DISK_WARNING}%",
            "Critical Threshold": f"{DISK_CRITICAL}%",
            "Status": status
        }
        await send_system_alert('disk', message, status, details)
    elif status == 'NORMAL' and current_alerts['disk']:
        # Was in alert state, now back to normal
        await send_system_alert('disk', f"✅ Disk usage back to normal: {disk_info['percent']:.1f}%", 'NORMAL')
        current_alerts['disk'] = False

async def check_and_alert_json(json_size):
    """Check JSON file size and send alert if needed."""
    status, message = check_json_status(json_size)
    
    if status in ['CRITICAL', 'WARNING']:
        details = {
            "File Size": f"{json_size/(1024*1024):.2f} MB",
            "Warning Threshold": f"{JSON_SIZE_WARNING/(1024*1024):.1f} MB",
            "Critical Threshold": f"{JSON_SIZE_CRITICAL/(1024*1024):.1f} MB",
            "Status": status
        }
        await send_system_alert('json', message, status, details)
    elif status == 'NORMAL' and current_alerts['json']:
        # Was in alert state, now back to normal
        await send_system_alert('json', f"✅ Registry file size back to normal: {json_size/(1024*1024):.2f} MB", 'NORMAL')
        current_alerts['json'] = False

# =============================================================================
# DISCORD BOT COMMANDS
# =============================================================================

@bot.command(name="system_status")
async def system_status(ctx):
    """Display current system status."""
    # Check if command is from admin or in bot command channel
    if ctx.author.id != ADMIN_USER_ID:
        await ctx.send("❌ This command is for admin only.", ephemeral=True)
        return
    
    # Get all system metrics
    cpu_temp = get_cpu_temperature()
    memory_info = get_memory_usage()
    disk_info = get_disk_usage()
    json_size = get_json_file_size()
    cpu_usage = get_cpu_usage()
    uptime = get_system_uptime()
    
    # Check statuses
    temp_status, temp_msg = check_temperature_status(cpu_temp)
    mem_status, mem_msg = check_memory_status(memory_info['percent'])
    disk_status, disk_msg = check_disk_status(disk_info['percent'])
    json_status, json_msg = check_json_status(json_size)
    
    # Create status embed
    embed = discord.Embed(
        title="🖥️ **Raspberry Pi 4 System Status**",
        description="Real-time system monitoring for Baekho Bot",
        color=discord.Color.blue(),
        timestamp=datetime.now(timezone.utc)
    )
    
    # Add system information
    embed.add_field(
        name="📊 **System Info**",
        value=f"**Model**: Raspberry Pi 4 (4GB RAM)\n"
              f"**Storage**: 32GB MicroSD Card\n"
              f"**Uptime**: {uptime}\n"
              f"**Last Check**: <t:{int(time.time())}:R>",
        inline=False
    )
    
    # Add metrics with status indicators
    status_emoji = {
        'CRITICAL': '🔴',
        'WARNING': '🟡', 
        'NORMAL': '🟢'
    }
    
    embed.add_field(
        name="🌡️ **CPU Temperature**",
        value=f"{status_emoji[temp_status]} {cpu_temp:.1f}°C\n"
              f"*Status: {temp_status}*\n"
              f"Thresholds: ⚠️{CPU_TEMP_WARNING}°C 🚨{CPU_TEMP_CRITICAL}°C",
        inline=True
    )
    
    embed.add_field(
        name="💾 **Memory (4GB RAM)**",
        value=f"{status_emoji[mem_status]} {memory_info['percent']:.1f}%\n"
              f"({memory_info['used_gb']:.1f}/{memory_info['total_gb']:.1f} GB)\n"
              f"*Status: {mem_status}*\n"
              f"Thresholds: ⚠️{MEMORY_WARNING}% 🚨{MEMORY_CRITICAL}%",
        inline=True
    )
    
    embed.add_field(
        name="💿 **Disk (32GB SD Card)**",
        value=f"{status_emoji[disk_status]} {disk_info['percent']:.1f}%\n"
              f"({disk_info['used_gb']:.1f}/{disk_info['total_gb']:.1f} GB)\n"
              f"*Status: {disk_status}*\n"
              f"Thresholds: ⚠️{DISK_WARNING}% 🚨{DISK_CRITICAL}%",
        inline=True
    )
    
    embed.add_field(
        name="📁 **Registry File**",
        value=f"{status_emoji[json_status]} {json_size/(1024*1024):.2f} MB\n"
              f"*Status: {json_status}*\n"
              f"Thresholds: ⚠️{JSON_SIZE_WARNING/(1024*1024):.1f}MB 🚨{JSON_SIZE_CRITICAL/(1024*1024):.1f}MB",
        inline=True
    )
    
    embed.add_field(
        name="⚡ **CPU Usage**",
        value=f"{cpu_usage:.1f}%",
        inline=True
    )
    
    # Add alert status
    alert_count = sum([
        1 for status in [temp_status, mem_status, disk_status, json_status] 
        if status in ['CRITICAL', 'WARNING']
    ])
    
    embed.add_field(
        name="🚨 **Alert Status**",
        value=f"**Active Alerts**: {alert_count}\n"
              f"**Monitoring Interval**: {MONITOR_INTERVAL}s\n"
              f"**Alert Cooldown**: {ALERT_COOLDOWN}s",
        inline=True
    )
    
    # Add footer with Pi-specific info
    embed.set_footer(text="Raspberry Pi 4 System Monitor | Baekho Bot")
    
    await ctx.send(embed=embed)

@bot.command(name="system_test")
async def system_test(ctx):
    """Test system monitoring by simulating alerts."""
    if ctx.author.id != ADMIN_USER_ID:
        await ctx.send("❌ This command is for admin only.", ephemeral=True)
        return
    
    # Get current metrics
    cpu_temp = get_cpu_temperature()
    memory_info = get_memory_usage()
    disk_info = get_disk_usage()
    json_size = get_json_file_size()
    
    # Send test alerts for each metric
    test_details = {
        "Test Type": "MANUAL TEST",
        "Real Value": "See above",
        "Note": "This is a test alert"
    }
    
    # Test CPU alert
    await send_system_alert('cpu_temp', f"🔧 TEST: CPU Temperature is {cpu_temp:.1f}°C", 'WARNING', test_details)
    
    # Test memory alert
    await send_system_alert('memory', f"🔧 TEST: Memory usage is {memory_info['percent']:.1f}%", 'WARNING', test_details)
    
    # Test disk alert
    await send_system_alert('disk', f"🔧 TEST: Disk usage is {disk_info['percent']:.1f}%", 'WARNING', test_details)
    
    # Test JSON alert
    await send_system_alert('json', f"🔧 TEST: Registry file is {json_size/(1024*1024):.2f} MB", 'WARNING', test_details)
    
    await ctx.send("✅ Test alerts sent to admin DM. Check your DMs!")

@bot.command(name="monitor_interval")
async def monitor_interval(ctx, seconds: int = None):
    """Change monitoring interval (admin only)."""
    if ctx.author.id != ADMIN_USER_ID:
        await ctx.send("❌ This command is for admin only.", ephemeral=True)
        return
    
    if seconds is None:
        current = monitor_system.seconds
        await ctx.send(f"⏱️ Current monitoring interval: {current} seconds")
        return
    
    if seconds < 30:
        await ctx.send("❌ Minimum interval is 30 seconds.")
        return
    
    if seconds > 3600:
        await ctx.send("❌ Maximum interval is 3600 seconds (1 hour).")
        return
    
    monitor_system.change_interval(seconds=seconds)
    await ctx.send(f"✅ Monitoring interval changed to {seconds} seconds")

@bot.command(name="monitor_stop")
async def monitor_stop(ctx):
    """Stop system monitoring (admin only)."""
    if ctx.author.id != ADMIN_USER_ID:
        await ctx.send("❌ This command is for admin only.", ephemeral=True)
        return
    
    if monitor_system.is_running():
        monitor_system.stop()
        await ctx.send("⏹️ System monitoring stopped")
    else:
        await ctx.send("ℹ️ System monitoring is already stopped")

@bot.command(name="monitor_start")
async def monitor_start(ctx):
    """Start system monitoring (admin only)."""
    if ctx.author.id != ADMIN_USER_ID:
        await ctx.send("❌ This command is for admin only.", ephemeral=True)
        return
    
    if not monitor_system.is_running():
        monitor_system.start()
        await ctx.send("▶️ System monitoring started")
    else:
        await ctx.send("ℹ️ System monitoring is already running")

# =============================================================================
# BOT EVENT HANDLERS
# =============================================================================

@bot.event
async def on_ready():
    """Bot startup initialization."""
    print(f'✅ {bot.user} is online!')
    print(f'🆔 Bot ID: {bot.user.id}')
    print(f'👥 Connected to {len(bot.guilds)} server(s)')
    
    # Check if we're on Raspberry Pi
    print("\n🖥️ Raspberry Pi System Monitor")
    print("=" * 50)
    
    # Test system metrics
    cpu_temp = get_cpu_temperature()
    memory_info = get_memory_usage()
    disk_info = get_disk_usage()
    json_size = get_json_file_size()
    
    print(f"🌡️  CPU Temperature: {cpu_temp:.1f}°C")
    print(f"💾 Memory Usage: {memory_info['percent']:.1f}% ({memory_info['used_gb']:.1f}/{memory_info['total_gb']:.1f} GB)")
    print(f"💿 Disk Usage: {disk_info['percent']:.1f}% ({disk_info['used_gb']:.1f}/{disk_info['total_gb']:.1f} GB)")
    print(f"📁 Registry File Size: {json_size/(1024*1024):.2f} MB")
    print(f"⏱️  System Uptime: {get_system_uptime()}")
    
    # Start monitoring task
    try:
        if not monitor_system.is_running():
            monitor_system.start()
            print(f"🔍 Started system monitoring (interval: {MONITOR_INTERVAL}s)")
    except Exception as e:
        print(f"❌ Error starting monitoring task: {e}")
    
    # Send startup notification to admin
    try:
        guild = bot.get_guild(GUILD_ID)
        if guild:
            admin = guild.get_member(ADMIN_USER_ID)
            if admin:
                dm_channel = await admin.create_dm()
                
                embed = discord.Embed(
                    title="🖥️ Raspberry Pi Monitor Online",
                    description="System monitoring is now active. I will send alerts for:\n"
                              "• High CPU temperature\n• High memory usage\n"
                              "• High disk usage\n• Large registry file size",
                    color=discord.Color.green(),
                    timestamp=datetime.now(timezone.utc)
                )
                
                embed.add_field(
                    name="📊 Initial System Status",
                    value=f"CPU: {cpu_temp:.1f}°C\n"
                          f"Memory: {memory_info['percent']:.1f}%\n"
                          f"Disk: {disk_info['percent']:.1f}%\n"
                          f"Registry: {json_size/(1024*1024):.2f} MB",
                    inline=True
                )
                
                embed.add_field(
                    name="⚙️ Monitoring Settings",
                    value=f"Interval: {MONITOR_INTERVAL}s\n"
                          f"Critical Interval: {CRITICAL_MONITOR_INTERVAL}s\n"
                          f"Alert Cooldown: {ALERT_COOLDOWN}s",
                    inline=True
                )
                
                embed.set_footer(text="Use !system_status for current status")
                
                await dm_channel.send(embed=embed)
                print("📢 Sent startup notification to admin")
    except Exception as e:
        print(f"❌ Error sending startup notification: {e}")
    
    # Set bot status
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching,
        name="system health"
    ))

@bot.event
async def on_command_error(ctx, error):
    """Handle command errors."""
    if isinstance(error, commands.CommandNotFound):
        return  # Ignore unknown commands
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing required argument: {error.param.name}", ephemeral=True)
    else:
        print(f"Command error: {error}")

# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    """
    Main entry point for the system monitor bot.
    """
    print("\n" + "="*50)
    print("🚀 Starting Raspberry Pi System Health Monitor")
    print("="*50)
    
    # Validate configuration
    if not TOKEN or TOKEN == 'your_bot_token_here':
        print("❌ ERROR: Bot token not configured. Please set TOKEN in config.txt")
        exit(1)
    
    if ADMIN_USER_ID == 0:
        print("⚠️ WARNING: ADMIN_USER_ID not set in config.txt")
        print("   Alerts will not be sent to admin!")
    
    # Check if running on Raspberry Pi
    print("\n🔍 Checking system compatibility...")
    
    # Check for Raspberry Pi temperature sensor
    temp_path = "/sys/class/thermal/thermal_zone0/temp"
    if os.path.exists(temp_path):
        print("✅ Raspberry Pi temperature sensor detected")
    else:
        print("⚠️ Raspberry Pi temperature sensor not found")
        print("   CPU temperature monitoring may not work properly")
    
    # Check for psutil
    try:
        import psutil
        print("✅ psutil module available")
    except ImportError:
        print("❌ ERROR: psutil module not installed!")
        print("   Install it with: pip install psutil")
        exit(1)
    
    # Check JSON file
    if os.path.exists('registered_users.json'):
        size = os.path.getsize('registered_users.json')
        print(f"✅ Registry file found: {size/(1024*1024):.2f} MB")
    else: 
        print("⚠️ Registry file not found (registered_users.json)")
    
    print("\n" + "="*50)
    print("⚙️  Monitoring Thresholds:")
    print(f"   CPU Temp: ⚠️{CPU_TEMP_WARNING}°C {CPU_TEMP_CRITICAL}°C")
    print(f"   Memory: ⚠️{MEMORY_WARNING}% {MEMORY_CRITICAL}%")
    print(f"   Disk: ⚠️{DISK_WARNING}% {DISK_CRITICAL}%")
    print(f"   Registry: ⚠️{JSON_SIZE_WARNING/(1024*1024):.1f}MB {JSON_SIZE_CRITICAL/(1024*1024):.1f}MB")
    print("="*50)
    
    # Start the bot
    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        print("❌ ERROR: Invalid bot token!")
        print("   Please check your token in config.txt")
    except Exception as e:
        print(f"❌ ERROR starting bot: {e}")