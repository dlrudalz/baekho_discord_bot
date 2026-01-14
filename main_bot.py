"""
DISCORD BOT: Family Registration & Private Chat Management System
===============================================================
A comprehensive Discord bot for managing family registrations, private conversations,
and server administration with role management and automated workflows.

Features:
- Multi-step registration via DM with name validation and role assignment
- Private chat creation with permanent admin delete buttons
- Automated message forwarding from monitored channels
- Role-based access control and team management
- Comprehensive logging and administrative commands

Author: Baekho Bot System
Version: 2.0.0
"""

# =============================================================================
# IMPORTS AND DEPENDENCIES
# =============================================================================

import discord
from discord.ext import commands, tasks
import os
import json
import asyncio
from typing import Dict, Optional, List, Tuple
from datetime import datetime, timedelta, timezone
import time

# =============================================================================
# CONFIGURATION MANAGEMENT
# =============================================================================

# Read bot configuration from config.txt file
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

# Extract configuration values with type conversion
# Core bot settings
TOKEN = config.get('TOKEN')
GUILD_ID = int(config.get('GUILD_ID', '0'))

# Role and channel IDs
RULES_CHANNEL_ID = int(config.get('RULES_CHANNEL_ID', '0'))
FAMILY_ROLE_ID = int(config.get('FAMILY_ROLE_ID', '0'))
RULES_MESSAGE_ID = int(config.get('RULES_MESSAGE_ID', '0'))
NATIONAL_TEAM_ROLE_ID = int(config.get('NATIONAL_TEAM_ROLE_ID', '0'))
DEMONSTRATION_TEAM_ROLE_ID = int(config.get('DEMONSTRATION_TEAM_ROLE_ID', '0'))
NATIONAL_TEAM_CHANNEL_ID = int(config.get('NATIONAL_TEAM_CHANNEL_ID', '0'))
DEMONSTRATION_TEAM_CHANNEL_ID = int(config.get('DEMONSTRATION_TEAM_CHANNEL_ID', '0'))
GENERAL_CHAT_CHANNEL_ID = int(config.get('GENERAL_CHAT_CHANNEL_ID', '0'))
MASTER_LEE_FAMILY_ROLE_ID = int(config.get('MASTER_LEE_FAMILY_ROLE_ID', '0'))
STUDENT_ROLE_ID = int(config.get('STUDENT_ROLE_ID', '0'))
INSTRUCTOR_ROLE_ID = int(config.get('INSTRUCTOR_ROLE_ID', '0'))
ADMIN_USER_ID = int(config.get('ADMIN_USER_ID', '0'))

# Private conversation category ID (already set up by setup program)
PRIVATE_CONVERSATION_CATEGORY_ID = int(config.get('PRIVATE_CONVERSATION_CATEGORY_ID', '0'))

# Command and logging channels
BOT_COMMAND_CHANNEL_ID = int(config.get('BOT_COMMAND_CHANNEL_ID', '0'))
LOG_CHANNEL_ID = int(config.get('LOG_CHANNEL_ID', '0'))

# =============================================================================
# CONFIGURATION VALIDATION AND DISPLAY
# =============================================================================

print("=" * 50)
print("📋 CONFIGURATION STATUS:")
print(f"   Token: {'✅' if TOKEN and TOKEN != 'your_bot_token_here' else '❌'}")
print(f"   Guild ID: {GUILD_ID}")
print(f"   Rules Channel ID: {RULES_CHANNEL_ID}")
print(f"   Family Role ID: {FAMILY_ROLE_ID}")
print(f"   Rules Message ID: {RULES_MESSAGE_ID}")
print(f"   National Team Role ID: {NATIONAL_TEAM_ROLE_ID}")
print(f"   Demonstration Team Role ID: {DEMONSTRATION_TEAM_ROLE_ID}")
print(f"   National Team Channel ID: {NATIONAL_TEAM_CHANNEL_ID}")
print(f"   Demonstration Team Channel ID: {DEMONSTRATION_TEAM_CHANNEL_ID}")
print(f"   Master Lee's Family Role ID: {MASTER_LEE_FAMILY_ROLE_ID}")
print(f"   Student Role ID: {STUDENT_ROLE_ID}")
print(f"   Instructor Role ID: {INSTRUCTOR_ROLE_ID}")
print(f"   General Chat Channel ID: {GENERAL_CHAT_CHANNEL_ID}")
print(f"   Admin User ID: {ADMIN_USER_ID}")
print(f"   Private Conversation Category ID: {PRIVATE_CONVERSATION_CATEGORY_ID}")
print(f"   Bot Command Channel ID: {BOT_COMMAND_CHANNEL_ID}")
print(f"   Log Channel ID: {LOG_CHANNEL_ID}")
print("=" * 50)

# Validate critical configuration
if not TOKEN or TOKEN == 'your_bot_token_here':
    print("❌ ERROR: Bot token not configured. Please set TOKEN in config.txt")
    exit(1)

# =============================================================================
# DISCORD BOT SETUP
# =============================================================================

# Configure Discord intents for required functionality
intents = discord.Intents.default()
intents.members = True      # Required for member tracking
intents.message_content = True  # Required for message reading
intents.reactions = True    # Required for reaction handling

# Initialize processing lock for thread safety
processing_lock = asyncio.Lock()

# Create bot instance with command prefix
bot = commands.Bot(command_prefix="!", intents=intents)

# =============================================================================
# GLOBAL DATA STORES
# =============================================================================

# User registration states
user_states: Dict[int, Dict] = {}

# Registered users persistent storage
REGISTRY_FILE = 'registered_users.json'

# Active conversation tracking
active_conversations: Dict[int, Dict] = {}  # user_id -> {admin_id, channel_id, channel_type}
message_references: Dict[int, int] = {}      # admin_message_id -> user_id

# Private channel management
private_channels: Dict[int, Dict] = {}    # channel_id -> {user_id, created_at, last_activity, delete_button_message_id, pinned_message_id}
user_private_channels: Dict[int, int] = {}  # user_id -> channel_id

# Monitored channels (where messages trigger private chat creation)
MONITORED_CHANNELS = []
if GENERAL_CHAT_CHANNEL_ID:
    MONITORED_CHANNELS.append(GENERAL_CHAT_CHANNEL_ID)

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def load_registered_users() -> Dict:
    """Load registered users from JSON file with error handling."""
    try:
        with open(REGISTRY_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_registered_users(users: Dict) -> None:
    """Save registered users to JSON file with pretty formatting."""
    with open(REGISTRY_FILE, 'w') as f:
        json.dump(users, f, indent=2)

# Initialize registered users from storage
registered_users = load_registered_users()

# =============================================================================
# NAME VALIDATION AND FORMATTING UTILITIES
# =============================================================================

def clean_name(name: str) -> str:
    """
    Clean and properly format a name string.
    
    Handles:
    - Extra whitespace removal
    - Proper capitalization (including special cases like McDonald, O'Brien)
    - Hyphenated names (Smith-Jones)
    
    Args:
        name: Raw name input string
        
    Returns:
        Properly formatted name string
    """
    if not name:
        return ""
    
    # Normalize whitespace
    cleaned = ' '.join(name.strip().split())
    
    # Capitalize with special case handling
    parts = cleaned.split()
    capitalized_parts = []
    
    for part in parts:
        if '-' in part:
            # Handle hyphenated names
            subparts = part.split('-')
            capitalized_subparts = [sub.capitalize() for sub in subparts]
            capitalized_parts.append('-'.join(capitalized_subparts))
        elif part.startswith("Mc") and len(part) > 2:
            # Handle "Mc" prefix names
            capitalized_parts.append("Mc" + part[2:].capitalize())
        elif part.startswith("Mac") and len(part) > 3:
            # Handle "Mac" prefix names
            capitalized_parts.append("Mac" + part[3:].capitalize())
        elif "'" in part:
            # Handle apostrophe names (O'Brien)
            apostrophe_idx = part.find("'")
            if apostrophe_idx > 0:
                capitalized_parts.append(
                    part[:apostrophe_idx].capitalize() + 
                    "'" + part[apostrophe_idx + 1:].capitalize()
                )
            else:
                capitalized_parts.append(part.capitalize())
        else:
            capitalized_parts.append(part.capitalize())
    
    return ' '.join(capitalized_parts)

def validate_name_format(name: str) -> Tuple[bool, str]:
    """
    Validate name format against business rules.
    
    Validation rules:
    - Minimum 2 characters, maximum 50 characters
    - Must contain both first and last name
    - Only allowed characters: letters, spaces, hyphens, apostrophes, periods
    - Each name part must be at least 2 letters
    
    Args:
        name: Name string to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not name:
        return False, "❌ Please enter a name."
    
    # Length validation
    if len(name) < 2:
        return False, "❌ Name must be at least 2 characters long."
    if len(name) > 50:
        return False, "❌ Name cannot exceed 50 characters."
    
    # Character validation
    if not all(c.isalpha() or c.isspace() or c in "-'." for c in name):
        return False, "❌ Name can only contain letters, spaces, hyphens (-), apostrophes ('), and periods (.)"
    
    # Require at least first and last name
    parts = name.split()
    if len(parts) < 2:
        return False, "❌ Please enter both first and last name (e.g., 'John Smith')."
    
    # Validate each name part
    for i, part in enumerate(parts):
        if not part.strip("-.'"):  # Check if part is empty or just special chars
            return False, "❌ Each name part must contain letters."
        if len(part.strip("-.'")) < 2:
            return False, f"❌ Each name part must be at least 2 letters long. '{part}' is too short."
    
    # Prevent excessive name parts (likely error)
    if len(parts) > 4:
        return False, "❌ Too many name parts detected. Please enter just first and last name."
    
    return True, ""

# =============================================================================
# LOGGING SYSTEM
# =============================================================================

async def send_to_log_channel(guild: discord.Guild, message: str, embed: discord.Embed = None) -> bool:
    """
    Send notification to configured log channel with fallback to admin DM.
    
    Args:
        guild: Discord guild object
        message: Text message to send
        embed: Optional embed to send
        
    Returns:
        True if sent to log channel, False if sent to admin DM
    """
    if LOG_CHANNEL_ID:
        try:
            log_channel = guild.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                if embed:
                    await log_channel.send(embed=embed)
                else:
                    await log_channel.send(message)
                return True
            else:
                print(f"⚠️ Log channel not found: {LOG_CHANNEL_ID}")
        except Exception as e:
            print(f"❌ Error sending to log channel: {e}")
    
    # Fallback: Send to admin DM if log channel fails
    try:
        admin_user = guild.get_member(ADMIN_USER_ID)
        if admin_user:
            admin_dm = await admin_user.create_dm()
            if embed:
                await admin_dm.send(embed=embed)
            else:
                await admin_dm.send(message)
    except Exception as e:
        print(f"❌ Error sending to admin DM: {e}")
    
    return False

# =============================================================================
# GENERAL CHAT MUTE SYSTEM
# =============================================================================
async def ensure_general_chat_mute_message(guild: discord.Guild) -> None:
    """
    Check if the general-chat channel has the permanent mute instruction message.
    Only checks and adds missing reactions - DOES NOT CREATE NEW MESSAGES.
    
    setup.py is responsible for creating the initial message.
    """
    general_chat = guild.get_channel(GENERAL_CHAT_CHANNEL_ID)
    if not general_chat:
        print("❌ General chat channel not found")
        return
    
    try:
        # Check existing pinned messages
        pinned_messages = await general_chat.pins()
        
        # Look for our mute instruction message
        mute_message_found = None
        for pinned_msg in pinned_messages:
            if pinned_msg.author == bot.user and pinned_msg.embeds:
                for embed in pinned_msg.embeds:
                    # Look for the message created by setup.py
                    if embed.title and "How to Access & Use General-Chat" in embed.title:
                        mute_message_found = pinned_msg
                        break
            if mute_message_found:
                break
        
        # If message exists, just ensure it has the reaction
        if mute_message_found:
            # Check if it has the reaction
            has_reaction = False
            for reaction in mute_message_found.reactions:
                if str(reaction.emoji) == '🔇':
                    has_reaction = True
                    break
            
            if not has_reaction:
                await mute_message_found.add_reaction('🔇')
                print(f"✅ Added missing 🔇 reaction to existing mute instruction message in #{general_chat.name}")
            else:
                print(f"✅ Mute instruction message found with reaction in #{general_chat.name}")
        else:
            # Message doesn't exist - setup.py should have created it
            print("⚠️ Mute instruction message not found. Run !setup_server to create it.")
            
    except Exception as e:
        print(f"❌ Error checking mute instruction message: {e}")

# =============================================================================
# COMMAND ACCESS CONTROL
# =============================================================================

def bot_channel_only():
    """
    Decorator to restrict commands to bot command channel.
    
    Ensures commands only work in the designated bot command channel
    and only for the admin user.
    """
    async def predicate(ctx):
        # Channel restriction
        if ctx.channel.id != BOT_COMMAND_CHANNEL_ID:
            if ctx.author.id == ADMIN_USER_ID:
                await ctx.send(f"❌ Manual commands can only be used in <#{BOT_COMMAND_CHANNEL_ID}>", ephemeral=True)
            return False
        
        # Admin authorization
        return ctx.author.id == ADMIN_USER_ID
    
    return commands.check(predicate)

# =============================================================================
# REGISTRATION VIEW CLASSES
# =============================================================================
class FinalConfirmationView(discord.ui.View):
    """
    Final confirmation view before registration completion.
    
    Allows users to review all entered information and make
    changes if needed before final submission.
    """
    
    def __init__(self, user_id: int, child_name: str, role: str, role_display: str, teams_selected: list):
        super().__init__(timeout=300)  # 5 minute timeout
        self.user_id = user_id
        self.child_name = child_name
        self.role = role
        self.role_display = role_display
        self.teams_selected = teams_selected
        
        # Format teams for display
        if self.teams_selected:
            team_list = []
            if "national" in self.teams_selected:
                team_list.append("National Team 🔴")
            if "demonstration" in self.teams_selected:
                team_list.append("Demonstration Team 🔵")
            self.teams_text = ", ".join(team_list)
        else:
            self.teams_text = "No teams selected"
    
    @discord.ui.button(label="✅ Yes, Everything Looks Good!", style=discord.ButtonStyle.green, emoji="✅", row=0)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle final confirmation and complete registration."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This confirmation is not for you.", ephemeral=True)
            return
        
        # Update user state
        if self.user_id in user_states:
            user_states[self.user_id]['waiting_for_final_confirmation'] = False
        
        # Disable buttons
        for child in self.children:
            child.disabled = True
        
        await interaction.response.edit_message(content="✅ **Registration confirmed!** Completing registration...", view=self)
        
        # Complete registration process
        await asyncio.sleep(1.5)
        
        guild = bot.get_guild(GUILD_ID)
        member = guild.get_member(self.user_id) if guild else None
        
        if member:
            await complete_registration(interaction.user, member)
        else:
            await interaction.followup.send("❌ Could not find you in the server. Please try again.", ephemeral=True)
    
    @discord.ui.button(label="✏️ Change Name", style=discord.ButtonStyle.secondary, emoji="📝", row=1)
    async def change_name_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Return to name entry step."""
        await self.go_back_to_step(interaction, "name", "Step 1: Child's Name")
    
    @discord.ui.button(label="👤 Change Role", style=discord.ButtonStyle.secondary, emoji="👤", row=1)
    async def change_role_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Return to role selection step."""
        await self.go_back_to_step(interaction, "role", "Step 2: Role Selection")
    
    @discord.ui.button(label="🎯 Change Teams", style=discord.ButtonStyle.secondary, emoji="🎯", row=1)
    async def change_teams_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Return to team selection step."""
        await self.go_back_to_step(interaction, "teams", "Step 3: Team Selection")
    
    async def go_back_to_step(self, interaction: discord.Interaction, step: str, step_name: str) -> None:
        """
        Navigate back to a specific registration step.
        
        Args:
            interaction: Discord interaction object
            step: Step identifier ('name', 'role', 'teams')
            step_name: Display name for the step
        """
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This confirmation is not for you.", ephemeral=True)
            return
        
        # Preserve current data for restoration
        if self.user_id in user_states:
            current_data = {
                'child_name': user_states[self.user_id].get('child_name'),
                'gender': user_states[self.user_id].get('gender'),
                'role_display': user_states[self.user_id].get('role_display'),
                'teams_selected': user_states[self.user_id].get('teams_selected', []).copy(),
            }
            
            # Set modification flags
            user_states[self.user_id]['modifying_from_final'] = True
            user_states[self.user_id]['preserved_data'] = current_data
            user_states[self.user_id]['modifying_step'] = step
            
            # Clear data for the specific step being modified
            if step == "name":
                user_states[self.user_id]['waiting_for_name'] = True
                user_states[self.user_id]['waiting_for_name_confirmation'] = False
                user_states[self.user_id]['child_name'] = None
                user_states[self.user_id]['child_name_original'] = None
                user_states[self.user_id]['child_name_cleaned'] = None
            elif step == "role":
                user_states[self.user_id]['waiting_for_role'] = True
                user_states[self.user_id]['waiting_for_role_confirmation'] = False
                user_states[self.user_id]['gender'] = None
                user_states[self.user_id]['role_display'] = None
            elif step == "teams":
                user_states[self.user_id]['waiting_for_teams'] = True
                user_states[self.user_id]['waiting_for_teams_confirmation'] = False
                user_states[self.user_id]['teams_selected'] = []
            
            user_states[self.user_id]['waiting_for_final_confirmation'] = False
            user_states[self.user_id]['waiting_for_mute'] = False
        
        # Disable buttons
        for child in self.children:
            child.disabled = True
        
        await interaction.response.edit_message(
            content=f"🔄 **Going back to {step_name}**...",
            view=self
        )
        
        # Send appropriate step message
        await asyncio.sleep(1.5)
        dm_channel = await interaction.user.create_dm()
        
        if step == "name":
            embed = discord.Embed(
                title="Step 1: Child's Name",
                description="Please type your child's **FIRST and LAST NAME** again (e.g., 'John Smith'):",
                color=discord.Color.blue()
            )
            tips_text = (
                "💡 **Name Entry Tips**\n"
                "**Remember to:**\n"
                "• Include both first and last name\n"
                "• Use proper spacing\n"
                "• Example: 'Michael Johnson'"
            )
            embed.add_field(name="Instructions", value=tips_text, inline=False)
            await dm_channel.send(embed=embed)
            
        elif step == "role":
            preserved_name = user_states[self.user_id]['preserved_data']['child_name'] if 'preserved_data' in user_states[self.user_id] else self.child_name
            embed = discord.Embed(
                title="Step 2: Select Your Role",
                description=f"Are you the mother, father, grandmother, or grandfather of **{preserved_name}**?\n\n"
                          "Please select your role below:",
                color=discord.Color.green()
            )
            view = RoleSelectView(self.user_id, preserved_name)
            await dm_channel.send(embed=embed, view=view)
            
        elif step == "teams":
            preserved_name = user_states[self.user_id]['preserved_data']['child_name'] if 'preserved_data' in user_states[self.user_id] else self.child_name
            preserved_role = user_states[self.user_id]['preserved_data']['gender'] if 'preserved_data' in user_states[self.user_id] else self.role
            
            embed = discord.Embed(
                title="Step 3: Team Selection",
                description="Which team(s) is your child currently in?\n\n"
                        "**THIS IS FOR ANNOUNCEMENT PURPOSES ONLY**.\n\n"
                        "🔴 **National Team**\n"
                        "🔵 **Demonstration Team**\n\n"
                        "You can select one, both, or none.\n"
                        "Click **✅ Done** when finished.",
                color=discord.Color.blue()
            )
            view = TeamSelectView(self.user_id, preserved_name, preserved_role)
            await dm_channel.send(embed=embed, view=view)
        
        print(f"👤 {interaction.user.name} went back to {step} step from final confirmation")

# =============================================================================
# STEP-SPECIFIC VIEW CLASSES
# =============================================================================
class NameConfirmationView(discord.ui.View):
    """View for confirming or changing the entered child's name."""
    
    def __init__(self, user_id: int, cleaned_name: str, original_input: str):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.cleaned_name = cleaned_name
        self.original_input = original_input
    
    @discord.ui.button(label="✅ Yes, This is Correct", style=discord.ButtonStyle.green, emoji="✅", row=0)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirm the entered name and proceed."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This confirmation is not for you.", ephemeral=True)
            return
        
        # Check if modifying from final confirmation
        modifying_from_final = False
        preserved_data = None
        
        if self.user_id in user_states:
            modifying_from_final = user_states[self.user_id].get('modifying_from_final', False)
            preserved_data = user_states[self.user_id].get('preserved_data', {})
        
        # Update user state
        if self.user_id in user_states:
            user_states[self.user_id]['child_name'] = self.cleaned_name
            user_states[self.user_id]['waiting_for_name'] = False
            user_states[self.user_id]['waiting_for_name_confirmation'] = False
            
            if modifying_from_final:
                # Return to final confirmation with updated data
                user_states[self.user_id]['modifying_from_final'] = False
                user_states[self.user_id]['waiting_for_final_confirmation'] = True
                
                for child in self.children:
                    child.disabled = True
                
                await interaction.response.edit_message(content=f"✅ **Name updated:** {self.cleaned_name}", view=self)
                
                # Return to final confirmation
                await asyncio.sleep(1.5)
                await self.return_to_final_confirmation(interaction.user, preserved_data)
                return
        
        # Normal flow: proceed to role selection
        user_states[self.user_id]['waiting_for_role'] = True
        
        for child in self.children:
            child.disabled = True
        
        await interaction.response.edit_message(
            content=f"✅ **Step 1 Complete**\n**Name confirmed:** {self.cleaned_name}", 
            view=self
        )
        
        # Move to role selection
        await asyncio.sleep(1.5)
        await self.send_role_selection(interaction.user, self.cleaned_name)
    
    async def return_to_final_confirmation(self, user: discord.User, preserved_data: Dict) -> None:
        """Return user to final confirmation view with preserved data."""
        dm_channel = await user.create_dm()
        
        # Extract data for final confirmation
        child_name = self.cleaned_name
        role = preserved_data.get('gender', user_states[self.user_id].get('gender'))
        role_display = preserved_data.get('role_display', user_states[self.user_id].get('role_display'))
        teams_selected = preserved_data.get('teams_selected', user_states[self.user_id].get('teams_selected', []))
        
        # Create final confirmation embed
        final_embed = discord.Embed(
            title="🔍 Final Confirmation",
            description="**Please review your information below:**\n\n"
                      "If everything looks good, click **✅ Yes, Everything Looks Good!**\n"
                      "If you need to change something, use the appropriate button below.",
            color=discord.Color.gold()
        )
        
        # Add formatted user information
        role_emoji = self.get_role_emoji(role)
        teams_text = self.format_teams_text(teams_selected)
        
        final_embed.add_field(name="📝 Child's Name", value=f"```{child_name}```", inline=False)
        final_embed.add_field(name=f"{role_emoji} Your Role", value=f"```{role_display}```", inline=False)
        final_embed.add_field(name="🎯 Selected Teams", value=f"```{teams_text}```", inline=False)
        final_embed.set_footer(text="Take a moment to review before confirming!")
        
        # Send final confirmation view
        view = FinalConfirmationView(self.user_id, child_name, role, role_display, teams_selected)
        await dm_channel.send(embed=final_embed, view=view)
        
        print(f"👤 {user.name} updated name and returned to final confirmation")
    
    async def send_role_selection(self, user: discord.User, child_name: str) -> None:
        """Send role selection view to user."""
        dm_channel = await user.create_dm()
        embed = discord.Embed(
            title="Step 2: Select Your Role",
            description=f"Are you the mother, father, grandmother, or grandfather of **{child_name}**?\n\n"
                      "Please select your role below:",
            color=discord.Color.green()
        )
        
        view = RoleSelectView(self.user_id, child_name)
        await dm_channel.send(embed=embed, view=view)
        
        print(f"👤 {user.name} confirmed name and moved to role selection")
    
    def get_role_emoji(self, role: str) -> str:
        """Get appropriate emoji for role."""
        emoji_map = {
            "mother": "👩",
            "father": "👨", 
            "grandmother": "👵",
            "grandfather": "👴"
        }
        return emoji_map.get(role, "👤")
    
    def format_teams_text(self, teams_selected: List[str]) -> str:
        """Format teams list for display."""
        if not teams_selected:
            return "No teams selected"
        
        team_list = []
        if "national" in teams_selected:
            team_list.append("National Team 🔴")
        if "demonstration" in teams_selected:
            team_list.append("Demonstration Team 🔵")
        return ", ".join(team_list)
    
    @discord.ui.button(label="✏️ No, I Need to Fix It", style=discord.ButtonStyle.gray, emoji="✏️", row=1)
    async def fix_it_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Allow user to re-enter the name."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This confirmation is not for you.", ephemeral=True)
            return
        
        # Reset name entry state
        if self.user_id in user_states:
            user_states[self.user_id]['waiting_for_name'] = True
            user_states[self.user_id]['waiting_for_name_confirmation'] = False
            user_states[self.user_id]['child_name_original'] = None
            user_states[self.user_id]['child_name_cleaned'] = None
        
        # Clear confirmation message and restart
        await interaction.response.defer(ephemeral=True)
        
        try:
            await interaction.delete_original_response()
            print(f"🗑️ Deleted name confirmation message for {interaction.user.name}")
        except Exception as e:
            print(f"⚠️ Could not delete message: {e}")
            try:
                await interaction.edit_original_response(content="🔄 Let's try that again...", embed=None, view=None)
            except:
                pass
        
        # Send new name entry instructions
        dm_channel = await interaction.user.create_dm()
        embed = discord.Embed(
            title="Step 1: Child's Name",
            description="Please type your child's **FIRST and LAST NAME** again (e.g., 'John Smith'):",
            color=discord.Color.blue()
        )
        
        tips_text = (
            "💡 **Name Entry Tips**\n"
            "**Remember to:**\n"
            "• Include both first and last name\n"
            "• Use proper spacing\n"
            "• Example: 'Michael Johnson'"
        )
        embed.add_field(name="Instructions", value=tips_text, inline=False)
        
        await dm_channel.send(embed=embed)
        
        print(f"👤 {interaction.user.name} chose to fix the name")

class RoleSelectView(discord.ui.View):
    """View for selecting family role (mother, father, grandmother, grandfather, student)."""
    
    def __init__(self, user_id: int, child_name: str):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.child_name = child_name
    
    @discord.ui.button(label="👩 Mother", style=discord.ButtonStyle.blurple, emoji="👩", row=0)
    async def mother_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_role_selection(interaction, "mother", "👩 Mother")
    
    @discord.ui.button(label="👨 Father", style=discord.ButtonStyle.blurple, emoji="👨", row=0)
    async def father_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_role_selection(interaction, "father", "👨 Father")
    
    @discord.ui.button(label="👵 Grandmother", style=discord.ButtonStyle.blurple, emoji="👵", row=1)
    async def grandmother_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_role_selection(interaction, "grandmother", "👵 Grandmother")
    
    @discord.ui.button(label="👴 Grandfather", style=discord.ButtonStyle.blurple, emoji="👴", row=1)
    async def grandfather_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_role_selection(interaction, "grandfather", "👴 Grandfather")
    
    @discord.ui.button(label="🎓 Student", style=discord.ButtonStyle.blurple, emoji="🎓", row=2)
    async def student_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_role_selection(interaction, "student", "🎓 Student")
    
    async def handle_role_selection(self, interaction: discord.Interaction, role: str, role_display: str) -> None:
        """Process role selection and show confirmation."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This selection is not for you.", ephemeral=True)
            return
        
        # Check if modifying from final confirmation
        modifying_from_final = False
        if self.user_id in user_states:
            modifying_from_final = user_states[self.user_id].get('modifying_from_final', False)
        
        # Update user state
        if self.user_id in user_states:
            user_states[self.user_id]['gender'] = role
            user_states[self.user_id]['role_display'] = role_display
            user_states[self.user_id]['waiting_for_role'] = False
            user_states[self.user_id]['waiting_for_role_confirmation'] = True
        
        # Disable buttons and show confirmation
        for child in self.children:
            child.disabled = True
        
        embed = discord.Embed(
            title="✅ Role Selected",
            description=f"You selected: **{role_display}**\n\n"
                      f"**Is this correct?**",
            color=discord.Color.gold()
        )
        
        confirmation_view = RoleConfirmationView(self.user_id, self.child_name, role, role_display, modifying_from_final)
        await interaction.response.edit_message(embed=embed, view=confirmation_view)
        
        print(f"👤 {interaction.user.name} selected role: {role_display}")

class RoleConfirmationView(discord.ui.View):
    """View for confirming selected family role."""
    
    def __init__(self, user_id: int, child_name: str, role: str, role_display: str, modifying_from_final: bool = False):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.child_name = child_name
        self.role = role
        self.role_display = role_display
        self.modifying_from_final = modifying_from_final
    
    @discord.ui.button(label="✅ Yes, This is Correct", style=discord.ButtonStyle.green, emoji="✅", row=0)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirm role selection and proceed."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This confirmation is not for you.", ephemeral=True)
            return
        
        # Update user state based on flow
        if self.user_id in user_states:
            user_states[self.user_id]['waiting_for_role_confirmation'] = False
            
            if self.modifying_from_final:
                user_states[self.user_id]['waiting_for_final_confirmation'] = True
                user_states[self.user_id]['modifying_from_final'] = False
            else:
                user_states[self.user_id]['waiting_for_teams'] = True
        
        # Disable buttons
        for child in self.children:
            child.disabled = True
        
        if self.modifying_from_final:
            await self.handle_modification_flow(interaction)
        else:
            await self.handle_normal_flow(interaction)
    
    async def handle_modification_flow(self, interaction: discord.Interaction) -> None:
        """Handle role confirmation when modifying from final step."""
        await interaction.response.edit_message(
            content=f"✅ **Role updated:** {self.role_display}",
            embed=None,
            view=self
        )
        
        # Return to final confirmation
        await asyncio.sleep(1.5)
        dm_channel = await interaction.user.create_dm()
        
        # Get user data for final confirmation
        user_data = user_states.get(self.user_id, {})
        child_name = user_data.get('child_name', 'Unknown')
        teams_selected = user_data.get('teams_selected', [])
        
        # Create and send final confirmation
        final_embed = self.create_final_confirmation_embed(child_name, teams_selected)
        view = FinalConfirmationView(self.user_id, child_name, self.role, self.role_display, teams_selected)
        await dm_channel.send(embed=final_embed, view=view)
        
        print(f"👤 {interaction.user.name} confirmed role and returned to final confirmation")
    
    async def handle_normal_flow(self, interaction: discord.Interaction) -> None:
        """Handle role confirmation in normal registration flow."""
        await interaction.response.edit_message(
            content=f"✅ **Step 2 Complete**\n**Role confirmed:** {self.role_display}",
            embed=None,
            view=self
        )
        
        # Proceed to team selection
        await asyncio.sleep(1.5)
        dm_channel = await interaction.user.create_dm()
        
        team_embed = discord.Embed(
            title="Step 3: Team Selection",
            description="Which team(s) is your child currently in?\n\n"
                    "**THIS IS FOR ANNOUNCEMENT PURPOSES ONLY**.\n\n"
                    "🔴 **National Team**\n"
                    "🔵 **Demonstration Team**\n\n"
                    "You can select one, both, or none.\n"
                    "Click **✅ Done** when finished.",
            color=discord.Color.blue()
        )
        
        view = TeamSelectView(self.user_id, self.child_name, self.role)
        await dm_channel.send(embed=team_embed, view=view)
        
        print(f"👤 {interaction.user.name} confirmed role: {self.role_display}")
    
    def create_final_confirmation_embed(self, child_name: str, teams_selected: List[str]) -> discord.Embed:
        """Create final confirmation embed with user data."""
        embed = discord.Embed(
            title="🔍 Final Registration Confirmation",
            description="**Please review your information below:**\n\n"
                      "If everything looks good, click **✅ Yes, Everything Looks Good!**\n"
                      "If you need to change something, use the appropriate button below.",
            color=discord.Color.gold()
        )
        
        role_emoji = self.get_role_emoji(self.role)
        teams_text = self.format_teams_text(teams_selected)
        
        embed.add_field(name="📝 Child's Name", value=f"```{child_name}```", inline=False)
        embed.add_field(name=f"{role_emoji} Your Role", value=f"```{self.role_display}```", inline=False)
        embed.add_field(name="🎯 Selected Teams", value=f"```{teams_text}```", inline=False)
        embed.set_footer(text="Take a moment to review before confirming!")
        
        return embed
    
    def get_role_emoji(self, role: str) -> str:
        """Get appropriate emoji for role."""
        emoji_map = {
            "mother": "👩",
            "father": "👨",
            "grandmother": "👵", 
            "grandfather": "👴"
        }
        return emoji_map.get(role, "👤")
    
    def format_teams_text(self, teams_selected: List[str]) -> str:
        """Format teams list for display."""
        if not teams_selected:
            return "No teams selected"
        
        team_list = []
        if "national" in teams_selected:
            team_list.append("National Team 🔴")
        if "demonstration" in teams_selected:
            team_list.append("Demonstration Team 🔵")
        return ", ".join(team_list)
    
    @discord.ui.button(label="✏️ No, I Need to Fix It", style=discord.ButtonStyle.gray, emoji="✏️", row=1)
    async def fix_it_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Allow user to re-select role."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This confirmation is not for you.", ephemeral=True)
            return
        
        # Reset role selection state
        if self.user_id in user_states:
            user_states[self.user_id]['waiting_for_role_confirmation'] = False
            user_states[self.user_id]['waiting_for_role'] = True
            user_states[self.user_id]['gender'] = None
            user_states[self.user_id]['role_display'] = None
        
        # Disable buttons and restart role selection
        for child in self.children:
            child.disabled = True
        
        await interaction.response.edit_message(
            content="🔄 Let's select your role again...",
            embed=None,
            view=self
        )
        
        # Send role selection again
        await asyncio.sleep(1.5)
        dm_channel = await interaction.user.create_dm()
        
        embed = discord.Embed(
            title="Step 2: Select Your Role",
            description=f"Are you the mother, father, grandmother, or grandfather of **{self.child_name}**?\n\n"
                      "Please select your role below:",
            color=discord.Color.green()
        )
        
        view = RoleSelectView(self.user_id, self.child_name)
        await dm_channel.send(embed=embed, view=view)

class TeamSelectView(discord.ui.View):
    """View for selecting team memberships with multi-select capability."""
    
    def __init__(self, user_id: int, child_name: str, role: str):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.child_name = child_name
        self.role = role
        self.selected_teams = set()  # Track selected teams
    
    @discord.ui.button(label="National Team", style=discord.ButtonStyle.gray, emoji="🔴", row=0)
    async def national_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Toggle National Team selection."""
        await self.toggle_team(interaction, button, "national", "National Team")
    
    @discord.ui.button(label="Demonstration Team", style=discord.ButtonStyle.gray, emoji="🔵", row=0)
    async def demonstration_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Toggle Demonstration Team selection."""
        await self.toggle_team(interaction, button, "demonstration", "Demonstration Team")
    
    @discord.ui.button(label="✅ Done", style=discord.ButtonStyle.green, emoji="✅", row=1)
    async def done_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Finalize team selections and show confirmation."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This selection is not for you.", ephemeral=True)
            return
        
        # Check if modifying from final confirmation
        modifying_from_final = False
        if self.user_id in user_states:
            modifying_from_final = user_states[self.user_id].get('modifying_from_final', False)
        
        # Update user state with selected teams
        if self.user_id in user_states:
            user_states[self.user_id]['teams_selected'] = list(self.selected_teams)
            user_states[self.user_id]['waiting_for_teams'] = False
            user_states[self.user_id]['waiting_for_teams_confirmation'] = True
        
        # Disable buttons and show confirmation
        for child in self.children:
            child.disabled = True
        
        # Format teams for display
        teams_text = self.format_teams_text()
        
        embed = discord.Embed(
            title="✅ Teams Selected",
            description=f"You selected: **{teams_text}**\n\n"
                      f"**Is this correct?**",
            color=discord.Color.gold()
        )
        
        confirmation_view = TeamConfirmationView(
            self.user_id,
            self.child_name,
            self.role,
            list(self.selected_teams),
            modifying_from_final
        )
        
        await interaction.response.edit_message(embed=embed, view=confirmation_view)
        
        print(f"👤 {interaction.user.name} selected teams: {teams_text}")
    
    async def toggle_team(self, interaction: discord.Interaction, button: discord.ui.Button, team: str, team_display: str) -> None:
        """Toggle team selection state."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This selection is not for you.", ephemeral=True)
            return
        
        # Toggle team in selection set
        if team in self.selected_teams:
            self.selected_teams.remove(team)
            button.style = discord.ButtonStyle.gray
            button.label = team_display
            print(f"👤 {interaction.user.name} deselected {team_display}")
        else:
            self.selected_teams.add(team)
            button.style = discord.ButtonStyle.green
            button.label = f"✓ {team_display}"
            print(f"👤 {interaction.user.name} selected {team_display}")
        
        # Update button appearance
        await interaction.response.edit_message(view=self)
    
    def format_teams_text(self) -> str:
        """Format selected teams for display."""
        if not self.selected_teams:
            return "No teams selected"
        
        team_list = []
        if "national" in self.selected_teams:
            team_list.append("National Team 🔴")
        if "demonstration" in self.selected_teams:
            team_list.append("Demonstration Team 🔵")
        return ", ".join(team_list)

class TeamConfirmationView(discord.ui.View):
    """View for confirming selected team memberships."""
    
    def __init__(self, user_id: int, child_name: str, role: str, teams_selected: list, modifying_from_final: bool = False):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.child_name = child_name
        self.role = role
        self.teams_selected = teams_selected
        self.modifying_from_final = modifying_from_final
        self.teams_text = self.format_teams_text(teams_selected)
    
    @discord.ui.button(label="✅ Yes, This is Correct", style=discord.ButtonStyle.green, emoji="✅", row=0)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirm team selections and proceed."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This confirmation is not for you.", ephemeral=True)
            return
        
        # Update user state based on flow
        if self.user_id in user_states:
            user_states[self.user_id]['waiting_for_teams_confirmation'] = False
            
            if self.modifying_from_final:
                user_states[self.user_id]['waiting_for_final_confirmation'] = True
                user_states[self.user_id]['modifying_from_final'] = False
            else:
                user_states[self.user_id]['waiting_for_final_confirmation'] = True
        
        # Disable buttons
        for child in self.children:
            child.disabled = True
        
        if self.modifying_from_final:
            await self.handle_modification_flow(interaction)
        else:
            await self.handle_normal_flow(interaction)
    
    async def handle_modification_flow(self, interaction: discord.Interaction) -> None:
        """Handle team confirmation when modifying from final step."""
        await interaction.response.edit_message(
            content=f"✅ **Teams updated:** {self.teams_text}",
            embed=None,
            view=self
        )
        
        # Return to final confirmation
        await asyncio.sleep(1.5)
        await self.return_to_final_confirmation(interaction.user)
    
    async def handle_normal_flow(self, interaction: discord.Interaction) -> None:
        """Handle team confirmation in normal registration flow."""
        await interaction.response.edit_message(
            content=f"✅ **Step 3 Complete**\n**Teams confirmed:** {self.teams_text}",
            embed=None,
            view=self
        )
        
        # Proceed to final confirmation
        await asyncio.sleep(1.5)
        await self.send_final_confirmation(interaction.user)
    
    async def return_to_final_confirmation(self, user: discord.User) -> None:
        """Return to final confirmation view after modification."""
        dm_channel = await user.create_dm()
        
        # Get user data for final confirmation
        user_data = user_states.get(self.user_id, {})
        child_name = user_data.get('child_name', 'Unknown')
        role_display = user_data.get('role_display', 'Unknown')
        
        # Create and send final confirmation
        final_embed = self.create_final_confirmation_embed(child_name, role_display)
        view = FinalConfirmationView(self.user_id, child_name, self.role, role_display, self.teams_selected)
        await dm_channel.send(embed=final_embed, view=view)
        
        print(f"👤 {user.name} updated teams and returned to final confirmation")
    
    async def send_final_confirmation(self, user: discord.User) -> None:
        """Send final confirmation view in normal flow."""
        dm_channel = await user.create_dm()
        
        # Get user data for final confirmation
        user_data = user_states.get(self.user_id, {})
        child_name = user_data.get('child_name', 'Unknown')
        role_display = user_data.get('role_display', 'Unknown')
        
        # Create and send final confirmation
        final_embed = self.create_final_confirmation_embed(child_name, role_display)
        view = FinalConfirmationView(self.user_id, child_name, self.role, role_display, self.teams_selected)
        await dm_channel.send(embed=final_embed, view=view)
        
        print(f"👤 {user.name} confirmed teams, moving to final confirmation")
    
    def create_final_confirmation_embed(self, child_name: str, role_display: str) -> discord.Embed:
        """Create final confirmation embed with user data."""
        embed = discord.Embed(
            title="🔍 Final Registration Confirmation",
            description="**Please review your information below:**\n\n"
                      "If everything looks good, click **✅ Yes, Everything Looks Good!**\n"
                      "If you need to change something, use the appropriate button below.",
            color=discord.Color.gold()
        )
        
        role_emoji = self.get_role_emoji(self.role)
        
        embed.add_field(name="📝 Child's Name", value=f"```{child_name}```", inline=False)
        embed.add_field(name=f"{role_emoji} Your Role", value=f"```{role_display}```", inline=False)
        embed.add_field(name="🎯 Selected Teams", value=f"```{self.teams_text}```", inline=False)
        embed.set_footer(text="Take a moment to review before confirming!")
        
        return embed
    
    def get_role_emoji(self, role: str) -> str:
        """Get appropriate emoji for role."""
        emoji_map = {
            "mother": "👩",
            "father": "👨",
            "grandmother": "👵",
            "grandfather": "👴"
        }
        return emoji_map.get(role, "👤")
    
    def format_teams_text(self, teams_selected: List[str]) -> str:
        """Format teams list for display."""
        if not teams_selected:
            return "No teams selected"
        
        team_list = []
        if "national" in teams_selected:
            team_list.append("National Team 🔴")
        if "demonstration" in teams_selected:
            team_list.append("Demonstration Team 🔵")
        return ", ".join(team_list)
    
    @discord.ui.button(label="✏️ No, I Need to Fix It", style=discord.ButtonStyle.gray, emoji="✏️", row=1)
    async def fix_it_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Allow user to re-select teams."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This confirmation is not for you.", ephemeral=True)
            return
        
        # Reset team selection state
        if self.user_id in user_states:
            user_states[self.user_id]['waiting_for_teams_confirmation'] = False
            user_states[self.user_id]['waiting_for_teams'] = True
            user_states[self.user_id]['teams_selected'] = []
        
        # Disable buttons and restart team selection
        for child in self.children:
            child.disabled = True
        
        await interaction.response.edit_message(
            content="🔄 Let's select teams again...",
            embed=None,
            view=self
        )
        
        # Send team selection again
        await asyncio.sleep(1.5)
        dm_channel = await interaction.user.create_dm()
        
        team_embed = discord.Embed(
            title="Step 3: Team Selection",
            description="Which team(s) is your child currently in?\n\n"
                    "**THIS IS FOR ANNOUNCEMENT PURPOSES ONLY**.\n\n"
                    "🔴 **National Team**\n"
                    "🔵 **Demonstration Team**\n\n"
                    "You can select one, both, or none.\n"
                    "Click **✅ Done** when finished.",
            color=discord.Color.blue()
        )
        
        view = TeamSelectView(self.user_id, self.child_name, self.role)
        await dm_channel.send(embed=team_embed, view=view)

# =============================================================================
# PRIVATE CHANNEL MANAGEMENT CLASSES
# =============================================================================
class PermanentDeleteChannelView(discord.ui.View):
    """
    Permanent delete button view pinned at top of private chats.
    
    Provides admin-only button to delete private chat channels.
    This view has no timeout and remains available indefinitely.
    """
    
    def __init__(self, channel_id: int, user_id: int):
        super().__init__(timeout=None)  # Permanent view
        self.channel_id = channel_id
        self.user_id = user_id
    
    @discord.ui.button(label="🗑️ Delete Private Chat", style=discord.ButtonStyle.danger, custom_id="delete_private_channel")
    async def delete_channel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle delete channel request - admin only."""
        # Admin authorization check
        if interaction.user.id != ADMIN_USER_ID:
            await interaction.response.send_message(
                "❌ Only the admin can delete this private chat channel.",
                ephemeral=True
            )
            return
        
        channel = interaction.guild.get_channel(self.channel_id)
        if not channel:
            await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
            return
        
        # Get user info for confirmation message
        user = interaction.guild.get_member(self.user_id)
        
        # Create deletion confirmation embed
        embed = discord.Embed(
            title="🗑️ Confirm Channel Deletion",
            description=f"Are you sure you want to delete this private chat with {user.mention if user else 'Unknown User'}?\n\n"
                       f"**Channel:** #{channel.name}\n"
                       f"**User:** {user.mention if user else 'Unknown'} ({self.user_id})\n\n"
                       f"**This action cannot be undone!** All messages will be permanently deleted.",
            color=discord.Color.red()
        )
        
        # Show confirmation view
        view = ConfirmDeleteView(channel.id, self.user_id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        
        print(f"🔄 Admin requested deletion for channel #{channel.name}")

class ConfirmDeleteView(discord.ui.View):
    """Confirmation view for channel deletion with timeout protection."""
    
    def __init__(self, channel_id: int, user_id: int):
        super().__init__(timeout=60)  # 1 minute timeout
        self.channel_id = channel_id
        self.user_id = user_id
        self.confirmed = False
    
    @discord.ui.button(label="✅ Confirm Delete", style=discord.ButtonStyle.danger)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirm and execute channel deletion."""
        if interaction.user.id != ADMIN_USER_ID:
            # Try to notify via DM since channel might be deleted
            try:
                admin_dm = await interaction.user.create_dm()
                await admin_dm.send("❌ Only admin can delete this channel.")
            except:
                pass
            return
        
        self.confirmed = True
        self.stop()
        
        channel = interaction.guild.get_channel(self.channel_id)
        if not channel:
            # Channel already deleted
            try:
                admin_dm = await interaction.user.create_dm()
                await admin_dm.send("❌ Channel not found.")
            except:
                pass
            return
        
        try:
            # Get channel info before deletion for logging
            channel_name = channel.name
            user = interaction.guild.get_member(self.user_id)
            
            # Send immediate response before deletion
            await interaction.response.send_message(
                "🗑️ Deleting channel...",
                ephemeral=True
            )
            
            # Brief delay to ensure response is sent
            await asyncio.sleep(0.5)
            
            # Delete the channel
            await channel.delete(reason="Private chat deleted by admin")
            
            # Clean up tracking data
            if self.channel_id in private_channels:
                if self.user_id in user_private_channels:
                    del user_private_channels[self.user_id]
                del private_channels[self.channel_id]
            
            # Log deletion to log channel
            embed = discord.Embed(
                title="🗑️ Private Chat Deleted",
                description=f"**Channel:** #{channel_name}\n"
                          f"**User:** {user.mention if user else 'Unknown'} ({self.user_id})\n"
                          f"**By:** {interaction.user.mention}",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            await send_to_log_channel(interaction.guild, "", embed)
            
            print(f"🗑️ Private channel deleted by admin for user: {user.name if user else 'Unknown'}")
            
        except Exception as e:
            print(f"❌ Error in confirm_button: {e}")
            
            # Error handling with fallback notification methods
            try:
                admin_dm = await interaction.user.create_dm()
                await admin_dm.send(f"❌ Error deleting channel: {e}")
            except:
                try:
                    await interaction.edit_original_response(
                        content=f"❌ Error deleting channel: {e}"
                    )
                except:
                    print(f"❌ Could not send error message to user: {e}")
    
    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel the deletion operation."""
        if interaction.user.id != ADMIN_USER_ID:
            await interaction.response.send_message("❌ Only admin can cancel this action.", ephemeral=True)
            return
        
        self.confirmed = False
        self.stop()
        
        await interaction.response.edit_message(content="✅ Deletion cancelled.", embed=None, view=None)

# =============================================================================
# PRIVATE CHANNEL FUNCTIONS
# =============================================================================
async def create_private_channel(guild: discord.Guild, user: discord.Member, original_channel_name: str) -> Optional[discord.TextChannel]:
    """
    Create a private channel for user communication in the existing category.
    
    Features:
    - Unique private channel per user
    - Permanent delete button pinned at top (admin only)
    - Proper permission configuration
    - Activity tracking
    
    Args:
        guild: Discord guild object
        user: Member to create channel for
        original_channel_name: Source channel name for context
        
    Returns:
        Created text channel or None on error
    """
    try:
        # Check for existing channel for this user
        if user.id in user_private_channels:
            channel_id = user_private_channels[user.id]
            channel = guild.get_channel(channel_id)
            if channel:
                # Update activity timestamp
                private_channels[channel_id]['last_activity'] = time.time()
                return channel
        
        # Get private conversation category from config
        if not PRIVATE_CONVERSATION_CATEGORY_ID:
            print("❌ PRIVATE_CONVERSATION_CATEGORY_ID not configured in config.txt")
            return None
        
        category = guild.get_channel(PRIVATE_CONVERSATION_CATEGORY_ID)
        if not category:
            print(f"❌ Private conversation category not found with ID: {PRIVATE_CONVERSATION_CATEGORY_ID}")
            print("   Please ensure setup program has run and category exists")
            return None
        
        # Configure channel permissions
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False, read_message_history=False),
            user: discord.PermissionOverwrite(
                read_messages=True, 
                send_messages=True, 
                read_message_history=True,
                attach_files=True,
                embed_links=True
            ),
            guild.get_member(ADMIN_USER_ID): discord.PermissionOverwrite(
                read_messages=True, 
                send_messages=True, 
                read_message_history=True,
                manage_channels=True,
                manage_messages=True,
                manage_permissions=True
            ),
            guild.me: discord.PermissionOverwrite(
                read_messages=True, 
                send_messages=True, 
                read_message_history=True,
                manage_channels=True,
                manage_messages=True,
                manage_permissions=True
            )
        }
        
        # Create sanitized channel name
        channel_name = f"private-{user.display_name.lower().replace(' ', '-')[:20]}"
        channel = await category.create_text_channel(
            name=channel_name,
            overwrites=overwrites,
            reason=f"Private conversation for {user.name}",
            topic=f"Private conversation with {user.name} | From: {original_channel_name}"
        )
        
        # Store channel metadata
        current_time = time.time()
        private_channels[channel.id] = {
            'user_id': user.id,
            'created_at': current_time,
            'last_activity': current_time,
            'pinned_message_id': None,  # Set after creating pinned message
            'original_channel': original_channel_name,
            'user_name': user.name
        }
        user_private_channels[user.id] = channel.id
        
        # Create and pin permanent delete button
        delete_view = PermanentDeleteChannelView(channel.id, user.id)
        delete_embed = discord.Embed(
            title="🗑️ Admin Delete Button",
            description="This button is permanently available for admin to delete this private chat.\n\n"
                       "**Only the admin can use this button.**",
            color=discord.Color.red()
        )
        
        delete_message = await channel.send(embed=delete_embed, view=delete_view)
        await delete_message.pin()
        private_channels[channel.id]['pinned_message_id'] = delete_message.id
        
        # Send welcome message
        welcome_msg = await channel.send(
            f"🔒 Private conversation for {user.mention}\n"
            f"Messages from #{original_channel_name} will appear here.\n"
            f"Only you and admin can see this channel.\n\n"
            f"**Admin can delete this chat at any time using the pinned button above.**"
        )
        
        # Log channel creation
        embed = discord.Embed(
            title="🔔 New Private Chat Created",
            description=f"**User:** {user.mention} ({user.id})\n"
                      f"**From:** #{original_channel_name}\n"
                      f"**Channel:** #{channel.name}\n"
                      f"**Created:** <t:{int(current_time)}:R>\n\n"
                      f"A permanent delete button is pinned at the top (admin only).",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        await send_to_log_channel(guild, "", embed)
        
        print(f"🔒 Created private chat for {user.name} with permanent delete button")
        return channel
        
    except Exception as e:
        print(f"❌ Error creating private chat: {e}")
        return None

async def cleanup_user_data(user_id: int) -> None:
    """
    Clean up all data associated with a user when they leave.
    
    Removes:
    - Registration data
    - User state tracking
    - Active conversations
    - Private chat references
    
    Args:
        user_id: Discord user ID to clean up
    """
    user_id_str = str(user_id)
    
    # Remove from registered users
    if user_id_str in registered_users:
        del registered_users[user_id_str]
        save_registered_users(registered_users)
        print(f"🗑️ Deleted registration data for user ID {user_id}")
    
    # Remove from user states
    if user_id in user_states:
        del user_states[user_id]
        print(f"🗑️ Removed user state for user ID {user_id}")
    
    # Remove from active conversations
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
    
    # Remove private chat reference
    if user_id in user_private_channels:
        channel_id = user_private_channels[user_id]
        if channel_id in private_channels:
            del private_channels[channel_id]
        del user_private_channels[user_id]
        print(f"🗑️ Removed private chat reference for user ID {user_id}")

# =============================================================================
# EVENT HANDLERS
# =============================================================================
@bot.event
async def on_ready():
    """Bot startup initialization and system verification."""
    print(f'✅ {bot.user} is online!')
    print(f'🆔 Bot ID: {bot.user.id}')
    print(f'👥 Connected to {len(bot.guilds)} server(s)')
    
    guild = bot.get_guild(GUILD_ID)
    if guild:
        print(f'🏠 Server: {guild.name} (ID: {guild.id})')
        
        # Only check for existing messages, don't create new ones
        await ensure_general_chat_mute_message(guild)  # Now just checks, doesn't create
        
        # Verify monitored channels
        print("\n📢 MONITORED CHANNELS (messages will create private chats):")
        for channel_id in MONITORED_CHANNELS:
            channel = guild.get_channel(channel_id)
            if channel:
                print(f'   ✅ #{channel.name} (ID: {channel.id})')
            else:
                print(f'   ❌ Channel not found! ID: {channel_id}')
        
        # Verify admin user
        admin_user = guild.get_member(ADMIN_USER_ID)
        if admin_user:
            print(f'👑 Admin: {admin_user.name}#{admin_user.discriminator} (ID: {admin_user.id})')
        else:
            print(f'⚠️ Admin user not found! ID: {ADMIN_USER_ID}')
        
        # Verify Master Lee's Family role
        master_lee_family_role = guild.get_role(MASTER_LEE_FAMILY_ROLE_ID)
        if master_lee_family_role:
            print(f'👑 Master Lee\'s Family Role: {master_lee_family_role.name} (ID: {master_lee_family_role.id})')
            print(f'   👥 Members with this role: {len(master_lee_family_role.members)}')
        else:
            print(f'⚠️ Master Lee\'s Family role not found! ID: {MASTER_LEE_FAMILY_ROLE_ID}')

       # Verify Student role
        student_role = guild.get_role(STUDENT_ROLE_ID)
        if student_role:
            print(f'🎓 Student Role: {student_role.name} (ID: {student_role.id})')
        else:
            print(f'⚠️ Student role not found! ID: {STUDENT_ROLE_ID}')

        # Verify Instructor role
        instructor_role = guild.get_role(INSTRUCTOR_ROLE_ID)
        if instructor_role:
            print(f'👨‍🏫 Instructor Role: {instructor_role.name} (ID: {instructor_role.id})')
        else:
            print(f'⚠️ Instructor role not found! ID: {INSTRUCTOR_ROLE_ID}')
        
        # Verify rules channel
        rules_channel = guild.get_channel(RULES_CHANNEL_ID)
        if rules_channel:
            print(f'\n📜 Rules Channel: #{rules_channel.name} (ID: {rules_channel.id})')
        else:
            print(f'❌ Rules channel not found! ID: {RULES_CHANNEL_ID}')
        
        # Verify family role
        family_role = guild.get_role(FAMILY_ROLE_ID)
        if family_role:
            print(f'👪 Family Role: {family_role.name} (ID: {family_role.id})')
        else:
            print(f'❌ Family role not found! ID: {FAMILY_ROLE_ID}')
        
        # Verify team roles
        national_role = guild.get_role(NATIONAL_TEAM_ROLE_ID)
        if national_role:
            print(f'🔴 National Team Role: {national_role.name} (ID: {national_role.id})')
        else:
            print(f"⚠️ National Team role not found! ID: {NATIONAL_TEAM_ROLE_ID}")
            
        demonstration_role = guild.get_role(DEMONSTRATION_TEAM_ROLE_ID)
        if demonstration_role:
            print(f'🔵 Demonstration Team Role: {demonstration_role.name} (ID: {demonstration_role.id})')
        else:
            print(f'⚠️ Demonstration Team role not found! ID: {DEMONSTRATION_TEAM_ROLE_ID}')
        
        # Verify private conversation category
        if PRIVATE_CONVERSATION_CATEGORY_ID:
            private_category = guild.get_channel(PRIVATE_CONVERSATION_CATEGORY_ID)
            if private_category:
                print(f'📁 Private Conversation Category: #{private_category.name} (ID: {private_category.id})')
            else:
                print(f'⚠️ Private conversation category not found! ID: {PRIVATE_CONVERSATION_CATEGORY_ID}')
                print('   Please ensure setup program has run to create the category')
        
        # Verify bot command channel
        if BOT_COMMAND_CHANNEL_ID:
            bot_channel = guild.get_channel(BOT_COMMAND_CHANNEL_ID)
            if bot_channel:
                print(f'💬 Bot Command Channel: #{bot_channel.name} (ID: {BOT_COMMAND_CHANNEL_ID})')
            else:
                print(f'⚠️ Bot command channel not found! ID: {BOT_COMMAND_CHANNEL_ID}')
        else:
            print(f'⚠️ Bot command channel not configured!')
        
        # Verify log channel
        if LOG_CHANNEL_ID:
            log_channel = guild.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                print(f'📋 Log Channel: #{log_channel.name} (ID: {LOG_CHANNEL_ID})')
            else:
                print(f'⚠️ Log channel not found! ID: {LOG_CHANNEL_ID}')
        else:
            print(f'⚠️ Log channel not configured! Notifications will be sent to admin DM')
        
        # Validate green check mark consistency
        print("\n🔍 Verifying green check marks for registered users...")
        await verify_green_check_consistency(guild, rules_channel)
    
    # Set bot status
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching,
        name="for messages to forward"
    ))

async def verify_green_check_consistency(guild: discord.Guild, rules_channel: Optional[discord.TextChannel]) -> None:
    """
    Verify consistency between registry and green check marks.
    
    Ensures:
    - Registered users have green check marks
    - Users with green check marks are properly registered
    - Master Lee's Family members are handled appropriately
    """
    if not rules_channel:
        return
    
    try:
        rules_message = await rules_channel.fetch_message(RULES_MESSAGE_ID)
        
        # Get users with green check reactions
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
                    # Check for Master Lee's Family role exemption
                    master_lee_family_role = guild.get_role(MASTER_LEE_FAMILY_ROLE_ID)
                    has_master_lee_family = master_lee_family_role and master_lee_family_role in member.roles
                    
                    if has_master_lee_family:
                        print(f"   ✅ {member.name} has Master Lee's Family role, skipping warning")
                        continue
                    
                    # Check if they have family role (completed registration)
                    family_role = guild.get_role(FAMILY_ROLE_ID)
                    has_family_role = family_role and family_role in member.roles
                    
                    if has_family_role:
                        print(f"   ℹ️ {member.name} has family role but not in registry, adding to registry...")
                        # Auto-add to registry with basic info
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

@bot.event
async def on_member_join(member: discord.Member):
    """Handle new member joining the server with logging."""
    print(f"👤 Member joined: {member.name} (ID: {member.id})")
    
    # Log member join event
    embed = discord.Embed(
        title="👤 Member Joined",
        description=f"**User:** {member.mention} ({member.id})\n"
                   f"**Name:** {member.name}\n"
                   f"**Joined:** <t:{int(time.time())}:R>",
        color=discord.Color.green(),
        timestamp=datetime.now(timezone.utc)
    )
    await send_to_log_channel(member.guild, "", embed)

@bot.event
async def on_member_remove(member: discord.Member):
    """
    Handle member leaving the server with comprehensive cleanup.
    
    Performs:
    - Data removal from all tracking systems
    - Private chat deletion
    - Green check mark reaction removal
    - Logging
    """
    user_id = member.id
    user_id_str = str(user_id)
    
    print(f"👤 Member left: {member.name} (ID: {user_id})")
    
    # Log member leave event
    embed = discord.Embed(
        title="👤 Member Left",
        description=f"**User:** {member.mention} ({member.id})\n"
                   f"**Name:** {member.name}\n"
                   f"**Left:** <t:{int(time.time())}:R>",
        color=discord.Color.orange(),
        timestamp=datetime.now(timezone.utc)
    )
    await send_to_log_channel(member.guild, "", embed)
    
    # Comprehensive data cleanup
    await cleanup_user_data(user_id)
    
    # Remove green check mark reaction
    await remove_green_check_reaction(member)
    
    print(f"✅ Cleanup complete for {member.name}")

async def remove_green_check_reaction(member: discord.Member) -> None:
    """Remove green check mark reaction from rules message when member leaves."""
    try:
        guild = bot.get_guild(GUILD_ID)
        if guild:
            rules_channel = guild.get_channel(RULES_CHANNEL_ID)
            if rules_channel:
                rules_message = await rules_channel.fetch_message(RULES_MESSAGE_ID)
                
                # Find and remove green check reaction
                for reaction in rules_message.reactions:
                    if str(reaction.emoji) == '✅':
                        async for user in reaction.users():
                            if user.id == member.id:
                                await reaction.remove(user)
                                print(f"✅ Removed green check mark reaction for {member.name}")
                                break
    except discord.NotFound:
        print("⚠️ Rules message not found, cannot remove reaction")
    except discord.Forbidden:
        print("❌ No permission to remove reaction from rules message")
    except Exception as e:
        print(f"⚠️ Error removing reaction: {e}")

@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    """
    Prevent unauthorized removal of green check marks.
    
    Business rules:
    - Registered users cannot remove their green check
    - Master Lee's Family members can remove theirs
    - Non-registered users can remove theirs
    """
    # Ignore bot reactions
    if payload.user_id == bot.user.id:
        return
    
    # Check if this is the rules channel green check removal
    if (payload.channel_id == RULES_CHANNEL_ID and 
        payload.message_id == RULES_MESSAGE_ID and 
        str(payload.emoji) == '✅'):
        
        guild = bot.get_guild(payload.guild_id)
        if guild:
            member = guild.get_member(payload.user_id)
            if member and not member.bot:
                # Check for Master Lee's Family role exemption
                master_lee_family_role = guild.get_role(MASTER_LEE_FAMILY_ROLE_ID)
                has_master_lee_family = master_lee_family_role and master_lee_family_role in member.roles
                
                if has_master_lee_family:
                    print(f"✅ User {member.name} has Master Lee's Family role, allowing reaction removal")
                    return
                
                # Check registration status
                is_registered = str(member.id) in registered_users
                has_family_role = False
                family_role = guild.get_role(FAMILY_ROLE_ID)
                if family_role:
                    has_family_role = family_role in member.roles
                
                # Re-add reaction for registered users
                if is_registered or has_family_role:
                    await re_add_green_check_reaction(guild, member)
                else:
                    print(f"ℹ️ User {member.name} is not registered, allowing reaction removal")
    
    # Handle mute instruction reaction removal
    elif payload.channel_id == GENERAL_CHAT_CHANNEL_ID:
        guild = bot.get_guild(payload.guild_id)
        if guild:
            channel = guild.get_channel(payload.channel_id)
            if channel:
                try:
                    message = await channel.fetch_message(payload.message_id)
                    # Check if this is our mute instruction message
                    if message.author == bot.user and message.embeds:
                        for embed in message.embeds:
                            if embed.title and "How to Access" in embed.title:
                                # This is the mute instruction message
                                member = guild.get_member(payload.user_id)
                                if member and not member.bot:
                                    # Check if user has Family Member role
                                    family_role = guild.get_role(FAMILY_ROLE_ID)
                                    if family_role and family_role in member.roles:
                                        # User has Family Member role, so they should still have view access
                                        # Remove send permission but keep view access
                                        await channel.set_permissions(member, overwrite=None)
                                        
                                        # Re-add permissions with send_messages disabled
                                        await channel.set_permissions(
                                            member,
                                            read_messages=True,
                                            send_messages=False,  # Disable sending
                                            view_channel=True,
                                            read_message_history=True,
                                            reason="User removed mute reaction"
                                        )
                                        print(f"❌ Removed send permission from {member.name} for removing mute reaction")
                                    else:
                                        # User doesn't have Family Member role, remove all permissions
                                        await channel.set_permissions(member, overwrite=None)
                                        print(f"❌ Removed all permissions from {member.name} (no Family Member role)")
                                break
                except:
                    pass

async def re_add_green_check_reaction(guild: discord.Guild, member: discord.Member) -> None:
    """Re-add green check reaction for registered users who removed it."""
    print(f"🔄 User {member.name} is registered/received family role, re-adding reaction...")
    
    try:
        rules_channel = guild.get_channel(RULES_CHANNEL_ID)
        if rules_channel:
            rules_message = await rules_channel.fetch_message(RULES_MESSAGE_ID)
            await rules_message.add_reaction('✅')
            print(f"✅ Re-added green check mark for {member.name}")
            
            # Notify user about registration lock
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
                print(f"⚠️ Cannot send DM warning to {member.name}")
    except Exception as e:
        print(f"❌ Error re-adding reaction: {e}")

@bot.event 
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    """
    Handle green check mark reactions to start registration.
    
    Triggers DM registration process when users react with ✅
    to the rules message.
    """
    # Ignore bot reactions
    if payload.user_id == bot.user.id:
        return
    
    # Check for rules channel green check reaction
    if (payload.channel_id == RULES_CHANNEL_ID and
        payload.message_id == RULES_MESSAGE_ID and
        str(payload.emoji) == '✅'):
        
        guild = bot.get_guild(payload.guild_id)
        if guild:
            member = guild.get_member(payload.user_id)
            if member and not member.bot:
                # Check for Master Lee's Family role exemption
                master_lee_family_role = guild.get_role(MASTER_LEE_FAMILY_ROLE_ID)
                has_master_lee_family = master_lee_family_role and master_lee_family_role in member.roles
                
                if has_master_lee_family:
                    await handle_master_lee_family_member(member)
                    return
                
                # Check if already registered
                if str(member.id) in registered_users:
                    await notify_already_registered(member)
                    return
                
                # Start registration process
                await log_registration_start(guild, member)
                await start_dm_process(member)
    
    # Check for general chat mute reaction
    elif payload.channel_id == GENERAL_CHAT_CHANNEL_ID and str(payload.emoji) == '🔇':
        guild = bot.get_guild(payload.guild_id)
        if guild:
            channel = guild.get_channel(payload.channel_id)
            if channel:
                try:
                    message = await channel.fetch_message(payload.message_id)
                    # Check if this is our mute instruction message
                    if message.author == bot.user and message.embeds:
                        for embed in message.embeds:
                            if embed.title and "How to Access" in embed.title:
                                # This is the mute instruction message
                                member = guild.get_member(payload.user_id)
                                if member and not member.bot:
                                    # Grant send permission when they react
                                    # Remove any existing permission override first
                                    await channel.set_permissions(member, overwrite=None)
                                    
                                    # Then add the new permission with send_messages enabled
                                    await channel.set_permissions(
                                        member,
                                        read_messages=True,
                                        send_messages=True,
                                        view_channel=True,
                                        read_message_history=True,
                                        reason="User reacted to mute instruction"
                                    )
                                    print(f"✅ Granted send permission to {member.name} for reacting to mute instruction")
                                    
                                    # Send confirmation DM
                                    try:
                                        dm_channel = await member.create_dm()
                                        confirm_embed = discord.Embed(
                                            title="✅ Access Granted",
                                            description=f"You now have permission to send messages in <#{GENERAL_CHAT_CHANNEL_ID}>!\n\n"
                                                    "**Remember:**\n"
                                                    "• All messages are auto-forwarded to private chats\n"
                                                    "• Keep conversations respectful\n"
                                                    "• Enjoy chatting with the community!",
                                            color=discord.Color.green()
                                        )
                                        await dm_channel.send(embed=confirm_embed)
                                    except:
                                        pass
                                break
                except:
                    pass

async def handle_master_lee_family_member(member: discord.Member) -> None:
    """Handle Master Lee's Family members (exempt from registration)."""
    print(f"✅ User {member.name} has Master Lee's Family role, skipping DM process")
    try:
        dm_channel = await member.create_dm()
        welcome_embed = discord.Embed(
            title="👑 Welcome Master Lee's Family Member!",
            description="As a member of Master Lee's Family, you have full access to the server.\n\n"
                      "You don't need to complete the standard registration process.\n"
                      "Enjoy your stay in our community!",
            color=discord.Color.gold()
        )
        await dm_channel.send(embed=welcome_embed)
    except discord.Forbidden:
        print(f"⚠️ Cannot send DM to {member.name}")

async def notify_already_registered(member: discord.Member) -> None:
    """Notify user they are already registered."""
    print(f"⚠️ User {member.name} already registered")
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
        print(f"⚠️ Cannot send DM to {member.name}")

async def log_registration_start(guild: discord.Guild, member: discord.Member) -> None:
    """Log registration start event."""
    embed = discord.Embed(
        title="📝 Registration Started",
        description=f"**User:** {member.mention} ({member.id})\n"
                  f"**Name:** {member.name}\n"
                  f"**Started:** <t:{int(time.time())}:R>",
        color=discord.Color.blue(),
        timestamp=datetime.now(timezone.utc)
    )
    await send_to_log_channel(guild, "", embed)

@bot.event
async def on_message(message: discord.Message):
    """
    Central message handler for all message types.
    
    Handles:
    - Monitored channel messages (create private chats)
    - Private chat messages
    - DM messages (registration, admin responses, user responses)
    - Command processing
    """
    if message.author.bot:
        return
    
    # Handle monitored channel messages
    if message.channel.id in MONITORED_CHANNELS:
        # Check if user has permission to send messages
        if not message.channel.permissions_for(message.author).send_messages:
            try:
                await message.delete()
                print(f'❌ Blocked message from {message.author.name} - no send permission')
                
                # Notify user via DM
                try:
                    dm_channel = await message.author.create_dm()
                    embed = discord.Embed(
                        title="🔒 Permission Required",
                        description=f"You don't have permission to send messages in <#{GENERAL_CHAT_CHANNEL_ID}> yet!\n\n"
                                  "**To get access:**\n"
                                  "1. Mute the channel notifications\n"
                                  "2. React with 🔇 to the pinned message in that channel\n"
                                  "3. You'll then be able to send messages\n\n"
                                  "This helps prevent notification spam for everyone.",
                        color=discord.Color.red()
                    )
                    await dm_channel.send(embed=embed)
                except:
                    pass
            except:
                pass
            return
        
        await handle_monitored_channel_message(message)
        await delete_original_message(message)
    
    # Handle private chat messages
    elif message.channel.id in private_channels:
        private_channels[message.channel.id]['last_activity'] = time.time()
        print(f'💬 Message in private chat #{message.channel.name}')
        await bot.process_commands(message)
        return
    
    # Handle DM messages
    elif isinstance(message.channel, discord.DMChannel):
        if message.author.id == ADMIN_USER_ID:
            await handle_admin_dm_response(message)
        elif message.author.id in active_conversations:
            await handle_user_dm_response(message)
        else:
            await handle_registration_dm(message)
    
    # Process commands
    await bot.process_commands(message)

async def delete_original_message(message: discord.Message) -> None:
    """Delete original message from monitored channel after processing."""
    try:
        await message.delete()
        print(f'🗑️ Deleted message from {message.author.name} in #{message.channel.name}')
    except discord.Forbidden:
        print(f'❌ Cannot delete message in #{message.channel.name}')
    except discord.NotFound:
        pass  # Message already deleted

# =============================================================================
# MESSAGE HANDLING FUNCTIONS
# =============================================================================
async def handle_monitored_channel_message(message: discord.Message):
    """
    Process messages from monitored channels by creating/using private chats.
    
    Features:
    - Thread-safe processing with locks
    - Automatic private chat creation
    - Message forwarding with attachments
    - Comprehensive logging
    """
    # Use lock to prevent concurrent processing issues
    async with processing_lock:
        guild = message.guild
        user = message.author
        
        # Log message before forwarding
        await log_monitored_message(guild, user, message)
        
        # Create or get existing private chat
        private_chat = await create_private_channel(guild, user, message.channel.name)
        
        if not private_chat:
            print(f"❌ Failed to create private chat for {user.name}")
            return
        
        # Forward message to private chat
        await forward_message_to_private_chat(private_chat, user, message)
        
        # Delete original message
        await delete_original_message(message)

async def log_monitored_message(guild: discord.Guild, user: discord.Member, message: discord.Message) -> None:
    """Log monitored channel message to log channel."""
    embed = discord.Embed(
        title="💬 Message in Monitored Channel",
        description=f"**User:** {user.mention} ({user.id})\n"
                  f"**Channel:** #{message.channel.name}\n"
                  f"**Content:** {message.content[:200]}{'...' if len(message.content) > 200 else ''}",
        color=discord.Color.purple(),
        timestamp=datetime.now(timezone.utc)
    )
    
    # Add attachment information if present
    if message.attachments:
        attachment_list = [f"📎 {attachment.filename}" for attachment in message.attachments[:3]]
        if len(message.attachments) > 3:
            attachment_list.append(f"...and {len(message.attachments) - 3} more")
        embed.add_field(name="Attachments", value="\n".join(attachment_list), inline=False)
    
    await send_to_log_channel(guild, "", embed)

async def forward_message_to_private_chat(channel: discord.TextChannel, user: discord.Member, original_message: discord.Message) -> None:
    """
    Forward message content to private chat with proper formatting.
    
    Handles:
    - Text content formatting
    - Attachment links
    - Error handling and retries
    - Rate limit management
    """
    # Format message for forwarding
    text_content = f"**{user.name}** (from #{original_message.channel.name}):\n{original_message.content}"
    
    # Add attachment links if present
    attachment_text = ""
    if original_message.attachments:
        attachment_links = []
        for i, attachment in enumerate(original_message.attachments):
            attachment_links.append(f"📎 Attachment {i+1}: {attachment.url}")
        attachment_text = "\n" + "\n".join(attachment_links)
    
    final_message = text_content + attachment_text
    
    try:
        # Send to private chat
        sent_msg = await channel.send(final_message)
        print(f'📤 Forwarded simple message from {original_message.author.name} in #{original_message.channel.name} to private chat')
        
    except discord.Forbidden as e:
        print(f'❌ Permission error: {e}')
        await notify_user_permission_error(user, channel.name)
        
    except discord.HTTPException as e:
        print(f"⚠️ Discord API rate limit or error: {e}")
        if e.status == 429:  # Too Many Requests
            retry_after = e.retry_after if hasattr(e, 'retry_after') else 5
            print(f'⏳ Rate limited, retry after: {retry_after} seconds')
            await asyncio.sleep(retry_after)
            
            # Retry sending
            try:
                sent_msg = await channel.send(final_message)
                print(f'📤 Retry successful for {user.name}')
            except Exception as retry_error:
                print(f'❌ Retry failed: {retry_error}')
    except Exception as e:
        print(f'❌ Unexpected error in forward_message_to_private_chat: {e}')

async def notify_user_permission_error(user: discord.Member, channel_name: str) -> None:
    """Notify user about permission errors via DM."""
    try:
        dm_channel = await user.create_dm()
        await dm_channel.send(
            f"📨 Your message in #{channel_name} was received, but there was a permission issue. "
            f"Please check if you can access the private chat."
        )
    except:
        pass

async def handle_admin_dm_response(message: discord.Message):
    """
    Handle admin responses to forwarded messages in DMs.
    
    Supports:
    - Reply-based message forwarding to users
    - Standalone admin messages with instructions
    - Error handling for user not found
    """
    # Check if this is a reply to a forwarded message
    if message.reference and message.reference.message_id:
        await forward_admin_reply_to_user(message)
    else:
        # Send instructions for standalone admin message
        await send_admin_instructions(message)

async def forward_admin_reply_to_user(message: discord.Message) -> None:
    """Forward admin reply to the original user."""
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
            
            # Forward to user
            await send_admin_response_to_user(user, message, emoji, channel_type)
            
        else:
            # Not a reply to our forwarded message
            pass
    except Exception as e:
        print(f'Error handling admin DM response: {e}')

async def send_admin_response_to_user(user: discord.Member, admin_message: discord.Message, emoji: str, channel_type: str) -> None:
    """Send admin response to user via DM."""
    try:
        user_dm = await user.create_dm()
        
        embed = discord.Embed(
            title=f"{emoji} Response from Admin",
            description=admin_message.content,
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text=f"Regarding your message in {channel_type}")
        
        await user_dm.send(embed=embed)
        
        print(f'📨 Sent admin response to {user.name} regarding {channel_type}')
        
        # Confirm to admin
        confirm_embed = discord.Embed(
            description=f"✅ Response sent to {user.mention} ({user.name})",
            color=discord.Color.green()
        )
        await admin_message.channel.send(embed=confirm_embed)
        
    except discord.Forbidden:
        error_embed = discord.Embed(
            description=f"❌ Cannot send DM to {user.name}. They may have DMs disabled.",
            color=discord.Color.red()
        )
        await admin_message.channel.send(embed=error_embed)
    except Exception as e:
        error_embed = discord.Embed(
            description=f"❌ Error sending response: {str(e)}",
            color=discord.Color.red()
        )
        await admin_message.channel.send(embed=error_embed)

async def send_admin_instructions(message: discord.Message) -> None:
    """Send instructions to admin about private chat system."""
    help_embed = discord.Embed(
        title="💭 How Private Chats Work",
        description="**New System:**\n"
                  "1. When a user sends a message in monitored channels\n"
                  "2. A private chat is created with a permanent delete button at the top\n"
                  "3. Only you and the user can see/access it\n"
                  "4. All conversation happens in that channel\n\n"
                  "**Benefits:**\n"
                  "• Clean separation between conversations\n"
                  "• Permanent delete button at top (admin only)\n"
                  "• No inactivity timer - button is always available\n"
                  "• Easy to track individual discussions",
        color=discord.Color.blue()
    )
    await message.channel.send(embed=help_embed)

async def handle_user_dm_response(message: discord.Message):
    """Forward user DM responses to admin."""
    user_id = message.author.id
    
    if user_id in active_conversations:
        conv_data = active_conversations[user_id]
        admin_id = conv_data.get('admin_id')
        channel_type = conv_data.get('channel_type', 'Chat')
        emoji = conv_data.get('channel_emoji', '💬')
        
        admin_user = bot.get_user(admin_id)
        if admin_user:
            await forward_user_response_to_admin(admin_user, message, emoji, channel_type, user_id)

async def forward_user_response_to_admin(admin_user: discord.User, user_message: discord.Message, emoji: str, channel_type: str, user_id: int) -> None:
    """Forward user response to admin via DM."""
    try:
        admin_dm = await admin_user.create_dm()
        
        # Create embed for user response
        embed = discord.Embed(
            title=f"{emoji} User Response ({channel_type})",
            description=user_message.content,
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_author(
            name=f"{user_message.author.name}",
            icon_url=user_message.author.avatar.url if user_message.author.avatar else None
        )
        embed.set_footer(text=f"User ID: {user_message.author.id}")
        
        # Handle attachments
        if user_message.attachments:
            attachment_info = []
            for i, attachment in enumerate(user_message.attachments[:3]):
                if hasattr(attachment, 'content_type') and attachment.content_type and 'image' in attachment.content_type:
                    attachment_info.append(f"📸 [Image {i+1}]({attachment.url})")
                elif hasattr(attachment, 'filename'):
                    attachment_info.append(f"📎 [{attachment.filename}]({attachment.url})")
                else:
                    attachment_info.append(f"📎 [Attachment {i+1}]({attachment.url})")
            
            if len(user_message.attachments) > 3:
                attachment_info.append(f"...and {len(user_message.attachments) - 3} more")
            
            embed.add_field(name="📎 Attachments", value="\n".join(attachment_info), inline=False)
            
            # Set image preview if available
            image_attachments = [a for a in user_message.attachments if hasattr(a, 'content_type') and a.content_type and 'image' in a.content_type]
            if image_attachments:
                embed.set_image(url=image_attachments[0].url)
        
        # Send to admin
        forward_msg = await admin_dm.send(embed=embed)
        
        # Update tracking
        active_conversations[user_id]['last_forwarded_message_id'] = forward_msg.id
        message_references[forward_msg.id] = user_id
        
        print(f'📤 Forwarded user response from {user_message.author.name} to admin')
        
    except discord.Forbidden:
        print(f'❌ Cannot send DM to admin!')
    except Exception as e:
        print(f"❌ Error forwarding user response: {e}")

async def handle_registration_dm(message: discord.Message):
    """
    Handle registration-related DMs from users.
    
    Processes:
    - Name entry validation
    - Step navigation guidance
    - State management
    """
    user_id = message.author.id
    
    # Name entry step
    if user_id in user_states and user_states[user_id]['waiting_for_name']:
        original_name = message.content.strip()
        
        # Validate name format
        is_valid, error_msg = validate_name_format(original_name)
        if not is_valid:
            await message.channel.send(f"{error_msg}\n\nPlease try again:")
            return
        
        # Clean and store name
        cleaned_name = clean_name(original_name)
        
        user_states[user_id]['child_name_original'] = original_name
        user_states[user_id]['child_name_cleaned'] = cleaned_name
        
        # Move to confirmation step
        user_states[user_id]['waiting_for_name'] = False
        user_states[user_id]['waiting_for_name_confirmation'] = True
        
        print(f"📝 {message.author.name} entered name: '{original_name}' -> cleaned: '{cleaned_name}'")
        
        # Send confirmation view
        await send_name_confirmation_view(message.channel, user_id, cleaned_name, original_name)
    
    # Guidance for other steps
    elif user_id in user_states:
        await provide_step_guidance(message.channel, user_id)

async def send_name_confirmation_view(channel: discord.DMChannel, user_id: int, cleaned_name: str, original_name: str) -> None:
    """Send name confirmation view with validation."""
    embed = discord.Embed(
        title="🔍 Please Confirm the Name",
        color=discord.Color.gold()
    )
    embed.add_field(name="📝 You entered:", value=f"```{original_name}```", inline=False)
    embed.add_field(name="✅ Formatted to:", value=f"```{cleaned_name}```", inline=False)
    embed.add_field(name="❓ Is this correct?", value="Please select an option below:", inline=False)
    
    view = NameConfirmationView(user_id, cleaned_name, original_name)
    await channel.send(embed=embed, view=view)

async def provide_step_guidance(channel: discord.DMChannel, user_id: int) -> None:
    """Provide guidance based on current registration step."""
    state = user_states[user_id]
    
    if state['waiting_for_name_confirmation']:
        await channel.send("⚠️ Please use the buttons above to confirm or change the name.")
    elif state['waiting_for_role']:
        await channel.send("⚠️ Please select your role using the buttons above.")
    elif state['waiting_for_role_confirmation']:
        await channel.send("⚠️ Please use the buttons above to confirm or change your role.")
    elif state['waiting_for_teams']:
        await channel.send("⚠️ Please select teams using the buttons above.")
    elif state['waiting_for_teams_confirmation']:
        await channel.send("⚠️ Please use the buttons above to confirm or change your teams.")
    elif state['waiting_for_final_confirmation']:
        await channel.send("⚠️ Please use the buttons above to confirm your registration or make changes.")

# =============================================================================
# REGISTRATION FUNCTIONS
# =============================================================================
async def assign_family_role(member: discord.Member) -> bool:
    """
    Assign Family Member role to user after registration.
    
    Args:
        member: Discord member to assign role to
        
    Returns:
        True if role assigned successfully, False otherwise
    """
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

async def assign_student_role(member: discord.Member) -> bool:
    """
    Assign Student role to user after registration.
    
    Args:
        member: Discord member to assign role to
        
    Returns:
        True if role assigned successfully, False otherwise
    """
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return False
    
    student_role = guild.get_role(STUDENT_ROLE_ID)
    if student_role and student_role not in member.roles:
        try:
            await member.add_roles(student_role, reason="Registration Complete")
            print(f'✅ Added Student role to {member.name} after registration')
            return True
        except discord.Forbidden:
            print(f'❌ Missing permissions to add role to {member.name}')
        except discord.HTTPException as e:
            print(f'❌ Error adding role to {member.name}: {e}')
    return False

async def assign_team_roles(member: discord.Member, teams_selected: list) -> List[str]:
    """
    Assign team roles based on user selection.
    
    Args:
        member: Discord member to assign roles to
        teams_selected: List of selected team identifiers
        
    Returns:
        List of successfully assigned team names
    """
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return []
    
    assigned_teams = []
    
    # Assign National Team role
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
    
    # Assign Demonstration Team role
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
                print(f"❌ Error adding Demonstration Team role to {member.name}: {e}")
    
    return assigned_teams

async def start_dm_process(member: discord.Member):
    """
    Initiate DM registration process with user.
    
    Sends:
    - Welcome message
    - Step-by-step instructions
    - Initial name entry prompt
    """
    try:
        if str(member.id) in registered_users:
            return
        
        print(f"📨 Attempting to DM {member.name}...")
        
        dm_channel = await member.create_dm()
        
        # Send welcome message
        embed1 = discord.Embed(
            title="👨‍👩‍👧‍👦 Server Registration",
            description="Welcome! Let's get started!\n\n"
                      "I'll guide you through 4 simple steps:",
            color=discord.Color.blue()
        )
        await dm_channel.send(embed=embed1)
        await asyncio.sleep(1)
        
        # Send name entry instructions
        embed2 = discord.Embed(
            title="Step 1: Child's Name",
            description="Please type your child's **FIRST and LAST NAME** (e.g., 'John Smith')",
            color=discord.Color.green()
        )
        
        tips_text = (
            "💡 **Name Entry Tips**\n"
            "**How to enter the name correctly:**\n\n"
            "✅ **Do:**\n"
            "• Include both first and last name\n"
            "• Use proper spacing\n\n"
            "❌ **Don't:**\n"
            "• Use nicknames only\n"
            "• Include middle names"
        )
        
        embed2.add_field(name="📝 Important", value="**ONLY put one of your child's name**", inline=False)
        embed2.add_field(name="Instructions", value=tips_text, inline=False)
        await dm_channel.send(embed=embed2)
        
        # Initialize user state for registration
        user_states[member.id] = {
            'waiting_for_name': True,
            'waiting_for_name_confirmation': False,
            'waiting_for_role': False,
            'waiting_for_role_confirmation': False,
            'waiting_for_teams': False,
            'waiting_for_teams_confirmation': False,
            'waiting_for_final_confirmation': False,
            'child_name': None,
            'child_name_original': None,
            'child_name_cleaned': None,
            'gender': None,
            'teams_selected': [],
            'role_display': None,
            'modifying_from_final': False,
            'preserved_data': {},
            'modifying_step': None
        }
        
        print(f"✅ DM sent to {member.name}")
        
    except discord.Forbidden:
        print(f"❌ Cannot send DM to {member.name} - they might have DMs disabled")
    except Exception as e:
        print(f"❌ Error sending DM to {member.name}: {e}")

async def complete_registration(user: discord.User, member: discord.Member):
    """
    Finalize registration process with comprehensive completion steps.
    """
    user_id = user.id
    
    if user_id not in user_states:
        return
    
    # Extract registration data
    child_name = user_states[user_id]['child_name']
    gender = user_states[user_id]['gender']
    role_display = user_states[user_id]['role_display']
    teams_selected = user_states[user_id]['teams_selected']
    
    # Generate nickname based on role
    nickname, role_name, emoji_role = generate_nickname_and_role(child_name, gender)
    
    dm_channel = await user.create_dm()
    
    # Attempt nickname assignment
    nickname_success, success_msg = await attempt_nickname_assignment(member, nickname)
    
    # Assign appropriate role based on registration type
    if gender == 'student':
        # Assign Student role (same permissions as Family Member)
        role_assigned = await assign_student_role(member)
        role_type = "Student"
    else:
        # Assign Family Member role for parents/grandparents
        role_assigned = await assign_family_role(member)
        role_type = "Family Member"
    
    # Grant access to general-chat if role assigned successfully
    if role_assigned:
        await grant_general_chat_access(member)
    
    # Assign team roles (if any selected)
    assigned_teams = await assign_team_roles(member, teams_selected)
    
    # Prepare completion message components
    team_message = format_team_message(teams_selected)
    role_msg = format_role_assignment_message(role_type, role_assigned, assigned_teams)
    
    # Send completion message
    await send_registration_completion_message(
        dm_channel, emoji_role, role_display, child_name, 
        success_msg, role_msg, team_message, gender
    )
    
    # Save registration data
    save_registration_data(user_id, child_name, role_name, role_display, 
                          nickname, gender, teams_selected)
    
    # Log successful registration
    await log_successful_registration(member, child_name, nickname, teams_selected, gender)
    
    # Clean up temporary state
    del user_states[user_id]
    
    print(f"✅ Registration complete for {user.name} as {gender} with teams: {teams_selected}")
    
async def grant_general_chat_access(member: discord.Member) -> bool:
    """
    Grant access to #general-chat channel after registration.
    
    Args:
        member: The member to grant access to
        
    Returns:
        True if access granted successfully, False otherwise
    """
    guild = member.guild
    general_chat = guild.get_channel(GENERAL_CHAT_CHANNEL_ID)
    
    if not general_chat:
        print(f"❌ General chat channel not found (ID: {GENERAL_CHAT_CHANNEL_ID})")
        return False
    
    try:
        # Grant view and read access to #general-chat
        await general_chat.set_permissions(
            member,
            read_messages=True,
            view_channel=True,
            read_message_history=True,
            reason="Granted after DM registration completion"
        )
        
        return True
        
    except discord.Forbidden:
        print(f"❌ No permission to modify #general-chat permissions for {member.name}")
        return False
    except Exception as e:
        print(f"❌ Error granting #general-chat access to {member.name}: {e}")
        return False

def generate_nickname_and_role(child_name: str, gender: str) -> Tuple[str, str, str]:
    """Generate nickname, role name, and emoji based on gender."""
    if gender == 'mother':
        return f"{child_name}'s Mother", "Mother", "👩"
    elif gender == 'father':
        return f"{child_name}'s Father", "Father", "👨"
    elif gender == 'grandmother':
        return f"{child_name}'s Grandmother", "Grandmother", "👵"
    elif gender == 'grandfather':
        return f"{child_name}'s Grandfather", "Grandfather", "👴"
    elif gender == 'student':
        # For student, just use their name as nickname (no "Student" suffix)
        return child_name, "Student", "🎓"
    else:
        return child_name, "Unknown", "👤"

async def attempt_nickname_assignment(member: discord.Member, nickname: str) -> Tuple[bool, str]:
    """Attempt to assign nickname to member with error handling."""
    try:
        await member.edit(nick=nickname, reason="Family Registration")
        print(f"✅ Changed {member.name}'s nickname to {nickname}")
        return True, f"✅ **Success!** Your nickname is now: **{nickname}**"
    except discord.Forbidden:
        manual_instructions = (
            f"⚠️ **Note:** I couldn't automatically set your nickname.\n\n"
            f"**Please manually change your server nickname to:**\n"
            f"```{nickname}```\n"
            f"1. Right-click server name → 'Change Nickname'\n"
            f"2. Enter: `{nickname}`\n"
            f"3. Click 'Save'"
        )
        print(f"⚠️ Cannot change nickname for {member.name}")
        return False, manual_instructions
    except Exception as e:
        error_msg = f"⚠️ Error setting nickname: {e}"
        print(f"❌ Error changing nickname for {member.name}: {e}")
        return False, error_msg

def format_team_message(teams_selected: List[str]) -> str:
    """Format team selection message for completion embed."""
    if not teams_selected:
        return "\n\n**Teams:** None selected - you can join teams later!"
    
    team_list = []
    if "national" in teams_selected:
        team_list.append("**National Team** 🔴")
    if "demonstration" in teams_selected:
        team_list.append("**Demonstration Team** 🔵")
    
    return f"\n\n**Teams Joined:**\n" + "\n".join([f"• {team}" for team in team_list])

def format_role_assignment_message(role_type: str, role_assigned: bool, assigned_teams: List[str]) -> str:
    """Format role assignment results message."""
    role_msg = ""
    if role_assigned:
        role_msg += f"✅ You have been given the **{role_type}** role!\n"
    else:
        role_msg += f"⚠️ Could not assign {role_type} role. Please contact an administrator.\n"
    
    if assigned_teams:
        role_msg += f"✅ Added to {len(assigned_teams)} team(s): {', '.join(assigned_teams)}"
    elif assigned_teams == []:  # Explicitly check for empty list
        role_msg += "⚠️ Could not assign team roles. Please contact an administrator."
    
    return role_msg

# In the send_registration_completion_message function, update the description:
async def send_registration_completion_message(
    dm_channel: discord.DMChannel, 
    emoji_role: str, 
    role_display: str, 
    child_name: str,
    success_msg: str,
    role_msg: str,
    team_message: str,
    gender: str
) -> None:
    """Send final registration completion message to user."""
    
    if gender == 'student':
        description = f"{emoji_role} You are now registered as **{role_display}**!\n\n"
    else:
        description = f"{emoji_role} You are now registered as **{role_display}** of **{child_name}**!\n\n"
    
    description += f"{success_msg}\n\n"
    description += f"{role_msg}{team_message}\n\n"
    description += f"**🎊 What's Next:**\n"
    description += f"• You can now see **#general-chat**!\n"
    description += f"• Check the pinned message in #general-chat for instructions on how to:\n"
    description += f"  1. Mute the channel (recommended)\n"
    description += f"  2. Get permission to send messages\n"
    description += f"  3. Understand how the chat works\n\n"
    description += f"Welcome to the family!"
    
    embed = discord.Embed(
        title="🎉 Registration Complete!",
        description=description,
        color=discord.Color.gold()
    )
    await dm_channel.send(embed=embed)

def save_registration_data(
    user_id: int,
    child_name: str,
    role_name: str,
    role_display: str,
    nickname: str,
    gender: str,
    teams_selected: List[str]
) -> None:
    """Save registration data to persistent storage."""
    registered_users[str(user_id)] = {
        'child_name': child_name,
        'role': role_name,
        'role_display': role_display,
        'nickname': nickname,
        'gender': gender,
        'teams': teams_selected,
        'registered_at': discord.utils.utcnow().isoformat()
    }
    save_registered_users(registered_users)

async def log_successful_registration(
    member: discord.Member,
    child_name: str,
    nickname: str,
    teams_selected: List[str],
    gender: str
) -> None:
    """Log successful registration to log channel."""
    guild = bot.get_guild(GUILD_ID)
    if guild:
        if gender == 'student':
            role_name = "Student"
        else:
            family_role = guild.get_role(FAMILY_ROLE_ID)
            role_name = family_role.name if family_role else "Family Member"
        
        log_embed = discord.Embed(
            title="✅ Registration Complete",
            description=f"**User:** {member.mention} ({member.id})\n"
                      f"**Child's Name:** {child_name}\n"
                      f"**Role:** {role_name}\n"
                      f"**Nickname:** {nickname}\n"
                      f"**Teams:** {', '.join(teams_selected) if teams_selected else 'None'}\n"
                      f"**Registered:** <t:{int(time.time())}:R>",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        await send_to_log_channel(guild, "", log_embed)

# =============================================================================
# COMMAND DEFINITIONS
# =============================================================================
# Bot command group for administrative functions
@bot.group(name="bot_command", invoke_without_command=True)
async def bot_command(ctx):
    """Main bot command category for administrative functions."""
    if ctx.invoked_subcommand is None:
        await ctx.send("❌ Invalid command. Use `!help bot_command` for available commands.", ephemeral=True)

# Chat command subcategory
@bot_command.command(name="chat")
@bot_channel_only()
async def chat_command(ctx):
    """
    Display available administrative chat commands.
    
    Only accessible in bot command channel by admin users.
    """
    embed = discord.Embed(
        title="💬 Admin Bot Commands",
        description="**Available commands in this chat:**\n\n"
                   "**📊 Statistics & Info:**\n"
                   "• `!bot_command chat active_private_chats` - Show active private chats\n"
                   "• `!bot_command chat register_stats` - Show registration statistics\n"
                   "• `!bot_command chat active_chats` - Show active conversations\n"
                   "• `!bot_command chat check_consistency` - Check registry consistency\n\n"
                   "**👤 User Management:**\n"
                   "• `!bot_command chat view_user @user` - View user info\n"
                   "• `!bot_command chat send_dm @user message` - Send DM to user\n"
                   "• `!bot_command chat assign_role @user` - Assign family role\n"
                   "• `!bot_command chat add_teams @user` - Add teams to user\n"
                   "• `!bot_command chat fix_name @user new_name` - Fix user's name\n\n"
                   "**🔧 Bot Management:**\n"
                   "• `!bot_command chat setup` - Setup rules message\n"
                   "• `!bot_command chat setup_bot_channel` - Setup bot command channel\n"
                   "• `!bot_command chat clear_chats` - Clear active conversations\n"
                   "• `!bot_command chat remove_check @user` - Remove user's check\n"
                   "• `!bot_command chat update_message_id ID` - Update rules message ID\n"
                   "• `!bot_command chat resend_delete_button #channel` - Resend delete button\n\n"
                   "**🛠️ Testing & Debug:**\n"
                   "• `!bot_command chat test_button` - Test delete button\n"
                   "• `!bot_command chat test_reaction` - Test reaction detection\n"
                   "• `!bot_command chat debug_ids` - Show all IDs\n"
                   "• `!bot_command chat check_message ID` - Check message reactions\n",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)

@bot_command.command(name="assign_instructor")
@bot_channel_only()
async def chat_assign_instructor(ctx, member: discord.Member):
    """Manually assign Instructor role to a user."""
    guild = ctx.guild
    instructor_role = guild.get_role(INSTRUCTOR_ROLE_ID)
    
    if not instructor_role:
        await ctx.send("❌ Instructor role not found!", ephemeral=True)
        return
    
    try:
        await member.add_roles(instructor_role, reason="Instructor role assigned by admin")
        
        # Also give them access to all channels that Master Lee's Family has
        master_role = guild.get_role(MASTER_LEE_FAMILY_ROLE_ID)
        
        # Copy permissions from Master Lee's Family role to Instructor role
        for channel in guild.channels:
            # Check if Master Lee's Family has permissions in this channel
            master_overwrite = channel.overwrites_for(master_role) if master_role else None
            
            if master_overwrite and any([
                master_overwrite.read_messages,
                master_overwrite.send_messages,
                master_overwrite.view_channel
            ]):
                # Apply same permissions to Instructor
                await channel.set_permissions(
                    instructor_role,
                    overwrite=master_overwrite,
                    reason="Instructor permissions set to match Master Lee's Family"
                )
        
        await ctx.send(f"✅ Assigned Instructor role to {member.mention} and copied Master Lee's Family permissions")
        
        # Log the assignment
        embed = discord.Embed(
            title="👨‍🏫 Instructor Role Assigned",
            description=f"**User:** {member.mention} ({member.id})\n"
                      f"**Assigned by:** {ctx.author.mention}\n"
                      f"**Time:** <t:{int(time.time())}:R>",
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc)
        )
        await send_to_log_channel(guild, "", embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error assigning Instructor role: {e}", ephemeral=True)

# =============================================================================
# ADMINISTRATIVE COMMANDS (BOT CHANNEL ONLY)
# =============================================================================
@bot_command.command(name="active_private_chats")
@bot_channel_only()
async def chat_active_private_chats(ctx):
    """Display all active private chats with status information."""
    if not private_channels:
        embed = discord.Embed(
            title="📁 Active Private Chats",
            description="No active private chats.",
            color=discord.Color.grey()
        )
        await ctx.send(embed=embed)
        return
    
    embed = discord.Embed(
        title="📁 Active Private Chats",
        description=f"Currently {len(private_channels)} active private chat(s):",
        color=discord.Color.blue()
    )
    
    for channel_id, data in private_channels.items():
        channel = ctx.guild.get_channel(channel_id)
        user = ctx.guild.get_member(data['user_id'])
        
        if channel and user:
            inactive_time = time.time() - data['last_activity']
            inactive_hours = inactive_time // 3600
            inactive_minutes = (inactive_time % 3600) // 60
            
            # Determine activity status (5 minute threshold)
            status = "✅ Active" if inactive_time < 300 else "⚠️ Inactive"
            
            embed.add_field(
                name=f"🔒 {channel.name}",
                value=f"👤 User: {user.mention}\n"
                      f"📅 Created: <t:{int(data['created_at'])}:R>\n"
                      f"⏰ Last Activity: {int(inactive_hours)}h {int(inactive_minutes)}m ago\n"
                      f"📝 From: {data['original_channel']}\n"
                      f"🔧 Status: {status}\n"
                      f"🛑 Delete button: ✅ Pinned at top",
                inline=True
            )
    
    await ctx.send(embed=embed)

@bot_command.command(name="cleanup_private_chats")
@bot_channel_only()
async def chat_cleanup_private_chats(ctx):
    """Bulk delete all private chats with confirmation."""
    count = len(private_channels)
    
    if count == 0:
        await ctx.send("✅ No private chats to clean up.", ephemeral=True)
        return
    
    class ConfirmCleanupView(discord.ui.View):
        """Confirmation view for bulk chat cleanup."""
        
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
            
            # Delete all channels
            channels_deleted = 0
            channels_to_delete = list(private_channels.keys())
            
            for channel_id in channels_to_delete:
                channel = ctx.guild.get_channel(channel_id)
                if channel:
                    try:
                        await channel.delete(reason="Bulk cleanup by admin")
                        channels_deleted += 1
                    except:
                        pass
            
            # Clear tracking data
            private_channels.clear()
            user_private_channels.clear()
            
            # Send confirmation
            await interaction.response.send_message(
                f"✅ Deleted {channels_deleted} private chats.",
                ephemeral=True
            )
            
            # Log bulk cleanup
            embed = discord.Embed(
                title="🗑️ Bulk Private Chat Cleanup",
                description=f"**Deleted:** {channels_deleted} private chats\n"
                          f"**By:** {interaction.user.mention}\n"
                          f"**Time:** <t:{int(time.time())}:R>",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            await send_to_log_channel(ctx.guild, "", embed)
            
            # Update original message
            embed = discord.Embed(
                title="✅ Cleanup Complete",
                description=f"Deleted {channels_deleted} private chats.",
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
    
    # Show confirmation prompt
    embed = discord.Embed(
        title="🧹 Cleanup Private Chats",
        description=f"This will delete **{count}** private chats.\n\n"
                   f"**Are you sure?** This action cannot be undone!\n"
                   f"All messages in these chats will be lost.",
        color=discord.Color.red()
    )
    
    view = ConfirmCleanupView()
    await ctx.send(embed=embed, view=view)

@bot_command.command(name="resend_delete_button")
@bot_channel_only()
async def chat_resend_delete_button(ctx, channel: discord.TextChannel):
    """Resend the permanent delete button in a private chat."""
    if channel.id not in private_channels:
        await ctx.send("❌ This is not a private chat channel.", ephemeral=True)
        return
    
    # Remove existing pinned delete button messages
    pinned_messages = await channel.pins()
    for msg in pinned_messages:
        if msg.author == bot.user and ("Delete Private Chat" in msg.content or "🗑️" in msg.content):
            try:
                await msg.unpin()
                await asyncio.sleep(0.5)
            except:
                pass
    
    # Create new delete button
    delete_view = PermanentDeleteChannelView(channel.id, private_channels[channel.id]['user_id'])
    delete_embed = discord.Embed(
        title="🗑️ Admin Delete Button (Resent)",
        description="This button is permanently available for admin to delete this private chat.\n\n"
                   "**Only the admin can use this button.**",
        color=discord.Color.red()
    )
    
    # Send and pin new button
    delete_message = await channel.send(embed=delete_embed, view=delete_view)
    await delete_message.pin()
    private_channels[channel.id]['pinned_message_id'] = delete_message.id
    
    await ctx.send(f"✅ Delete button resent and pinned in {channel.mention}", ephemeral=True)
    
    # Log the action
    embed = discord.Embed(
        title="🔄 Delete Button Resent",
        description=f"**Channel:** {channel.mention}\n"
                   f"**User:** <@{private_channels[channel.id]['user_id']}>\n"
                   f"**By:** {ctx.author.mention}",
        color=discord.Color.blue(),
        timestamp=datetime.now(timezone.utc)
    )
    await send_to_log_channel(ctx.guild, "", embed)

@bot_command.command(name="active_chats")
@bot_channel_only()
async def chat_active_chats(ctx):
    """Display active 1-on-1 conversations."""
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

@bot_command.command(name="clear_chats")
@bot_channel_only()
async def chat_clear_chats(ctx):
    """Clear all active conversation tracking data."""
    count = len(active_conversations)
    active_conversations.clear()
    message_references.clear()
    
    embed = discord.Embed(
        title="🧹 Conversations Cleared",
        description=f"Cleared {count} active conversation(s).",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

@bot_command.command(name="test_button")
@bot_channel_only()
async def chat_test_button(ctx):
    """Test the permanent delete button functionality."""
    view = PermanentDeleteChannelView(ctx.channel.id, ctx.author.id)
    
    embed = discord.Embed(
        title="🛠️ Test Permanent Delete Button",
        description="This is a test of the permanent delete button functionality.\n\n"
                   "Only you (the admin) can press this button!\n\n"
                   "**Note:** In private chats, this button is pinned at the top and always available.",
        color=discord.Color.blue()
    )
    
    await ctx.send(embed=embed, view=view)
    await ctx.send("✅ Test button sent! Try pressing it.")

@bot_command.command(name="test_reaction")
@bot_channel_only()
async def chat_test_reaction(ctx):
    """Test reaction detection functionality."""
    test_msg = await ctx.send("Test message - react with ✅ to see if bot detects it!")
    await test_msg.add_reaction('✅')
    await ctx.send(f"Test message ID: `{test_msg.id}` - try reacting with ✅!")

@bot_command.command(name="debug_ids")
@bot_channel_only()
async def chat_debug_ids(ctx):
    """Display all configured IDs for debugging purposes."""
    embed = discord.Embed(title="🔧 Debug Info", color=discord.Color.blue())
    
    # Add all configuration IDs
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
    embed.add_field(name="Private Conversation Category ID", value=f"`{PRIVATE_CONVERSATION_CATEGORY_ID}`", inline=True)
    embed.add_field(name="Bot Command Channel ID", value=f"`{BOT_COMMAND_CHANNEL_ID}`", inline=True)
    embed.add_field(name="Log Channel ID", value=f"`{LOG_CHANNEL_ID}`", inline=True)
    embed.add_field(name="Bot User ID", value=f"`{bot.user.id}`", inline=True)
    
    # Add channel status information
    if ctx.channel.id == RULES_CHANNEL_ID:
        embed.add_field(name="✅ Channel Status", value="This IS the rules channel!", inline=False)
    else:
        embed.add_field(name="⚠️ Channel Status", value=f"This is NOT the rules channel.\nRules channel: <#{RULES_CHANNEL_ID}>", inline=False)
    
    await ctx.send(embed=embed)

@bot_command.command(name="check_message")
@bot_channel_only()
async def chat_check_message(ctx, message_id: int = None):
    """Check reactions on a specific message."""
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

@bot_command.command(name="assign_role")
@bot_channel_only()
async def chat_assign_role(ctx, member: discord.Member):
    """Manually assign Family Member role to a user."""
    success = await assign_family_role(member)
    if success:
        await ctx.send(f"✅ Assigned Family Member role to {member.mention}")
    else:
        await ctx.send(f"❌ Failed to assign role to {member.mention}")

@bot_command.command(name="update_message_id")
@bot_channel_only()
async def chat_update_message_id(ctx, message_id: int):
    """Manually update the rules message ID in configuration."""
    config['RULES_MESSAGE_ID'] = str(message_id)
    with open('config.txt', 'w') as f:
        for key, value in config.items():
            f.write(f"{key}={value}\n")
    
    await ctx.send(f"✅ Updated rules message ID to: {message_id}")
    print(f"📝 Manually updated rules message ID to: {message_id}")

@bot_command.command(name="register_stats")
@bot_channel_only()
async def chat_register_stats(ctx):
    """Display registration statistics."""
    total_registered = len(registered_users)
    
    # Calculate team distribution
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
    
    embed.add_field(name="🔴 National Team", value=f"{national_count} members", inline=True)
    embed.add_field(name="🔵 Demonstration Team", value=f"{demonstration_count} members", inline=True)
    embed.add_field(name="🏆 Both Teams", value=f"{both_teams_count} members", inline=True)
    embed.add_field(name="👪 No Teams", value=f"{no_teams_count} members", inline=True)
    
    await ctx.send(embed=embed)

@bot_command.command(name="add_teams")
@bot_channel_only()
async def chat_add_teams(ctx, member: discord.Member):
    """Allow user to join teams post-registration."""
    user_id = member.id
    
    if str(user_id) not in registered_users:
        await ctx.send(f"❌ {member.mention} is not registered yet!", ephemeral=True)
        return
    
    try:
        dm_channel = await member.create_dm()
        
        user_data = registered_users[str(user_id)]
        child_name = user_data['child_name']
        gender = user_data['gender']
        
        embed = discord.Embed(
            title="🎯 Join Teams",
            description="Select which teams you'd like to join:\n\n"
                      "🔴 **National Team** - For competitive athletes\n"
                      "🔵 **Demonstration Team** - For performances and shows\n\n"
                      "You can select one, both, or none.\n"
                      "Click **✅ Done** when finished.",
            color=discord.Color.blue()
        )
        
        view = TeamSelectView(user_id, child_name, gender)
        await dm_channel.send(embed=embed, view=view)
        
        await ctx.send(f"✅ Sent team selection DM to {member.mention}", ephemeral=True)
        
    except discord.Forbidden:
        await ctx.send(f"❌ Cannot send DM to {member.mention} - they might have DMs disabled", ephemeral=True)

@bot_command.command(name="view_user")
@bot_channel_only()
async def chat_view_user(ctx, member: discord.Member):
    """View detailed registration information for a user."""
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
    embed.add_field(name="Role", value=user_data.get('role_display', user_data['role']), inline=True)
    embed.add_field(name="Nickname", value=user_data['nickname'], inline=True)
    
    teams = user_data.get('teams', [])
    if teams:
        team_list = []
        if "national" in teams:
            team_list.append("National Team 🔴")
        if "demonstration" in teams:
            team_list.append("Demonstration Team 🎯")
        embed.add_field(name="Teams", value=", ".join(team_list), inline=True)
    else:
        embed.add_field(name="Teams", value="None", inline=True)
    
    embed.add_field(name="Registered At", value=user_data['registered_at'], inline=False)
    embed.add_field(name="User ID", value=user_id, inline=True)
    
    await ctx.send(embed=embed, ephemeral=True)

@bot_command.command(name="send_dm")
@bot_channel_only()
async def chat_send_dm(ctx, member: discord.Member, *, message: str):
    """Send a direct message to a user."""
    try:
        dm_channel = await member.create_dm()
        embed = discord.Embed(
            title="💬 Message from Admin",
            description=message,
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        await dm_channel.send(embed=embed)
        await ctx.send(f"✅ DM sent to {member.mention}", ephemeral=True)
    except discord.Forbidden:
        await ctx.send(f"❌ Cannot send DM to {member.mention}", ephemeral=True)
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}", ephemeral=True)

@bot_command.command(name="remove_check")
@bot_channel_only()
async def chat_remove_check(ctx, member: discord.Member):
    """Manually remove a user's green check mark reaction."""
    try:
        rules_channel = ctx.guild.get_channel(RULES_CHANNEL_ID)
        if rules_channel:
            rules_message = await rules_channel.fetch_message(RULES_MESSAGE_ID)
            
            # Find and remove green check reaction
            for reaction in rules_message.reactions:
                if str(reaction.emoji) == '✅':
                    await reaction.remove(member)
                    await ctx.send(f"✅ Removed green check mark reaction for {member.mention}")
                    
                    # Clean up user data
                    await cleanup_user_data(member.id)
                    await ctx.send(f"🗑️ Cleaned up data for {member.mention}")
                    return
        
        await ctx.send("❌ Could not find green check mark reaction")
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

@bot_command.command(name="check_consistency")
@bot_channel_only()
async def chat_check_consistency(ctx):
    """Check consistency between registry and green check marks."""
    guild = ctx.guild
    rules_channel = guild.get_channel(RULES_CHANNEL_ID)
    
    if not rules_channel:
        await ctx.send("❌ Rules channel not found")
        return
    
    try:
        rules_message = await rules_channel.fetch_message(RULES_MESSAGE_ID)
        
        # Get users with green check reactions
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
                value="\n".join(missing_check[:10]) + 
                     (f"\n...and {len(missing_check)-10} more" if len(missing_check) > 10 else ""),
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
                    # Check Master Lee's Family role exemption
                    master_lee_family_role = guild.get_role(MASTER_LEE_FAMILY_ROLE_ID)
                    has_master_lee_family = master_lee_family_role and master_lee_family_role in member.roles
                    
                    if has_master_lee_family:
                        print(f"   ✅ {member.name} has Master Lee's Family role, skipping warning")
                        continue
                    
                    # Check if they have family role (completed registration)
                    family_role = guild.get_role(FAMILY_ROLE_ID)
                    has_family_role = family_role and family_role in member.roles
                    
                    if has_family_role:
                        print(f"   ℹ️ {member.name} has family role but not in registry, adding to registry...")
                        # Auto-add to registry
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
                        not_registered.append(f"{member.name} (ID: {user_id})")
        
        if not_registered:
            embed.add_field(
                name="⚠️ Users with green check but NOT registered",
                value="\n".join(not_registered[:10]) + 
                     (f"\n...and {len(not_registered)-10} more" if len(not_registered) > 10 else ""),
                inline=False
            )
        
        embed.set_footer(text=f"Total registered: {len(registered_users)} | Total green checks: {len(green_check_users)}")
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

@bot_command.command(name="fix_name")
@bot_channel_only()
async def chat_fix_name(ctx, member: discord.Member, *, new_name: str):
    """Admin command to fix a user's registered name."""
    user_id_str = str(member.id)
    
    if user_id_str not in registered_users:
        await ctx.send(f"❌ {member.mention} is not registered yet!", ephemeral=True)
        return
    
    # Validate and clean new name
    is_valid, error_msg = validate_name_format(new_name)
    if not is_valid:
        await ctx.send(f"❌ Invalid name: {error_msg}", ephemeral=True)
        return
    
    cleaned_name = clean_name(new_name)
    
    # Update registered data
    old_name = registered_users[user_id_str]['child_name']
    registered_users[user_id_str]['child_name'] = cleaned_name
    
    # Update nickname
    old_nickname = registered_users[user_id_str]['nickname']
    gender = registered_users[user_id_str]['gender']
    
    if gender == 'mother':
        new_nickname = f"{cleaned_name}'s Mother"
    elif gender == 'father':
        new_nickname = f"{cleaned_name}'s Father"
    elif gender == 'grandmother':
        new_nickname = f"{cleaned_name}'s Grandmother"
    else:  # grandfather
        new_nickname = f"{cleaned_name}'s Grandfather"
    
    registered_users[user_id_str]['nickname'] = new_nickname
    
    # Attempt to update server nickname
    try:
        await member.edit(nick=new_nickname, reason="Name correction by admin")
    except discord.Forbidden:
        await ctx.send(f"⚠️ Could not update nickname for {member.mention} due to permissions.", ephemeral=True)
    except Exception as e:
        await ctx.send(f"⚠️ Error updating nickname: {e}", ephemeral=True)
    
    # Save changes
    save_registered_users(registered_users)
    
    # Send confirmation
    embed = discord.Embed(
        title="✅ Name Updated",
        description=f"Updated name for {member.mention}",
        color=discord.Color.green()
    )
    embed.add_field(name="Old Name", value=old_name, inline=True)
    embed.add_field(name="New Name", value=cleaned_name, inline=True)
    embed.add_field(name="Old Nickname", value=old_nickname, inline=False)
    embed.add_field(name="New Nickname", value=new_nickname, inline=False)
    
    await ctx.send(embed=embed)

# =============================================================================
# SETUP COMMANDS
# =============================================================================
@bot_command.command(name="setup")
@bot_channel_only()
async def chat_setup(ctx):
    """Set up the rules message with reaction in rules channel."""
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
    
    # Update configuration
    config['RULES_MESSAGE_ID'] = str(rules_message.id)
    with open('config.txt', 'w') as f:
        for key, value in config.items():
            f.write(f"{key}={value}\n")
    
    await ctx.send(f"✅ Rules message set up! New Message ID: {rules_message.id}")
    print(f"📝 New rules message ID saved: {rules_message.id}")

@bot_command.command(name="setup_bot_channel")
@bot_channel_only()
async def setup_bot_channel_command(ctx):
    """Set up the bot command channel for administrative commands."""
    # Check if already exists
    if BOT_COMMAND_CHANNEL_ID:
        channel = ctx.guild.get_channel(BOT_COMMAND_CHANNEL_ID)
        if channel:
            await ctx.send(f"✅ Bot command channel already exists: {channel.mention}")
            return
    
    # Create private admin-only channel
    overwrites = {
        ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        ctx.guild.get_member(ADMIN_USER_ID): discord.PermissionOverwrite(
            read_messages=True,
            send_messages=True,
            manage_messages=True,
            embed_links=True,
            attach_files=True,
            read_message_history=True
        ),
        ctx.guild.me: discord.PermissionOverwrite(
            read_messages=True,
            send_messages=True,
            manage_messages=True,
            embed_links=True,
            attach_files=True,
            read_message_history=True
        )
    }
    
    try:
        channel = await ctx.guild.create_text_channel(
            name="bot-commands",
            overwrites=overwrites,
            reason="Bot command channel for admin commands",
            topic="💬 Bot command channel for admin commands. Only admin can see and use commands here."
        )
        
        # Update configuration
        config['BOT_COMMAND_CHANNEL_ID'] = str(channel.id)
        with open('config.txt', 'w') as f:
            for key, value in config.items():
                f.write(f"{key}={value}\n")
        
        embed = discord.Embed(
            title="✅ Bot Command Channel Created",
            description=f"Channel: {channel.mention}\n\n"
                      "**Features:**\n"
                      "• Only you and the bot can see this channel\n"
                      "• Manual commands only work here\n"
                      "• Use `!bot_command chat` to see available commands",
            color=discord.Color.green()
        )
        await channel.send(embed=embed)
        
        # Send help in new channel
        await chat_command(channel)
        
    except Exception as e:
        await ctx.send(f"❌ Error creating bot command channel: {e}")

@bot_command.command(name="setup_log_channel")
@bot_channel_only()
async def setup_log_channel_command(ctx):
    """Set up the log channel for bot notifications."""
    # Check if already exists
    if LOG_CHANNEL_ID:
        channel = ctx.guild.get_channel(LOG_CHANNEL_ID)
        if channel:
            await ctx.send(f"✅ Log channel already configured: {channel.mention}")
            return
    
    # Create private log channel
    overwrites = {
        ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        ctx.guild.get_member(ADMIN_USER_ID): discord.PermissionOverwrite(
            read_messages=True,
            send_messages=False,  # Admin doesn't need to send here
            manage_messages=True,
            embed_links=True,
            attach_files=True,
            read_message_history=True
        ),
        ctx.guild.me: discord.PermissionOverwrite(
            read_messages=True,
            send_messages=True,
            manage_messages=True,
            embed_links=True,
            attach_files=True,
            read_message_history=True
        )
    }
    
    try:
        channel = await ctx.guild.create_text_channel(
            name="bot-logs",
            overwrites=overwrites,
            reason="Log channel for bot notifications",
            topic="📋 Bot logs and notifications. All notifications that would go to admin DM will appear here."
        )
        
        # Update configuration
        config['LOG_CHANNEL_ID'] = str(channel.id)
        with open('config.txt', 'w') as f:
            for key, value in config.items():
                f.write(f"{key}={value}\n")
        
        embed = discord.Embed(
            title="✅ Log Channel Created",
            description=f"Channel: {channel.mention}\n\n"
                      "**Features:**\n"
                      "• All bot notifications will appear here\n"
                      "• No more admin DMs for private chat alerts\n"
                      "• Includes: new chats, registrations, deletions, etc.",
            color=discord.Color.green()
        )
        await channel.send(embed=embed)
        
        # Send test log message
        test_embed = discord.Embed(
            title="📋 Log Channel Active",
            description="This channel will now receive all bot notifications.\n\n"
                      "**Notifications include:**\n"
                      "• New private chats created\n"
                      "• User registrations\n"
                      "• Chat deletions\n"
                      "• Member joins/leaves\n"
                      "• Message forwarding logs",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        await channel.send(embed=test_embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error creating log channel: {e}")

# =============================================================================
# GENERAL CHAT COMMANDS
# =============================================================================
@bot_command.command(name="reset_general_permissions")
@bot_channel_only()
async def chat_reset_general_permissions(ctx):
    """Reset all permissions for general-chat channel to default."""
    guild = ctx.guild
    general_chat = guild.get_channel(GENERAL_CHAT_CHANNEL_ID)
    
    if not general_chat:
        await ctx.send("❌ General chat channel not found", ephemeral=True)
        return
    
    try:
        # Reset permissions for @everyone
        await general_chat.set_permissions(
            guild.default_role,
            read_messages=True,
            send_messages=False,
            read_message_history=True,
            reason="Reset to default permissions"
        )
        
        # Reset permissions for family role
        family_role = guild.get_role(FAMILY_ROLE_ID)
        if family_role:
            await general_chat.set_permissions(
                family_role,
                send_messages=False,
                reason="Reset family role permissions"
            )
        
        # Clear all user-specific permissions
        for overwrite in general_chat.overwrites:
            if isinstance(overwrite, discord.Member):
                await general_chat.set_permissions(overwrite, overwrite=None, reason="Clear user permissions")
        
        await ctx.send("✅ Reset all permissions for general-chat channel", ephemeral=True)
        
    except Exception as e:
        await ctx.send(f"❌ Error resetting permissions: {e}", ephemeral=True)

# =============================================================================
# PRIVATE CHAT COMMANDS (NOT RESTRICTED TO BOT CHANNEL)
# =============================================================================

@bot.command(name="close_chat")
async def close_chat(ctx, channel: discord.TextChannel = None):
    """
    Close a private chat channel.
    
    Works in private chats and requires admin authorization.
    """
    if ctx.author.id != ADMIN_USER_ID:
        await ctx.send("❌ This command is only for the admin.", ephemeral=True)
        return
    
    if not channel:
        channel = ctx.channel
    
    if channel.id not in private_channels:
        await ctx.send("❌ This is not a private chat.", ephemeral=True)
        return
    
    # Get channel data
    data = private_channels[channel.id]
    user = ctx.guild.get_member(data['user_id'])
    
    # Show confirmation
    embed = discord.Embed(
        title="🗑️ Delete Private Chat",
        description=f"Are you sure you want to delete **{channel.name}**?\n\n"
                   f"**User:** {user.mention if user else 'Unknown'}\n"
                   f"**Created:** <t:{int(data['created_at'])}:R>\n"
                   f"**This action cannot be undone!** All messages will be permanently deleted.",
        color=discord.Color.red()
    )
    
    view = ConfirmDeleteView(channel.id, data['user_id'])
    await ctx.send(embed=embed, view=view)

# =============================================================================
# PUBLIC COMMANDS
# =============================================================================

@bot.command(name="force_register")
async def force_register(ctx):
    """Force start registration process for the command user."""
    if str(ctx.author.id) in registered_users:
        await ctx.send("✅ You are already registered!", ephemeral=True)
        return
    
    await start_dm_process(ctx.author)
    await ctx.send("📨 Check your DMs to complete registration!", ephemeral=True)

# =============================================================================
# ERROR HANDLING
# =============================================================================

@bot.event
async def on_command_error(ctx, error):
    """
    Global command error handler.
    
    Provides user-friendly error messages for common issues.
    """
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You need admin permissions for this command.", ephemeral=True)
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing required argument: {error.param.name}", ephemeral=True)
    elif isinstance(error, commands.CommandNotFound):
        pass  # Ignore unknown commands
    elif isinstance(error, commands.CheckFailure):
        pass  # Decorator already handles authorization messages
    else:
        print(f"Error: {error}")

# =============================================================================
# BOT STARTUP
# =============================================================================

if __name__ == "__main__":
    """
    Main bot startup sequence with validation and error handling.
    """
    print("\n🚀 Starting Family Registration & Private Chats Bot...")
    print()
    
    # Validate critical configuration
    if not TOKEN:
        print("❌ ERROR: Bot token not found in config.txt")
        print("   Please add: TOKEN=your_bot_token_here")
        exit(1) 

    if not ADMIN_USER_ID:
        print("⚠️ WARNING: ADMIN_USER_ID not set in config.txt")
        print("   Chat forwarding will not work without this!")
        print("   Please add: ADMIN_USER_ID=your_discord_user_id_here")
    
    # Validate private conversation category
    if not PRIVATE_CONVERSATION_CATEGORY_ID:
        print("⚠️ WARNING: PRIVATE_CONVERSATION_CATEGORY_ID not configured")
        print("   Private chats will not be created!")
        print("   Please ensure setup program has run to create the category")
    
    # Start the bot
    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        print("❌ ERROR: Invalid bot token!")
        print("   Please check your token in config.txt")
    except Exception as e:
        print(f"❌ ERROR starting bot: {e}")
