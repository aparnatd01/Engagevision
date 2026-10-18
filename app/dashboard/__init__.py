from flask import Blueprint
dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/teacher')
from app.dashboard import routes  # noqa: F401, E402
