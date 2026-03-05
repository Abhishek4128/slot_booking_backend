"""
server.py — Pure Python HTTP Backend
No Django, No Flask — only built-in libraries + mysql-connector-python
Run: python server.py
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
# import mimetypes
# from pathlib import Path
import mysql.connector
import hashlib
import os
from datetime import date
from urllib.parse import urlparse, parse_qs

# ── CONFIG ────────────────────────────────────────────────────────────────────
DB_CONFIG = {
    'host':     'mysql.railway.internal',
    'user':     'root',
    'password': 'nqdyEBIeewACCFiBkvXqwzqQVMQKhuuZ',       
    'database': 'railway',
    'port':     3306,
    'charset':  'utf8mb4',
}

SERVER_PORT   = 8000
# BASE_DIR     = Path(__file__).resolve().parent.parent
# FRONTEND_DIR = BASE_DIR / 'frontend'
ALLOWED_ORIGIN = 'https://glowing-pika-f770ac.netlify.app'   



def get_db():
    return mysql.connector.connect(**DB_CONFIG)


def db_fetch(sql, params=None):
    """Run a SELECT and return list of dicts."""
    conn = get_db()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute(sql, params or ())
        return cur.fetchall()
    finally:
        cur.close(); conn.close()


def db_fetch_one(sql, params=None):
    rows = db_fetch(sql, params)
    return rows[0] if rows else None


def db_execute(sql, params=None):
    """Run INSERT / UPDATE / DELETE. Returns lastrowid."""
    conn = get_db()
    cur  = conn.cursor()
    try:
        cur.execute(sql, params or ())
        conn.commit()
        return cur.lastrowid
    finally:
        cur.close(); conn.close()


def setup_db():
    """Create database, tables, and seed slots on first run."""
    conn = mysql.connector.connect(
        host=DB_CONFIG['host'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password'],
        port=DB_CONFIG['port'],
    )
    cur = conn.cursor()

    cur.execute(f"CREATE DATABASE IF NOT EXISTS {DB_CONFIG['database']} "
                f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    cur.execute(f"USE {DB_CONFIG['database']}")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            username      VARCHAR(80)  UNIQUE NOT NULL,
            email         VARCHAR(120) UNIQUE NOT NULL,
            password_hash VARCHAR(200) NOT NULL,
            full_name     VARCHAR(150),
            token         VARCHAR(200),
            created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS slots (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            title       VARCHAR(200) NOT NULL,
            description TEXT,
            slot_date   DATE         NOT NULL,
            start_time  TIME         NOT NULL,
            end_time    TIME         NOT NULL,
            capacity    INT          DEFAULT 5,
            location    VARCHAR(200) DEFAULT 'Online',
            status      VARCHAR(20)  DEFAULT 'available',
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id         INT AUTO_INCREMENT PRIMARY KEY,
            user_id    INT NOT NULL,
            slot_id    INT NOT NULL,
            status     VARCHAR(20) DEFAULT 'confirmed',
            notes      TEXT,
            booked_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)  ON DELETE CASCADE,
            FOREIGN KEY (slot_id) REFERENCES slots(id)  ON DELETE CASCADE,
            UNIQUE KEY unique_booking (user_id, slot_id)
        )
    """)

   
    cur.execute("SELECT COUNT(*) FROM slots")
    if cur.fetchone()[0] == 0:
        today = date.today().isoformat()
        samples = [
            ("Morning Standup",      "Daily team sync.",          today, "09:00", "10:00", 5,  "Conference Room A"),
            ("UX Design Review",     "Review wireframes.",        today, "10:00", "11:00", 4,  "Design Lab"),
            ("Product Strategy",     "Roadmap planning.",         today, "11:00", "12:00", 6,  "Board Room"),
            ("Lunch & Learn",        "Knowledge sharing.",        today, "12:00", "13:00", 10, "Cafeteria"),
            ("Sprint Planning",      "Sprint goals and tasks.",   today, "14:00", "15:00", 8,  "Engineering Hub"),
            ("Marketing Sync",       "Campaign updates.",         today, "15:00", "16:00", 5,  "Online (Zoom)"),
            ("1-on-1 Coaching",      "Career development.",       today, "16:00", "17:00", 2,  "Private Office"),
            ("Dev Workshop",         "Hands-on coding session.",  today, "09:00", "10:00", 6,  "Workshop Room"),
            ("Client Onboarding",    "New client welcome.",       today, "11:00", "12:00", 4,  "Online (Meet)"),
            ("Data Analytics Brief", "Weekly metrics review.",    today, "14:00", "15:00", 5,  "Analytics Suite"),
        ]
        cur.executemany("""
            INSERT INTO slots (title, description, slot_date,
                               start_time, end_time, capacity, location)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, samples)
        print(f"  ✓ Seeded {len(samples)} sample slots.")

    conn.commit(); cur.close(); conn.close()
    print("  ✓ Database ready.")


def hash_password(password):
    salt   = os.urandom(16).hex()
    digest = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}:{digest}"


def verify_password(password, stored):
    try:
        salt, digest = stored.split(':')
        return hashlib.sha256((salt + password).encode()).hexdigest() == digest
    except Exception:
        return False


def new_token(user_id, username):
    raw = f"{user_id}:{username}:{os.urandom(16).hex()}"
    return hashlib.sha256(raw.encode()).hexdigest()



class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        print(f"  [{self.address_string()}] {fmt % args}")

    def send_json(self, data, status=200):
        body = json.dumps(data, default=str).encode()
        self.send_response(status)
        self.send_header('Content-Type',                  'application/json')
        self.send_header('Content-Length',                len(body))
        self.send_header('Access-Control-Allow-Origin',   ALLOWED_ORIGIN)
        self.send_header('Access-Control-Allow-Methods',  'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers',  'Content-Type, Authorization')
        self.end_headers()
        self.wfile.write(body)

    def fail(self, msg, status=400):
        self.send_json({'success': False, 'error': msg}, status)

    def body(self):
        n = int(self.headers.get('Content-Length', 0))
        return json.loads(self.rfile.read(n)) if n else {}

    def token(self):
        return self.headers.get('Authorization', '').replace('Bearer ', '').strip() or None

    def current_user(self):
        t = self.token()
        return db_fetch_one("SELECT * FROM users WHERE token=%s", (t,)) if t else None

    
    

    # def serve_file(self, file_path):
    #     try:
    #         with open(file_path, 'rb') as f:
    #            content = f.read()
    #         mime, _ = mimetypes.guess_type(str(file_path))
    #         mime = mime or 'application/octet-stream'
    #         self.send_response(200)
    #         self.send_header('Content-Type', mime)
    #         self.send_header('Content-Length', len(content))
    #         self.send_header('Access-Control-Allow-Origin', ALLOWED_ORIGIN)
    #         self.end_headers()
    #         self.wfile.write(content)
    #     except FileNotFoundError:
    #         self.send_response(404)
    #         self.end_headers()
    #         self.wfile.write(b'File not found')
    




    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin',  ALLOWED_ORIGIN)
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()

    

    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path
        qs     = parse_qs(parsed.query)

        # Health check
        if path == '/':
           return self.send_json({'status': 'SlotBook API is running'})
        if path == '/api/slots':
            today  = date.today().isoformat()
            d_filt = qs.get('date',   [None])[0]
            s_filt = qs.get('status', [None])[0]

            sql  = "SELECT * FROM slots WHERE slot_date >= %s"
            args = [today]
            if d_filt:
                sql  = "SELECT * FROM slots WHERE slot_date = %s"
                args = [d_filt]
            if s_filt:
                sql += " AND status = %s"; args.append(s_filt)
            sql += " ORDER BY slot_date, start_time"

            slots = db_fetch(sql, args)
            for s in slots:
                cnt = db_fetch_one(
                    "SELECT COUNT(*) AS c FROM bookings "
                    "WHERE slot_id=%s AND status='confirmed'", (s['id'],))
                s['booked_count']     = cnt['c']
                s['available_spots']  = s['capacity'] - cnt['c']
                s['occupancy_percent']= int(cnt['c'] / s['capacity'] * 100) if s['capacity'] else 100

            user = self.current_user()
            booked_ids = []
            if user:
                rows = db_fetch(
                    "SELECT slot_id FROM bookings "
                    "WHERE user_id=%s AND status='confirmed'", (user['id'],))
                booked_ids = [r['slot_id'] for r in rows]

            all_today = db_fetch("SELECT status FROM slots WHERE slot_date >= %s", (today,))
            return self.send_json({
                'success': True,
                'slots':   slots,
                'user_booked_ids': booked_ids,
                'stats': {
                    'total':     len(all_today),
                    'available': sum(1 for s in all_today if s['status'] == 'available'),
                    'full':      sum(1 for s in all_today if s['status'] == 'full'),
                }
            })

        elif path == '/api/my-bookings':
            user = self.current_user()
            if not user:
                return self.fail('Not authenticated', 401)
            rows = db_fetch("""
                SELECT b.*, s.title, s.slot_date, s.start_time,
                       s.end_time, s.location, s.capacity
                FROM bookings b
                JOIN slots s ON b.slot_id = s.id
                WHERE b.user_id = %s
                ORDER BY b.booked_at DESC
            """, (user['id'],))
            return self.send_json({'success': True, 'bookings': rows})

        elif path == '/api/me':
            user = self.current_user()
            if not user:
                return self.fail('Not authenticated', 401)
            return self.send_json({'success': True, 'user': {
                'id': user['id'], 'username': user['username'],
                'email': user['email'], 'full_name': user['full_name'],
            }})

        else:
            self.fail('Not found', 404)


    def do_POST(self):
        path = urlparse(self.path).path
        data = self.body()

        if path == '/api/register':
            username  = data.get('username', '').strip()
            email     = data.get('email',    '').strip()
            password  = data.get('password', '')
            full_name = data.get('full_name','').strip()

            if not all([username, email, password]):
                return self.fail('Username, email and password are required.')
            if len(password) < 6:
                return self.fail('Password must be at least 6 characters.')
            if db_fetch_one("SELECT id FROM users WHERE username=%s", (username,)):
                return self.fail('Username already taken.')
            if db_fetch_one("SELECT id FROM users WHERE email=%s", (email,)):
                return self.fail('Email already registered.')

            pw_hash = hash_password(password)
            token   = new_token(0, username)
            uid     = db_execute(
                "INSERT INTO users (username,email,password_hash,full_name,token) "
                "VALUES (%s,%s,%s,%s,%s)",
                (username, email, pw_hash, full_name, token)
            )
            return self.send_json({'success': True, 'token': token,
                                   'user': {'id': uid, 'username': username,
                                            'email': email, 'full_name': full_name}})

        elif path == '/api/login':
            username = data.get('username', '').strip()
            password = data.get('password', '')
            user = db_fetch_one("SELECT * FROM users WHERE username=%s", (username,))
            if not user or not verify_password(password, user['password_hash']):
                return self.fail('Invalid username or password.', 401)
            token = new_token(user['id'], username)
            db_execute("UPDATE users SET token=%s WHERE id=%s", (token, user['id']))
            return self.send_json({'success': True, 'token': token,
                                   'user': {'id': user['id'], 'username': user['username'],
                                            'email': user['email'], 'full_name': user['full_name']}})

        elif path == '/api/book':
            user = self.current_user()
            if not user:
                return self.fail('Not authenticated', 401)

            slot_id = data.get('slot_id')
            notes   = data.get('notes', '')
            slot    = db_fetch_one("SELECT * FROM slots WHERE id=%s", (slot_id,))

            if not slot:
                return self.fail('Slot not found.')
            if slot['status'] != 'available':
                return self.fail('This slot is not available.')
            if db_fetch_one(
                "SELECT id FROM bookings WHERE user_id=%s AND slot_id=%s AND status='confirmed'",
                (user['id'], slot_id)
            ):
                return self.fail('You already booked this slot.')

            cnt = db_fetch_one(
                "SELECT COUNT(*) AS c FROM bookings "
                "WHERE slot_id=%s AND status='confirmed'", (slot_id,))
            if cnt['c'] >= slot['capacity']:
                return self.fail('Slot is full.')

            db_execute(
                "INSERT INTO bookings (user_id,slot_id,notes,status) "
                "VALUES (%s,%s,%s,'confirmed')",
                (user['id'], slot_id, notes)
            )
            if cnt['c'] + 1 >= slot['capacity']:
                db_execute("UPDATE slots SET status='full' WHERE id=%s", (slot_id,))

            return self.send_json({'success': True,
                                   'message': f"Successfully booked '{slot['title']}'"})

        elif path == '/api/cancel':
            user = self.current_user()
            if not user:
                return self.fail('Not authenticated', 401)

            booking = db_fetch_one(
                "SELECT * FROM bookings WHERE id=%s AND user_id=%s",
                (data.get('booking_id'), user['id'])
            )
            if not booking:
                return self.fail('Booking not found.')

            db_execute("UPDATE bookings SET status='cancelled' WHERE id=%s", (booking['id'],))
            db_execute(
                "UPDATE slots SET status='available' "
                "WHERE id=%s AND status='full'", (booking['slot_id'],)
            )
            return self.send_json({'success': True, 'message': 'Booking cancelled.'})

        elif path == '/api/logout':
            user = self.current_user()
            if user:
                db_execute("UPDATE users SET token=NULL WHERE id=%s", (user['id'],))
            return self.send_json({'success': True})

        else:
            self.fail('Not found', 404)



if __name__ == '__main__':
    print("\n🔧 Setting up database...")
    setup_db()
    port = int(os.environ.get('PORT', 8000)) 
    print(f"\n🚀 Server running at → http://localhost:{port}")
    print("   Press Ctrl+C to stop.\n")
    HTTPServer(('0.0.0.0', port), Handler).serve_forever()
