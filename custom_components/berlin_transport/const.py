import json
import pathlib
from datetime import timedelta

_MANIFEST = json.loads(
    (pathlib.Path(__file__).parent / "manifest.json").read_text(encoding="utf-8")
)
_VERSION = _MANIFEST.get("version", "unknown")
_DOCS_URL = _MANIFEST.get(
    "documentation",
    "https://github.com/manoth-msft/home-assistant-bvg-vbb-departures",
)

DOMAIN = "berlin_transport"
SCAN_INTERVAL = timedelta(seconds=120)
FALLBACK_TIME = timedelta(minutes=15)

# Primary and secondary API endpoints
PRIM_API_ENDPOINT = "https://v6.vbb.transport.rest"
SEC_API_ENDPOINT = "https://we1external.dynv6.net:8500"  # Secondary/redundant instance
BVG_API_ENDPOINT = "https://www.bvg.de/connection-search/v1/departureBoard"
BVG_API_REFERER = "https://www.bvg.de/"

API_USER_AGENT = f"home-assistant-bvg-vbb-departures/{_VERSION} ({_DOCS_URL})"
API_MAX_RESULTS = 20
DEFAULT_DEPARTURES_DURATION = 60

# API Request timeouts (seconds)
API_REQUEST_TIMEOUT = 30  # All API requests (locations, departures, trips validation)

# Backoff configuration
BACKOFF_BASE = 2  # Exponential backoff base (2^n)
BACKOFF_MAX_SECONDS = 600  # 10 minutes maximum backoff

# Feature gates
PRIM_API_ENABLED = True  # Enable primary VBB/transport.rest API
SEC_API_ENABLED = True  # Enable secondary/redundant API endpoint
BVG_FALLBACK_ENABLED = True  # Enable BVG API as fallback when transport.rest fails

# Direction Stop-ID migration (v0.1.6)
# Toggle für Migration von Stop-Namen zu Stop-IDs
DIRECTION_ID_MIGRATION_ENABLED = True
# DEBUG-MODE: Liste von Stop-Namen die als TEXT gespeichert werden
# (leer in Produktion)
DIRECTION_DEBUG_KEEP_AS_TEXT: list[str] = []
# Automatischer Flag wenn Debug-Liste nicht leer
DIRECTION_DEBUG_MODE_ENABLED = len(DIRECTION_DEBUG_KEEP_AS_TEXT) > 0

# Cache management
CACHE_TTL_SECONDS = 7200  # 2 hours: Time-to-live for cached request variants

# Default values
DEFAULT_ICON = "mdi:clock"
DEFAULT_WALKING_TIME = 1  # minutes

CONF_DEPARTURES = "departures"
CONF_DEPARTURES_NAME = "name"
CONF_DEPARTURES_STOP_ID = "stop_id"
CONF_SELECTED_STOP = "selected_stop"
CONF_DEPARTURES_EXCLUDED_STOPS = "excluded_stops"
CONF_DEPARTURES_WALKING_TIME = "walking_time"
CONF_DEPARTURES_DIRECTION = "direction"
CONF_DEPARTURES_DURATION = "duration"
CONF_EXCLUDE_RINGBAHN_CLOCKWISE = "exclude_ringbahn_clockwise"

# Direction config flow (v0.1.6)
DIRECTION_MIGRATION_STATE = "direction_migration_state"  # "not_needed" | "completed" | "failed"
CONF_EXCLUDE_RINGBAHN_COUNTERCLOCKWISE = "exclude_ringbahn_counterclockwise"
CONF_REMOVE_BERLIN_SUFFIX = "remove_berlin_suffix"
CONF_SHOW_API_LINE_COLORS = "show_official_line_colors"
CONF_TYPE_SUBURBAN = "suburban"
CONF_TYPE_SUBWAY = "subway"
CONF_TYPE_TRAM = "tram"
CONF_TYPE_BUS = "bus"
CONF_TYPE_FERRY = "ferry"
CONF_TYPE_EXPRESS = "express"
CONF_TYPE_REGIONAL = "regional"

STOP_SUFFIX_BERLIN = "(Berlin)"

TRANSPORT_TYPE_VISUALS = {
    CONF_TYPE_SUBURBAN: {
        "code": "S",
        "icon": "mdi:subway-variant",
        "color": "#008D4F",
    },
    CONF_TYPE_SUBWAY: {
        "code": "U",
        "icon": "mdi:subway",
        "color": "#2864A6",
    },
    CONF_TYPE_TRAM: {
        "code": "M",
        "icon": "mdi:tram",
        "color": "#D82020",
    },
    CONF_TYPE_BUS: {
        "code": "BUS",
        "icon": "mdi:bus",
        "color": "#A5027D"
    },
    CONF_TYPE_FERRY: {
        "code": "F",
        "icon": "mdi:ferry",
        "color": "#0080BA"
    },
    CONF_TYPE_EXPRESS: {
        "code": "Train",
        "icon": "mdi:train",
        "color": "#4D4D4D"
    },
    CONF_TYPE_REGIONAL: {
        "code": "RE",
        "icon": "mdi:train",
        "color": "#F01414"
    }
}
