import discord
from discord.ext import commands, tasks
import os
import json
import asyncio
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from collections import deque
import traceback

# Read configuration from config.txt
config = {}
try:
    with open('config.txt', 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                config[key.strip()] = value.strip()
except FileNotFoundError:
    print("ERROR: config.txt not found!")
    print("Please create config.txt with your bot settings.")
    exit(1)

# Get values from config
TOKEN = config.get('TOKEN')
GUILD_ID = int(config.get('GUILD_ID', '0'))
RULES_CHANNEL_ID = int(config.get('RULES_CHANNEL_ID', '0'))
FAMILY_ROLE_ID = int(config.get('FAMILY_ROLE_ID', '0'))
RULES_MESSAGE_ID = int(config.get('RULES_MESSAGE_ID', '0'))
NATIONAL_TEAM_ROLE_ID = int(config.get('NATIONAL_TEAM_ROLE_ID', '0'))
DEMONSTRATION_TEAM_ROLE_ID = int(config.get('DEMONSTRATION_TEAM_ROLE_ID', '0'))
NATIONAL_TEAM_CHANNEL_ID = int(config.get('NATIONAL_TEAM_CHANNEL_ID', '0'))
DEMONSTRATION_TEAM_CHANNEL_ID = int(config.get('DEMONSTRATION_TEAM_CHANNEL_ID', '0'))
GENERAL_CHAT_CHANNEL_ID = int(config.get('GENERAL_CHAT_CHANNEL_ID', '0'))
ADMIN_USER_ID = int(config.get('ADMIN_USER_ID', '0'))

print("=" * 50)
print("📋 CONFIGURATION LOADED:")
print(f"   Token: {'✅' if TOKEN and TOKEN != 'your_bot_token_here' else '❌'}")
print(f"   Guild ID: {GUILD_ID}")
print(f"   Rules Channel ID: {RULES_CHANNEL_ID}")
print(f"   Family Role ID: {FAMILY_ROLE_ID}")
print(f"   Rules Message ID: {RULES_MESSAGE_ID}")
print(f"   National Team Role ID: {NATIONAL_TEAM_ROLE_ID}")
print(f"   Demonstration Team Role ID: {DEMONSTRATION_TEAM_ROLE_ID}")
print(f"   National Team Channel ID: {NATIONAL_TEAM_CHANNEL_ID}")
print(f"   Demonstration Team Channel ID: {DEMONSTRATION_TEAM_CHANNEL_ID}")
print(f"   General Chat Channel ID: {GENERAL_CHAT_CHANNEL_ID}")
print(f"   Admin User ID: {ADMIN_USER_ID}")
print("=" * 50)

if not TOKEN or TOKEN == 'your_bot_token_here':
    print("❌ ERROR: Please set your bot token in config.txt")
    exit(1)

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Store user states for DM process
user_states: Dict[int, Dict] = {}
REGISTRY_FILE = 'registered_users.json'

# Enhanced conversation system
class ConversationManager:
    def __init__(self):
        self.active_conversations = {}
        self.history = {}
        self.message_queue = deque()
        self.admin_current_chat = None
        self.conversation_threads = {}
        self.admin_notifications_enabled = True
        
    def add_to_queue(self, user_id: int, user_name: str, message: str, channel: str, timestamp: datetime):
        queue_item = {
            'user_id': user_id,
            'user_name': user_name,
            'message': message,
            'channel': channel,
            'timestamp': timestamp,
            'status': 'pending'
        }
        self.message_queue.append(queue_item)
        
        self.active_conversations[user_id] = {
            'last_message': timestamp,
            'channel': channel,
            'username': user_name,
            'unread': True,
            'message_count': self.active_conversations.get(user_id, {}).get('message_count', 0) + 1
        }
        
        if user_id not in self.history:
            self.history[user_id] = []
        
        self.history[user_id].append({
            'from': 'user',
            'message': message,
            'channel': channel,
            'timestamp': timestamp,
            'read': False
        })
        
        if len(self.history[user_id]) > 50:
            self.history[user_id] = self.history[user_id][-50:]
        
        return queue_item
    
    def get_queue_summary(self):
        pending = len([m for m in self.message_queue if m['status'] == 'pending'])
        total = len(self.message_queue)
        recent_users = []
        
        seen_users = set()
        for item in list(self.message_queue)[-10:]:
            if item['user_id'] not in seen_users:
                seen_users.add(item['user_id'])
                recent_users.append(item['user_name'])
        
        return {
            'pending': pending,
            'total': total,
            'recent_users': recent_users[:5]
        }
    
    def mark_as_read(self, user_id: int):
        if user_id in self.active_conversations:
            self.active_conversations[user_id]['unread'] = False
        
        if user_id in self.history:
            for msg in self.history[user_id]:
                if msg['from'] == 'user':
                    msg['read'] = True
    
    def get_conversation_partners(self, limit=10):
        sorted_users = sorted(
            self.active_conversations.items(),
            key=lambda x: x[1]['last_message'],
            reverse=True
        )
        
        result = []
        for user_id, data in sorted_users[:limit]:
            unread_count = 0
            if user_id in self.history:
                unread_count = sum(1 for msg in self.history[user_id] 
                                 if msg['from'] == 'user' and not msg.get('read', False))
            
            result.append({
                'user_id': user_id,
                'username': data['username'],
                'channel': data['channel'],
                'last_message': data['last_message'],
                'unread': data.get('unread', False),
                'unread_count': unread_count,
                'message_count': data.get('message_count', 0)
            })
        
        return result
    
    def get_recent_messages(self, user_id: int, limit=10):
        if user_id not in self.history:
            return []
        
        return self.history[user_id][-limit:]
    
    def add_admin_message(self, user_id: int, message: str, timestamp: datetime):
        if user_id not in self.history:
            self.history[user_id] = []
        
        self.history[user_id].append({
            'from': 'admin',
            'message': message,
            'timestamp': timestamp,
            'read': True
        })
        
        self.mark_as_read(user_id)
        
        if len(self.history[user_id]) > 50:
            self.history[user_id] = self.history[user_id][-50:]
    
    def clear_old_conversations(self, hours=24):
        cutoff = datetime.now() - timedelta(hours=hours)
        removed_count = 0
        
        to_remove = []
        for user_id, data in self.active_conversations.items():
            if data['last_message'] < cutoff:
                to_remove.append(user_id)
        
        for user_id in to_remove:
            del self.active_conversations[user_id]
            removed_count += 1
        
        new_queue = deque()
        for item in self.message_queue:
            if item['timestamp'] >= cutoff:
                new_queue.append(item)
            else:
                removed_count += 1
        
        self.message_queue = new_queue
        
        return removed_count

# Initialize conversation manager
conv_manager = ConversationManager()

def load_registered_users():
    try:
        with open(REGISTRY_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_registered_users(users):
    with open(REGISTRY_FILE, 'w') as f:
        json.dump(users, f, indent=2)

registered_users = load_registered_users()

@bot.event
async def on_ready():
    print(f'✅ {bot.user} is online!')
    print(f'🆔 Bot ID: {bot.user.id}')
    print(f'👥 Connected to {len(bot.guilds)} server(s)')
    
    guild = bot.get_guild(GUILD_ID)
    if guild:
        print(f'🏠 Server: {guild.name} (ID: {guild.id})')
        
        rules_channel = guild.get_channel(RULES_CHANNEL_ID)
        if rules_channel:
            print(f'📜 Rules Channel: #{rules_channel.name} (ID: {rules_channel.id})')
        else:
            print(f'❌ Rules channel not found! ID: {RULES_CHANNEL_ID}')
        
        family_role = guild.get_role(FAMILY_ROLE_ID)
        if family_role:
            print(f'👪 Family Role: {family_role.name} (ID: {family_role.id})')
        else:
            print(f'❌ Family role not found! ID: {FAMILY_ROLE_ID}')
        
        national_role = guild.get_role(NATIONAL_TEAM_ROLE_ID)
        if national_role:
            print(f'🇺🇳 National Team Role: {national_role.name} (ID: {national_role.id})')
        else:
            print(f'⚠️ National Team role not found! ID: {NATIONAL_TEAM_ROLE_ID}')
            
        demonstration_role = guild.get_role(DEMONSTRATION_TEAM_ROLE_ID)
        if demonstration_role:
            print(f'🎯 Demonstration Team Role: {demonstration_role.name} (ID: {demonstration_role.id})')
        else:
            print(f'⚠️ Demonstration Team role not found! ID: {DEMONSTRATION_TEAM_ROLE_ID}')
        
        national_channel = guild.get_channel(NATIONAL_TEAM_CHANNEL_ID)
        if national_channel:
            print(f'📢 National Team Channel: #{national_channel.name} (ID: {national_channel.id})')
        else:
            print(f'⚠️ National Team channel not found! ID: {NATIONAL_TEAM_CHANNEL_ID}')
            
        demonstration_channel = guild.get_channel(DEMONSTRATION_TEAM_CHANNEL_ID)
        if demonstration_channel:
            print(f'📢 Demonstration Team Channel: #{demonstration_channel.name} (ID: {demonstration_channel.id})')
        else:
            print(f'⚠️ Demonstration Team channel not found! ID: {DEMONSTRATION_TEAM_CHANNEL_ID}')
        
        general_channel = guild.get_channel(GENERAL_CHAT_CHANNEL_ID)
        if general_channel:
            print(f'💬 General Chat Channel: #{general_channel.name} (ID: {general_channel.id})')
        else:
            print(f'⚠️ General Chat channel not found! ID: {GENERAL_CHAT_CHANNEL_ID}')
        
        if RULES_MESSAGE_ID:
            try:
                rules_channel = guild.get_channel(RULES_CHANNEL_ID)
                if rules_channel:
                    try:
                        rules_message = await rules_channel.fetch_message(RULES_MESSAGE_ID)
                        print(f'✅ Rules message found! (ID: {rules_message.id})')
                        reactions = [str(r.emoji) for r in rules_message.reactions]
                        if reactions:
                            print(f'   Reactions on message: {", ".join(reactions)}')
                        else:
                            print(f'   No reactions on message yet')
                    except discord.NotFound:
                        print(f'❌ Rules message not found! ID: {RULES_MESSAGE_ID}')
                    except discord.Forbidden:
                        print(f'❌ No permission to read rules message')
            except Exception as e:
                print(f'⚠️ Error checking rules message: {e}')
        else:
            print('⚠️ No rules message ID set')
    
    cleanup_old_conversations.start()
    
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching,
        name="for messages to forward"
    ))

@tasks.loop(hours=1)
async def cleanup_old_conversations():
    try:
        removed = conv_manager.clear_old_conversations(hours=24)
        if removed > 0:
            print(f"🧹 Cleaned up {removed} old conversation items")
    except Exception as e:
        print(f"❌ Error cleaning up old conversations: {e}")

async def assign_family_role(member: discord.Member):
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return False
    
    family_role = guild.get_role(FAMILY_ROLE_ID)
    if family_role and family_role not in member.roles:
        try:
            await member.add_roles(family_role, reason="Registration Complete")
            print(f'✅ Added Family Member role to {member.name} after registration')
            return True
        except discord.Forbidden:
            print(f'❌ Missing permissions to add role to {member.name}')
        except discord.HTTPException as e:
            print(f'❌ Error adding role to {member.name}: {e}')
    return False

async def assign_team_roles(member: discord.Member, teams_selected: list):
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return []
    
    assigned_teams = []
    
    if "national" in teams_selected:
        national_role = guild.get_role(NATIONAL_TEAM_ROLE_ID)
        if national_role and national_role not in member.roles:
            try:
                await member.add_roles(national_role, reason="National Team Registration")
                assigned_teams.append("National Team")
                print(f'✅ Added National Team role to {member.name}')
            except discord.Forbidden:
                print(f'❌ Missing permissions to add National Team role to {member.name}')
            except discord.HTTPException as e:
                print(f'❌ Error adding National Team role to {member.name}: {e}')
    
    if "demonstration" in teams_selected:
        demonstration_role = guild.get_role(DEMONSTRATION_TEAM_ROLE_ID)
        if demonstration_role and demonstration_role not in member.roles:
            try:
                await member.add_roles(demonstration_role, reason="Demonstration Team Registration")
                assigned_teams.append("Demonstration Team")
                print(f'✅ Added Demonstration Team role to {member.name}')
            except discord.Forbidden:
                print(f'❌ Missing permissions to add Demonstration Team role to {member.name}')
            except discord.HTTPException as e:
                print(f'❌ Error adding Demonstration Team role to {member.name}: {e}')
    
    return assigned_teams

async def forward_message_to_admin(message: discord.Message):
    if message.author.bot:
        return
    
    try:
        await message.delete()
        print(f"🗑️ Deleted message from {message.author.name} in #{message.channel.name}")
    except discord.Forbidden:
        print(f"❌ No permission to delete message in #{message.channel.name}")
    except discord.HTTPException as e:
        print(f"❌ Error deleting message: {e}")
    
    channel_name = message.channel.name
    channel_type = "Unknown"
    
    if message.channel.id == GENERAL_CHAT_CHANNEL_ID:
        channel_type = "General Chat"
    elif message.channel.id == NATIONAL_TEAM_CHANNEL_ID:
        channel_type = "National Team Chat"
    elif message.channel.id == DEMONSTRATION_TEAM_CHANNEL_ID:
        channel_type = "Demonstration Team Chat"
    else:
        channel_type = f"#{channel_name}"
    
    guild = bot.get_guild(GUILD_ID)
    member = guild.get_member(message.author.id) if guild else None
    roles = []
    
    if member:
        roles = [role.name for role in member.roles if role.name != "@everyone"]
    
    queue_item = conv_manager.add_to_queue(
        user_id=message.author.id,
        user_name=message.author.name,
        message=message.content,
        channel=channel_type,
        timestamp=message.created_at
    )
    
    admin = await bot.fetch_user(ADMIN_USER_ID)
    if not admin:
        print(f"❌ Admin user not found! ID: {ADMIN_USER_ID}")
        return
    
    embed = discord.Embed(
        title=f"📨 New Message from {message.author.name}",
        description=f"**From:** {message.author.mention} (`{message.author.id}`)\n"
                   f"**Channel:** {channel_type}\n"
                   f"**Roles:** {', '.join(roles) if roles else 'No roles'}\n"
                   f"**Queue Position:** #{len(conv_manager.message_queue)}\n\n"
                   f"**Message:**\n{message.content}",
        color=discord.Color.blue(),
        timestamp=message.created_at
    )
    
    if message.attachments:
        attachment_list = []
        for i, attachment in enumerate(message.attachments, 1):
            attachment_list.append(f"[Attachment {i}: {attachment.filename}]({attachment.url})")
        embed.add_field(name="📎 Attachments", value="\n".join(attachment_list), inline=False)
    
    queue_summary = conv_manager.get_queue_summary()
    if queue_summary['pending'] > 1:
        embed.add_field(
            name="📊 Message Queue",
            value=f"**Total Pending:** {queue_summary['pending']} messages\n"
                  f"**Recent Users:** {', '.join(queue_summary['recent_users'][:3])}",
            inline=False
        )
    
    embed.set_footer(text=f"Reply with: !chat {message.author.id} [message]")
    
    try:
        await admin.send(embed=embed)
        
        try:
            notify_embed = discord.Embed(
                title="✅ Message Sent",
                description=f"Your message has been sent to the admin from **{channel_type}**.\n"
                           "You'll receive a response via DM when available.",
                color=discord.Color.green()
            )
            await message.author.send(embed=notify_embed)
        except discord.Forbidden:
            print(f"⚠️ Cannot send confirmation DM to {message.author.name}")
        except Exception as e:
            print(f"⚠️ Error sending confirmation: {e}")
        
        print(f"📤 Forwarded message from {message.author.name} to admin (from {channel_type})")
        
    except discord.Forbidden:
        print(f"❌ Cannot send DM to admin (ID: {ADMIN_USER_ID})")
    except Exception as e:
        print(f"❌ Error forwarding message: {e}")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        await bot.process_commands(message)
        return
    
    if message.channel.id in [GENERAL_CHAT_CHANNEL_ID, NATIONAL_TEAM_CHANNEL_ID, DEMONSTRATION_TEAM_CHANNEL_ID]:
        await forward_message_to_admin(message)
        return
    
    if isinstance(message.channel, discord.DMChannel):
        user_id = message.author.id
        
        if user_id == ADMIN_USER_ID:
            if message.content and not message.content.startswith('!'):
                if conv_manager.admin_current_chat:
                    current_user_id = conv_manager.admin_current_chat
                    user = await bot.fetch_user(current_user_id)
                    
                    if user:
                        await send_message_to_user(user, message.content, message.author)
                        return
                    else:
                        await message.channel.send("❌ Current chat user not found. Use `!current` to see your active chat.")
                        return
                else:
                    await message.channel.send("ℹ️ No active chat. Use `!queue` to see pending messages or `!chat USER_ID` to start a conversation.")
                    return
            else:
                await bot.process_commands(message)
            return
        
        if str(user_id) not in registered_users:
            await message.channel.send("❌ You need to register first! Please react to the rules message in the server.")
            return
        
        admin = await bot.fetch_user(ADMIN_USER_ID)
        if admin:
            queue_item = conv_manager.add_to_queue(
                user_id=user_id,
                user_name=message.author.name,
                message=message.content,
                channel='Direct Message',
                timestamp=message.created_at
            )
            
            embed = discord.Embed(
                title=f"📨 Direct Message from {message.author.name}",
                description=f"**From:** {message.author.mention} (`{message.author.id}`)\n"
                           f"**Via:** Direct Message\n"
                           f"**Queue Position:** #{len(conv_manager.message_queue)}\n\n"
                           f"**Message:**\n{message.content}",
                color=discord.Color.purple(),
                timestamp=message.created_at
            )
            
            if message.attachments:
                attachment_list = []
                for i, attachment in enumerate(message.attachments, 1):
                    attachment_list.append(f"[Attachment {i}: {attachment.filename}]({attachment.url})")
                embed.add_field(name="📎 Attachments", value="\n".join(attachment_list), inline=False)
            
            queue_summary = conv_manager.get_queue_summary()
            if queue_summary['pending'] > 1:
                embed.add_field(
                    name="📊 Message Queue",
                    value=f"**Total Pending:** {queue_summary['pending']} messages\n"
                          f"**Recent Users:** {', '.join(queue_summary['recent_users'][:3])}",
                    inline=False
                )
            
            embed.set_footer(text=f"Reply with: !chat {user_id} [message]")
            
            try:
                await admin.send(embed=embed)
                await message.channel.send("✅ Your message has been sent to the admin!")
                print(f"📤 Forwarded DM from {message.author.name} to admin")
            except discord.Forbidden:
                await message.channel.send("❌ Cannot reach admin at the moment.")
                print(f"❌ Cannot send DM to admin")
            except Exception as e:
                await message.channel.send("❌ Error sending your message.")
                print(f"❌ Error forwarding DM: {e}")
        else:
            await message.channel.send("❌ Admin not found.")
    
    await bot.process_commands(message)

async def send_message_to_user(user: discord.User, message: str, admin: discord.User):
    try:
        embed = discord.Embed(
            title="📨 Message from Admin",
            description=message,
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        embed.set_footer(text="You can reply to this message directly in DM")
        
        await user.send(embed=embed)
        
        conv_manager.add_admin_message(user.id, message, datetime.now())
        conv_manager.admin_current_chat = user.id
        conv_manager.mark_as_read(user.id)
        
        confirmation = discord.Embed(
            title="✅ Message Sent",
            description=f"**To:** {user.mention} (`{user.id}`)\n\n"
                       f"**Your message:**\n{message}",
            color=discord.Color.blue()
        )
        
        await admin.send(embed=confirmation)
        print(f"📨 Admin sent message to {user.name}")
        
    except discord.Forbidden:
        await admin.send(f"❌ Cannot send DM to {user.mention}. They might have DMs disabled.")
    except Exception as e:
        await admin.send(f"❌ Error sending message: {e}")
        print(f"❌ Error sending message to user: {e}")

@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    print(f"\n🎯 REACTION DETECTED:")
    print(f"   Channel ID: {payload.channel_id}")
    print(f"   Message ID: {payload.message_id}")
    print(f"   Emoji: {payload.emoji}")
    print(f"   User ID: {payload.user_id}")
    
    if payload.user_id == bot.user.id:
        print("   👆 Bot's own reaction, ignoring")
        return
    
    if payload.channel_id == RULES_CHANNEL_ID:
        print(f"   📍 This is in the RULES CHANNEL!")
        print(f"   Looking for message ID: {RULES_MESSAGE_ID}")
        
        if payload.message_id == RULES_MESSAGE_ID:
            print(f"   ✅ CORRECT MESSAGE FOUND!")
            
            if str(payload.emoji) == '✅':
                print(f"   🎉 GREEN CHECK MARK DETECTED!")
                
                guild = bot.get_guild(payload.guild_id)
                if guild:
                    member = guild.get_member(payload.user_id)
                    if member and not member.bot:
                        print(f"   👤 User: {member.name}")
                        
                        if str(member.id) in registered_users:
                            print(f"   ⚠️ User already registered")
                            return
                        
                        print(f"   🚀 Starting DM process...")
                        await start_dm_process(member)
                    else:
                        print(f"   ❌ Could not find member")
            else:
                print(f"   ❌ Wrong emoji: {payload.emoji} (expected ✅)")
        else:
            print(f"   ❌ Wrong message ID: {payload.message_id} (expected {RULES_MESSAGE_ID})")
    else:
        print(f"   ❌ Not in rules channel (expected {RULES_CHANNEL_ID})")
    
    channel = bot.get_channel(payload.channel_id)
    if isinstance(channel, discord.DMChannel):
        print(f"   💬 This is a DM reaction")
        user = bot.get_user(payload.user_id)
        if user and not user.bot:
            await handle_dm_reaction(user, payload.emoji, payload.message_id)

async def start_dm_process(member: discord.Member):
    try:
        if str(member.id) in registered_users:
            return
        
        print(f"📨 Attempting to DM {member.name}...")
        
        dm_channel = await member.create_dm()
        
        embed = discord.Embed(
            title="👨‍👩‍👧‍👦 Family Registration",
            description="Welcome! Let's register you as a parent.\n\n"
                      "I'll guide you through 3 simple steps:",
            color=discord.Color.blue()
        )
        embed.add_field(name="Step 1", value="Your child's name", inline=True)
        embed.add_field(name="Step 2", value="Select mother or father", inline=True)
        embed.add_field(name="Step 3", value="Choose which teams to join", inline=True)
        
        await dm_channel.send(embed=embed)
        await asyncio.sleep(1)
        
        await dm_channel.send("**Step 1 of 3**: Please type your child's name below:")
        
        user_states[member.id] = {
            'waiting_for_name': True,
            'waiting_for_gender': False,
            'waiting_for_teams': False,
            'child_name': None,
            'gender': None,
            'teams_selected': [],
            'gender_message_id': None,
            'team_message_id': None
        }
        
        print(f"✅ DM sent to {member.name}")
        
    except discord.Forbidden:
        print(f"❌ Cannot send DM to {member.name} - they might have DMs disabled")
    except Exception as e:
        print(f"❌ Error sending DM to {member.name}: {e}")

async def handle_dm_reaction(user: discord.User, emoji: discord.PartialEmoji, message_id: int):
    user_id = user.id
    
    if (user_id in user_states and 
        user_states[user_id]['waiting_for_gender'] and
        user_states[user_id]['gender_message_id'] == message_id):
        
        guild = bot.get_guild(GUILD_ID)
        if not guild:
            return
        
        member = guild.get_member(user_id)
        if not member:
            return
        
        child_name = user_states[user_id]['child_name']
        
        if str(emoji) == '👩':
            new_nickname = f"{child_name}'s Mother"
            role_name = "Mother"
            emoji_role = "👩"
            user_states[user_id]['gender'] = 'mother'
        elif str(emoji) == '👨':
            new_nickname = f"{child_name}'s Father"
            role_name = "Father"
            emoji_role = "👨"
            user_states[user_id]['gender'] = 'father'
        else:
            return
        
        dm_channel = await user.create_dm()
        
        embed = discord.Embed(
            title=f"✅ Step 2 Complete!",
            description=f"{emoji_role} You selected: **{role_name}**\n\n"
                      f"**Step 3 of 3**: Team Selection\n\n"
                      f"Would you like to join any teams? React below:\n\n"
                      f"🇺🇳 - Join **National Team**\n"
                      f"🎯 - Join **Demonstration Team**\n"
                      f"✅ - Done (skip teams or finish selection)\n\n"
                      f"You can select multiple teams by reacting to both emojis, then react with ✅ when done.",
            color=discord.Color.blue()
        )
        
        team_message = await dm_channel.send(embed=embed)
        await team_message.add_reaction('🇺🇳')
        await team_message.add_reaction('🎯')
        await team_message.add_reaction('✅')
        
        user_states[user_id]['waiting_for_gender'] = False
        user_states[user_id]['waiting_for_teams'] = True
        user_states[user_id]['team_message_id'] = team_message.id
        
        print(f"✅ {user.name} selected gender: {role_name}")
    
    elif (user_id in user_states and 
          user_states[user_id]['waiting_for_teams'] and
          user_states[user_id]['team_message_id'] == message_id and
          str(emoji) == '✅'):
        
        guild = bot.get_guild(GUILD_ID)
        if not guild:
            return
        
        member = guild.get_member(user_id)
        if not member:
            return
        
        dm_channel = await user.create_dm()
        try:
            team_message = await dm_channel.fetch_message(message_id)
            
            for reaction in team_message.reactions:
                if str(reaction.emoji) == '🇺🇳':
                    async for reaction_user in reaction.users():
                        if reaction_user.id == user_id:
                            if "national" not in user_states[user_id]['teams_selected']:
                                user_states[user_id]['teams_selected'].append("national")
                            break
                
                elif str(reaction.emoji) == '🎯':
                    async for reaction_user in reaction.users():
                        if reaction_user.id == user_id:
                            if "demonstration" not in user_states[user_id]['teams_selected']:
                                user_states[user_id]['teams_selected'].append("demonstration")
                            break
        except Exception as e:
            print(f"Error fetching team message: {e}")
            return
        
        await complete_registration(user, member)

async def complete_registration(user: discord.User, member: discord.Member):
    user_id = user.id
    
    if user_id not in user_states:
        return
    
    child_name = user_states[user_id]['child_name']
    gender = user_states[user_id]['gender']
    teams_selected = user_states[user_id]['teams_selected']
    
    if gender == 'mother':
        new_nickname = f"{child_name}'s Mother"
        role_name = "Mother"
        emoji_role = "👩"
    else:
        new_nickname = f"{child_name}'s Father"
        role_name = "Father"
        emoji_role = "👨"
    
    dm_channel = await user.create_dm()
    
    nickname_success = False
    try:
        await member.edit(nick=new_nickname, reason="Family Registration")
        nickname_success = True
        print(f"✅ Changed {user.name}'s nickname to {new_nickname}")
        success_msg = f"✅ **Success!** Your nickname is now: **{new_nickname}**"
    except discord.Forbidden:
        success_msg = (
            f"⚠️ **Note:** I couldn't automatically set your nickname.\n\n"
            f"**Please manually change your server nickname to:**\n"
            f"```{new_nickname}```\n"
            f"1. Right-click server name → 'Change Nickname'\n"
            f"2. Enter: `{new_nickname}`\n"
            f"3. Click 'Save'"
        )
        print(f"⚠️ Cannot change nickname for {user.name}")
    except Exception as e:
        success_msg = f"⚠️ Error setting nickname: {e}"
        print(f"❌ Error changing nickname for {user.name}: {e}")
    
    family_role_assigned = await assign_family_role(member)
    assigned_teams = await assign_team_roles(member, teams_selected)
    
    team_message = ""
    if teams_selected:
        team_list = []
        if "national" in teams_selected:
            team_list.append("**National Team** 🇺🇳")
        if "demonstration" in teams_selected:
            team_list.append("**Demonstration Team** 🎯")
        
        team_message = f"\n\n**Teams Joined:**\n"
        team_message += "\n".join([f"• {team}" for team in team_list])
    else:
        team_message = "\n\n**Teams:** None selected - you can join teams later!"
    
    role_msg = ""
    if family_role_assigned:
        role_msg += "✅ You have been given the **Family Member** role!\n"
    else:
        role_msg += "⚠️ Could not assign Family Member role. Please contact an administrator.\n"
    
    if assigned_teams:
        role_msg += f"✅ Added to {len(assigned_teams)} team(s): {', '.join(assigned_teams)}"
    elif teams_selected:
        role_msg += "⚠️ Could not assign team roles. Please contact an administrator."
    
    embed = discord.Embed(
        title="🎉 Registration Complete!",
        description=f"{emoji_role} You are now registered as **{role_name}** of **{child_name}**!\n\n"
                  f"{success_msg}\n\n"
                  f"{role_msg}{team_message}\n\n"
                  f"Welcome to the family!",
        color=discord.Color.gold()
    )
    
    await dm_channel.send(embed=embed)
    
    registered_users[str(user_id)] = {
        'child_name': child_name,
        'role': role_name,
        'nickname': new_nickname,
        'gender': gender,
        'teams': teams_selected,
        'registered_at': discord.utils.utcnow().isoformat()
    }
    save_registered_users(registered_users)
    
    del user_states[user_id]
    
    print(f"✅ Registration complete for {user.name} with teams: {teams_selected}")

@bot.command(name="chat", aliases=["c"])
async def chat_command(ctx, user_reference: str = None, *, message: str = None):
    if ctx.author.id != ADMIN_USER_ID:
        await ctx.send("❌ This command is for admin only.", ephemeral=True)
        return
    
    if not user_reference:
        embed = discord.Embed(
            title="💬 Chat Commands",
            description="**Start a chat:**\n"
                       "`!chat USER_ID message` - Start chat with user\n"
                       "`!chat @mention message` - Start chat with mentioned user\n\n"
                       "**Manage conversations:**\n"
                       "`!queue` - View pending messages\n"
                       "`!current` - View current chat\n"
                       "`!chats` - List all conversations\n"
                       "`!next` - Move to next pending message\n"
                       "`!read USER_ID` - Mark conversation as read\n",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)
        return
    
    user = None
    
    if user_reference.startswith('<@') and user_reference.endswith('>'):
        user_id = int(user_reference.strip('<@!>'))
        user = await bot.fetch_user(user_id)
    elif user_reference.isdigit():
        user_id = int(user_reference)
        user = await bot.fetch_user(user_id)
    else:
        guild = bot.get_guild(GUILD_ID)
        if guild:
            member = guild.get_member_named(user_reference)
            if member:
                user = member
    
    if not user:
        await ctx.send(f"❌ User '{user_reference}' not found.")
        return
    
    if not message:
        conv_manager.admin_current_chat = user.id
        conv_manager.mark_as_read(user.id)
        
        recent_messages = conv_manager.get_recent_messages(user.id, limit=5)
        
        embed = discord.Embed(
            title=f"💬 Now chatting with {user.name}",
            description=f"**User:** {user.mention} (`{user.id}`)\n"
                       f"**Status:** Active chat\n\n"
                       f"Type your message to reply (no command needed!)",
            color=discord.Color.green()
        )
        
        if recent_messages:
            msg_list = []
            for msg in recent_messages:
                sender = "👤" if msg['from'] == 'user' else "👑"
                time_str = msg['timestamp'].strftime("%H:%M")
                content = msg['message'][:50] + "..." if len(msg['message']) > 50 else msg['message']
                msg_list.append(f"{sender} **{time_str}:** {content}")
            
            embed.add_field(name="📝 Recent Messages", value="\n".join(msg_list), inline=False)
        
        await ctx.send(embed=embed)
        return
    
    await send_message_to_user(user, message, ctx.author)

@bot.command(name="queue", aliases=["q"])
async def queue_command(ctx):
    if ctx.author.id != ADMIN_USER_ID:
        await ctx.send("❌ This command is for admin only.", ephemeral=True)
        return
    
    queue_summary = conv_manager.get_queue_summary()
    conversations = conv_manager.get_conversation_partners(limit=10)
    
    embed = discord.Embed(
        title="📊 Message Queue",
        description=f"**Pending Messages:** {queue_summary['pending']}\n"
                   f"**Active Conversations:** {len(conversations)}\n"
                   f"**Current Chat:** {'None' if not conv_manager.admin_current_chat else f'User ID: {conv_manager.admin_current_chat}'}",
        color=discord.Color.blue()
    )
    
    if conversations:
        convo_list = []
        for i, conv in enumerate(conversations[:5], 1):
            time_diff = datetime.now() - conv['last_message']
            minutes = int(time_diff.total_seconds() / 60)
            
            status = "🔴" if conv['unread'] else "🟢"
            unread = f" ({conv['unread_count']} new)" if conv['unread_count'] > 0 else ""
            
            convo_list.append(
                f"{status} **{conv['username']}** - {minutes}m ago{unread}\n"
                f"   `!chat {conv['user_id']}` - {conv['channel']}"
            )
        
        embed.add_field(name="💬 Recent Conversations", value="\n".join(convo_list), inline=False)
    
    if queue_summary['recent_users']:
        embed.add_field(
            name="👥 Recent Users",
            value=", ".join(queue_summary['recent_users']),
            inline=False
        )
    
    embed.set_footer(text="Use !chat USER_ID to start a conversation")
    
    await ctx.send(embed=embed)

@bot.command(name="current", aliases=["curr"])
async def current_command(ctx):
    if ctx.author.id != ADMIN_USER_ID:
        await ctx.send("❌ This command is for admin only.", ephemeral=True)
        return
    
    if not conv_manager.admin_current_chat:
        await ctx.send("ℹ️ No active chat. Use `!queue` to see pending messages.")
        return
    
    user_id = conv_manager.admin_current_chat
    user = await bot.fetch_user(user_id)
    
    if not user:
        await ctx.send("❌ Current chat user not found.")
        conv_manager.admin_current_chat = None
        return
    
    recent_messages = conv_manager.get_recent_messages(user_id, limit=10)
    unread_count = sum(1 for msg in recent_messages if msg['from'] == 'user' and not msg.get('read', False))
    
    embed = discord.Embed(
        title=f"💬 Current Chat: {user.name}",
        description=f"**User:** {user.mention} (`{user.id}`)\n"
                   f"**Unread Messages:** {unread_count}\n"
                   f"**Total Messages:** {len(recent_messages)}\n\n"
                   f"**How to reply:**\n"
                   f"Just type your message (no command needed!)",
        color=discord.Color.green()
    )
    
    if recent_messages:
        msg_list = []
        for msg in recent_messages[-5:]:
            sender = "👤 User" if msg['from'] == 'user' else "👑 You"
            time_str = msg['timestamp'].strftime("%H:%M")
            read_status = " 🔴" if msg['from'] == 'user' and not msg.get('read', False) else ""
            content = msg['message'][:80] + "..." if len(msg['message']) > 80 else msg['message']
            msg_list.append(f"**{sender}** ({time_str}){read_status}:\n{content}\n")
        
        embed.add_field(name="📝 Recent Messages", value="\n".join(msg_list), inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name="next", aliases=["n"])
async def next_command(ctx):
    if ctx.author.id != ADMIN_USER_ID:
        await ctx.send("❌ This command is for admin only.", ephemeral=True)
        return
    
    conversations = conv_manager.get_conversation_partners(limit=20)
    unread_conversations = [c for c in conversations if c['unread_count'] > 0]
    
    if not unread_conversations:
        await ctx.send("✅ No unread messages in queue.")
        return
    
    next_conv = unread_conversations[0]
    user = await bot.fetch_user(next_conv['user_id'])
    
    if not user:
        await ctx.send(f"❌ User {next_conv['user_id']} not found.")
        return
    
    conv_manager.admin_current_chat = next_conv['user_id']
    conv_manager.mark_as_read(next_conv['user_id'])
    
    recent_messages = conv_manager.get_recent_messages(next_conv['user_id'], limit=5)
    unread_messages = [m for m in recent_messages if m['from'] == 'user' and not m.get('read', False)]
    
    embed = discord.Embed(
        title=f"➡️ Switched to {user.name}",
        description=f"**User:** {user.mention} (`{user.id}`)\n"
                   f"**Unread Messages:** {next_conv['unread_count']}\n"
                   f"**From:** {next_conv['channel']}\n\n"
                   f"Type your message to reply (no command needed!)",
        color=discord.Color.blue()
    )
    
    if unread_messages:
        latest = unread_messages[-1]
        embed.add_field(
            name="📨 Latest Message",
            value=latest['message'],
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command(name="read", aliases=["r"])
async def read_command(ctx, user_id: int = None):
    if ctx.author.id != ADMIN_USER_ID:
        await ctx.send("❌ This command is for admin only.", ephemeral=True)
        return
    
    if not user_id:
        if conv_manager.admin_current_chat:
            user_id = conv_manager.admin_current_chat
        else:
            await ctx.send("ℹ️ Specify a user ID: `!read USER_ID`")
            return
    
    conv_manager.mark_as_read(user_id)
    
    user = await bot.fetch_user(user_id)
    if user:
        await ctx.send(f"✅ Marked conversation with {user.mention} as read.")
    else:
        await ctx.send(f"✅ Marked conversation with user ID `{user_id}` as read.")

@bot.command(name="chats", aliases=["conv", "conversations"])
async def chats_command(ctx):
    if ctx.author.id != ADMIN_USER_ID:
        await ctx.send("❌ This command is for admin only.", ephemeral=True)
        return
    
    conversations = conv_manager.get_conversation_partners(limit=15)
    
    if not conversations:
        await ctx.send("📭 No active conversations.")
        return
    
    embed = discord.Embed(
        title="💬 Active Conversations",
        description=f"**Total:** {len(conversations)}\n"
                   f"**Current Chat:** {'None' if not conv_manager.admin_current_chat else f'User ID: {conv_manager.admin_current_chat}'}",
        color=discord.Color.blue()
    )
    
    unread = [c for c in conversations if c['unread_count'] > 0]
    read = [c for c in conversations if c['unread_count'] == 0]
    
    if unread:
        unread_list = []
        for conv in unread[:5]:
            time_diff = datetime.now() - conv['last_message']
            minutes = int(time_diff.total_seconds() / 60)
            unread_list.append(f"🔴 **{conv['username']}** - {minutes}m ago ({conv['unread_count']} new)")
        
        embed.add_field(name="🔴 Unread Conversations", value="\n".join(unread_list), inline=False)
    
    if read:
        read_list = []
        for conv in read[:5]:
            time_diff = datetime.now() - conv['last_message']
            minutes = int(time_diff.total_seconds() / 60)
            read_list.append(f"🟢 **{conv['username']}** - {minutes}m ago")
        
        embed.add_field(name="🟢 Read Conversations", value="\n".join(read_list), inline=False)
    
    embed.set_footer(text="Use !chat USER_ID to start a conversation")
    
    await ctx.send(embed=embed)

@bot.command(name="clear_queue", aliases=["clear"])
async def clear_queue_command(ctx):
    if ctx.author.id != ADMIN_USER_ID:
        await ctx.send("❌ This command is for admin only.", ephemeral=True)
        return
    
    removed = conv_manager.clear_old_conversations(hours=1)
    await ctx.send(f"✅ Cleared {removed} old messages from queue.")

@bot.command(name="setup")
@commands.has_permissions(administrator=True)
async def setup_rules(ctx):
    if ctx.channel.id != RULES_CHANNEL_ID:
        await ctx.send(f"⚠️ Please run this command in the rules channel (<#{RULES_CHANNEL_ID}>)")
        return
    
    embed = discord.Embed(
        title="📜 Server Rules & Registration",
        description="**Welcome to our Family Server!** 👨‍👩‍👧‍👦\n\n"
                   "**Rules:**\n"
                   "1. Be respectful to all family members\n"
                   "2. No bullying or harassment\n"
                   "3. Keep conversations family-friendly\n"
                   "4. Respect everyone's privacy\n"
                   "5. Have fun and build our community!\n\n"
                   "**After reading the rules, react with ✅ below to begin registration.**\n"
                   "You will receive a private DM to complete the process.\n\n"
                   "**Note:** You will receive the Family Member role after completing registration.",
        color=discord.Color.purple()
    )
    
    rules_message = await ctx.send(embed=embed)
    await rules_message.add_reaction('✅')
    
    config['RULES_MESSAGE_ID'] = str(rules_message.id)
    with open('config.txt', 'w') as f:
        for key, value in config.items():
            f.write(f"{key}={value}\n")
    
    await ctx.send(f"✅ Rules message set up! New Message ID: {rules_message.id}")
    print(f"📝 New rules message ID saved: {rules_message.id}")

@bot.command(name="setup_teams")
@commands.has_permissions(administrator=True)
async def setup_teams(ctx):
    embed = discord.Embed(
        title="🏗️ Team Setup Instructions",
        description="To set up teams, please add the following to your config.txt file:\n\n"
                   f"```\n"
                   f"NATIONAL_TEAM_ROLE_ID=your_national_team_role_id_here\n"
                   f"DEMONSTRATION_TEAM_ROLE_ID=your_demo_team_role_id_here\n"
                   f"NATIONAL_TEAM_CHANNEL_ID=your_national_team_channel_id_here\n"
                   f"DEMONSTRATION_TEAM_CHANNEL_ID=your_demo_team_channel_id_here\n"
                   f"GENERAL_CHAT_CHANNEL_ID=your_general_chat_channel_id_here\n"
                   f"ADMIN_USER_ID=your_discord_user_id_here\n"
                   f"```\n\n"
                   f"**Current Configuration:**\n"
                   f"National Team Role ID: `{NATIONAL_TEAM_ROLE_ID}`\n"
                   f"Demonstration Team Role ID: `{DEMONSTRATION_TEAM_ROLE_ID}`\n"
                   f"National Team Channel ID: `{NATIONAL_TEAM_CHANNEL_ID}`\n"
                   f"Demonstration Team Channel ID: `{DEMONSTRATION_TEAM_CHANNEL_ID}`\n"
                   f"General Chat Channel ID: `{GENERAL_CHAT_CHANNEL_ID}`\n"
                   f"Admin User ID: `{ADMIN_USER_ID}`",
        color=discord.Color.blue()
    )
    
    await ctx.send(embed=embed)

@bot.command(name="chat_info")
async def chat_info(ctx):
    embed = discord.Embed(
        title="💬 How Chat Works",
        description="**All messages in chat channels are forwarded to the admin via DM.**\n\n"
                   "When you send a message in:\n"
                   f"• <#{GENERAL_CHAT_CHANNEL_ID}> - General Chat\n"
                   f"• <#{NATIONAL_TEAM_CHANNEL_ID}> - National Team Chat\n"
                   f"• <#{DEMONSTRATION_TEAM_CHANNEL_ID}> - Demonstration Team Chat\n\n"
                   "**What happens:**\n"
                   "1. Your message is deleted from the channel\n"
                   "2. It's sent to the admin via DM\n"
                   "3. Admin can reply to you directly\n"
                   "4. You'll receive responses in your DMs\n\n"
                   "**Note:** You can also DM the bot directly to talk to the admin.",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)

@bot.command(name="debug_ids")
async def debug_ids(ctx):
    embed = discord.Embed(title="🔧 Debug Info", color=discord.Color.blue())
    
    embed.add_field(name="Guild ID", value=f"`{GUILD_ID}`", inline=True)
    embed.add_field(name="Current Channel ID", value=f"`{ctx.channel.id}`", inline=True)
    embed.add_field(name="Rules Channel ID", value=f"`{RULES_CHANNEL_ID}`", inline=True)
    embed.add_field(name="Family Role ID", value=f"`{FAMILY_ROLE_ID}`", inline=True)
    embed.add_field(name="Rules Message ID", value=f"`{RULES_MESSAGE_ID}`", inline=True)
    embed.add_field(name="National Team Role ID", value=f"`{NATIONAL_TEAM_ROLE_ID}`", inline=True)
    embed.add_field(name="Demo Team Role ID", value=f"`{DEMONSTRATION_TEAM_ROLE_ID}`", inline=True)
    embed.add_field(name="National Team Channel ID", value=f"`{NATIONAL_TEAM_CHANNEL_ID}`", inline=True)
    embed.add_field(name="Demo Team Channel ID", value=f"`{DEMONSTRATION_TEAM_CHANNEL_ID}`", inline=True)
    embed.add_field(name="General Chat Channel ID", value=f"`{GENERAL_CHAT_CHANNEL_ID}`", inline=True)
    embed.add_field(name="Admin User ID", value=f"`{ADMIN_USER_ID}`", inline=True)
    embed.add_field(name="Bot User ID", value=f"`{bot.user.id}`", inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name="force_register")
async def force_register(ctx):
    if str(ctx.author.id) in registered_users:
        await ctx.send("✅ You are already registered!", ephemeral=True)
        return
    
    await start_dm_process(ctx.author)
    await ctx.send("📨 Check your DMs to complete registration!", ephemeral=True)

@bot.command(name="assign_role")
@commands.has_permissions(administrator=True)
async def assign_role(ctx, member: discord.Member):
    success = await assign_family_role(member)
    if success:
        await ctx.send(f"✅ Assigned Family Member role to {member.mention}")
    else:
        await ctx.send(f"❌ Failed to assign role to {member.mention}")

@bot.command(name="update_message_id")
@commands.has_permissions(administrator=True)
async def update_message_id(ctx, message_id: int):
    config['RULES_MESSAGE_ID'] = str(message_id)
    with open('config.txt', 'w') as f:
        for key, value in config.items():
            f.write(f"{key}={value}\n")
    
    await ctx.send(f"✅ Updated rules message ID to: {message_id}")
    print(f"📝 Manually updated rules message ID to: {message_id}")

@bot.command(name="register_stats")
async def register_stats(ctx):
    total_registered = len(registered_users)
    
    national_count = 0
    demonstration_count = 0
    both_teams_count = 0
    no_teams_count = 0
    
    for user_data in registered_users.values():
        teams = user_data.get('teams', [])
        if "national" in teams and "demonstration" in teams:
            both_teams_count += 1
        elif "national" in teams:
            national_count += 1
        elif "demonstration" in teams:
            demonstration_count += 1
        else:
            no_teams_count += 1
    
    embed = discord.Embed(
        title="📊 Registration Statistics",
        description=f"**Total Registered:** {total_registered}",
        color=discord.Color.green()
    )
    
    embed.add_field(name="🇺🇳 National Team", value=f"{national_count} members", inline=True)
    embed.add_field(name="🎯 Demonstration Team", value=f"{demonstration_count} members", inline=True)
    embed.add_field(name="🏆 Both Teams", value=f"{both_teams_count} members", inline=True)
    embed.add_field(name="👪 No Teams", value=f"{no_teams_count} members", inline=True)
    
    await ctx.send(embed=embed)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You need admin permissions for this command.", ephemeral=True)
    elif isinstance(error, commands.CommandNotFound):
        pass
    else:
        print(f"Command Error: {error}")
        print(traceback.format_exc())

if __name__ == "__main__":
    print("\n🚀 Starting Family Registration Bot...")
    print("📝 Make sure your config.txt has the correct values!")
    print("\nRequired config values:")
    print("   TOKEN=your_bot_token")
    print("   ADMIN_USER_ID=your_discord_user_id")
    print("\nChannel values:")
    print("   GENERAL_CHAT_CHANNEL_ID=channel_id_here")
    print("   NATIONAL_TEAM_CHANNEL_ID=channel_id_here")
    print("   DEMONSTRATION_TEAM_CHANNEL_ID=channel_id_here")
    print("\nOptional team values:")
    print("   NATIONAL_TEAM_ROLE_ID=role_id_here")
    print("   DEMONSTRATION_TEAM_ROLE_ID=role_id_here")
    print()
    
    if not TOKEN:
        print("❌ ERROR: Bot token not found in config.txt")
        print("   Please add: TOKEN=your_bot_token_here")
        exit(1)
    
    if not ADMIN_USER_ID:
        print("⚠️ WARNING: ADMIN_USER_ID not set in config.txt")
        print("   Add: ADMIN_USER_ID=your_discord_user_id")
    
    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        print("❌ ERROR: Invalid bot token!")
        print("   Please check your token in config.txt")
    except Exception as e:
        print(f"❌ ERROR starting bot: {e}")
        print(traceback.format_exc())
