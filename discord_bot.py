import discord
from discord.ext import commands
import os
import json
import asyncio
from typing import Dict, Optional

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
        
        # Check rules channel
        rules_channel = guild.get_channel(RULES_CHANNEL_ID)
        if rules_channel:
            print(f'📜 Rules Channel: #{rules_channel.name} (ID: {rules_channel.id})')
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
        
        # Check team channels
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
        
        # Check rules message
        if RULES_MESSAGE_ID:
            try:
                rules_channel = guild.get_channel(RULES_CHANNEL_ID)
                if rules_channel:
                    try:
                        rules_message = await rules_channel.fetch_message(RULES_MESSAGE_ID)
                        print(f'✅ Rules message found! (ID: {rules_message.id})')
                        # Check if message has reactions
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
    
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching,
        name="for ✅ reactions"
    ))

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

async def send_team_welcome_messages(member: discord.Member, teams_selected: list):
    """Send welcome messages to team channels"""
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return
    
    if "national" in teams_selected:
        national_channel = guild.get_channel(NATIONAL_TEAM_CHANNEL_ID)
        if national_channel:
            try:
                await national_channel.send(f"🎉 Welcome {member.mention} to the **National Team**! 🇺🇳\nPlease introduce yourself and check the pinned messages for important information!")
                print(f'✅ Sent National Team welcome message for {member.name}')
            except discord.Forbidden:
                print(f'❌ Cannot send message to National Team channel for {member.name}')
            except Exception as e:
                print(f'❌ Error sending National Team welcome: {e}')
    
    if "demonstration" in teams_selected:
        demonstration_channel = guild.get_channel(DEMONSTRATION_TEAM_CHANNEL_ID)
        if demonstration_channel:
            try:
                await demonstration_channel.send(f"🎉 Welcome {member.mention} to the **Demonstration Team**! 🎯\nPlease introduce yourself and check the pinned messages for important information!")
                print(f'✅ Sent Demonstration Team welcome message for {member.name}')
            except discord.Forbidden:
                print(f'❌ Cannot send message to Demonstration Team channel for {member.name}')
            except Exception as e:
                print(f'❌ Error sending Demonstration Team welcome: {e}')

@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    """Debug function to see ALL reactions"""
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
    
    # Also handle DM reactions
    channel = bot.get_channel(payload.channel_id)
    if isinstance(channel, discord.DMChannel):
        print(f"   💬 This is a DM reaction")
        user = bot.get_user(payload.user_id)
        if user and not user.bot:
            await handle_dm_reaction(user, payload.emoji, payload.message_id)

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
async def on_message(message: discord.Message):
    """Handle messages in DMs"""
    if message.author.bot:
        return
    
    if isinstance(message.channel, discord.DMChannel):
        user_id = message.author.id
        
        if user_id in user_states and user_states[user_id]['waiting_for_name']:
            child_name = message.content.strip()
            
            # Basic validation
            if len(child_name) < 2 or len(child_name) > 30:
                await message.channel.send("❌ Name must be 2-30 characters.")
                return
            
            if not all(c.isalnum() or c.isspace() for c in child_name):
                await message.channel.send("❌ Please use only letters, numbers, and spaces.")
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
    
    await bot.process_commands(message)

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
    
    # Send welcome messages to team channels
    await send_team_welcome_messages(member, teams_selected)
    
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
        
        # Add channel mentions
        channel_mentions = []
        if "national" in teams_selected and NATIONAL_TEAM_CHANNEL_ID:
            channel_mentions.append(f"<#{NATIONAL_TEAM_CHANNEL_ID}>")
        if "demonstration" in teams_selected and DEMONSTRATION_TEAM_CHANNEL_ID:
            channel_mentions.append(f"<#{DEMONSTRATION_TEAM_CHANNEL_ID}>")
        
        if channel_mentions:
            team_message += f"\n\n📢 Check your team channels: {', '.join(channel_mentions)}"
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

@bot.command(name="setup_teams")
@commands.has_permissions(administrator=True)
async def setup_teams(ctx):
    """Set up team channels and roles"""
    embed = discord.Embed(
        title="🏗️ Team Setup Instructions",
        description="To set up teams, please add the following to your config.txt file:\n\n"
                   f"```\n"
                   f"NATIONAL_TEAM_ROLE_ID=your_national_team_role_id_here\n"
                   f"DEMONSTRATION_TEAM_ROLE_ID=your_demo_team_role_id_here\n"
                   f"NATIONAL_TEAM_CHANNEL_ID=your_national_team_channel_id_here\n"
                   f"DEMONSTRATION_TEAM_CHANNEL_ID=your_demo_team_channel_id_here\n"
                   f"```\n\n"
                   f"**Current Configuration:**\n"
                   f"National Team Role ID: `{NATIONAL_TEAM_ROLE_ID}`\n"
                   f"Demonstration Team Role ID: `{DEMONSTRATION_TEAM_ROLE_ID}`\n"
                   f"National Team Channel ID: `{NATIONAL_TEAM_CHANNEL_ID}`\n"
                   f"Demonstration Team Channel ID: `{DEMONSTRATION_TEAM_CHANNEL_ID}`",
        color=discord.Color.blue()
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

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You need admin permissions for this command.", ephemeral=True)
    elif isinstance(error, commands.CommandNotFound):
        pass
    else:
        print(f"Error: {error}")

if __name__ == "__main__":
    print("\n🚀 Starting Family Registration Bot...")
    print("📝 Make sure your config.txt has the correct values!")
    print("\nRequired config values:")
    print("   TOKEN=your_bot_token")
    print("\nOptional team values:")
    print("   NATIONAL_TEAM_ROLE_ID=role_id_here")
    print("   DEMONSTRATION_TEAM_ROLE_ID=role_id_here")
    print("   NATIONAL_TEAM_CHANNEL_ID=channel_id_here")
    print("   DEMONSTRATION_TEAM_CHANNEL_ID=channel_id_here")
    print()
    
    if not TOKEN:
        print("❌ ERROR: Bot token not found in config.txt")
        print("   Please add: TOKEN=your_bot_token_here")
        exit(1)
    
    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        print("❌ ERROR: Invalid bot token!")
        print("   Please check your token in config.txt")
    except Exception as e:
        print(f"❌ ERROR starting bot: {e}")