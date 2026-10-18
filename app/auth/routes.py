"""
Auth Blueprint Routes — EngageVision
Login / Logout / Forgot Password / Reset Password for Admin and Teacher.

Teacher accounts are created by Admin only.
Self-registration is NOT supported and there is NO register route.
"""

import re
import os
import hashlib
import secrets
import logging
from datetime import datetime, timedelta

from flask import (
    render_template, request, redirect, url_for,
    session, flash, Blueprint, current_app
)
from werkzeug.security import check_password_hash, generate_password_hash

from app.models import (
    get_user_by_username,
    update_user_last_login,
    update_user_password,
    get_teacher_by_email,
    create_reset_token,
    get_valid_reset_token,
    invalidate_reset_token,
    activate_teacher_account,
    username_exists,
    get_teacher_by_staff_id,
)

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

# Token expiry: 1 hour
RESET_TOKEN_EXPIRY_MINUTES = 60

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _role_redirect():
    role = session.get('role')
    if role == 'admin':
        return redirect(url_for('admin.dashboard'))
    return redirect(url_for('dashboard.index'))


def _hash_token(raw_token: str) -> str:
    """SHA-256 hash a raw token for safe DB storage."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


def _send_reset_email(teacher, reset_url):
    """
    Send a professional password-reset email to the teacher.
    Returns True on success, False on failure.
    Uses Flask-Mail with SMTP credentials from .env — never hardcoded.
    """
    from flask_mail import Message
    from app import mail

    teacher_name = f"{teacher.get('first_name', '')} {teacher.get('last_name', '')}".strip() or teacher['username']

    subject = "ENGAGEVISION Password Reset"

    html_body = f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>ENGAGEVISION Password Reset</title>
</head>
<body style="margin:0;padding:0;background:#f4f7fa;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f7fa;padding:40px 20px;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(18,59,93,.1);">

          <!-- Header -->
          <tr>
            <td style="background:linear-gradient(135deg,#123b5d 0%,#1a4f7a 60%,#0f8b8d 100%);padding:36px 40px;text-align:center;">
              <div style="display:inline-block;background:rgba(255,255,255,.15);border-radius:10px;padding:12px 20px;margin-bottom:16px;">
                <span style="font-size:28px;color:#fff;">&#128274;</span>
              </div>
              <h1 style="margin:0;font-size:26px;font-weight:800;color:#fff;letter-spacing:1px;">ENGAGEVISION</h1>
              <p style="margin:6px 0 0;font-size:13px;color:rgba(255,255,255,.75);">AI-Based Student Engagement Monitoring System</p>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:36px 40px;">
              <h2 style="margin:0 0 12px;font-size:20px;font-weight:700;color:#123b5d;">Password Reset Request</h2>
              <p style="margin:0 0 20px;font-size:15px;color:#374151;line-height:1.7;">
                Hello, <strong>{teacher_name}</strong>,
              </p>
              <p style="margin:0 0 20px;font-size:15px;color:#374151;line-height:1.7;">
                We received a request to reset the password for your ENGAGEVISION teacher account.
                Click the button below to set a new password.
              </p>

              <!-- CTA Button -->
              <table cellpadding="0" cellspacing="0" width="100%">
                <tr>
                  <td align="center" style="padding:8px 0 28px;">
                    <a href="{reset_url}"
                       style="display:inline-block;background:linear-gradient(135deg,#123b5d,#2563a6);color:#fff;text-decoration:none;font-size:16px;font-weight:700;padding:14px 36px;border-radius:8px;letter-spacing:.3px;">
                      &#128273; Reset My Password
                    </a>
                  </td>
                </tr>
              </table>

              <!-- Token expiry info -->
              <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:14px 18px;margin-bottom:24px;">
                <p style="margin:0;font-size:13px;color:#1e40af;line-height:1.6;">
                  <strong>&#8987; This link expires in {RESET_TOKEN_EXPIRY_MINUTES} minutes</strong>
                  and can only be used <strong>once</strong>.
                  If it expires, you can request a new one from the login page.
                </p>
              </div>

              <!-- URL fallback -->
              <p style="margin:0 0 8px;font-size:13px;color:#6b7a99;">If the button doesn't work, copy and paste this link into your browser:</p>
              <p style="margin:0 0 24px;font-size:12px;word-break:break-all;color:#2563a6;background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:10px 14px;">
                {reset_url}
              </p>

              <!-- Security warning -->
              <div style="background:#fef2f2;border:1px solid #fca5a5;border-radius:8px;padding:14px 18px;">
                <p style="margin:0;font-size:13px;color:#991b1b;line-height:1.6;">
                  <strong>&#9888; Security Notice:</strong>
                  If you did not request this password reset, please ignore this email.
                  Your current password will remain unchanged.
                  Do not share this link with anyone.
                </p>
              </div>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background:#f8fafc;padding:20px 40px;border-top:1px solid #e2e8f0;text-align:center;">
              <p style="margin:0;font-size:12px;color:#9ca3af;line-height:1.6;">
                ENGAGEVISION &mdash; AI-Powered Classroom Intelligence<br/>
                Academic Institution Platform &copy; {datetime.now().year}<br/>
                This is an automated message. Please do not reply to this email.
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""

    text_body = (
        f"ENGAGEVISION — Password Reset Request\n\n"
        f"Hello, {teacher_name},\n\n"
        f"We received a request to reset your ENGAGEVISION teacher account password.\n\n"
        f"Click the link below to set a new password:\n{reset_url}\n\n"
        f"This link expires in {RESET_TOKEN_EXPIRY_MINUTES} minutes and can only be used once.\n\n"
        f"If you did not request a password reset, please ignore this email. "
        f"Your password will remain unchanged.\n\n"
        f"— ENGAGEVISION Security Team"
    )

    try:
        msg = Message(
            subject=subject,
            recipients=[teacher['email']],
            body=text_body,
            html=html_body,
        )
        mail.send(msg)
        return True
    except Exception as exc:
        # Log the error type but NEVER log passwords, tokens, or email content
        logger.error("Failed to send password reset email: %s", type(exc).__name__)
        return False


# ── LOGIN ─────────────────────────────────────────────────────────────────────

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return _role_redirect()

    error         = None
    selected_role = request.args.get('role', 'admin')
    if selected_role not in ('admin', 'teacher'):
        selected_role = 'admin'

    if request.method == 'POST':
        username      = request.form.get('username', '').strip()
        password      = request.form.get('password', '')
        selected_role = request.form.get('role', 'admin').strip()

        if selected_role not in ('admin', 'teacher'):
            selected_role = 'admin'

        if not username:
            error = 'Username is required.'
        elif not password:
            error = 'Password is required.'

        if not error:
            user = get_user_by_username(username)

            if user is None:
                error = 'Invalid username or password.'
            elif user['role'] != selected_role:
                role_label = 'Admin' if selected_role == 'admin' else 'Teacher'
                error = f'This account is not registered as {role_label}. Please select the correct role.'
            elif user.get('password_hash') is None:
                # Teacher account exists but setup not yet completed
                error = ('Your account has not been set up yet. '
                         'Please use the "Set Up Account" option below '
                         'to create your login credentials.')
            elif not check_password_hash(user['password_hash'], password):
                error = 'Invalid username or password.'
            elif not user['is_active']:
                error = 'Your account is inactive. Please contact the administrator.'

        if error:
            return render_template('auth/login.html', error=error,
                                   username=username, selected_role=selected_role)

        # Successful login
        session.clear()
        session['user_id']    = user['id']
        session['role']       = user['role']
        session['username']   = user['username']
        session['full_name']  = f"{user['first_name']} {user['last_name']}".strip() or user['username']
        session['staff_id']   = user.get('staff_id', '')
        session['department'] = user.get('department', '')
        session.permanent     = True

        update_user_last_login(user['id'])

        first = user['first_name'] or user['username']
        flash(f"Welcome back, {first}!", 'success')
        return _role_redirect()

    return render_template('auth/login.html', error=None, username='', selected_role=selected_role)


# ── LOGOUT ────────────────────────────────────────────────────────────────────

@auth_bp.route('/logout')
def logout():
    name = session.get('full_name', 'User').split()[0]
    session.clear()
    flash(f'You have been logged out, {name}. Goodbye!', 'info')
    return redirect(url_for('auth.login'))


# ── FORGOT PASSWORD (Teacher only — email-based) ──────────────────────────────

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """
    Step 1: Teacher enters their registered email address.
    A secure, single-use, time-limited reset link is sent to that email.
    We always show the same message regardless of whether the email exists
    to prevent account enumeration.
    """
    if 'user_id' in session:
        return _role_redirect()

    submitted = False
    dev_reset_url = None   # Only shown in development mode when mail is not configured

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()

        if not email:
            flash('Please enter your registered email address.', 'danger')
            return render_template('auth/forgot_password.html', submitted=False)

        if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            flash('Please enter a valid email address.', 'danger')
            return render_template('auth/forgot_password.html', submitted=False)

        # Look up teacher by email only (not staff ID)
        teacher = get_teacher_by_email(email)

        if teacher:
            raw_token  = secrets.token_urlsafe(48)
            token_hash = _hash_token(raw_token)
            expires_at = datetime.now() + timedelta(minutes=RESET_TOKEN_EXPIRY_MINUTES)

            create_reset_token(teacher['id'], token_hash, expires_at)

            reset_url = url_for('auth.reset_password', token=raw_token, _external=True)

            # Try to send the email
            mail_sent = _send_reset_email(teacher, reset_url)

            if not mail_sent:
                # Development fallback: show the link directly if email is not configured
                mail_configured = bool(
                    current_app.config.get('MAIL_USERNAME') and
                    current_app.config['MAIL_USERNAME'] != 'your_email@gmail.com'
                )
                if not mail_configured:
                    dev_reset_url = reset_url

        submitted = True
        return render_template('auth/forgot_password.html',
                               submitted=submitted,
                               dev_reset_url=dev_reset_url)

    return render_template('auth/forgot_password.html', submitted=False)


# ── RESET PASSWORD ────────────────────────────────────────────────────────────

@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Step 2: Teacher enters a new password using the reset link."""
    if 'user_id' in session:
        return _role_redirect()

    token_hash = _hash_token(token)
    token_row  = get_valid_reset_token(token_hash)

    if not token_row:
        flash('This password reset link is invalid or has expired. Please request a new one.', 'danger')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        new_pw      = request.form.get('new_password', '')
        confirm_pw  = request.form.get('confirm_password', '')

        errors = []
        if not new_pw:
            errors.append('New password is required.')
        elif len(new_pw) < 8:
            errors.append('Password must be at least 8 characters.')
        elif not re.search(r'[A-Z]', new_pw):
            errors.append('Password must contain at least one uppercase letter.')
        elif not re.search(r'[a-z]', new_pw):
            errors.append('Password must contain at least one lowercase letter.')
        elif not re.search(r'[0-9]', new_pw):
            errors.append('Password must contain at least one digit.')

        if new_pw and new_pw != confirm_pw:
            errors.append('Passwords do not match.')

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('auth/reset_password.html', token=token)

        # Hash and save new password — never store plain text
        update_user_password(token_row['uid'], generate_password_hash(new_pw))

        # Single-use: invalidate token immediately after use
        invalidate_reset_token(token_row['id'])

        flash('Password reset successful! You can now log in with your new password.', 'success')
        return redirect(url_for('auth.login', role='teacher'))

    return render_template('auth/reset_password.html', token=token)



# ── TEACHER ACCOUNT SETUP (Staff-ID based) ────────────────────────────────────

@auth_bp.route('/teacher-setup', methods=['GET', 'POST'])
def teacher_setup():
    """
    Teacher account setup via Staff ID.
    GET  — show the form (Staff ID, Username, Password, Confirm Password).
    POST — validate Staff ID, create credentials, activate account.
    No activation email, link, token, or OTP is involved.
    """
    if 'user_id' in session:
        return _role_redirect()

    error = None
    form_data = {'staff_id': '', 'username': ''}

    if request.method == 'POST':
        staff_id   = request.form.get('staff_id', '').strip()
        username   = request.form.get('username', '').strip()
        password   = request.form.get('password', '')
        confirm_pw = request.form.get('confirm_password', '')

        form_data = {'staff_id': staff_id, 'username': username}

        errors = []

        # ── Staff ID validation ──
        if not staff_id:
            errors.append('Staff ID is required.')
        else:
            teacher = get_teacher_by_staff_id(staff_id)
            if not teacher:
                errors.append('Teacher record not found. Please check your Staff ID and try again.')
            elif teacher.get('username') is not None:
                errors.append('Account already exists. Please login.')

        # Only validate credentials if Staff ID is valid and account is pending
        if not errors:
            # ── Username validation ──
            if not username:
                errors.append('Username is required.')
            elif len(username) < 3:
                errors.append('Username must be at least 3 characters.')
            elif not re.match(r'^[A-Za-z0-9_.]+$', username):
                errors.append('Username may only contain letters, numbers, underscores, and dots.')
            elif username_exists(username):
                errors.append('That username is already taken. Please choose a different one.')

            # ── Password validation ──
            if not password:
                errors.append('Password is required.')
            elif len(password) < 8:
                errors.append('Password must be at least 8 characters.')
            elif not re.search(r'[A-Z]', password):
                errors.append('Password must contain at least one uppercase letter.')
            elif not re.search(r'[a-z]', password):
                errors.append('Password must contain at least one lowercase letter.')
            elif not re.search(r'[0-9]', password):
                errors.append('Password must contain at least one digit.')

            if password and password != confirm_pw:
                errors.append('Passwords do not match.')

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('auth/teacher_setup.html',
                                   error=None, form=form_data)

        # All valid — activate the account
        activate_teacher_account(
            user_id       = teacher['id'],
            username      = username,
            password_hash = generate_password_hash(password),
        )

        flash(
            'Your account has been set up successfully! '
            'You can now log in with your chosen username and password.',
            'success'
        )
        return redirect(url_for('auth.login', role='teacher'))

    return render_template('auth/teacher_setup.html',
                           error=None, form=form_data)

