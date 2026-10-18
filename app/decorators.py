"""
Authentication decorators for role-based access control.
"""

from functools import wraps
from flask import session, redirect, url_for, flash, abort


def login_required(f):
    """Require any authenticated user (admin or teacher)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def teacher_required(f):
    """Require the user to be an authenticated TEACHER."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        if session.get('role') != 'teacher':
            abort(403)
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """Require the user to be an authenticated ADMIN."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        if session.get('role') != 'admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated
