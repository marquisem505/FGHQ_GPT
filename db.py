import sqlite3, os, time
DB_PATH = os.getenv("DB_PATH", "bot.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    c = get_conn()
    c.execute("""CREATE TABLE IF NOT EXISTS messages(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER,
      role TEXT,         -- 'user' | 'assistant' | 'system'
      content TEXT,
      ts INTEGER
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS memory(
      user_id INTEGER PRIMARY KEY,
      summary TEXT DEFAULT '',
      updated_at INTEGER
    )""")
    c.commit()

def add_message(user_id:int, role:str, content:str):
    conn = get_conn()
    conn.execute("INSERT INTO messages(user_id,role,content,ts) VALUES(?,?,?,?)",
                 (user_id, role, content, int(time.time())))
    conn.commit()

def get_recent_messages(user_id:int, limit:int=12):
    conn = get_conn()
    cur = conn.execute("""SELECT role, content FROM messages
                          WHERE user_id=? ORDER BY id DESC LIMIT ?""",
                       (user_id, limit))
    rows = cur.fetchall()
    return list(reversed(rows))

def get_summary(user_id:int)->str:
    conn = get_conn()
    cur = conn.execute("SELECT summary FROM memory WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    return row[0] if row else ""

def save_summary(user_id:int, summary:str):
    conn = get_conn()
    now = int(time.time())
    if get_summary(user_id) == "":
        conn.execute("INSERT OR REPLACE INTO memory(user_id, summary, updated_at) VALUES(?,?,?)",
                     (user_id, summary, now))
    else:
        conn.execute("UPDATE memory SET summary=?, updated_at=? WHERE user_id=?",
                     (summary, now, user_id))
    conn.commit()

def wipe_user(user_id:int):
    conn = get_conn()
    conn.execute("DELETE FROM messages WHERE user_id=?", (user_id,))
    conn.execute("DELETE FROM memory WHERE user_id=?", (user_id,))
    conn.commit()