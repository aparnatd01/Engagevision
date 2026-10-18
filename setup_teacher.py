"""
setup_teacher.py
────────────────────────────────────────────────────────────────────────────
Run this script ONCE after importing database/schema.sql
to properly hash the default teacher's password.

Usage:
    python setup_teacher.py

It will update the default teacher (T001) password hash in MySQL.
────────────────────────────────────────────────────────────────────────────
"""

import sys
import pymysql
from werkzeug.security import generate_password_hash

# ── Configuration — must match app/config.py ────────────────────────────────────────────
DB_HOST     = 'localhost'
DB_PORT     = 3306
DB_USER     = 'root'
DB_PASSWORD = 'aparna63'
DB_NAME     = 'engagevision'    # ← must match your MySQL database name

# ── Default teacher credentials ───────────────────────────────────────────────
STAFF_ID     = 'T001'
PASSWORD     = 'Admin@123'

print("=" * 60)
print("  EngageVision — Teacher Setup Script")
print("=" * 60)

try:
    conn = pymysql.connect(
        host=DB_HOST, port=DB_PORT,
        user=DB_USER, password=DB_PASSWORD,
        database=DB_NAME, charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor,
    )
    print(f"✅ Connected to MySQL: {DB_HOST}/{DB_NAME}")

    hashed = generate_password_hash(PASSWORD)
    print(f"✅ Password hashed successfully.")

    with conn.cursor() as cur:
        cur.execute(
            "UPDATE teachers SET password_hash = %s WHERE staff_id = %s",
            (hashed, STAFF_ID)
        )
        if cur.rowcount == 0:
            # Insert if not exists
            cur.execute(
                """INSERT INTO teachers (name, staff_id, department, email, password_hash)
                   VALUES (%s, %s, %s, %s, %s)""",
                ('Dr. Ananya Sharma', STAFF_ID,
                 'Master of Computer Applications',
                 'ananya.sharma@college.edu', hashed)
            )
            print(f"✅ Teacher '{STAFF_ID}' inserted.")
        else:
            print(f"✅ Teacher '{STAFF_ID}' password updated.")

    conn.commit()
    conn.close()

    print()
    print("  Default Login Credentials:")
    print(f"  Staff ID  : {STAFF_ID}")
    print(f"  Password  : {PASSWORD}")
    print()
    print("  Run the app with: python run.py")
    print("=" * 60)

except pymysql.err.OperationalError as e:
    print(f"\u274c MySQL Connection Error: {e}")
    print()
    print("  Please check:")
    print(f"  1. MySQL is running on {DB_HOST}:{DB_PORT}")
    print(f"  2. User '{DB_USER}' password is correct")
    print(f"  3. Database '{DB_NAME}' exists (CREATE DATABASE {DB_NAME};)")
    print( "  4. You have run database/schema.sql first")
    sys.exit(1)
except pymysql.err.IntegrityError as e:
    print(f"\u274c Integrity Error (duplicate teacher?): {e}")
    sys.exit(1)
except Exception as e:
    print(f"\u274c Unexpected error: {e}")
    sys.exit(1)
