# Home Assistant BVG Integration - Code Review

**Date:** 2026-07-06  
**Reviewed Files:** sensor.py, config_flow.py, bvg_api.py, bvg_departure.py, departure.py, const.py

---

## Summary

The integration demonstrates solid architecture with good error handling patterns and fallback mechanisms. However, there are several critical issues related to timezone handling, potential null pointer crashes, unbounded caching, and missing input validation that could cause stability issues.

**Critical Issues:** 5  
**High Priority Issues:** 8  
**Medium Priority Issues:** 6  
**Low Priority Issues:** 5

---

## CRITICAL ISSUES

### 1. ⚠️ CRITICAL: Timezone Naive/Aware Mismatch Causes Crashes
**File:** [sensor.py](sensor.py#L215-L220)  
**Severity:** CRITICAL  
**Risk:** Runtime crashes on sensor update

**Issue:**
```python
# Line 215-220: _prune_cached_departures()
def _prune_cached_departures(self) -> None:
    self.departures = [
        departure
        for departure in self.departures
        if departure.timestamp >= datetime.now(departure.timestamp.tzinfo)  # ⚠️ CRASH RISK
    ]
```

The code uses `datetime.now(departure.timestamp.tzinfo)` but `departure.timestamp` is always UTC-aware (from `departure.py` and API responses). This comparison mixes naive and aware datetimes, causing `TypeError: can't compare offset-naive and offset-aware datetimes`.

Additionally, comparing UTC timestamps using local time semantics is incorrect.

**Fix:**
```python
def _prune_cached_departures(self) -> None:
    from datetime import datetime, timezone
    now_utc = datetime.now(timezone.utc)
    self.departures = [
        departure
        for departure in self.departures
        if departure.timestamp >= now_utc
    ]
```

---

### 2. ⚠️ CRITICAL: Inconsistent Timezone Usage Throughout Code
**File:** [sensor.py](sensor.py#L264), [sensor.py](sensor.py#L402)  
**Severity:** CRITICAL  
**Risk:** Stale data, incorrect availability, logic errors

**Issue:**
The code uses `datetime.utcnow()` (naive) in multiple places but compares against UTC-aware timestamps from departures:
- Line 264: `now_utc = datetime.utcnow()` - creates naive datetime
- Line 402: Same issue in `async_update()`
- These are then compared with timezone-aware `last_update_success` and `departure.timestamp`

This causes incorrect comparisons and logic errors with age calculations.

**Fix:**
Replace all instances of `datetime.utcnow()` with:
```python
from datetime import datetime, timezone
now_utc = datetime.now(timezone.utc)
```

Affected lines: 264, 402, and all usages in `_is_within_fallback()`, `_is_data_stale()`, `_last_updated_ago()`, `_health_status()`, `_health_details()`.

---

### 3. ⚠️ CRITICAL: Unbounded ETags Cache Memory Leak
**File:** [sensor.py](sensor.py#L575-L583)  
**Severity:** CRITICAL  
**Risk:** Memory leak over time, potential OOM crash

**Issue:**
```python
# ETags are cached indefinitely
self._etag_by_request[request_key] = response_etag
self._cached_departures_by_request[request_key] = copy.deepcopy(parsed_departures)
```

The ETag cache dictionary `_etag_by_request` and `_cached_departures_by_request` grow indefinitely. If a user configures multiple directions that are later removed from config, old ETags and cached data persist forever, consuming memory.

**Fix:**
Implement cache expiration. Add to `__init__`:
```python
self._cache_max_age = timedelta(hours=1)  # or appropriate value
```

Add cache pruning:
```python
def _prune_expired_caches(self) -> None:
    """Remove expired ETags and cached departures."""
    if not self.last_update_success:
        return
    max_age = self.last_update_success + self._cache_max_age
    expired_keys = [k for k, v in self._etag_by_request.items() 
                    if len(v) > 10]  # or time-based logic
    for key in expired_keys:
        self._etag_by_request.pop(key, None)
        self._cached_departures_by_request.pop(key, None)
```

Or alternatively, limit cache size:
```python
MAX_CACHE_ENTRIES = 50
if len(self._etag_by_request) > MAX_CACHE_ENTRIES:
    # Remove oldest entries
```

---

### 4. ⚠️ CRITICAL: Missing Input Validation in Config Flow
**File:** [config_flow.py](config_flow.py#L56-L70)  
**Severity:** CRITICAL  
**Risk:** Invalid configuration accepted, sensor creation fails

**Issue:**
```python
async def get_stop_id(session: aiohttp.ClientSession, name: str) -> Optional[list[dict[str, Any]]]:
    # No validation of 'name' parameter - accepts empty strings, None, etc.
    # No timeout handling for 240-second timeout
    try:
        async with async_timeout.timeout(240):  # Hard-coded timeout
```

The config flow:
1. Never validates that `name` (stop search) is non-empty
2. Never validates that the API returned a valid list of stops
3. Silently accepts empty results without warning user
4. Has a 240-second timeout that will block the UI

**Fix:**
```python
async def get_stop_id(session: aiohttp.ClientSession, name: str) -> Optional[list[dict[str, Any]]]:
    # Validate input
    if not name or not name.strip():
        _LOGGER.warning("Stop search query is empty")
        return []
    
    name = name.strip()
    
    try:
        async with async_timeout.timeout(10):  # Reduce timeout for UI responsiveness
            response = await session.get(...)
            # ... rest of code
```

And in `async_step_stop()`:
```python
if not self.data[CONF_FOUND_STOPS]:
    return self.async_show_form(
        step_id="user",
        data_schema=NAME_SCHEMA,
        errors={"base": "no_stops_found"},
        description_placeholders={"name": user_input[CONF_SEARCH]},
    )
```

---

### 5. ⚠️ CRITICAL: Direction Handling Logic Error
**File:** [sensor.py](sensor.py#L601-L613)  
**Severity:** CRITICAL  
**Risk:** API requests always fail when direction is None

**Issue:**
```python
# Lines 601-613
if self.direction is None:
    res = await self.fetch_directional_departure(self.direction)  # ⚠️ ALWAYS SENDS None
    if res is None:
        return None
    departures += res
else:
    for direction in self.direction.split(","):
        res = await self.fetch_directional_departure(direction.strip())
        if res is None:
            return None
        departures += res
```

The logic is inverted: when `self.direction is None`, it fetches with `None`, which is correct. But the variable name suggests it should be checking if direction is provided. However, looking at the logic, it seems the intent is:
- If NO direction specified → fetch all directions (pass None)
- If direction(s) specified → fetch each one

But the code has a critical flaw: it **returns None** if ANY directional fetch fails. This means a single-direction API error fails the entire sensor update, instead of being resilient.

**Fix:**
```python
async def fetch_departures(self) -> list[Departure] | None:
    departures = []
    directions_to_fetch = [None] if self.direction is None else [d.strip() for d in self.direction.split(",")]
    
    for direction in directions_to_fetch:
        res = await self.fetch_directional_departure(direction)
        if res is None:
            # Log warning but continue with other directions
            _LOGGER.warning(
                "Failed to fetch departures for stop %s (direction=%s), continuing with other directions",
                self.stop_id,
                direction,
            )
            continue  # ⚠️ Changed from return None
        departures += res
    
    if not departures:
        _LOGGER.warning("No departures found for any direction for stop %s", self.stop_id)
        return None
    
    # Continue with dedup/filter steps...
```

---

## HIGH PRIORITY ISSUES

### 6. 🔴 Missing Timeout Handling in Config Flow
**File:** [config_flow.py](config_flow.py#L57-L80)  
**Severity:** HIGH  
**Risk:** UI freezes for 240 seconds on network issues

**Issue:**
The stop search has a 240-second timeout that blocks the config flow UI:
```python
async with async_timeout.timeout(240):
    response = await session.get(...)
```

This is excessive for a user-facing operation. Users will think the UI is frozen.

**Fix:**
Reduce timeout and handle gracefully:
```python
try:
    async with async_timeout.timeout(10):  # 10 seconds max for UI
        response = await session.get(...)
except asyncio.TimeoutError:
    _LOGGER.warning("Stop search timed out after 10s for query '%s'", name)
    return []
```

---

### 7. 🔴 Hard-Coded 240-Second Timeout Everywhere
**File:** [sensor.py](sensor.py#L538), [sensor.py](sensor.py#L470), [bvg_api.py](bvg_api.py#L47)  
**Severity:** HIGH  
**Risk:** Excessive timeouts cause slow failure recovery

**Issue:**
Multiple places use `async_timeout.timeout(240)` (4 minutes!). This is far too long for an HTTP request and delays failure detection.

**Fix:**
Create a constant and use reasonable timeouts:
```python
# In const.py
API_TIMEOUT_SECONDS = 10  # 10 seconds for normal requests
BVG_TIMEOUT_SECONDS = 10
```

Then use:
```python
async with async_timeout.timeout(API_TIMEOUT_SECONDS):
    response = await session.get(...)
```

---

### 8. 🔴 Missing Validation for Configuration Values
**File:** [sensor.py](sensor.py#L120-L140)  
**Severity:** HIGH  
**Risk:** Invalid config crashes sensor or produces wrong behavior

**Issue:**
Config values are not validated:
```python
self.walking_time: int = config.get(CONF_DEPARTURES_WALKING_TIME) or 1
```

Possible issues:
- `walking_time` could be negative (would fetch past departures)
- `stop_id` could be 0 or negative (invalid ID)
- `duration` is hard-coded to 60 but never validated

**Fix:**
Add validation in `__init__`:
```python
self.walking_time: int = config.get(CONF_DEPARTURES_WALKING_TIME) or 1
if self.walking_time <= 0 or self.walking_time > 120:
    _LOGGER.warning("Invalid walking_time %s, using default 1", self.walking_time)
    self.walking_time = 1

if self.stop_id <= 0:
    _LOGGER.error("Invalid stop_id %s", self.stop_id)
    self._attr_available = False
    self.departures = []
```

---

### 9. 🔴 Response Type Validation Too Lenient
**File:** [bvg_departure.py](bvg_departure.py#L66-L80)  
**Severity:** HIGH  
**Risk:** Silent failures on API schema changes

**Issue:**
```python
# Lines 66-80
if isinstance(response, dict):
    elements = response.get("elements", [])
elif isinstance(response, list):
    elements = []
    for item in response:
        if isinstance(item, dict) and "elements" in item:
            elements.extend(item["elements"])
else:
    _LOGGER.warning("BVG response has unexpected type: %s", type(response))
    return departures  # ⚠️ Returns empty list silently
```

The code handles dict and list responses but if API returns something else (e.g., string error), it silently fails. No validation that required fields exist.

**Fix:**
```python
def parse_bvg_departures(response: dict[str, Any] | list[Any]) -> list[Departure]:
    """Parse BVG departureBoard API response into Departure objects."""
    departures: list[Departure] = []

    # Validate response type and structure
    if not isinstance(response, (dict, list)):
        _LOGGER.error("BVG response has unexpected type: %s (expected dict or list)", type(response))
        return departures

    # Extract elements
    elements = []
    if isinstance(response, dict):
        if "elements" not in response:
            _LOGGER.warning("BVG response dict missing 'elements' key: %s", response.keys())
            return departures
        elements = response.get("elements", [])
        if not isinstance(elements, list):
            _LOGGER.error("BVG response 'elements' is not a list: %s", type(elements))
            return departures
    
    # ... rest of parsing
```

---

### 10. 🔴 Backoff Logic May Trigger Immediately
**File:** [sensor.py](sensor.py#L343-L356)  
**Severity:** HIGH  
**Risk:** Excessive backoff on transient errors

**Issue:**
```python
# Line 348-350
backoff_seconds = min(
    900,
    SCAN_INTERVAL.total_seconds() * (2 ** (self._consecutive_failures - 1))
)
```

With `SCAN_INTERVAL = 120` seconds:
- 1st failure: 120 * 2^0 = 120 seconds
- 2nd failure: 120 * 2^1 = 240 seconds
- 3rd failure: 120 * 2^2 = 480 seconds
- 4th failure: 120 * 2^3 = 960 seconds (capped at 900)

The first backoff is 120 seconds, which seems excessive for transient errors. Most HTTP transients recover in seconds.

**Fix:**
```python
# Add to const.py
BACKOFF_BASE_SECONDS = 10  # Start with 10 seconds
BACKOFF_MAX_SECONDS = 600  # Cap at 10 minutes

# In sensor.py
backoff_seconds = min(
    BACKOFF_MAX_SECONDS,
    BACKOFF_BASE_SECONDS * (2 ** (self._consecutive_failures - 1)),
)
```

---

### 11. 🔴 No Rate Limit Handling in Config Flow
**File:** [config_flow.py](config_flow.py#L76-L82)  
**Severity:** HIGH  
**Risk:** Config flow can hammer API with repeated searches

**Issue:**
```python
except aiohttp.ClientResponseError as ex:
    if ex.status == 429:
        retry_after = ex.headers.get("Retry-After") if ex.headers else None
        _LOGGER.warning(...)
    # ⚠️ No backoff - user can immediately retry and get rate limited again
```

When rate limited (429), the code logs but doesn't inform the user or prevent immediate retry.

**Fix:**
```python
async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
    if user_input is None:
        return self.async_show_form(...)
    
    if not user_input[CONF_SEARCH].strip():
        return self.async_show_form(
            step_id="user",
            data_schema=NAME_SCHEMA,
            errors={"base": "empty_search"},
        )
    
    session = async_get_clientsession(self.hass)
    self.data[CONF_FOUND_STOPS] = await get_stop_id(session, user_input[CONF_SEARCH])
    
    if not self.data[CONF_FOUND_STOPS]:
        return self.async_show_form(
            step_id="user",
            data_schema=NAME_SCHEMA,
            errors={"base": "no_stops_found"},
            description_placeholders={"search": user_input[CONF_SEARCH]},
        )
    
    return await self.async_step_stop()
```

---

### 12. 🔴 Logging Uses F-Strings Instead of % Formatting
**File:** Multiple files  
**Severity:** HIGH (code quality)  
**Risk:** Structured logging breaks, performance impact

**Issue:**
Home Assistant uses structured logging. F-strings bypass logging formatting:
```python
# config_flow.py, line 159
_LOGGER.debug(f"OK: found stops for {user_input[CONF_SEARCH]}: {self.data[CONF_FOUND_STOPS]}")

# sensor.py, line 599
_LOGGER.debug(f"OK: selected stop {selected_stop[0]} [{selected_stop[1]}]")
```

This breaks structured logging and prevents filtering/redaction. Should use:
```python
_LOGGER.debug("OK: found stops for %s: %s", user_input[CONF_SEARCH], self.data[CONF_FOUND_STOPS])
```

**Fix:**
Replace all f-string logging with `%s` formatting:
```
grep -r "f\".*_LOGGER\|f'.*_LOGGER" custom_components/berlin_transport/
```

---

## MEDIUM PRIORITY ISSUES

### 13. 📋 No Input Sanitization for Direction/Excluded Stops
**File:** [sensor.py](sensor.py#L526-L538)  
**Severity:** MEDIUM  
**Risk:** Malformed API parameters on bad input

**Issue:**
```python
if self.excluded_stops is None:
    excluded_stops = []
else:
    excluded_stops = [
        stop.strip()
        for stop in self.excluded_stops.split(",")
        if stop.strip()
    ]
```

If `excluded_stops` is an empty string or contains only whitespace, it silently becomes `[]`. But if the config has a trailing comma or unusual format, the parsing may be unpredictable.

**Fix:**
```python
def _parse_excluded_stops(self) -> list[str]:
    """Parse comma-separated excluded stop IDs, validating format."""
    if not self.excluded_stops:
        return []
    
    excluded = [s.strip() for s in self.excluded_stops.split(",")]
    excluded = [s for s in excluded if s and s.isdigit()]  # Only valid IDs
    
    if len(excluded) != len(self.excluded_stops.split(",")):
        invalid = [s.strip() for s in self.excluded_stops.split(",") if s.strip() and not s.strip().isdigit()]
        _LOGGER.warning(
            "Invalid stop IDs in excluded_stops: %s. Using only valid IDs: %s",
            invalid, excluded
        )
    
    return excluded
```

---

### 14. 📋 Copy.deepcopy() Inefficient for Large Departure Objects
**File:** [sensor.py](sensor.py#L564), [sensor.py](sensor.py#L576)  
**Severity:** MEDIUM  
**Risk:** Performance issue with large departure lists

**Issue:**
```python
if cached_departures is not None:
    return copy.deepcopy(cached_departures)  # ⚠️ Expensive for large lists

# Later:
self._cached_departures_by_request[request_key] = copy.deepcopy(parsed_departures)
```

`deepcopy()` is expensive and slow. Since `Departure` objects are dataclasses and immutable, this is unnecessary.

**Fix:**
Remove deepcopy - Departure objects are immutable dataclasses:
```python
if cached_departures is not None:
    return cached_departures  # Safe - dataclass is immutable

# Or if mutation is possible:
self._cached_departures_by_request[request_key] = parsed_departures.copy()  # Shallow copy
```

---

### 15. 📋 No Logging of API Response Size/Details
**File:** [sensor.py](sensor.py#L588)  
**Severity:** MEDIUM  
**Risk:** Difficult to debug performance issues

**Issue:**
```python
_LOGGER.debug(
    "OK: departures response for stop %s (status=%s)",
    self.stop_id,
    response.status,
)
```

Missing information:
- How many departures were returned?
- How many were filtered?
- Response time?

**Fix:**
```python
_LOGGER.debug(
    "OK: departures response for stop %s (status=%s, raw_count=%s, filtered_count=%s)",
    self.stop_id,
    response.status,
    len(departures_data),
    len(parsed_departures),
)
```

---

### 16. 📋 Entity Attributes Not Properly Sorted
**File:** [sensor.py](sensor.py#L260)  
**Severity:** MEDIUM  
**Risk:** Inconsistent UI presentation

**Issue:**
The `extra_state_attributes` dict is not consistent in ordering. Some integrations prefer alphabetical ordering for attribute consistency.

**Fix:**
```python
@property
def extra_state_attributes(self):
    now_utc = datetime.now(timezone.utc)
    self._prune_cached_departures()
    cache_age_seconds = None
    if self.last_update_success:
        cache_age_seconds = int((now_utc - self.last_update_success).total_seconds())

    # Define attributes in consistent order
    attributes = {
        # Operational attributes
        "health_status": self._health_status(now_utc),
        "health_details": self._health_details(now_utc),
        "data_source": self._data_source,
        "data_is_stale": self._is_data_stale(now_utc),
        
        # Timing attributes
        "last_update_success": self.last_update_success,
        "last_updated": self.last_update_success,
        "last_updated_ago": self._last_updated_ago(now_utc),
        "cache_age_seconds": cache_age_seconds,
        "backoff_until": self._next_retry_at,
        
        # Data attributes
        "departures": [
            departure.to_dict(self.show_api_line_colors, self.walking_time)
            for departure in self.departures or []
        ],
        "consecutive_failures": self._consecutive_failures,
    }
    
    return dict(sorted(attributes.items()))
```

---

### 17. 📋 Missing Documentation on Config Parameters
**File:** [config_flow.py](config_flow.py#L41-L50)  
**Severity:** MEDIUM  
**Risk:** User confusion, misconfiguration

**Issue:**
No descriptions of what parameters mean:
```python
DATA_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_DEPARTURES_DIRECTION): cv.string,  # ⚠️ What format?
        vol.Optional(CONF_DEPARTURES_EXCLUDED_STOPS): cv.string,  # ⚠️ Comma-separated IDs?
        vol.Optional(CONF_DEPARTURES_WALKING_TIME, default=1): cv.positive_int,  # ⚠️ Minutes? Seconds?
        # ...
    }
)
```

**Fix:**
Add descriptions via `selector` objects:
```python
from homeassistant.helpers import selector

DATA_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_DEPARTURES_DIRECTION): cv.string,
        vol.Optional(CONF_DEPARTURES_EXCLUDED_STOPS): cv.string,
        vol.Optional(CONF_DEPARTURES_WALKING_TIME, default=1): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1, max=120, mode=selector.NumberSelectorMode.SLIDER,
                unit_of_measurement="minutes"
            )
        ),
        # ...
    }
)
```

---

## LOW PRIORITY ISSUES

### 18. 📝 Type Hints Incomplete
**File:** Multiple files  
**Severity:** LOW  
**Risk:** MyPy validation disabled

**Issue:**
The file header has:
```python
# mypy: disable-error-code="attr-defined,call-arg"
```

This disables type checking. Type hints should be complete:
```python
async def fetch_departures(self) -> list[Departure] | None:
    # Missing return type annotation on internal method
    departures = []  # Type should be explicit: list[Departure]
```

**Fix:**
- Remove mypy disable comments gradually
- Add explicit type hints for all variables
- Use `list[Departure]` instead of bare `departures`

---

### 19. 📝 Inconsistent Error Handling Pattern
**File:** [config_flow.py](config_flow.py#L94-L108)  
**Severity:** LOW  
**Risk:** Code maintainability

**Issue:**
Multiple except blocks with similar error handling:
```python
except aiohttp.ClientResponseError as ex:
    # Handle
except aiohttp.ClientConnectorError as ex:
    # Handle
except aiohttp.ServerDisconnectedError as ex:
    # Handle
except aiohttp.ClientError as ex:
    # Handle
```

This is verbose and aiohttp.ClientError already covers most cases.

**Fix:**
```python
except aiohttp.ClientResponseError as ex:
    # Handle specific case
except aiohttp.ClientError as ex:
    # Handles ClientConnectorError, ServerDisconnectedError, etc.
except TimeoutError as ex:
    # Handle separately
```

---

### 20. 📝 Constants Could Be More Descriptive
**File:** [const.py](const.py)  
**Severity:** LOW  
**Risk:** Maintenance difficulty

**Issue:**
Magic numbers without explanation:
```python
SCAN_INTERVAL = timedelta(seconds=120)  # ⚠️ Why 120?
FALLBACK_TIME = timedelta(minutes=15)  # ⚠️ Why 15?
API_MAX_RESULTS = 20  # ⚠️ Why 20?
```

**Fix:**
Add comments:
```python
# Update sensor state every 2 minutes (balance freshness vs API load)
SCAN_INTERVAL = timedelta(seconds=120)

# Cache departures for 15 minutes in fallback mode
# After this, data is marked stale but still available if API fails
FALLBACK_TIME = timedelta(minutes=15)

# Maximum departures to fetch per API request
# BVG API also uses 30 as practical max
API_MAX_RESULTS = 20
```

---

## SUMMARY TABLE

| ID | Severity | Issue | File | Impact |
|---|----------|-------|------|--------|
| 1 | 🔴 CRITICAL | Timezone naive/aware crash | sensor.py:215 | Runtime crash |
| 2 | 🔴 CRITICAL | Inconsistent UTC usage | sensor.py:264 | Logic errors |
| 3 | 🔴 CRITICAL | Unbounded cache memory leak | sensor.py:575 | OOM crash |
| 4 | 🔴 CRITICAL | Missing config validation | config_flow.py:56 | Invalid configs |
| 5 | 🔴 CRITICAL | Direction logic error | sensor.py:601 | API always fails |
| 6 | 🔴 HIGH | Missing timeout handling | config_flow.py:57 | UI freezes |
| 7 | 🔴 HIGH | Hard-coded 240s timeout | sensor.py:538 | Slow failure |
| 8 | 🔴 HIGH | No config value validation | sensor.py:120 | Crashes/wrong behavior |
| 9 | 🔴 HIGH | Lenient response validation | bvg_departure.py:66 | Silent failures |
| 10 | 🔴 HIGH | Excessive backoff | sensor.py:348 | Over-backoff |
| 11 | 🔴 HIGH | No rate limit handling | config_flow.py:76 | Hammering API |
| 12 | 🔴 HIGH | F-string logging | Multiple | Breaks structure |
| 13 | 🟡 MEDIUM | No input sanitization | sensor.py:526 | Bad parameters |
| 14 | 🟡 MEDIUM | Expensive deepcopy | sensor.py:564 | Performance |
| 15 | 🟡 MEDIUM | Missing log details | sensor.py:588 | Hard to debug |
| 16 | 🟡 MEDIUM | Unsorted attributes | sensor.py:260 | UI inconsistency |
| 17 | 🟡 MEDIUM | No parameter docs | config_flow.py:41 | User confusion |
| 18 | 🟠 LOW | Incomplete type hints | Multiple | Maintenance |
| 19 | 🟠 LOW | Inconsistent error handling | config_flow.py:94 | Maintainability |
| 20 | 🟠 LOW | Missing constant comments | const.py | Documentation |

---

## Recommended Fix Priority

**Phase 1 (Address immediately):**
1. Issue #1 (Timezone crash) - prevents sensor operation
2. Issue #2 (UTC usage) - causes logic errors
3. Issue #5 (Direction logic) - prevents API calls from working
4. Issue #3 (Memory leak) - causes crashes over time
5. Issue #4 (Config validation) - allows invalid configs

**Phase 2 (High impact):**
6. Issue #6 (Timeout handling)
7. Issue #7 (Timeout constants)
8. Issue #8 (Config validation)
9. Issue #12 (Logging format)

**Phase 3 (Quality):**
10. Remaining HIGH and MEDIUM issues

---

## Testing Recommendations

After fixes, test these scenarios:
1. **Timezone handling:** Run sensor in multiple timezones, verify timestamp comparisons work
2. **Crash recovery:** Stop API service, verify backoff works and recovers gracefully
3. **Memory usage:** Monitor sensor for 24+ hours with multiple config entries
4. **Config flow:** Test with invalid/empty stops, rate limiting (429 response)
5. **Direction filtering:** Test single direction, multiple directions, no direction specified
6. **Edge cases:** Test with 0 departures, 100+ departures, cancelled services
