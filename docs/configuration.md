# Configuration Guide

## Integration Configuration

This page explains all configuration options for the BVG/VBB Departures integration. Most options are optional and only needed for advanced use cases.

### 📍 Direction

Filter departures to show only trains heading to a specific destination.

**What it does:** Instead of showing all departures from your stop, you'll only see trains that go to (or pass through) your specified destination.

**Example:** If you select "S Treptower Park" but only want to see trains going to "S+U Neukölln", you can filter by the S+U Neukölln direction.

**How to use:**
- Provide the `stop_id` of your destination (or any stop along the intended route)
- For multiple directions, use comma-separated values: `900078201,900190001`

**When to use this:** 
- You're at a station with multiple lines or directions
- You only care about trains heading in one direction

**Finding the stop_id:** See [FAQ: How do I find my stop_id?](./faq.md#q-how-do-i-find-my-stop_id)

---

### 🚫 Exclude Stops

Hide departures from nearby stops that you don't want to see.

**What it does:** Some stations have multiple stop points (e.g., bus stops, tram stops at the same location). This option lets you exclude specific ones.

**Example:** 
- You monitor "S Treptower Park" (the main station)
- But there's also a bus stop at the same location (S Treptower Park Bus)
- You can exclude the bus stop by providing its `stop_id`

**How to use:**
- Find the `stop_id` of the stops you want to exclude
- Provide a comma-separated list: `900190702,900190703`

**When to use this:** 
- Your primary stop has multiple nearby stops you want to hide

---

### ⏱️ Duration

Time window for fetching departures (currently fixed at 60 minutes).

**What it does:** The integration fetches all departures happening within the next 60 minutes.

**Current state:** This is hardcoded and not user-configurable. We found that 60 minutes covers most commuting scenarios while keeping API load reasonable.

**Why not user-configurable?** 
- The API has rate limits (100 requests/minute)
- 60 minutes is a sensible default for most use cases
- Shorter windows = more frequent updates needed; longer windows = excessive API data

---

### 🚶 Walking Time

How long it takes you to walk to the stop (in minutes).

**What it does:** The integration hides departures that leave before you can realistically reach the stop.

**Example:**
- You configured 10 minutes walking time
- A train leaves in 8 minutes
- It won't be shown (you can't reach it in time)

**How to use:**
- Enter the time in minutes: `10`, `15`, etc.

**When to use this:** 
- You want to avoid seeing departures that are unreachable
- Gives you a more realistic view of usable departures

---

### 🎨 Enable Official VBB Line Colors

Use the official VBB color scheme for transport lines instead of the default colors.

**What it does:** Changes the background colors of line numbers to match the official VBB design.

**When to use this:** 
- You prefer the official look
- You're familiar with VBB's color coding

**Default:** Disabled (uses a clean predefined color scheme)

---

### ⟳⟲ Hide Ringbahn Direction

Hide Ringbahn trains going clockwise (⟳) or counter-clockwise (⟲).

**What it does:** The Ringbahn is Berlin's circular train line. You can hide one direction to reduce clutter.

**Example:**
- You only care about trains going counter-clockwise (⟲)
- Enable "Hide Ringbahn ⟳" to hide the clockwise direction

**When to use this:** 
- You only need one Ringbahn direction
- You want a cleaner list of departures

---

### 🏷️ Remove (Berlin) Suffix

Strip the "(Berlin)" suffix from station names.

**What it does:** 
- With suffix: `S+U Alexanderplatz Bhf (Berlin)`
- Without suffix: `S+U Alexanderplatz Bhf`

**When to use this:** 
- You prefer cleaner, shorter station names

---

### 🚌 Transport Options

Choose which types of transport to show or hide.

**Available options:**
- **Suburban** (S-Bahn)
- **Subway** (U-Bahn)
- **Tram** (Straßenbahn)
- **Bus**
- **Ferry** (Fähre)
- **Express** (Express-Busse)
- **Regional** (Regionalbahn)

**Default:** All enabled

**When to use this:** 
- You only care about certain transport types
- You want to hide buses, for example, if you only use trains

---

## Dashboard Card Configuration

The dashboard card has separate configuration options for display:

### 📋 Show Cancelled Departures
Display cancelled trains (shown with strikethrough). Default: enabled.

### ⏱️ Show Delay
Display reported delays next to departure times. Default: enabled.

### 🕐 Show Absolute Time
Show the exact scheduled departure time. Default: enabled.

### ⏳ Show Relative Time
Show countdown (e.g., "in 5 minutes"). Default: enabled.

### 🚶 Subtract Walking Time from Relative Time
Adjust the countdown to account for your walking time.

**Example:**
- Train leaves in 15 minutes
- You configured 10 minutes walking time
- Display shows: "Leave in 5 minutes" (15 - 10)

Default: disabled.

---

## Common Configuration Scenarios

### Scenario 1: Commute to Work (Single Direction)
You take the S1 from S Treptower Park to S+U Neukölln every weekday.

**Configuration:**
- Stop: `S Treptower Park`
- Direction: `900078201` (S+U Neukölln)
- Walking time: `10` minutes
- Transport types: Only **Suburban** enabled
- Show delay: enabled
- Show relative time: enabled

---

### Scenario 2: Picking Up Kids from School
The school is near Alexanderplatz. You'll use any available transport.

**Configuration:**
- Stop: `S+U Alexanderplatz Bhf`
- Walking time: `15` minutes
- Transport types: All enabled (multiple options)
- Show absolute time: enabled
- Remove (Berlin) suffix: enabled

---

### Scenario 3: Flexible Transportation (Multiple Destinations)
You want to see all options but exclude a specific nearby stop.

**Configuration:**
- Stop: `Friedrichstraße`
- Exclude stops: `900100045` (if there's a bus stop you don't need)
- Transport types: All enabled
- Walking time: `5` minutes
- Hide Ringbahn ⟳: enabled (only care about ⟲)

---

## Updating Configuration

To change configuration options after setup:

1. Go to **Settings > Devices & Services**
2. Find the **BVG/VBB Departures** integration
3. Click the three dots next to your sensor
4. Select **Delete**
5. Add the integration again with updated settings

The sensor will keep the same ID, so your dashboards don't need updating.
