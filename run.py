"""
EngageVision — AI-Based Student Engagement Monitoring System
Entry point for the Flask application.

Usage:
    python run.py

Configuration:
    Copy .env.example to .env and set your MySQL credentials before running.
    Run `python setup_admin.py` first to create the admin account.
"""

import os
import sys
import io

# ── Ensure print() output is never block-buffered ───────────────────────────
# When Werkzeug's debug reloader starts Flask in a child process on Windows,
# the child's stdout is a pipe (not a TTY).  Python defaults to 8KB block
# buffering on pipes, so print() output only appears after the buffer fills or
# the process exits — long after the video processing finishes.
# Setting PYTHONUNBUFFERED=1 (and reconfiguring sys.stdout) makes every print()
# visible in the VS Code terminal immediately.
os.environ["PYTHONUNBUFFERED"] = "1"
if not sys.stdout.line_buffering:
    try:
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer,
            encoding=sys.stdout.encoding or "utf-8",
            errors="replace",
            line_buffering=True,
        )
    except Exception:
        pass

from app import create_app

app = create_app()

if __name__ == '__main__':
    # Ensure upload directories exist
    os.makedirs(os.path.join('app', 'static', 'uploads', 'videos'), exist_ok=True)
    os.makedirs(os.path.join('app', 'static', 'uploads', 'crops'),  exist_ok=True)
    os.makedirs(os.path.join('app', 'static', 'uploads', 'reports'), exist_ok=True)

    host = os.environ.get('FLASK_RUN_HOST', '0.0.0.0')
    port = int(os.environ.get('FLASK_RUN_PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', '1') == '1'

    print("=" * 60)
    print("  EngageVision — AI-Based Engagement Monitoring System")
    print(f"  Running at: http://127.0.0.1:{port}")
    print("  To create admin: python setup_admin.py")
    print("=" * 60)

    app.run(debug=debug, host=host, port=port)
