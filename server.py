


from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import mysql.connector
import hashlib
import os
from datetime import date, timedelta
from urllib.parse import urlparse, parse_qs

# ── CONFIG ─────────────────────────────────────────
DB_CONFIG = {
    'host':     'mysql.railway.internal',
    'user':     'root',
    'password': 'nqdyEBIeewACCFiBkvXqwzqQVMQKhuuZ',
    'database': 'railway',
    'port':     3306,
    'charset':  'utf8mb4',
}

ALLOWED_ORIGIN = 'https://effortless-haupia-4c5a9e.netlify.app'


# ── DB HELPERS ─────────────────────────────────────
def get_db():
    return mysql.connector.connect(**DB_CONFIG)


def db_fetch(sql, params=None):
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute(sql, params or ())
    data = cur.fetchall()
    cur.close()
    conn.close()
    return data


def db_fetch_one(sql, params=None):
    rows = db_fetch(sql, params)
    return rows[0] if rows else None


def db_execute(sql, params=None):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql, params or ())
    conn.commit()
    cur.close()
    conn.close()


# ── 🔥 AUTO SLOT GENERATION (IMPORTANT) ─────────────
def ensure_slots():
    today = date.today()

    for i in range(7):  # maintain next 7 days
        day = (today + timedelta(days=i)).isoformat()

        existing = db_fetch_one(
            "SELECT COUNT(*) as c FROM slots WHERE slot_date=%s",
            (day,)
        )

        if existing['c'] == 0:
            samples = [
                ("Morning Standup", "Daily team sync.", day, "09:00", "10:00", 5, "Conference Room A"),
                ("UX Design Review", "Review wireframes.", day, "10:00", "11:00", 4, "Design Lab"),
                ("Product Strategy", "Roadmap planning.", day, "11:00", "12:00", 6, "Board Room"),
                ("Lunch & Learn", "Knowledge sharing.", day, "12:00", "13:00", 10, "Cafeteria"),
            ]

            conn = get_db()
            cur = conn.cursor()
            cur.executemany("""
                INSERT INTO slots (title, description, slot_date,
                                   start_time, end_time, capacity, location)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
            """, samples)
            conn.commit()
            cur.close()
            conn.close()

            print(f"✓ Created slots for {day}")


# ── DB SETUP ───────────────────────────────────────
def setup_db():
    conn = mysql.connector.connect(
        host=DB_CONFIG['host'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password'],
        port=DB_CONFIG['port'],
    )
    cur = conn.cursor()

    cur.execute(f"CREATE DATABASE IF NOT EXISTS {DB_CONFIG['database']}")
    cur.execute(f"USE {DB_CONFIG['database']}")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(80) UNIQUE,
            email VARCHAR(120) UNIQUE,
            password_hash VARCHAR(200),
            full_name VARCHAR(150),
            token VARCHAR(200)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS slots (
            id INT AUTO_INCREMENT PRIMARY KEY,
            title VARCHAR(200),
            description TEXT,
            slot_date DATE,
            start_time TIME,
            end_time TIME,
            capacity INT,
            location VARCHAR(200),
            status VARCHAR(20) DEFAULT 'available'
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT,
            slot_id INT,
            status VARCHAR(20),
            notes TEXT
        )
    """)

    conn.commit()
    cur.close()
    conn.close()

    print("✓ Database ready")


# ── AUTH ───────────────────────────────────────────
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def new_token(user_id):
    return hashlib.sha256(f"{user_id}{os.urandom(16)}".encode()).hexdigest()


# ── SERVER ─────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):

    def send_json(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', ALLOWED_ORIGIN)
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', ALLOWED_ORIGIN)
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/':
            return self.send_json({"status": "API running"})

        if path == '/api/slots':
            ensure_slots()  

            today = date.today().isoformat()
            slots = db_fetch("SELECT * FROM slots WHERE slot_date >= %s ORDER BY slot_date", (today,))

            return self.send_json({
                "success": True,
                "slots": slots
            })

    def do_POST(self):
        self.send_json({"success": True})


# ── MAIN ───────────────────────────────────────────
if __name__ == '__main__':
    print("Starting server...")
    setup_db()
    port = int(os.environ.get('PORT', 8000))
    HTTPServer(('0.0.0.0', port), Handler).serve_forever()