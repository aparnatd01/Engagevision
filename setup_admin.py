#!/usr/bin/env python3
"""
setup_admin.py — EngageVision Admin Bootstrap Script
═══════════════════════════════════════════════════════════════════

Run this script ONCE after creating the database with schema.sql
to set the admin account password securely.

Usage:
    python setup_admin.py

The script will:
  1. Connect to MySQL using your .env configuration
  2. Prompt you for the admin username (default: admin)
  3. Prompt you for a secure password (hidden input)
  4. Hash the password with Werkzeug
  5. Update the admin account in the `users` table

Do NOT store admin credentials in this file.
Do NOT commit .env to version control.
"""

import sys
import getpass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import os
import re

try:
    import pymysql
    import pymysql.cursors
except ImportError:
    print("ERROR: PyMySQL is not installed. Run: pip install PyMySQL")
    sys.exit(1)

try:
    from werkzeug.security import generate_password_hash
except ImportError:
    print("ERROR: Werkzeug is not installed. Run: pip install Werkzeug")
    sys.exit(1)


# ─── Configuration ─────────────────────────────────────────────────────────
DB_HOST = os.environ.get('MYSQL_HOST', 'localhost')
DB_PORT = int(os.environ.get('MYSQL_PORT', 3306))
DB_USER = os.environ.get('MYSQL_USER', 'root')
DB_PASS = os.environ.get('MYSQL_PASSWORD', '')
DB_NAME = os.environ.get('MYSQL_DB', 'engagevision')


def validate_password(pw: str) -> list:
    """Return list of error strings; empty list means OK."""
    errors = []
    if len(pw) < 8:
        errors.append("Password must be at least 8 characters.")
    if not re.search(r'[A-Z]', pw):
        errors.append("Password must contain at least one uppercase letter (A-Z).")
    if not re.search(r'[0-9]', pw):
        errors.append("Password must contain at least one digit (0-9).")
    return errors


def main():
    print("=" * 60)
    print("  EngageVision — Admin Account Setup")
    print("=" * 60)
    print(f"\nDatabase: {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
    print()

    # Connect to DB
    try:
        conn = pymysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASS,
            database=DB_NAME,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor,
        )
    except Exception as e:
        print(f"ERROR: Could not connect to MySQL: {e}")
        print("\nPlease check your .env file and make sure MySQL is running.")
        sys.exit(1)

    try:
        with conn.cursor() as cur:
            # Check for existing admins
            cur.execute("SELECT id, username, email FROM users WHERE role='admin'")
            admins = cur.fetchall()

        if admins:
            print("Existing admin account(s):")
            for a in admins:
                print(f"  • ID {a['id']:3d} | {a['username']:<20s} | {a['email']}")
            print()
            print("You can set/reset the password for any admin account.")
            username = input("Enter admin username to update [default: admin]: ").strip() or 'admin'
        else:
            print("No admin account found. Creating a new admin account.\n")
            username    = input("Admin username  [default: admin]: ").strip() or 'admin'
            first_name  = input("First name      [default: System]: ").strip() or 'System'
            last_name   = input("Last name       [default: Admin]:  ").strip() or 'Admin'
            email       = input("Email address:  ").strip()
            if not email:
                email = f"{username}@engagevision.edu"

        print()
        while True:
            pw = getpass.getpass("Enter new admin password: ")
            errors = validate_password(pw)
            if errors:
                for e in errors:
                    print(f"  ✗ {e}")
                print()
                continue
            confirm = getpass.getpass("Confirm password:        ")
            if pw != confirm:
                print("  ✗ Passwords do not match. Try again.\n")
                continue
            break

        hashed = generate_password_hash(pw)

        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE username=%s AND role='admin'", (username,))
            row = cur.fetchone()

            if row:
                cur.execute(
                    "UPDATE users SET password_hash=%s, is_active=1 WHERE id=%s",
                    (hashed, row['id'])
                )
                conn.commit()
                print(f"\n✅ Password updated for admin '{username}'.")
            else:
                # Create new admin
                cur.execute(
                    """INSERT INTO users
                       (username, email, password_hash, role, first_name, last_name, is_active)
                       VALUES (%s, %s, %s, 'admin', %s, %s, 1)""",
                    (username, email, hashed, first_name, last_name)
                )
                conn.commit()
                print(f"\n✅ Admin account '{username}' created successfully.")

        print()
        print("=" * 60)
        print("  Setup complete! You can now log in to EngageVision.")
        print(f"  URL:      http://127.0.0.1:5000")
        print(f"  Username: {username}")
        print(f"  Password: (the one you just set)")
        print("=" * 60)

    finally:
        conn.close()


if __name__ == '__main__':
    main()
