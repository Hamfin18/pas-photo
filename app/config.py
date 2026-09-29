import os

APP_ENV = os.getenv("APP_ENV", "development").lower()
IS_PRODUCTION = APP_ENV == "production"

DEFAULT_OUTPUT_WIDTH = 300
DEFAULT_OUTPUT_HEIGHT = 400
MIN_OUTPUT_SIZE = 50
MAX_OUTPUT_SIZE = 4000
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/jpg", "image/png"}
DEFAULT_BG_HEX = "#FFFFFF"

# Rate limit: POST /api/process & /api/cutout & /api/compose
RATE_LIMIT_MAX_CALLS = 10
RATE_LIMIT_PERIOD_SEC = 60

# Crop adjust bounds
MIN_ZOOM = 1.0
MAX_ZOOM = 2.5
