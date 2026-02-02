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
import psutil
import subprocess
import platform

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
AFTER_SCHOOL_ROLE_ID = int(config.get('AFTER_SCHOOL_ROLE_ID', '0'))  # ADD THIS
AFTER_SCHOOL_CHANNEL_ID = int(config.get('AFTER_SCHOOL_CHANNEL_ID', '0'))  # ADD THIS
GENERAL_CHAT_CHANNEL_ID = int(config.get('GENERAL_CHAT_CHANNEL_ID', '0'))
MASTER_LEE_FAMILY_ROLE_ID = int(config.get('MASTER_LEE_FAMILY_ROLE_ID', '0'))
STUDENT_ROLE_ID = int(config.get('STUDENT_ROLE_ID', '0'))
INSTRUCTOR_ROLE_ID = int(config.get('INSTRUCTOR_ROLE_ID', '0'))
ADMIN_USER_ID = int(config.get('ADMIN_USER_ID', '0'))

# Private conversation category ID (already set up by setup program)
PRIVATE_CONVERSATION_CATEGORY_ID = int(config.get('PRIVATE_CONVERSATION_CATEGORY_ID', '0'))

# Command and logging channels
BOT_COMMAND_CHANNEL_ID = int(config.get('COMMAND_CHANNEL_ID', '0'))
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
    Send notification to configured log channel ONLY.
    
    Args:
        guild: Discord guild object
        message: Text message to send
        embed: Optional embed to send
        
    Returns:
        True if sent to log channel, False if failed
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
                # Don't fallback to admin DM
        except Exception as e:
            print(f"❌ Error sending to log channel: {e}")
            # Don't fallback to admin DM
    else:
        print(f"⚠️ LOG_CHANNEL_ID not configured in config.txt")
    
    return False

# =============================================================================
# COMMAND ACCESS CONTROL
# =============================================================================
def bot_channel_only():
    """
    Decorator to restrict commands to bot command channel.
    
    Silently deletes ALL command messages if used in wrong channel.
    """
    async def predicate(ctx):
        # Channel restriction - silently delete if wrong channel
        if ctx.channel.id != BOT_COMMAND_CHANNEL_ID:
            try:
                await ctx.message.delete()
            except:
                pass
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
    """
    
    def __init__(self, user_id: int, child_name: str, role: str, role_display: str, programs_selected: list):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.child_name = child_name
        self.role = role
        self.role_display = role_display
        self.programs_selected = programs_selected
        
        # Format programs for display
        self.programs_text = self.format_programs_text(programs_selected)
    
    def format_programs_text(self, programs_selected: List[str]) -> str:
        """Format programs list for display."""
        if not programs_selected:
            return "No programs selected"
        
        program_list = []
        if "national" in programs_selected:
            program_list.append("National Team 🔴")
        if "demonstration" in programs_selected:
            program_list.append("Demonstration Team 🔵")
        if "after_school" in programs_selected:
            program_list.append("After School 📚")
        return ", ".join(program_list)
    
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
    
    @discord.ui.button(label="🎯 Change Programs", style=discord.ButtonStyle.secondary, emoji="🎯", row=1)
    async def change_programs_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Return to program selection step."""
        await self.go_back_to_step(interaction, "teams", "Step 3: Program Selection")

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
            view = ProgramSelectView(self.user_id, preserved_name, preserved_role)
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
    
    # In RoleConfirmationView.handle_normal_flow method, change to:
    async def handle_normal_flow(self, interaction: discord.Interaction) -> None:
        """Handle role confirmation in normal registration flow."""
        await interaction.response.edit_message(
            content=f"✅ **Step 2 Complete**\n**Role confirmed:** {self.role_display}",
            embed=None,
            view=self
        )
        
        # Proceed to program selection
        await asyncio.sleep(1.5)
        dm_channel = await interaction.user.create_dm()
        
        program_embed = discord.Embed(
            title="Step 3: Program Selection",
            description="Which program(s) is your child currently enrolled in?\n\n"
                    "**THIS IS FOR ANNOUNCEMENT PURPOSES ONLY**.\n\n"
                    "🔴 **National Team**\n"
                    "🔵 **Demonstration Team**\n"
                    "📚 **After School**\n\n"
                    "You can select one, multiple, or none.\n"
                    "**Click 'None' if not enrolled in any program.**\n"
                    "Click **✅ Done** when finished.",
            color=discord.Color.blue()
        )
        
        view = ProgramSelectView(self.user_id, self.child_name, self.role)
        await dm_channel.send(embed=program_embed, view=view)
        
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

class ProgramSelectView(discord.ui.View):
    """View for selecting program enrollments with multi-select capability."""
    
    def __init__(self, user_id: int, child_name: str, role: str):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.child_name = child_name
        self.role = role
        self.selected_programs = set()  # Track selected programs
        self.none_selected = False  # Track if none is selected
    
    @discord.ui.button(label="National Team", style=discord.ButtonStyle.gray, emoji="🔴", row=0)
    async def national_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Toggle National Team selection."""
        await self.toggle_program(interaction, button, "national", "National Team")
    
    @discord.ui.button(label="Demonstration Team", style=discord.ButtonStyle.gray, emoji="🔵", row=0)
    async def demonstration_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Toggle Demonstration Team selection."""
        await self.toggle_program(interaction, button, "demonstration", "Demonstration Team")
    
    @discord.ui.button(label="After School", style=discord.ButtonStyle.gray, emoji="📚", row=1)
    async def after_school_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Toggle After School selection."""
        await self.toggle_program(interaction, button, "after_school", "After School")
    
    @discord.ui.button(label="None", style=discord.ButtonStyle.gray, emoji="❌", row=1)
    async def none_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Toggle None selection."""
        await self.toggle_none(interaction, button)
    
    @discord.ui.button(label="✅ Done", style=discord.ButtonStyle.green, emoji="✅", row=2)
    async def done_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Finalize program selections and show confirmation."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This selection is not for you.", ephemeral=True)
            return
        
        # Check if modifying from final confirmation
        modifying_from_final = False
        if self.user_id in user_states:
            modifying_from_final = user_states[self.user_id].get('modifying_from_final', False)
        
        # Update user state with selected programs
        if self.user_id in user_states:
            user_states[self.user_id]['programs_selected'] = list(self.selected_programs)
            user_states[self.user_id]['waiting_for_programs'] = False
            user_states[self.user_id]['waiting_for_programs_confirmation'] = True
        
        # Disable buttons and show confirmation
        for child in self.children:
            child.disabled = True
        
        # Format programs for display
        programs_text = self.format_programs_text()
        
        embed = discord.Embed(
            title="✅ Programs Selected",
            description=f"You selected: **{programs_text}**\n\n"
                      f"**Is this correct?**",
            color=discord.Color.gold()
        )
        
        confirmation_view = ProgramConfirmationView(
            self.user_id,
            self.child_name,
            self.role,
            list(self.selected_programs),
            modifying_from_final
        )
        
        await interaction.response.edit_message(embed=embed, view=confirmation_view)
        
        print(f"👤 {interaction.user.name} selected programs: {programs_text}")
    
    async def toggle_program(self, interaction: discord.Interaction, button: discord.ui.Button, program: str, program_display: str) -> None:
        """Toggle program selection state."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This selection is not for you.", ephemeral=True)
            return
        
        # If "none" is selected, clear it when selecting a program
        if self.none_selected:
            self.none_selected = False
            # Reset none button style
            for child in self.children:
                if hasattr(child, 'label') and child.label and child.label.replace("✓ ", "") == "None":
                    child.style = discord.ButtonStyle.gray
                    child.label = "None"
        
        # Toggle program in selection set
        if program in self.selected_programs:
            self.selected_programs.remove(program)
            # Find the correct button and update its style
            for child in self.children:
                if hasattr(child, 'label') and child.label and program_display in child.label:
                    child.style = discord.ButtonStyle.gray
                    child.label = child.label.replace("✓ ", "")
            print(f"👤 {interaction.user.name} deselected {program_display}")
        else:
            self.selected_programs.add(program)
            # Find the correct button and update its style
            for child in self.children:
                if hasattr(child, 'label') and child.label and program_display in child.label:
                    child.style = discord.ButtonStyle.green
                    child.label = f"✓ {program_display}"
            print(f"👤 {interaction.user.name} selected {program_display}")
        
        # Update button appearance
        await interaction.response.edit_message(view=self)
    
    async def toggle_none(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Toggle None selection (exclusive with other programs)."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This selection is not for you.", ephemeral=True)
            return
        
        if self.none_selected:
            # Deselect none
            self.none_selected = False
            # Find the None button and update its style
            for child in self.children:
                if hasattr(child, 'label') and child.label and child.label.replace("✓ ", "") == "None":
                    child.style = discord.ButtonStyle.gray
                    child.label = "None"
        else:
            # Select none (clear all other selections)
            self.none_selected = True
            self.selected_programs.clear()
            
            # Find the None button and update its style
            for child in self.children:
                if hasattr(child, 'label') and child.label and child.label.replace("✓ ", "") == "None":
                    child.style = discord.ButtonStyle.green
                    child.label = "✓ None"
                
                # Reset all other program buttons (excluding Done button)
                if hasattr(child, 'label') and child.label and child.label.replace("✓ ", "") not in ["None", "✅ Done"]:
                    child.style = discord.ButtonStyle.gray
                    child.label = child.label.replace("✓ ", "")
        
        print(f"👤 {interaction.user.name} {'selected' if self.none_selected else 'deselected'} None")
        
        # Update button appearance
        await interaction.response.edit_message(view=self)
    
    def format_programs_text(self) -> str:
        """Format selected programs for display."""
        if self.none_selected:
            return "No programs selected"
        
        if not self.selected_programs:
            return "No programs selected"
        
        program_list = []
        if "national" in self.selected_programs:
            program_list.append("National Team 🔴")
        if "demonstration" in self.selected_programs:
            program_list.append("Demonstration Team 🔵")
        if "after_school" in self.selected_programs:
            program_list.append("After School 📚")
        
        return ", ".join(program_list)

class ProgramConfirmationView(discord.ui.View):
    """View for confirming selected program enrollments."""
    
    def __init__(self, user_id: int, child_name: str, role: str, programs_selected: list, modifying_from_final: bool = False):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.child_name = child_name
        self.role = role
        self.programs_selected = programs_selected
        self.modifying_from_final = modifying_from_final
        self.programs_text = self.format_programs_text(programs_selected)
    
    @discord.ui.button(label="✅ Yes, This is Correct", style=discord.ButtonStyle.green, emoji="✅", row=0)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirm program selections and proceed."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This confirmation is not for you.", ephemeral=True)
            return
        
        # Update user state based on flow
        if self.user_id in user_states:
            user_states[self.user_id]['waiting_for_programs_confirmation'] = False
            
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
        """Handle program confirmation when modifying from final step."""
        await interaction.response.edit_message(
            content=f"✅ **Programs updated:** {self.programs_text}",
            embed=None,
            view=self
        )
        
        # Return to final confirmation
        await asyncio.sleep(1.5)
        await self.return_to_final_confirmation(interaction.user)
    
    async def handle_normal_flow(self, interaction: discord.Interaction) -> None:
        """Handle program confirmation in normal registration flow."""
        await interaction.response.edit_message(
            content=f"✅ **Step 3 Complete**\n**Programs confirmed:** {self.programs_text}",
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
        view = FinalConfirmationView(self.user_id, child_name, self.role, role_display, self.programs_selected)
        await dm_channel.send(embed=final_embed, view=view)
        
        print(f"👤 {user.name} updated programs and returned to final confirmation")
    
    async def send_final_confirmation(self, user: discord.User) -> None:
        """Send final confirmation view in normal flow."""
        dm_channel = await user.create_dm()
        
        # Get user data for final confirmation
        user_data = user_states.get(self.user_id, {})
        child_name = user_data.get('child_name', 'Unknown')
        role_display = user_data.get('role_display', 'Unknown')
        
        # Create and send final confirmation
        final_embed = self.create_final_confirmation_embed(child_name, role_display)
        view = FinalConfirmationView(self.user_id, child_name, self.role, role_display, self.programs_selected)
        await dm_channel.send(embed=final_embed, view=view)
        
        print(f"👤 {user.name} confirmed programs, moving to final confirmation")
    
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
        embed.add_field(name="🎯 Selected Programs", value=f"```{self.programs_text}```", inline=False)
        embed.set_footer(text="Take a moment to review before confirming!")
        
        return embed
    
    def get_role_emoji(self, role: str) -> str:
        """Get appropriate emoji for role."""
        emoji_map = {
            "mother": "👩",
            "father": "👨",
            "grandmother": "👵",
            "grandfather": "👴",
            "student": "🎓"
        }
        return emoji_map.get(role, "👤")
    
    def format_programs_text(self, programs_selected: List[str]) -> str:
        """Format programs list for display."""
        if not programs_selected:
            return "No programs selected"
        
        program_list = []
        if "national" in programs_selected:
            program_list.append("National Team 🔴")
        if "demonstration" in programs_selected:
            program_list.append("Demonstration Team 🔵")
        if "after_school" in programs_selected:
            program_list.append("After School 📚")
        return ", ".join(program_list)
    
    @discord.ui.button(label="✏️ No, I Need to Fix It", style=discord.ButtonStyle.gray, emoji="✏️", row=1)
    async def fix_it_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Allow user to re-select programs."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ This confirmation is not for you.", ephemeral=True)
            return
        
        # Reset program selection state
        if self.user_id in user_states:
            user_states[self.user_id]['waiting_for_programs_confirmation'] = False
            user_states[self.user_id]['waiting_for_programs'] = True
            user_states[self.user_id]['programs_selected'] = []
        
        # Disable buttons and restart program selection
        for child in self.children:
            child.disabled = True
        
        await interaction.response.edit_message(
            content="🔄 Let's select programs again...",
            embed=None,
            view=self
        )
        
        # Send program selection again
        await asyncio.sleep(1.5)
        dm_channel = await interaction.user.create_dm()
        
        program_embed = discord.Embed(
            title="Step 3: Program Selection",
            description="Which program(s) is your child currently enrolled in?\n\n"
                    "**THIS IS FOR ANNOUNCEMENT PURPOSES ONLY**.\n\n"
                    "🔴 **National Team**\n"
                    "🔵 **Demonstration Team**\n"
                    "📚 **After School**\n\n"
                    "You can select one, multiple, or none.\n"
                    "**Click 'None' if not enrolled in any program.**\n"
                    "Click **✅ Done** when finished.",
            color=discord.Color.blue()
        )
        
        view = ProgramSelectView(self.user_id, self.child_name, self.role)
        await dm_channel.send(embed=program_embed, view=view)

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
        """Handle delete channel request - admin and Master Lee's Family only."""
        # Authorization check
        master_lee_family_role = interaction.guild.get_role(MASTER_LEE_FAMILY_ROLE_ID)
        is_master_lee_family = master_lee_family_role and master_lee_family_role in interaction.user.roles
        
        if interaction.user.id != ADMIN_USER_ID and not is_master_lee_family:
            await interaction.response.send_message(
                "❌ Only admin and Master Lee's Family role members can delete this private chat channel.",
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
        
        print(f"🔄 {'Admin' if interaction.user.id == ADMIN_USER_ID else 'Master Lee Family member'} requested deletion for channel #{channel.name}")

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
        master_lee_family_role = interaction.guild.get_role(MASTER_LEE_FAMILY_ROLE_ID)
        is_master_lee_family = master_lee_family_role and master_lee_family_role in interaction.user.roles
        
        if interaction.user.id != ADMIN_USER_ID and not is_master_lee_family:
            # Try to notify via DM since channel might be deleted
            try:
                admin_dm = await interaction.user.create_dm()
                await admin_dm.send("❌ Only admin and Master Lee's Family can delete this channel.")
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
            
            # TICKER SYSTEM: Reset the ticker before deleting channel
            user_id_str = str(self.user_id)
            if user_id_str in registered_users:
                registered_users[user_id_str]['has_active_private_chat'] = False
                registered_users[user_id_str]['private_chat_channel_id'] = None
                save_registered_users(registered_users)
            
            # Send immediate response before deletion
            await interaction.response.send_message(
                "🗑️ Deleting channel...",
                ephemeral=True
            )
            
            # Brief delay to ensure response is sent
            await asyncio.sleep(0.5)
            
            # Delete the channel
            await channel.delete(reason=f"Private chat deleted by {'admin' if interaction.user.id == ADMIN_USER_ID else 'Master Lee Family member'}")
            
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
                        f"**By:** {interaction.user.mention} ({'Admin' if interaction.user.id == ADMIN_USER_ID else 'Master Lee Family'})",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            await send_to_log_channel(interaction.guild, "", embed)
            
            print(f"🗑️ Private channel deleted by {'admin' if interaction.user.id == ADMIN_USER_ID else 'Master Lee Family member'} for user: {user.name if user else 'Unknown'}")
            
        except Exception as e:
            print(f"❌ Error in confirm_button: {e}")
            
            # Only log to log channel, no DM fallback
            error_embed = discord.Embed(
                title="❌ Error Deleting Channel",
                description=f"**Error:** {str(e)[:1000]}\n"
                        f"**Channel ID:** {self.channel_id}\n"
                        f"**User:** {interaction.user.mention}",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            await send_to_log_channel(interaction.guild, "", error_embed)
            
            # Try to update the interaction response if possible
            try:
                await interaction.edit_original_response(
                    content=f"❌ Error deleting channel: {e}"
                )
            except:
                pass

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel the deletion operation."""
        master_lee_family_role = interaction.guild.get_role(MASTER_LEE_FAMILY_ROLE_ID)
        is_master_lee_family = master_lee_family_role and master_lee_family_role in interaction.user.roles
        
        if interaction.user.id != ADMIN_USER_ID and not is_master_lee_family:
            await interaction.response.send_message("❌ Only admin and Master Lee's Family can cancel this action.", ephemeral=True)
            return
        
        self.confirmed = False
        self.stop()
        
        await interaction.response.edit_message(content="✅ Deletion cancelled.", embed=None, view=None)

class GeneralChatButtonView(discord.ui.View):
    """
    View for the general-chat button that creates private chats.
    
    This button replaces the old typing/reaction system.
    """
    
    def __init__(self):
        super().__init__(timeout=None)  # Permanent view
    
    @discord.ui.button(label="📩 Request Private Chat", style=discord.ButtonStyle.primary, custom_id="request_private_chat", emoji="📩")
    async def request_private_chat_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle private chat request button press."""
        # Defer the response since we need time to create the channel
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        user = interaction.user
        
        print(f"📩 {user.name} clicked the private chat request button")
        
        # Check if user is allowed (has Family Member, Student, or Instructor role)
        allowed_roles = [FAMILY_ROLE_ID, STUDENT_ROLE_ID, INSTRUCTOR_ROLE_ID, MASTER_LEE_FAMILY_ROLE_ID]
        user_roles = [role.id for role in user.roles]
        
        has_allowed_role = any(role_id in user_roles for role_id in allowed_roles if role_id != 0)
        
        if not has_allowed_role:
            # Check if they're a registered user
            is_registered = str(user.id) in registered_users
            
            if not is_registered:
                await interaction.followup.send(
                    "❌ You need to complete registration first! Please react with ✅ in the rules channel to begin.",
                    ephemeral=True
                )
                return
        
        # TICKER SYSTEM: Check if user already has an active private chat
        user_id_str = str(user.id)
        if user_id_str in registered_users:
            user_data = registered_users[user_id_str]
            
            # Check if they have an active private chat according to ticker
            if user_data.get('has_active_private_chat', False) and user_data.get('private_chat_channel_id'):
                channel_id = user_data['private_chat_channel_id']
                existing_channel = guild.get_channel(channel_id)
                
                if existing_channel:
                    # Channel exists and ticker says it's active
                    # Simply return without sending any message
                    return
        
        # Create new private chat
        private_chat = await create_private_channel(guild, user, "general-chat-button")
        
        if not private_chat:
            await interaction.followup.send(
                "❌ Failed to create private chat. Please contact an administrator.",
                ephemeral=True
            )
            return
        
        # Update ticker in registered users
        if user_id_str in registered_users:
            registered_users[user_id_str]['has_active_private_chat'] = True
            registered_users[user_id_str]['private_chat_channel_id'] = private_chat.id
            save_registered_users(registered_users)
        
        # Return without sending the instructions message
        return
    
# =============================================================================
# RULES CHANNEL REGISTRATION BUTTON
# =============================================================================
class RulesRegistrationView(discord.ui.View):
    """
    Permanent view for the rules channel with a registration button.
    Replaces the old green check reaction system.
    """
    
    def __init__(self):
        super().__init__(timeout=None)  # Permanent view
    
    @discord.ui.button(label="✅ Register Now", style=discord.ButtonStyle.green, custom_id="rules_register_button", emoji="✅", row=0)
    async def register_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle registration button press in rules channel."""
        # Defer the response since we need time to process
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        user = interaction.user
        
        print(f"📝 {user.name} clicked registration button in rules channel")
        
        # Check if user is already registered
        user_id_str = str(user.id)
        if user_id_str in registered_users:
            await interaction.followup.send(
                "✅ You are already registered! No need to register again.",
                ephemeral=True
            )
            return
        
        # Check if user has Master Lee's Family role (exempt from registration)
        master_lee_family_role = guild.get_role(MASTER_LEE_FAMILY_ROLE_ID)
        if master_lee_family_role and master_lee_family_role in user.roles:
            await interaction.followup.send(
                "👑 As a Master Lee's Family member, you don't need to complete registration!",
                ephemeral=True
            )
            return
        
        # Check if user is instructor (exempt from registration)
        instructor_role = guild.get_role(INSTRUCTOR_ROLE_ID)
        if instructor_role and instructor_role in user.roles:
            await interaction.followup.send(
                "👨‍🏫 As an instructor, you don't need to complete registration!",
                ephemeral=True
            )
            return
        
        # Start registration process
        await log_registration_start(guild, user)
        await start_dm_process(user)
        
        await interaction.followup.send(
            "📨 **Registration started!** Check your DMs to complete the process.",
            ephemeral=True
        )
    
    @discord.ui.button(label="📋 Registration Guide", style=discord.ButtonStyle.secondary, custom_id="registration_guide_button", emoji="📋", row=1)
    async def guide_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show registration guide and instructions."""
        embed = discord.Embed(
            title="📋 Registration Guide",
            description="**Step-by-step registration process:**\n\n"
                      "1. **Click '✅ Register Now' button above**\n"
                      "2. **Check your DMs** - 백호 (baekho) will message you\n"
                      "3. **Follow the DM prompts** to enter:\n"
                      "   • Your child's name\n"
                      "   • Your role (mother/father/grandparent/student)\n"
                      "   • Programs your child is in\n"
                      "4. **Review and confirm** your information\n\n"
                      "**After registration:**\n"
                      "• You'll get access to the server\n"
                      "• Use the 📩 button in general-chat to talk to us\n"
                      "• Your nickname will be updated automatically\n"
                      "• You'll be added to relevant announcement channels",
            color=discord.Color.blue()
        )
        
        embed.set_footer(text="Need help? Contact an admin.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

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
    - Ticker system to prevent duplicate channels
    
    Args:
        guild: Discord guild object
        user: Member to create channel for
        original_channel_name: Source channel name for context
        
    Returns:
        Created text channel or None on error
    """
    try:
        # TICKER SYSTEM: Check registered_users.json first for existing channel
        user_id_str = str(user.id)
        
        # If user is registered, check if they have an active private chat ticker
        if user_id_str in registered_users:
            user_data = registered_users[user_id_str]
            
            # Check if ticker says they have an active chat
            has_active_ticker = user_data.get('has_active_private_chat', False)
            channel_id = user_data.get('private_chat_channel_id')
            
            if has_active_ticker and channel_id:
                # Ticker says they have an active chat - check if channel exists
                channel = guild.get_channel(channel_id)
                
                if channel:
                    # Channel exists and ticker is correct
                    # Update activity timestamp
                    private_channels[channel_id]['last_activity'] = time.time()
                    print(f"✅ Using existing channel from ticker: #{channel.name} for {user.name}")
                    return channel
                else:
                    # Channel doesn't exist but ticker says it should
                    # This means channel was deleted manually or by Discord
                    print(f"⚠️ Ticker inconsistency: Channel {channel_id} doesn't exist for {user.name}")
                    
                    # Clear the ticker since channel doesn't exist
                    registered_users[user_id_str]['has_active_private_chat'] = False
                    registered_users[user_id_str]['private_chat_channel_id'] = None
                    save_registered_users(registered_users)
        
        # SECONDARY CHECK: Check for existing channel in memory (backup check)
        if user.id in user_private_channels:
            channel_id = user_private_channels[user.id]
            channel = guild.get_channel(channel_id)
            
            if channel:
                # Channel exists in memory tracking
                # Update activity timestamp
                private_channels[channel_id]['last_activity'] = time.time()
                
                # Also update the ticker in registered_users.json for consistency
                if user_id_str in registered_users:
                    registered_users[user_id_str]['has_active_private_chat'] = True
                    registered_users[user_id_str]['private_chat_channel_id'] = channel_id
                    save_registered_users(registered_users)
                
                print(f"✅ Using existing channel from memory: #{channel.name} for {user.name}")
                return channel
            else:
                # Channel exists in memory but not in Discord
                # Clean up the memory tracking
                if channel_id in private_channels:
                    del private_channels[channel_id]
                del user_private_channels[user.id]
        
        # Get private conversation category from config
        if not PRIVATE_CONVERSATION_CATEGORY_ID:
            print("❌ PRIVATE_CONVERSATION_CATEGORY_ID not configured in config.txt")
            return None
        
        category = guild.get_channel(PRIVATE_CONVERSATION_CATEGORY_ID)
        if not category or not isinstance(category, discord.CategoryChannel):
            print(f"❌ Private conversation category not found with ID: {PRIVATE_CONVERSATION_CATEGORY_ID}")
            print("   Please ensure setup program has run and category exists")
            return None
                
        # Configure channel permissions
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                read_messages=False, 
                read_message_history=False
            ),
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

        # Add Master Lee's Family role with FULL permissions (including delete)
        master_lee_family_role = guild.get_role(MASTER_LEE_FAMILY_ROLE_ID)
        if master_lee_family_role:
            overwrites[master_lee_family_role] = discord.PermissionOverwrite(
                read_messages=True, 
                send_messages=True, 
                read_message_history=True,
                manage_channels=True,
                manage_messages=True,
                manage_permissions=True,
                attach_files=True,
                embed_links=True
            )
        
        # Create sanitized channel name
        # Remove special characters and limit length
        sanitized_name = user.display_name.lower().replace(' ', '-')
        sanitized_name = ''.join(c for c in sanitized_name if c.isalnum() or c == '-')
        sanitized_name = sanitized_name[:20]  # Discord limit is 100, but we'll keep it short
        
        # Ensure the name starts with 'private-'
        if not sanitized_name.startswith('private-'):
            channel_name = f"private-{sanitized_name}"
        else:
            channel_name = sanitized_name
        
        # Make sure channel name is unique by adding timestamp if needed
        existing_names = [ch.name for ch in category.channels if isinstance(ch, discord.TextChannel)]
        if channel_name in existing_names:
            # Add timestamp to make it unique
            timestamp = str(int(time.time()))[-4:]  # Last 4 digits of timestamp
            channel_name = f"{channel_name}-{timestamp}"
        
        # Create the channel
        channel = await category.create_text_channel(
            name=channel_name,
            overwrites=overwrites,
            reason=f"Private conversation for {user.name}",
            topic=f"Private conversation with {user.name} | From: {original_channel_name} | Created: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )
        
        # Store channel metadata in memory
        current_time = time.time()
        private_channels[channel.id] = {
            'user_id': user.id,
            'created_at': current_time,
            'last_activity': current_time,
            'pinned_message_id': None,  # Will be set after creating pinned message
            'original_channel': original_channel_name,
            'user_name': user.name,
            'channel_name': channel_name
        }
        user_private_channels[user.id] = channel.id
        
        # TICKER SYSTEM: Update ticker in registered users
        if user_id_str in registered_users:
            registered_users[user_id_str]['has_active_private_chat'] = True
            registered_users[user_id_str]['private_chat_channel_id'] = channel.id
            save_registered_users(registered_users)
        else:
            # User is not in registered_users.json (might be Master Lee's Family or other special case)
            print(f"⚠️ User {user.name} not in registered_users.json, but creating channel anyway")
            
            # Create a minimal entry for them
            registered_users[user_id_str] = {
                'child_name': user.name,
                'role': 'Special',
                'role_display': 'Special User',
                'nickname': user.display_name,
                'gender': 'unknown',
                'teams': [],
                'registered_at': discord.utils.utcnow().isoformat(),
                'has_active_private_chat': True,
                'private_chat_channel_id': channel.id,
                'auto_added': True
            }
            save_registered_users(registered_users)
        
        # Create and pin permanent delete button
        delete_view = PermanentDeleteChannelView(channel.id, user.id)
        delete_embed = discord.Embed(
            title="🗑️ Admin Delete Button",
            description="This button is permanently available for admin to delete this private chat.\n\n"
                       "**Who can use this button:**\n"
                       "• Server Admin\n"
                       "• Master Lee's Family members\n\n"
                       "**Important:**\n"
                       "• Do NOT create new private chats\n"
                       "• Use this channel for all communication\n"
                       "• Only admins can delete this channel",
            color=discord.Color.red()
        )
        delete_embed.set_footer(text="This button will always be available at the top of this channel")
        
        delete_message = await channel.send(embed=delete_embed, view=delete_view)
        await delete_message.pin()
        private_channels[channel.id]['pinned_message_id'] = delete_message.id
        
        # Send welcome message
        welcome_embed = discord.Embed(
            title="🔒 Private Conversation",
            description=f"Welcome to your private conversation channel, {user.mention}!\n\n"
                      f"• Created from: #{original_channel_name}\n"
                      f"• Created at: <t:{int(current_time)}:F>\n"
                      f"**Please send your message here!**",
            color=discord.Color.blue()
        )
                    
        await channel.send(embed=welcome_embed)
        
        # Log channel creation
        embed = discord.Embed(
            title="🔔 New Private Chat Created",
            description=f"**User:** {user.mention} ({user.id})\n"
                      f"**From:** #{original_channel_name}\n"
                      f"**Channel:** #{channel.name} ({channel.id})\n"
                      f"**Created:** <t:{int(current_time)}:R>\n\n"
                      f"A permanent delete button is pinned at the top (admin only).",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        await send_to_log_channel(guild, "", embed)
        
        print(f"🔒 Created private chat for {user.name} with permanent delete button")
        print(f"   Channel: #{channel.name} (ID: {channel.id})")
        print(f"   Ticker updated: has_active_private_chat = True")
        
        return channel
        
    except discord.Forbidden as e:
        print(f"❌ Permission error creating private chat: {e}")
        print(f"   Make sure the bot has 'Manage Channels' permission")
        return None
    except discord.HTTPException as e:
        if e.status == 429:  # Rate limit
            print(f"⏳ Rate limited, retry after: {e.retry_after} seconds")
            await asyncio.sleep(e.retry_after)
            
            # Try to create again after rate limit
            try:
                print("🔄 Retrying channel creation after rate limit...")
                return await create_private_channel(guild, user, original_channel_name)
            except Exception as retry_error:
                print(f"❌ Retry failed: {retry_error}")
                return None
        else:
            print(f"❌ Discord API error creating private chat: {e}")
            return None
    except Exception as e:
        print(f"❌ Unexpected error creating private chat: {e}")
        print(f"   Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return None
    
async def reinitialize_private_chat_views():
    """
    Re-register persistent delete button views for existing private chats.
    This is necessary when the bot restarts to maintain button functionality.
    """
    if not PRIVATE_CONVERSATION_CATEGORY_ID:
        print("⚠️ PRIVATE_CONVERSATION_CATEGORY_ID not configured, cannot reinitialize views")
        return
    
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        print("❌ Guild not found for reinitializing views")
        return
    
    category = guild.get_channel(PRIVATE_CONVERSATION_CATEGORY_ID)
    if not category or not isinstance(category, discord.CategoryChannel):
        print(f"❌ Private conversation category not found: {PRIVATE_CONVERSATION_CATEGORY_ID}")
        return
    
    print(f"🔄 Reinitializing delete button views for private chats in category: {category.name}")
    
    # Load registered users to get user IDs for existing channels
    registered_users = load_registered_users()
    
    # Clear and rebuild tracking dictionaries
    private_channels.clear()
    user_private_channels.clear()
    
    # Scan all channels in the private conversation category
    for channel in category.channels:
        if isinstance(channel, discord.TextChannel) and channel.name.startswith("private-"):
            print(f"  🔍 Found existing private chat: #{channel.name}")
            
            # Try to extract user ID from channel name or topic
            user_id = None
            
            # Method 1: Check if user exists in registered_users and has this channel ID
            for user_id_str, user_data in registered_users.items():
                if user_data.get('private_chat_channel_id') == channel.id:
                    user_id = int(user_id_str)
                    break
            
            # Method 2: Extract from channel topic if possible
            if not user_id and channel.topic:
                import re
                # Look for user ID in the topic
                match = re.search(r'User ID: (\d+)', channel.topic)
                if match:
                    user_id = int(match.group(1))
            
            # Method 3: Extract from channel permissions
            if not user_id:
                for member_id, perms in channel.overwrites.items():
                    if isinstance(member_id, discord.Member) and perms.read_messages:
                        # Check if this is a regular user (not admin/Master Lee's Family)
                        if member_id.id != ADMIN_USER_ID:
                            master_lee_family_role = guild.get_role(MASTER_LEE_FAMILY_ROLE_ID)
                            if not master_lee_family_role or master_lee_family_role not in member_id.roles:
                                user_id = member_id.id
                                break
            
            if user_id:
                # Rebuild the tracking data
                current_time = time.time()
                private_channels[channel.id] = {
                    'user_id': user_id,
                    'created_at': current_time,
                    'last_activity': current_time,
                    'pinned_message_id': None,
                    'original_channel': 'existing',
                    'user_name': guild.get_member(user_id).name if guild.get_member(user_id) else 'Unknown',
                    'channel_name': channel.name
                }
                user_private_channels[user_id] = channel.id
                
                print(f"    ✅ Re-registered view for user ID: {user_id}")
                
                # Update ticker in registered_users if needed
                user_id_str = str(user_id)
                if user_id_str in registered_users:
                    registered_users[user_id_str]['has_active_private_chat'] = True
                    registered_users[user_id_str]['private_chat_channel_id'] = channel.id
                else:
                    # Create entry for user if not in registry
                    registered_users[user_id_str] = {
                        'child_name': guild.get_member(user_id).name if guild.get_member(user_id) else 'Unknown',
                        'role': 'Existing',
                        'role_display': 'Existing User',
                        'nickname': guild.get_member(user_id).display_name if guild.get_member(user_id) else 'Unknown',
                        'gender': 'unknown',
                        'teams': [],
                        'registered_at': discord.utils.utcnow().isoformat(),
                        'has_active_private_chat': True,
                        'private_chat_channel_id': channel.id,
                        'auto_added': True,
                        'existing_channel': True
                    }
                
                # Re-register the persistent delete button view
                delete_view = PermanentDeleteChannelView(channel.id, user_id)
                bot.add_view(delete_view)
                
                # Check if channel already has a delete button pinned
                try:
                    pinned_messages = await channel.pins()
                    delete_button_found = False
                    
                    for pinned_msg in pinned_messages:
                        if pinned_msg.author == bot.user and pinned_msg.embeds:
                            for embed in pinned_msg.embeds:
                                if embed.title and "Admin Delete Button" in embed.title:
                                    delete_button_found = True
                                    private_channels[channel.id]['pinned_message_id'] = pinned_msg.id
                                    
                                    # Edit the existing pinned message to update the view
                                    await pinned_msg.edit(view=delete_view)
                                    print(f"    ✅ Updated existing delete button in #{channel.name}")
                                    break
                        
                        if delete_button_found:
                            break
                    
                    if not delete_button_found:
                        # Send new delete button and pin it
                        delete_embed = discord.Embed(
                            title="🗑️ Admin Delete Button",
                            description="This button is permanently available for admin to delete this private chat.\n\n"
                                       "**Who can use this button:**\n"
                                       "• Server Admin\n"
                                       "• Master Lee's Family members\n\n"
                                       "**Important:**\n"
                                       "• Do NOT create new private chats\n"
                                       "• Use this channel for all communication\n"
                                       "• Only admins can delete this channel",
                            color=discord.Color.red()
                        )
                        delete_embed.set_footer(text="This button will always be available at the top of this channel")
                        
                        delete_message = await channel.send(embed=delete_embed, view=delete_view)
                        await delete_message.pin()
                        private_channels[channel.id]['pinned_message_id'] = delete_message.id
                        print(f"    ✅ Created new delete button for #{channel.name}")
                
                except Exception as e:
                    print(f"    ❌ Error reinitializing delete button for #{channel.name}: {e}")
            else:
                print(f"    ⚠️ Could not determine user for channel #{channel.name}")
    
    # Save updated registered users
    save_registered_users(registered_users)
    print(f"✅ Reinitialization complete. Found {len(private_channels)} existing private chats.")

def migrate_existing_users():
    """Migrate existing registered users to include proper structure."""
    try:
        with open(REGISTRY_FILE, 'r') as f:
            users = json.load(f)
        
        needs_update = False
        for user_id, user_data in users.items():
            # Check if user has old structure
            if 'teams' in user_data and 'programs' not in user_data:
                # Rename 'teams' to 'programs'
                user_data['programs'] = user_data['teams']
                del user_data['teams']
                needs_update = True
            
            # Ensure 'roles' field exists and is a list
            if 'roles' not in user_data:
                user_data['roles'] = []
                needs_update = True
            
            # Ensure 'has_active_private_chat' field exists
            if 'has_active_private_chat' not in user_data:
                user_data['has_active_private_chat'] = False
                needs_update = True
            
            # Ensure 'private_chat_channel_id' field exists
            if 'private_chat_channel_id' not in user_data:
                user_data['private_chat_channel_id'] = None
                needs_update = True
            
            # Ensure 'registered_at' is in correct format (if missing)
            if 'registered_at' not in user_data:
                user_data['registered_at'] = discord.utils.utcnow().isoformat()
                needs_update = True
        
        if needs_update:
            with open(REGISTRY_FILE, 'w') as f:
                json.dump(users, f, indent=2)
            print("✅ Migrated existing users to new structure")
        else:
            print("✅ All users already have new structure")
    except (FileNotFoundError, json.JSONDecodeError):
        print("⚠️ No existing users to migrate or error reading file")

async def cleanup_user_data(user_id: int) -> None:
    """
    Clean up all data associated with a user when they leave.
    
    Removes:
    - Registration data
    - User state tracking
    - Active conversations
    - Private chat references
    """
    user_id_str = str(user_id)
    
    # Remove from registered users
    if user_id_str in registered_users:
        # Log the roles being removed
        stored_roles = registered_users[user_id_str].get('roles', [])
        print(f"🗑️ Removing user with roles: {stored_roles}")
        
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
    

async def verify_green_check_consistency(guild: discord.Guild, rules_channel: Optional[discord.TextChannel]) -> None:
    """
    Verify consistency between registry and server members.
    
    NEW LOGIC: Compares users in Discord with JSON file only.
    Green check reactions are no longer used.
    """
    if not rules_channel:
        return
    
    try:
        print(f"\n🔍 Checking registration status based on JSON registry...")
        print(f"   Found {len(registered_users)} users in JSON registry")
        
        # Get all server members (excluding bots)
        all_members = [member for member in guild.members if not member.bot]
        print(f"   Found {len(all_members)} non-bot members in server")
        
        # Check 1: Users in server but NOT in JSON (unregistered)
        users_not_in_json = []
        for member in all_members:
            user_id_str = str(member.id)
            
            # Skip Master Lee's Family members (exempt from registration)
            master_lee_family_role = guild.get_role(MASTER_LEE_FAMILY_ROLE_ID)
            is_master_lee_family = master_lee_family_role and master_lee_family_role in member.roles
            
            # Skip admin
            is_admin = member.id == ADMIN_USER_ID
            
            # Skip if already in JSON
            if user_id_str in registered_users:
                continue
            
            # Skip exempt users
            if is_master_lee_family or is_admin:
                continue
            
            # Skip instructors
            instructor_role = guild.get_role(INSTRUCTOR_ROLE_ID)
            if instructor_role and instructor_role in member.roles:
                continue
            
            # User is in server but not in JSON (and not exempt)
            users_not_in_json.append(member)
        
        # Check 2: Users in JSON but NOT in server (left server)
        users_not_in_server = []
        for user_id_str in registered_users.keys():
            user_id = int(user_id_str)
            member = guild.get_member(user_id)
            if not member:
                users_not_in_server.append(user_id_str)
        
        # PRINT ALL UNREGISTERED USERS WITHOUT TRUNCATION
        print(f"\n🔴 UNREGISTERED USERS (in server but NOT in JSON): {len(users_not_in_json)}")
        if users_not_in_json:
            print("   List of all unregistered users:")
            for i, member in enumerate(sorted(users_not_in_json, key=lambda x: x.name.lower()), 1):
                # Get their roles (excluding @everyone)
                member_roles = [role.name for role in member.roles if role.name != "@everyone"]
                roles_text = f", Roles: {', '.join(member_roles)}" if member_roles else ""
                
                print(f"   {i:3d}. {member.name} (ID: {member.id}){roles_text}")
        else:
            print("   ✅ All users in server are registered!")
        
        # PRINT ALL USERS IN JSON BUT NOT IN SERVER
        print(f"\n🔵 USERS IN JSON BUT NOT IN SERVER: {len(users_not_in_server)}")
        if users_not_in_server:
            print("   List of all registered users who left the server:")
            for i, user_id_str in enumerate(users_not_in_server, 1):
                user_data = registered_users[user_id_str]
                child_name = user_data.get('child_name', 'Unknown')
                role_display = user_data.get('role_display', 'Unknown')
                print(f"   {i:3d}. {child_name}'s {role_display} (ID: {user_id_str})")
        else:
            print("   ✅ All registered users are still in the server!")
        
        # Summary statistics
        registered_in_server = len([m for m in all_members if str(m.id) in registered_users])
        print(f"\n📈 SUMMARY:")
        print(f"   Registered and in server: {registered_in_server}")
        print(f"   Unregistered in server: {len(users_not_in_json)}")
        print(f"   Registered but left server: {len(users_not_in_server)}")
        
        # Log detailed report to log channel
        embed = discord.Embed(
            title="🔍 Registration Consistency Check",
            description=f"**Comprehensive registration verification completed**",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(
            name="📊 Statistics",
            value=(
                f"• **Total server members:** {len(all_members)}\n"
                f"• **Registered in JSON:** {len(registered_users)}\n"
                f"• **Registered & in server:** {registered_in_server}\n"
                f"• **Unregistered in server:** {len(users_not_in_json)}\n"
                f"• **Registered but left:** {len(users_not_in_server)}"
            ),
            inline=False
        )
        
        # For log channel, we'll list all unregistered users
        if users_not_in_json:
            # Create a string with all unregistered users
            unregistered_list = ""
            for i, member in enumerate(sorted(users_not_in_json, key=lambda x: x.name.lower()), 1):
                # Get member roles
                member_roles = [role.name for role in member.roles if role.name != "@everyone"]
                roles_text = f" [{', '.join(member_roles[:2])}]" if member_roles else ""
                if len(member_roles) > 2:
                    roles_text = f" [{', '.join(member_roles[:2])} +{len(member_roles)-2} more]"
                
                entry = f"{i}. **{member.name}**{roles_text}\n"
                
                # Discord field value limit is 1024 characters
                if len(unregistered_list) + len(entry) <= 1000:
                    unregistered_list += entry
                else:
                    # If we exceed the limit, truncate and note how many more
                    remaining = len(users_not_in_json) - i + 1
                    unregistered_list += f"... and {remaining} more unregistered users"
                    break
            
            embed.add_field(
                name=f"🔴 Unregistered Users ({len(users_not_in_json)} total)",
                value=unregistered_list or "None",
                inline=False
            )
        
        # For users in JSON but not in server
        if users_not_in_server:
            left_server_list = ""
            for i, user_id_str in enumerate(users_not_in_server[:20], 1):  # Show first 20 in log channel
                user_data = registered_users[user_id_str]
                child_name = user_data.get('child_name', 'Unknown')
                role_display = user_data.get('role_display', 'Unknown')
                entry = f"{i}. {child_name}'s {role_display}\n"
                
                if len(left_server_list) + len(entry) <= 1000:
                    left_server_list += entry
                else:
                    remaining = len(users_not_in_server) - i + 1
                    left_server_list += f"... and {remaining} more"
                    break
            
            if len(users_not_in_server) > 20:
                left_server_list += f"\n... and {len(users_not_in_server) - 20} more"
            
            embed.add_field(
                name=f"🔵 Registered But Left Server ({len(users_not_in_server)} total)",
                value=left_server_list or "None",
                inline=False
            )
        
        await send_to_log_channel(guild, "", embed)
        
    except Exception as e:
        print(f"⚠️ Error checking registration status: {e}")
        import traceback
        traceback.print_exc()

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
    """No longer removing green check mark reactions - we're using buttons now."""
    print(f"⚠️ Note: Registration now uses buttons. No green check reactions to remove for {member.name}")
    return  # Do nothing - we're using buttons now

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
    
    # Handle monitored channel messages - ONLY DELETE THEM NOW
    if message.channel.id == GENERAL_CHAT_CHANNEL_ID:
        # Delete any messages sent in general-chat
        try:
            await message.delete()
            print(f'🗑️ Deleted message from {message.author.name} in #{message.channel.name}')
            
            # Notify user via DM
            try:
                dm_channel = await message.author.create_dm()
                embed = discord.Embed(
                    title="⚠️ No Typing in General Chat",
                    description=f"You cannot send messages in <#{GENERAL_CHAT_CHANNEL_ID}>!\n\n"
                              "**To talk to us:**\n"
                              "1. Go to the general-chat channel\n"
                              "2. Click the **📩 Request Private Chat** button\n"
                              "3. A private chat will be created for you\n\n"
                              "Use the button every time you want to talk to us.",
                    color=discord.Color.red()
                )
                await dm_channel.send(embed=embed)
            except:
                pass
        except:
            pass
        return
    
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
        # Log this error to log channel
        error_embed = discord.Embed(
            title="❌ Cannot Send DM to Admin",
            description=f"**User:** {user_message.author.mention}\n"
                    f"**Message:** {user_message.content[:200]}",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )
        await send_to_log_channel(admin_user.guild, "", error_embed)
    except Exception as e:
        print(f"❌ Error forwarding user response: {e}")
        # Log this error to log channel
        error_embed = discord.Embed(
            title="❌ Error Forwarding User Response",
            description=f"**User:** {user_message.author.mention}\n"
                    f"**Error:** {str(e)[:1000]}",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )
        await send_to_log_channel(user_message.guild, "", error_embed)

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
    """Assign Family Member role to user after registration."""
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return False
    
    family_role = guild.get_role(FAMILY_ROLE_ID)
    if family_role and family_role not in member.roles:
        try:
            await member.add_roles(family_role, reason="Registration Complete")
            print(f'✅ Added Family Member role to {member.name} after registration')
            
            # Update JSON file
            await update_user_roles_in_json(member.id, member)
            
            return True
        except discord.Forbidden:
            print(f'❌ Missing permissions to add role to {member.name}')
        except discord.HTTPException as e:
            print(f'❌ Error adding role to {member.name}: {e}')
    return False

async def assign_student_role(member: discord.Member) -> bool:
    """Assign Student role to user after registration."""
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return False
    
    student_role = guild.get_role(STUDENT_ROLE_ID)
    if student_role and student_role not in member.roles:
        try:
            await member.add_roles(student_role, reason="Registration Complete")
            print(f'✅ Added Student role to {member.name} after registration')
            
            # Update JSON file
            await update_user_roles_in_json(member.id, member)
            
            return True
        except discord.Forbidden:
            print(f'❌ Missing permissions to add role to {member.name}')
        except discord.HTTPException as e:
            print(f'❌ Error adding role to {member.name}: {e}')
    return False

async def assign_program_roles(member: discord.Member, programs_selected: list) -> List[str]:
    """Assign program roles based on user selection."""
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return []
    
    assigned_programs = []
    
    # Assign National Team role
    if "national" in programs_selected:
        national_role = guild.get_role(NATIONAL_TEAM_ROLE_ID)
        if national_role and national_role not in member.roles:
            try:
                await member.add_roles(national_role, reason="National Team Registration")
                assigned_programs.append("National Team")
                print(f'✅ Added National Team role to {member.name}')
            except discord.Forbidden:
                print(f'❌ Missing permissions to add National Team role to {member.name}')
            except discord.HTTPException as e:
                print(f'❌ Error adding National Team role to {member.name}: {e}')
    
    # Assign Demonstration Team role
    if "demonstration" in programs_selected:
        demonstration_role = guild.get_role(DEMONSTRATION_TEAM_ROLE_ID)
        if demonstration_role and demonstration_role not in member.roles:
            try:
                await member.add_roles(demonstration_role, reason="Demonstration Team Registration")
                assigned_programs.append("Demonstration Team")
                print(f'✅ Added Demonstration Team role to {member.name}')
            except discord.Forbidden:
                print(f'❌ Missing permissions to add Demonstration Team role to {member.name}')
            except discord.HTTPException as e:
                print(f"❌ Error adding Demonstration Team role to {member.name}: {e}")
    
    # Assign After School role
    if "after_school" in programs_selected:
        after_school_role = guild.get_role(AFTER_SCHOOL_ROLE_ID)
        if after_school_role and after_school_role not in member.roles:
            try:
                await member.add_roles(after_school_role, reason="After School Program Registration")
                assigned_programs.append("After School")
                print(f'✅ Added After School role to {member.name}')
            except discord.Forbidden:
                print(f'❌ Missing permissions to add After School role to {member.name}')
            except discord.HTTPException as e:
                print(f"❌ Error adding After School role to {member.name}: {e}")
    
    # Update JSON file with all roles
    await update_user_roles_in_json(member.id, member)
    
    return assigned_programs

async def assign_program_roles(member: discord.Member, programs_selected: list) -> List[str]:
    """
    Assign program roles based on user selection.
    
    Args:
        member: Discord member to assign roles to
        programs_selected: List of selected program identifiers
        
    Returns:
        List of successfully assigned program names
    """
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return []
    
    assigned_programs = []
    
    # Assign National Team role
    if "national" in programs_selected:
        national_role = guild.get_role(NATIONAL_TEAM_ROLE_ID)
        if national_role and national_role not in member.roles:
            try:
                await member.add_roles(national_role, reason="National Team Registration")
                assigned_programs.append("National Team")
                print(f'✅ Added National Team role to {member.name}')
            except discord.Forbidden:
                print(f'❌ Missing permissions to add National Team role to {member.name}')
            except discord.HTTPException as e:
                print(f'❌ Error adding National Team role to {member.name}: {e}')
    
    # Assign Demonstration Team role
    if "demonstration" in programs_selected:
        demonstration_role = guild.get_role(DEMONSTRATION_TEAM_ROLE_ID)
        if demonstration_role and demonstration_role not in member.roles:
            try:
                await member.add_roles(demonstration_role, reason="Demonstration Team Registration")
                assigned_programs.append("Demonstration Team")
                print(f'✅ Added Demonstration Team role to {member.name}')
            except discord.Forbidden:
                print(f'❌ Missing permissions to add Demonstration Team role to {member.name}')
            except discord.HTTPException as e:
                print(f"❌ Error adding Demonstration Team role to {member.name}: {e}")
    
    # Assign After School role
    if "after_school" in programs_selected:
        after_school_role = guild.get_role(AFTER_SCHOOL_ROLE_ID)
        if after_school_role and after_school_role not in member.roles:
            try:
                await member.add_roles(after_school_role, reason="After School Program Registration")
                assigned_programs.append("After School")
                print(f'✅ Added After School role to {member.name}')
            except discord.Forbidden:
                print(f'❌ Missing permissions to add After School role to {member.name}')
            except discord.HTTPException as e:
                print(f"❌ Error adding After School role to {member.name}: {e}")
    
    return assigned_programs

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
    programs_selected = user_states[user_id].get('programs_selected', [])  # Changed from teams_selected
    
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
    
    # Assign program roles (if any selected)
    assigned_programs = await assign_program_roles(member, programs_selected)  # Changed from assign_team_roles
    
    # Prepare completion message components
    program_message = format_program_message(programs_selected)  # Changed from team_message
    role_msg = format_role_assignment_message(role_type, role_assigned, assigned_programs)  # Changed
    
    # Send completion message
    await send_registration_completion_message(
        dm_channel, emoji_role, role_display, child_name, 
        success_msg, role_msg, program_message, gender  # Changed
    )
    
    # Save registration data
    save_registration_data(
        user_id=user.id,
        child_name=child_name,
        role_name=role_name,  # This should be the role name like "Mother", "Father", "Student"
        role_display=role_display,
        nickname=nickname,
        gender=gender,
        programs_selected=programs_selected,  # Changed from teams_selected
        member=member
    )
    
    # Log successful registration
    await log_successful_registration(member, child_name, nickname, programs_selected, gender)  # Changed
    
    # Clean up temporary state
    del user_states[user_id]
    
    print(f"✅ Registration complete for {user.name} as {gender} with programs: {programs_selected}")

async def update_user_roles_in_json(user_id: int, member: discord.Member) -> None:
    """Update the roles array in registered_users.json for a specific user."""
    user_id_str = str(user_id)
    
    if user_id_str in registered_users:
        roles = []
        
        # Check for special roles first (these should be preserved)
        if MASTER_LEE_FAMILY_ROLE_ID and discord.utils.get(member.roles, id=MASTER_LEE_FAMILY_ROLE_ID):
            roles.append("Master Lee's Family")
        if INSTRUCTOR_ROLE_ID and discord.utils.get(member.roles, id=INSTRUCTOR_ROLE_ID):
            roles.append("Instructor")
        
        # Check for admin role
        if user_id == ADMIN_USER_ID:
            if "Admin" not in roles:
                roles.append("Admin")
        
        # Check for family role (for parents/grandparents)
        if FAMILY_ROLE_ID and discord.utils.get(member.roles, id=FAMILY_ROLE_ID):
            if "Family Member" not in roles:
                roles.append("Family Member")
        
        # Check for student role
        if STUDENT_ROLE_ID and discord.utils.get(member.roles, id=STUDENT_ROLE_ID):
            if "Student" not in roles:
                roles.append("Student")
        
        # Check for program roles
        if NATIONAL_TEAM_ROLE_ID and discord.utils.get(member.roles, id=NATIONAL_TEAM_ROLE_ID):
            if "National Team" not in roles:
                roles.append("National Team")
        if DEMONSTRATION_TEAM_ROLE_ID and discord.utils.get(member.roles, id=DEMONSTRATION_TEAM_ROLE_ID):
            if "Demonstration Team" not in roles:
                roles.append("Demonstration Team")
        if AFTER_SCHOOL_ROLE_ID and discord.utils.get(member.roles, id=AFTER_SCHOOL_ROLE_ID):
            if "After School" not in roles:
                roles.append("After School")
        
        # Update the roles in JSON
        registered_users[user_id_str]['roles'] = roles
        save_registered_users(registered_users)
        
        print(f"📝 Updated JSON roles for {member.name}: {roles}")
    else:
        print(f"⚠️ User {member.name} not in registered_users.json, cannot update roles")
    
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

def format_program_message(programs_selected: List[str]) -> str:
    """Format program selection message for completion embed."""
    if not programs_selected:
        return "\n\n**Programs:** None selected - you can join programs later!"
    
    program_list = []
    if "national" in programs_selected:
        program_list.append("**National Team** 🔴")
    if "demonstration" in programs_selected:
        program_list.append("**Demonstration Team** 🔵")
    if "after_school" in programs_selected:
        program_list.append("**After School** 📚")
    
    return f"\n\n**Programs Enrolled:**\n" + "\n".join([f"• {program}" for program in program_list])

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
    description += f"• To talk to us, click the **📩 Request Private Chat** button in that channel\n"
    description += f"• Use the button every time you want to talk to us\n"
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
    programs_selected: List[str],
    member: discord.Member = None
) -> None:
    """Save registration data to persistent storage including Discord roles."""
    # Get the current timestamp in ISO format with timezone
    registered_at = discord.utils.utcnow().isoformat()
    
    # Determine roles array based on member's current roles
    roles = []
    
    if member:
        # Check for special roles
        if MASTER_LEE_FAMILY_ROLE_ID and discord.utils.get(member.roles, id=MASTER_LEE_FAMILY_ROLE_ID):
            roles.append("Master Lee's Family")
        if INSTRUCTOR_ROLE_ID and discord.utils.get(member.roles, id=INSTRUCTOR_ROLE_ID):
            roles.append("Instructor")
        
        # Check for Family Member role (for parents/grandparents)
        if gender in ['mother', 'father', 'grandmother', 'grandfather']:
            if FAMILY_ROLE_ID and discord.utils.get(member.roles, id=FAMILY_ROLE_ID):
                roles.append("Family Member")
        
        # Check for Student role
        if gender == 'student':
            if STUDENT_ROLE_ID and discord.utils.get(member.roles, id=STUDENT_ROLE_ID):
                roles.append("Student")
        
        # Check for program roles
        if "national" in programs_selected and NATIONAL_TEAM_ROLE_ID and discord.utils.get(member.roles, id=NATIONAL_TEAM_ROLE_ID):
            roles.append("National Team")
        if "demonstration" in programs_selected and DEMONSTRATION_TEAM_ROLE_ID and discord.utils.get(member.roles, id=DEMONSTRATION_TEAM_ROLE_ID):
            roles.append("Demonstration Team")
        if "after_school" in programs_selected and AFTER_SCHOOL_ROLE_ID and discord.utils.get(member.roles, id=AFTER_SCHOOL_ROLE_ID):
            roles.append("After School")
    
    # Create the user data structure exactly as specified
    user_data = {
        'child_name': child_name,
        'role': role_name,  # e.g., "Mother", "Father", "Student"
        'role_display': role_display,  # e.g., "👩 Mother", "🎓 Student"
        'nickname': nickname,
        'gender': gender,  # e.g., "mother", "father", "student"
        'registered_at': registered_at,
        'programs': programs_selected,  # Changed from 'teams' to 'programs'
        'has_active_private_chat': False,
        'private_chat_channel_id': None,
        'roles': roles
    }
    
    # Save to registered_users
    registered_users[str(user_id)] = user_data
    save_registered_users(registered_users)
    
    print(f"✅ Saved registration data for user {user_id} with roles: {roles}")

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
        # If no subcommand was invoked, show help
        embed = create_bot_commands_embed()
        await ctx.send(embed=embed)

@bot_command.command(name="chat")
@bot_channel_only()
async def chat_command(ctx):
    """
    Display available administrative chat commands.
    
    Only accessible in bot command channel by admin users.
    """
    embed = discord.Embed(
        title="💬 **ADMIN BOT COMMANDS**",
        description="**All commands must be used in this channel only.**\n\n"
                   "Use `!bot_command [command_name]`\n"
                   "**Example:** `!bot_command view_user @user`\n",
        color=discord.Color.blue()
    )
    
    # Section 1: REAL-TIME MONITORING
    embed.add_field(
        name="📊 **REAL-TIME MONITORING**",
        value=(
            "`active_private_chats` - Show all active private chats with activity status\n"
            "`active_chats` - Show active 1-on-1 conversations\n"
            "`register_stats` - Show registration statistics\n"
        ),
        inline=False
    )
    
    # Section 2: USER MANAGEMENT
    embed.add_field(
        name="👤 **USER MANAGEMENT**",
        value=(
            "`view_user @user` - Complete user profile with all data\n"
            "`view_user_roles @user` - View JSON vs Discord role comparison\n"
            "`send_dm @user message` - Send direct message to user\n"
            "`assign_role @user add/remove role` - Add/remove any role (national_team, demonstration_team, after_school, student, instructor, master_family)\n"
            "`fix_name @user new_name` - Fix user's registered name\n"
            "`remove_check @user` - Remove user's green check\n"
        ),
        inline=False
    )
    
    # Section 3: PRIVATE CHAT MANAGEMENT
    embed.add_field(
        name="🔒 **PRIVATE CHAT MANAGEMENT**",
        value=(
            "`resend_delete_button #channel` - Fix delete button in channel\n"
        ),
        inline=False
    )
    
    # Section 4: ROLE MANAGEMENT
    embed.add_field(
        name="🎭 **ROLE MANAGEMENT**",
        value=(
            "`remove_role @user role_type` - Remove special role (instructor, master_family, both)\n"
        ),
        inline=False
    )
    
    # Section 5: REGISTRATION & CONSISTENCY
    embed.add_field(
        name="📝 **REGISTRATION & CONSISTENCY**",
        value=(
            "`check_consistency` - Check registry/green check consistency\n"
            "`force_register` - Force start registration for yourself\n"
        ),
        inline=False
    )
    
    # Section 6: DATA MANAGEMENT
    embed.add_field(
        name="💾 **DATA MANAGEMENT**",
        value=(
            "`view_json_data @user` - View raw JSON data for user\n"
            "`cleanup_json` - Clean orphaned JSON entries\n"
            "`migrate_json_structure` - Migrate JSON to new structure with backup\n"
            "`list_backups` - List all backup files\n"
            "`verify_json_structure` - Verify JSON structure\n"
        ),
        inline=False
    )
    
    # Section 7: SYSTEM & MAINTENANCE
    embed.add_field(
        name="🛠️ **SYSTEM & MAINTENANCE**",
        value=(
            "`setup` - Setup rules message\n"
            "`setup_bot_channel` - Create bot command channel\n"
            "`setup_log_channel` - Create log channel\n"
            "`clear_chats` - Clear active conversations\n"
            "`update_message_id ID` - Update rules message ID\n"
            "`clear_channel [#channel]` - Clear ALL messages in a channel\n"
        ),
        inline=False
    )
    
    # Section 8: JSON SYNCHRONIZATION
    embed.add_field(
        name="🔄 **JSON SYNCHRONIZATION**",
        value=(
            "`update_discord_roles` - Update Discord roles from JSON file (for ALL users)\n"
            "`update_json_roles` - Force immediate JSON sync\n"
            "`force_json_sync @user` - Force sync for specific user\n"
            "`json_task_status` - Show JSON task status\n"
            "`start_json_task` - Start JSON sync task\n"
            "`stop_json_task` - Stop JSON sync task\n"
            "`verify_json_roles @user` - Verify JSON role sync\n"
        ),
        inline=False
    )
    
    # Section 9: TESTING & DEBUGGING
    embed.add_field(
        name="🐛 **TESTING & DEBUGGING**",
        value=(
            "`debug_ids` - Show all configuration IDs\n"
            "`check_message ID` - Check message reactions\n"
        ),
        inline=False
    )
    
    # Section 10: PUBLIC COMMANDS
    embed.add_field(
        name="🌐 **PUBLIC COMMANDS**",
        value=(
            "`!force_register` - Force start registration for yourself\n"
        ),
        inline=False
    )
    
    embed.set_footer(
        text="🚀 Bot v2.0.0 | Commands only work in bot-commands channel | Prefix: !"
    )
    
    await ctx.send(embed=embed)

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
    
    # Calculate program distribution
    national_count = 0
    demonstration_count = 0
    after_school_count = 0
    multiple_programs_count = 0
    no_programs_count = 0
    
    for user_data in registered_users.values():
        programs = user_data.get('programs', [])
        program_count = 0
        
        if "national" in programs:
            national_count += 1
            program_count += 1
        if "demonstration" in programs:
            demonstration_count += 1
            program_count += 1
        if "after_school" in programs:
            after_school_count += 1
            program_count += 1
        
        if program_count > 1:
            multiple_programs_count += 1
        elif program_count == 0:
            no_programs_count += 1
    
    embed = discord.Embed(
        title="📊 Registration Statistics",
        description=f"**Total Registered:** {total_registered}",
        color=discord.Color.green()
    )
    
    embed.add_field(name="🔴 National Team", value=f"{national_count} members", inline=True)
    embed.add_field(name="🔵 Demonstration Team", value=f"{demonstration_count} members", inline=True)
    embed.add_field(name="📚 After School", value=f"{after_school_count} members", inline=True)
    embed.add_field(name="🎯 Multiple Programs", value=f"{multiple_programs_count} members", inline=True)
    embed.add_field(name="👪 No Programs", value=f"{no_programs_count} members", inline=True)
    
    await ctx.send(embed=embed)

@bot_command.command(name="view_json_data")
@bot_channel_only()
async def chat_view_json_data(ctx, member: discord.Member = None):
    """
    View the JSON data for a user (including roles stored in JSON).
    
    Useful for debugging what's actually in the JSON file.
    """
    if not member:
        # Show all users in JSON if no member specified
        total_users = len(registered_users)
        
        if total_users == 0:
            await ctx.send("📁 JSON file is empty.", ephemeral=True)
            return
        
        # Create paginated view of all users
        users_per_page = 10
        pages = []
        current_page = []
        
        for user_id_str, user_data in registered_users.items():
            try:
                user_id = int(user_id_str)
                guild_member = ctx.guild.get_member(user_id)
                user_name = guild_member.name if guild_member else f"ID: {user_id} (Not in server)"
                
                child_name = user_data.get('child_name', 'Unknown')
                roles = user_data.get('roles', [])
                
                entry = f"**{user_name}**\n"
                entry += f"• Child: {child_name}\n"
                entry += f"• Roles in JSON: {', '.join(roles) if roles else 'None'}\n"
                entry += f"• ID: {user_id_str}\n"
                
                current_page.append(entry)
                
                if len(current_page) >= users_per_page:
                    pages.append(current_page)
                    current_page = []
            except:
                continue
        
        if current_page:
            pages.append(current_page)
        
        if not pages:
            await ctx.send("📁 No valid users found in JSON.", ephemeral=True)
            return
        
        class JSONListView(discord.ui.View):
            def __init__(self, pages):
                super().__init__(timeout=60)
                self.current_page = 0
                self.pages = pages
            
            @discord.ui.button(label="⬅️ Previous", style=discord.ButtonStyle.secondary)
            async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != ctx.author.id:
                    await interaction.response.send_message("❌ This is not for you.", ephemeral=True)
                    return
                
                self.current_page = (self.current_page - 1) % len(self.pages)
                await self.update_message(interaction)
            
            @discord.ui.button(label="➡️ Next", style=discord.ButtonStyle.secondary)
            async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != ctx.author.id:
                    await interaction.response.send_message("❌ This is not for you.", ephemeral=True)
                    return
                
                self.current_page = (self.current_page + 1) % len(self.pages)
                await self.update_message(interaction)
            
            async def update_message(self, interaction):
                embed = discord.Embed(
                    title="📁 JSON File Contents",
                    description=f"**Total users in JSON:** {total_users}\n**Page {self.current_page + 1}/{len(self.pages)}**",
                    color=discord.Color.blue()
                )
                
                for entry in self.pages[self.current_page]:
                    embed.add_field(name="---", value=entry, inline=False)
                
                await interaction.response.edit_message(embed=embed, view=self)
        
        # Send first page
        embed = discord.Embed(
            title="📁 JSON File Contents",
            description=f"**Total users in JSON:** {total_users}\n**Page 1/{len(pages)}**",
            color=discord.Color.blue()
        )
        
        for entry in pages[0]:
            embed.add_field(name="---", value=entry, inline=False)
        
        view = JSONListView(pages)
        await ctx.send(embed=embed, view=view, ephemeral=True)
        return
    
    # If member is specified, show their specific data
    user_id_str = str(member.id)
    
    if user_id_str not in registered_users:
        await ctx.send(f"❌ {member.mention} is not in the JSON file.", ephemeral=True)
        return
    
    user_data = registered_users[user_id_str]
    
    embed = discord.Embed(
        title=f"📄 JSON Data for {member.name}",
        description=f"**User ID:** {member.id}",
        color=discord.Color.blue()
    )
    
    # Show all fields
    embed.add_field(name="Child's Name", value=user_data.get('child_name', 'Not set'), inline=True)
    embed.add_field(name="Registration Role", value=user_data.get('role_display', user_data.get('role', 'Not set')), inline=True)
    embed.add_field(name="Gender", value=user_data.get('gender', 'Not set'), inline=True)
    embed.add_field(name="Nickname", value=user_data.get('nickname', 'Not set'), inline=True)
    
    # Programs (teams)
    programs = user_data.get('programs', [])
    if programs:
        program_list = []
        if "national" in programs:
            program_list.append("National Team 🔴")
        if "demonstration" in programs:
            program_list.append("Demonstration Team 🔵")
        if "after_school" in programs:
            program_list.append("After School 📚")
        embed.add_field(name="Programs", value=", ".join(program_list), inline=True)
    else:
        embed.add_field(name="Programs", value="None", inline=True)
    
    # Stored roles
    roles = user_data.get('roles', [])
    if roles:
        embed.add_field(name="Roles in JSON", value="\n".join([f"• {role}" for role in roles]), inline=False)
    else:
        embed.add_field(name="Roles in JSON", value="No roles stored", inline=False)
    
    # Registration info
    embed.add_field(name="Registered At", value=user_data.get('registered_at', 'Unknown'), inline=False)
    
    # Private chat info
    has_chat = user_data.get('has_active_private_chat', False)
    chat_status = "✅ Active" if has_chat else "❌ Inactive"
    channel_id = user_data.get('private_chat_channel_id')
    channel_mention = f"<#{channel_id}>" if channel_id else "None"
    
    embed.add_field(name="Private Chat Status", value=chat_status, inline=True)
    embed.add_field(name="Private Chat Channel", value=channel_mention, inline=True)
    
    # Auto-added flag
    if user_data.get('auto_added'):
        embed.add_field(name="⚠️ Note", value="User was auto-added (not through normal registration)", inline=False)
    
    await ctx.send(embed=embed, ephemeral=True)

@bot_command.command(name="update_discord_roles")
@bot_channel_only()
async def chat_update_roles_from_json(ctx):
    """
    Update Discord roles from registered_users.json file.
    
    This command reads the JSON file and synchronizes Discord roles 
    for all registered users based on the JSON data.
    
    Useful when you've manually edited the JSON file and need to
    apply those changes to Discord roles.
    """
    await ctx.send("🔄 **Starting role update from JSON file...**")
    
    guild = ctx.guild
    total_users = len(registered_users)
    processed = 0
    updated = 0
    errors = []
    
    # Create role mapping from JSON role names to Discord role IDs
    role_mapping = {
        "Family Member": FAMILY_ROLE_ID,
        "National Team": NATIONAL_TEAM_ROLE_ID,
        "Demonstration Team": DEMONSTRATION_TEAM_ROLE_ID,
        "After School": AFTER_SCHOOL_ROLE_ID,
        "Student": STUDENT_ROLE_ID,
        "Instructor": INSTRUCTOR_ROLE_ID,
        "Master Lee's Family": MASTER_LEE_FAMILY_ROLE_ID
    }
    
    # Create a reverse mapping for logging
    id_to_name = {v: k for k, v in role_mapping.items() if v}
    
    # Process each user in the JSON file
    for user_id_str, user_data in registered_users.items():
        try:
            user_id = int(user_id_str)
            member = guild.get_member(user_id)
            
            if not member:
                errors.append(f"User {user_id_str} not found in server")
                continue
            
            processed += 1
            
            # Get stored roles from JSON
            stored_role_names = user_data.get('roles', [])
            stored_role_ids = []
            
            # Convert role names to role IDs
            for role_name in stored_role_names:
                if role_name in role_mapping and role_mapping[role_name]:
                    stored_role_ids.append(role_mapping[role_name])
            
            # Get current Discord roles (only managed ones)
            current_role_ids = []
            for role_id, role_name in id_to_name.items():
                role = guild.get_role(role_id)
                if role and role in member.roles:
                    current_role_ids.append(role_id)
            
            # Compare and update
            roles_to_add = set(stored_role_ids) - set(current_role_ids)
            roles_to_remove = set(current_role_ids) - set(stored_role_ids)
            
            changes_made = False
            role_changes = []
            
            # Add missing roles
            for role_id in roles_to_add:
                role = guild.get_role(role_id)
                if role and role not in member.roles:
                    try:
                        await member.add_roles(role, reason="JSON sync: Add missing role")
                        role_changes.append(f"➕ {id_to_name.get(role_id, 'Unknown Role')}")
                        changes_made = True
                    except Exception as e:
                        errors.append(f"{member.name}: Failed to add {id_to_name.get(role_id, 'Unknown')} - {e}")
            
            # Remove extra roles
            for role_id in roles_to_remove:
                role = guild.get_role(role_id)
                if role and role in member.roles:
                    try:
                        await member.remove_roles(role, reason="JSON sync: Remove extra role")
                        role_changes.append(f"➖ {id_to_name.get(role_id, 'Unknown Role')}")
                        changes_made = True
                    except Exception as e:
                        errors.append(f"{member.name}: Failed to remove {id_to_name.get(role_id, 'Unknown')} - {e}")
            
            if changes_made:
                updated += 1
                print(f"✅ Updated roles for {member.name}: {', '.join(role_changes)}")
            
            # Update progress every 10 users
            if processed % 10 == 0:
                await ctx.send(f"📊 Processed {processed}/{total_users} users...")
                
        except Exception as e:
            errors.append(f"Error processing user {user_id_str}: {str(e)}")
            print(f"❌ Error processing user {user_id_str}: {e}")
    
    # Create summary embed
    embed = discord.Embed(
        title="✅ JSON Role Update Complete",
        description=f"**Processed:** {processed} users\n"
                  f"**Updated:** {updated} users\n"
                  f"**Errors:** {len(errors)}",
        color=discord.Color.green(),
        timestamp=datetime.now(timezone.utc)
    )
    
    # Add detailed results
    if updated > 0:
        embed.add_field(
            name="📝 Updates Applied",
            value=f"Successfully updated roles for {updated} users based on JSON file.",
            inline=False
        )
    
    if errors:
        # Show first 5 errors if there are many
        error_display = "\n".join(errors[:5])
        if len(errors) > 5:
            error_display += f"\n...and {len(errors) - 5} more errors"
        
        embed.add_field(
            name="❌ Errors Encountered",
            value=error_display,
            inline=False
        )
    
    if updated == 0 and len(errors) == 0:
        embed.add_field(
            name="⚡ No Changes Needed",
            value="All users already have the correct roles according to the JSON file.",
            inline=False
        )
    
    embed.set_footer(text=f"JSON file: {REGISTRY_FILE}")
    
    await ctx.send(embed=embed)
    
    # Log to log channel
    log_embed = discord.Embed(
        title="🔄 JSON Role Update Executed",
        description=f"**Processed:** {processed} users\n"
                  f"**Updated:** {updated} users\n"
                  f"**By:** {ctx.author.mention}",
        color=discord.Color.blue(),
        timestamp=datetime.now(timezone.utc)
    )
    await send_to_log_channel(guild, "", log_embed)

@bot_command.command(name="assign_role")
@bot_channel_only()
async def chat_assign_role(ctx, member: discord.Member, action: str, *, role_type_input: str):
    """
    Add or remove a role from a user and update JSON immediately.
    
    Usage:
    !bot_command assign_role @user add national_team
    !bot_command assign_role @user remove after_school
    !bot_command assign_role @user add "demonstration team"
    !bot_command assign_role @user add master_family
    !bot_command assign_role @user add instructor

    Role Types:
    - family_member: Family Member role
    - national_team: National Team role
    - demonstration_team: Demonstration Team role
    - after_school: After School role
    - student: Student role
    - instructor: Instructor role
    - master_family: Master Lee's Family role
    
    Note: This updates the JSON file immediately and optionally updates Discord roles.
    """
    
    # Normalize role type input
    role_type = role_type_input.lower().replace(' ', '_').replace('-', '_')
    
    # Debug: Show what we received
    print(f"DEBUG: Received - member: {member}, action: {action}, role_type_input: {role_type_input}, normalized: {role_type}")
    
    # Map role types to role IDs and display names
    role_mapping = {
        'family_member': {
            'id': FAMILY_ROLE_ID,
            'name': 'Family Member',
            'json_name': 'Family Member',
            'requires_discord': True
        },
        'family': {
            'id': FAMILY_ROLE_ID,
            'name': 'Family Member',
            'json_name': 'Family Member',
            'requires_discord': True
        },
        'national_team': {
            'id': NATIONAL_TEAM_ROLE_ID,
            'name': 'National Team',
            'json_name': 'National Team',
            'requires_discord': True,
            'program_field': 'national'
        },
        'national': {
            'id': NATIONAL_TEAM_ROLE_ID,
            'name': 'National Team',
            'json_name': 'National Team',
            'requires_discord': True,
            'program_field': 'national'
        },
        'demonstration_team': {
            'id': DEMONSTRATION_TEAM_ROLE_ID,
            'name': 'Demonstration Team',
            'json_name': 'Demonstration Team',
            'requires_discord': True,
            'program_field': 'demonstration'
        },
        'demo': {
            'id': DEMONSTRATION_TEAM_ROLE_ID,
            'name': 'Demonstration Team',
            'json_name': 'Demonstration Team',
            'requires_discord': True,
            'program_field': 'demonstration'
        },
        'demonstration': {
            'id': DEMONSTRATION_TEAM_ROLE_ID,
            'name': 'Demonstration Team',
            'json_name': 'Demonstration Team',
            'requires_discord': True,
            'program_field': 'demonstration'
        },
        'after_school': {
            'id': AFTER_SCHOOL_ROLE_ID,
            'name': 'After School',
            'json_name': 'After School',
            'requires_discord': True,
            'program_field': 'after_school'
        },
        'afterschool': {
            'id': AFTER_SCHOOL_ROLE_ID,
            'name': 'After School',
            'json_name': 'After School',
            'requires_discord': True,
            'program_field': 'after_school'
        },
        'student': {
            'id': STUDENT_ROLE_ID,
            'name': 'Student',
            'json_name': 'Student',
            'requires_discord': True
        },
        'instructor': {
            'id': INSTRUCTOR_ROLE_ID,
            'name': 'Instructor',
            'json_name': 'Instructor',
            'requires_discord': True
        },
        'master_family': {
            'id': MASTER_LEE_FAMILY_ROLE_ID,
            'name': "Master Lee's Family",
            'json_name': "Master Lee's Family",
            'requires_discord': True
        },
        'master': {
            'id': MASTER_LEE_FAMILY_ROLE_ID,
            'name': "Master Lee's Family",
            'json_name': "Master Lee's Family",
            'requires_discord': True
        },
        'master_lee': {
            'id': MASTER_LEE_FAMILY_ROLE_ID,
            'name': "Master Lee's Family",
            'json_name': "Master Lee's Family",
            'requires_discord': True
        },
        'master_lee_family': {
            'id': MASTER_LEE_FAMILY_ROLE_ID,
            'name': "Master Lee's Family",
            'json_name': "Master Lee's Family",
            'requires_discord': True
        }
    }
    
    # Validate action
    action = action.lower()
    if action not in ['add', 'remove']:
        valid_actions = "`add` or `remove`"
        await ctx.send(f"❌ Invalid action. Use {valid_actions}.", ephemeral=True)
        return
    
    # Check if role type exists
    if role_type not in role_mapping:
        # Create a more helpful error message with available roles
        valid_roles = "\n".join([f"- `{role}` ({role_mapping[role]['name']})" for role in role_mapping.keys()])
        embed = discord.Embed(
            title="❌ Invalid Role Type",
            description=f"**You entered:** `{role_type_input}`\n**Normalized to:** `{role_type}`\n\n"
                       f"**Available roles:**\n{valid_roles}",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed, ephemeral=True)
        return
    
    role_info = role_mapping[role_type]
    role_id = role_info['id']
    role_display = role_info['name']
    json_role_name = role_info['json_name']
    
    # Check if role is configured
    if role_id == 0:
        await ctx.send(f"❌ {role_display} role is not configured in config.txt", ephemeral=True)
        return
    
    user_id_str = str(member.id)
    
    # SPECIAL HANDLING FOR MASTER LEE'S FAMILY AND INSTRUCTOR ROLES
    # Create JSON entry if it doesn't exist for these special roles
    if role_type in ['master_family', 'master', 'master_lee', 'master_lee_family', 'instructor']:
        if user_id_str not in registered_users:
            # Create a proper JSON entry for the user
            if role_type.startswith('master'):
                # Master Lee's Family member
                registered_users[user_id_str] = {
                    'child_name': member.name,
                    'role': "Master Lee's Family",
                    'role_display': "👑 Master Lee's Family",
                    'nickname': member.display_name,
                    'gender': 'master_family',
                    'programs': [],
                    'registered_at': discord.utils.utcnow().isoformat(),
                    'has_active_private_chat': False,
                    'private_chat_channel_id': None,
                    'roles': [json_role_name],
                    'master_lee_family': True,
                    'auto_added': True
                }
                print(f"✅ Created JSON entry for Master Lee's Family member: {member.name}")
            elif role_type == 'instructor':
                # Instructor
                registered_users[user_id_str] = {
                    'child_name': member.name,
                    'role': 'Instructor',
                    'role_display': '👨‍🏫 Instructor',
                    'nickname': member.display_name,
                    'gender': 'instructor',
                    'programs': [],
                    'registered_at': discord.utils.utcnow().isoformat(),
                    'has_active_private_chat': False,
                    'private_chat_channel_id': None,
                    'roles': [json_role_name],
                    'instructor': True,
                    'auto_added': True
                }
                print(f"✅ Created JSON entry for Instructor: {member.name}")
    
    # Check if user exists in JSON (general case)
    if user_id_str not in registered_users:
        # Create entry if not exists for other roles
        registered_users[user_id_str] = {
            'child_name': member.name,
            'role': 'Admin-Assigned',
            'role_display': '👑 Admin-Assigned Role',
            'nickname': member.display_name,
            'gender': 'unknown',
            'programs': [],
            'registered_at': discord.utils.utcnow().isoformat(),
            'has_active_private_chat': False,
            'private_chat_channel_id': None,
            'roles': [],
            'admin_assigned': True
        }
    
    # Get current JSON data
    user_data = registered_users[user_id_str]
    current_roles = user_data.get('roles', [])
    current_programs = user_data.get('programs', [])
    
    # Track changes
    changes_made = False
    discord_changes = []
    json_changes = []
    
    # Handle ADD action
    if action == 'add':
        # Update Discord role if required
        if role_info['requires_discord']:
            discord_role = ctx.guild.get_role(role_id)
            if discord_role and discord_role not in member.roles:
                try:
                    await member.add_roles(discord_role, reason=f"Role added by admin {ctx.author.name}")
                    discord_changes.append(f"➕ Added {role_display} Discord role")
                    changes_made = True
                    
                    # ADD GREEN CHECK MARK FOR MASTER LEE'S FAMILY AND INSTRUCTOR
                    if role_type in ['master_family', 'master', 'master_lee', 'master_lee_family', 'instructor']:
                        try:
                            rules_channel = ctx.guild.get_channel(RULES_CHANNEL_ID)
                            if rules_channel:
                                rules_message = await rules_channel.fetch_message(RULES_MESSAGE_ID)
                                # Check if user already has green check
                                has_reaction = False
                                for reaction in rules_message.reactions:
                                    if str(reaction.emoji) == '✅':
                                        async for user in reaction.users():
                                            if user.id == member.id:
                                                has_reaction = True
                                                break
                                    if has_reaction:
                                        break
                                
                                if not has_reaction:
                                    await rules_message.add_reaction('✅')
                                    discord_changes.append(f"✅ Added green check mark")
                                    print(f"✅ Added green check mark for {member.name}")
                        except Exception as e:
                            print(f"⚠️ Could not add green check reaction: {e}")
                            discord_changes.append(f"⚠️ Could not add green check: {e}")
                    
                except Exception as e:
                    error_msg = f"⚠️ Could not add Discord role: {e}"
                    await ctx.send(error_msg, ephemeral=True)
                    discord_changes.append(error_msg)
                    # Still update JSON even if Discord fails
            elif discord_role and discord_role in member.roles:
                discord_changes.append(f"✅ Already has {role_display} Discord role")
            elif not discord_role:
                discord_changes.append(f"❌ Discord role not found (ID: {role_id})")
        
        # Update JSON roles array
        if json_role_name not in current_roles:
            current_roles.append(json_role_name)
            user_data['roles'] = current_roles
            json_changes.append(f"➕ Added {role_display} to JSON roles")
            changes_made = True
            
            # Set special flags
            if role_type.startswith('master'):
                user_data['master_lee_family'] = True
            elif role_type == 'instructor':
                user_data['instructor'] = True
        else:
            json_changes.append(f"✅ Already has {role_display} in JSON roles")
        
        # Update programs field if applicable
        if 'program_field' in role_info:
            program_field = role_info['program_field']
            if program_field not in current_programs:
                current_programs.append(program_field)
                user_data['programs'] = current_programs
                json_changes.append(f"➕ Added {role_display} to JSON programs")
                changes_made = True
            else:
                json_changes.append(f"✅ Already has {role_display} in JSON programs")
    
    # Handle REMOVE action
    elif action == 'remove':
        # Update Discord role if required
        if role_info['requires_discord']:
            discord_role = ctx.guild.get_role(role_id)
            if discord_role and discord_role in member.roles:
                try:
                    await member.remove_roles(discord_role, reason=f"Role removed by admin {ctx.author.name}")
                    discord_changes.append(f"➖ Removed {role_display} Discord role")
                    changes_made = True
                except Exception as e:
                    error_msg = f"⚠️ Could not remove Discord role: {e}"
                    await ctx.send(error_msg, ephemeral=True)
                    discord_changes.append(error_msg)
                    # Still update JSON even if Discord fails
            elif discord_role and discord_role not in member.roles:
                discord_changes.append(f"✅ Already missing {role_display} Discord role")
            elif not discord_role:
                discord_changes.append(f"❌ Discord role not found (ID: {role_id})")
        
        # Update JSON roles array
        if json_role_name in current_roles:
            current_roles.remove(json_role_name)
            user_data['roles'] = current_roles
            json_changes.append(f"➖ Removed {role_display} from JSON roles")
            changes_made = True
            
            # Clear special flags
            if role_type.startswith('master'):
                user_data['master_lee_family'] = False
            elif role_type == 'instructor':
                user_data['instructor'] = False
        else:
            json_changes.append(f"✅ Already missing {role_display} from JSON roles")
        
        # Update programs field if applicable
        if 'program_field' in role_info:
            program_field = role_info['program_field']
            if program_field in current_programs:
                current_programs.remove(program_field)
                user_data['programs'] = current_programs
                json_changes.append(f"➖ Removed {role_display} from JSON programs")
                changes_made = True
            else:
                json_changes.append(f"✅ Already missing {role_display} from JSON programs")
    
    # Save changes to JSON
    if changes_made:
        registered_users[user_id_str] = user_data
        save_registered_users(registered_users)
    
    # Create response embed
    embed = discord.Embed(
        title="✅ Role Adjustment Complete" if changes_made else "ℹ️ Role Status",
        description=f"**User:** {member.mention} ({member.id})\n"
                  f"**Action:** {action.upper()} {role_display}",
        color=discord.Color.green() if changes_made else discord.Color.blue()
    )
    
    # Add change details
    if discord_changes:
        embed.add_field(
            name="🔄 Discord Status",
            value="\n".join(discord_changes),
            inline=False
        )
    
    if json_changes:
        embed.add_field(
            name="📝 JSON Status",
            value="\n".join(json_changes),
            inline=False
        )
    
    # Show current state
    embed.add_field(
        name="📋 Current JSON Roles",
        value=", ".join(user_data.get('roles', [])) if user_data.get('roles') else "None",
        inline=True
    )
    
    embed.add_field(
        name="🎯 Current JSON Programs",
        value=", ".join(user_data.get('programs', [])) if user_data.get('programs') else "None",
        inline=True
    )
    
    # Show special flags
    special_flags = []
    if user_data.get('master_lee_family'):
        special_flags.append("Master Lee's Family")
    if user_data.get('instructor'):
        special_flags.append("Instructor")
    if user_data.get('admin_assigned'):
        special_flags.append("Admin-Assigned")
    
    if special_flags:
        embed.add_field(
            name="🏷️ Special Flags",
            value=", ".join(special_flags),
            inline=False
        )
    
    embed.set_footer(text=f"Updated by {ctx.author.name}")
    
    await ctx.send(embed=embed, ephemeral=True)
    
    # Log to log channel if changes were made
    if changes_made:
        log_embed = discord.Embed(
            title="🔄 Role Adjustment",
            description=f"**User:** {member.mention} ({member.id})\n"
                      f"**Action:** {action.upper()} {role_display}\n"
                      f"**By:** {ctx.author.mention}\n"
                      f"**Time:** <t:{int(time.time())}:R>",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        if discord_changes:
            log_embed.add_field(name="Discord Changes", value="\n".join(discord_changes), inline=False)
        if json_changes:
            log_embed.add_field(name="JSON Updates", value="\n".join(json_changes), inline=False)
        
        await send_to_log_channel(ctx.guild, "", log_embed)
        
        print(f"✅ Admin adjusted role for {member.name}: {action} {role_display}")

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

@bot_command.command(name="view_user_roles")
@bot_channel_only()
async def chat_view_user_roles(ctx, member: discord.Member):
    """View a user's stored roles in the JSON file and compare with current Discord roles."""
    user_id_str = str(member.id)
    
    if user_id_str not in registered_users:
        await ctx.send(f"❌ {member.mention} is not registered in the system!", ephemeral=True)
        return
    
    user_data = registered_users[user_id_str]
    
    embed = discord.Embed(
        title=f"👤 Role Information: {member.name}",
        description=f"**Child's Name:** {user_data.get('child_name', 'Not set')}\n"
                   f"**Registration Role:** {user_data.get('role_display', user_data.get('role', 'Not set'))}",
        color=discord.Color.blue()
    )
    
    # Get current Discord roles for comparison
    current_roles = [role.name for role in member.roles if role.name != "@everyone"]
    stored_roles = user_data.get('roles', [])
    
    embed.add_field(
        name="📋 Stored in JSON",
        value="\n".join([f"• {role}" for role in stored_roles]) if stored_roles else "No roles stored",
        inline=True
    )
    
    embed.add_field(
        name="🔄 Current Discord Roles",
        value="\n".join([f"• {role}" for role in current_roles[:10]]) if current_roles else "No roles",
        inline=True
    )
    
    # Check for discrepancies
    missing_from_json = set(current_roles) - set(stored_roles)
    missing_from_discord = set(stored_roles) - set(current_roles)
    
    if missing_from_json:
        embed.add_field(
            name="⚠️ Missing from JSON",
            value="\n".join([f"• {role}" for role in missing_from_json]),
            inline=False
        )
    
    if missing_from_discord:
        embed.add_field(
            name="⚠️ Missing from Discord",
            value="\n".join([f"• {role}" for role in missing_from_discord]),
            inline=False
        )
    
    if not missing_from_json and not missing_from_discord:
        embed.add_field(
            name="✅ Status",
            value="JSON and Discord roles are synchronized!",
            inline=False
        )
    else:
        embed.add_field(
            name="🔧 Action Required",
            value=f"Use `!bot_command chat update_discord_roles {member.mention}` to fix",
            inline=False
        )
    
    await ctx.send(embed=embed, ephemeral=True)

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
# AUTO-PIN BOT COMMAND ON STARTUP
# =============================================================================
async def auto_setup_command_chat():
    """
    Automatically send and pin the bot command help message on startup.
    Only creates if not already exists.
    """
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        print("❌ Guild not found for auto-pin")
        return
    
    bot_channel = guild.get_channel(BOT_COMMAND_CHANNEL_ID)
    if not bot_channel:
        print("❌ Bot command channel not found for auto-pin")
        return
    
    try:
        # Check if bot command message already exists and is pinned
        pinned_messages = await bot_channel.pins()
        bot_command_exists = False
        
        for pinned_msg in pinned_messages:
            # Check if this is a bot command message from our bot
            if pinned_msg.author == bot.user and pinned_msg.embeds:
                for embed in pinned_msg.embeds:
                    if embed.title and "ADMIN BOT COMMANDS" in embed.title:
                        bot_command_exists = True
                        print(f"✅ Bot command message already pinned: {pinned_msg.id}")
                        break
            
            if bot_command_exists:
                break
        
        # If no existing bot command message, create and pin one
        if not bot_command_exists:
            print("📌 Creating and pinning bot command message...")
            
            # Create the bot command embed using the updated function
            embed = create_bot_commands_embed()
            message = await bot_channel.send(embed=embed)
            
            # Pin the message
            await message.pin(reason="Auto-pinned bot command on startup")
            print(f"✅ Bot command message created and pinned: {message.id}")
            
            # Also log to log channel
            log_embed = discord.Embed(
                title="📌 Bot Command Auto-Pinned",
                description=f"Bot command help message has been auto-pinned in {bot_channel.mention}",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            await send_to_log_channel(guild, "", log_embed)
    
    except Exception as e:
        print(f"❌ Error auto-pinning bot command: {e}")
        import traceback
        traceback.print_exc()

def create_bot_commands_embed():
    """Create the bot commands embed for auto-pinning."""
    embed = discord.Embed(
        title="💬 **ADMIN BOT COMMANDS**",
        description="**All commands must be used in this channel only.**\n\n"
                   "Use `!bot_command [command_name]` or just `!bot_command` for main menu\n"
                   "**Example:** `!bot_command view_user @user`\n",
        color=discord.Color.blue()
    )
    
    # Section 1: REAL-TIME MONITORING
    embed.add_field(
        name="📊 **REAL-TIME MONITORING**",
        value=(
            "`active_private_chats` - Show all active private chats with activity status\n"
            "`active_chats` - Show active 1-on-1 conversations\n"
            "`register_stats` - Show registration statistics\n"
            "`system_status` - Show Raspberry Pi system status\n"
            "`monitoring_config` - View monitoring thresholds and settings\n"
        ),
        inline=False
    )
    
    # Section 2: USER MANAGEMENT
    embed.add_field(
        name="👤 **USER MANAGEMENT**",
        value=(
            "`view_user @user` - Complete user profile with all data\n"
            "`view_user_roles @user` - View JSON vs Discord role comparison\n"
            "`send_dm @user message` - Send direct message to user\n"
            "`assign_role @user add/remove role` - Add/remove any role (national_team, demonstration_team, after_school, student, instructor, master_family)\n"
            "`fix_name @user new_name` - Fix user's registered name\n"
            "`remove_check @user` - Remove user's green check\n"
            "`update_discord_roles` - Update Discord roles from JSON file\n"
        ),
        inline=False
    )
    
    # Section 3: PRIVATE CHAT MANAGEMENT
    embed.add_field(
        name="🔒 **PRIVATE CHAT MANAGEMENT**",
        value=(
            "`resend_delete_button #channel` - Fix delete button in channel\n"
            "`reset_general_permissions` - Reset general-chat permissions\n"
        ),
        inline=False
    )
    
    # Section 4: ROLE MANAGEMENT
    embed.add_field(
        name="🎭 **ROLE MANAGEMENT**",
        value=(
            "`remove_role @user role_type` - Remove special role (instructor, master_family, both)\n"
            "`apply_role_permissions` - Apply role permissions to all channels\n"
            "`check_channel_permissions [channel]` - Check channel permissions\n"
        ),
        inline=False
    )
    
    # Section 5: REGISTRATION & CONSISTENCY
    embed.add_field(
        name="📝 **REGISTRATION & CONSISTENCY**",
        value=(
            "`check_consistency` - Check registry/green check consistency\n"
            "`force_register` - Force start registration for yourself\n"
        ),
        inline=False
    )
    
    # Section 6: DATA MANAGEMENT
    embed.add_field(
        name="💾 **DATA MANAGEMENT**",
        value=(
            "`view_json_data @user` - View raw JSON data for user\n"
            "`cleanup_json` - Clean orphaned JSON entries\n"
            "`migrate_json_structure` - Migrate JSON to new structure with backup\n"
            "`list_backups` - List all backup files\n"
            "`verify_json_structure` - Verify JSON structure\n"
        ),
        inline=False
    )
    
    # Section 7: SYSTEM & MAINTENANCE
    embed.add_field(
        name="🛠️ **SYSTEM & MAINTENANCE**",
        value=(
            "`setup` - Setup rules message\n"
            "`setup_bot_channel` - Create bot command channel\n"
            "`setup_log_channel` - Create log channel\n"
            "`clear_chats` - Clear active conversations\n"
            "`update_message_id ID` - Update rules message ID\n"
            "`clear_channel [#channel]` - Clear ALL messages in a channel\n"
        ),
        inline=False
    )
    
    # Section 8: JSON SYNCHRONIZATION
    embed.add_field(
        name="🔄 **JSON SYNCHRONIZATION**",
        value=(
            "`update_json_roles` - Force immediate JSON sync\n"
            "`force_json_sync @user` - Force sync for specific user\n"
            "`json_task_status` - Show JSON task status\n"
            "`start_json_task` - Start JSON sync task\n"
            "`stop_json_task` - Stop JSON sync task\n"
            "`verify_json_roles @user` - Verify JSON role sync\n"
        ),
        inline=False
    )
    
    # Section 9: SYSTEM MONITORING
    embed.add_field(
        name="📈 **SYSTEM MONITORING**",
        value=(
            "`monitoring_status` - Show monitoring task status\n"
            "`start_monitoring` - Start system monitoring\n"
            "`stop_monitoring` - Stop system monitoring\n"
            "`test_alert` - Test monitoring alert system\n"
            "`update_monitoring_config setting value` - Update monitoring thresholds\n"
        ),
        inline=False
    )
    
    # Section 10: TESTING & DEBUGGING
    embed.add_field(
        name="🐛 **TESTING & DEBUGGING**",
        value=(
            "`debug_ids` - Show all configuration IDs\n"
            "`check_message ID` - Check message reactions\n"
        ),
        inline=False
    )
    
    # Section 11: PUBLIC COMMANDS
    embed.add_field(
        name="🌐 **PUBLIC COMMANDS**",
        value=(
            "`!force_register` - Force start registration for yourself\n"
        ),
        inline=False
    )
    
    embed.set_footer(
        text="🚀 Bot v2.0.0 | Commands only work in bot-commands channel | Prefix: !"
    )
    
    return embed

async def auto_setup_general_chat_button():
    """
    Automatically send the private chat request button message in general-chat on startup.
    Only creates if not already exists.
    """
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        print("❌ Guild not found for auto-setting up general-chat button")
        return
    
    general_chat = guild.get_channel(GENERAL_CHAT_CHANNEL_ID)
    if not general_chat:
        print("❌ General chat channel not found for auto-setting up button")
        return
    
    try:
        # Check if button message already exists (by looking for a message with our button)
        button_message_found = False
        async for message in general_chat.history(limit=50):
            if message.author == bot.user and message.components:
                # Check if this message has our button
                for action_row in message.components:
                    for component in action_row.children:
                        if component.custom_id == "request_private_chat":
                            button_message_found = True
                            break
                if button_message_found:
                    break
        
        # If no button message found, create one
        if not button_message_found:
            print("📌 Creating private chat request button message in general-chat...")
            
            embed = discord.Embed(
                title="💬 Need to Talk to Us?",
                description=(
                    "**Click the button below to start a private conversation!**\n\n"
                    "## 🔐 **HOW IT WORKS**\n"
                    "1. Click the **📩 Request Private Chat** button below\n"
                    "2. A private chat will be created just for you\n"
                    "3. Only you and our admin team can see it\n"
                    "4. We'll respond to you in that private chat\n\n"
                    "## ⚠️ **IMPORTANT RULES**\n"
                    "• **DO NOT TYPE IN THIS CHANNEL**\n"
                    "• Use the button every time you need to talk to us\n"
                    "• If you already have a private chat, clicking will show you your existing chat\n"
                    "• Only admins can delete private chats\n\n"
                    "## 🎯 **WHEN TO USE THIS**\n"
                    "• Questions about classes\n"
                    "• Schedule changes\n"
                    "• Payment inquiries\n"
                    "• Any private matter\n"
                ),
                color=discord.Color.blue()
            )
            
            view = GeneralChatButtonView()
            await general_chat.send(embed=embed, view=view)
            
            print("✅ Private chat request button message created in general-chat")
            
    except Exception as e:
        print(f"❌ Error auto-setting up general-chat button: {e}")
        import traceback
        traceback.print_exc()

# =============================================================================
# AUTO-SETUP FUNCTIONS FOR WELCOME CHANNEL
# =============================================================================
async def auto_setup_welcome_channel():
    """
    Automatically set up the welcome channel (rules message) with registration button on bot startup.
    Only creates if not already exists.
    """
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        print("❌ Guild not found for auto-setting up welcome channel")
        return
    
    welcome_channel = guild.get_channel(RULES_CHANNEL_ID)
    if not welcome_channel:
        print("❌ Welcome channel (rules channel) not found")
        return
    
    try:
        # Check if rules message already exists and is pinned
        pinned_messages = await welcome_channel.pins()
        rules_message_exists = False
        rules_message_id = None
        
        for pinned_msg in pinned_messages:
            if pinned_msg.author == bot.user and pinned_msg.embeds:
                for embed in pinned_msg.embeds:
                    if embed.title and "Server Rules & Registration" in embed.title:
                        rules_message_exists = True
                        rules_message_id = pinned_msg.id
                        print(f"✅ Rules message already pinned: {pinned_msg.id}")
                        
                        # Check if it has our button view
                        has_button = False
                        if pinned_msg.components:
                            for component in pinned_msg.components:
                                if component.children and component.children[0].custom_id == "rules_register_button":
                                    has_button = True
                                    break
                        
                        if not has_button:
                            # Update existing message with button
                            print(f"🔄 Updating existing rules message with button view...")
                            view = RulesRegistrationView()
                            await pinned_msg.edit(view=view)
                            print(f"✅ Added registration button to existing rules message")
                        
                        break
                if rules_message_exists:
                    break
        
        # If no existing rules message, check all messages in the channel (not just pinned)
        if not rules_message_exists:
            async for message in welcome_channel.history(limit=100):
                if message.author == bot.user and message.embeds:
                    for embed in message.embeds:
                        if embed.title and "Server Rules & Registration" in embed.title:
                            rules_message_exists = True
                            rules_message_id = message.id
                            print(f"✅ Found existing rules message: {message.id}")
                            
                            # Check if it has our button view
                            has_button = False
                            if message.components:
                                for component in message.components:
                                    if component.children and component.children[0].custom_id == "rules_register_button":
                                        has_button = True
                                        break
                            
                            if not has_button:
                                # Update existing message with button
                                print(f"🔄 Updating existing rules message with button view...")
                                view = RulesRegistrationView()
                                await message.edit(view=view)
                                print(f"✅ Added registration button to existing rules message")
                            
                            # Pin it if not already pinned
                            if not message.pinned:
                                await message.pin(reason="Rules message with registration button")
                                print(f"📌 Pinned existing rules message")
                            
                            break
                if rules_message_exists:
                    break
        
        # If no rules message found, create one
        if not rules_message_exists:
            print("📌 Creating and pinning rules message with registration button...")
            
            # Create the rules embed
            rules_embed = discord.Embed(
                title="📜 Server Rules & Registration",
                description="**Welcome to our Tae Kwon Do Server!** 👨‍👩‍👧‍👦\n\n"
                          "**Rules:**\n"
                          "1. Be respectful to all family members\n"
                          "2. No bullying or harassment\n"
                          "3. Keep conversations family-friendly\n"
                          "4. Respect everyone's privacy\n"
                          "5. Have fun and build our community!\n\n"
                          "**To register, click the '✅ Register Now' button below.**\n"
                          "You will receive a DM from 백호 (baekho) to complete the process.\n\n"
                          "**After registration:**\n"
                          "• You'll get access to the server\n"
                          "• Use the 📩 button in general-chat to talk to us\n"
                          "• Your nickname will be updated automatically",
                color=discord.Color.purple()
            )
            
            # Send and pin the rules message with button
            view = RulesRegistrationView()
            rules_message = await welcome_channel.send(embed=rules_embed, view=view)
            await rules_message.pin(reason="Auto-pinned rules message with registration button on startup")
            
            # Update config with new message ID
            await update_welcome_message_id(rules_message.id)
            
            print(f"✅ Rules message with button created and pinned: {rules_message.id}")
            
            # Log to log channel
            log_embed = discord.Embed(
                title="📌 Rules Message Auto-Pinned",
                description=f"Rules message with registration button has been auto-pinned in {welcome_channel.mention}",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            await send_to_log_channel(guild, "", log_embed)
        
    except Exception as e:
        print(f"❌ Error auto-setting up welcome channel: {e}")
        import traceback
        traceback.print_exc()

async def update_welcome_message_id(new_message_id: int):
    """
    Update the rules message ID in config.txt.
    
    Args:
        new_message_id: The new message ID to save
    """
    try:
        # Read current config
        config_dict = {}
        try:
            with open('config.txt', 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        config_dict[key.strip()] = value.strip()
        except FileNotFoundError:
            print("❌ config.txt not found")
            return
        
        # Update the message ID
        config_dict['RULES_MESSAGE_ID'] = str(new_message_id)
        
        # Write updated config back
        with open('config.txt', 'w') as f:
            for key, value in config_dict.items():
                f.write(f"{key}={value}\n")
        
        # Update the global variable
        globals()['RULES_MESSAGE_ID'] = new_message_id
        
        print(f"✅ Updated rules message ID to: {new_message_id}")
        
    except Exception as e:
        print(f"❌ Error updating config file: {e}")

# =============================================================================
# CHANNEL CLEARING FUNCTION
# =============================================================================
@bot_command.command(name="clear_channel")
@bot_channel_only()
async def chat_clear_channel(ctx, channel: discord.TextChannel = None):
    """
    Clear ALL messages in a channel for a fresh start.
    
    Usage:
    !bot_command clear_channel #channel-name
    !bot_command clear_channel (clears current channel)
    
    Warning: This cannot be undone!
    """
    if not channel:
        channel = ctx.channel
    
    # Double-check authorization
    if ctx.author.id != ADMIN_USER_ID:
        await ctx.send("❌ Only admin can clear channels.", ephemeral=True)
        return
    
    # Show confirmation
    class ConfirmClearView(discord.ui.View):
        """Confirmation view for channel clearing."""
        
        def __init__(self, channel_id: int, user_id: int):
            super().__init__(timeout=60)
            self.channel_id = channel_id
            self.user_id = user_id
            self.confirmed = False
            self.timed_out = False
        
        async def on_timeout(self):
            """Handle view timeout."""
            self.timed_out = True
            # Disable all buttons on timeout
            for child in self.children:
                child.disabled = True
            
            # Try to update the message
            try:
                # Get the original message from the interaction if available
                if hasattr(self, 'message') and self.message:
                    await self.message.edit(content="⏰ **Confirmation timed out.** Please run the command again if you still want to clear the channel.", view=self)
            except:
                pass
        
        @discord.ui.button(label="✅ Yes, Clear Everything", style=discord.ButtonStyle.danger)
        async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            """Confirm and execute channel clearing."""
            # Check if timed out
            if self.timed_out:
                await interaction.response.send_message("❌ This confirmation has timed out. Please run the command again.", ephemeral=True)
                return
            
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("❌ Only the command author can confirm this action.", ephemeral=True)
                return
            
            self.confirmed = True
            self.stop()
            
            channel = interaction.guild.get_channel(self.channel_id)
            if not channel:
                await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
                return
            
            # Send initial response
            await interaction.response.send_message("🗑️ Clearing channel... This may take a while...", ephemeral=True)
            
            try:
                deleted_count = 0
                
                # Function to delete messages in batches
                async def delete_batch():
                    nonlocal deleted_count
                    async for message in channel.history(limit=None):
                        try:
                            await message.delete()
                            deleted_count += 1
                            # Small delay to avoid rate limits
                            if deleted_count % 10 == 0:
                                await asyncio.sleep(0.5)
                        except discord.NotFound:
                            pass  # Message already deleted
                        except discord.Forbidden:
                            await interaction.followup.send(
                                f"❌ No permission to delete messages in {channel.mention}",
                                ephemeral=True
                            )
                            return False
                        except Exception as e:
                            print(f"Error deleting message: {e}")
                            continue
                    return True
                
                # Delete all messages
                success = await delete_batch()
                
                if success:
                    # Send completion message
                    completion_embed = discord.Embed(
                        title="✅ Channel Cleared",
                        description=f"Successfully cleared {deleted_count} messages from {channel.mention}",
                        color=discord.Color.green()
                    )
                    
                    # Delete the original confirmation message
                    try:
                        if hasattr(self, 'message') and self.message:
                            await self.message.delete()
                            print(f"🗑️ Deleted confirmation message for channel clear")
                    except:
                        pass
                    
                    # Send the completion message
                    await interaction.followup.send(embed=completion_embed, ephemeral=True)
                    
                    # Log to log channel
                    log_embed = discord.Embed(
                        title="🗑️ Channel Cleared",
                        description=f"**Channel:** {channel.mention}\n"
                                  f"**Messages cleared:** {deleted_count}\n"
                                  f"**By:** {interaction.user.mention}",
                        color=discord.Color.orange(),
                        timestamp=datetime.now(timezone.utc)
                    )
                    await send_to_log_channel(interaction.guild, "", log_embed)
                    
                    print(f"🧹 Cleared {deleted_count} messages from #{channel.name}")
            
            except Exception as e:
                error_embed = discord.Embed(
                    title="❌ Error Clearing Channel",
                    description=f"Error: {str(e)}",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=error_embed, ephemeral=True)
        
        @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
        async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            """Cancel the clearing operation."""
            # Check if timed out
            if self.timed_out:
                await interaction.response.send_message("❌ This confirmation has timed out. Please run the command again.", ephemeral=True)
                return
            
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("❌ Only the command author can cancel this action.", ephemeral=True)
                return
            
            self.confirmed = False
            self.stop()
            
            # Delete the confirmation message
            try:
                if hasattr(self, 'message') and self.message:
                    await self.message.delete()
                    print(f"🗑️ Deleted cancelled confirmation message")
                    await interaction.response.send_message("✅ Clear operation cancelled.", ephemeral=True)
                else:
                    await interaction.response.edit_message(
                        content="✅ Clear operation cancelled.",
                        embed=None,
                        view=None
                    )
            except:
                await interaction.response.edit_message(
                    content="✅ Clear operation cancelled.",
                    embed=None,
                    view=None
                )
    
    # Show confirmation embed
    embed = discord.Embed(
        title="⚠️ CLEAR CHANNEL CONFIRMATION",
        description=f"**You are about to clear ALL messages in {channel.mention}**\n\n"
                   f"**This action will:**\n"
                   f"• Delete ALL messages in the channel\n"
                   f"• Cannot be undone\n"
                   f"• May take several minutes\n\n"
                   f"**Are you absolutely sure?**",
        color=discord.Color.red()
    )
    
    embed.add_field(
        name="⚠️ Warning",
        value="This is a destructive operation. All message history will be permanently deleted.",
        inline=False
    )
    
    view = ConfirmClearView(channel.id, ctx.author.id)
    message = await ctx.send(embed=embed, view=view, ephemeral=True)
    view.message = message  # Store message reference for timeout handling

# =============================================================================
# SYSTEM MONITOR CLASS (MODIFIED)
# =============================================================================

class SystemMonitor:
    """System monitoring class for Raspberry Pi with enhanced hourly status checks."""
    
    def __init__(self, bot):
        self.bot = bot
        # Critical thresholds
        self.cpu_temp_critical = 75.0  # °C - Critical threshold
        self.memory_critical = 90.0    # % - Critical threshold  
        self.disk_critical = 90.0      # % - Critical threshold
        self.registry_critical = 10 * 1024 * 1024  # 10 MB - Critical threshold
        
        # Warning thresholds (for hourly reports)
        self.cpu_temp_warning = 65.0   # °C - Warning threshold
        self.memory_warning = 80.0     # % - Warning threshold
        self.disk_warning = 80.0       # % - Warning threshold
        self.registry_warning = 5 * 1024 * 1024  # 5 MB - Warning threshold
        
        # Monitoring settings
        self.check_interval = 300  # 5 minutes (in seconds)
        self.last_alert_time = {}
        self.alert_cooldown = 3600  # 1 hour cooldown between alerts for same metric
        self.last_hourly_report = 0  # Track when we last sent hourly report
        self.report_count = 0  # Track number of reports sent
        
        # Performance tracking
        self.performance_history = {
            'cpu_temps': [],
            'memory_usage': [],
            'disk_usage': [],
            'registry_sizes': []
        }
        self.MAX_HISTORY = 144  # Store 24 hours of data (24 * 6 checks/hour)

    def get_status_emoji(self, value, warning_threshold, critical_threshold, value_type="percent"):
        """Get appropriate emoji for status based on value and thresholds."""
        if value is None:
            return "❓"
        
        if value_type == "temp":
            if value >= critical_threshold:
                return "🔥"  # Critical
            elif value >= warning_threshold:
                return "⚠️"  # Warning
            else:
                return "✅"  # Normal
        
        elif value_type == "percent":
            if value >= critical_threshold:
                return "🔴"  # Critical
            elif value >= warning_threshold:
                return "🟡"  # Warning
            else:
                return "🟢"  # Normal
        
        elif value_type == "size":
            if value >= critical_threshold:
                return "📈"  # Critical
            elif value >= warning_threshold:
                return "📊"  # Warning
            else:
                return "📉"  # Normal
        
        return "❓"
    
    def format_uptime(self, seconds):
        """Convert seconds to human readable uptime format."""
        if seconds is None:
            return "Unknown"
        
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if secs > 0 or not parts:
            parts.append(f"{secs}s")
        
        return " ".join(parts)
    
    def format_file_size(self, size_bytes):
        """Convert bytes to human readable format."""
        if size_bytes is None:
            return "Unknown"
        
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
    
    async def send_enhanced_hourly_report(self):
        """Send enhanced hourly system status report to log channel."""
        try:
            current_time = time.time()
            
            # Check if at least 1 hour has passed since last report
            if current_time - self.last_hourly_report < 3600:
                return
            
            guild = self.bot.get_guild(GUILD_ID)
            if not guild or not LOG_CHANNEL_ID:
                return
            
            log_channel = guild.get_channel(LOG_CHANNEL_ID)
            if not log_channel:
                return
            
            # Get all system metrics
            cpu_temp = await self.get_cpu_temperature()
            cpu_usage = self.get_cpu_usage()
            memory_usage = self.get_memory_usage()
            disk_usage = self.get_disk_usage()
            registry_size = self.get_registry_file_size()
            
            # Get uptime info
            system_uptime = self.get_system_uptime()
            bot_uptime = self.get_bot_uptime(getattr(self.bot, 'start_time', current_time))
            
            # Get network info
            network_info = self.get_network_info()
            
            # Get process count
            process_count = self.get_process_count()
            
            # Get bot statistics
            total_users = len(registered_users)
            active_chats = len(private_channels)
            registered_today = self.get_registrations_today()
            
            # Update performance history
            self.update_performance_history(cpu_temp, memory_usage, disk_usage, registry_size)
            
            # Determine overall system health
            overall_status = self.get_overall_system_status(
                cpu_temp, memory_usage, disk_usage, registry_size
            )
            
            # Create enhanced hourly status embed
            embed = discord.Embed(
                title="📊 ENHANCED HOURLY SYSTEM STATUS",
                description=f"**Time:** <t:{int(current_time)}:F>\n"
                          f"**Bot:** {self.bot.user.name}\n"
                          f"**Overall Status:** {overall_status}",
                color=self.get_status_color(overall_status),
                timestamp=datetime.now(timezone.utc)
            )
            
            # Section 1: SYSTEM HEALTH (Critical Metrics)
            embed.add_field(
                name="🩺 SYSTEM HEALTH",
                value=self.format_health_section(cpu_temp, cpu_usage, memory_usage, disk_usage),
                inline=False
            )
            
            # Section 2: BOT STATISTICS
            embed.add_field(
                name="🤖 BOT STATISTICS",
                value=self.format_bot_stats(total_users, active_chats, registered_today),
                inline=True
            )
            
            # Section 3: STORAGE & DATA
            embed.add_field(
                name="💾 STORAGE & DATA",
                value=self.format_storage_section(disk_usage, registry_size, total_users),
                inline=True
            )
            
            # Section 4: UPTIME & PERFORMANCE
            embed.add_field(
                name="⏱️ UPTIME & PERFORMANCE",
                value=self.format_uptime_section(system_uptime, bot_uptime, process_count, network_info),
                inline=False
            )
            
            # Section 5: BACKGROUND TASKS
            embed.add_field(
                name="🔄 BACKGROUND TASKS",
                value=self.format_task_section(),
                inline=True
            )
            
            # Section 6: PERFORMANCE TRENDS
            if len(self.performance_history['cpu_temps']) > 1:
                embed.add_field(
                    name="📈 PERFORMANCE TRENDS (24h)",
                    value=self.format_trends_section(),
                    inline=True
                )
            
            # Section 7: ALERTS & NOTIFICATIONS
            active_alerts = self.check_active_alerts(cpu_temp, memory_usage, disk_usage, registry_size)
            if active_alerts:
                embed.add_field(
                    name="🚨 ACTIVE ALERTS",
                    value="\n".join([f"• {alert}" for alert in active_alerts]),
                    inline=False
                )
                embed.color = discord.Color.red()
            
            # Footer with thresholds
            footer_text = (
                f"Report #{self.report_count} | "
                f"CPU: ≥{self.cpu_temp_critical}°C | "
                f"Mem: ≥{self.memory_critical}% | "
                f"Disk: ≥{self.disk_critical}% | "
                f"Next: <t:{int(current_time) + 3600}:R>"
            )
            embed.set_footer(text=footer_text)
            
            await log_channel.send(embed=embed)
            self.last_hourly_report = current_time
            self.report_count += 1
            
            print(f"📊 Sent enhanced hourly system status report to log channel")
            
        except Exception as e:
            print(f"❌ Error sending enhanced hourly status report: {e}")
            import traceback
            traceback.print_exc()
    
    def format_health_section(self, cpu_temp, cpu_usage, memory_usage, disk_usage):
        """Format system health section with status indicators."""
        cpu_emoji = self.get_status_emoji(cpu_temp, self.cpu_temp_warning, self.cpu_temp_critical, "temp")
        memory_emoji = self.get_status_emoji(memory_usage, self.memory_warning, self.memory_critical, "percent")
        disk_emoji = self.get_status_emoji(disk_usage, self.disk_warning, self.disk_critical, "percent")
        
        lines = []
        lines.append(f"{cpu_emoji} **CPU:** {cpu_temp or 'N/A'}°C | {cpu_usage or 'N/A'}%")
        lines.append(f"{memory_emoji} **Memory:** {memory_usage or 'N/A'}%")
        lines.append(f"{disk_emoji} **Disk:** {disk_usage or 'N/A'}%")
        
        # Add thresholds info
        lines.append(f"")
        lines.append(f"**Thresholds:** CPU≥{self.cpu_temp_critical}°C, Mem≥{self.memory_critical}%, Disk≥{self.disk_critical}%")
        
        return "\n".join(lines)
    
    def format_bot_stats(self, total_users, active_chats, registered_today):
        """Format bot statistics section."""
        lines = []
        lines.append(f"👤 **Users:** {total_users}")
        lines.append(f"💬 **Active Chats:** {active_chats}")
        lines.append(f"📝 **Reg Today:** {registered_today}")
        lines.append(f"📁 **JSON Size:** {self.format_file_size(self.get_registry_file_size())}")
        return "\n".join(lines)
    
    def format_storage_section(self, disk_usage, registry_size, total_users):
        """Format storage and data section."""
        lines = []
        
        # Disk usage with bar
        disk_bar = self.create_progress_bar(disk_usage or 0)
        lines.append(f"💿 **Disk:** {disk_usage or 0}%")
        lines.append(f"`{disk_bar}`")
        
        # Registry info
        registry_emoji = self.get_status_emoji(registry_size, self.registry_warning, self.registry_critical, "size")
        lines.append(f"{registry_emoji} **Registry:** {self.format_file_size(registry_size)}")
        lines.append(f"📊 **Avg/User:** {self.format_file_size((registry_size or 0) / max(total_users, 1))}")
        
        return "\n".join(lines)
    
    def format_uptime_section(self, system_uptime, bot_uptime, process_count, network_info):
        """Format uptime and performance section."""
        lines = []
        lines.append(f"🖥️ **System:** {self.format_uptime(system_uptime)}")
        lines.append(f"🤖 **Bot:** {self.format_uptime(bot_uptime)}")
        lines.append(f"⚙️ **Processes:** {process_count}")
        
        if network_info:
            lines.append(f"🌐 **Network:** {network_info}")
        
        # Load averages (Linux only)
        try:
            load_avg = os.getloadavg()
            lines.append(f"📊 **Load Avg:** {load_avg[0]:.2f}, {load_avg[1]:.2f}, {load_avg[2]:.2f}")
        except:
            pass
        
        return "\n".join(lines)
    
    def format_task_section(self):
        """Format background tasks section."""
        lines = []
        
        # JSON sync task
        json_task = update_json_with_roles
        json_status = "✅" if json_task.is_running() else "❌"
        lines.append(f"{json_status} **JSON Sync:** {'Running' if json_task.is_running() else 'Stopped'}")
        
        # Monitoring task
        monitoring = monitoring_task
        monitor_status = "✅" if monitoring.is_running() else "❌"
        lines.append(f"{monitor_status} **Monitoring:** {'Running' if monitoring.is_running() else 'Stopped'}")
        
        # Next JSON sync time
        if json_task.is_running():
            try:
                next_run = json_task.next_iteration
                if next_run:
                    next_run_timestamp = int(next_run.timestamp())
                    lines.append(f"🔄 **Next Sync:** <t:{next_run_timestamp}:R>")
            except:
                pass
        
        return "\n".join(lines)
    
    def format_trends_section(self):
        """Format performance trends section."""
        lines = []
        
        # CPU trend
        if self.performance_history['cpu_temps']:
            cpu_min = min(self.performance_history['cpu_temps'])
            cpu_max = max(self.performance_history['cpu_temps'])
            cpu_avg = sum(self.performance_history['cpu_temps']) / len(self.performance_history['cpu_temps'])
            lines.append(f"🌡️ **CPU Temp:** {cpu_min:.1f}-{cpu_max:.1f}°C (avg: {cpu_avg:.1f}°C)")
        
        # Memory trend
        if self.performance_history['memory_usage']:
            mem_min = min(self.performance_history['memory_usage'])
            mem_max = max(self.performance_history['memory_usage'])
            mem_avg = sum(self.performance_history['memory_usage']) / len(self.performance_history['memory_usage'])
            lines.append(f"🧠 **Memory:** {mem_min:.1f}-{mem_max:.1f}% (avg: {mem_avg:.1f}%)")
        
        return "\n".join(lines)
    
    def create_progress_bar(self, percentage, length=10):
        """Create a text-based progress bar."""
        filled = int(round(length * percentage / 100))
        bar = '█' * filled + '░' * (length - filled)
        return bar
    
    def get_overall_system_status(self, cpu_temp, memory_usage, disk_usage, registry_size):
        """Determine overall system status based on all metrics."""
        statuses = []
        
        if cpu_temp and cpu_temp >= self.cpu_temp_critical:
            statuses.append("CPU Critical")
        elif cpu_temp and cpu_temp >= self.cpu_temp_warning:
            statuses.append("CPU Warning")
        
        if memory_usage and memory_usage >= self.memory_critical:
            statuses.append("Memory Critical")
        elif memory_usage and memory_usage >= self.memory_warning:
            statuses.append("Memory Warning")
        
        if disk_usage and disk_usage >= self.disk_critical:
            statuses.append("Disk Critical")
        elif disk_usage and disk_usage >= self.disk_warning:
            statuses.append("Disk Warning")
        
        if registry_size and registry_size >= self.registry_critical:
            statuses.append("Registry Critical")
        elif registry_size and registry_size >= self.registry_warning:
            statuses.append("Registry Warning")
        
        if not statuses:
            return "✅ **All Systems Normal**"
        elif any("Critical" in s for s in statuses):
            return f"🚨 **CRITICAL: {', '.join(statuses)}**"
        else:
            return f"⚠️ **WARNINGS: {', '.join(statuses)}**"
    
    def get_status_color(self, status_text):
        """Get embed color based on status text."""
        if "CRITICAL" in status_text:
            return discord.Color.red()
        elif "WARNINGS" in status_text:
            return discord.Color.orange()
        elif "Normal" in status_text:
            return discord.Color.green()
        else:
            return discord.Color.blue()
    
    def check_active_alerts(self, cpu_temp, memory_usage, disk_usage, registry_size):
        """Check for active alerts that need immediate attention."""
        alerts = []
        
        if cpu_temp and cpu_temp >= self.cpu_temp_critical:
            alerts.append(f"🔥 CPU Temperature: {cpu_temp}°C (Critical: ≥{self.cpu_temp_critical}°C)")
        
        if memory_usage and memory_usage >= self.memory_critical:
            alerts.append(f"💾 Memory Usage: {memory_usage}% (Critical: ≥{self.memory_critical}%)")
        
        if disk_usage and disk_usage >= self.disk_critical:
            alerts.append(f"💿 Disk Usage: {disk_usage}% (Critical: ≥{self.disk_critical}%)")
        
        if registry_size and registry_size >= self.registry_critical:
            alerts.append(f"📁 Registry Size: {self.format_file_size(registry_size)} (Critical: ≥{self.format_file_size(self.registry_critical)})")
        
        return alerts
    
    def update_performance_history(self, cpu_temp, memory_usage, disk_usage, registry_size):
        """Update performance history for trends."""
        if cpu_temp:
            self.performance_history['cpu_temps'].append(cpu_temp)
            if len(self.performance_history['cpu_temps']) > self.MAX_HISTORY:
                self.performance_history['cpu_temps'].pop(0)
        
        if memory_usage:
            self.performance_history['memory_usage'].append(memory_usage)
            if len(self.performance_history['memory_usage']) > self.MAX_HISTORY:
                self.performance_history['memory_usage'].pop(0)
        
        if disk_usage:
            self.performance_history['disk_usage'].append(disk_usage)
            if len(self.performance_history['disk_usage']) > self.MAX_HISTORY:
                self.performance_history['disk_usage'].pop(0)
        
        if registry_size:
            self.performance_history['registry_sizes'].append(registry_size)
            if len(self.performance_history['registry_sizes']) > self.MAX_HISTORY:
                self.performance_history['registry_sizes'].pop(0)
    
    def get_registrations_today(self):
        """Get number of registrations in the last 24 hours."""
        try:
            count = 0
            today = datetime.now(timezone.utc).date()
            
            for user_data in registered_users.values():
                registered_at = user_data.get('registered_at')
                if registered_at:
                    try:
                        # Parse the ISO format timestamp
                        reg_date = datetime.fromisoformat(registered_at.replace('Z', '+00:00')).date()
                        if reg_date == today:
                            count += 1
                    except:
                        continue
            
            return count
        except:
            return 0
    
    def get_process_count(self):
        """Get number of running processes."""
        try:
            return len(psutil.pids())
        except:
            return "N/A"
    
    def get_network_info(self):
        """Get network information."""
        try:
            net_io = psutil.net_io_counters()
            return f"↑{self.format_file_size(net_io.bytes_sent)} ↓{self.format_file_size(net_io.bytes_recv)}"
        except:
            return None

    # Keep existing methods for getting system metrics
    async def get_cpu_temperature(self):
        """Get CPU temperature for Raspberry Pi."""
        try:
            if platform.system() == "Linux" and os.path.exists("/sys/class/thermal/thermal_zone0/temp"):
                with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                    temp = float(f.read().strip()) / 1000.0
                return temp
            elif os.path.exists("/sys/class/thermal/thermal_zone1/temp"):
                with open("/sys/class/thermal/thermal_zone1/temp", "r") as f:
                    temp = float(f.read().strip()) / 1000.0
                return temp
            else:
                # Try using vcgencmd for Raspberry Pi
                try:
                    result = subprocess.run(['vcgencmd', 'measure_temp'], 
                                           capture_output=True, text=True)
                    if result.returncode == 0:
                        temp_str = result.stdout.strip()
                        temp = float(temp_str.split('=')[1].split("'")[0])
                        return temp
                except:
                    pass
                
                # Try using psutil as last resort
                if hasattr(psutil, "sensors_temperatures"):
                    temps = psutil.sensors_temperatures()
                    if 'cpu-thermal' in temps:
                        return temps['cpu-thermal'][0].current
                    elif 'coretemp' in temps:
                        return temps['coretemp'][0].current
                    
                return None
        except Exception as e:
            print(f"❌ Error reading CPU temperature: {e}")
            return None
    
    def get_memory_usage(self):
        """Get memory usage percentage."""
        try:
            memory = psutil.virtual_memory()
            return memory.percent
        except Exception as e:
            print(f"❌ Error reading memory usage: {e}")
            return None
    
    def get_disk_usage(self):
        """Get disk usage percentage."""
        try:
            disk = psutil.disk_usage('/')
            return disk.percent
        except Exception as e:
            print(f"❌ Error reading disk usage: {e}")
            return None
    
    def get_cpu_usage(self):
        """Get CPU usage percentage."""
        try:
            return psutil.cpu_percent(interval=1)
        except Exception as e:
            print(f"❌ Error reading CPU usage: {e}")
            return None
    
    def get_system_uptime(self):
        """Get system uptime in seconds."""
        try:
            return time.time() - psutil.boot_time()
        except Exception as e:
            print(f"❌ Error reading system uptime: {e}")
            return None
    
    def get_registry_file_size(self):
        """Get the size of the registered_users.json file."""
        try:
            if os.path.exists(REGISTRY_FILE):
                size = os.path.getsize(REGISTRY_FILE)
                return size  # Size in bytes
            return 0
        except Exception as e:
            print(f"❌ Error reading registry file size: {e}")
            return None
    
    def get_bot_uptime(self, start_time):
        """Get bot uptime in seconds."""
        try:
            return time.time() - start_time
        except Exception as e:
            print(f"❌ Error calculating bot uptime: {e}")
            return None
    
    async def check_system_metrics(self):
        """Check all system metrics and send alerts only if critical."""
        try:
            # Check CPU temperature
            cpu_temp = await self.get_cpu_temperature()
            if cpu_temp and cpu_temp >= self.cpu_temp_critical:
                await self.send_monitoring_alert("cpu_temp", cpu_temp, self.cpu_temp_critical)
            
            # Check memory usage
            memory_usage = self.get_memory_usage()
            if memory_usage and memory_usage >= self.memory_critical:
                await self.send_monitoring_alert("memory", memory_usage, self.memory_critical)
            
            # Check disk usage
            disk_usage = self.get_disk_usage()
            if disk_usage and disk_usage >= self.disk_critical:
                await self.send_monitoring_alert("disk", disk_usage, self.disk_critical)
            
            # Check registry file size
            registry_size = self.get_registry_file_size()
            if registry_size and registry_size >= self.registry_critical:
                await self.send_monitoring_alert("registry", registry_size, self.registry_critical)
            
            # Send enhanced hourly report
            await self.send_enhanced_hourly_report()
            
            # SILENT mode: Minimal console output
            # Only log errors, not normal status
            
        except Exception as e:
            print(f"❌ Error in system metrics check: {e}")
            import traceback
            traceback.print_exc()
    
    async def send_monitoring_alert(self, metric, value, threshold):
        """Send alert to admin via Discord DM when critical thresholds are exceeded."""
        try:
            admin_user = self.bot.get_user(ADMIN_USER_ID)
            if not admin_user:
                print(f"❌ Admin user not found: {ADMIN_USER_ID}")
                return
            
            # Check cooldown
            current_time = time.time()
            if metric in self.last_alert_time:
                time_since_last_alert = current_time - self.last_alert_time[metric]
                if time_since_last_alert < self.alert_cooldown:
                    print(f"⚠️ Alert for {metric} is in cooldown ({int(self.alert_cooldown - time_since_last_alert)}s remaining)")
                    return
            
            # Update last alert time
            self.last_alert_time[metric] = current_time
            
            # Create alert embed
            if metric == "cpu_temp":
                title = "🔥 CPU Temperature Critical"
                description = f"CPU temperature is at **{value}°C** which exceeds the critical threshold of **{threshold}°C**!"
                color = discord.Color.red()
                icon = "🔥"
            elif metric == "memory":
                title = "💾 Memory Usage Critical"
                description = f"Memory usage is at **{value}%** which exceeds the critical threshold of **{threshold}%**!"
                color = discord.Color.orange()
                icon = "💾"
            elif metric == "disk":
                title = "💿 Disk Usage Critical"
                description = f"Disk usage is at **{value}%** which exceeds the critical threshold of **{threshold}%**!"
                color = discord.Color.purple()
                icon = "💿"
            elif metric == "registry":
                title = "📁 Registry File Size Critical"
                description = f"Registry file size is **{self.format_file_size(value)}** which exceeds the critical threshold of **{self.format_file_size(threshold)}**!"
                color = discord.Color.dark_purple()
                icon = "📁"
            else:
                return
            
            embed = discord.Embed(
                title=f"{icon} {title}",
                description=description,
                color=color,
                timestamp=datetime.now(timezone.utc)
            )
            
            # Add system information
            embed.add_field(name="🖥️ Host", value=platform.node(), inline=True)
            embed.add_field(name="📅 Time", value=f"<t:{int(current_time)}:T>", inline=True)
            embed.add_field(name="🚨 Metric", value=metric.replace("_", " ").title(), inline=True)
            
            # Add recommendations
            if metric == "cpu_temp":
                embed.add_field(
                    name="💡 Recommendations",
                    value="• Check cooling system\n• Reduce CPU load\n• Ensure proper ventilation",
                    inline=False
                )
            elif metric == "memory":
                embed.add_field(
                    name="💡 Recommendations",
                    value="• Close unnecessary applications\n• Check for memory leaks\n• Consider adding more RAM",
                    inline=False
                )
            elif metric == "disk":
                embed.add_field(
                    name="💡 Recommendations",
                    value="• Clean up temporary files\n• Archive old logs\n• Expand storage capacity",
                    inline=False
                )
            elif metric == "registry":
                embed.add_field(
                    name="💡 Recommendations",
                    value="• Clean up old user data\n• Backup and archive\n• Consider database migration",
                    inline=False
                )
            
            embed.set_footer(text="System Monitoring Alert")
            
            # Send DM to admin
            try:
                await admin_user.send(embed=embed)
                print(f"⚠️ Sent {metric} alert to admin: {value} exceeds {threshold}")
            except discord.Forbidden:
                print(f"❌ Cannot send DM to admin. Admin may have DMs disabled.")
                
                # Try to log to log channel as fallback
                error_embed = discord.Embed(
                    title=f"⚠️ System Alert - {title}",
                    description=f"**Could not send DM to admin.**\n\n{description}",
                    color=color,
                    timestamp=datetime.now(timezone.utc)
                )
                await send_to_log_channel(self.bot.get_guild(GUILD_ID), "", error_embed)
                
        except Exception as e:
            print(f"❌ Error sending monitoring alert: {e}")

# =============================================================================
# MONITORING TASK
# =============================================================================
@tasks.loop(seconds=300)  # Run every 5 minutes
async def monitoring_task():
    """Background task to check system metrics periodically."""
    global system_monitor
    if system_monitor:
        await system_monitor.check_system_metrics()

@monitoring_task.before_loop
async def before_monitoring_task():
    """Wait for bot to be ready before starting monitoring."""
    await bot.wait_until_ready()
    print("📊 System monitoring task is waiting to start...")
    print("📊 System monitoring task is waiting to start...")

# =============================================================================
# MONITORING COMMANDS
# =============================================================================
@bot_command.command(name="system_status")
@bot_channel_only()
async def chat_system_status(ctx):
    """Display current enhanced system status with detailed information."""
    global system_monitor
    if not system_monitor:
        await ctx.send("❌ System monitor not initialized.", ephemeral=True)
        return
    
    # Create a comprehensive system status embed
    embed = discord.Embed(
        title="📊 SYSTEM STATUS REPORT",
        description=f"**Generated:** <t:{int(time.time())}:F>\n"
                  f"**Bot:** {bot.user.name}",
        color=discord.Color.blue(),
        timestamp=datetime.now(timezone.utc)
    )
    
    # Get all system metrics
    cpu_temp = await system_monitor.get_cpu_temperature()
    cpu_usage = system_monitor.get_cpu_usage()
    memory_usage = system_monitor.get_memory_usage()
    disk_usage = system_monitor.get_disk_usage()
    registry_size = system_monitor.get_registry_file_size()
    
    # Get uptime info
    system_uptime = system_monitor.get_system_uptime()
    bot_uptime = system_monitor.get_bot_uptime(getattr(bot, 'start_time', time.time()))
    
    # Section 1: SYSTEM HEALTH
    cpu_emoji = system_monitor.get_status_emoji(cpu_temp, system_monitor.cpu_temp_warning, system_monitor.cpu_temp_critical, "temp")
    memory_emoji = system_monitor.get_status_emoji(memory_usage, system_monitor.memory_warning, system_monitor.memory_critical, "percent")
    disk_emoji = system_monitor.get_status_emoji(disk_usage, system_monitor.disk_warning, system_monitor.disk_critical, "percent")
    
    health_section = (
        f"{cpu_emoji} **CPU Temperature:** {cpu_temp or 'N/A'}°C\n"
        f"   ↳ Usage: {cpu_usage or 'N/A'}%\n"
        f"   ↳ Thresholds: Warning≥{system_monitor.cpu_temp_warning}°C, Critical≥{system_monitor.cpu_temp_critical}°C\n\n"
        
        f"{memory_emoji} **Memory Usage:** {memory_usage or 'N/A'}%\n"
        f"   ↳ Thresholds: Warning≥{system_monitor.memory_warning}%, Critical≥{system_monitor.memory_critical}%\n\n"
        
        f"{disk_emoji} **Disk Usage:** {disk_usage or 'N/A'}%\n"
        f"   ↳ Thresholds: Warning≥{system_monitor.disk_warning}%, Critical≥{system_monitor.disk_critical}%\n"
    )
    
    embed.add_field(name="🩺 SYSTEM HEALTH", value=health_section, inline=False)
    
    # Section 2: BOT STATISTICS
    total_users = len(registered_users)
    active_chats = len(private_channels)
    registered_today = system_monitor.get_registrations_today()
    
    bot_stats = (
        f"👤 **Registered Users:** {total_users}\n"
        f"💬 **Active Private Chats:** {active_chats}\n"
        f"📝 **Registrations Today:** {registered_today}\n"
        f"📁 **Registry File Size:** {system_monitor.format_file_size(registry_size)}\n"
        f"   ↳ Thresholds: Warning≥{system_monitor.format_file_size(system_monitor.registry_warning)}, "
        f"Critical≥{system_monitor.format_file_size(system_monitor.registry_critical)}\n"
    )
    
    embed.add_field(name="🤖 BOT STATISTICS", value=bot_stats, inline=False)
    
    # Section 3: UPTIME & PERFORMANCE
    uptime_section = (
        f"🖥️ **System Uptime:** {system_monitor.format_uptime(system_uptime)}\n"
        f"🤖 **Bot Uptime:** {system_monitor.format_uptime(bot_uptime)}\n"
        f"⚙️ **Process Count:** {system_monitor.get_process_count()}\n"
    )
    
    # Add load averages if available
    try:
        load_avg = os.getloadavg()
        uptime_section += f"📊 **Load Average:** {load_avg[0]:.2f}, {load_avg[1]:.2f}, {load_avg[2]:.2f}\n"
    except:
        pass
    
    # Add network info if available
    network_info = system_monitor.get_network_info()
    if network_info:
        uptime_section += f"🌐 **Network:** {network_info}\n"
    
    embed.add_field(name="⏱️ UPTIME & PERFORMANCE", value=uptime_section, inline=False)
    
    # Section 4: BACKGROUND TASKS
    json_task = update_json_with_roles
    monitoring = monitoring_task
    
    tasks_section = (
        f"{'✅' if json_task.is_running() else '❌'} **JSON Sync Task:** {'Running' if json_task.is_running() else 'Stopped'}\n"
        f"{'✅' if monitoring.is_running() else '❌'} **System Monitoring:** {'Running' if monitoring.is_running() else 'Stopped'}\n"
        f"🔄 **Next JSON Sync:** {'N/A' if not json_task.is_running() else '<t:' + str(int(json_task.next_iteration.timestamp())) + ':R>'}\n"
        f"⏰ **Next Hourly Report:** <t:{int(time.time() + 3600 - (time.time() - system_monitor.last_hourly_report))}:R>\n"
        f"📈 **Reports Sent:** {system_monitor.report_count}\n"
    )
    
    embed.add_field(name="🔄 BACKGROUND TASKS", value=tasks_section, inline=False)
    
    # Section 5: PERFORMANCE TRENDS
    if len(system_monitor.performance_history['cpu_temps']) > 0:
        cpu_min = min(system_monitor.performance_history['cpu_temps'])
        cpu_max = max(system_monitor.performance_history['cpu_temps'])
        cpu_avg = sum(system_monitor.performance_history['cpu_temps']) / len(system_monitor.performance_history['cpu_temps'])
        
        trends_section = (
            f"🌡️ **CPU Temperature:**\n"
            f"   ↳ Min: {cpu_min:.1f}°C\n"
            f"   ↳ Max: {cpu_max:.1f}°C\n"
            f"   ↳ Avg: {cpu_avg:.1f}°C\n"
        )
        
        if len(system_monitor.performance_history['memory_usage']) > 0:
            mem_min = min(system_monitor.performance_history['memory_usage'])
            mem_max = max(system_monitor.performance_history['memory_usage'])
            mem_avg = sum(system_monitor.performance_history['memory_usage']) / len(system_monitor.performance_history['memory_usage'])
            
            trends_section += (
                f"\n🧠 **Memory Usage:**\n"
                f"   ↳ Min: {mem_min:.1f}%\n"
                f"   ↳ Max: {mem_max:.1f}%\n"
                f"   ↳ Avg: {mem_avg:.1f}%\n"
            )
        
        embed.add_field(name="📈 PERFORMANCE TRENDS", value=trends_section, inline=False)
    
    # Section 6: ACTIVE ALERTS
    active_alerts = system_monitor.check_active_alerts(cpu_temp, memory_usage, disk_usage, registry_size)
    if active_alerts:
        embed.add_field(
            name="🚨 ACTIVE CRITICAL ALERTS",
            value="\n".join([f"• {alert}" for alert in active_alerts]),
            inline=False
        )
        embed.color = discord.Color.red()
    
    # Section 7: MONITORING CONFIGURATION
    config_section = (
        f"⚙️ **Check Interval:** {system_monitor.check_interval // 60} minutes\n"
        f"⏳ **Alert Cooldown:** {system_monitor.alert_cooldown // 3600} hours\n"
        f"📊 **History Points:** {len(system_monitor.performance_history['cpu_temps'])}/{system_monitor.MAX_HISTORY}\n"
        f"📋 **Log Channel:** {'✅ Configured' if LOG_CHANNEL_ID else '❌ Not configured'}\n"
    )
    
    embed.add_field(name="🔧 MONITORING CONFIG", value=config_section, inline=False)
    
    # Footer
    footer_text = (
        f"System Monitor | "
        f"Hourly reports: {system_monitor.report_count} | "
        f"Next report: <t:{int(time.time() + 3600 - (time.time() - system_monitor.last_hourly_report))}:R>"
    )
    embed.set_footer(text=footer_text)
    
    await ctx.send(embed=embed)

@bot_command.command(name="monitoring_config")
@bot_channel_only()
async def chat_monitoring_config(ctx):
    """Display current monitoring configuration."""
    global system_monitor
    if not system_monitor:
        await ctx.send("❌ System monitor not initialized.", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="⚙️ Monitoring Configuration",
        description="Current system monitoring settings:",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="📊 Check Interval",
        value=f"{system_monitor.check_interval} seconds ({system_monitor.check_interval//60} minutes)",
        inline=True
    )
    
    embed.add_field(
        name="🔥 CPU Temp Critical",
        value=f"{system_monitor.cpu_temp_critical}°C",
        inline=True
    )
    
    embed.add_field(
        name="💾 Memory Critical",
        value=f"{system_monitor.memory_critical}%",
        inline=True
    )
    
    embed.add_field(
        name="📁 Registry Critical",
        value=f"{system_monitor.format_file_size(system_monitor.registry_critical)}",
        inline=True
    )
    
    embed.add_field(
        name="⏳ Alert Cooldown",
        value=f"{system_monitor.alert_cooldown} seconds ({system_monitor.alert_cooldown//3600} hours)",
        inline=True
    )
    
    # Get current metrics
    cpu_temp = await system_monitor.get_cpu_temperature()
    memory_usage = system_monitor.get_memory_usage()
    registry_size = system_monitor.get_registry_file_size()
    
    embed.add_field(
        name="📈 Current Metrics",
        value=f"• CPU Temp: {cpu_temp}°C\n• Memory: {memory_usage}%\n• Registry: {system_monitor.format_file_size(registry_size)}",
        inline=False
    )
    
    embed.set_footer(text="Use !bot_command update_monitoring_config to change settings")
    await ctx.send(embed=embed, ephemeral=True)

@bot_command.command(name="update_monitoring_config")
@bot_channel_only()
async def chat_update_monitoring_config(ctx, setting: str, value: float):
    """
    Update monitoring configuration.
    
    Settings:
    - cpu_temp: CPU temperature critical threshold (°C)
    - memory: Memory usage critical threshold (%)
    - registry: Registry file size critical threshold (MB)
    - interval: Check interval (minutes)
    - cooldown: Alert cooldown (hours)
    """
    global system_monitor
    if not system_monitor:
        await ctx.send("❌ System monitor not initialized.", ephemeral=True)
        return
    
    setting = setting.lower()
    
    try:
        if setting == "cpu_temp":
            old_value = system_monitor.cpu_temp_critical
            system_monitor.cpu_temp_critical = float(value)
            await ctx.send(f"✅ CPU temperature critical threshold updated: {old_value}°C → {value}°C", ephemeral=True)
            
        elif setting == "memory":
            old_value = system_monitor.memory_critical
            system_monitor.memory_critical = float(value)
            await ctx.send(f"✅ Memory usage critical threshold updated: {old_value}% → {value}%", ephemeral=True)
            
        elif setting == "registry":
            old_value = system_monitor.registry_critical / (1024 * 1024)  # Convert back to MB for display
            system_monitor.registry_critical = float(value) * 1024 * 1024  # Convert MB to bytes
            await ctx.send(f"✅ Registry file size critical threshold updated: {old_value}MB → {value}MB", ephemeral=True)
            
        elif setting == "interval":
            old_value = system_monitor.check_interval // 60  # Convert to minutes for display
            system_monitor.check_interval = int(value) * 60  # Convert minutes to seconds
            await ctx.send(f"✅ Check interval updated: {old_value} minutes → {value} minutes", ephemeral=True)
            
        elif setting == "cooldown":
            old_value = system_monitor.alert_cooldown // 3600  # Convert to hours for display
            system_monitor.alert_cooldown = int(value) * 3600  # Convert hours to seconds
            await ctx.send(f"✅ Alert cooldown updated: {old_value} hours → {value} hours", ephemeral=True)
            
        else:
            await ctx.send("❌ Invalid setting. Available: cpu_temp, memory, registry, interval, cooldown", ephemeral=True)
            
    except ValueError:
        await ctx.send("❌ Invalid value. Please provide a number.", ephemeral=True)

@bot_command.command(name="test_alert")
@bot_channel_only()
async def chat_test_alert(ctx):
    """Test the monitoring alert system."""
    global system_monitor
    if not system_monitor:
        await ctx.send("❌ System monitor not initialized.", ephemeral=True)
        return
    
    # Send a test alert
    await system_monitor.send_monitoring_alert("cpu_temp", 85.0, 75.0)
    await ctx.send("✅ Test alert sent to admin. Check your DMs!", ephemeral=True)

@bot_command.command(name="monitoring_status")
@bot_channel_only()
async def chat_monitoring_task_status(ctx):
    """Show the status of the monitoring task."""
    task = monitoring_task
    
    embed = discord.Embed(
        title="📊 Monitoring Task Status",
        color=discord.Color.blue()
    )
    
    if task.is_running():
        embed.description = "✅ **Monitoring task is running**"
        embed.add_field(
            name="Check Interval",
            value=f"Every {system_monitor.check_interval} seconds ({system_monitor.check_interval//60} minutes)",
            inline=True
        )
        embed.add_field(
            name="Last Check",
            value=f"Running continuously",
            inline=True
        )
    else:
        embed.description = "❌ **Monitoring task is not running**"
        embed.add_field(
            name="Status",
            value="Use `!bot_command start_monitoring` to start the task",
            inline=False
        )
    
    # Add cooldown status
    if system_monitor.last_alert_time:
        cooldown_info = []
        for metric, last_time in system_monitor.last_alert_time.items():
            time_since = time.time() - last_time
            if time_since < system_monitor.alert_cooldown:
                remaining = system_monitor.alert_cooldown - time_since
                cooldown_info.append(f"• {metric}: {int(remaining)}s remaining")
        
        if cooldown_info:
            embed.add_field(
                name="⏳ Alert Cooldowns",
                value="\n".join(cooldown_info),
                inline=False
            )
    
    await ctx.send(embed=embed)

@bot_command.command(name="start_monitoring")
@bot_channel_only()
async def chat_start_monitoring(ctx):
    """Manually start the monitoring task."""
    task = monitoring_task
    
    if task.is_running():
        await ctx.send("✅ Monitoring task is already running.", ephemeral=True)
        return
    
    try:
        task.start()
        await ctx.send("✅ Started system monitoring task!")
        
        # Log to log channel
        embed = discord.Embed(
            title="▶️ System Monitoring Started",
            description=f"System monitoring task has been started.\n"
                       f"**By:** {ctx.author.mention}\n"
                       f"**Interval:** Every {system_monitor.check_interval//60} minutes\n"
                       f"**Time:** <t:{int(time.time())}:R>",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        await send_to_log_channel(ctx.guild, "", embed)
        
    except Exception as e:
        await ctx.send(f"❌ Failed to start monitoring: {str(e)}", ephemeral=True)

@bot_command.command(name="stop_monitoring")
@bot_channel_only()
async def chat_stop_monitoring(ctx):
    """Stop the monitoring task."""
    task = monitoring_task
    
    if not task.is_running():
        await ctx.send("❌ Monitoring task is not running.", ephemeral=True)
        return
    
    try:
        task.cancel()
        await ctx.send("✅ Stopped system monitoring task.")
        
        # Log to log channel
        embed = discord.Embed(
            title="⏹️ System Monitoring Stopped",
            description=f"System monitoring task has been stopped.\n"
                       f"**By:** {ctx.author.mention}\n"
                       f"**Time:** <t:{int(time.time())}:R>",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        await send_to_log_channel(ctx.guild, "", embed)
        
    except Exception as e:
        await ctx.send(f"❌ Failed to stop monitoring: {str(e)}", ephemeral=True)

# =============================================================================
# MODIFY ON_READY TO REMOVE STARTUP REPORT
# =============================================================================
@bot.event
async def on_ready():
    """Bot startup initialization and system verification."""
    global system_monitor
    
    print(f'✅ {bot.user} is online!')
    print(f'🆔 Bot ID: {bot.user.id}')
    print(f'👥 Connected to {len(bot.guilds)} server(s)')
    
    # Initialize system monitor (for hourly reports only)
    system_monitor = SystemMonitor(bot)
    print(f'📊 System monitor initialized')
    
    # Store bot start time for uptime calculations
    bot.start_time = time.time()
    
    # Minimal startup logging - NO STARTUP REPORT
    guild = bot.get_guild(GUILD_ID)
    if guild:
        # Just log to console
        print(f"🏠 Server: {guild.name} (ID: {guild.id})")
        
        # Register persistent views
        bot.add_view(RulesRegistrationView())
        bot.add_view(GeneralChatButtonView())
        
        # Re-register delete button views for existing private chats
        await reinitialize_private_chat_views()
        
        # AUTO-SETUP CHANNELS ON STARTUP
        print("\n🔄 Auto-setting up channels on startup...")
        await auto_setup_welcome_channel()  # Setup welcome channel (rules message)
        await auto_setup_command_chat()     # Setup bot command channel
        await auto_setup_general_chat_button()  # Setup general-chat button
        
        # ========================================================
        # START ALL BACKGROUND TASKS ON STARTUP
        # ========================================================
        
        # Start JSON role synchronization task (24-hour intervals)
        if not update_json_with_roles.is_running():
            try:
                update_json_with_roles.start()
                print('✅ 24-hour JSON role synchronization task started')
            except Exception as e:
                print(f'⚠️ Failed to start JSON sync task: {e}')
        
        # Start system monitoring task (5-minute intervals)
        if not monitoring_task.is_running():
            try:
                monitoring_task.start()
                print('✅ System monitoring task started (every 5 minutes)')
                print('   Hourly detailed reports will be sent to log channel')
            except Exception as e:
                print(f'⚠️ Failed to start monitoring task: {e}')
        
        # ========================================================
        # POST-STARTUP CHECKS
        # ========================================================
        
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

        after_school_role = guild.get_role(AFTER_SCHOOL_ROLE_ID)
        if after_school_role:
            print(f'📚 After School Role: {after_school_role.name} (ID: {after_school_role.id})')
        else:
            print(f'⚠️ After School role not found! ID: {AFTER_SCHOOL_ROLE_ID}')

        # Verify After School channel
        after_school_channel = guild.get_channel(AFTER_SCHOOL_CHANNEL_ID)
        if after_school_channel:
            print(f'📢 After School Channel: #{after_school_channel.name} (ID: {after_school_channel.id})')
        else:
            print(f'⚠️ After School channel not found! ID: {AFTER_SCHOOL_CHANNEL_ID}')
        
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
                print(f'   Enhanced hourly reports will be sent here')
            else:
                print(f'⚠️ Log channel not found! ID: {LOG_CHANNEL_ID}')
        else:
            print(f'⚠️ Log channel not configured! Enhanced hourly reports cannot be sent')
        
        # Validate green check mark consistency
        print("\n🔍 Checking registration status...")
        await verify_green_check_consistency(guild, rules_channel)
        
        # AUTO-LOG ADMIN INFO ON SERVER START
        admin_member = guild.get_member(ADMIN_USER_ID)
        if admin_member:
            admin_id_str = str(ADMIN_USER_ID)
            
            # Check if admin already exists in registered_users
            if admin_id_str not in registered_users:
                # Create admin entry
                registered_users[admin_id_str] = {
                    'child_name': 'Admin User',
                    'role': 'Admin',
                    'role_display': '👑 Server Admin',
                    'nickname': admin_member.display_name,
                    'gender': 'admin',
                    'programs': [],
                    'registered_at': discord.utils.utcnow().isoformat(),
                    'has_active_private_chat': False,
                    'private_chat_channel_id': None,
                    'roles': ['Admin'],
                    'admin_user': True,
                    'auto_added': True
                }
                save_registered_users(registered_users)
                print(f"✅ Auto-logged admin user: {admin_member.name}")
            else:
                # Ensure admin has Admin role in the array
                if 'Admin' not in registered_users[admin_id_str].get('roles', []):
                    registered_users[admin_id_str]['roles'] = registered_users[admin_id_str].get('roles', []) + ['Admin']
                    registered_users[admin_id_str]['admin_user'] = True
                    save_registered_users(registered_users)
                    print(f"✅ Updated admin roles for: {admin_member.name}")
    
    migrate_existing_users()
    
    print("\n🚀 Bot startup complete! All systems operational.")
    print("   Enhanced hourly system reports will be sent to log channel")
    print("="*50)

# ============================================================================
# ROLE MANAGEMENT COMMANDS
# =============================================================================
@bot_command.command(name="remove_role")
@bot_channel_only()
async def remove_role(ctx, member: discord.Member, role_type: str):
    """
    Remove special role from a user.
    
    role_type options: 'instructor', 'master_family', 'both'
    """
    guild = ctx.guild
    instructor_role = guild.get_role(INSTRUCTOR_ROLE_ID)
    master_family_role = guild.get_role(MASTER_LEE_FAMILY_ROLE_ID)
    
    role_type = role_type.lower()
    
    try:
        removed_roles = []
        reason = "Role removed by admin"
        
        if role_type == 'instructor' or role_type == 'both':
            if instructor_role and instructor_role in member.roles:
                await member.remove_roles(instructor_role, reason=reason)
                removed_roles.append("Instructor")
        
        if role_type == 'master_family' or role_type == 'both':
            if master_family_role and master_family_role in member.roles:
                await member.remove_roles(master_family_role, reason=reason)
                removed_roles.append("Master Lee's Family")
        
        if not removed_roles:
            await ctx.send(f"❌ {member.mention} doesn't have the specified role(s) to remove.", ephemeral=True)
            return
        
        # Log the removal
        embed = discord.Embed(
            title="🗑️ Special Role(s) Removed",
            description=f"**User:** {member.mention} ({member.id})\n"
                      f"**Removed Roles:** {', '.join(removed_roles)}\n"
                      f"**Removed by:** {ctx.author.mention}\n"
                      f"**Time:** <t:{int(time.time())}:R>",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        await send_to_log_channel(guild, "", embed)
        
        # Send success message
        success_embed = discord.Embed(
            title="✅ Role(s) Removed",
            description=f"Removed **{', '.join(removed_roles)}** role(s) from {member.mention}",
            color=discord.Color.green()
        )
        await ctx.send(embed=success_embed)
        
        print(f"🗑️ Removed {', '.join(removed_roles)} role(s) from {member.name}")
        
    except discord.Forbidden:
        await ctx.send("❌ I don't have permission to remove roles!", ephemeral=True)
    except Exception as e:
        await ctx.send(f"❌ Error removing role: {e}", ephemeral=True)

@bot_command.command(name="cleanup_json")
@bot_channel_only()
async def chat_cleanup_json(ctx):
    """Clean up registered_users.json by removing users no longer in the server."""
    guild = ctx.guild
    original_count = len(registered_users)
    removed_users = []
    
    for user_id_str in list(registered_users.keys()):
        user_id = int(user_id_str)
        member = guild.get_member(user_id)
        
        if not member:
            # User not in server, remove from JSON
            removed_users.append({
                'id': user_id_str,
                'name': registered_users[user_id_str].get('child_name', 'Unknown'),
                'roles': registered_users[user_id_str].get('roles', [])
            })
            del registered_users[user_id_str]
    
    # Save cleaned JSON
    if removed_users:
        save_registered_users(registered_users)
    
    # Create report
    embed = discord.Embed(
        title="🧹 JSON Cleanup Complete",
        description=f"**Original users:** {original_count}\n"
                   f"**Current users:** {len(registered_users)}\n"
                   f"**Removed users:** {len(removed_users)}",
        color=discord.Color.green()
    )
    
    if removed_users:
        removed_list = []
        for user in removed_users[:10]:  # Show first 10
            removed_list.append(f"• ID: {user['id']}, Name: {user['name']}, Roles: {len(user['roles'])}")
        
        embed.add_field(
            name="🗑️ Removed Users",
            value="\n".join(removed_list),
            inline=False
        )
        
        if len(removed_users) > 10:
            embed.add_field(
                name="ℹ️ Note",
                value=f"... and {len(removed_users) - 10} more users",
                inline=False
            )
    else:
        embed.add_field(
            name="✅ No Cleanup Needed",
            value="All registered users are still in the server.",
            inline=False
        )
    
    await ctx.send(embed=embed)
    
    # Log to log channel
    log_embed = discord.Embed(
        title="🧹 JSON Cleanup Executed",
        description=f"**Removed:** {len(removed_users)} orphaned users\n"
                   f"**By:** {ctx.author.mention}",
        color=discord.Color.orange(),
        timestamp=datetime.now(timezone.utc)
    )
    await send_to_log_channel(guild, "", log_embed)

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
# BACKGROUND TASKS
# =============================================================================
@tasks.loop(hours=24)  # Runs every 24 hours
async def update_json_with_roles():
    """
    Background task that updates registered_users.json with current Discord roles.
    Runs every 24 hours to keep JSON synchronized with Discord.
    """
    try:
        guild = bot.get_guild(GUILD_ID)
        if not guild:
            print("⚠️ Cannot update JSON with roles: Guild not found")
            return
        
        print("🔄 Starting 24-hour JSON role update task...")
        updated_count = 0
        errors = []
        
        # Role ID to name mapping for tracking
        role_mapping = {
            FAMILY_ROLE_ID: "Family Member",
            NATIONAL_TEAM_ROLE_ID: "National Team", 
            DEMONSTRATION_TEAM_ROLE_ID: "Demonstration Team",
            AFTER_SCHOOL_ROLE_ID: "After School",
            STUDENT_ROLE_ID: "Student",
            INSTRUCTOR_ROLE_ID: "Instructor",
            MASTER_LEE_FAMILY_ROLE_ID: "Master Lee's Family"
        }
        
        # Filter out 0 IDs (unconfigured roles)
        role_mapping = {k: v for k, v in role_mapping.items() if k != 0}
        
        # Update each registered user
        for user_id_str, user_data in registered_users.items():
            try:
                user_id = int(user_id_str)
                member = guild.get_member(user_id)
                
                if not member:
                    # User not in server, but keep their data
                    continue
                
                # Get current roles from Discord
                current_roles = []
                for role_id, role_name in role_mapping.items():
                    role = guild.get_role(role_id)
                    if role and role in member.roles:
                        current_roles.append(role_name)
                
                # Add Admin role if applicable
                if user_id == ADMIN_USER_ID:
                    if "Admin" not in current_roles:
                        current_roles.append("Admin")
                
                # Check if roles have changed
                stored_roles = user_data.get('roles', [])
                
                # Also update the programs field based on current roles
                # Map role names to program identifiers
                programs = []
                if "National Team" in current_roles:
                    programs.append("national")
                if "Demonstration Team" in current_roles:
                    programs.append("demonstration")
                if "After School" in current_roles:
                    programs.append("after_school")
                
                # Update the programs field
                registered_users[user_id_str]['programs'] = programs
                
                # Sort for comparison
                current_roles_sorted = sorted(current_roles)
                stored_roles_sorted = sorted(stored_roles)
                
                if current_roles_sorted != stored_roles_sorted:
                    # Update the user's roles in JSON
                    registered_users[user_id_str]['roles'] = current_roles
                    updated_count += 1
                    
                    # Log the change
                    print(f"📝 Updated roles for {member.name}: {stored_roles} -> {current_roles}")
                    print(f"📝 Updated programs for {member.name}: {programs}")
                    
            except Exception as e:
                errors.append(f"User {user_id_str}: {str(e)}")
                continue
        
        # Save if updates were made
        if updated_count > 0:
            save_registered_users(registered_users)
            print(f"✅ JSON updated: {updated_count} users' roles and programs synchronized")
            
            # Log to log channel
            embed = discord.Embed(
                title="🔄 JSON Role Synchronization Complete",
                description=f"**Updated:** {updated_count} users\n"
                          f"**Time:** <t:{int(time.time())}:F>\n"
                          f"**Task:** 24-hour automatic sync\n\n"
                          f"**Note:** Programs field now synchronized with roles",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            
            guild = bot.get_guild(GUILD_ID)
            if guild:
                await send_to_log_channel(guild, "", embed)
        
        if errors:
            print(f"⚠️ Errors during JSON update: {len(errors)} errors")
            for error in errors[:5]:  # Show first 5 errors
                print(f"   {error}")
            if len(errors) > 5:
                print(f"   ...and {len(errors) - 5} more")
                
    except Exception as e:
        print(f"❌ Error in JSON update task: {e}")
        import traceback
        traceback.print_exc()

@update_json_with_roles.before_loop
async def before_update_json_task():
    """Wait for bot to be ready before starting the task."""
    await bot.wait_until_ready()
    print("⏰ 24-hour JSON update task is waiting to start...")

# =============================================================================
# CHANNEL PERMISSION CONFIGURATION
# =============================================================================

# Define channel permission mappings in a structured way
CHANNEL_PERMISSIONS_CONFIG = {
    # Category-wide permissions
    "categories": {
        # 🤖 BOT category (admin only)
        "🤖 BOT": {
            "clear_existing": True,
            "permissions": {
                "default": {  # @everyone
                    "view_channel": False,
                    "read_messages": False
                },
                "roles": {
                    "admin_user": {  # Admin user (by member)
                        "view_channel": True,
                        "read_messages": True,
                        "send_messages": True,
                        "manage_channels": True,
                        "manage_permissions": True
                    },
                    "bot": {  # Bot itself
                        "view_channel": True,
                        "read_messages": True,
                        "send_messages": True,
                        "manage_channels": True,
                        "manage_permissions": True
                    },                    
                    "Master Lee's Family": {  # Full access
                        "view_channel": True,  # ← ADD THIS LINE
                        "read_messages": True,
                        "send_messages": True,
                        "manage_messages": True,
                        "read_message_history": True,
                        "embed_links": True,
                        "attach_files": True,
                        "manage_channels": True,  # ← Consider adding this too
                        "manage_permissions": True  # ← Consider adding this too
                    },
                    "Instructor": {  # Special role - NO ACCESS
                        "view_channel": False,
                        "read_messages": False
                    }
                }
            }
        },
        
        # 🔒 PRIVATE CONVERSATIONS category (admin only)
        "🔒 PRIVATE CONVERSATIONS": {
            "clear_existing": True,
            "permissions": {
                "default": {  # @everyone
                    "view_channel": False,
                    "read_messages": False,
                    "send_messages": False
                },
                "roles": {
                    "admin_user": {  # Admin user (by member)
                        "view_channel": True,
                        "read_messages": True,
                        "send_messages": True,
                        "manage_channels": True,
                        "read_message_history": True
                    },
                    "bot": {  # Bot itself
                        "view_channel": True,
                        "read_messages": True,
                        "send_messages": True,
                        "manage_channels": True,
                        "read_message_history": True
                    },
                    "Master Lee's Family": {  # Special role - NO ACCESS
                        "view_channel": True,
                        "read_messages": True,
                        "send_messages": True,
                        "manage_channels": True,
                        "read_message_history": True
                    },
                    "Instructor": {  # Special role - NO ACCESS
                        "view_channel": False,
                        "read_messages": False
                    }
                }
            }
        }
    },
    
    # Individual channel permissions
    "channels": {
        # Schedule channel - visible to everyone with different access levels

        "schedule": {
            "clear_existing": True,
            "permissions": {
                "default": {  # @everyone - can't see by default
                    "read_messages": False,
                    "send_messages": False,
                    "view_channel": False
                },
                "roles": {
                    "Master Lee's Family": {  # Full access
                        "read_messages": True,
                        "send_messages": True,
                        "view_channel": True,
                        "read_message_history": True,
                        "embed_links": True,
                        "attach_files": True
                    },
                    "Family Member": {  # READ ONLY
                        "read_messages": True,
                        "send_messages": False,  # READ ONLY
                        "view_channel": True,
                        "read_message_history": True
                    },
                    "Student": {  # READ ONLY (same as Family Member)
                        "read_messages": True,
                        "send_messages": False,  # READ ONLY
                        "view_channel": True,
                        "read_message_history": True
                    },
                    "Instructor": {  # Full access (same as Master Lee's Family)
                        "read_messages": True,
                        "send_messages": True,
                        "view_channel": True,
                        "read_message_history": True,
                        "embed_links": True,
                        "attach_files": True
                    }
                },
                "members": {
                    "admin_user": {  # Admin user (by member)
                        "read_messages": True,
                        "send_messages": True,
                        "view_channel": True,
                        "read_message_history": True,
                        "manage_channels": True
                    },
                    "bot": {  # Bot itself
                        "read_messages": True,
                        "send_messages": True,
                        "view_channel": True,
                        "read_message_history": True,
                        "manage_channels": True
                    }
                }
            }
        },
        
        # General-chat - visible to everyone but different posting rights
        "general-chat": {
            "clear_existing": True,
            "permissions": {
                "default": {  # @everyone - can't see by default
                    "read_messages": False,
                    "send_messages": False,
                    "view_channel": False
                },
                "roles": {
                    "Master Lee's Family": {  # Can see AND send messages
                        "read_messages": True,
                        "send_messages": True,
                        "view_channel": True,
                        "read_message_history": True,
                        "embed_links": True,
                        "attach_files": True
                    },
                    "Family Member": {  # Can see but CANNOT send messages
                        "read_messages": True,
                        "send_messages": False,  # CANNOT SEND
                        "view_channel": True,
                        "read_message_history": True,
                        "add_reactions": False
                    },
                    "Student": {  # Can see but CANNOT send messages (same as Family Member)
                        "read_messages": True,
                        "send_messages": False,  # CANNOT SEND
                        "view_channel": True,
                        "read_message_history": True,
                        "add_reactions": False
                    },
                    "Instructor": {  # Can see AND send messages
                        "read_messages": True,
                        "send_messages": True,
                        "view_channel": True,
                        "read_message_history": True
                    }
                },
                "members": {
                    "admin_user": {  # Admin user (by member)
                        "read_messages": True,
                        "send_messages": True,
                        "view_channel": True,
                        "read_message_history": True,
                        "manage_messages": True
                    },
                    "bot": {  # Bot itself
                        "read_messages": True,
                        "send_messages": True,
                        "view_channel": True,
                        "read_message_history": True,
                        "manage_messages": True
                    }
                }
            }
        },
        
        # Welcome channel - public read-only
        "welcome": {
            "clear_existing": True,
            "permissions": {
                "default": {  # @everyone - public read-only
                    "read_messages": True,
                    "send_messages": False,  # READ ONLY
                    "read_message_history": True
                }
            }
        },
        
        # Announcement channels - role-specific access
        "announcements": {
            "channel_pattern": "announcements",  # Matches any channel with "announcements" in name
            "clear_existing": True,
            "permissions": {
                "default": {  # @everyone - can't see by default
                    "read_messages": False,
                    "send_messages": False
                },
                "roles": {
                    "Master Lee's Family": {  # Full access to all announcements
                        "read_messages": True,
                        "send_messages": True,
                        "manage_messages": True,
                        "read_message_history": True,
                        "embed_links": True,
                        "attach_files": True
                    },
                    "Instructor": {  # Full access to all announcements
                        "read_messages": True,
                        "send_messages": True,
                        "manage_messages": True,
                        "read_message_history": True
                    },
                    "Family Member": {  # Can see but CANNOT send messages
                        "read_messages": True,
                        "send_messages": False,  # CANNOT SEND
                        "view_channel": True,
                        "read_message_history": True,
                        "add_reactions": False
                    },
                },
                "members": {
                    "admin_user": {  # Admin user (by member)
                        "read_messages": True,
                        "send_messages": True,
                        "manage_messages": True,
                        "read_message_history": True
                    },
                    "bot": {  # Bot itself
                        "read_messages": True,
                        "send_messages": True,
                        "manage_messages": True,
                        "read_message_history": True
                    }
                }
            }
        },
        
        # National Team announcement channel - specific role access
        "national-team-announcements": {
            "clear_existing": True,
            "permissions": {
                "default": {  # @everyone - can't see by default
                    "read_messages": False,
                    "send_messages": False
                },
                "roles": {
                    "Master Lee's Family": {  # Full access
                        "read_messages": True,
                        "send_messages": True,
                        "manage_messages": True,
                        "read_message_history": True,
                        "embed_links": True,
                        "attach_files": True
                    },
                    "Instructor": {  # Full access
                        "read_messages": True,
                        "send_messages": True,
                        "manage_messages": True,
                        "read_message_history": True
                    },
                    "National Team": {  # READ ONLY for team members
                        "read_messages": True,
                        "send_messages": False,  # READ ONLY
                        "read_message_history": True
                    }
                },
                "members": {
                    "admin_user": {  # Admin user (by member)
                        "read_messages": True,
                        "send_messages": True,
                        "manage_messages": True,
                        "read_message_history": True
                    },
                    "bot": {  # Bot itself
                        "read_messages": True,
                        "send_messages": True,
                        "manage_messages": True,
                        "read_message_history": True
                    }
                }
            }
        },
        
        # Demonstration Team announcement channel - specific role access
        "demonstration-team-announcements": {
            "clear_existing": True,
            "permissions": {
                "default": {  # @everyone - can't see by default
                    "read_messages": False,
                    "send_messages": False
                },
                "roles": {
                    "Master Lee's Family": {  # Full access
                        "read_messages": True,
                        "send_messages": True,
                        "manage_messages": True,
                        "read_message_history": True,
                        "embed_links": True,
                        "attach_files": True
                    },
                    "Instructor": {  # Full access
                        "read_messages": True,
                        "send_messages": True,
                        "manage_messages": True,
                        "read_message_history": True
                    },
                    "Demonstration Team": {  # READ ONLY for team members
                        "read_messages": True,
                        "send_messages": False,  # READ ONLY
                        "read_message_history": True
                    }
                },
                "members": {
                    "admin_user": {  # Admin user (by member)
                        "read_messages": True,
                        "send_messages": True,
                        "manage_messages": True,
                        "read_message_history": True
                    },
                    "bot": {  # Bot itself
                        "read_messages": True,
                        "send_messages": True,
                        "manage_messages": True,
                        "read_message_history": True
                    }
                }
            }
        },
        
        # After School announcement channel - specific role access
        "after-school-announcements": {
            "clear_existing": True,
            "permissions": {
                "default": {  # @everyone - can't see by default
                    "read_messages": False,
                    "send_messages": False
                },
                "roles": {
                    "Master Lee's Family": {  # Full access
                        "read_messages": True,
                        "send_messages": True,
                        "manage_messages": True,
                        "read_message_history": True,
                        "embed_links": True,
                        "attach_files": True
                    },
                    "Instructor": {  # Full access
                        "read_messages": True,
                        "send_messages": True,
                        "manage_messages": True,
                        "read_message_history": True
                    },
                    "After School": {  # READ ONLY for team members
                        "read_messages": True,
                        "send_messages": False,  # READ ONLY
                        "read_message_history": True
                    }
                },
                "members": {
                    "admin_user": {  # Admin user (by member)
                        "read_messages": True,
                        "send_messages": True,
                        "manage_messages": True,
                        "read_message_history": True
                    },
                    "bot": {  # Bot itself
                        "read_messages": True,
                        "send_messages": True,
                        "manage_messages": True,
                        "read_message_history": True
                    }
                }
            }
        },
        # 🔧 BOT CATEGORY CHANNELS
        "bot-commands": {
            "clear_existing": True,
            "permissions": {
                "default": {  # @everyone - can't see by default
                    "view_channel": False,
                    "read_messages": False,
                    "send_messages": False
                },
                "roles": {
                    "Master Lee's Family": {  # Full access to bot commands
                        "view_channel": True,
                        "read_messages": True,
                        "send_messages": True,
                        "read_message_history": True,
                        "embed_links": True,
                        "attach_files": True,
                        "manage_messages": False,  # Keep this False unless you want them to delete messages
                        "manage_channels": False  # Keep this False
                    },
                    "Instructor": {  # NO ACCESS to bot commands
                        "view_channel": False,
                        "read_messages": False,
                        "send_messages": False
                    }
                },
                "members": {
                    "admin_user": {  # Admin user (by member)
                        "view_channel": True,
                        "read_messages": True,
                        "send_messages": True,
                        "manage_channels": True,
                        "manage_permissions": True,
                        "manage_messages": True,
                        "read_message_history": True
                    },
                    "bot": {  # Bot itself
                        "view_channel": True,
                        "read_messages": True,
                        "send_messages": True,
                        "manage_channels": True,
                        "manage_permissions": True,
                        "manage_messages": True,
                        "read_message_history": True
                    }
                }
            }
        },
        
        "bot-logs": {
            "clear_existing": True,
            "permissions": {
                "default": {  # @everyone - can't see by default
                    "view_channel": False,
                    "read_messages": False,
                    "send_messages": False
                },
                "roles": {
                    "Master Lee's Family": {  # Read-only access to logs
                        "view_channel": True,
                        "read_messages": True,
                        "send_messages": False,  # Cannot send in logs
                        "read_message_history": True
                    },
                    "Instructor": {  # NO ACCESS to logs
                        "view_channel": False,
                        "read_messages": False,
                        "send_messages": False
                    }
                },
                "members": {
                    "admin_user": {  # Admin user (by member)
                        "view_channel": True,
                        "read_messages": True,
                        "send_messages": False,  # Admin shouldn't need to send here
                        "manage_channels": True,
                        "manage_permissions": True,
                        "read_message_history": True
                    },
                    "bot": {  # Bot itself
                        "view_channel": True,
                        "read_messages": True,
                        "send_messages": True,
                        "manage_channels": True,
                        "manage_permissions": True,
                        "read_message_history": True
                    }
                }
            }
        }
    }
}

# Role name to ID mapping for easier reference
ROLE_IDS = {
    "Master Lee's Family": MASTER_LEE_FAMILY_ROLE_ID,
    "Family Member": FAMILY_ROLE_ID,
    "Student": STUDENT_ROLE_ID,
    "Instructor": INSTRUCTOR_ROLE_ID,
    "National Team": NATIONAL_TEAM_ROLE_ID,
    "Demonstration Team": DEMONSTRATION_TEAM_ROLE_ID,
    "After School": AFTER_SCHOOL_ROLE_ID
}

# =============================================================================
# PERMISSION HELPER FUNCTIONS
# =============================================================================

async def clear_channel_permissions(channel):
    """Clear all existing permissions from a channel."""
    try:
        # Clear @everyone permissions
        await channel.set_permissions(channel.guild.default_role, overwrite=None)
        
        # Clear all other role and member permissions
        for target, _ in channel.overwrites.items():
            await channel.set_permissions(target, overwrite=None)
        
        return True
    except Exception as e:
        print(f"❌ Error clearing permissions for #{channel.name}: {e}")
        return False

async def apply_permission_overwrite(channel, target, permissions):
    """Apply permission overwrite to a channel for a specific target."""
    try:
        # Get existing overwrite or create a new one
        existing_overwrite = channel.overwrites_for(target)
        if existing_overwrite:
            overwrite = existing_overwrite
        else:
            overwrite = discord.PermissionOverwrite()
        
        # Set each permission from our configuration
        for perm_name, perm_value in permissions.items():
            if hasattr(overwrite, perm_name):
                setattr(overwrite, perm_name, perm_value)
            else:
                print(f"⚠️ Unknown permission: {perm_name}")
        
        # Apply the overwrite
        await channel.set_permissions(target, overwrite=overwrite)
        return True
    except Exception as e:
        print(f"❌ Error applying permissions for {target} in #{channel.name}: {e}")
        return False

async def get_role_by_name(guild, role_name):
    """Get a role by its display name from configuration."""
    if role_name == "admin_user":
        return guild.get_member(ADMIN_USER_ID)
    elif role_name == "bot":
        return guild.me
    elif role_name in ROLE_IDS:
        role_id = ROLE_IDS[role_name]
        return guild.get_role(role_id)
    else:
        # Try to find role by name
        return discord.utils.get(guild.roles, name=role_name)

async def apply_channel_permissions(guild, channel, config):
    """Apply permissions to a specific channel based on configuration."""
    try:
        channel_name = channel.name
        print(f"🔧 Applying permissions to #{channel_name}...")
        
        # Clear existing permissions if configured
        if config.get("clear_existing", True):
            # For channels in categories, just sync with category
            if channel.category:
                await channel.edit(sync_permissions=True)
                print(f"  ↳ Synced #{channel_name} with category #{channel.category.name}")
            else:
                # Clear all permissions for channels not in categories
                for target, _ in channel.overwrites.items():
                    await channel.set_permissions(target, overwrite=None)
        
        # If channel is in a category, we should apply category permissions
        # But for now, let's just apply the specific channel permissions
        permissions_config = config.get("permissions", {})
        applied_count = 0
        
        # Apply default permissions (@everyone)
        if "default" in permissions_config:
            await apply_permission_overwrite(
                channel, 
                guild.default_role, 
                permissions_config["default"]
            )
            applied_count += 1
        
        # Apply role permissions
        if "roles" in permissions_config:
            for role_name, role_perms in permissions_config["roles"].items():
                role = await get_role_by_name(guild, role_name)
                if role:
                    await apply_permission_overwrite(channel, role, role_perms)
                    applied_count += 1
                else:
                    print(f"⚠️ Role not found: {role_name}")
        
        # Apply member permissions
        if "members" in permissions_config:
            for member_name, member_perms in permissions_config["members"].items():
                member = await get_role_by_name(guild, member_name)
                if member:
                    await apply_permission_overwrite(channel, member, member_perms)
                    applied_count += 1
                else:
                    print(f"⚠️ Member not found: {member_name}")
        
        print(f"✅ Applied {applied_count} permission sets to #{channel_name}")
        return True
        
    except Exception as e:
        print(f"❌ Error applying permissions to #{channel.name}: {e}")
        return False

# =============================================================================
# RESTRUCTURED APPLY ROLE PERMISSIONS COMMAND
# =============================================================================

@bot_command.command(name="apply_role_permissions")
@bot_channel_only()
async def chat_apply_role_permissions(ctx, specific_channel: str = None):
    """
    Apply role permissions to all existing channels and categories based on configuration.
    
    Usage:
    !bot_command apply_role_permissions - Apply to all channels
    !bot_command apply_role_permissions schedule - Apply to specific channel
    
    This command uses the CHANNEL_PERMISSIONS_CONFIG to determine permissions.
    """
    if ctx.author.id != ADMIN_USER_ID:
        await ctx.send("❌ Only the configured admin can run this command.")
        return
    
    guild = ctx.guild
    
    # Confirmation
    if not specific_channel:
        embed = discord.Embed(
            title="🛠️ Apply Role Permissions",
            description="**This will apply role permissions to ALL channels based on configuration.**\n\n"
                      "**What it does:**\n"
                      "• Clears all existing permissions first\n"
                      "• Applies permissions from CHANNEL_PERMISSIONS_CONFIG\n"
                      "• Updates ALL channels and categories in the server\n\n"
                      "**Configuration includes:**\n"
                      "• Channel-specific permissions\n"
                      "• Role-based access control\n"
                      "• Special handling for Master Lee's Family role\n\n"
                      "Type `APPLY PERMISSIONS` to proceed.",
            color=discord.Color.orange()
        )
        
        await ctx.send(embed=embed)
        
        def check(msg):
            return msg.author == ctx.author and msg.channel == ctx.channel and msg.content == "APPLY PERMISSIONS"
        
        try:
            await bot.wait_for('message', timeout=30.0, check=check)
        except:
            await ctx.send("❌ Permission application cancelled (timeout).")
            return
    
    await ctx.send("🔄 Applying role permissions... This may take a moment.")
    
    try:
        # Track results
        results = {
            "categories": {"total": 0, "success": 0, "failed": 0},
            "channels": {"total": 0, "success": 0, "failed": 0}
        }
        
        # ========== APPLY CATEGORY PERMISSIONS ==========
        print("\n" + "="*50)
        print("🔄 Applying category permissions...")
        print("="*50)
        
        category_config = CHANNEL_PERMISSIONS_CONFIG.get("categories", {})
        
        for category in guild.categories:
            category_name = category.name
            
            # Skip if specific channel requested and this isn't it
            if specific_channel and category_name.lower() != specific_channel.lower():
                continue
            
            if category_name in category_config:
                results["categories"]["total"] += 1
                print(f"\n📁 Processing category: {category_name}")
                
                success = await apply_channel_permissions(guild, category, category_config[category_name])
                
                if success:
                    results["categories"]["success"] += 1
                    print(f"✅ Successfully applied permissions to category: {category_name}")
                else:
                    results["categories"]["failed"] += 1
                    print(f"❌ Failed to apply permissions to category: {category_name}")
        
        # ========== APPLY CHANNEL PERMISSIONS ==========
        print("\n" + "="*50)
        print("🔄 Applying channel permissions...")
        print("="*50)
        
        channel_config = CHANNEL_PERMISSIONS_CONFIG.get("channels", {})
        
        for channel in guild.channels:
            # Skip categories (already processed) and voice channels
            if isinstance(channel, discord.CategoryChannel):
                continue
            
            channel_name = channel.name.lower()
            
            # Skip if specific channel requested and this isn't it
            if specific_channel and channel_name != specific_channel.lower():
                continue
            
            results["channels"]["total"] += 1
            
            # Find matching configuration for this channel
            channel_config_to_apply = None
            
            # First, check for exact match
            if channel.name in channel_config:
                channel_config_to_apply = channel_config[channel.name]
            
            # If no exact match, check for pattern match
            if not channel_config_to_apply:
                for config_name, config_data in channel_config.items():
                    pattern = config_data.get("channel_pattern")
                    if pattern and pattern.lower() in channel_name:
                        channel_config_to_apply = config_data
                        break
            
            if channel_config_to_apply:
                print(f"\n📝 Processing channel: #{channel.name}")
                
                success = await apply_channel_permissions(guild, channel, channel_config_to_apply)
                
                if success:
                    results["channels"]["success"] += 1
                    print(f"✅ Successfully applied permissions to #{channel.name}")
                else:
                    results["channels"]["failed"] += 1
                    print(f"❌ Failed to apply permissions to #{channel.name}")
            else:
                # No configuration for this channel, skip it
                results["channels"]["total"] -= 1
                print(f"⏭️ Skipping #{channel.name} (no configuration found)")
        
        # ========== FINAL SUMMARY ==========
        print("\n" + "="*50)
        print("✅ ROLE PERMISSIONS APPLIED!")
        print("="*50)
        
        # Create summary embed
        total_success = results["categories"]["success"] + results["channels"]["success"]
        total_failed = results["categories"]["failed"] + results["channels"]["failed"]
        total_processed = results["categories"]["total"] + results["channels"]["total"]
        
        embed = discord.Embed(
            title="✅ Role Permissions Applied!",
            description="Permissions have been applied to all channels based on configuration.\n\n"
                      f"**Total Processed:** {total_processed}\n"
                      f"**Successfully Applied:** {total_success}\n"
                      f"**Failed:** {total_failed}\n\n"
                      "All channels now have proper role-based permissions.",
            color=discord.Color.green()
        )
        
        # Add category results
        embed.add_field(
            name="📁 Categories",
            value=f"Total: {results['categories']['total']}\n"
                  f"Success: {results['categories']['success']}\n"
                  f"Failed: {results['categories']['failed']}",
            inline=True
        )
        
        # Add channel results
        embed.add_field(
            name="📝 Channels",
            value=f"Total: {results['channels']['total']}\n"
                  f"Success: {results['channels']['success']}\n"
                  f"Failed: {results['channels']['failed']}",
            inline=True
        )
        
        # Add permission structure summary
        embed.add_field(
            name="🔐 Permission Structure Applied",
            value="**BOT Category:** Admin-only\n"
                  "**PRIVATE CONVERSATIONS:** Admin-only\n"
                  "**Schedule:** Read-only for Family/Students, full for Admin/Master/Instructors\n"
                  "**General-chat:** View-only for Family/Students, full for Admin/Master/Instructors\n"
                  "**Welcome:** Public read-only\n"
                  "**Announcements:** Role-based read-only access",
            inline=False
        )
        
        # Add special note about Master Lee's Family role
        embed.add_field(
            name="👑 Special Handling",
            value="• **Master Lee's Family role** has full access to most channels\n"
                  "• **Instructor role** has similar permissions to Master Lee's Family\n"
                  "• **Family Member/Student roles** have view-only access\n"
                  "• **Team roles** only see their specific announcement channels",
            inline=False
        )
        
        await ctx.send(embed=embed)
        
        # Send to log channel if it exists
        log_channel = guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            log_embed = discord.Embed(
                title="🛠️ Role Permissions Applied",
                description="Role permissions have been applied to all channels based on configuration.",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            log_embed.add_field(name="Applied By", value=ctx.author.mention, inline=True)
            log_embed.add_field(name="Categories Processed", value=str(results["categories"]["total"]), inline=True)
            log_embed.add_field(name="Channels Processed", value=str(results["channels"]["total"]), inline=True)
            log_embed.add_field(name="Total Success", value=str(total_success), inline=True)
            log_embed.add_field(name="Total Failed", value=str(total_failed), inline=True)
            log_embed.set_footer(text="All channels updated with proper permissions")
            await log_channel.send(embed=log_embed)
        
        print(f"\n📊 SUMMARY:")
        print(f"  Categories: {results['categories']['success']}/{results['categories']['total']} successful")
        print(f"  Channels: {results['channels']['success']}/{results['channels']['total']} successful")
        print(f"  Total: {total_success}/{total_processed} successful")
        print("="*50)
        
    except Exception as e:
        error_embed = discord.Embed(
            title="❌ Error Applying Permissions",
            description=f"Unexpected error: {str(e)}",
            color=discord.Color.red()
        )
        await ctx.send(embed=error_embed)
        print(f"❌ Apply permissions error: {e}")
        import traceback
        traceback.print_exc()

# =============================================================================
# QUICK PERMISSION CHECK COMMAND
# =============================================================================

@bot_command.command(name="check_channel_permissions")
@bot_channel_only()
async def chat_check_channel_permissions(ctx, channel_name: str = None):
    """
    Check current permissions for a specific channel or all channels.
    
    Usage:
    !bot_command check_channel_permissions - Check all channels
    !bot_command check_channel_permissions general-chat - Check specific channel
    """
    guild = ctx.guild
    
    if channel_name:
        # Check specific channel
        channel = discord.utils.get(guild.channels, name=channel_name)
        if not channel:
            await ctx.send(f"❌ Channel '{channel_name}' not found.", ephemeral=True)
            return
        
        await display_channel_permissions(ctx, channel)
    else:
        # Check all channels
        await ctx.send("🔄 Checking permissions for all channels... This may take a moment.")
        
        channels_with_permissions = []
        for channel in guild.channels:
            if channel.overwrites:
                channels_with_permissions.append(channel)
        
        if not channels_with_permissions:
            await ctx.send("ℹ️ No channels have custom permissions set.")
            return
        
        # Create paginated view
        class PermissionsListView(discord.ui.View):
            def __init__(self, channels):
                super().__init__(timeout=60)
                self.channels = channels
                self.current_page = 0
                self.pages = self.create_pages()
            
            def create_pages(self):
                """Create paginated list of channels."""
                pages = []
                items_per_page = 10
                
                for i in range(0, len(self.channels), items_per_page):
                    page_channels = self.channels[i:i + items_per_page]
                    page_text = []
                    
                    for channel in page_channels:
                        overwrite_count = len(channel.overwrites)
                        page_text.append(f"• **#{channel.name}** ({channel.type.name}) - {overwrite_count} permission sets")
                    
                    pages.append("\n".join(page_text))
                
                return pages
            
            @discord.ui.button(label="⬅️ Previous", style=discord.ButtonStyle.secondary)
            async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != ctx.author.id:
                    await interaction.response.send_message("❌ This is not for you.", ephemeral=True)
                    return
                
                self.current_page = (self.current_page - 1) % len(self.pages)
                await self.update_message(interaction)
            
            @discord.ui.button(label="➡️ Next", style=discord.ButtonStyle.secondary)
            async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != ctx.author.id:
                    await interaction.response.send_message("❌ This is not for you.", ephemeral=True)
                    return
                
                self.current_page = (self.current_page + 1) % len(self.pages)
                await self.update_message(interaction)
            
            async def update_message(self, interaction):
                embed = discord.Embed(
                    title="📋 Channels with Custom Permissions",
                    description=f"**Page {self.current_page + 1}/{len(self.pages)}**\n\n{self.pages[self.current_page]}",
                    color=discord.Color.blue()
                )
                embed.set_footer(text=f"Total: {len(self.channels)} channels with custom permissions")
                await interaction.response.edit_message(embed=embed, view=self)
        
        view = PermissionsListView(channels_with_permissions)
        embed = discord.Embed(
            title="📋 Channels with Custom Permissions",
            description=f"**Page 1/{len(view.pages)}**\n\n{view.pages[0]}",
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Total: {len(channels_with_permissions)} channels with custom permissions")
        
        await ctx.send(embed=embed, view=view)

async def display_channel_permissions(ctx, channel):
    """Display detailed permissions for a specific channel."""
    embed = discord.Embed(
        title=f"🔐 Permissions for #{channel.name}",
        description=f"**Type:** {channel.type.name}\n"
                   f"**Category:** {channel.category.name if channel.category else 'None'}\n"
                   f"**Permission Overwrites:** {len(channel.overwrites)}",
        color=discord.Color.blue()
    )
    
    if not channel.overwrites:
        embed.add_field(name="ℹ️ No Custom Permissions", value="This channel uses default permissions.", inline=False)
    else:
        for target, overwrite in channel.overwrites.items():
            target_name = target.name if hasattr(target, 'name') else str(target)
            target_type = "Role" if isinstance(target, discord.Role) else "Member"
            
            # Format permissions
            allowed = []
            denied = []
            
            for perm, value in overwrite:
                if value is True:
                    allowed.append(f"`{perm}`")
                elif value is False:
                    denied.append(f"`{perm}`")
            
            perm_text = ""
            if allowed:
                perm_text += f"✅ **Allowed:** {', '.join(allowed[:5])}\n"
                if len(allowed) > 5:
                    perm_text += f"  ...and {len(allowed) - 5} more\n"
            
            if denied:
                perm_text += f"❌ **Denied:** {', '.join(denied[:5])}\n"
                if len(denied) > 5:
                    perm_text += f"  ...and {len(denied) - 5} more"
            
            if not perm_text:
                perm_text = "No specific permissions set"
            
            embed.add_field(
                name=f"{target_type}: {target_name}",
                value=perm_text,
                inline=False
            )
    
    await ctx.send(embed=embed, ephemeral=True)

# =============================================================================
# MANUAL UPDATE COMMAND
# =============================================================================

@bot_command.command(name="update_json_roles")
@bot_channel_only()
async def chat_update_json_roles(ctx):
    """
    Manually trigger JSON role update immediately.
    
    Use this command to force an update without waiting for the 24-hour task.
    """
    await ctx.send("🔄 Starting manual JSON role update...")
    
    try:
        # Get current counts before update
        before_count = len(registered_users)
        
        # Run the update function
        await update_json_with_roles()
        
        # Get updated counts
        after_count = len(registered_users)
        
        # Send completion message
        embed = discord.Embed(
            title="✅ Manual JSON Update Complete",
            description=f"**Users in JSON:** {after_count}\n"
                       f"**Previous count:** {before_count}\n\n"
                       f"JSON file has been synchronized with current Discord roles.",
            color=discord.Color.green()
        )
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        error_embed = discord.Embed(
            title="❌ Manual Update Failed",
            description=f"Error: {str(e)}",
            color=discord.Color.red()
        )
        await ctx.send(embed=error_embed)

@bot_command.command(name="force_json_sync")
@bot_channel_only()
async def chat_force_json_sync(ctx, member: discord.Member = None):
    """
    Force sync JSON roles for a specific user or all users.
    
    Usage:
    !bot_command force_json_sync @user  # Sync specific user
    !bot_command force_json_sync        # Sync all users
    """
    guild = ctx.guild
    
    if member:
        # Sync specific user
        user_id_str = str(member.id)
        
        if user_id_str not in registered_users:
            await ctx.send(f"❌ {member.mention} is not in the JSON registry!", ephemeral=True)
            return
        
        # Get current Discord roles
        current_roles = []
        role_mapping = {
            FAMILY_ROLE_ID: "Family Member",
            NATIONAL_TEAM_ROLE_ID: "National Team",
            DEMONSTRATION_TEAM_ROLE_ID: "Demonstration Team",
            AFTER_SCHOOL_ROLE_ID: "After School",
            STUDENT_ROLE_ID: "Student",
            INSTRUCTOR_ROLE_ID: "Instructor",
            MASTER_LEE_FAMILY_ROLE_ID: "Master Lee's Family"
        }
        
        for role_id, role_name in role_mapping.items():
            if role_id != 0:  # Skip unconfigured roles
                role = guild.get_role(role_id)
                if role and role in member.roles:
                    current_roles.append(role_name)
        
        # Add Admin role if applicable
        if member.id == ADMIN_USER_ID:
            if "Admin" not in current_roles:
                current_roles.append("Admin")
        
        # Update programs based on roles
        programs = []
        if "National Team" in current_roles:
            programs.append("national")
        if "Demonstration Team" in current_roles:
            programs.append("demonstration")
        if "After School" in current_roles:
            programs.append("after_school")
        
        # Update JSON
        registered_users[user_id_str]['roles'] = current_roles
        registered_users[user_id_str]['programs'] = programs
        save_registered_users(registered_users)
        
        # Send confirmation
        embed = discord.Embed(
            title="✅ User JSON Synced",
            description=f"Updated JSON roles and programs for {member.mention}",
            color=discord.Color.green()
        )
        embed.add_field(
            name="Current Roles in JSON",
            value="\n".join([f"• {role}" for role in current_roles]) if current_roles else "No roles",
            inline=False
        )
        embed.add_field(
            name="Updated Programs in JSON",
            value=", ".join(programs) if programs else "No programs",
            inline=False
        )
        
        await ctx.send(embed=embed)
        
    else:
        # Sync all users
        await ctx.send("🔄 Force syncing JSON roles and programs for ALL users...")
        
        # Run the update function
        await update_json_with_roles()
        
        await ctx.send("✅ Force sync complete! Programs field now synchronized with roles.")

@bot_command.command(name="json_task_status")
@bot_channel_only()
async def chat_json_task_status(ctx):
    """Show the status of the 24-hour JSON update task."""
    task = update_json_with_roles
    
    embed = discord.Embed(
        title="⏰ JSON Update Task Status",
        color=discord.Color.blue()
    )
    
    if task.is_running():
        # Calculate next run time
        current_time = discord.utils.utcnow()
        hours_since_start = (current_time - task.next_iteration).total_seconds() / 3600
        
        embed.description = "✅ **Task is running**"
        embed.add_field(
            name="Next Run",
            value=f"Approximately every 24 hours\nLast started: {hours_since_start:.1f} hours ago",
            inline=False
        )
    else:
        embed.description = "❌ **Task is not running**"
        embed.add_field(
            name="Status",
            value="The background task is not running. Use `!bot_command start_json_task` to start it.",
            inline=False
        )
    
    embed.add_field(
        name="Total Users in JSON",
        value=f"{len(registered_users)} users",
        inline=True
    )
    
    await ctx.send(embed=embed)

@bot_command.command(name="start_json_task")
@bot_channel_only()
async def chat_start_json_task(ctx):
    """Manually start the 24-hour JSON update task."""
    task = update_json_with_roles
    
    if task.is_running():
        await ctx.send("✅ JSON update task is already running.", ephemeral=True)
        return
    
    try:
        task.start()
        await ctx.send("✅ Started 24-hour JSON update task!")
        
        # Log to log channel
        embed = discord.Embed(
            title="▶️ JSON Update Task Started",
            description=f"24-hour JSON role synchronization task has been started.\n"
                       f"**By:** {ctx.author.mention}\n"
                       f"**Time:** <t:{int(time.time())}:R>",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        await send_to_log_channel(ctx.guild, "", embed)
        
    except Exception as e:
        await ctx.send(f"❌ Failed to start task: {str(e)}", ephemeral=True)

@bot_command.command(name="stop_json_task")
@bot_channel_only()
async def chat_stop_json_task(ctx):
    """Stop the 24-hour JSON update task."""
    task = update_json_with_roles
    
    if not task.is_running():
        await ctx.send("❌ JSON update task is not running.", ephemeral=True)
        return
    
    try:
        task.cancel()
        await ctx.send("✅ Stopped 24-hour JSON update task.")
        
        # Log to log channel
        embed = discord.Embed(
            title="⏹️ JSON Update Task Stopped",
            description=f"24-hour JSON role synchronization task has been stopped.\n"
                       f"**By:** {ctx.author.mention}\n"
                       f"**Time:** <t:{int(time.time())}:R>",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        await send_to_log_channel(ctx.guild, "", embed)
        
    except Exception as e:
        await ctx.send(f"❌ Failed to stop task: {str(e)}", ephemeral=True)

@bot_command.command(name="migrate_json_structure")
@bot_channel_only()
async def chat_migrate_json_structure(ctx):
    """
    Migrate existing JSON file to new structure and create backup.
    
    This command will:
    1. Create a timestamped backup of the current JSON file
    2. Migrate all existing users to the new structure
    3. Preserve special roles (Instructor, Master Lee's Family, etc.)
    4. Transform 'teams' field to 'programs' field
    5. Ensure all required fields exist
    """
    await ctx.send("🔄 **Starting JSON Migration Process**")
    
    try:
        # Step 1: Create backup of current file
        backup_filename = f"registered_users_backup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        
        # Read current data
        with open(REGISTRY_FILE, 'r') as f:
            current_data = json.load(f)
        
        # Create backup
        with open(backup_filename, 'w') as f:
            json.dump(current_data, f, indent=2)
        
        embed_step1 = discord.Embed(
            title="✅ Step 1: Backup Created",
            description=f"Created backup file: `{backup_filename}`\n\n"
                      f"**Original users:** {len(current_data)}\n"
                      f"**Backup size:** {os.path.getsize(backup_filename)} bytes",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed_step1)
        
        # Step 2: Perform migration
        migrated_count = 0
        errors = []
        new_data = {}
        
        for user_id_str, user_data in current_data.items():
            try:
                # Create new structure with default values
                migrated_user = {
                    'child_name': user_data.get('child_name', 'Unknown'),
                    'role': user_data.get('role', 'Unknown'),
                    'role_display': user_data.get('role_display', user_data.get('role', 'Unknown')),
                    'nickname': user_data.get('nickname', user_data.get('child_name', 'Unknown')),
                    'gender': user_data.get('gender', 'unknown'),
                    'registered_at': user_data.get('registered_at', discord.utils.utcnow().isoformat()),
                    'has_active_private_chat': user_data.get('has_active_private_chat', False),
                    'private_chat_channel_id': user_data.get('private_chat_channel_id', None),
                    'roles': [],  # Will be populated from Discord roles
                    'programs': []  # New field
                }
                
                # Handle teams/programs migration
                if 'teams' in user_data:
                    # Migrate teams to programs
                    teams = user_data['teams']
                    programs = []
                    if isinstance(teams, list):
                        for team in teams:
                            if team == "national":
                                programs.append("national")
                            elif team == "demonstration":
                                programs.append("demonstration")
                            elif team == "after_school":
                                programs.append("after_school")
                    migrated_user['programs'] = programs
                    print(f"🔁 Migrated teams to programs for {user_id_str}: {teams} -> {programs}")
                
                # Preserve programs if already exists
                if 'programs' in user_data:
                    migrated_user['programs'] = user_data['programs']
                
                # Preserve roles if they exist (special roles)
                if 'roles' in user_data:
                    migrated_user['roles'] = user_data['roles']
                
                # Preserve auto_added flag
                if 'auto_added' in user_data:
                    migrated_user['auto_added'] = user_data['auto_added']
                
                # Preserve admin flag
                if 'admin_user' in user_data:
                    migrated_user['admin_user'] = user_data['admin_user']
                
                # Preserve master_lee_family flag
                if 'master_lee_family' in user_data:
                    migrated_user['master_lee_family'] = user_data['master_lee_family']
                
                # Preserve instructor flag
                if 'instructor' in user_data:
                    migrated_user['instructor'] = user_data['instructor']
                
                # Add to new data
                new_data[user_id_str] = migrated_user
                migrated_count += 1
                
            except Exception as e:
                errors.append(f"User {user_id_str}: {str(e)}")
                # Keep original data as fallback
                new_data[user_id_str] = user_data
        
        # Step 3: Save migrated data
        with open(REGISTRY_FILE, 'w') as f:
            json.dump(new_data, f, indent=2)
        
        # Step 4: Load the migrated data into memory
        global registered_users
        registered_users = new_data
        
        # Step 5: Create summary
        embed_summary = discord.Embed(
            title="✅ JSON Migration Complete",
            description=f"**Successfully migrated:** {migrated_count} users\n"
                      f"**Errors encountered:** {len(errors)}\n"
                      f"**New file structure:** ✅ Applied",
            color=discord.Color.gold()
        )
        
        # Show sample of new structure
        if new_data:
            sample_user_id = list(new_data.keys())[0]
            sample_data = new_data[sample_user_id]
            
            embed_summary.add_field(
                name="📋 Sample of New Structure",
                value=f"```json\n{json.dumps({sample_user_id: sample_data}, indent=2)[:1000]}...```",
                inline=False
            )
        
        # Show errors if any
        if errors:
            error_list = "\n".join(errors[:5])
            if len(errors) > 5:
                error_list += f"\n...and {len(errors) - 5} more errors"
            
            embed_summary.add_field(
                name="⚠️ Migration Errors",
                value=error_list,
                inline=False
            )
        
        # Migration checklist
        checklist = """
        ✅ **Migration Checklist:**
        • Created backup before migration
        • Preserved all user data
        • Renamed 'teams' field to 'programs'
        • Added 'roles' array for special roles
        • Ensured all required fields exist
        • Maintained special role flags
        • Preserved timestamps
        """
        embed_summary.add_field(name="📋 Migration Results", value=checklist, inline=False)
        
        embed_summary.set_footer(text=f"Migration completed at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        await ctx.send(embed=embed_summary)
        
        # Step 6: Verify special roles are preserved
        await verify_special_roles(ctx)
        
        # Step 7: Log to log channel
        log_embed = discord.Embed(
            title="🔄 JSON Structure Migration",
            description=f"**Users migrated:** {migrated_count}\n"
                      f"**Backup created:** {backup_filename}\n"
                      f"**By:** {ctx.author.mention}",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        await send_to_log_channel(ctx.guild, "", log_embed)
        
        print(f"✅ JSON migration complete: {migrated_count} users migrated, backup: {backup_filename}")
        
    except FileNotFoundError:
        error_embed = discord.Embed(
            title="❌ Migration Failed",
            description=f"JSON file `{REGISTRY_FILE}` not found!",
            color=discord.Color.red()
        )
        await ctx.send(embed=error_embed)
        
    except json.JSONDecodeError as e:
        error_embed = discord.Embed(
            title="❌ JSON Parse Error",
            description=f"Could not parse JSON file:\n```{str(e)}```",
            color=discord.Color.red()
        )
        await ctx.send(embed=error_embed)
        
    except Exception as e:
        error_embed = discord.Embed(
            title="❌ Migration Error",
            description=f"Unexpected error during migration:\n```{str(e)}```",
            color=discord.Color.red()
        )
        await ctx.send(embed=error_embed)
        import traceback
        traceback.print_exc()

async def verify_special_roles(ctx):
    """Verify that special roles are properly preserved after migration."""
    guild = ctx.guild
    special_roles_count = 0
    
    embed = discord.Embed(
        title="🔍 Verifying Special Roles",
        description="Checking that special roles (Instructor, Master Lee's Family) are preserved...",
        color=discord.Color.blue()
    )
    
    for user_id_str, user_data in registered_users.items():
        roles = user_data.get('roles', [])
        
        if "Master Lee's Family" in roles or "Instructor" in roles:
            special_roles_count += 1
            
            # Get member if in server
            user_id = int(user_id_str)
            member = guild.get_member(user_id)
            
            if member:
                # Verify Discord roles match JSON
                has_master_family = MASTER_LEE_FAMILY_ROLE_ID and guild.get_role(MASTER_LEE_FAMILY_ROLE_ID) in member.roles
                has_instructor = INSTRUCTOR_ROLE_ID and guild.get_role(INSTRUCTOR_ROLE_ID) in member.roles
                
                json_has_master = "Master Lee's Family" in roles
                json_has_instructor = "Instructor" in roles
                
                if has_master_family != json_has_master or has_instructor != json_has_instructor:
                    embed.add_field(
                        name=f"⚠️ {member.name}",
                        value=f"Discord: Master={has_master_family}, Instructor={has_instructor}\n"
                              f"JSON: Master={json_has_master}, Instructor={json_has_instructor}",
                        inline=True
                    )
    
    embed.add_field(
        name="📊 Special Roles Summary",
        value=f"**Total users with special roles in JSON:** {special_roles_count}",
        inline=False
    )
    
    if special_roles_count > 0:
        embed.add_field(
            name="✅ Verification Complete",
            value="Special roles have been preserved in the migrated JSON structure.",
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot_command.command(name="list_backups")
@bot_channel_only()
async def chat_list_backups(ctx):
    """List all backup files created by the migration command."""
    import glob
    
    backup_files = glob.glob("registered_users_backup_*.json")
    
    if not backup_files:
        embed = discord.Embed(
            title="📁 No Backups Found",
            description="No backup files found. Use `!bot_command migrate_json_structure` to create a backup.",
            color=discord.Color.grey()
        )
        await ctx.send(embed=embed)
        return
    
    # Sort by creation time (newest first)
    backup_files.sort(key=os.path.getmtime, reverse=True)
    
    embed = discord.Embed(
        title="📁 Available Backups",
        description=f"Found {len(backup_files)} backup file(s):",
        color=discord.Color.blue()
    )
    
    for i, backup_file in enumerate(backup_files[:10]):  # Show first 10
        file_size = os.path.getsize(backup_file)
        file_time = datetime.fromtimestamp(os.path.getmtime(backup_file), timezone.utc)
        
        embed.add_field(
            name=f"📄 {backup_file}",
            value=f"**Size:** {file_size:,} bytes\n"
                  f"**Created:** <t:{int(file_time.timestamp())}:R>\n"
                  f"**Path:** `{backup_file}`",
            inline=False
        )
    
    if len(backup_files) > 10:
        embed.set_footer(text=f"Showing 10 of {len(backup_files)} backups")
    
    await ctx.send(embed=embed)

@bot_command.command(name="verify_json_structure")
@bot_channel_only()
async def chat_verify_json_structure(ctx):
    """Verify that JSON file follows the new structure."""
    
    try:
        with open(REGISTRY_FILE, 'r') as f:
            data = json.load(f)
        
        total_users = len(data)
        valid_users = 0
        invalid_users = []
        missing_fields = {}
        
        required_fields = [
            'child_name', 'role', 'role_display', 'nickname', 
            'gender', 'registered_at', 'programs', 'has_active_private_chat',
            'private_chat_channel_id', 'roles'
        ]
        
        for user_id, user_data in data.items():
            user_valid = True
            missing = []
            
            for field in required_fields:
                if field not in user_data:
                    user_valid = False
                    missing.append(field)
                    
                    # Track missing fields globally
                    if field not in missing_fields:
                        missing_fields[field] = 0
                    missing_fields[field] += 1
            
            # Check field types
            if 'programs' in user_data and not isinstance(user_data['programs'], list):
                user_valid = False
                missing.append("programs (not a list)")
            
            if 'roles' in user_data and not isinstance(user_data['roles'], list):
                user_valid = False
                missing.append("roles (not a list)")
            
            if user_valid:
                valid_users += 1
            else:
                invalid_users.append({
                    'id': user_id,
                    'name': user_data.get('child_name', 'Unknown'),
                    'missing': missing
                })
        
        # Create report embed
        embed = discord.Embed(
            title="🔍 JSON Structure Verification",
            description=f"**Total users:** {total_users}\n"
                      f"**Valid structure:** {valid_users}\n"
                      f"**Invalid structure:** {len(invalid_users)}",
            color=discord.Color.blue() if valid_users == total_users else discord.Color.orange()
        )
        
        if missing_fields:
            embed.add_field(
                name="❌ Missing Fields",
                value="\n".join([f"• {field}: {count} users" for field, count in missing_fields.items()]),
                inline=False
            )
        
        if invalid_users:
            # Show first 5 invalid users
            sample = []
            for user in invalid_users[:5]:
                sample.append(f"• {user['name']} (ID: {user['id']}): {', '.join(user['missing'])}")
            
            embed.add_field(
                name="⚠️ Users with Invalid Structure",
                value="\n".join(sample),
                inline=False
            )
            
            if len(invalid_users) > 5:
                embed.add_field(
                    name="📋 More Issues",
                    value=f"... and {len(invalid_users) - 5} more users need fixing",
                    inline=False
                )
            
            embed.add_field(
                name="🔧 Solution",
                value="Run `!bot_command migrate_json_structure` to fix all users",
                inline=False
            )
        else:
            embed.add_field(
                name="✅ All Good!",
                value="All users have the correct JSON structure.",
                inline=False
            )
        
        # Show sample of good structure
        if valid_users > 0:
            # Find a valid user to show as example
            for user_id, user_data in data.items():
                is_valid = all(field in user_data for field in required_fields)
                if is_valid:
                    sample = {
                        user_id: {
                            k: v for k, v in user_data.items() 
                            if k in required_fields + ['auto_added', 'admin_user', 'master_lee_family', 'instructor']
                        }
                    }
                    sample_json = json.dumps(sample, indent=2, ensure_ascii=False)[:800]
                    embed.add_field(
                        name="📋 Sample Valid Structure",
                        value=f"```json\n{sample_json}...```",
                        inline=False
                    )
                    break
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        error_embed = discord.Embed(
            title="❌ Verification Failed",
            description=f"Error verifying JSON structure:\n```{str(e)}```",
            color=discord.Color.red()
        )
        await ctx.send(embed=error_embed)

# =============================================================================
# QUICK VERIFICATION COMMAND
# =============================================================================

@bot_command.command(name="verify_json_roles")
@bot_channel_only()
async def chat_verify_json_roles(ctx, member: discord.Member = None):
    """
    Verify and show role synchronization status.
    
    Shows comparison between JSON stored roles and current Discord roles.
    """
    if member:
        # Verify specific user
        await chat_view_user_roles(ctx, member)
        return
    
    # Verify all users
    guild = ctx.guild
    total_users = len(registered_users)
    in_sync_count = 0
    out_of_sync_count = 0
    not_in_server = 0
    
    # Role mapping
    role_mapping = {
        FAMILY_ROLE_ID: "Family Member",
        NATIONAL_TEAM_ROLE_ID: "National Team",
        DEMONSTRATION_TEAM_ROLE_ID: "Demonstration Team",
        AFTER_SCHOOL_ROLE_ID: "After School",
        STUDENT_ROLE_ID: "Student",
        INSTRUCTOR_ROLE_ID: "Instructor",
        MASTER_LEE_FAMILY_ROLE_ID: "Master Lee's Family"
    }
    
    for user_id_str, user_data in registered_users.items():
        try:
            user_id = int(user_id_str)
            member = guild.get_member(user_id)
            
            if not member:
                not_in_server += 1
                continue
            
            # Get current Discord roles
            current_roles = []
            for role_id, role_name in role_mapping.items():
                if role_id != 0:
                    role = guild.get_role(role_id)
                    if role and role in member.roles:
                        current_roles.append(role_name)
            
            # Add Admin role if applicable
            if user_id == ADMIN_USER_ID and "Admin" not in current_roles:
                current_roles.append("Admin")
            
            # Get stored roles
            stored_roles = user_data.get('roles', [])
            
            # Compare (sorted for consistency)
            if sorted(current_roles) == sorted(stored_roles):
                in_sync_count += 1
            else:
                out_of_sync_count += 1
                
        except Exception:
            not_in_server += 1
    
    # Create report embed
    embed = discord.Embed(
        title="🔍 JSON Role Verification Report",
        description=f"**Total users in JSON:** {total_users}",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="✅ In Sync",
        value=f"{in_sync_count} users\nJSON matches Discord roles",
        inline=True
    )
    
    embed.add_field(
        name="⚠️ Out of Sync",
        value=f"{out_of_sync_count} users\nNeeds synchronization",
        inline=True
    )
    
    embed.add_field(
        name="❌ Not in Server",
        value=f"{not_in_server} users\nCannot verify (left server)",
        inline=True
    )
    
    if out_of_sync_count > 0:
        embed.add_field(
            name="🔧 Action Required",
            value=f"Run `!bot_command update_json_roles` to sync all users\n"
                   f"Or `!bot_command force_json_sync @user` for specific users",
            inline=False
        )
    
    await ctx.send(embed=embed)

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