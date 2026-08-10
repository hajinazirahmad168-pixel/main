import os
import sqlite3
import requests
import asyncio
from datetime import datetime
from telethon import TelegramClient, events
from telethon.tl.functions.channels import InviteToChannelRequest, GetParticipantsRequest
from telethon.tl.types import ChannelParticipantsSearch
from telethon.errors import FloodWaitError, SessionPasswordNeededError

# ============================================================
# CONFIGURATION
# ============================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8450745944:AAENLDlCcSeIb3SftTWoZQqXC8vPRgQ_pkw")
API_ID = int(os.environ.get("API_ID", 30217812))
API_HASH = os.environ.get("API_HASH", "d21066a90786cf2dd348b907ece69d24")

ADMINS = [8762845215]  # Sirf aap

DB_FILE = "bot_saas.db"

# ============================================================
# PLAN LIMITS - Free = 35 Adds | Unlimited Accounts
# ============================================================

def get_plan_limits(plan):
    limits = {
        'free': {'adds': 35, 'dms': 10, 'accounts': 999999},
        'basic': {'adds': 200, 'dms': 100, 'accounts': 999999},
        'pro': {'adds': 1000, 'dms': 500, 'accounts': 999999},
        'enterprise': {'adds': 99999, 'dms': 99999, 'accounts': 999999}
    }
    return limits.get(plan, limits['free'])

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
    print("✅ Database initialized!")

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

def total_users_count():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    count = c.fetchone()[0]
    conn.close()
    return count

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

# ============================================================
# DATABASE INITIALIZE
# ============================================================

init_db()

# ============================================================
# BOT INSTANCE
# ============================================================

bot = TelegramClient('bot_session_final', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

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
✅ **Unlimited Accounts** in all plans!
✅ **Free Plan: 35 adds/day!**

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

# ============================================================
# USERS COMMAND - FIXED WITH BYPASS
# ============================================================

@bot.on(events.NewMessage(pattern='/users'))
async def users_command(event):
    # 🔥 Hardcoded bypass for aap (ID: 8762845215)
    if event.sender_id != 8762845215:
        if not is_admin(event.sender_id):
            await event.reply("❌ Unauthorized!")
            return

    users = get_all_users(50)
    total = total_users_count()

    if not users:
        await event.reply("📭 Koi user nahi mila. Pehle kisi ne bot start nahi kiya.")
        return

    message = f"👥 **User List (Showing {len(users)} of {total}):**\n\n"

    for user in users:
        user_id, username, first_name, plan, is_banned, is_admin, total_adds, total_dms, last_active = user

        status = "🟢" if not is_banned else "🔴"
        admin_badge = "👑 " if is_admin else ""
        if not username:
            username = "NoUsername"

        message += f"{status} {admin_badge}**{first_name}** (@{username})\n"
        message += f"   🆔 ID: `{user_id}`\n"
        message += f"   📊 Adds: {total_adds} | DMs: {total_dms}\n"
        message += f"   💎 Plan: {plan.upper()}\n"
        message += f"   📅 Last Active: {last_active[:16] if last_active != 'Never' else 'Never'}\n\n"

    if len(users) == 50 and total > 50:
        message += f"\n📌 Sirf 50 users dikhaye gaye. Total users: {total}"

    await event.reply(message)

# ============================================================
# ADMINS COMMAND
# ============================================================

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

# ============================================================
# ADD ADMIN - FIXED (Fetches from Telegram if not in DB)
# ============================================================

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
    
    # Pehle database mein check karo
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT user_id, first_name FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    conn.close()
    
    user_id = None
    first_name = username

    if user:
        user_id, first_name = user
    else:
        # 🔥 Database mein nahi mila, Telegram se direct fetch karo!
        try:
            await event.reply(f"⏳ User @{username} database mein nahi mila, Telegram se dhoond raha hoon...")
            entity = await bot.get_entity(username)
            user_id = entity.id
            first_name = entity.first_name or username
            
            # User ko database mein save karo
            create_user(user_id, username, first_name)
            await event.reply(f"✅ User @{username} ko database mein add kar diya gaya!")
            
        except Exception as e:
            await event.reply(f"❌ Telegram par @{username} nahi mila. Error: {str(e)[:50]}")
            return

    if is_admin(user_id):
        await event.reply(f"❌ @{username} is already an admin!")
        return
    
    add_admin(user_id, username, first_name, event.sender_id)
    
    await event.reply(f"✅ @{username} is now an admin! (User ID: {user_id})")
    
    try:
        await bot.send_message(user_id, f"👑 Congratulations! You've been made an admin of AutoBot SaaS by an admin.")
    except:
        pass

# ============================================================
# REMOVE ADMIN
# ============================================================

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

# ============================================================
# BAN / UNBAN
# ============================================================

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

# ============================================================
# STATS
# ============================================================

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

# ============================================================
# BROADCAST
# ============================================================

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

# ============================================================
# LOGIN / ACCOUNTS / STATUS / PLAN
# ============================================================

@bot.on(events.NewMessage(pattern='/login'))
async def login_command(event):
    await event.reply("""
📱 **Login to your Telegram Account**

Send phone number with country code:
Example: `+923001234567`

✅ **Unlimited accounts allowed!**
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
✅ **Unlimited accounts allowed!**
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
    
    message += "\n💡 Use /login to add more accounts. **Unlimited allowed!**"
    
    await event.reply(message)

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
📱 Linked Accounts: {len(sessions)} / ∞ **Unlimited!**

📈 Today:
• Adds: {adds_done}/{limits['adds']}
• DMs: {dms_done}/{limits['dms']}

📊 Lifetime:
• Total Adds: {stats[1] if stats else 0}
• Total DMs: {stats[2] if stats else 0}

🔄 Resets at midnight
✅ **Unlimited accounts in all plans!**
""")

@bot.on(events.NewMessage(pattern='/plan'))
async def plan_command(event):
    await event.reply("""
📊 **Pricing Plans:**

🆓 **Free** → **35 adds/day** | 10 DMs | ∞ Accounts

💎 **Basic** → 200 adds/day | 100 DMs | ∞ Accounts

⚡ **Pro** → 1000 adds/day | 500 DMs | ∞ Accounts

👑 **Enterprise** → Unlimited adds | ∞ DMs | ∞ Accounts

✅ **Every plan includes UNLIMITED accounts!**
✅ **Free plan: 35 adds/day!**

🔑 **Upgrade:** @Real_Member_Adding_1
""")

# ============================================================
# ADD GROUP (Main Feature)
# ============================================================

@bot.on(events.NewMessage(pattern='/addgroup'))
async def addgroup_command(event):
    user_id = event.sender_id
    user = get_user(user_id)
    
    if not user:
        await event.reply("❌ Please use /start first!")
        return
    
    if user[5] == 1:
        await event.reply("❌ You are banned!")
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
        await event.reply("❌ No accounts linked! Use /login first.")
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
                            
                            asyncio.create_task(run_add_task(
                                event, user_id, source, target, count, selected_sessions
                            ))
                            
            except Exception as e:
                await event.reply(f"❌ Error: {str(e)[:100]}")

# ============================================================
# ADD TASK FUNCTION
# ============================================================

async def run_add_task(event, user_id, source, target, count, selected_sessions):
    try:
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
        
        await event.reply(f"""
✅ **Add Task Completed!**

📊 Results:
✅ Added: {total_added}
⏭️ Skipped: {total_skipped}
❌ Failed: {total_failed}
📌 Source: {source}
🎯 Target: {target}
""")
        
    except Exception as e:
        await event.reply(f"❌ Task error: {str(e)[:200]}")

# ============================================================
# STOP
# ============================================================

@bot.on(events.NewMessage(pattern='/stop'))
async def stop_command(event):
    await event.reply("⏹️ Task stopped (if any was running).")

# ============================================================
# ECHO HANDLER - Plain Messages Ka Reply (FIXED)
# ============================================================

@bot.on(events.NewMessage())
async def echo_handler(event):
    # Outgoing messages (jo bot ne khud bheje) ko ignore karo
    if event.out:
        return
    # Agar command hai toh ignore karo (commands pe alag handlers hain)
    if event.raw_text.startswith('/'):
        return
    
    # Debug: Railway logs mein dikhega
    print(f"📩 Echo triggered: '{event.raw_text}' from {event.sender_id}")
    
    try:
        await event.reply(f"👋 Hello! You sent: '{event.raw_text}'\n\nUse /start for commands.")
    except Exception as e:
        print(f"❌ Echo reply failed: {e}")

# ============================================================
# MAIN
# ============================================================

print("✅ Bot Started Successfully!")
print("✅ Free Plan: 35 adds/day!")
print("✅ Unlimited Accounts in all plans!")
print("✅ Echo handler is active!")

def main():
    bot.run_until_disconnected()

if __name__ == "__main__":
    main()# DATABASE SETUP
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
    print("✅ Database initialized!")

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

# ============================================================
# DATABASE INITIALIZE
# ============================================================

init_db()

# ============================================================
# BOT INSTANCE
# ============================================================

bot = TelegramClient('bot_session_v3', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

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
✅ **Unlimited Accounts** in all plans!
✅ **Free Plan: 35 adds/day!**

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

✅ **Unlimited accounts allowed!**
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
✅ **Unlimited accounts allowed!**
""")
                    
                    await temp_client.disconnect()
                    
                except Exception as e:
                    await event.reply(f"❌ Login failed: {str(e)[:100]}")
        
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
    
    message += "\n💡 Use /login to add more accounts. **Unlimited allowed!**"
    
    await event.reply(message)

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
📱 Linked Accounts: {len(sessions)} / ∞ **Unlimited!**

📈 Today:
• Adds: {adds_done}/{limits['adds']}
• DMs: {dms_done}/{limits['dms']}

📊 Lifetime:
• Total Adds: {stats[1] if stats else 0}
• Total DMs: {stats[2] if stats else 0}

🔄 Resets at midnight
✅ **Unlimited accounts in all plans!**
""")

@bot.on(events.NewMessage(pattern='/plan'))
async def plan_command(event):
    await event.reply("""
📊 **Pricing Plans:**

🆓 **Free** → **35 adds/day** | 10 DMs | ∞ Accounts

💎 **Basic** → 200 adds/day | 100 DMs | ∞ Accounts

⚡ **Pro** → 1000 adds/day | 500 DMs | ∞ Accounts

👑 **Enterprise** → Unlimited adds | ∞ DMs | ∞ Accounts

✅ **Every plan includes UNLIMITED accounts!**
✅ **Free plan: 35 adds/day!**

🔑 **Upgrade:** @Real_Member_Adding_1
""")

@bot.on(events.NewMessage(pattern='/addgroup'))
async def addgroup_command(event):
    user_id = event.sender_id
    user = get_user(user_id)
    
    if not user:
        await event.reply("❌ Please use /start first!")
        return
    
    if user[5] == 1:
        await event.reply("❌ You are banned!")
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
        await event.reply("❌ No accounts linked! Use /login first.")
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
                            
                            asyncio.create_task(run_add_task(
                                event, user_id, source, target, count, selected_sessions
                            ))
                            
            except Exception as e:
                await event.reply(f"❌ Error: {str(e)[:100]}")

# ============================================================
# ADD TASK FUNCTION
# ============================================================

async def run_add_task(event, user_id, source, target, count, selected_sessions):
    try:
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
        
        await event.reply(f"""
✅ **Add Task Completed!**

📊 Results:
✅ Added: {total_added}
⏭️ Skipped: {total_skipped}
❌ Failed: {total_failed}
📌 Source: {source}
🎯 Target: {target}
""")
        
    except Exception as e:
        await event.reply(f"❌ Task error: {str(e)[:200]}")

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
print("✅ Free Plan: 35 adds/day!")
print("✅ Unlimited Accounts in all plans!")

def main():
    bot.run_until_disconnected()

if __name__ == "__main__":
    main()
