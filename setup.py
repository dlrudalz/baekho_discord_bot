import discord
from discord.ext import commands
import os
import json
from typing import Dict
import asyncio

# ============================================================================
# CONFIGURATION SETUP
# ============================================================================

# Read configuration settings from config.txt file
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

# Extract configuration values with default fallbacks
TOKEN = config.get('TOKEN')
GUILD_ID = int(config.get('GUILD_ID', '0'))
ADMIN_USER_ID = int(config.get('ADMIN_USER_ID', '0'))

# Validate essential configuration values
if not TOKEN or TOKEN == 'your_bot_token_here':
    print("❌ ERROR: Please set your bot token in config.txt")
    exit(1)

# Configure Discord intents for required functionality
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

# Initialize the bot with command prefix and intents
bot = commands.Bot(command_prefix="!", intents=intents)

# Temporary storage for created IDs before updating config file
created_ids = {}

# Track if setup has been completed
setup_completed = False

# ============================================================================
# UTILITY FUNCTIONS AND CHECKS
# ============================================================================

def is_command_channel():
    """Decorator to restrict commands to the designated command channel.
    
    Allows the setup_server command to be used anywhere for initial setup.
    All other admin commands are restricted to the configured command channel.
    """
    async def predicate(ctx):
        # Allow !setup_server to be used anywhere by admin
        if ctx.command.name == "setup_server":
            return True
            
        # Get command channel ID from config
        command_channel_id = config.get('COMMAND_CHANNEL_ID')
        if not command_channel_id or command_channel_id == '0':
            await ctx.send("❌ Command channel not set up yet. Please run !setup_server first.")
            return False
        
        # Check if current channel is the command channel
        if ctx.channel.id != int(command_channel_id):
            await ctx.send(f"❌ This command can only be used in the command channel.")
            return False
            
        return True
    return commands.check(predicate)

async def update_config_file():
    """Update config.txt with new IDs.
    
    This function merges newly created IDs with existing configuration.
    """
    try:
        # Read existing config to get current values
        config_dict = {}
        try:
            with open('config.txt', 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        config_dict[key.strip()] = value.strip()
        except FileNotFoundError:
            pass
        
        # Update config_dict with created_ids
        config_dict.update(created_ids)
        
        # Write the updated config back to config.txt
        with open('config.txt', 'w') as f:
            for key, value in config_dict.items():
                f.write(f"{key}={value}\n")
        
        # Print summary of updated IDs
        print("\n📝 UPDATED/ADDED CONFIG ENTRIES:")
        for key in sorted(created_ids.keys()):
            print(f"   {key}: {created_ids[key]}")
        
        # Also update the global config variable
        globals()['config'].update(created_ids)
        
        # Clear created_ids after successful update
        created_ids.clear()
        
        return True
        
    except Exception as e:
        print(f"❌ Error updating config file: {e}")
        return False

async def check_bot_permissions(guild):
    """Check if the bot has necessary permissions for server setup.
    
    Returns a tuple of (success, message) indicating whether the bot
    has required permissions and a descriptive message.
    """
    bot_member = guild.get_member(bot.user.id)
    if not bot_member:
        return False, "Bot member not found in guild"
    
    # Check for Administrator permission first
    if bot_member.guild_permissions.administrator:
        return True, "✅ Bot has Administrator permission"
    
    # Check individual required permissions
    required_permissions = [
        ("manage_roles", "Manage Roles"),
        ("manage_channels", "Manage Channels"),
        ("manage_messages", "Manage Messages"),
        ("read_messages", "Read Messages"),
        ("send_messages", "Send Messages"),
        ("embed_links", "Embed Links"),
        ("attach_files", "Attach Files"),
        ("read_message_history", "Read Message History"),
        ("add_reactions", "Add Reactions")
    ]
    
    missing_perms = []
    for perm, name in required_permissions:
        if not getattr(bot_member.guild_permissions, perm):
            missing_perms.append(name)
    
    if missing_perms:
        return False, f"❌ Bot missing permissions: {', '.join(missing_perms)}"
    
    return True, "✅ Bot has all required permissions"

async def check_if_already_setup(guild):
    """Check if server setup has already been completed.
    
    Returns True if any of the main setup elements already exist.
    """
    global setup_completed
    
    # Check if any of the main categories already exist
    category_names = ["👋 WELCOME", "📅 SCHEDULE", "🔒 PRIVATE CONVERSATIONS", 
                      "📢 ANNOUNCEMENTS", "💭 TEXT CHANNELS", "🤖 BOT"]
    
    for category_name in category_names:
        category = discord.utils.get(guild.categories, name=category_name)
        if category:
            return True, f"Category '{category_name}' already exists"
    
    # Check if any of the main roles already exist
    role_names = ["Master Lee's Family", "Family Member", "National Team", "Demonstration Team"]
    
    for role_name in role_names:
        role = discord.utils.get(guild.roles, name=role_name)
        if role:
            return True, f"Role '{role_name}' already exists"
    
    # Check config file for existing IDs
    required_ids = [
        'WELCOME_CATEGORY_ID',
        'SCHEDULE_CATEGORY_ID',
        'PRIVATE_CONVERSATION_CATEGORY_ID',
        'ANNOUNCEMENTS_CATEGORY_ID',
        'TEXT_CHANNELS_CATEGORY_ID',
        'BOT_CATEGORY_ID',
        'MASTER_LEE_FAMILY_ROLE_ID',
        'FAMILY_ROLE_ID'
    ]
    
    for id_name in required_ids:
        id_value = config.get(id_name, '0')
        if id_value != '0' and id_value != '':
            # Check if the ID exists in the server
            try:
                if 'CATEGORY' in id_name:
                    category = guild.get_channel(int(id_value))
                    if category:
                        return True, f"Config contains existing category ID for {id_name}"
                elif 'ROLE' in id_name:
                    role = guild.get_role(int(id_value))
                    if role:
                        return True, f"Config contains existing role ID for {id_name}"
            except (ValueError, discord.NotFound):
                pass
    
    return False, "Server setup has not been completed yet"

async def ensure_general_chat_mute_message_setup(guild: discord.Guild, general_chat: discord.TextChannel, family_role: discord.Role):
    """
    Ensure the general-chat channel has the permanent mute instruction message.
    
    This message explains the muting system and allows users to react to gain
    permission to type in the channel.
    
    Args:
        guild: Discord guild object
        general_chat: The general chat channel
        family_role: The family role object
    """
    if not general_chat:
        print("❌ General chat channel not found")
        return
    
    try:
        # Check existing pinned messages
        pinned_messages = await general_chat.pins()
        
        # Look for our mute instruction message
        mute_message_found = False
        for pinned_msg in pinned_messages:
            if pinned_msg.author == bot.user and pinned_msg.embeds:
                for embed in pinned_msg.embeds:
                    if embed.title and "general-chat" in embed.title.lower():
                        mute_message_found = True
                        break
            if mute_message_found:
                break
        
        # Create and pin if not found
        if not mute_message_found:
            # Send temporary message while setting up
            temp_msg = await general_chat.send("🔄 Setting up general chat permissions...")
            
            # COMBINED EMBED: How This Chat Works + How to Get Access
            combined_embed = discord.Embed(
                title="🔒 How to Access & Use General-Chat",
                description=(
                    "**IMPORTANT:** Please Read Over Everything!\n\n"
                    "## 🔐 **HOW TO GET ACCESS**\n"
                    "### **Step 1: Mute This Channel:**\n"
                    "   📱 **On Mobile:**\n"
                    "   • Long-press on this channel name\n"
                    "   • Tap 'Mute Channel'\n"
                    "   • Select 'Until I turn it back on'\n\n"
                    "   💻 **On Desktop:**\n"
                    "   • Right-click on this channel\n"
                    "   • Click 'Mute Channel'\n"
                    "   • Select 'Until I turn it back on'\n\n"
                    "### **Step 2: Gain Typing Permission**\n"
                    "• React with 🔇 below to unlock typing permission\n"
                    "• This reaction grants you permission to type in this channel\n"
                    "• You only need to do this once\n\n"
                    "## ⚠️ **IMPORTANT NOTES**\n"
                    "• This is not group chat.\n"
                    "• It is for an individual who have questions for us.\n"
                ),
                color=discord.Color.red()
            )
            
            # Add footer with reminder
            combined_embed.set_footer(text="⬇️⬇️⬇️ REACT WITH 🔇 TO GAIN TYPING PERMISSION")
            
            # Send the combined message
            mute_message = await general_chat.send(embed=combined_embed)
            
            # Add the reaction
            await mute_message.add_reaction('🔇')
            
            # Pin the message
            await mute_message.pin()
            
            # Delete temporary message
            await temp_msg.delete()
            
            print("✅ Created and pinned combined general-chat instruction message")
            
    except Exception as e:
        print(f"❌ Error ensuring general-chat instruction message: {e}")

# ============================================================================
# BOT EVENTS
# ============================================================================

@bot.event
async def on_ready():
    """Event handler for when the bot has successfully connected to Discord.
    
    Prints connection information, validates permissions, and provides setup guidance.
    """
    print(f'✅ Setup bot is online!')
    print(f'🆔 Bot ID: {bot.user.id}')
    print(f'👥 Connected to {len(bot.guilds)} server(s)')
    
    guild = bot.get_guild(GUILD_ID)
    if guild:
        print(f'🏠 Server: {guild.name} (ID: {guild.id})')
        print(f'👑 Admin User ID: {ADMIN_USER_ID}')
        
        # Check bot permissions
        has_perms, message = await check_bot_permissions(guild)
        print(f'🔐 Permissions: {message}')
        
        # Check if setup has already been completed
        already_setup, setup_message = await check_if_already_setup(guild)
        if already_setup:
            print(f'📊 Setup Status: {setup_message}')
            print('⚠️  !setup_server can only be run once. Use !reset_setup first if needed.')
        
        if not has_perms:
            print("\n⚠️ IMPORTANT: The bot needs proper permissions to set up the server.")
            print("Please re-invite the bot with these permissions:")
            print("1. Go to Discord Developer Portal → Your Bot → OAuth2 → URL Generator")
            print("2. Select 'bot' scope")
            print("3. Select these permissions:")
            print("   - ✅ Administrator (recommended)")
            print("   OR all of these:")
            print("   - ✅ Manage Roles")
            print("   - ✅ Manage Channels")
            print("   - ✅ Manage Messages")
            print("   - ✅ Read Messages/View Channels")
            print("   - ✅ Send Messages")
            print("   - ✅ Embed Links")
            print("   - ✅ Attach Files")
            print("   - ✅ Read Message History")
            print("   - ✅ Add Reactions")
            print("\n4. Also make sure the bot's role is ABOVE other roles in Server Settings → Roles")
        
        admin_user = guild.get_member(ADMIN_USER_ID)
        if admin_user:
            print(f'👑 Admin: {admin_user.name} (ID: {admin_user.id})')
        else:
            print(f'⚠️ Admin user not found! ID: {ADMIN_USER_ID}')
    else:
        print(f'❌ Guild not found! ID: {GUILD_ID}')

@bot.event
async def on_command_error(ctx, error):
    """Global error handler for bot commands.
    
    Handles permission errors, command not found errors, and other command-related exceptions.
    """
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You need administrator permissions to run setup commands.")
    elif isinstance(error, commands.CommandNotFound):
        pass
    elif isinstance(error, commands.CheckFailure):
        # This handles the is_command_channel check
        pass
    else:
        print(f"Error: {error}")

# ============================================================================
# ADMIN COMMANDS
# ============================================================================

@bot.command(name="cleanup_unrecorded")
@commands.has_permissions(administrator=True)
@is_command_channel()
async def cleanup_unrecorded(ctx):
    """Clean up all server elements not recorded in config.txt.
    
    Deletes categories, channels, and roles that are not listed in the configuration file.
    Only elements protected by config IDs are preserved. Requires explicit confirmation.
    """
    if ctx.author.id != ADMIN_USER_ID:
        await ctx.send("❌ Only the configured admin can run this command.")
        return
    
    guild = ctx.guild
    
    # Check if we're in the right server
    if guild.id != GUILD_ID:
        await ctx.send("❌ This command must be run in the configured server.")
        return
    
    # Check bot permissions
    has_perms, message = await check_bot_permissions(guild)
    if not has_perms:
        await ctx.send(f"❌ {message}\n\nPlease re-invite the bot with proper permissions.")
        return
    
    # Confirmation
    embed = discord.Embed(
        title="⚠️ Cleanup Unrecorded Elements",
        description="**WARNING:** This will delete ALL categories, channels, and roles that are NOT recorded in config.txt!\n\n"
                   "This includes:\n"
                   "• Categories not in config.txt\n"
                   "• Text channels not in config.txt\n"
                   "• Voice channels not in config.txt\n"
                   "• Roles not in config.txt\n\n"
                   "**Only the @everyone role and the bot's own role will be preserved.**\n\n"
                   "Type `YES, CLEANUP UNRECORDED` to proceed.",
        color=discord.Color.red()
    )
    
    await ctx.send(embed=embed)
    
    def check(msg):
        return msg.author == ctx.author and msg.channel == ctx.channel and msg.content == "YES, CLEANUP UNRECORDED"
    
    try:
        await bot.wait_for('message', timeout=30.0, check=check)
    except:
        await ctx.send("❌ Cleanup cancelled (timeout).")
        return
    
    await ctx.send("🔄 Starting cleanup... This may take a moment.")
    
    # Collect all IDs from config.txt - FIXED: Only collect valid integer IDs
    config_ids = set()
    
    # Add all IDs from config, but only if they're valid integers
    for key, value in config.items():
        # Skip token and any non-ID values
        if key == 'TOKEN' or value is None:
            continue
            
        # Try to convert to integer, skip if it fails
        try:
            int_value = int(value)
            if int_value != 0:  # Skip '0' values
                config_ids.add(int_value)
        except ValueError:
            # Not an integer, skip it
            continue
    
    # Also add the bot's user ID and guild ID and admin user ID
    config_ids.add(bot.user.id)
    config_ids.add(guild.id)
    config_ids.add(ADMIN_USER_ID)
    
    # Add the @everyone role ID
    config_ids.add(guild.default_role.id)
    
    # Keep track of what we delete
    deleted_categories = []
    deleted_text_channels = []
    deleted_voice_channels = []
    deleted_roles = []
    
    try:
        # ========== DELETE UNRECORDED CHANNELS ==========
        await ctx.send("🔄 **Step 1/3: Checking channels...**")
        
        # Check all text channels
        for channel in guild.text_channels:
            if channel.id not in config_ids:
                try:
                    channel_name = channel.name
                    await channel.delete(reason="Cleanup unrecorded channels")
                    deleted_text_channels.append(channel_name)
                    await asyncio.sleep(0.5)  # Rate limit protection
                except discord.Forbidden:
                    await ctx.send(f"❌ No permission to delete channel: #{channel.name}")
                except discord.HTTPException as e:
                    await ctx.send(f"❌ Error deleting channel #{channel.name}: {e}")
        
        # Check all voice channels
        for channel in guild.voice_channels:
            if channel.id not in config_ids:
                try:
                    channel_name = channel.name
                    await channel.delete(reason="Cleanup unrecorded channels")
                    deleted_voice_channels.append(channel_name)
                    await asyncio.sleep(0.5)
                except discord.Forbidden:
                    await ctx.send(f"❌ No permission to delete voice channel: {channel.name}")
                except discord.HTTPException as e:
                    await ctx.send(f"❌ Error deleting voice channel {channel.name}: {e}")
        
        # ========== DELETE UNRECORDED CATEGORIES ==========
        await ctx.send("🔄 **Step 2/3: Checking categories...**")
        
        for category in guild.categories:
            if category.id not in config_ids:
                # Check if category is empty
                if len(category.channels) == 0:
                    try:
                        category_name = category.name
                        await category.delete(reason="Cleanup unrecorded categories")
                        deleted_categories.append(category_name)
                        await asyncio.sleep(0.5)
                    except discord.Forbidden:
                        await ctx.send(f"❌ No permission to delete category: {category.name}")
                    except discord.HTTPException as e:
                        await ctx.send(f"❌ Error deleting category {category.name}: {e}")
                else:
                    await ctx.send(f"⚠️ Category '{category.name}' has {len(category.channels)} channels. Skipping.")
        
        # ========== DELETE UNRECORDED ROLES ==========
        await ctx.send("🔄 **Step 3/3: Checking roles...**")
        
        for role in guild.roles:
            # Skip @everyone, bot's roles, and roles in config
            if role.id in config_ids:
                continue
            
            # Skip the bot's own roles
            if role in guild.me.roles:
                continue
            
            # Skip managed roles (bot roles)
            if role.managed:
                continue
            
            # Skip the @everyone role
            if role == guild.default_role:
                continue
            
            try:
                role_name = role.name
                await role.delete(reason="Cleanup unrecorded roles")
                deleted_roles.append(role_name)
                await asyncio.sleep(0.5)
            except discord.Forbidden:
                await ctx.send(f"❌ No permission to delete role: {role.name}")
            except discord.HTTPException as e:
                await ctx.send(f"❌ Error deleting role {role.name}: {e}")
        
        # ========== CREATE SUMMARY ==========
        summary_embed = discord.Embed(
            title="🧹 Cleanup Complete",
            description="Deleted all elements not recorded in config.txt",
            color=discord.Color.green()
        )
        
        if deleted_categories:
            categories_text = "\n".join([f"• {cat}" for cat in deleted_categories])
            summary_embed.add_field(
                name=f"🗑️ Deleted Categories ({len(deleted_categories)})",
                value=categories_text[:1024],
                inline=False
            )
        
        if deleted_text_channels:
            text_channels_text = "\n".join([f"• #{chan}" for chan in deleted_text_channels])
            summary_embed.add_field(
                name=f"🗑️ Deleted Text Channels ({len(deleted_text_channels)})",
                value=text_channels_text[:1024],
                inline=False
            )
        
        if deleted_voice_channels:
            voice_channels_text = "\n".join([f"• {chan}" for chan in deleted_voice_channels])
            summary_embed.add_field(
                name=f"🗑️ Deleted Voice Channels ({len(deleted_voice_channels)})",
                value=voice_channels_text[:1024],
                inline=False
            )
        
        if deleted_roles:
            roles_text = "\n".join([f"• @{role}" for role in deleted_roles])
            summary_embed.add_field(
                name=f"🗑️ Deleted Roles ({len(deleted_roles)})",
                value=roles_text[:1024],
                inline=False
            )
        
        if not any([deleted_categories, deleted_text_channels, deleted_voice_channels, deleted_roles]):
            summary_embed.add_field(
                name="✅ No Changes Needed",
                value="Everything in the server is already recorded in config.txt!",
                inline=False
            )
        
        summary_embed.add_field(
            name="📊 Config IDs Protected",
            value=f"Protected {len(config_ids)} IDs from config.txt",
            inline=False
        )
        
        summary_embed.set_footer(text="✅ Cleanup completed successfully")
        
        await ctx.send(embed=summary_embed)
        
        # Send to log channel if it exists
        log_channel_id = config.get('LOG_CHANNEL_ID')
        if log_channel_id and log_channel_id != '0':
            try:
                log_channel = guild.get_channel(int(log_channel_id))
                if log_channel:
                    log_embed = discord.Embed(
                        title="🧹 Cleanup Unrecorded Elements",
                        description=f"Deleted all elements not in config.txt\nCleaned by: {ctx.author.mention}",
                        color=discord.Color.green(),
                        timestamp=discord.utils.utcnow()
                    )
                    
                    total_deleted = len(deleted_categories) + len(deleted_text_channels) + len(deleted_voice_channels) + len(deleted_roles)
                    log_embed.add_field(name="Total Deleted", value=str(total_deleted), inline=True)
                    log_embed.add_field(name="Categories", value=str(len(deleted_categories)), inline=True)
                    log_embed.add_field(name="Text Channels", value=str(len(deleted_text_channels)), inline=True)
                    log_embed.add_field(name="Voice Channels", value=str(len(deleted_voice_channels)), inline=True)
                    log_embed.add_field(name="Roles", value=str(len(deleted_roles)), inline=True)
                    
                    await log_channel.send(embed=log_embed)
            except:
                pass
        
        print("=" * 50)
        print("🧹 CLEANUP COMPLETE!")
        print("=" * 50)
        print(f"Deleted Categories: {len(deleted_categories)}")
        print(f"Deleted Text Channels: {len(deleted_text_channels)}")
        print(f"Deleted Voice Channels: {len(deleted_voice_channels)}")
        print(f"Deleted Roles: {len(deleted_roles)}")
        print(f"Protected IDs from config: {len(config_ids)}")
        print("=" * 50)
        
    except Exception as e:
        await ctx.send(f"❌ Unexpected error during cleanup: {str(e)}")
        print(f"❌ Cleanup error: {e}")
        import traceback
        traceback.print_exc()

@bot.command(name="setup_server")
@commands.has_permissions(administrator=True)
async def setup_server(ctx):
    """Complete server setup with categories, channels, roles, and permissions.
    
    This is the main setup command that creates the entire server structure.
    It can be run from any channel by the configured admin user.
    CAN ONLY BE RUN ONCE - Use !reset_setup first if needed.
    """
    if ctx.author.id != ADMIN_USER_ID:
        await ctx.send("❌ Only the configured admin can run this command.")
        return
    
    guild = ctx.guild
    
    # Check if we're in the right server
    if guild.id != GUILD_ID:
        await ctx.send("❌ This command must be run in the configured server.")
        return
    
    # ========== CHECK IF SETUP HAS ALREADY BEEN COMPLETED ==========
    already_setup, setup_message = await check_if_already_setup(guild)
    if already_setup:
        embed = discord.Embed(
            title="❌ Setup Already Completed",
            description=f"**Server setup has already been completed!**\n\n"
                       f"Reason: {setup_message}\n\n"
                       f"If you need to run setup again, you must first:\n"
                       f"1. Use `!reset_setup` to delete all setup elements\n"
                       f"2. Or use `!cleanup_unrecorded` to clean up specific elements\n\n"
                       f"**Note:** The `!setup_server` command can only be run **once** per server setup.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        return
    
    # Check bot permissions
    has_perms, message = await check_bot_permissions(guild)
    if not has_perms:
        await ctx.send(f"❌ {message}\n\nPlease re-invite the bot with proper permissions.")
        
        # Create embed with invite instructions
        embed = discord.Embed(
            title="🔐 Bot Permission Error",
            description="The bot needs Administrator permissions or the following specific permissions:",
            color=discord.Color.red()
        )
        embed.add_field(
            name="Required Permissions",
            value="• Manage Roles\n• Manage Channels\n• Manage Messages\n• Read Messages\n• Send Messages\n• Embed Links\n• Attach Files\n• Read Message History\n• Add Reactions",
            inline=False
        )
        embed.add_field(
            name="How to fix",
            value="1. Go to [Discord Developer Portal](https://discord.com/developers/applications)\n"
                  "2. Select your bot application\n"
                  "3. Go to OAuth2 → URL Generator\n"
                  "4. Select 'bot' scope and check all required permissions\n"
                  "5. Use the generated link to re-invite the bot\n"
                  "6. Make sure the bot's role is ABOVE other roles in Server Settings → Roles",
            inline=False
        )
        await ctx.send(embed=embed)
        return
    
    # Confirmation message for first-time setup
    embed = discord.Embed(
        title="🚀 Server Setup Confirmation",
        description="**⚠️ IMPORTANT:** This command can only be run **once**!\n\n"
                   "This will create:\n"
                   "• 7 categories\n• 9 channels\n• 4 roles\n• Complete permission structure\n\n"
                   "If you need to run this again, you must use `!reset_setup` first.\n\n"
                   "Type `CONFIRM SETUP` to proceed with the setup.",
        color=discord.Color.orange()
    )
    
    await ctx.send(embed=embed)
    
    def check(msg):
        return msg.author == ctx.author and msg.channel == ctx.channel and msg.content == "CONFIRM SETUP"
    
    try:
        await bot.wait_for('message', timeout=30.0, check=check)
    except:
        await ctx.send("❌ Setup cancelled (timeout).")
        return
    
    await ctx.send("🚀 Starting server setup... This may take a moment.")
    
    try:
        # ========== CREATE ROLES ==========
        await ctx.send("🔄 **Step 1/6: Creating roles...**")

        try:
            # 1. Master Lee's Family Role (Admin role)
            master_lee_family_role = await guild.create_role(
                name="Master Lee's Family",
                color=discord.Color.gold(),
                hoist=True,
                mentionable=True,
                reason="Admin role for Master Lee's family members"
            )
            created_ids['MASTER_LEE_FAMILY_ROLE_ID'] = str(master_lee_family_role.id)
            
            # 2. Family Member Role (For registered parents/grandparents)
            family_role = await guild.create_role(
                name="Family Member",
                color=discord.Color.blue(),
                hoist=True,
                mentionable=True,
                reason="Role for registered family members"
            )
            created_ids['FAMILY_ROLE_ID'] = str(family_role.id)
            
            # 3. National Team Role
            national_role = await guild.create_role(
                name="National Team",
                color=discord.Color.red(),
                hoist=True,
                mentionable=True,
                reason="Role for national team members"
            )
            created_ids['NATIONAL_TEAM_ROLE_ID'] = str(national_role.id)
            
            # 4. Demonstration Team Role
            demonstration_role = await guild.create_role(
                name="Demonstration Team",
                color=discord.Color.green(),
                hoist=True,
                mentionable=True,
                reason="Role for demonstration team members"
            )
            created_ids['DEMONSTRATION_TEAM_ROLE_ID'] = str(demonstration_role.id)
            
            # 5. Student Role (same permissions as Family Member)
            student_role = await guild.create_role(
                name="Student",
                color=discord.Color.purple(),
                hoist=True,
                mentionable=True,
                reason="Role for students"
            )
            created_ids['STUDENT_ROLE_ID'] = str(student_role.id)
            
            # 6. Instructor Role (same permissions as Master Lee's Family)
            instructor_role = await guild.create_role(
                name="Instructor",
                color=discord.Color.dark_gold(),
                hoist=True,
                mentionable=True,
                reason="Role for instructors"
            )
            created_ids['INSTRUCTOR_ROLE_ID'] = str(instructor_role.id)
            
            await ctx.send("✅ **Roles created:** Master Lee's Family, Family Member, National Team, Demonstration Team, Student, Instructor")
            
        except discord.Forbidden as e:
            await ctx.send(f"❌ Error creating roles: {e}\n\nPlease make sure the bot's role is ABOVE other roles in Server Settings → Roles")
            return
        
        # ========== CREATE CATEGORIES ==========
        await ctx.send("🔄 **Step 2/6: Creating categories...**")

        try:
            # 1. WELCOME Category (formerly REQUIREMENTS)
            welcome_category = await guild.create_category(
                name="👋 WELCOME",
                position=0,
                reason="Welcome category for registration"
            )
            created_ids['WELCOME_CATEGORY_ID'] = str(welcome_category.id)
            
            # 2. 📅 SCHEDULE Category
            schedule_category = await guild.create_category(
                name="📅 SCHEDULE",
                position=1,
                reason="Schedule category for class times"
            )
            created_ids['SCHEDULE_CATEGORY_ID'] = str(schedule_category.id)
            
            # 3. 📢 ANNOUNCEMENTS Category
            announcements_category = await guild.create_category(
                name="📢 ANNOUNCEMENTS",
                position=2,
                reason="Announcements category"
            )
            created_ids['ANNOUNCEMENTS_CATEGORY_ID'] = str(announcements_category.id)
            
            # 4. 💭 TEXT CHANNELS Category
            text_channels_category = await guild.create_category(
                name="💭 TEXT CHANNELS",
                position=3,
                reason="General text channels category"
            )
            created_ids['TEXT_CHANNELS_CATEGORY_ID'] = str(text_channels_category.id)
            
            # 5. 🤖 BOT Category (Admin only)
            bot_category = await guild.create_category(
                name="🤖 BOT",
                position=4,
                reason="Bot channels category - Admin only"
            )
            created_ids['BOT_CATEGORY_ID'] = str(bot_category.id)
            
            # Set BOT category permissions to be visible only to admin user
            await bot_category.set_permissions(guild.default_role,
                view_channel=False,
                read_messages=False
            )
            
            # Get admin user object
            admin_user = guild.get_member(ADMIN_USER_ID)
            if admin_user:
                await bot_category.set_permissions(admin_user,
                    view_channel=True,
                    read_messages=True,
                    manage_channels=True,
                    manage_permissions=True
                )
            
            # Bot needs access too
            await bot_category.set_permissions(guild.me,
                view_channel=True,
                read_messages=True,
                manage_channels=True,
                manage_permissions=True
            )
            
            await ctx.send("✅ **Categories created:** WELCOME, SCHEDULE, ANNOUNCEMENTS, TEXT CHANNELS, BOT (Admin only)")
            
        except discord.Forbidden as e:
            await ctx.send(f"❌ Error creating categories: {e}\n\nPlease make sure the bot has 'Manage Channels' permission.")
            return
        
        # ========== CREATE CHANNELS WITH PERMISSIONS ==========
        await ctx.send("🔄 **Step 3/6: Creating channels...**")

        try:
            # 1. WELCOME Category - welcome channel (public)
            welcome_channel = await welcome_category.create_text_channel(
                name="welcome",
                topic="Welcome channel with rules and registration information",
                reason="Welcome channel for new members"
            )
            created_ids['WELCOME_CHANNEL_ID'] = str(welcome_channel.id)
            created_ids['RULES_CHANNEL_ID'] = str(welcome_channel.id)
            
            # Set permissions for welcome channel (public)
            await welcome_channel.set_permissions(guild.default_role, 
                read_messages=True,
                send_messages=False,
                read_message_history=True
            )
            
            # 2. 📅 SCHEDULE Category - schedule channel (restricted access, read-only for Family Member)
            schedule_channel = await schedule_category.create_text_channel(
                name="schedule",
                topic="Class schedules and training times - Access: Bot, Master Lee's Family (can text), Family Members (read-only)",
                reason="Schedule channel for classes - Restricted access, read-only for Family Member"
            )
            created_ids['SCHEDULE_CHANNEL_ID'] = str(schedule_channel.id)
            
            # Set permissions for schedule channel (restricted access)
            await schedule_channel.set_permissions(guild.default_role,
                read_messages=False,
                send_messages=False,
                view_channel=False
            )
            # Allow bot to access the channel with full permissions
            await schedule_channel.set_permissions(guild.me,
                read_messages=True,
                send_messages=True,
                manage_messages=True,
                view_channel=True,
                read_message_history=True
            )
            # Allow Master Lee's Family role to send messages
            await schedule_channel.set_permissions(master_lee_family_role,
                read_messages=True,
                send_messages=True,
                view_channel=True,
                read_message_history=True,
                embed_links=True,
                attach_files=True
            ) 
            # Allow Family Member role to READ ONLY (can't send messages)
            await schedule_channel.set_permissions(family_role,
                read_messages=True,
                send_messages=False,  # CHANGED FROM True TO False
                view_channel=True,
                read_message_history=True
            )
            await schedule_channel.set_permissions(student_role,
                read_messages=True,
                send_messages=False,  # Same as Family Member (read-only)
                view_channel=True,
                read_message_history=True
            )
            await schedule_channel.set_permissions(instructor_role,
                read_messages=True,
                send_messages=True,      # Can send messages (same as Master Lee's Family)
                view_channel=True,
                read_message_history=True,
                embed_links=True,
                attach_files=True
            )
            
            # 3. 💬 PRIVATE CONVERSATION Category - no channels by default
            # This category will have private chats created automatically
            
            # 4. 📢 ANNOUNCEMENTS Category
            # a) general-announcement (public - Family Member role only, read-only)
            general_announcement = await announcements_category.create_text_channel(
                name="general-announcements",
                topic="General announcements for all family members - Family Members: read-only",
                reason="General announcements channel"
            )
            created_ids['GENERAL_ANNOUNCEMENT_CHANNEL_ID'] = str(general_announcement.id)
            
            # Set permissions for general-announcement (Family Member role only, read-only)
            await general_announcement.set_permissions(guild.default_role,
                read_messages=False,
                send_messages=False
            )
            await general_announcement.set_permissions(family_role,
                read_messages=True,
                send_messages=False,  # READ ONLY
                read_message_history=True
            )
            await general_announcement.set_permissions(master_lee_family_role,
                read_messages=True,
                send_messages=True,
                manage_messages=True,
                read_message_history=True
            )
            await general_announcement.set_permissions(student_role,
                read_messages=True,
                send_messages=False,  # READ ONLY (same as Family Member)
                read_message_history=True
            )
            await general_announcement.set_permissions(instructor_role,
                read_messages=True,
                send_messages=True,      # Can send messages
                manage_messages=True,
                read_message_history=True
            )
            
            # b) demonstration-team (private - Demonstration Team role only, read-only)
            demonstration_team_channel = await announcements_category.create_text_channel(
                name="demonstration-team-announcements",
                topic="Demonstration team announcements and updates - Demonstration Team: read-only",
                reason="Demonstration team announcements"
            )
            created_ids['DEMONSTRATION_TEAM_CHANNEL_ID'] = str(demonstration_team_channel.id)
            
            # Set permissions for demonstration-team (Demonstration Team role only, read-only)
            await demonstration_team_channel.set_permissions(guild.default_role,
                read_messages=False,
                send_messages=False
            )
            await demonstration_team_channel.set_permissions(demonstration_role,
                read_messages=True,
                send_messages=False,  # CHANGED FROM True TO False (read-only)
                read_message_history=True
            )
            await demonstration_team_channel.set_permissions(master_lee_family_role,
                read_messages=True,
                send_messages=True,
                manage_messages=True,
                read_message_history=True
            )
            # Bot also needs access
            await demonstration_team_channel.set_permissions(guild.me,
                read_messages=True,
                send_messages=True,
                manage_messages=True,
                read_message_history=True
            )
            await demonstration_team_channel.set_permissions(instructor_role,
                read_messages=True,
                send_messages=True,
                manage_messages=True,
                read_message_history=True
            )
            
            # c) national-team (private - National Team role only, read-only)
            national_team_channel = await announcements_category.create_text_channel(
                name="national-team-announcements",
                topic="National team announcements and updates - National Team: read-only",
                reason="National team announcements"
            )
            created_ids['NATIONAL_TEAM_CHANNEL_ID'] = str(national_team_channel.id)
            
            # Set permissions for national-team (National Team role only, read-only)
            await national_team_channel.set_permissions(guild.default_role,
                read_messages=False,
                send_messages=False
            )
            await national_team_channel.set_permissions(national_role,
                read_messages=True,
                send_messages=False,  # CHANGED FROM True TO False (read-only)
                read_message_history=True
            )
            await national_team_channel.set_permissions(master_lee_family_role,
                read_messages=True,
                send_messages=True,
                manage_messages=True,
                read_message_history=True
            )
            # Bot also needs access
            await national_team_channel.set_permissions(guild.me,
                read_messages=True,
                send_messages=True,
                manage_messages=True,
                read_message_history=True
            )
            await national_team_channel.set_permissions(instructor_role,
                read_messages=True,
                send_messages=True,
                manage_messages=True,
                read_message_history=True
            )

            # 5. 💭 TEXT CHANNELS Category
            # a) general-chat (HIDDEN until registration - only visible after getting Family Member role)
            general_chat = await text_channels_category.create_text_channel(
                name="general-chat",
                topic="General chat for family members - Visible only after completing registration",
                reason="General chat channel - Hidden until registration"
            )
            created_ids['GENERAL_CHAT_CHANNEL_ID'] = str(general_chat.id)

            # Set permissions for general-chat (HIDDEN by default, only visible after getting Family Member role)
            await general_chat.set_permissions(guild.default_role,
                read_messages=False,      # Hidden from @everyone
                send_messages=False,
                view_channel=False
            )

            # Bot needs access
            await general_chat.set_permissions(guild.me,
                read_messages=True,
                send_messages=True,
                manage_messages=True,
                view_channel=True,
                read_message_history=True
            )

            # Admin needs access
            if admin_user:
                await general_chat.set_permissions(admin_user,
                    read_messages=True,
                    send_messages=True,
                    manage_messages=True,
                    view_channel=True,
                    read_message_history=True
                )

            # Master Lee's Family role can see it AND send messages by default
            await general_chat.set_permissions(master_lee_family_role,
                read_messages=True,
                send_messages=True,
                view_channel=True,
                read_message_history=True
            )

            # Family Member role CAN see by default but CANNOT send by default (will be enabled after mute reaction)
            await general_chat.set_permissions(family_role,
                read_messages=True,      # Can view the channel
                send_messages=False,     # Cannot send until they react with 🔇
                view_channel=True,       # Can see the channel
                read_message_history=True
            )
            await general_chat.set_permissions(student_role,
                read_messages=True,      # Can view the channel
                send_messages=False,     # Cannot send until they react with 🔇 (same as Family Member)
                view_channel=True,       # Can see the channel
                read_message_history=True
            )
            await general_chat.set_permissions(instructor_role,
                read_messages=True,
                send_messages=True,      # Can send by default
                view_channel=True,
                read_message_history=True
            )

            await ensure_general_chat_mute_message_setup(ctx.guild, general_chat, family_role)
            
            # 6. 🤖 BOT Category - All channels visible only to admin user
            # a) command (Admin only)
            command_channel = await bot_category.create_text_channel(
                name="command",
                topic="Bot command channel - type !help for available commands",
                reason="Bot command channel - Admin only"
            )
            created_ids['COMMAND_CHANNEL_ID'] = str(command_channel.id)
            
            # Set permissions for command channel (Admin user only)
            await command_channel.set_permissions(guild.default_role,
                read_messages=False,
                send_messages=False
            )
            
            if admin_user:
                await command_channel.set_permissions(admin_user,
                    read_messages=True,
                    send_messages=True,
                    manage_messages=True,
                    read_message_history=True
                )
            
            # Bot needs access too
            await command_channel.set_permissions(guild.me,
                read_messages=True,
                send_messages=True,
                manage_messages=True,
                read_message_history=True
            )
            
            # b) log (Admin only)
            log_channel = await bot_category.create_text_channel(
                name="log",
                topic="Bot logs and notifications - Admin only",
                reason="Bot log channel - Admin only"
            )
            created_ids['LOG_CHANNEL_ID'] = str(log_channel.id)
            
            # Set permissions for log channel (Admin user only)
            await log_channel.set_permissions(guild.default_role,
                read_messages=False,
                send_messages=False
            )
            
            if admin_user:
                await log_channel.set_permissions(admin_user,
                    read_messages=True,
                    send_messages=False,
                    read_message_history=True,
                    manage_messages=True
                )
            
            # Bot needs access too
            await log_channel.set_permissions(guild.me,
                read_messages=True,
                send_messages=True,
                manage_messages=True,
                read_message_history=True
            )
            
            # REMOVED: admin-chat channel creation
            
            await ctx.send("✅ **Channels created with proper permissions**")
            
        except discord.Forbidden as e:
            await ctx.send(f"❌ Error creating channels: {e}\n\nPlease make sure the bot has 'Manage Channels' permission.")
            return
        
        # ========== CREATE RULES MESSAGE ==========
        await ctx.send("🔄 **Step 4/6: Creating rules message...**")
        
        try:
            rules_embed = discord.Embed(
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
            
            rules_message = await welcome_channel.send(embed=rules_embed)
            await rules_message.add_reaction('✅')
            created_ids['RULES_MESSAGE_ID'] = str(rules_message.id)
            
            await ctx.send("✅ **Rules message created and pinned with ✅ reaction**")
            
        except discord.Forbidden as e:
            await ctx.send(f"❌ Error creating rules message: {e}\n\nPlease make sure the bot has 'Send Messages' and 'Add Reactions' permissions.")
            return
        
        # ========== CREATE PRIVATE CHATS CATEGORY ==========
        await ctx.send("🔄 **Step 5/6: Setting up private chats category...**")

        try:
            private_chats_category = await guild.create_category(
                name="🔒 PRIVATE CONVERSATIONS",  # Changed from "💬" to "🔒"
                position=2,
                reason="Category for temporary private chats"
            )
            created_ids['PRIVATE_CONVERSATION_CATEGORY_ID'] = str(private_chats_category.id)  # Use the same key
            
            # Set permissions for private chats category (no one can see by default)
            await private_chats_category.set_permissions(guild.default_role,
                read_messages=False,
                send_messages=False,
                view_channel=False
            )
            
            if admin_user:
                await private_chats_category.set_permissions(admin_user,
                    read_messages=True,
                    send_messages=True,
                    manage_channels=True,
                    view_channel=True
                )
            
            # Bot needs access too
            await private_chats_category.set_permissions(guild.me,
                read_messages=True,
                send_messages=True,
                manage_channels=True,
                view_channel=True
            )
            
            await ctx.send("✅ **Private conversations category created (admin-only access)**")
            
        except discord.Forbidden as e:
            await ctx.send(f"❌ Error creating private chats category: {e}\n\nPlease make sure the bot has 'Manage Channels' permission.")
            return
        
        # ========== UPDATE CONFIG FILE ==========
        await ctx.send("🔄 **Step 6/6: Updating configuration...**")
        
        # Also store the guild ID if not already in config
        if 'GUILD_ID' not in config or config['GUILD_ID'] == '0':
            created_ids['GUILD_ID'] = str(guild.id)
        
        # Also store admin user ID if not already in config
        if 'ADMIN_USER_ID' not in config or config['ADMIN_USER_ID'] == '0':
            created_ids['ADMIN_USER_ID'] = str(ADMIN_USER_ID)
        
        # Also store bot ID
        created_ids['BOT_USER_ID'] = str(bot.user.id)
        
        # Mark setup as completed
        globals()['setup_completed'] = True
        
        # Update the config file
        success = await update_config_file()
        
        if success:
            # ========== FINAL SUMMARY ==========
            summary_embed = discord.Embed(
                title="🎉 Server Setup Complete!",
                description="The server has been successfully configured with all categories, channels, roles, and permissions.\n\n"
                           "**⚠️ IMPORTANT: This setup can only be run once!**\n"
                           "If you need to modify the setup, use individual fix commands or run `!reset_setup` first.",
                color=discord.Color.green()
            )
            
            summary_embed.add_field(
                name="📁 Categories Created (All IDs saved)",
                value=f"• 👋 WELCOME (ID: {welcome_category.id})\n"
                    f"• 📅 SCHEDULE (ID: {schedule_category.id})\n"
                    f"• 💬 PRIVATE CONVERSATIONS (ID: {private_chats_category.id})\n"
                    f"• 📢 ANNOUNCEMENTS (ID: {announcements_category.id})\n"
                    f"• 💭 TEXT CHANNELS (ID: {text_channels_category.id})\n"
                    f"• 🤖 BOT **(Admin User Only)** (ID: {bot_category.id})\n",
                inline=False
            )
            
            summary_embed.add_field(
                name="👑 Roles Created (All IDs saved)",
                value=f"• Master Lee's Family (Admin) (ID: {master_lee_family_role.id})\n"
                      f"• Family Member (ID: {family_role.id})\n"
                      f"• National Team (ID: {national_role.id})\n"
                      f"• Demonstration Team (ID: {demonstration_role.id})",
                inline=False
            )
            
            summary_embed.add_field(
                name="🔐 BOT Category Permissions",
                value=f"**🤖 BOT category and its channels are now visible ONLY to:**\n"
                      f"• Admin user: {admin_user.mention if admin_user else 'Not found'}\n"
                      f"• The bot itself\n\n"
                      f"**Master Lee's Family role CANNOT access BOT category**",
                inline=False
            )
            
            summary_embed.add_field(
                name="🔐 Command Channel Restriction",
                value=f"**All admin commands (except !setup_server) now restricted to:**\n"
                      f"• {command_channel.mention} (ID: {command_channel.id})\n\n"
                      f"**!setup_server can be used anywhere by admin**",
                inline=False
            )
            
            summary_embed.add_field(
                name="⚠️ One-Time Setup Notice",
                value="**This setup can only be run once!**\n"
                      "To modify the setup:\n"
                      "• Use individual commands like `!fix_schedule_permissions`\n"
                      "• Or use `!reset_setup` to delete everything and start over\n"
                      "• Never run `!setup_server` again without resetting first",
                inline=False
            )
            
            summary_embed.set_footer(text="✅ All IDs have been saved to config.txt")
            
            await ctx.send(embed=summary_embed)
            
            # Send to log channel if it exists
            log_channel_obj = guild.get_channel(int(created_ids.get('LOG_CHANNEL_ID', '0')))
            if log_channel_obj:
                log_embed = discord.Embed(
                    title="🚀 Server Setup Completed",
                    description="The server has been fully configured by the setup bot.",
                    color=discord.Color.green(),
                    timestamp=discord.utils.utcnow()
                )
                log_embed.add_field(name="Setup By", value=ctx.author.mention, inline=True)
                log_embed.add_field(name="Time", value=f"<t:{int(discord.utils.utcnow().timestamp())}:R>", inline=True)
                log_embed.add_field(name="Categories Created", value="7", inline=True)
                log_embed.add_field(name="Channels Created", value="9", inline=True)  # Reduced from 10 (removed admin-chat)
                log_embed.add_field(name="Roles Created", value="4", inline=True)
                log_embed.add_field(name="One-Time Setup", value="✅ Completed - Cannot be run again", inline=True)
                log_embed.set_footer(text="All IDs saved to config.txt")
                await log_channel_obj.send(embed=log_embed)
            
            print("=" * 50)
            print("✅ SERVER SETUP COMPLETE!")
            print("=" * 50)
            print("⚠️  IMPORTANT: This setup can only be run once!")
            print("=" * 50)
            print("\n📝 ALL CONFIG VALUES SAVED:")
            for key, value in created_ids.items():
                print(f"   {key}: {value}")
            print("=" * 50)
            print("\n🔐 IMPORTANT: BOT category permissions set to:")
            print(f"   • Admin User (ID: {ADMIN_USER_ID}) - Full access")
            print(f"   • Bot (ID: {bot.user.id}) - Full access")
            print(f"   • Master Lee's Family Role - NO ACCESS (removed)")
            print(f"   • @everyone - NO ACCESS")
            print("=" * 50)
            print("\n🔐 COMMAND RESTRICTIONS:")
            print("   • !setup_server - Can be used anywhere by admin (ONCE ONLY)")
            print(f"   • All other commands - Restricted to command channel (ID: {command_channel.id})")
            print("=" * 50)
            print("\n🚀 Next: Run the main bot with:")
            print("   python main_bot.py")
            
        else:
            await ctx.send("❌ Error updating config file. Please check console for details.")
        
    except Exception as e:
        await ctx.send(f"❌ Unexpected error during setup: {str(e)}")
        print(f"❌ Setup error: {e}")
        import traceback
        traceback.print_exc()

@bot.command(name="setup_check")
@commands.has_permissions(administrator=True)
@is_command_channel()
async def setup_check(ctx):
    """Check current server setup status and bot permissions.
    
    Provides a comprehensive overview of the current server configuration,
    including roles, categories, channel permissions, and config values.
    """
    if ctx.author.id != ADMIN_USER_ID:
        await ctx.send("❌ Only the configured admin can run this command.")
        return
    
    guild = ctx.guild
    
    # Check if setup has already been completed
    already_setup, setup_message = await check_if_already_setup(guild)
    
    # Check bot permissions
    has_perms, perm_message = await check_bot_permissions(guild)
    
    embed = discord.Embed(
        title="🔍 Server Setup Check",
        description="Checking current server configuration...",
        color=discord.Color.blue()
    )
    
    # Add setup status
    if already_setup:
        embed.add_field(
            name="📊 Setup Status",
            value=f"✅ **Setup already completed**\n{setup_message}\n\n"
                  "⚠️ **!setup_server can only be run once!**\n"
                  "Use individual fix commands or !reset_setup first.",
            inline=False
        )
    else:
        embed.add_field(
            name="📊 Setup Status",
            value="❌ **Setup not completed yet**\nYou can run `!setup_server` to set up the server.",
            inline=False
        )
    
    embed.add_field(
        name="🔐 Bot Permissions",
        value=perm_message,
        inline=False
    )
    
    # Check roles
    required_roles = ["Master Lee's Family", "Family Member", "National Team", "Demonstration Team", "Student", "Instructor"]
    roles_found = []
    roles_missing = []
    
    for role_name in required_roles:
        role = discord.utils.get(guild.roles, name=role_name)
        if role:
            roles_found.append(f"✅ {role_name} (ID: {role.id})")
        else:
            roles_missing.append(f"❌ {role_name}")
    
    roles_text = "\n".join(roles_found + roles_missing) if roles_found or roles_missing else "No required roles found"
    embed.add_field(
        name="👑 Roles",
        value=roles_text,
        inline=False
    )
    
    # Check categories
    required_categories = ["👋 WELCOME", "📅 SCHEDULE", "🔒 PRIVATE CONVERSATIONS", 
                          "📢 ANNOUNCEMENTS", "💭 TEXT CHANNELS", "🤖 BOT"]
    categories_found = []
    categories_missing = []
    
    for category_name in required_categories:
        category = discord.utils.get(guild.categories, name=category_name)
        if category:
            categories_found.append(f"✅ {category_name} (ID: {category.id})")
        else:
            categories_missing.append(f"❌ {category_name}")
    
    categories_text = "\n".join(categories_found + categories_missing) if categories_found or categories_missing else "No required categories found"
    embed.add_field(
        name="📁 Categories",
        value=categories_text,
        inline=False
    )
    
    # Check schedule channel permissions
    schedule_channel = discord.utils.get(guild.channels, name="schedule")
    if schedule_channel:
        # Check who can view the schedule channel
        everyone_perms = schedule_channel.permissions_for(guild.default_role)
        family_role = discord.utils.get(guild.roles, name="Family Member")
        master_role = discord.utils.get(guild.roles, name="Master Lee's Family")
        
        schedule_perms = []
        if everyone_perms.view_channel or everyone_perms.read_messages:
            schedule_perms.append("❌ @everyone can view (should NOT have access)")
        else:
            schedule_perms.append("✅ @everyone cannot view")
        
        if family_role:
            family_perms = schedule_channel.permissions_for(family_role)
            if family_perms.view_channel and family_perms.read_messages:
                schedule_perms.append(f"✅ Family Member role can view (ID: {family_role.id})")
            else:
                schedule_perms.append(f"❌ Family Member role cannot view")
        
        if master_role:
            master_perms = schedule_channel.permissions_for(master_role)
            if master_perms.view_channel and master_perms.read_messages:
                schedule_perms.append(f"✅ Master Lee's Family role can view (ID: {master_role.id})")
            else:
                schedule_perms.append(f"❌ Master Lee's Family role cannot view")
        
        # Check bot permissions
        bot_perms = schedule_channel.permissions_for(guild.me)
        if bot_perms.view_channel and bot_perms.read_messages:
            schedule_perms.append(f"✅ Bot can view (ID: {guild.me.id})")
        else:
            schedule_perms.append(f"❌ Bot cannot view")
        
        embed.add_field(
            name="📅 Schedule Channel Permissions",
            value="\n".join(schedule_perms),
            inline=False
        )
    else:
        embed.add_field(
            name="📅 Schedule Channel",
            value="❌ Not found",
            inline=False
        )
    
    # Check bot category permissions
    bot_category = discord.utils.get(guild.categories, name="🤖 BOT")
    if bot_category:
        # Check if @everyone can view the category
        everyone_perms = bot_category.permissions_for(guild.default_role)
        if everyone_perms.view_channel or everyone_perms.read_messages:
            bot_cat_status = "❌ **BOT category is visible to everyone** - Should be admin only!"
        else:
            bot_cat_status = "✅ **BOT category is properly hidden from everyone**"
        
        # Check if admin user can view
        admin_user = guild.get_member(ADMIN_USER_ID)
        if admin_user:
            admin_perms = bot_category.permissions_for(admin_user)
            if admin_perms.view_channel and admin_perms.read_messages:
                bot_cat_status += f"\n✅ **Admin user can access BOT category (ID: {admin_user.id})**"
            else:
                bot_cat_status += f"\n❌ **Admin user cannot access BOT category**"
        
        # Check if Master Lee's Family role can view (should NOT)
        admin_role = discord.utils.get(guild.roles, name="Master Lee's Family")
        if admin_role:
            admin_role_perms = bot_category.permissions_for(admin_role)
            if admin_role_perms.view_channel or admin_role_perms.read_messages:
                bot_cat_status += f"\n⚠️ **Master Lee's Family role can access BOT category (should NOT)**"
            else:
                bot_cat_status += f"\n✅ **Master Lee's Family role cannot access BOT category (correct)**"
    else:
        bot_cat_status = "❌ BOT category not found"
    
    embed.add_field(
        name="🤖 BOT Category Visibility",
        value=bot_cat_status,
        inline=False
    )
    
    # Check command channel restriction
    command_channel_id = config.get('COMMAND_CHANNEL_ID')
    if command_channel_id and command_channel_id != '0':
        command_channel = guild.get_channel(int(command_channel_id))
        if command_channel:
            embed.add_field(
                name="🔐 Command Channel Restriction",
                value=f"✅ **Command channel set to:** {command_channel.mention}\n"
                      f"• !setup_server can be used anywhere\n"
                      f"• All other commands restricted to this channel",
                inline=False
            )
        else:
            embed.add_field(
                name="🔐 Command Channel Restriction",
                value=f"⚠️ **Command channel ID exists but channel not found**\nID: {command_channel_id}",
                inline=False
            )
    else:
        embed.add_field(
            name="🔐 Command Channel Restriction",
            value="❌ **Command channel not set up**\nRun !setup_server to create it",
            inline=False
        )
    
    # Check bot role position
    bot_member = guild.get_member(bot.user.id)
    if bot_member:
        bot_top_role = bot_member.top_role
        role_position = f"Position: {bot_top_role.position} (higher is better)"
        if bot_top_role.position < 5:  # Arbitrary threshold
            role_position += "\n⚠️ Bot role might be too low for proper setup"
        embed.add_field(
            name="🤖 Bot Role Position",
            value=role_position,
            inline=False
        )
    
    # Check config values
    embed.add_field(
        name="⚙️ Current Config Values",
        value=f"**Guild ID:** `{GUILD_ID}`\n"
              f"**Admin User ID:** `{ADMIN_USER_ID}`\n"
              f"**Bot User ID:** `{config.get('BOT_USER_ID', 'Not set')}`\n"
              f"**Welcome Category ID:** `{config.get('WELCOME_CATEGORY_ID', 'Not set')}`\n"
              f"**Schedule Category ID:** `{config.get('SCHEDULE_CATEGORY_ID', 'Not set')}`\n"
              f"**Schedule Channel ID:** `{config.get('SCHEDULE_CHANNEL_ID', 'Not set')}`\n"
              f"**Family Role ID:** `{config.get('FAMILY_ROLE_ID', 'Not set')}`\n"
              f"**General Chat ID:** `{config.get('GENERAL_CHAT_CHANNEL_ID', 'Not set')}`\n"
              f"**Command Channel ID:** `{config.get('COMMAND_CHANNEL_ID', 'Not set')}`",
        inline=False
    )
    
    if not has_perms:
        embed.add_field(
            name="🚨 Action Required",
            value="The bot needs proper permissions to run setup.\n"
                  "Use `!setup_server` after fixing permissions.",
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command(name="fix_schedule_permissions")
@commands.has_permissions(administrator=True)
@is_command_channel()
async def fix_schedule_permissions(ctx):
    """Fix schedule channel permissions to be accessible only to bot, Master Lee's Family, and Family Member roles.
    
    This command corrects schedule channel permissions if they were improperly set.
    """
    if ctx.author.id != ADMIN_USER_ID:
        await ctx.send("❌ Only the configured admin can run this command.")
        return
    
    guild = ctx.guild
    
    # Check if we're in the right server
    if guild.id != GUILD_ID:
        await ctx.send("❌ This command must be run in the configured server.")
        return
    
    await ctx.send("🔄 Fixing schedule channel permissions...")
    
    try:
        # Find the schedule channel
        schedule_channel = discord.utils.get(guild.channels, name="schedule")
        if not schedule_channel:
            await ctx.send("❌ Schedule channel not found!")
            return
        
        # Find required roles
        master_role = discord.utils.get(guild.roles, name="Master Lee's Family")
        family_role = discord.utils.get(guild.roles, name="Family Member")
        
        if not master_role:
            await ctx.send("❌ 'Master Lee's Family' role not found!")
            return
        
        if not family_role:
            await ctx.send("❌ 'Family Member' role not found!")
            return
        
        # Update schedule channel permissions
        await schedule_channel.set_permissions(guild.default_role,
            read_messages=False,
            send_messages=False,
            view_channel=False
        )
        
        # Allow bot to access the channel
        await schedule_channel.set_permissions(guild.me,
            read_messages=True,
            send_messages=True,
            manage_messages=True,
            view_channel=True,
            read_message_history=True
        )
        
        # Allow Master Lee's Family role
        await schedule_channel.set_permissions(master_role,
            read_messages=True,
            send_messages=True,
            view_channel=True,
            read_message_history=True,
            embed_links=True,
            attach_files=True
        )
        
        # Allow Family Member role
        await schedule_channel.set_permissions(family_role,
            read_messages=True,
            send_messages=True,
            view_channel=True,
            read_message_history=True,
            embed_links=True,
            attach_files=True
        )
        
        # Update config with schedule channel ID if not already present
        created_ids['SCHEDULE_CHANNEL_ID'] = str(schedule_channel.id)
        await update_config_file()
        
        await ctx.send("✅ **Schedule channel permissions fixed!** Now accessible only to:\n"
                      f"• The bot (ID: {guild.me.id})\n"
                      f"• Master Lee's Family role (ID: {master_role.id})\n"
                      f"• Family Member role (ID: {family_role.id})")
        
        # Send confirmation to log channel if it exists
        log_channel_id = config.get('LOG_CHANNEL_ID')
        if log_channel_id and log_channel_id != '0':
            try:
                log_channel = guild.get_channel(int(log_channel_id))
                if log_channel:
                    embed = discord.Embed(
                        title="🔧 Schedule Channel Permissions Fixed",
                        description="The schedule channel has been made accessible only to bot, Master Lee's Family, and Family Member roles.",
                        color=discord.Color.green(),
                        timestamp=discord.utils.utcnow()
                    )
                    embed.add_field(name="Channel", value=f"#{schedule_channel.name} (ID: {schedule_channel.id})", inline=True)
                    embed.add_field(name="Fixed By", value=ctx.author.mention, inline=True)
                    embed.add_field(name="Accessible to", value=f"Bot, Master Lee's Family, Family Member", inline=False)
                    await log_channel.send(embed=embed)
            except:
                pass
                
    except Exception as e:
        await ctx.send(f"❌ Error fixing schedule channel permissions: {str(e)}")

@bot.command(name="fix_bot_category")
@commands.has_permissions(administrator=True)
@is_command_channel()
async def fix_bot_category(ctx):
    """Fix BOT category to be visible only to admin user.
    
    This command corrects BOT category permissions if they were improperly set.
    Removes access from the Master Lee's Family role and ensures only admin can access.
    """
    if ctx.author.id != ADMIN_USER_ID:
        await ctx.send("❌ Only the configured admin can run this command.")
        return
    
    guild = ctx.guild
    
    # Check if we're in the right server
    if guild.id != GUILD_ID:
        await ctx.send("❌ This command must be run in the configured server.")
        return
    
    await ctx.send("🔄 Fixing BOT category permissions...")
    
    try:
        # Find the BOT category
        bot_category = discord.utils.get(guild.categories, name="🤖 BOT")
        if not bot_category:
            await ctx.send("❌ BOT category not found!")
            return
        
        # Find the admin user
        admin_user = guild.get_member(ADMIN_USER_ID)
        if not admin_user:
            await ctx.send("❌ Admin user not found in the server!")
            return
        
        # Set category permissions
        await bot_category.set_permissions(guild.default_role,
            view_channel=False,
            read_messages=False
        )
        
        # Remove any role-based permissions (especially Master Lee's Family role)
        admin_role = discord.utils.get(guild.roles, name="Master Lee's Family")
        if admin_role:
            # Remove role permissions by setting them to None
            await bot_category.set_permissions(admin_role, overwrite=None)
        
        # Set permissions for admin user
        await bot_category.set_permissions(admin_user,
            view_channel=True,
            read_messages=True,
            manage_channels=True,
            manage_permissions=True
        )
        
        # Ensure bot has access
        await bot_category.set_permissions(guild.me,
            view_channel=True,
            read_messages=True,
            manage_channels=True,
            manage_permissions=True
        )
        
        # Fix permissions for all channels in the BOT category
        for channel in bot_category.channels:
            # Remove @everyone permissions
            await channel.set_permissions(guild.default_role,
                read_messages=False,
                send_messages=False
            )
            
            # Remove any role-based permissions
            if admin_role:
                await channel.set_permissions(admin_role, overwrite=None)
            
            # Set permissions for admin user
            await channel.set_permissions(admin_user,
                read_messages=True,
                send_messages=True,
                manage_messages=True,
                read_message_history=True
            )
            
            # Ensure bot has access
            await channel.set_permissions(guild.me,
                read_messages=True,
                send_messages=True,
                manage_messages=True,
                read_message_history=True
            )
        
        await ctx.send(f"✅ **BOT category fixed!** Now visible only to admin user ({admin_user.mention}) and the bot.")
        
        # Send confirmation to log channel if it exists
        log_channel_id = config.get('LOG_CHANNEL_ID')
        if log_channel_id and log_channel_id != '0':
            try:
                log_channel = guild.get_channel(int(log_channel_id))
                if log_channel:
                    embed = discord.Embed(
                        title="🔧 BOT Category Fixed",
                        description=f"The BOT category has been made visible only to admin user.",
                        color=discord.Color.green(),
                        timestamp=discord.utils.utcnow()
                    )
                    embed.add_field(name="Fixed By", value=ctx.author.mention, inline=True)
                    embed.add_field(name="Admin User", value=admin_user.mention, inline=True)
                    await log_channel.send(embed=embed)
            except:
                pass
                
    except Exception as e:
        await ctx.send(f"❌ Error fixing BOT category: {str(e)}")

@bot.command(name="get_invite")
@commands.has_permissions(administrator=True)
@is_command_channel()
async def get_invite(ctx):
    """Generate a bot invite link with proper permissions.
    
    Creates an OAuth2 invite URL with Administrator permissions for easy bot re-invitation.
    """
    if ctx.author.id != ADMIN_USER_ID:
        await ctx.send("❌ Only the configured admin can run this command.")
        return
    
    # Create invite with proper permissions
    permissions = discord.Permissions()
    permissions.administrator = True  # Recommended for setup
    
    invite_url = discord.utils.oauth_url(
        bot.user.id,
        permissions=permissions,
        scopes=["bot", "applications.commands"]
    )
    
    embed = discord.Embed(
        title="🤖 Bot Invite Link",
        description="Use this link to re-invite the bot with proper permissions:",
        color=discord.Color.blue()
    )
    embed.add_field(
        name="Invite URL",
        value=f"[Click here to invite bot]({invite_url})",
        inline=False
    )
    embed.add_field(
        name="Instructions",
        value="1. Use this link to re-invite the bot\n"
              "2. Make sure to check 'Administrator' permission\n"
              "3. After inviting, run `!setup_check` again",
        inline=False
    )
    
    await ctx.send(embed=embed)
    
    # Also send to DM for convenience
    try:
        dm = await ctx.author.create_dm()
        await dm.send(f"Bot invite link: {invite_url}")
        await ctx.send("✅ Also sent invite link to your DMs.")
    except:
        pass

@bot.command(name="reset_setup")
@commands.has_permissions(administrator=True)
@is_command_channel()
async def reset_setup(ctx):
    """Reset server setup by deleting all created channels, categories, and roles.
    
    This command removes all elements created by the setup bot and clears config IDs.
    Requires explicit confirmation before proceeding.
    After reset, !setup_server can be run again.
    """
    if ctx.author.id != ADMIN_USER_ID:
        await ctx.send("❌ Only the configured admin can run this command.")
        return
    
    # Confirmation
    embed = discord.Embed(
        title="⚠️ Reset Server Setup",
        description="**WARNING:** This will delete all categories, channels, and roles created by the setup bot!\n\n"
                   "**This will allow you to run `!setup_server` again.**\n\n"
                   "This action cannot be undone!\n\n"
                   "Type `CONFIRM RESET` to proceed.",
        color=discord.Color.red()
    )
    
    await ctx.send(embed=embed)
    
    def check(msg):
        return msg.author == ctx.author and msg.channel == ctx.channel and msg.content == "CONFIRM RESET"
    
    try:
        await bot.wait_for('message', timeout=30.0, check=check)
    except:
        await ctx.send("❌ Reset cancelled (timeout).")
        return
    
    await ctx.send("🔄 Starting reset... This may take a moment.")
    
    guild = ctx.guild
    
    try:
        # Delete categories (in reverse order to avoid hierarchy issues)
        categories_to_delete = [
            "👋 WELCOME", "📅 SCHEDULE", "🔒 PRIVATE CONVERSATIONS",
            "📢 ANNOUNCEMENTS", "💭 TEXT CHANNELS", "🤖 BOT"
        ]
        
        for category_name in categories_to_delete:
            category = discord.utils.get(guild.categories, name=category_name)
            if category:
                # Delete all channels in category first
                for channel in category.channels:
                    try:
                        await channel.delete(reason="Reset setup")
                    except:
                        pass
                # Delete category
                try:
                    await category.delete(reason="Reset setup")
                    await ctx.send(f"🗑️ Deleted category: {category_name}")
                except:
                    pass
        
        # Delete roles (except @everyone)
        roles_to_delete = ["Master Lee's Family", "Family Member", "National Team", "Demonstration Team", "Student", "Instructor"]

        for role_name in roles_to_delete:
            role = discord.utils.get(guild.roles, name=role_name)
            if role and not role.is_default():
                try:
                    await role.delete(reason="Reset setup")
                    await ctx.send(f"🗑️ Deleted role: {role_name}")
                except:
                    pass
        
        # Clear config file IDs (but keep token and admin ID)
        config_to_clear = [
            'RULES_CHANNEL_ID', 'FAMILY_ROLE_ID', 'RULES_MESSAGE_ID',
            'NATIONAL_TEAM_ROLE_ID', 'DEMONSTRATION_TEAM_ROLE_ID',
            'NATIONAL_TEAM_CHANNEL_ID', 'DEMONSTRATION_TEAM_CHANNEL_ID',
            'GENERAL_CHAT_CHANNEL_ID', 'MASTER_LEE_FAMILY_ROLE_ID',
            'STUDENT_ROLE_ID', 'INSTRUCTOR_ROLE_ID',
            'TEMPORARY_CHANNELS_CATEGORY_ID', 'ADMIN_CHAT_CHANNEL_ID',
            'LOG_CHANNEL_ID', 'SCHEDULE_CHANNEL_ID', 'COMMAND_CHANNEL_ID',
            'GENERAL_ANNOUNCEMENT_CHANNEL_ID', 'WELCOME_CHANNEL_ID',
            'BOT_USER_ID', 'WELCOME_CATEGORY_ID', 'SCHEDULE_CATEGORY_ID',
            'PRIVATE_CONVERSATION_CATEGORY_ID', 'ANNOUNCEMENTS_CATEGORY_ID',
            'TEXT_CHANNELS_CATEGORY_ID', 'BOT_CATEGORY_ID'
        ]
        
        try:
            # Read current config
            current_config = {}
            try:
                with open('config.txt', 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            current_config[key.strip()] = value.strip()
            except FileNotFoundError:
                pass
            
            # Clear the specified keys
            for key in config_to_clear:
                current_config[key] = '0'
            
            # Update created_ids with cleared values
            for key in config_to_clear:
                created_ids[key] = '0'
            
            # Reset setup_completed flag
            globals()['setup_completed'] = False
            
            # Update the config file
            await update_config_file()
            
            await ctx.send("🗑️ Cleared config file IDs")
        except Exception as e:
            await ctx.send(f"⚠️ Could not clear config file: {e}")
        
        embed = discord.Embed(
            title="✅ Reset Complete!",
            description="All setup elements have been deleted and config has been cleared.\n\n"
                       "**You can now run `!setup_server` again.**\n\n"
                       "⚠️ Remember: `!setup_server` can only be run **once** per setup!",
            color=discord.Color.green()
        )
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error during reset: {str(e)}")
        print(f"❌ Reset error: {e}")

# ============================================================================
# BOT EXECUTION
# ============================================================================

if __name__ == "__main__":
    """Main execution block for the setup bot.
    
    Displays startup information and command overview before starting the bot.
    """
    print("\n🔧 Starting Server Setup Bot...")
    print("=" * 50)
    print("Commands:")
    print("  !setup_server          - Full server setup (can be used anywhere) [ONE-TIME ONLY]")
    print("  !setup_check           - Check current setup and permissions")
    print("  !cleanup_unrecorded    - Remove everything not in config.txt")
    print("  !fix_schedule_permissions - Fix schedule channel permissions")
    print("  !fix_bot_category      - Fix BOT category to be admin-only")
    print("  !get_invite           - Get bot invite link with proper permissions")
    print("  !reset_setup          - Reset setup (delete everything) [Allows !setup_server again]")
    print("=" * 50)
    print("\n🔐 IMPORTANT COMMAND RESTRICTIONS:")
    print("  • !setup_server can be used anywhere by admin (ONE-TIME ONLY)")
    print("  • All other commands MUST be used in the command channel")
    print("=" * 50)
    print("\n⚠️  ONE-TIME SETUP RESTRICTION:")
    print("  • !setup_server can only be run ONCE per server setup")
    print("  • To run it again, use !reset_setup first")
    print("  • The bot checks for existing setup elements before allowing setup")
    print("=" * 50)
    print("\n⚠️  IMPORTANT: The bot needs Administrator permission to set up the server.")
    print("   Run !setup_server first to create the server structure.")
    print("=" * 50)
    
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

