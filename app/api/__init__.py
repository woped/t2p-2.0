from flask import Blueprint
import logging

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__)
logger.debug("API blueprint initialized", extra={"blueprint": "api"})

from app.api import routes