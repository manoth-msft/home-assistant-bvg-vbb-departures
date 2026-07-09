# Frequently Asked Questions (FAQ)

## Configuration & Setup

### Q: How do I find my stop_id?

The primary stop you select will be resolved automatically by the integration.  
You only need to look up `stop_id` values if you want to use advanced configuration options such as **Direction** or **Excluded stops**.

To find a `stop_id`, you can query the VBB API. Open the link below in a new window and replace `alexanderplatz` with the name of your stop. Partial matches are supported.

**https://v6.vbb.transport.rest/locations?results=1&query=alexanderplatz**

The API will return a response similar to:

```json
[
  {
    "type": "stop",
    "id": "900100003",
    "name": "S+U Alexanderplatz Bhf (Berlin)",
    "location": {
      "type": "location",
      "id": "900100003",
      "latitude": 52.521508,
      "longitude": 13.411267
    },
    "products": {
      "suburban": true,
      "subway": true,
      "tram": true,
      "bus": true,
      "ferry": false,
      "express": false,
      "regional": true
    },
    "stationDHID": "de:11000:900100003"
  }
]
```

The first `"id"` field contains the required `stop_id` — here: **900100003**.

---

### Q: How do I set up direction filtering? (v0.1.6+)

Starting with v0.1.6, direction filtering is now configured through a dedicated config flow UI instead of manual text entry.

**Setup process:**
1. During initial setup, after selecting your stop, you'll be prompted: *"Do you want to filter departures by a specific direction?"*
2. Enter a station name (e.g., "Zwickauer Damm", "Adlershof"). Partial names are supported.
3. If multiple stations match your input, you'll see a dropdown to select the correct one.
4. The integration automatically validates that the station exists on your departures route.
5. If validation fails, you'll see a warning but can choose to proceed anyway.

**No need to know Stop-IDs anymore!** The integration handles the lookup and conversion automatically.

**What changed from v0.1.5?**
- **Old (v0.1.5)**: You had to find numeric Stop-IDs and configure them as text in YAML.
- **New (v0.1.6)**: Just type the station name in the config flow. The integration finds the Stop-ID for you.
- **Auto-migration**: If you have an old config with a Stop-Name in the direction field, it's automatically converted to a Stop-ID on startup.

---

### Q: I see a warning "Direction stop not found on trips". What does this mean?

Starting with v0.1.6, the integration validates that your direction station exists on the departures route.

**If you see this warning:**
- It means the station you selected isn't expected on the route during the next 7 days (based on today's schedule).
- This can happen if:
  - The station is served on some lines but not others
  - The station's service has changed
  - There's a temporary service disruption
  
**What to do:**
- The warning is informational only — your sensor will still work fine and fetch departures.
- The integration doesn't block the configuration, so you can ignore the warning.
- If the warning persists, verify that the station name matches exactly what you intended.

---

### Q: How can I change configuration options later?

Go to **Settings > Devices & Services**, select the **BVG/VBB Departures** integration, and click on the three dots next to the entity you want to update. Delete the entry.

Then choose **Add Integration** and re-add the stop with the adjusted configuration.

The new entity will receive the same ID as the previous one, so your dashboards do not need to be updated.

---

### Q: Stop search shows an error during configuration. What should I do?

When searching for a stop, you might see errors like:
- **"Stop search failed: API rate limited..."**
- **"Stop search failed: API is slow or unreachable..."**
- **"Stop search failed: Cannot connect to API server..."**

Or you might see:
- **"No stops found for '{search_query}'. Try a different or shorter name."**

**Why this happens:**
- **API errors**: The VBB/transport.rest API has rate limits (100 requests/minute) and occasionally experiences outages or slowness.
- **No stops found**: Your search term doesn't match any known stop. Partial names are supported.

**Solution:**
- **For API errors**: Wait a few minutes and try again. The integration will show you the specific error type (rate limit, timeout, unreachable), so you know what's happening. Once the API recovers, your configuration will succeed.
- **For "no stops found"**: Try a different or shorter search term. For example, search for "Rudow" instead of "Rudow Station", or "Alexanderplatz" instead of "S+U Alexanderplatz". Partial matches are supported.

---

### Q: What happens if the primary API fails?

The integration uses a **dual-API failover system** for reliability:

1. **Primary endpoint**: `v6.vbb.transport.rest` (official VBB API)
2. **Secondary endpoint**: Custom redundant instance (for fallback)
3. **BVG fallback**: If both primary and secondary fail, the integration falls back to BVG's API with backoff

**Behavior:**
- Both primary and secondary endpoints are tried immediately in sequence with no delay
- If both fail, the integration applies exponential backoff (max 10 minutes) and activates BVG fallback
- Your last successful departure data is kept visible on the dashboard during outages
- The sensor's `health_status` attribute shows whether you're using primary, secondary, or fallback data

This means you get maximum uptime even when one API is down or slow.

---

### Q: What data source does this integration use?

The integration uses the **VBB Public API** to fetch all transport information.

- **Primary API docs:** [https://v6.vbb.transport.rest/api.html](https://v6.vbb.transport.rest/api.html)  
- **Rate limit:** 100 requests per minute (per endpoint)
- **Data format:** [HAFAS](https://github.com/public-transport/hafas-client)

---

### Q: How often does the integration update?

The integration updates every **120 seconds** (2 minutes). It makes a separate request for each stop.

This is usually sufficient, but adding dozens of stops is not recommended to avoid hitting the rate limit.

---

### Q: What entities are created by the integration?

For each stop, the integration creates **one entity**. It stores the upcoming departures in `attributes.departures`. 

The entity state itself is mainly for human-readable display of the next departure.

---

### Q: What happens if the VBB API returns errors?

If the API fails (for example with 502/503 or timeout errors), the integration keeps showing the last successful departures instead of going blank.

The sensor marks these values as stale (`data_is_stale: true`) and reports the current state via `health_status` (values: `ok`, `stale`, `backoff`, `degraded`, `no_data`). It then retries automatically with adaptive backoff.

---

## Features & Behavior

### Q: Does the integration support multiple stops?

Yes. Each stop is a separate sensor that you add individually via the config flow. Each stop is updated independently every 120 seconds.

---

### Q: Can I filter by transport type?

Yes. You can enable or disable specific transport types (buses, trams, trains, ferries, etc.) during configuration.

---

### Q: Does the integration support intermediate stops in filters?

No. Direction filters work only for **final destinations** (endpoints). If you want to filter by an intermediate stop, you would need to use that stop's `stop_id`, but this will show all departures to that location (not just passing through).

---

### Q: Can I filter departures to only show routes within walking distance?

Yes, through the **Walking time** configuration option. The integration hides departures that leave before you can realistically reach the stop.

---

### Q: Does the card update automatically?

Yes. The card displays data from the sensor, which updates every 120 seconds. The card refreshes automatically when the sensor state changes.

---

## Dashboard & Display

### Q: How do I add the card to my dashboard?

1. Open any dashboard and add a new card
2. Under **Custom cards**, select **BVG/VBB departures card**
3. Choose the entity you created
4. Adjust display options as needed (show delay, show relative time, etc.)
5. Save the card

See the [Configuration Guide](./configuration.md#dashboard-card-configuration) for card options.

---

### Q: Can I customize the card appearance?

Yes, the card has several display options:
- Show/hide cancelled departures
- Show/hide delays
- Show absolute time, relative time, or both
- Subtract walking time from the countdown

See [Configuration Guide → Card](./configuration.md#dashboard-card-configuration) for details.

---

### Q: Why is the card not displaying?

The card needs at least one successful sensor update before it can display data. This usually takes 1-2 minutes after adding the sensor.

If the card still doesn't display:
1. Check that the entity is selected correctly
2. Check the Home Assistant logs for errors
3. See the [Troubleshooting Guide](./troubleshooting.md)

---

## Troubleshooting

### Q: The sensor shows "unavailable"

This can happen for several reasons:
- The API is temporarily unreachable
- The first update hasn't completed yet (wait 1-2 minutes)
- The stop name wasn't found in the API

See the [Troubleshooting Guide](./troubleshooting.md) for more solutions.

---

### Q: Sensor updates are slow or hanging

This could be a timeout or slow network connection. The integration has a 240-second timeout for API requests.

See the [Troubleshooting Guide](./troubleshooting.md) for debugging steps.

---

### Q: The direction filter doesn't work

Make sure you've provided the correct `stop_id` for your destination. See [How do I find my stop_id?](#q-how-do-i-find-my-stop_id) above.

---

## Installation Issues

### Q: How do I install manually?

See the [Manual Installation Guide](./manual_install.md).

---

### Q: Can I use this integration with other Home Assistant add-ons?

Yes, this is a standard Home Assistant integration and works with any compatible add-ons or automations.

---

## Support & Contributing

### Q: Where can I report bugs or request features?

Visit the GitHub repository:
- **Bug reports:** [Open an issue](https://github.com/manoth-msft/home-assistant-bvg-vbb-departures/issues)
- **Feature requests:** [Open an issue](https://github.com/manoth-msft/home-assistant-bvg-vbb-departures/issues)
- **Contributions:** [Open a pull request](https://github.com/manoth-msft/home-assistant-bvg-vbb-departures/pulls)

---

### Q: Is this project still maintained?

Yes, this is an active project with ongoing maintenance and improvements. Check the [CHANGELOG](../CHANGELOG.md) for the latest updates.

---

## Still Have Questions?

If you don't find your question here, feel free to:
- Check the [Configuration Guide](./configuration.md) for detailed explanations
- Check the [Troubleshooting Guide](./troubleshooting.md) for common issues
- [Open an issue](https://github.com/manoth-msft/home-assistant-bvg-vbb-departures/issues) on GitHub
