"""
Flask Application Factory — EngageVision v2.0
Two-role system: Admin + Teacher
Sprint 1 + Sprint 2: Auth, Teacher Management, Dashboards
"""

import os
from flask import Flask, redirect, url_for, session, render_template
from flask_mail import Mail

from app.config import config
from app import database

# Shared Mail instance — init_app called in create_app
mail = Mail()


def create_app(config_name='default'):
    app = Flask(__name__, template_folder='templates', static_folder='static')

    # ── Load config ──────────────────────────────────────────────────────────
    app.config.from_object(config[config_name])

    # ── Upload directories (future AI sprints) ───────────────────────────────
    for folder in ['UPLOAD_FOLDER', 'CROPS_FOLDER', 'REPORTS_FOLDER']:
        os.makedirs(app.config[folder], exist_ok=True)

    # ── Database ─────────────────────────────────────────────────────────────
    database.init_app(app)

    # ── Mail ─────────────────────────────────────────────────────────────────
    mail.init_app(app)

    # ── Register Blueprints ──────────────────────────────────────────────────
    from app.auth.routes      import auth_bp
    from app.admin.routes     import admin_bp
    from app.dashboard.routes import dashboard_bp
    from app.monitoring.routes import monitoring_bp
    from app.reports.routes   import reports_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(monitoring_bp)
    app.register_blueprint(reports_bp)

    # ── Root redirect ────────────────────────────────────────────────────────
    @app.route('/')
    def index():
        if 'user_id' in session:
            role = session.get('role')
            if role == 'admin':
                return redirect(url_for('admin.dashboard'))
            return redirect(url_for('dashboard.index'))
        return redirect(url_for('auth.login'))

    # ── Error handlers ───────────────────────────────────────────────────────
    @app.errorhandler(403)
    def forbidden(e):
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template('errors/500.html'), 500

    return app
