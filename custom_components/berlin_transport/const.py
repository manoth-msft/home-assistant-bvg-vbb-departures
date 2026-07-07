from datetime import timedelta

DOMAIN = "berlin_transport"
SCAN_INTERVAL = timedelta(seconds=120)
FALLBACK_TIME = timedelta(minutes=15)
API_ENDPOINT = "https://v6.vbb.transport.rest"
API_MAX_RESULTS = 20
DEFAULT_DEPARTURES_DURATION = 60

# Feature gates
EXTRACT_AND_STORE_DIRECTION_NAME = True  # v0.1.4.2+: Extract direction name from API for BVG fallback data collection
BVG_FALLBACK_ENABLED = False  # v0.1.5+: Enable BVG API fallback mechanism using collected direction names

# API Request timeouts (seconds)
API_REQUEST_TIMEOUT = 240  # 4 minutes

# Backoff configuration
BACKOFF_BASE = 2  # Exponential backoff base (2^n)
BACKOFF_MAX_SECONDS = 900  # 15 minutes maximum backoff

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
CONF_DEPARTURES_DIRECTION_NAME = "direction_name"  # v0.1.5: Direction name for BVG
CONF_DEPARTURES_DURATION = "duration"
CONF_EXCLUDE_RINGBAHN_CLOCKWISE = "exclude_ringbahn_clockwise"
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
