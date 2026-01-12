# baekho_discord_bot

## 🚀 Quick Start Guide

This README provides comprehensive documentation for both bots, including setup instructions, command references, troubleshooting guides, and best practices. You can copy the entire content above and paste it into a `README.md` file in your project directory.

# Discord Family Registration & Private Chats System
## 📋 Overview

A comprehensive Discord bot system for managing Tae Kwon Do family communities with automatic registration, private chat forwarding, and role management.

## 🏗️ System Architecture

### Two-Bot System:
1. **Setup Bot** (`setup_bot.py`) - Server configuration and structure creation
2. **Main Bot** (`registration_private_chat_bot.py`) - User registration and chat management


### Step 1: Prerequisites
# Install required packages
pip install discord.py


### Step 2: Create Configuration File (config.txt)
# BOT SETTINGS
TOKEN=your_main_bot_token_here
GUILD_ID=your_server_id_here
ADMIN_USER_ID=your_discord_user_id_here

# Leave other IDs as 0 - they will be auto-filled by setup bot
RULES_CHANNEL_ID=0
FAMILY_ROLE_ID=0
RULES_MESSAGE_ID=0
NATIONAL_TEAM_ROLE_ID=0
DEMONSTRATION_TEAM_ROLE_ID=0
NATIONAL_TEAM_CHANNEL_ID=0
DEMONSTRATION_TEAM_CHANNEL_ID=0
GENERAL_CHAT_CHANNEL_ID=0
MASTER_LEE_FAMILY_ROLE_ID=0
TEMPORARY_CHANNELS_CATEGORY_ID=0
ADMIN_CHAT_CHANNEL_ID=0
LOG_CHANNEL_ID=0

### Bot 1: Setup Bot (setup_bot.py)
Purpose
Automatically configures the entire server structure with proper categories, channels, roles, and permissions.

# Server Setup & Configuration
!setup_server                    # Complete server setup (categories, channels, roles)
!setup_check                     # Check current setup status and permissions
!organize_config                 # Organize config.txt into logical groups

# Cleanup & Maintenance
!cleanup_unrecorded              # Remove everything not in config.txt
!reset_setup                     # Reset everything (delete all created elements)

# Permission Management
!fix_schedule_permissions        # Fix schedule channel access permissions
!fix_bot_category                # Make BOT category admin-only
!get_invite                      # Generate bot invite link with proper permissions

### Bot 2: Main Bot (main_bot.py)
Purpose
Handles user registration, private chat management, and automated role assignment.

# User Registration Flow
1. User reacts with ✅ to rules message
2. Bot sends DM with registration steps:
   └─ Step 1: Enter child's first and last name
   └─ Step 2: Select role (mother/father/grandmother/grandfather)
   └─ Step 3: Select teams (National, Demonstration, or none)
3. Bot assigns roles and sets nickname
4. User gains access to appropriate channels

# Private Chat System
Monitored Channels: Messages in these channels trigger private chat creation
Auto-Deletion: Original message deleted from public channel
Private Channel: Created with only user and admin access
Permanent Delete Button: Pinned at top for admin to delete chat anytime

# Admin Commands (Admin Chat Channel Only)
# Statistics & Monitoring
!bot_command chat active_private_chats     # List all active private chats
!bot_command chat register_stats           # Show registration statistics
!bot_command chat active_chats             # Show active conversations
!bot_command chat check_consistency        # Verify registry vs. green checks

# User Management
!bot_command chat view_user @user         # View user's registration info
!bot_command chat send_dm @user message   # Send DM to user
!bot_command chat assign_role @user       # Manually assign family role
!bot_command chat add_teams @user        # Allow user to join teams
!bot_command chat fix_name @user "Name"  # Fix user's registered name

# Bot Configuration
!bot_command chat setup                   # Setup rules message
!bot_command chat setup_private_chats     # Setup private chats category
!bot_command chat setup_admin_chat        # Setup admin chat channel
!bot_command chat clear_chats             # Clear all active conversations
!bot_command chat remove_check @user      # Remove user's green check
!bot_command chat update_message_id ID    # Update rules message ID
!bot_command chat resend_delete_button #channel  # Resend delete button

# Testing & Debugging
!bot_command chat test_button            # Test delete button functionality
!bot_command chat test_reaction          # Test reaction detection
!bot_command chat debug_ids              # Show all configured IDs
!bot_command chat check_message ID       # Check specific message reactions