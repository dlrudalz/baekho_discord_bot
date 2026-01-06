import discord
from discord.ext import commands
import os
import json
import asyncio
from typing import Dict, Optional, List
from datetime import datetime

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

# Store active conversations for 1-on-1 chat forwarding
active_conversations: Dict[int, Dict] = {}  # user_id -> {admin_id, channel_id, channel_type}
# Store message references for admin replies
message_references: Dict[int, int] = {}  # admin_message_id -> user_id

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

@bot.event
async def on_ready():
    print(f'✅ {bot.user} is online!')
    print(f'🆔 Bot ID: {bot.user.id}')
    print(f'👥 Connected to {len(bot.guilds)} server(s)')
    
    guild = bot.get_guild(GUILD_ID)
    if guild:
        print(f'🏠 Server: {guild.name} (ID: {guild.id})')
        
        # Check monitored channels
        print("\n📢 MONITORED CHANNELS (messages will be forwarded):")
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
    
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching,
        name="for messages to forward"
    ))

@bot.event
async def on_message(message: discord.Message):
    """Handle messages in monitored channels and DMs"""
    if message.author.bot:
        return
    
    # Handle messages in monitored channels (forward to admin)
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

async def handle_monitored_channel_message(message: discord.Message):
    """Forward messages from monitored channels to admin via DM"""
    admin_user = bot.get_user(ADMIN_USER_ID)
    if not admin_user:
        print(f'❌ Admin user not found! ID: {ADMIN_USER_ID}')
        return
    
    try:
        dm_channel = await admin_user.create_dm()
        
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
        
        # Create embed for the forwarded message
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
        embed.add_field(name="👤 Author", value=f"{message.author.mention}\nID: `{message.author.id}`", inline=True)
        embed.add_field(name="📝 Channel", value=f"#{channel_name}\n{emoji} {channel_type}", inline=True)
        
        # Handle attachments
        if message.attachments:
            attachment_info = []
            for i, attachment in enumerate(message.attachments[:3]):  # Limit to first 3 attachments
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
        
        embed.add_field(
            name="💭 How to Respond",
            value="**Reply to this message** to send a DM back to the user.\nYour response will be sent as a direct message from you.",
            inline=False
        )
        
        # Send the forwarded message
        forward_msg = await dm_channel.send(embed=embed)
        
        # Store conversation state
        active_conversations[message.author.id] = {
            'admin_id': ADMIN_USER_ID,
            'admin_dm_channel': dm_channel.id,
            'last_forwarded_message_id': forward_msg.id,
            'original_channel_id': message.channel.id,
            'original_channel_name': channel_name,
            'channel_type': channel_type,
            'channel_emoji': emoji
        }
        
        # Store message reference for easy lookup
        message_references[forward_msg.id] = message.author.id
        
        print(f'📤 Forwarded message from {message.author.name} in {channel_type} to admin')
        
    except discord.Forbidden:
        print(f'❌ Cannot send DM to admin!')
    except Exception as e:
        print(f'❌ Error forwarding message: {e}')

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
            title="💭 How to Respond to Users",
            description="To respond to a user's message:\n\n"
                      "1. Find their original message above\n"
                      "2. **Click 'Reply'** on that message\n"
                      "3. Type your response\n"
                      "4. Send the message\n\n"
                      "**Your response will be sent directly to the user as a DM from you.**\n\n"
                      "The user can then reply to your DM, and their response will appear here for you to continue the conversation.",
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
                      "I'll guide you through 3 simple steps:",
            color=discord.Color.blue()
        )
        embed.add_field(name="Step 1", value="Your child's name", inline=True)
        embed.add_field(name="Step 2", value="Select mother or father", inline=True)
        embed.add_field(name="Step 3", value="Choose which teams to join", inline=True)
        
        await dm_channel.send(embed=embed)
        await asyncio.sleep(1)
        
        await dm_channel.send("**Step 1 of 3**: Please type your child's name below:")
        
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
    
    # Update config with new message ID
    config['RULES_MESSAGE_ID'] = str(rules_message.id)
    with open('config.txt', 'w') as f:
        for key, value in config.items():
            f.write(f"{key}={value}\n")
    
    await ctx.send(f"✅ Rules message set up! New Message ID: {rules_message.id}")
    print(f"📝 New rules message ID saved: {rules_message.id}")

@bot.command(name="setup_chat_forwarding")
@commands.has_permissions(administrator=True)
async def setup_chat_forwarding(ctx):
    """Set up chat forwarding configuration"""
    embed = discord.Embed(
        title="💬 Chat Forwarding Setup",
        description="**How it works:**\n"
                   "1. Messages in monitored channels are deleted\n"
                   "2. Messages are forwarded to admin via DM\n"
                   "3. Admin can reply directly to the forwarded message\n"
                   "4. Replies are sent back to the user via DM\n\n"
                   "**Current Configuration:**\n"
                   f"General Chat Channel ID: `{GENERAL_CHAT_CHANNEL_ID}`\n"
                   f"National Team Channel ID: `{NATIONAL_TEAM_CHANNEL_ID}`\n"
                   f"Demonstration Team Channel ID: `{DEMONSTRATION_TEAM_CHANNEL_ID}`\n"
                   f"Admin User ID: `{ADMIN_USER_ID}`\n\n"
                   "**To change these, edit your config.txt file.**",
        color=discord.Color.blue()
    )
    
    await ctx.send(embed=embed)

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
    print("\n🚀 Starting Family Registration & Chat Forwarding Bot...")
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
    print("NATIONAL_TEAM_ROLE_ID=national_team_role_id_here")
    print("DEMONSTRATION_TEAM_ROLE_ID=demonstration_team_role_id_here")
    print("\n=== HOW IT WORKS ===")
    print("1. Users react to ✅ in rules channel to register")
    print("2. Registration happens via DM")
    print("3. Messages in monitored channels are forwarded to admin")
    print("4. Admin can reply directly to forwarded messages")
    print("5. All original messages in channels are deleted")
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
