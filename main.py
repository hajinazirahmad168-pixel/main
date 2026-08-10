import asyncio
import os
import sqlite3
import requests
from datetime import datetime
from telethon import TelegramClient, events

# ============================================================
# CONFIGURATION
# ============================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8450745944:AAENLDlCcSeIb3SftTWoZQqXC8vPRgQ_pkw")
API_ID = int(os.environ.get("API_ID", 30217812))
API_HASH = os.environ.get("API_HASH", "d21066a90786cf2dd348b907ece69d24")

ADMINS = [8762845215]

DB_FILE = "bot_saas.db"

# ============================================================
# DATABASE SETUP
# ============================================================

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
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
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS daily_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            date TEXT,
            adds_done INTEGER DEFAULT 0,
            dms_done INTEGER DEFAULT 0
        )
    ''')
    
    conn.commit()
    
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
# DATABASE FUNCTIONS
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
    c.execute("SELECT user_id, username, first_name FROM admins WHERE is_active = 1")
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

def get_user_stats(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM user_stats WHERE user_id = ?", (user_id,))
    stats = c.fetchone()
    conn.close()
    return stats

# ============================================================
# BOT INSTANCE
# ============================================================

bot = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# ============================================================
# COMMANDS
# ============================================================

@bot.on(events.NewMessage(pattern='/start'))
async def start_command(event):
    user_id = event.sender_id
    username = event.sender.username or 'NoUsername'
    first_name = event.sender.first_name or 'User'
    
    create_user(user_id, username, first_name)
    
    is_admin_user = is_admin(user_id)
    
    menu = f"""
🚀 **Welcome to AutoBot SaaS!**  
Hi {first_name}!

✅ Add members to groups
✅ Send mass DMs

📌 **Commands:**
/start - Show menu
/login - Add Telegram account
/addgroup - Add members to groups
/accounts - View linked accounts
/status - Check your plan
/plan - View pricing plans
/stop - Stop current task
"""
    
    if is_admin_user:
        menu += """
👑 **Admin Commands:**
/users - View all users
/admins - Manage admins
/addadmin @username - Add new admin
/removeadmin @username - Remove admin
/ban @username - Ban user
/unban @username - Unban user
/stats - Bot statistics
/broadcast - Send message to all users
"""
    
    await event.reply(menu)

@bot.on(events.NewMessage(pattern='/ping'))
async def ping_command(event):
    await event.reply("🏓 Pong! Bot is alive!")

@bot.on(events.NewMessage(pattern='/users'))
async def users_command(event):
    if not is_admin(event.sender_id):
        await event.reply("❌ Unauthorized!")
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
        message += f"   📊 Adds: {total_adds} | DMs: {total_dms}\n"
        message += f"   💎 Plan: {plan.upper()}\n\n"
    
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
        user_id, username, first_name = admin
        message += f"• {first_name} (@{username})\n"
        message += f"  ID: `{user_id}`\n\n"
    
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
        await event.reply(f"❌ User @{username} not found!")
        return
    
    user_id, first_name = user
    
    if is_admin(user_id):
        await event.reply(f"❌ @{username} is already an admin!")
        return
    
    add_admin(user_id, username, first_name, event.sender_id)
    
    await event.reply(f"✅ @{username} is now an admin!")

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
    
    await event.reply(f"✅ @{username} has been unbanned!")

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
    c.execute("SELECT COUNT(*) FROM admins WHERE is_active = 1")
    total_admins = c.fetchone()[0]
    conn.close()
    
    await event.reply(f"""
📊 **Bot Statistics:**

👥 Total Users: {total_users}
👑 Admins: {total_admins}
📱 Sessions: {total_sessions}
👤 Members Added: {total_members}
⚡ Status: Running
🤖 Bot is online!
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
            
            await event.reply(f"✅ Broadcast sent to {sent} users!")

@bot.on(events.NewMessage(pattern='/login'))
async def login_command(event):
    await event.reply("""
📱 **Login to your Telegram Account**

Send phone number with country code:
Example: `+923001234567`
""")

@bot.on(events.NewMessage(pattern='/status'))
async def status_command(event):
    user_id = event.sender_id
    user = get_user(user_id)
    
    if not user:
        await event.reply("❌ Please use /start first!")
        return
    
    plan = user[3]
    sessions = get_user_sessions(user_id)
    stats = get_user_stats(user_id)
    
    await event.reply(f"""
📊 **Your Status:**

👤 Plan: {plan.upper()}
📱 Linked Accounts: {len(sessions)}

📊 Lifetime:
• Total Adds: {stats[1] if stats else 0}
• Total DMs: {stats[2] if stats else 0}
""")

@bot.on(events.NewMessage(pattern='/plan'))
async def plan_command(event):
    await event.reply("""
📊 **Pricing Plans:**

🆓 **Free** → 10 adds/day | 1 account
💎 **Basic** → 200 adds/day | 3 accounts
⚡ **Pro** → 1000 adds/day | 5 accounts
👑 **Enterprise** → Unlimited

🔑 **Upgrade:** @Real_Member_Adding_1
""")

@bot.on(events.NewMessage(pattern='/addgroup'))
async def addgroup_command(event):
    await event.reply("""
📌 **Add Members**

First login with /login
Then use this format:
`/addgroup @source @target 50`
""")

@bot.on(events.NewMessage(pattern='/stop'))
async def stop_command(event):
    await event.reply("⏹️ Task stopped (if any was running).")

@bot.on(events.NewMessage())
async def echo(event):
    if not event.out and not event.raw_text.startswith('/'):
        await event.reply(f"👋 Hello! Use /start for commands.")

# ============================================================
# MAIN
# ============================================================

print("✅ Bot Started Successfully!")

def main():
    bot.run_until_disconnected()

if __name__ == "__main__":
    main()
