from flask import Blueprint

messaging_bp = Blueprint('messaging', __name__)

from . import routes  # noqa: E402,F401
