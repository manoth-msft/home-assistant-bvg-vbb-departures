import re
from dataclasses import dataclass, field
from datetime import datetime

from .const import TRANSPORT_TYPE_VISUALS, DEFAULT_ICON

HEX_COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{3,8}$")


def _str_or_none(value) -> str | None:
    """Return API text values as plain strings (or None)."""
    return None if value is None else str(value)


def _hex_color_or_none(value) -> str | None:
    """Only accept CSS hex colors from the API, everything else is dropped."""
    if isinstance(value, str) and HEX_COLOR_PATTERN.match(value):
        return value
    return None


def _int_or_none(value) -> int | None:
    """Return the delay in seconds as int (or None if missing/invalid)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    return None


@dataclass
class Departure:
    """Departure dataclass to store data from API:
    https://v6.vbb.transport.rest/api.html#get-stopsiddepartures"""

    trip_id: str
    line_name: str
    line_type: str
    timestamp: datetime
    time: str
    direction: str | None = None
    icon: str | None = None
    bg_color: str | None = None
    fallback_color: str | None = None
    location: tuple[float, float] | None = None
    cancelled: bool = False
    delay: int | None = None
    warnings: list[dict[str, str]] | None = None
    # Internal cache for hash computation (not part of equality/repr)
    _hash_cache: int | None = field(default=None, init=False, repr=False, compare=False)

    @classmethod
    def from_dict(cls, source):
        line_type = source.get("line", {}).get("product")
        line_visuals = TRANSPORT_TYPE_VISUALS.get(line_type) or {}
        timestamp = datetime.fromisoformat(
            source.get("when") or source.get("plannedWhen")
        )
        return cls(
            trip_id=source["tripId"],
            line_name=_str_or_none(source.get("line", {}).get("name")),
            line_type=line_type,
            timestamp=timestamp,
            time=timestamp.strftime("%H:%M"),
            direction=_str_or_none(source.get("direction")),
            icon=line_visuals.get("icon") or DEFAULT_ICON,
            bg_color=_hex_color_or_none(
                (source.get("line", {}).get("color") or {}).get("bg")
            ),
            fallback_color=line_visuals.get("color"),
            location=[
                source.get("currentTripPosition", {}).get("latitude") or 0.0,
                source.get("currentTripPosition", {}).get("longitude") or 0.0,
            ],
            cancelled=bool(source.get("cancelled", False)),
            delay=_int_or_none(source.get("delay")),
            warnings=[
                {"id": remark.get("id"), "summary": remark.get("summary")}
                for remark in source.get("remarks", [])
                if (
                    remark.get("type") == "warning"
                    and remark.get("summary")
                    and remark.get("id")
                )
            ]
            or None,
        )

    def to_dict(self, show_api_line_colors: bool, walking_time: int):
        color = self.fallback_color
        if show_api_line_colors and self.bg_color is not None:
            color = self.bg_color
        return {
            "line_name": self.line_name,
            "line_type": self.line_type,
            "time": self.time,
            "timestamp": self.timestamp,
            "direction": self.direction,
            "color": color,
            "cancelled": self.cancelled,
            "delay": self.delay,
            "warnings": self.warnings,
            "walking_time": walking_time,
        }

    # Make the object hashable and use all infos that can be displayed in the
    # frontend
    def __hash__(self) -> int:
        # Return cached hash if available (Departure objects are effectively immutable)
        if self._hash_cache is not None:
            return self._hash_cache

        # Compute hash once from essential uniqueness fields
        # trip_id + timestamp are unique per departure, so use simplified hash
        # instead of expensive to_dict() + sort operations
        self._hash_cache = hash((
            self.trip_id,
            self.timestamp,
            self.line_name,
            self.direction,
        ))
        return self._hash_cache
