# Troubleshooting Guide

This guide covers common issues and how to resolve them.

## Common Issues

### Sensor shows "unavailable"

**Symptoms:**
- Entity state shows "unavailable"
- No departures are displayed
- Dashboard card is empty

**Possible causes:**

#### 1. First update hasn't completed yet
If you just added the sensor, it takes 1-2 minutes for the first update.

**Solution:** Wait 2-3 minutes, then check again.

---

#### 2. Stop name not found in the API
The integration couldn't find your stop in the VBB API.

**Solution:**
- Go to **Settings > Devices & Services**
- Delete the sensor
- Add it again and carefully check the stop name suggestion list
- Make sure your stop exists in Berlin/Brandenburg

**Debug:** Test the stop manually:
```
https://v6.vbb.transport.rest/locations?results=5&query=YOUR_STOP_NAME
```
Replace `YOUR_STOP_NAME` with your stop. If this returns no results, the API doesn't know your stop.

---

#### 3. API is experiencing issues
The VBB API might be temporarily unreachable.

**Check:** Visit [https://v6.vbb.transport.rest/api.html](https://v6.vbb.transport.rest/api.html) and see if the API is responding.

**Solution:** 
- Wait 5-10 minutes for the API to recover
- The integration will retry automatically
- When the API recovers, your sensor will update automatically

---

#### 4. Network connectivity issue
Your Home Assistant instance can't reach the VBB API servers.

**Check:** Does your Home Assistant have internet access? Can it reach other external services?

**Solution:**
- Check your network configuration
- Try restarting Home Assistant
- Check firewall rules if on a restricted network

---

### Card not displaying departures

**Symptoms:**
- Card loads but shows empty list
- "No departures found" message

**Possible causes:**

#### 1. Sensor hasn't updated yet
The sensor needs at least one successful update.

**Solution:** Wait 1-2 minutes after adding the sensor.

---

#### 2. Direction filter is too restrictive
Your direction filter might be excluding all departures.

**Solution:**
- Check that you provided the correct `stop_id` for your direction
- Try removing the direction filter temporarily to see all departures
- See [Configuration Guide](./configuration.md#-direction) for help

---

#### 3. Walking time is too high
If walking time is longer than most departures, everything gets filtered out.

**Example:** If walking time is 30 minutes and your next departure is in 15 minutes, it won't be shown.

**Solution:** 
- Reduce the walking time to a realistic value
- Or set it to 0 and adjust in the card's display options

---

#### 4. Transport type filters are too restrictive
You might have disabled the transport type you're looking for.

**Solution:**
- Go to **Settings > Devices & Services**
- Delete and re-add the sensor
- Enable at least one transport type that serves your stop

---

### Sensor updates are slow or hanging

**Symptoms:**
- Sensor takes longer than 2-3 minutes to update
- Updates seem to stall indefinitely
- Home Assistant logs show timeout errors

**Possible causes:**

#### 1. Slow internet connection
Your network connection to the VBB API is slow.

**Check:** The integration has a **240-second timeout** for API requests. If your connection is very slow, requests might time out.

**Solution:**
- Check your internet connection speed
- Try accessing [https://v6.vbb.transport.rest/api.html](https://v6.vbb.transport.rest/api.html) directly to see how fast it responds
- This is usually not a problem; the integration will retry if it times out

---

#### 2. Home Assistant system is overloaded
Your Home Assistant instance might be under heavy load.

**Check:** 
- Is your Home Assistant CPU usage high?
- Are there other long-running tasks?

**Solution:**
- Reduce the number of integrations or automations running
- Check Home Assistant system resources
- Consider upgrading hardware if consistently overloaded

---

#### 3. Too many sensors
If you have too many sensors, API rate limits might be hit.

**Background:** Each sensor makes a request every 120 seconds. With 100 requests/minute limit, you can have up to ~8 sensors comfortably.

**Solution:**
- Reduce the number of sensors you're running
- Spread out sensors across different Home Assistant instances if needed

---

### Direction filter not working

**Symptoms:**
- You set a direction filter, but still see all departures
- Card shows trains going everywhere, not just your destination

**Possible causes:**

#### 1. Wrong stop_id for direction
The direction filter uses `stop_id`, not station name.

**Solution:**
- See [FAQ: How do I find my stop_id?](./faq.md#q-how-do-i-find-my-stop_id)
- Make sure you're providing the `stop_id`, not the station name
- The `stop_id` is a numeric code like `900100003`

---

#### 2. Direction is an intermediate stop, not endpoint
The direction filter works for **final destinations only**. If you try to filter for a stop in the middle of a line, it won't work.

**Example:**
- You want to filter for trains passing through "Friedrichstraße" (an intermediate stop)
- But many lines pass through Friedrichstraße without ending there
- The filter can't distinguish these; it only filters by endpoint

**Solution:**
- Use a stop that is a final destination (endpoint) for the line
- Or remove the direction filter and use other filtering options

---

#### 3. BVG fallback API used (no filter support)
If the main API (transport.rest) is down, the integration uses BVG's API, which doesn't support server-side filtering.

**Check:** Look at the `health_status` attribute. If it says `"backoff"` or `"degraded"`, the BVG fallback might be in use.

**Solution:** Wait for the main API to recover. This is usually temporary.

---

### High memory or CPU usage

**Symptoms:**
- Home Assistant uses more memory after running this integration
- CPU spikes when updating

**Possible causes:**

#### 1. Too many departures being cached
The integration caches departures to handle API outages. If you're monitoring very busy stops, this can use memory.

**Background:** The integration keeps the last 10 recent API responses cached per stop.

**Solution:**
- This is usually not significant unless you have many sensors
- If memory is critical, reduce the number of sensors

---

#### 2. Departure list is very large
Some stops have dozens of departures per hour.

**Solution:**
- Use direction or transport type filters to reduce the list size
- Use the card's options to show fewer departures on screen

---

### JSON or attribute errors in logs

**Symptoms:**
- Home Assistant logs show JSON parsing errors
- Error messages about missing attributes

**Solution:**
- This is usually a temporary API response issue
- The integration will retry automatically
- If it persists, check the [FAQ](./faq.md#q-what-happens-if-the-vbb-api-returns-errors)

---

## Debugging Steps

### 1. Enable debug logging

Add this to your `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.berlin_transport: debug
```

Then restart Home Assistant. Debug logs will appear in Settings > System > Logs.

---

### 2. Check sensor attributes

In Home Assistant:
1. Go to **Developer Tools > States**
2. Search for your sensor (e.g., `sensor.s_treptower_park`)
3. Click it to see all attributes

**Important attributes:**
- `health_status`: Current state (`ok`, `stale`, `backoff`, `degraded`, `no_data`)
- `health_details`: Description of the current state
- `data_is_stale`: Whether the data is from a previous update
- `last_updated`: Timestamp of the last successful update

---

### 3. Test the API manually

To verify the API is working:

```bash
curl "https://v6.vbb.transport.rest/stops/900100003/departures?stop_id=900100003"
```

Replace `900100003` with your stop_id. If this works, the API is available.

---

### 4. Check Home Assistant logs

1. Go to **Settings > System > Logs**
2. Search for `berlin_transport` or your stop name
3. Look for error messages or warnings

---

## Still Having Issues?

If none of these solutions help:

1. **Gather information:**
   - Screenshots of the error
   - Relevant log entries (Settings > System > Logs)
   - Your configuration (stop name, filters)
   - Approximate time issue started

2. **Report the issue:**
   - [Open a GitHub issue](https://github.com/manoth-msft/home-assistant-bvg-vbb-departures/issues)
   - Include the information from step 1
   - Describe what you expected vs. what happened

3. **Get help:**
   - Check if there's a similar open issue
   - Ask in the Home Assistant community forum

---

## Known Limitations

### BVG API Fallback (When transport.rest is unavailable)

When the main API (transport.rest) has problems, the integration uses the BVG API as fallback. However:

- **Direction filtering doesn't work** on the BVG API (it lacks this capability)
- **Walking time filtering still works** (calculated locally)
- **Transport type filtering still works** (calculated locally)

This is expected behavior. Once the main API recovers, filtering resumes working normally.

---

### Rate Limiting

The VBB API has a rate limit of **100 requests per minute**. With sensors updating every 120 seconds:
- 1-8 sensors: No issues
- 8-15 sensors: Approaching the limit
- 15+ sensors: Likely to hit rate limits

**Solution:** Reduce the number of sensors or spread them across multiple Home Assistant instances.

---

## Performance Tips

1. **Use direction filters** to reduce the size of departure lists
2. **Use walking time** to hide unreachable departures
3. **Disable transport types** you don't need
4. **Don't monitor too many stops** (8-10 is comfortable)
5. **Use the card's display options** to show fewer items on screen

---

## Getting Help

- **Configuration questions:** See [Configuration Guide](./configuration.md)
- **General questions:** See [FAQ](./faq.md)
- **Bugs or feature requests:** [Open an issue on GitHub](https://github.com/manoth-msft/home-assistant-bvg-vbb-departures/issues)
