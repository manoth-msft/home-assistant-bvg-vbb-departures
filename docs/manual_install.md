# 🚉 Berlin (BVG) and Brandenburg (VBB) public transport departures for Home Assistant

### Install sensor component manually

This documentation is incomplete. It will be updated in a future release.

#### How do I find my `stop_id`?

Unfortunately, I didn't have time to figure out a proper user-friendly approach of adding new components to Home Assistant, so you will have to do some routine work of finding the IDs of the nearest transport stops to you. Sorry about that :)

Simply use this URL: **https://v6.vbb.transport.rest/locations?results=1&query=alexanderplatz**

Replace `alexanderplatz` with the name of your own stop.

![](./docs/screenshots/stop-id-api.jpg)

> 🧐 **Pro tip:**
> You can also use their [location-based API](https://v6.vbb.transport.rest/api.html#get-stopsnearby) to find all stops nearby using your GPS coordinates.

**1.** Copy the whole [berlin_transport](./custom_components/) directory to the `custom_components` folder of your Home Assistant installation. If you can't find the `custom_components` directory at the same level with your `configuration.yml` — simply create it yourself and put `berlin_transport` there.

**2.** Go to Home Assistant web interface -> `Developer Tools` -> `Check and Restart` and click "Restart" button. It will reload all components in the system.

**3.** Now you can add your new custom sensor to the corresponding section in the `configuration.yml` file.

```yaml
sensor:
  - platform: berlin_transport
    departures:
      - name: "S+U Schönhauser Allee" # free-form name, only for display purposes
        stop_id: 900110001 # actual Stop ID for the API
        # direction: 900110002,900007102 # Optional stop_id to limit departures for a specific direction (same URL as to find the stop_id), multiple Values can be specified using a comma separated list
        # walking_time: 5 # Optional parameter with value in minutes that hides transport closer than N minutes
        # suburban: false # Optionally hide transport options
        # show_official_line_colors: true # Optionally enable official VBB line colors. By default predefined colors will be used.
        # duration is currently fixed to 30 minutes in code and not configurable
      - name: "Stargarder Str." # currently you have to add more than one stop to track
        stop_id: 900000110501
        # direction: 900000100002 # Optional stop_id to limit departures for a specific direction (same URL as to find the stop_id), multiple Values can be specified using a comma separated list
        # excluded_stops: 900110502,900007102 # Exclude these stop IDs from the departures, duplicate departures may be shown for nearby stations
        # walking_time: 5 # Optional parameter with value in minutes that hide transport closer than N minutes
        # show_official_line_colors: true # Optionally enable official VBB line colors. By default predefined colors will be used.
        # exclude_ringbahn_clockwise: true # Optionally hide Ringbahn services running clockwise
        # exclude_ringbahn_counterclockwise: false # Optionally hide Ringbahn services running counter‑clockwise
        # remove_berlin_suffix: false # Optionally remove the (Berlin) suffix which the BVG appoends to some stops.
        # duration is currently fixed to 30 minutes in code and not configurable
```

**4.** Restart Home Assistant core again and you should now see two new entities (however, it may take some time for them to fetch new data). If you don't see anything new — check the logs (Settings -> System -> Logs). Some error should pop up there.

### Add the lovelace card

Go to [lovelace-berlin-transport-card](https://github.com/vas3k/lovelace-berlin-transport-card) repo and follow installation instructions there.
