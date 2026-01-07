import discord
from discord.ext import commands, tasks
import os
import json
import asyncio
from typing import Dict, Optional, List, Tuple
from datetime import datetime, timedelta
import time

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

# Get values from config - using your exact IDs
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

# New configuration for temporary channels
TEMPORARY_CHANNELS_CATEGORY_ID = int(config.get('TEMPORARY_CHANNELS_CATEGORY_ID', '0'))
INACTIVITY_TIMEOUT = int(config.get('INACTIVITY_TIMEOUT', '7200'))  # Default 2 hours in seconds
INACTIVITY_CHECK_INTERVAL = int(config.get('INACTIVITY_CHECK_INTERVAL', '300'))  # Check every 5 minutes

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
print(f"   Temp Channels Category ID: {TEMPORARY_CHANNELS_CATEGORY_ID}")
print(f"   Inactivity Timeout: {INACTIVITY_TIMEOUT} seconds ({INACTIVITY_TIMEOUT//3600} hours)")
print("=" * 50)

if not TOKEN or TOKEN == 'your_bot_token_here':
    print("❌ ERROR: Please set your bot token in config.txt")
    exit(1)

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.reactions = True

processing_lock = asyncio.Lock()

bot = commands.Bot(command_prefix="!", intents=intents)

# Store user states for DM process
user_states: Dict[int, Dict] = {}
REGISTRY_FILE = 'registered_users.json'

# Store active conversations for 1-on-1 chat forwarding
active_conversations: Dict[int, Dict] = {}  # user_id -> {admin_id, channel_id, channel_type}
# Store message references for admin replies
message_references: Dict[int, int] = {}  # admin_message_id -> user_id

# Store temporary channels data
temporary_channels: Dict[int, Dict] = {}  # channel_id -> {user_id, created_at, last_activity, delete_button_message_id, delete_button_sent}
user_temporary_channels: Dict[int, int] = {}  # user_id -> channel_id

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

# List of monitored channels (where messages get forwarded to admin)
MONITORED_CHANNELS = []
if GENERAL_CHAT_CHANNEL_ID:
    MONITORED_CHANNELS.append(GENERAL_CHAT_CHANNEL_ID)
if NATIONAL_TEAM_CHANNEL_ID:
    MONITORED_CHANNELS.append(NATIONAL_TEAM_CHANNEL_ID)
if DEMONSTRATION_TEAM_CHANNEL_ID:
    MONITORED_CHANNELS.append(DEMONSTRATION_TEAM_CHANNEL_ID)

# ========== NEW CLASSES FOR TEMPORARY CHANNELS WITH BUTTONS ==========

class DeleteChannelView(discord.ui.View):
    """View with button for deleting temporary channels - ONLY ADMIN CAN PRESS"""
    def __init__(self, channel_id: int, user_id: int):
        super().__init__(timeout=None)
        self.channel_id = channel_id
        self.user_id = user_id
    
    @discord.ui.button(label="🗑️ Delete Temporary Channel", style=discord.ButtonStyle.danger, custom_id="delete_temp_channel")
    async def delete_channel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle delete channel button press - ONLY ADMIN CAN PRESS"""
        # Only admin can delete the channel
        if interaction.user.id != ADMIN_USER_ID:
            await interaction.response.send_message(
                "❌ Only the admin can delete this temporary channel.",
                ephemeral=True
            )
            return
        
        channel = interaction.guild.get_channel(self.channel_id)
        if not channel:
            await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
            return
        
        # Get user info for logging
        user = interaction.guild.get_member(self.user_id)
        
        # Disable the button and update message
        button.disabled = True
        button.label = "✅ Channel Deleted"
        button.style = discord.ButtonStyle.success
        
        await interaction.response.edit_message(view=self)
        
        # Send confirmation and delete channel
        await asyncio.sleep(1)  # Give user time to see the button change
        
        try:
            await channel.delete(reason="Temporary channel deleted by admin")
            
            # Clean up data
            if self.channel_id in temporary_channels:
                if self.user_id in user_temporary_channels:
                    del user_temporary_channels[self.user_id]
                del temporary_channels[self.channel_id]
            
            print(f"🗑️ Temporary channel deleted by admin for user: {user.name if user else 'Unknown'}")
        except Exception as e:
            print(f"❌ Error deleting channel: {e}")
            await interaction.followup.send("❌ Error deleting channel.", ephemeral=True)

class ConfirmDeleteView(discord.ui.View):
    """Confirmation view for deleting channel"""
    def __init__(self, channel_id: int, user_id: int):
        super().__init__(timeout=60)  # 1 minute timeout
        self.channel_id = channel_id
        self.user_id = user_id
        self.confirmed = False
    
    @discord.ui.button(label="✅ Confirm Delete", style=discord.ButtonStyle.danger)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != ADMIN_USER_ID:
            await interaction.response.send_message("❌ Only admin can delete this channel.", ephemeral=True)
            return
        
        self.confirmed = True
        self.stop()
        
        channel = interaction.guild.get_channel(self.channel_id)
        if channel:
            try:
                await channel.delete(reason="Temporary channel deleted by admin")
                
                # Clean up data
                if self.channel_id in temporary_channels:
                    if self.user_id in user_temporary_channels:
                        del user_temporary_channels[self.user_id]
                    del temporary_channels[self.channel_id]
                
                await interaction.response.send_message("✅ Channel deleted successfully.", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"❌ Error deleting channel: {e}", ephemeral=True)
    
    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != ADMIN_USER_ID:
            await interaction.response.send_message("❌ Only admin can cancel this action.", ephemeral=True)
            return
        
        self.confirmed = False
        self.stop()
        
        # Reset the delete button sent flag so it can be sent again after inactivity
        if self.channel_id in temporary_channels:
            temporary_channels[self.channel_id]['delete_button_sent'] = False
        
        await interaction.response.send_message("✅ Deletion cancelled.", ephemeral=True)

# ========== TEMPORARY CHANNELS FUNCTIONS ==========

async def create_temporary_channel(guild: discord.Guild, user: discord.Member, original_channel_name: str) -> Optional[discord.TextChannel]:
    """Create a temporary private channel for a user"""
    try:
        # Check if user already has a temporary channel
        if user.id in user_temporary_channels:
            channel_id = user_temporary_channels[user.id]
            channel = guild.get_channel(channel_id)
            if channel:
                # Update last activity
                temporary_channels[channel_id]['last_activity'] = time.time()
                return channel
        
        # Get or create temporary channels category
        category = None
        if TEMPORARY_CHANNELS_CATEGORY_ID:
            category = guild.get_channel(TEMPORARY_CHANNELS_CATEGORY_ID)
        
        if not category:
            # Create a new category
            category = await guild.create_category(
                name="📁 Private Conversations",
                reason="Temporary channels category",
                position=0
            )
            # Update config
            config['TEMPORARY_CHANNELS_CATEGORY_ID'] = str(category.id)
            with open('config.txt', 'w') as f:
                for key, value in config.items():
                    f.write(f"{key}={value}\n")
        
        # Create channel with appropriate permissions
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.get_member(ADMIN_USER_ID): discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }
        
        # Create the channel
        channel_name = f"private-{user.display_name.lower().replace(' ', '-')[:20]}"
        channel = await category.create_text_channel(
            name=channel_name,
            overwrites=overwrites,
            reason=f"Temporary channel for {user.name}",
            topic=f"Private conversation with {user.name} | From: {original_channel_name}"
        )
        
        # Store channel data
        current_time = time.time()
        temporary_channels[channel.id] = {
            'user_id': user.id,
            'created_at': current_time,
            'last_activity': current_time,
            'delete_button_sent': False,
            'delete_button_message_id': None,
            'original_channel': original_channel_name,
            'user_name': user.name
        }
        user_temporary_channels[user.id] = channel.id
        
        # Send welcome message with instructions
        embed = discord.Embed(
            title="🔒 Private Conversation",
            description=f"Welcome {user.mention}!\n\n"
                       f"This is a private channel between you and the admin.\n"
                       f"Messages from **#{original_channel_name}** will appear here.\n\n"
                       f"**After {INACTIVITY_TIMEOUT//3600} hours of inactivity, a delete button will appear (admin only).**",
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Channel created at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        welcome_msg = await channel.send(embed=embed)
        
        # Send initial instructions to admin
        admin_user = guild.get_member(ADMIN_USER_ID)
        if admin_user:
            try:
                admin_dm = await admin_user.create_dm()
                admin_embed = discord.Embed(
                    title="🔔 New Temporary Channel Created",
                    description=f"A temporary channel has been created for conversation with **{user.name}**\n\n"
                               f"**Channel:** #{channel.name}\n"
                               f"**User:** {user.mention} (`{user.id}`)\n"
                               f"**From:** #{original_channel_name}\n\n"
                               f"You can delete this channel at any time using the `!close_channel` command in the channel.",
                    color=discord.Color.green()
                )
                await admin_dm.send(embed=admin_embed)
            except:
                pass
        
        print(f"🔒 Created temporary channel for {user.name}")
        return channel
        
    except Exception as e:
        print(f"❌ Error creating temporary channel: {e}")
        return None

async def send_delete_button_helper(channel: discord.TextChannel):
    """Send delete button in the channel (only admin can press)"""
    try:
        if channel.id not in temporary_channels:
            return
        
        data = temporary_channels[channel.id]
        
        # Calculate inactivity time
        current_time = time.time()
        inactive_time = current_time - data['last_activity']
        inactive_hours = inactive_time // 3600
        inactive_minutes = (inactive_time % 3600) // 60
        
        # Create embed
        embed = discord.Embed(
            title="⏰ Channel Inactive",
            description=f"This channel has been inactive for **{int(inactive_hours)}h {int(inactive_minutes)}m**.\n\n"
                       f"**Admin can delete this channel using the button below.**\n"
                       f"If conversation continues, the button will be removed.",
            color=discord.Color.orange()
        )
        embed.set_footer(text=f"User: {data['user_name']} | Created: {datetime.fromtimestamp(data['created_at']).strftime('%Y-%m-%d %H:%M')}")
        
        # Create view with delete button
        view = DeleteChannelView(channel.id, data['user_id'])
        
        # Send message with button
        button_msg = await channel.send(embed=embed, view=view)
        
        # Update channel data
        temporary_channels[channel.id]['delete_button_sent'] = True
        temporary_channels[channel.id]['delete_button_message_id'] = button_msg.id
        
        print(f"⏰ Sent delete button for inactive channel #{channel.name}")
        
        # Also notify admin via DM
        admin_user = channel.guild.get_member(ADMIN_USER_ID)
        if admin_user:
            try:
                admin_dm = await admin_user.create_dm()
                admin_embed = discord.Embed(
                    title="🔔 Channel Inactive - Delete Button Sent",
                    description=f"The temporary channel **#{channel.name}** has been inactive for {int(inactive_hours)} hours.\n\n"
                               f"A delete button has been sent in the channel.\n"
                               f"You can delete it by pressing the button in the channel.",
                    color=discord.Color.orange()
                )
                await admin_dm.send(embed=admin_embed)
            except:
                pass
        
        return button_msg
        
    except Exception as e:
        print(f"❌ Error sending delete button: {e}")
        return None

async def check_inactive_channels(guild: discord.Guild):
    """Check for inactive temporary channels and send delete buttons"""
    current_time = time.time()
    channels_to_check = list(temporary_channels.items())
    
    for channel_id, data in channels_to_check:
        channel = guild.get_channel(channel_id)
        if not channel:
            # Channel was deleted, clean up
            if channel_id in temporary_channels:
                user_id = temporary_channels[channel_id].get('user_id')
                if user_id in user_temporary_channels:
                    del user_temporary_channels[user_id]
                del temporary_channels[channel_id]
            continue
        
        # Check if channel is inactive
        inactive_time = current_time - data['last_activity']
        
        # Send delete button after inactivity timeout
        if inactive_time >= INACTIVITY_TIMEOUT and not data['delete_button_sent']:
            await send_delete_button_helper(channel)  # Changed from send_delete_button
        
        # If button was sent but there's been activity since, remove the button
        elif data['delete_button_sent'] and inactive_time < INACTIVITY_TIMEOUT:
            # Remove the delete button message
            button_msg_id = data.get('delete_button_message_id')
            if button_msg_id:
                try:
                    button_msg = await channel.fetch_message(button_msg_id)
                    await button_msg.delete()
                    print(f"✅ Removed delete button from #{channel.name} (activity resumed)")
                except:
                    pass
            
            # Reset button sent flag
            temporary_channels[channel_id]['delete_button_sent'] = False
            temporary_channels[channel_id]['delete_button_message_id'] = None

async def cleanup_user_data(user_id: int):
    """Clean up all data for a user when they leave"""
    user_id_str = str(user_id)
    
    # Remove from registered_users
    if user_id_str in registered_users:
        del registered_users[user_id_str]
        save_registered_users(registered_users)
        print(f"🗑️ Deleted registration data for user ID {user_id}")
    
    # Remove from user_states
    if user_id in user_states:
        del user_states[user_id]
        print(f"🗑️ Removed user state for user ID {user_id}")
    
    # Remove from active_conversations
    if user_id in active_conversations:
        # Clean up message references
        message_ids_to_remove = []
        for admin_msg_id, user_msg_id in message_references.items():
            if user_msg_id == user_id:
                message_ids_to_remove.append(admin_msg_id)
        
        for msg_id in message_ids_to_remove:
            del message_references[msg_id]
        
        del active_conversations[user_id]
        print(f"🗑️ Removed active conversations for user ID {user_id}")
    
    # Remove temporary channel if exists
    if user_id in user_temporary_channels:
        channel_id = user_temporary_channels[user_id]
        if channel_id in temporary_channels:
            del temporary_channels[channel_id]
        del user_temporary_channels[user_id]
        print(f"🗑️ Removed temporary channel reference for user ID {user_id}")

# ========== EVENT HANDLERS ==========

@bot.event
async def on_ready():
    print(f'✅ {bot.user} is online!')
    print(f'🆔 Bot ID: {bot.user.id}')
    print(f'👥 Connected to {len(bot.guilds)} server(s)')
    
    guild = bot.get_guild(GUILD_ID)
    if guild:
        print(f'🏠 Server: {guild.name} (ID: {guild.id})')
        
        # Check monitored channels
        print("\n📢 MONITORED CHANNELS (messages will create temporary channels):")
        for channel_id in MONITORED_CHANNELS:
            channel = guild.get_channel(channel_id)
            if channel:
                print(f'   ✅ #{channel.name} (ID: {channel.id})')
            else:
                print(f'   ❌ Channel not found! ID: {channel_id}')
        
        # Check admin user
        admin_user = guild.get_member(ADMIN_USER_ID)
        if admin_user:
            print(f'👑 Admin: {admin_user.name}#{admin_user.discriminator} (ID: {admin_user.id})')
        else:
            print(f'⚠️ Admin user not found! ID: {ADMIN_USER_ID}')
        
        # Check rules channel
        rules_channel = guild.get_channel(RULES_CHANNEL_ID)
        if rules_channel:
            print(f'\n📜 Rules Channel: #{rules_channel.name} (ID: {rules_channel.id})')
        else:
            print(f'❌ Rules channel not found! ID: {RULES_CHANNEL_ID}')
        
        # Check family role
        family_role = guild.get_role(FAMILY_ROLE_ID)
        if family_role:
            print(f'👪 Family Role: {family_role.name} (ID: {family_role.id})')
        else:
            print(f'❌ Family role not found! ID: {FAMILY_ROLE_ID}')
        
        # Check team roles
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
        
        # Check temporary channels category
        if TEMPORARY_CHANNELS_CATEGORY_ID:
            temp_category = guild.get_channel(TEMPORARY_CHANNELS_CATEGORY_ID)
            if temp_category:
                print(f'📁 Temporary Channels Category: #{temp_category.name} (ID: {temp_category.id})')
            else:
                print(f'⚠️ Temporary channels category not found! ID: {TEMPORARY_CHANNELS_CATEGORY_ID}')
        
        # Ensure all registered users have the green check mark
        print("\n🔍 Verifying green check marks for registered users...")
        try:
            if rules_channel:
                rules_message = await rules_channel.fetch_message(RULES_MESSAGE_ID)
                
                # Get users who reacted with green check
                green_check_users = set()
                for reaction in rules_message.reactions:
                    if str(reaction.emoji) == '✅':
                        async for user in reaction.users():
                            if not user.bot:
                                green_check_users.add(user.id)
                
                # Check registered users without green check
                for user_id_str in registered_users.keys():
                    user_id = int(user_id_str)
                    member = guild.get_member(user_id)
                    
                    if member and user_id not in green_check_users:
                        print(f"   ⚠️ Registered user {member.name} missing green check, adding...")
                        try:
                            await rules_message.add_reaction('✅')
                            print(f"   ✅ Added green check for {member.name}")
                        except Exception as e:
                            print(f"   ❌ Error adding green check for {member.name}: {e}")
                
                # Check users with green check but not registered
                print("\n🔍 Checking for non-registered users with green check...")
                for user_id in green_check_users:
                    if str(user_id) not in registered_users:
                        member = guild.get_member(user_id)
                        if member:
                            # Check if they have family role (completed registration)
                            if family_role and family_role in member.roles:
                                print(f"   ℹ️ {member.name} has family role but not in registry, adding to registry...")
                                # Add to registry with basic info
                                registered_users[str(user_id)] = {
                                    'child_name': 'Unknown',
                                    'role': 'Parent',
                                    'nickname': member.display_name,
                                    'gender': 'unknown',
                                    'teams': [],
                                    'registered_at': discord.utils.utcnow().isoformat(),
                                    'auto_added': True
                                }
                                save_registered_users(registered_users)
                            else:
                                print(f"   ⚠️ {member.name} has green check but is not registered (no family role)")
        except Exception as e:
            print(f"⚠️ Error verifying green check marks: {e}")
    
    # Start background tasks
    inactivity_check.start()
    
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching,
        name="for messages to forward"
    ))

@tasks.loop(seconds=INACTIVITY_CHECK_INTERVAL)
async def inactivity_check():
    """Background task to check for inactive channels"""
    guild = bot.get_guild(GUILD_ID)
    if guild:
        await check_inactive_channels(guild)

@bot.event
async def on_member_remove(member: discord.Member):
    """Handle when a member leaves the server"""
    user_id = member.id
    user_id_str = str(user_id)
    
    print(f"👤 Member left: {member.name} (ID: {user_id})")
    
    # Delete user data from registered_users
    if user_id_str in registered_users:
        # Remove from registered_users
        del registered_users[user_id_str]
        save_registered_users(registered_users)
        print(f"🗑️ Deleted registration data for {member.name}")
    
    # Remove from user_states if present
    if user_id in user_states:
        del user_states[user_id]
        print(f"🗑️ Removed user state for {member.name}")
    
    # Remove from active_conversations
    if user_id in active_conversations:
        # Remove message references for this user
        message_ids_to_remove = []
        for admin_msg_id, user_msg_id in message_references.items():
            if user_msg_id == user_id:
                message_ids_to_remove.append(admin_msg_id)
        
        for msg_id in message_ids_to_remove:
            del message_references[msg_id]
        
        del active_conversations[user_id]
        print(f"🗑️ Removed active conversations for {member.name}")
    
    # Delete temporary channel if exists
    if user_id in user_temporary_channels:
        channel_id = user_temporary_channels[user_id]
        channel = member.guild.get_channel(channel_id)
        if channel:
            try:
                await channel.delete(reason=f"User {member.name} left the server")
                print(f"🗑️ Deleted temporary channel for {member.name}")
            except Exception as e:
                print(f"⚠️ Error deleting temporary channel: {e}")
        
        # Clean up data
        if channel_id in temporary_channels:
            del temporary_channels[channel_id]
        del user_temporary_channels[user_id]
    
    # Try to remove the green check mark reaction from rules message
    try:
        guild = bot.get_guild(GUILD_ID)
        if guild:
            rules_channel = guild.get_channel(RULES_CHANNEL_ID)
            if rules_channel:
                rules_message = await rules_channel.fetch_message(RULES_MESSAGE_ID)
                
                # Find the green check mark reaction
                for reaction in rules_message.reactions:
                    if str(reaction.emoji) == '✅':
                        # Remove this user's reaction
                        async for user in reaction.users():
                            if user.id == user_id:
                                await reaction.remove(user)
                                print(f"✅ Removed green check mark reaction for {member.name}")
                                break
    except discord.NotFound:
        print("⚠️ Rules message not found, cannot remove reaction")
    except discord.Forbidden:
        print("❌ No permission to remove reaction from rules message")
    except Exception as e:
        print(f"⚠️ Error removing reaction: {e}")
    
    print(f"✅ Cleanup complete for {member.name}")

@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    """Prevent users from removing their green check mark reaction"""
    print(f"\n❌ REACTION REMOVED DETECTED:")
    print(f"   Channel ID: {payload.channel_id}")
    print(f"   Message ID: {payload.message_id}")
    print(f"   Emoji: {payload.emoji}")
    print(f"   User ID: {payload.user_id}")
    
    # Ignore bot's own reactions
    if payload.user_id == bot.user.id:
        return
    
    # Check if this is the rules channel and the correct message
    if (payload.channel_id == RULES_CHANNEL_ID and 
        payload.message_id == RULES_MESSAGE_ID and 
        str(payload.emoji) == '✅'):
        
        print(f"   ⚠️ User tried to remove green check mark!")
        
        guild = bot.get_guild(payload.guild_id)
        if guild:
            member = guild.get_member(payload.user_id)
            if member and not member.bot:
                print(f"   👤 User: {member.name}")
                
                # Check if user is registered
                is_registered = str(member.id) in registered_users
                
                # Check if user has the family role (completed registration)
                has_family_role = False
                family_role = guild.get_role(FAMILY_ROLE_ID)
                if family_role:
                    has_family_role = family_role in member.roles
                
                # If user is registered or has family role, re-add the reaction
                if is_registered or has_family_role:
                    print(f"   🔄 User is registered/received family role, re-adding reaction...")
                    
                    try:
                        rules_channel = guild.get_channel(RULES_CHANNEL_ID)
                        if rules_channel:
                            rules_message = await rules_channel.fetch_message(RULES_MESSAGE_ID)
                            await rules_message.add_reaction('✅')
                            print(f"   ✅ Re-added green check mark for {member.name}")
                            
                            # Send warning to user in DM if possible
                            try:
                                dm_channel = await member.create_dm()
                                warning_embed = discord.Embed(
                                    title="⚠️ Registration Locked",
                                    description="Your green check mark reaction cannot be removed!\n\n"
                                              "Once you've accepted the rules and begun registration, "
                                              "your agreement is recorded. If you leave the server, "
                                              "your data will be automatically deleted.",
                                    color=discord.Color.orange()
                                )
                                await dm_channel.send(embed=warning_embed)
                            except discord.Forbidden:
                                print(f"   ⚠️ Cannot send DM warning to {member.name}")
                    except Exception as e:
                        print(f"   ❌ Error re-adding reaction: {e}")
                else:
                    print(f"   ℹ️ User is not registered, allowing reaction removal")
        else:
            print(f"   ❌ Guild not found")

@bot.event 
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    """Handle reactions for registration"""
    print(f"\n🎯 REACTION DETECTED:")
    print(f"   Channel ID: {payload.channel_id}")
    print(f"   Message ID: {payload.message_id}")
    print(f"   Emoji: {payload.emoji}")
    print(f"   User ID: {payload.user_id}")
    
    # Ignore bot's own reactions
    if payload.user_id == bot.user.id:
        print("   👆 Bot's own reaction, ignoring")
        return
    
    # Check if this is in our rules channel
    if payload.channel_id == RULES_CHANNEL_ID:
        print(f"   📍 This is in the RULES CHANNEL!")
        print(f"   Looking for message ID: {RULES_MESSAGE_ID}")
        
        # Check if it's the right message
        if payload.message_id == RULES_MESSAGE_ID:
            print(f"   ✅ CORRECT MESSAGE FOUND!")
            
            # Check if it's the green check mark
            if str(payload.emoji) == '✅':
                print(f"   🎉 GREEN CHECK MARK DETECTED!")
                
                guild = bot.get_guild(payload.guild_id)
                if guild:
                    member = guild.get_member(payload.user_id)
                    if member and not member.bot:
                        print(f"   👤 User: {member.name}")
                        
                        # Check if already registered
                        if str(member.id) in registered_users:
                            print(f"   ⚠️ User already registered")
                            
                            # Send message that they're already registered
                            try:
                                dm_channel = await member.create_dm()
                                already_registered_embed = discord.Embed(
                                    title="✅ Already Registered",
                                    description="You are already registered in our system!\n\n"
                                              "Your green check mark is locked and cannot be removed.",
                                    color=discord.Color.green()
                                )
                                await dm_channel.send(embed=already_registered_embed)
                            except discord.Forbidden:
                                print(f"   ⚠️ Cannot send DM to {member.name}")
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
    
    # Also handle DM reactions for registration
    channel = bot.get_channel(payload.channel_id)
    if isinstance(channel, discord.DMChannel):
        print(f"   💬 This is a DM reaction")
        user = bot.get_user(payload.user_id)
        if user and not user.bot:
            await handle_dm_reaction(user, payload.emoji, payload.message_id)

@bot.event
async def on_message(message: discord.Message):
    """Handle messages in monitored channels and DMs"""
    if message.author.bot:
        return
    
    # Handle messages in monitored channels (create temporary channel and forward)
    if message.channel.id in MONITORED_CHANNELS:
        await handle_monitored_channel_message(message)
        # Delete the original message
        try:
            await message.delete()
            print(f'🗑️ Deleted message from {message.author.name} in #{message.channel.name}')
        except discord.Forbidden:
            print(f'❌ Cannot delete message in #{message.channel.name}')
        except discord.NotFound:
            pass  # Message already deleted
    
    # Handle messages in temporary channels
    elif message.channel.id in temporary_channels:
        # Update last activity for this channel
        temporary_channels[message.channel.id]['last_activity'] = time.time()
        
        # If delete button was sent, remove it
        data = temporary_channels[message.channel.id]
        if data['delete_button_sent']:
            button_msg_id = data.get('delete_button_message_id')
            if button_msg_id:
                try:
                    button_msg = await message.channel.fetch_message(button_msg_id)
                    await button_msg.delete()
                    print(f"✅ Removed delete button from #{message.channel.name} (activity resumed)")
                except:
                    pass
            
            # Reset button sent flag
            temporary_channels[message.channel.id]['delete_button_sent'] = False
            temporary_channels[message.channel.id]['delete_button_message_id'] = None
        
        print(f'💬 Message in temporary channel #{message.channel.name}')
        
        # IMPORTANT: Process commands in temporary channels too!
        # This allows commands like !send_delete_button to work
        await bot.process_commands(message)
        return  # Return early so we don't double-process commands
    
    # Handle DMs to the bot (from admin or users)
    elif isinstance(message.channel, discord.DMChannel):
        # Check if this is the admin responding to a forwarded message
        if message.author.id == ADMIN_USER_ID:
            await handle_admin_dm_response(message)
        # Check if this is a user responding to admin in an active conversation
        elif message.author.id in active_conversations:
            await handle_user_dm_response(message)
        # Otherwise, handle registration DMs
        else:
            await handle_registration_dm(message)
    
    await bot.process_commands(message)

# ========== MESSAGE HANDLING FUNCTIONS ==========
async def handle_monitored_channel_message(message: discord.Message):
    """Handle messages from monitored channels by creating/using temporary channels"""
    # Acquire lock to prevent overlapping operations
    async with processing_lock:
        guild = message.guild
        user = message.author
        
        # Create or get existing temporary channel
        temp_channel = await create_temporary_channel(guild, user, message.channel.name)
        
        if not temp_channel:
            print(f"❌ Failed to create temporary channel for {user.name}")
            return
        
        # Determine which channel the message came from
        channel_name = message.channel.name
        channel_type = ""
        emoji = ""
        if message.channel.id == GENERAL_CHAT_CHANNEL_ID:
            channel_type = "General Chat"
            emoji = "👥"
        elif message.channel.id == NATIONAL_TEAM_CHANNEL_ID:
            channel_type = "National Team Chat"
            emoji = "🇺🇳"
        elif message.channel.id == DEMONSTRATION_TEAM_CHANNEL_ID:
            channel_type = "Demonstration Team Chat"
            emoji = "🎯"
        else:
            channel_type = f"#{channel_name}"
            emoji = "💬"
        
        # Create embed for the message
        embed = discord.Embed(
            title=f"{emoji} Message from {channel_type}",
            description=message.content,
            color=discord.Color.blue(),
            timestamp=message.created_at
        )
        
        # Add author info
        embed.set_author(
            name=f"{message.author.name} ({message.author.nick if message.author.nick else 'No nickname'})",
            icon_url=message.author.avatar.url if message.author.avatar else None
        )
        
        # Add metadata
        embed.add_field(name="👤 Author", value=f"{message.author.mention}", inline=True)
        embed.add_field(name="📝 Original Channel", value=f"#{channel_name}", inline=True)
        
        # Handle attachments
        if message.attachments:
            attachment_info = []
            for i, attachment in enumerate(message.attachments[:3]):
                if hasattr(attachment, 'content_type') and attachment.content_type and 'image' in attachment.content_type:
                    attachment_info.append(f"📸 [Image {i+1}]({attachment.url})")
                elif hasattr(attachment, 'filename'):
                    attachment_info.append(f"📎 [{attachment.filename}]({attachment.url})")
                else:
                    attachment_info.append(f"📎 [Attachment {i+1}]({attachment.url})")
            
            if len(message.attachments) > 3:
                attachment_info.append(f"...and {len(message.attachments) - 3} more")
            
            embed.add_field(name="📎 Attachments", value="\n".join(attachment_info), inline=False)
            
            # Also send first image as image in embed if available
            image_attachments = [a for a in message.attachments if hasattr(a, 'content_type') and a.content_type and 'image' in a.content_type]
            if image_attachments:
                embed.set_image(url=image_attachments[0].url)
        
        embed.set_footer(text="Reply in this channel to continue the conversation")
        
        try:
            # Send the message in temporary channel FIRST
            await temp_channel.send(embed=embed)
            print(f'📤 Forwarded message from {message.author.name} in {channel_type} to temporary channel')
            
            # Delete the original message AFTER successful forwarding
            await message.delete()
            print(f'🗑️ Deleted message from {message.author.name} in #{message.channel.name}')
            
        except discord.HTTPException as e:
            print(f'⚠️ Discord API rate limit or error: {e}')
            if e.status == 429:  # Too Many Requests
                retry_after = e.retry_after if hasattr(e, 'retry_after') else 5
                print(f'⏳ Rate limited, retry after: {retry_after} seconds')
                await asyncio.sleep(retry_after)
                
                # Try deleting again after backoff
                try:
                    await message.delete()
                    print(f'🗑️ Deleted message after rate limit backoff')
                except:
                    pass
        except discord.Forbidden:
            print(f'❌ Cannot delete message in #{message.channel.name} - check bot permissions')
        except discord.NotFound:
            pass  # Message already deleted
        except Exception as e:
            print(f'❌ Unexpected error in handle_monitored_channel_message: {e}')

async def handle_admin_dm_response(message: discord.Message):
    """Handle when admin responds to a forwarded message"""
    # Check if this is a reply to a forwarded message
    if message.reference and message.reference.message_id:
        try:
            referenced_msg_id = message.reference.message_id
            
            # Check if we have this message in our references
            if referenced_msg_id in message_references:
                user_id = message_references[referenced_msg_id]
                
                guild = bot.get_guild(GUILD_ID)
                if not guild:
                    return
                
                user = guild.get_member(user_id)
                if not user:
                    await message.channel.send("❌ User not found in the server.")
                    return
                
                # Get conversation context
                conv_data = active_conversations.get(user_id, {})
                channel_type = conv_data.get('channel_type', 'Chat')
                emoji = conv_data.get('channel_emoji', '💬')
                
                try:
                    user_dm = await user.create_dm()
                    
                    # Create embed for the admin's response
                    embed = discord.Embed(
                        title=f"{emoji} Response from Admin",
                        description=message.content,
                        color=discord.Color.green(),
                        timestamp=datetime.utcnow()
                    )
                    embed.set_footer(text=f"Regarding your message in {channel_type}")
                    
                    # Send the admin's message to the user
                    await user_dm.send(embed=embed)
                    
                    print(f'📨 Sent admin response to {user.name} regarding {channel_type}')
                    
                    # Confirm to admin
                    confirm_embed = discord.Embed(
                        description=f"✅ Response sent to {user.mention} ({user.name})",
                        color=discord.Color.green()
                    )
                    await message.channel.send(embed=confirm_embed)
                    
                except discord.Forbidden:
                    error_embed = discord.Embed(
                        description=f"❌ Cannot send DM to {user.name}. They may have DMs disabled.",
                        color=discord.Color.red()
                    )
                    await message.channel.send(embed=error_embed)
                except Exception as e:
                    error_embed = discord.Embed(
                        description=f"❌ Error sending response: {str(e)}",
                        color=discord.Color.red()
                    )
                    await message.channel.send(embed=error_embed)
            else:
                # Not a reply to one of our forwarded messages
                pass
        except Exception as e:
            print(f'Error handling admin DM response: {e}')
    else:
        # Admin sent a message without replying - send instructions
        help_embed = discord.Embed(
            title="💭 How Temporary Channels Work",
            description="**New System:**\n"
                      "1. When a user sends a message in monitored channels\n"
                      "2. A private temporary channel is created\n"
                      "3. Only you and the user can see/access it\n"
                      "4. All conversation happens in that channel\n\n"
                      "**Benefits:**\n"
                      "• Clean separation between conversations\n"
                      "• Delete button appears after inactivity (admin only)\n"
                      "• Easy to track individual discussions",
            color=discord.Color.blue()
        )
        await message.channel.send(embed=help_embed)

async def handle_user_dm_response(message: discord.Message):
    """Handle when a user responds to admin in DM"""
    user_id = message.author.id
    
    if user_id in active_conversations:
        conv_data = active_conversations[user_id]
        admin_id = conv_data.get('admin_id')
        channel_type = conv_data.get('channel_type', 'Chat')
        emoji = conv_data.get('channel_emoji', '💬')
        
        admin_user = bot.get_user(admin_id)
        if admin_user:
            try:
                admin_dm = await admin_user.create_dm()
                
                # Forward user's response to admin
                embed = discord.Embed(
                    title=f"{emoji} User Response ({channel_type})",
                    description=message.content,
                    color=discord.Color.blue(),
                    timestamp=datetime.utcnow()
                )
                embed.set_author(
                    name=f"{message.author.name}",
                    icon_url=message.author.avatar.url if message.author.avatar else None
                )
                embed.set_footer(text=f"User ID: {message.author.id}")
                
                # Handle attachments in user's response
                if message.attachments:
                    attachment_info = []
                    for i, attachment in enumerate(message.attachments[:3]):
                        if hasattr(attachment, 'content_type') and attachment.content_type and 'image' in attachment.content_type:
                            attachment_info.append(f"📸 [Image {i+1}]({attachment.url})")
                        elif hasattr(attachment, 'filename'):
                            attachment_info.append(f"📎 [{attachment.filename}]({attachment.url})")
                        else:
                            attachment_info.append(f"📎 [Attachment {i+1}]({attachment.url})")
                    
                    if len(message.attachments) > 3:
                        attachment_info.append(f"...and {len(message.attachments) - 3} more")
                    
                    embed.add_field(name="📎 Attachments", value="\n".join(attachment_info), inline=False)
                    
                    # Set image if available
                    image_attachments = [a for a in message.attachments if hasattr(a, 'content_type') and a.content_type and 'image' in a.content_type]
                    if image_attachments:
                        embed.set_image(url=image_attachments[0].url)
                
                forward_msg = await admin_dm.send(embed=embed)
                
                # Update the last forwarded message ID
                active_conversations[user_id]['last_forwarded_message_id'] = forward_msg.id
                message_references[forward_msg.id] = user_id
                
                print(f'📤 Forwarded user response from {message.author.name} to admin')
                
            except discord.Forbidden:
                print(f'❌ Cannot send DM to admin!')
            except Exception as e:
                print(f'❌ Error forwarding user response: {e}')

async def handle_registration_dm(message: discord.Message):
    """Handle registration DMs (existing functionality)"""
    user_id = message.author.id
    
    if user_id in user_states and user_states[user_id]['waiting_for_name']:
        child_name = message.content.strip()
        
        # Basic validation
        if len(child_name) < 2 or len(child_name) > 30:
            await message.channel.send("❌ Name must be 2-30 characters.")
            return
        
        if not all(c.isalnum() or c.isspace() or c in ".-'" for c in child_name):
            await message.channel.send("❌ Please use only letters, numbers, spaces, and basic punctuation.")
            return
        
        user_states[user_id]['child_name'] = child_name
        user_states[user_id]['waiting_for_name'] = False
        user_states[user_id]['waiting_for_gender'] = True
        
        print(f"📝 {message.author.name} entered child name: {child_name}")
        
        embed = discord.Embed(
            title="👨‍👩‍👧‍👦 Select Your Role",
            description=f"**Step 2 of 3**: Are you the mother or father of **{child_name}**?\n\n"
                      "👩 - I am the **Mother**\n"
                      "👨 - I am the **Father**\n\n"
                      "React with the appropriate emoji below:",
            color=discord.Color.green()
        )
        
        gender_message = await message.channel.send(embed=embed)
        await gender_message.add_reaction('👩')
        await gender_message.add_reaction('👨')
        
        user_states[user_id]['gender_message_id'] = gender_message.id
        
    elif user_id in user_states and user_states[user_id]['waiting_for_gender']:
        await message.channel.send("⚠️ Please select by reacting to the message above with 👩 or 👨.")
    elif user_id in user_states and user_states[user_id]['waiting_for_teams']:
        await message.channel.send("⚠️ Please select teams by reacting to the message above with 🇺🇳, 🎯, or ✅ when done.")

# ========== REGISTRATION FUNCTIONS ==========

async def assign_family_role(member: discord.Member):
    """Assign Family Member role to a member"""
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
    """Assign team roles to a member based on selection"""
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

async def start_dm_process(member: discord.Member):
    """Start the DM registration process"""
    try:
        if str(member.id) in registered_users:
            return
        
        print(f"📨 Attempting to DM {member.name}...")
        
        dm_channel = await member.create_dm()
        
        embed = discord.Embed(
            title="👨‍👩‍👧‍👦 Family Registration",
            description="Welcome! Let's register you as a parent.\n\n"
                      "I'll guide you through 3 steps:",
            color=discord.Color.blue()
        )
        embed.add_field(name="Step 1", value="Please type your child's FIRST and LAST NAME", inline=True)
        
        await dm_channel.send(embed=embed)
        await asyncio.sleep(1)
        
        # Initialize user state
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
    """Handle gender and team selection in DMs"""
    user_id = user.id
    
    # Handle gender selection
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
        
        # Send confirmation and move to team selection
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
    
    # Handle team selection completion
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
        
        # Get the team message to check which reactions the user added
        dm_channel = await user.create_dm()
        try:
            team_message = await dm_channel.fetch_message(message_id)
            
            # Check which team reactions the user has
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
        
        # Complete registration
        await complete_registration(user, member)

async def complete_registration(user: discord.User, member: discord.Member):
    """Complete the registration process"""
    user_id = user.id
    
    if user_id not in user_states:
        return
    
    child_name = user_states[user_id]['child_name']
    gender = user_states[user_id]['gender']
    teams_selected = user_states[user_id]['teams_selected']
    
    # Set nickname based on gender
    if gender == 'mother':
        new_nickname = f"{child_name}'s Mother"
        role_name = "Mother"
        emoji_role = "👩"
    else:  # father
        new_nickname = f"{child_name}'s Father"
        role_name = "Father"
        emoji_role = "👨"
    
    dm_channel = await user.create_dm()
    
    # Try to change nickname
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
    
    # Assign Family Member role
    family_role_assigned = await assign_family_role(member)
    
    # Assign team roles
    assigned_teams = await assign_team_roles(member, teams_selected)
    
    # Prepare team selection message
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
    
    # Prepare role assignment message
    role_msg = ""
    if family_role_assigned:
        role_msg += "✅ You have been given the **Family Member** role!\n"
    else:
        role_msg += "⚠️ Could not assign Family Member role. Please contact an administrator.\n"
    
    if assigned_teams:
        role_msg += f"✅ Added to {len(assigned_teams)} team(s): {', '.join(assigned_teams)}"
    elif teams_selected:
        role_msg += "⚠️ Could not assign team roles. Please contact an administrator."
    
    # Send final completion message
    embed = discord.Embed(
        title="🎉 Registration Complete!",
        description=f"{emoji_role} You are now registered as **{role_name}** of **{child_name}**!\n\n"
                  f"{success_msg}\n\n"
                  f"{role_msg}{team_message}\n\n"
                  f"Welcome to the family!",
        color=discord.Color.gold()
    )
    
    await dm_channel.send(embed=embed)
    
    # Register user data
    registered_users[str(user_id)] = {
        'child_name': child_name,
        'role': role_name,
        'nickname': new_nickname,
        'gender': gender,
        'teams': teams_selected,
        'registered_at': discord.utils.utcnow().isoformat()
    }
    save_registered_users(registered_users)
    
    # Clean up
    del user_states[user_id]
    
    print(f"✅ Registration complete for {user.name} with teams: {teams_selected}")

# ========== COMMANDS ==========

@bot.command(name="setup")
@commands.has_permissions(administrator=True)
async def setup_rules(ctx):
    """Set up the rules message with reaction"""
    if ctx.channel.id != RULES_CHANNEL_ID:
        await ctx.send(f"⚠️ Please run this command in the rules channel (<#{RULES_CHANNEL_ID}>)")
        return
    
    embed = discord.Embed(
        title="📜 Server Rules & Registration",
        description="**Welcome to our Tae Kwon Do Server!** 👨‍👩‍👧‍👦\n\n"
                   "**Rules:**\n"
                   "1. Be respectful to all family members\n"
                   "2. No bullying or harassment\n"
                   "3. Keep conversations family-friendly\n"
                   "4. Respect everyone's privacy\n"
                   "5. Have fun and build our community!\n\n"
                   "**After reading the rules, react with ✅ below to begin registration.**\n"
                   "You will receive a DM from 백호 (baekho) to complete the process.\n\n"
                   "**Note:** You will receive the access to the server after completing registration.",
        color=discord.Color.purple()
    )
    
    rules_message = await ctx.send(embed=embed)
    await rules_message.add_reaction('✅')
    
    # Update config with new message ID
    config['RULES_MESSAGE_ID'] = str(rules_message.id)
    with open('config.txt', 'w') as f:
        for key, value in config.items():
            f.write(f"{key}={value}\n")
    
    await ctx.send(f"✅ Rules message set up! New Message ID: {rules_message.id}")
    print(f"📝 New rules message ID saved: {rules_message.id}")

@bot.command(name="setup_temp_channels")
@commands.has_permissions(administrator=True)
async def setup_temp_channels(ctx):
    """Set up temporary channels configuration"""
    embed = discord.Embed(
        title="🔧 Temporary Channels Setup",
        description="**How temporary channels work:**\n"
                   "1. When a user sends a message in monitored channels\n"
                   "2. A private temporary channel is created\n"
                   "3. Only admin and the user can access it\n"
                   "4. After inactivity, a delete button appears (admin only)\n\n"
                   "**Current Configuration:**\n"
                   f"Temporary Channels Category ID: `{TEMPORARY_CHANNELS_CATEGORY_ID}`\n"
                   f"Inactivity Timeout: `{INACTIVITY_TIMEOUT}` seconds ({INACTIVITY_TIMEOUT//3600} hours)\n"
                   f"Check Interval: `{INACTIVITY_CHECK_INTERVAL}` seconds\n\n"
                   "**To change these, edit your config.txt file:**\n"
                   "`TEMPORARY_CHANNELS_CATEGORY_ID=category_id`\n"
                   "`INACTIVITY_TIMEOUT=7200` (2 hours in seconds)\n"
                   "`INACTIVITY_CHECK_INTERVAL=300` (5 minutes)",
        color=discord.Color.blue()
    )
    
    # Create category if not exists
    if not TEMPORARY_CHANNELS_CATEGORY_ID:
        category = await ctx.guild.create_category(
            name="📁 Private Conversations",
            reason="Temporary channels category",
            position=0
        )
        
        # Update config
        config['TEMPORARY_CHANNELS_CATEGORY_ID'] = str(category.id)
        with open('config.txt', 'w') as f:
            for key, value in config.items():
                f.write(f"{key}={value}\n")
        
        embed.add_field(name="✅ Created Category", value=f"New category created with ID: `{category.id}`", inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name="active_temp_channels")
@commands.has_permissions(administrator=True)
async def active_temp_channels(ctx):
    """Show active temporary channels"""
    if ctx.author.id != ADMIN_USER_ID:
        await ctx.send("❌ This command is only for the admin.", ephemeral=True)
        return
    
    if not temporary_channels:
        embed = discord.Embed(
            title="📁 Active Temporary Channels",
            description="No active temporary channels.",
            color=discord.Color.grey()
        )
        await ctx.send(embed=embed)
        return
    
    embed = discord.Embed(
        title="📁 Active Temporary Channels",
        description=f"Currently {len(temporary_channels)} active temporary channel(s):",
        color=discord.Color.blue()
    )
    
    for channel_id, data in temporary_channels.items():
        channel = ctx.guild.get_channel(channel_id)
        user = ctx.guild.get_member(data['user_id'])
        
        if channel and user:
            inactive_time = time.time() - data['last_activity']
            inactive_hours = inactive_time // 3600
            inactive_minutes = (inactive_time % 3600) // 60
            
            status = "✅ Active" if inactive_time < 300 else "⚠️ Inactive"  # 5 minutes threshold
            button_status = "🔴 Delete Button Sent" if data['delete_button_sent'] else "🟢 No Button"
            
            embed.add_field(
                name=f"🔒 {channel.name}",
                value=f"👤 User: {user.mention}\n"
                      f"📅 Created: <t:{int(data['created_at'])}:R>\n"
                      f"⏰ Inactive: {int(inactive_hours)}h {int(inactive_minutes)}m\n"
                      f"📝 From: {data['original_channel']}\n"
                      f"🔧 Status: {status}\n"
                      f"🛑 {button_status}",
                inline=True
            )
    
    await ctx.send(embed=embed)

@bot.command(name="close_channel")
@commands.has_permissions(administrator=True)
async def close_channel(ctx, channel: discord.TextChannel = None):
    """Close a temporary channel (admin only)"""
    if ctx.author.id != ADMIN_USER_ID:
        await ctx.send("❌ This command is only for the admin.", ephemeral=True)
        return
    
    if not channel:
        channel = ctx.channel
    
    if channel.id not in temporary_channels:
        await ctx.send("❌ This is not a temporary channel.", ephemeral=True)
        return
    
    # Get channel data
    data = temporary_channels[channel.id]
    user = ctx.guild.get_member(data['user_id'])
    
    # Send confirmation with buttons
    embed = discord.Embed(
        title="🗑️ Delete Temporary Channel",
        description=f"Are you sure you want to delete **{channel.name}**?\n\n"
                   f"**User:** {user.mention if user else 'Unknown'}\n"
                   f"**Created:** <t:{int(data['created_at'])}:R>\n"
                   f"**This action cannot be undone!**",
        color=discord.Color.red()
    )
    
    view = ConfirmDeleteView(channel.id, data['user_id'])
    await ctx.send(embed=embed, view=view)

@bot.command(name="send_delete_button")
@commands.has_permissions(administrator=True)
async def send_delete_button_cmd(ctx, channel: discord.TextChannel = None):
    """Manually send a delete button to a temporary channel"""
    if ctx.author.id != ADMIN_USER_ID:
        await ctx.send("❌ This command is only for the admin.", ephemeral=True)
        return
    
    if not channel:
        channel = ctx.channel
    
    if channel.id not in temporary_channels:
        await ctx.send("❌ This is not a temporary channel.", ephemeral=True)
        return
    
    # Send delete button - call the helper function, not recursively!
    button_msg = await send_delete_button_helper(channel)
    
    if button_msg:
        await ctx.send("✅ Delete button sent!", ephemeral=True)
    else:
        await ctx.send("❌ Failed to send delete button.", ephemeral=True)

@bot.command(name="cleanup_temp_channels")
@commands.has_permissions(administrator=True)
async def cleanup_temp_channels(ctx):
    """Clean up all temporary channels"""
    if ctx.author.id != ADMIN_USER_ID:
        await ctx.send("❌ This command is only for the admin.", ephemeral=True)
        return
    
    count = len(temporary_channels)
    
    if count == 0:
        await ctx.send("✅ No temporary channels to clean up.", ephemeral=True)
        return
    
    class ConfirmCleanupView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=60)
            self.confirmed = False
        
        @discord.ui.button(label="✅ Yes, Delete All", style=discord.ButtonStyle.danger)
        async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != ADMIN_USER_ID:
                await interaction.response.send_message("❌ Only admin can perform this action.", ephemeral=True)
                return
            
            self.confirmed = True
            self.stop()
            
            channels_deleted = 0
            channels_to_delete = list(temporary_channels.keys())
            
            for channel_id in channels_to_delete:
                channel = ctx.guild.get_channel(channel_id)
                if channel:
                    try:
                        await channel.delete(reason="Bulk cleanup by admin")
                        channels_deleted += 1
                    except:
                        pass
            
            # Clear data
            temporary_channels.clear()
            user_temporary_channels.clear()
            
            await interaction.response.send_message(
                f"✅ Deleted {channels_deleted} temporary channels.",
                ephemeral=True
            )
            
            # Update the original message
            embed = discord.Embed(
                title="✅ Cleanup Complete",
                description=f"Deleted {channels_deleted} temporary channels.",
                color=discord.Color.green()
            )
            await interaction.message.edit(embed=embed, view=None)
        
        @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
        async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != ADMIN_USER_ID:
                await interaction.response.send_message("❌ Only admin can cancel this action.", ephemeral=True)
                return
            
            self.confirmed = False
            self.stop()
            
            await interaction.response.send_message("❌ Cleanup cancelled.", ephemeral=True)
            
            embed = discord.Embed(
                title="❌ Cleanup Cancelled",
                description="No channels were deleted.",
                color=discord.Color.grey()
            )
            await interaction.message.edit(embed=embed, view=None)
    
    embed = discord.Embed(
        title="🧹 Cleanup Temporary Channels",
        description=f"This will delete **{count}** temporary channels.\n\n"
                   f"**Are you sure?** This action cannot be undone!\n"
                   f"All messages in these channels will be lost.",
        color=discord.Color.red()
    )
    
    view = ConfirmCleanupView()
    await ctx.send(embed=embed, view=view)

@bot.command(name="set_inactivity_timeout")
@commands.has_permissions(administrator=True)
async def set_inactivity_timeout(ctx, hours: int):
    """Set the inactivity timeout for temporary channels"""
    if ctx.author.id != ADMIN_USER_ID:
        await ctx.send("❌ This command is only for the admin.", ephemeral=True)
        return
    
    if hours < 1 or hours > 24:
        await ctx.send("❌ Timeout must be between 1 and 24 hours.", ephemeral=True)
        return
    
    seconds = hours * 3600
    config['INACTIVITY_TIMEOUT'] = str(seconds)
    
    with open('config.txt', 'w') as f:
        for key, value in config.items():
            f.write(f"{key}={value}\n")
    
    global INACTIVITY_TIMEOUT
    INACTIVITY_TIMEOUT = seconds
    
    # Restart the inactivity check task
    inactivity_check.cancel()
    inactivity_check.start()
    
    embed = discord.Embed(
        title="✅ Inactivity Timeout Updated",
        description=f"Delete buttons will now appear after **{hours} hours** of inactivity.",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

@bot.command(name="test_button")
@commands.has_permissions(administrator=True)
async def test_button(ctx):
    """Test the delete button functionality"""
    if ctx.author.id != ADMIN_USER_ID:
        await ctx.send("❌ This command is only for the admin.", ephemeral=True)
        return
    
    # Create a test view
    view = DeleteChannelView(ctx.channel.id, ctx.author.id)
    
    embed = discord.Embed(
        title="🛠️ Test Delete Button",
        description="This is a test of the delete button functionality.\n\n"
                   "Only you (the admin) can press this button!",
        color=discord.Color.blue()
    )
    
    await ctx.send(embed=embed, view=view)
    await ctx.send("✅ Test button sent! Try pressing it.")

@bot.command(name="active_chats")
async def active_chats(ctx):
    """Show active 1-on-1 conversations"""
    if ctx.author.id != ADMIN_USER_ID:
        await ctx.send("❌ This command is only for the admin.", ephemeral=True)
        return
    
    if not active_conversations:
        embed = discord.Embed(
            title="💭 Active Conversations",
            description="No active conversations.",
            color=discord.Color.grey()
        )
        await ctx.send(embed=embed)
        return
    
    embed = discord.Embed(
        title="💭 Active Conversations",
        description=f"Currently {len(active_conversations)} active conversation(s):",
        color=discord.Color.blue()
    )
    
    for user_id, conv_data in active_conversations.items():
        guild = bot.get_guild(GUILD_ID)
        if guild:
            member = guild.get_member(user_id)
            if member:
                channel_type = conv_data.get('channel_type', 'Unknown')
                emoji = conv_data.get('channel_emoji', '💬')
                embed.add_field(
                    name=f"{emoji} {member.name}",
                    value=f"Channel: {channel_type}\nUser ID: `{user_id}`",
                    inline=True
                )
    
    await ctx.send(embed=embed)

@bot.command(name="clear_chats")
async def clear_chats(ctx):
    """Clear all active conversations"""
    if ctx.author.id != ADMIN_USER_ID:
        await ctx.send("❌ This command is only for the admin.", ephemeral=True)
        return
    
    count = len(active_conversations)
    active_conversations.clear()
    message_references.clear()
    
    embed = discord.Embed(
        title="🧹 Conversations Cleared",
        description=f"Cleared {count} active conversation(s).",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

@bot.command(name="test_reaction")
async def test_reaction(ctx):
    """Test reaction detection"""
    test_msg = await ctx.send("Test message - react with ✅ to see if bot detects it!")
    await test_msg.add_reaction('✅')
    await ctx.send(f"Test message ID: `{test_msg.id}` - try reacting with ✅!")

@bot.command(name="debug_ids")
async def debug_ids(ctx):
    """Show all configured IDs"""
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
    embed.add_field(name="Temp Channels Category ID", value=f"`{TEMPORARY_CHANNELS_CATEGORY_ID}`", inline=True)
    embed.add_field(name="Bot User ID", value=f"`{bot.user.id}`", inline=True)
    
    # Check if we're in the rules channel
    if ctx.channel.id == RULES_CHANNEL_ID:
        embed.add_field(name="✅ Channel Status", value="This IS the rules channel!", inline=False)
    else:
        embed.add_field(name="⚠️ Channel Status", value=f"This is NOT the rules channel.\nRules channel: <#{RULES_CHANNEL_ID}>", inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name="check_message")
async def check_message(ctx, message_id: int = None):
    """Check a specific message's reactions"""
    if not message_id:
        message_id = RULES_MESSAGE_ID
    
    try:
        message = await ctx.channel.fetch_message(message_id)
        
        embed = discord.Embed(title=f"Message {message_id}", color=discord.Color.green())
        embed.add_field(name="Content", value=message.content[:100] + "..." if len(message.content) > 100 else message.content, inline=False)
        
        reactions = [str(r.emoji) for r in message.reactions]
        if reactions:
            embed.add_field(name="Reactions", value=", ".join(reactions), inline=False)
        else:
            embed.add_field(name="Reactions", value="No reactions", inline=False)
        
        await ctx.send(embed=embed)
    except discord.NotFound:
        await ctx.send(f"❌ Message {message_id} not found in this channel!")
    except discord.Forbidden:
        await ctx.send("❌ No permission to read this message!")
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")

@bot.command(name="force_register")
async def force_register(ctx):
    """Force start registration for yourself"""
    if str(ctx.author.id) in registered_users:
        await ctx.send("✅ You are already registered!", ephemeral=True)
        return
    
    await start_dm_process(ctx.author)
    await ctx.send("📨 Check your DMs to complete registration!", ephemeral=True)

@bot.command(name="assign_role")
@commands.has_permissions(administrator=True)
async def assign_role(ctx, member: discord.Member):
    """Manually assign Family Member role to a user"""
    success = await assign_family_role(member)
    if success:
        await ctx.send(f"✅ Assigned Family Member role to {member.mention}")
    else:
        await ctx.send(f"❌ Failed to assign role to {member.mention}")

@bot.command(name="update_message_id")
@commands.has_permissions(administrator=True)
async def update_message_id(ctx, message_id: int):
    """Manually update the rules message ID"""
    config['RULES_MESSAGE_ID'] = str(message_id)
    with open('config.txt', 'w') as f:
        for key, value in config.items():
            f.write(f"{key}={value}\n")
    
    await ctx.send(f"✅ Updated rules message ID to: {message_id}")
    print(f"📝 Manually updated rules message ID to: {message_id}")

@bot.command(name="register_stats")
async def register_stats(ctx):
    """Show registration statistics"""
    total_registered = len(registered_users)
    
    # Count team members
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

@bot.command(name="add_teams")
@commands.has_permissions(administrator=True)
async def add_teams(ctx, member: discord.Member):
    """Allow a user to join teams after registration"""
    user_id = member.id
    
    if str(user_id) not in registered_users:
        await ctx.send(f"❌ {member.mention} is not registered yet!", ephemeral=True)
        return
    
    # Create DM channel
    try:
        dm_channel = await member.create_dm()
        
        embed = discord.Embed(
            title="🎯 Join Teams",
            description="Would you like to join any teams? React below:\n\n"
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
        
        # Store in user states for processing
        user_states[user_id] = {
            'waiting_for_name': False,
            'waiting_for_gender': False,
            'waiting_for_teams': True,
            'child_name': registered_users[str(user_id)]['child_name'],
            'gender': registered_users[str(user_id)]['gender'],
            'teams_selected': registered_users[str(user_id)].get('teams', []),
            'team_message_id': team_message.id,
            'adding_teams': True  # Flag to indicate adding teams after registration
        }
        
        await ctx.send(f"✅ Sent team selection DM to {member.mention}", ephemeral=True)
        
    except discord.Forbidden:
        await ctx.send(f"❌ Cannot send DM to {member.mention} - they might have DMs disabled", ephemeral=True)

@bot.command(name="view_user")
@commands.has_permissions(administrator=True)
async def view_user(ctx, member: discord.Member):
    """View a user's registration information"""
    user_id = str(member.id)
    
    if user_id not in registered_users:
        await ctx.send(f"❌ {member.mention} is not registered yet!", ephemeral=True)
        return
    
    user_data = registered_users[user_id]
    
    embed = discord.Embed(
        title=f"👤 User Information: {member.name}",
        color=discord.Color.blue()
    )
    
    embed.add_field(name="Child's Name", value=user_data['child_name'], inline=True)
    embed.add_field(name="Role", value=user_data['role'], inline=True)
    embed.add_field(name="Nickname", value=user_data['nickname'], inline=True)
    
    teams = user_data.get('teams', [])
    if teams:
        team_list = []
        if "national" in teams:
            team_list.append("National Team 🇺🇳")
        if "demonstration" in teams:
            team_list.append("Demonstration Team 🎯")
        embed.add_field(name="Teams", value=", ".join(team_list), inline=True)
    else:
        embed.add_field(name="Teams", value="None", inline=True)
    
    embed.add_field(name="Registered At", value=user_data['registered_at'], inline=False)
    embed.add_field(name="User ID", value=user_id, inline=True)
    
    await ctx.send(embed=embed, ephemeral=True)

@bot.command(name="send_dm")
@commands.has_permissions(administrator=True)
async def send_dm(ctx, member: discord.Member, *, message: str):
    """Send a DM to a user"""
    try:
        dm_channel = await member.create_dm()
        embed = discord.Embed(
            title="💬 Message from Admin",
            description=message,
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        await dm_channel.send(embed=embed)
        await ctx.send(f"✅ DM sent to {member.mention}", ephemeral=True)
    except discord.Forbidden:
        await ctx.send(f"❌ Cannot send DM to {member.mention}", ephemeral=True)
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}", ephemeral=True)

@bot.command(name="remove_check")
@commands.has_permissions(administrator=True)
async def remove_check(ctx, member: discord.Member):
    """Manually remove a user's green check mark (for testing)"""
    try:
        rules_channel = ctx.guild.get_channel(RULES_CHANNEL_ID)
        if rules_channel:
            rules_message = await rules_channel.fetch_message(RULES_MESSAGE_ID)
            
            # Find the green check mark reaction
            for reaction in rules_message.reactions:
                if str(reaction.emoji) == '✅':
                    # Remove this user's reaction
                    await reaction.remove(member)
                    await ctx.send(f"✅ Removed green check mark reaction for {member.mention}")
                    
                    # Also cleanup their data
                    await cleanup_user_data(member.id)
                    await ctx.send(f"🗑️ Cleaned up data for {member.mention}")
                    return
        
        await ctx.send("❌ Could not find green check mark reaction")
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

@bot.command(name="check_consistency")
@commands.has_permissions(administrator=True)
async def check_consistency(ctx):
    """Check consistency between registry and green check marks"""
    guild = ctx.guild
    rules_channel = guild.get_channel(RULES_CHANNEL_ID)
    
    if not rules_channel:
        await ctx.send("❌ Rules channel not found")
        return
    
    try:
        rules_message = await rules_channel.fetch_message(RULES_MESSAGE_ID)
        
        # Get users who reacted with green check
        green_check_users = set()
        for reaction in rules_message.reactions:
            if str(reaction.emoji) == '✅':
                async for user in reaction.users():
                    if not user.bot:
                        green_check_users.add(user.id)
        
        embed = discord.Embed(
            title="🔍 Registry Consistency Check",
            color=discord.Color.blue()
        )
        
        # Check registered users without green check
        missing_check = []
        for user_id_str in registered_users.keys():
            user_id = int(user_id_str)
            if user_id not in green_check_users:
                member = guild.get_member(user_id)
                if member:
                    missing_check.append(f"{member.name} (ID: {user_id})")
        
        if missing_check:
            embed.add_field(
                name="❌ Registered users WITHOUT green check",
                value="\n".join(missing_check[:10]) + (f"\n...and {len(missing_check)-10} more" if len(missing_check) > 10 else ""),
                inline=False
            )
        else:
            embed.add_field(
                name="✅ All registered users have green check",
                value="No issues found!",
                inline=False
            )
        
        # Check users with green check but not registered
        not_registered = []
        for user_id in green_check_users:
            if str(user_id) not in registered_users:
                member = guild.get_member(user_id)
                if member:
                    not_registered.append(f"{member.name} (ID: {user_id})")
        
        if not_registered:
            embed.add_field(
                name="⚠️ Users with green check but NOT registered",
                value="\n".join(not_registered[:10]) + (f"\n...and {len(not_registered)-10} more" if len(not_registered) > 10 else ""),
                inline=False
            )
        
        embed.set_footer(text=f"Total registered: {len(registered_users)} | Total green checks: {len(green_check_users)}")
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You need admin permissions for this command.", ephemeral=True)
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing required argument: {error.param.name}", ephemeral=True)
    elif isinstance(error, commands.CommandNotFound):
        pass
    else:
        print(f"Error: {error}")

if __name__ == "__main__":
    print("\n🚀 Starting Family Registration & Temporary Channels Bot...")
    print("📝 Make sure your config.txt has the correct values!")
    print("\n=== REQUIRED CONFIG VALUES ===")
    print("TOKEN=your_bot_token_here")
    print("GUILD_ID=your_server_id_here")
    print("RULES_CHANNEL_ID=rules_channel_id_here")
    print("FAMILY_ROLE_ID=family_role_id_here")
    print("ADMIN_USER_ID=your_discord_user_id_here")
    print("\n=== OPTIONAL (but recommended) ===")
    print("GENERAL_CHAT_CHANNEL_ID=general_chat_channel_id_here")
    print("NATIONAL_TEAM_CHANNEL_ID=national_team_channel_id_here")
    print("DEMONSTRATION_TEAM_CHANNEL_ID=demonstration_team_channel_id_here")
    print("TEMPORARY_CHANNELS_CATEGORY_ID=temporary_channels_category_id_here")
    print("INACTIVITY_TIMEOUT=7200 (2 hours in seconds)")
    print("INACTIVITY_CHECK_INTERVAL=300 (5 minutes)")
    print("\n=== HOW IT WORKS ===")
    print("1. Users react to ✅ in rules channel to register")
    print("2. Registration happens via DM")
    print("3. Messages in monitored channels create temporary private channels")
    print("4. Only admin and the user can access the temporary channel")
    print("5. After inactivity, a delete button appears (admin only)")
    print("\n=== NEW FEATURES ===")
    print("🔒 Private temporary channels for each conversation")
    print("🛑 Delete button appears after inactivity (admin only)")
    print("🔄 Button disappears when conversation resumes")
    print("✅ Button-only deletion (no auto-delete)")
    print("📁 Organized in a dedicated category")
    print()
    
    if not TOKEN:
        print("❌ ERROR: Bot token not found in config.txt")
        print("   Please add: TOKEN=your_bot_token_here")
        exit(1)
    
    if not ADMIN_USER_ID:
        print("⚠️ WARNING: ADMIN_USER_ID not set in config.txt")
        print("   Chat forwarding will not work without this!")
        print("   Please add: ADMIN_USER_ID=your_discord_user_id_here")
    
    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        print("❌ ERROR: Invalid bot token!")
        print("   Please check your token in config.txt")
    except Exception as e:
        print(f"❌ ERROR starting bot: {e}")