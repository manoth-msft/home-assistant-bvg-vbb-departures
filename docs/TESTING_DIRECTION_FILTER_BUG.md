# Test Case: Direction Filter Bug (0.1.4.1)

## Bug Description
When using the **direction filter** feature (optional), the sensor fails to fetch any departures and returns no data. This is a critical bug that affects all users who set a `direction_id` in their configuration.

## Affected Configuration
This bug occurs when you use the `direction` parameter in your Home Assistant configuration:

```yaml
sensor:
  - platform: berlin_transport
    stop_id: "900110001"  # S+U Schönhauser Allee
    direction_id: "900110006"  # U Eberswalder Str. (optional)
    # ↑ This causes the bug!
```

## Root Cause
The `fetch_departures()` method has a logic error:

```python
if self.direction is None:
    res = await self.fetch_directional_departure(self.direction)  # ❌ BUG: Passes None!
```

When `self.direction is None`, it should NOT fetch any departures. But the code still tries to fetch with `None` as direction, which causes the API call to fail silently.

## Step-by-Step Reproduction

### Prerequisites
- Home Assistant installed and running
- Berlin Transport integration (0.1.4.1) installed
- Access to Home Assistant UI and YAML config

### Reproduce the Bug

#### Step 1: Configure Sensor with Direction
Edit your `configuration.yaml`:

```yaml
sensor:
  - platform: berlin_transport
    name: "U2 to Alexanderplatz"
    stop_id: "900110001"        # U Schönhauser Allee (Berlin)
    direction_id: "900110012"   # Alexanderplatz (your destination)
```

**Why this config:**
- `stop_id`: Where you're traveling FROM
- `direction_id`: Where you want to GO (this filters to only show trains going to Alexanderplatz)

#### Step 2: Restart Home Assistant
- Go to **Settings** → **System** → **Restart** 
- Wait for restart to complete

#### Step 3: Check the Sensor State
- Go to **Developer Tools** → **States**
- Search for your sensor: `sensor.u2_to_alexanderplatz`

**Expected Result (if bug was fixed):**
- Sensor state shows: `Next U2 at 14:32` (next departure time)
- Attribute `departures` contains a list of upcoming trains

**Actual Result (BUG - 0.1.4.1):**
- Sensor state shows: `N/A`
- Attribute `departures`: empty list `[]`
- No data is fetched

#### Step 4: Check the Logs
- Go to **Settings** → **System** → **Logs**
- Search for `berlin_transport` or your sensor name
- Look for error messages

**You should see something like:**
```
[WARNING] API error for stop 900110001: ...
[DEBUG] Using cached departures for stop 900110001 (0 consecutive failures)
```

This indicates the API call with `direction=None` failed, causing the sensor to fall back to empty cache.

#### Step 5: Verify Without Direction Works
To confirm it's the direction filter that's broken:

Edit `configuration.yaml` and REMOVE the `direction_id`:

```yaml
sensor:
  - platform: berlin_transport
    name: "U2 All Directions"
    stop_id: "900110001"        # U Schönhauser Allee
    # direction_id removed!
```

Restart Home Assistant again.

**Expected Result:**
- Sensor now shows data: `Next U2 at 14:35`
- Departures list is populated
- **This proves the direction filter is the culprit**

## Why This is Critical

Users who want to filter departures to a specific destination will get:
- ❌ No departures displayed on dashboard
- ❌ Lovelace cards showing empty state
- ❌ Confusion: "Is the API down? Is my sensor broken?"
- ❌ No way to use the integration for their intended purpose (tracking specific train directions)

## Expected Behavior (After Fix)

With the same config:
```yaml
stop_id: "900110001"        # U Schönhauser Allee
direction_id: "900110012"   # Alexanderplatz
```

The sensor should:
1. ✅ Fetch all departures from Schönhauser Allee
2. ✅ Filter to only show trains going TOWARD Alexanderplatz
3. ✅ Display next departure: `Next U2 at 14:32`
4. ✅ Show only relevant directions in departures attribute

## Test Result

| Scenario | Status | Expected | Actual (0.1.4.1) |
|----------|--------|----------|------------------|
| No direction set | ✅ Works | Shows all departures | Shows all departures |
| Direction set | ❌ **BROKEN** | Shows filtered departures | Shows N/A (empty) |
| Direction set, check logs | ❌ **BROKEN** | Clean API calls | API fails with None direction |

## Workaround (Until 0.1.4.2)

**There is no workaround.** If you need direction filtering, you must either:
1. Wait for 0.1.4.2 patch
2. Revert to 0.1.3.x (if available)
3. Create separate sensors for different lines (without direction filtering)

## Files Modified in Fix

The fix requires changes to `custom_components/berlin_transport/sensor.py`:

```python
# Current (BROKEN):
if self.direction is None:
    res = await self.fetch_directional_departure(self.direction)  # None!

# Fixed (0.1.4.2):
if self.direction is not None:
    # Only fetch with direction if direction is explicitly set
    for direction in self.direction.split(","):
        res = await self.fetch_directional_departure(direction.strip())
```

---

**Report Date:** 2026-07-06  
**Affected Version:** 0.1.4.1  
**Fix Version:** 0.1.4.2  
**Severity:** 🔴 CRITICAL
