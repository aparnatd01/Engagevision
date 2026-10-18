"""EngageVision Monitoring Blueprint."""

from flask import Blueprint

monitoring_bp = Blueprint(
    "monitoring",
    __name__,
    url_prefix="/monitoring"
)

from . import routes