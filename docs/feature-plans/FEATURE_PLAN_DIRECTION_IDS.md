# Feature Plan v0.1.6: Direction Stop-ID Management

## 📋 Status: Erkenntnisse aus API-Tests (2026-07-09)

### ✅ Was funktioniert (API-Level)
1. **Single Intermediate Stop Filtering:** `?direction=900083101` (Zwischenstation) funktioniert korrekt
   - API filtert richtig nach intermediate stops
   - Test bewies: Mit Filter nur U7 zu Rudow, ohne Filter + U7 zu Spandau
   - **tripIds unterscheiden sich!** → API filtert wirklich

2. **Single Destination Filtering:** `?direction=900083201` (Endstation) funktioniert wie erwartet

### ❌ Was nicht funktioniert (API-Level)
1. **Comma-Separated Direction IDs:** `?direction=900083101,900083102` → HTTP 400 `"direction must be an IBNR"`
   - API akzeptiert **nur eine Stop-ID** pro Request
   - Dokumentation: Nur `string` Parameter, keine Mehrfach-Unterstützung
   - **Lösung:** Lokal im Client mehrere Requests oder post-filter

2. **Stop-Namen statt Stop-IDs:** `?direction=Adlershof` (Stop-Name) → HTTP 500
   - API verlangt numerische IBNR-IDs
   - **Lösung:** Config-Flow muss Stop-Namen zu Stop-IDs konvertieren

### 🛑 Bestehende Fehler (Production)
- **25× HTTP 500 Fehler** (2026-07-09): Nutzer gaben Stop-NAMEN ein
  - `direction=S Tegel`, `direction=Adlershof`, `direction=S Heiligensee`
  - Alle Nutzer benutzten die Config-Datei direkt statt Config-Flow
  - **Keine Migration** → alte Einträge sind permanent fehlerhaft

---

## 🎯 v0.1.6 Lösung: Single Direction mit Validierung

**Ansatz:** Pragmatisch - EINE Stop-ID pro Sensor mit API-Validierung

### Phase 1: Config-Flow Neubau (4-5h)

**Anforderung:** Nutzer soll Stop-Namen eingeben (nicht IDs suchen müssen), wir speichern die Stop-ID

**Flow:**
```
async_step_user
  ↓ (Stop wählen: U Wutzkyallee)
async_step_stop
  ↓ (Optional: Soll ich Richtungsfilter setzen?)
async_step_direction_input  [NEU]
  ↓ "Geben Sie Stationsnamen ein, auf die gefiltert werden soll"
  ↓ User: "Zwickauer Damm"
  ↓ GET /locations?query=Zwickauer%20Damm
  ↓ 1 oder mehrere Treffer gefunden
async_step_direction_select  [NEU]  (falls mehrere Treffer)
  ↓ "Welche Station gemeint?"
  ↓ User: "Zwickauer Damm (Berlin), Stop-ID 900083101"
  ↓ Validierung: GET /trips?currentlyStoppingAt=900083102&fromWhen=today&untilWhen=next-week
  ↓ "Finde ich in den nächsten 7 Tagen Züge von U Wutzkyallee über Zwickauer Damm?"
async_step_direction_validate  [NEU]
  ↓ Falls Stop NICHT auf Route: ⚠️ Warnung
  ↓ "Warnung: Diese Station wird in den nächsten 7 Tagen von keiner Linie befahren"
  ↓ User kann ignorieren oder zurück zum Filter
async_step_details
  ↓ (Connectiontypes, Ringbahn, etc.)
```

**Code-Beispiel:**

```python
async def async_step_direction_input(self, user_input=None) -> FlowResult:
    """Nutzer gibt Stationsnamen für Richtungsfilter ein."""
    if user_input is None:
        return self.async_show_form(
            step_id="direction_input",
            data_schema=vol.Schema({
                vol.Optional("direction_name"): cv.string,
            }),
            description_placeholders={
                "main_stop": self.data.get(CONF_DEPARTURES_NAME, "Unknown"),
            }
        )
    
    direction_name = user_input.get("direction_name", "").strip()
    
    # Abbrechen wenn leer
    if not direction_name:
        return await self.async_step_details()
    
    # API-Suche
    try:
        session = async_get_clientsession(self.hass)
        stops = await get_stop_id(session, direction_name)
    except Exception as ex:
        _LOGGER.warning("[config_flow] Stop search failed: %s", ex)
        return self.async_show_form(
            step_id="direction_input",
            errors={"base": "search_failed"}
        )
    
    if not stops:
        return self.async_show_form(
            step_id="direction_input",
            errors={"base": "stop_not_found"}
        )
    
    # Eindeutig gefunden?
    if len(stops) == 1:
        self._direction_stop = stops[0]
        return await self.async_step_direction_validate()
    
    # Mehrere Treffer → zum Select-Step
    self._direction_candidates = stops
    return await self.async_step_direction_select()

async def async_step_direction_select(self, user_input=None) -> FlowResult:
    """Nutzer wählt aus mehreren Stationen."""
    if user_input is None:
        options = [
            f"{s['name']} [{s['id']}]" for s in self._direction_candidates
        ]
        return self.async_show_form(
            step_id="direction_select",
            data_schema=vol.Schema({
                vol.Required("selected_stop"): vol.In(options),
            })
        )
    
    selected_text = user_input["selected_stop"]
    # Parse: "U Zwickauer Damm [900083101]" → get ID
    stop_id = selected_text.split("[")[-1].rstrip("]")
    
    self._direction_stop = {
        "id": stop_id,
        "name": selected_text.split(" [")[0]
    }
    
    return await self.async_step_direction_validate()

async def async_step_direction_validate(self) -> FlowResult:
    """Validiere, dass Stop auf der Strecke liegt."""
    
    main_stop_id = self.data.get(CONF_DEPARTURES_STOP_ID)
    direction_id = self._direction_stop["id"]
    direction_name = self._direction_stop["name"]
    
    # DEBUG-MODE: Bestimmte Stationen als TEXT speichern statt als Stop-ID
    if DIRECTION_DEBUG_MODE_ENABLED and direction_name in DIRECTION_DEBUG_KEEP_AS_TEXT:
        _LOGGER.warning(
            "[config_flow] DEBUG-MODE: Direction '%s' wird als TEXT gespeichert, nicht als Stop-ID!",
            direction_name
        )
        self.data[CONF_DEPARTURES_DIRECTION] = direction_name  # ← TEXT, nicht ID!
        return await self.async_step_details()
    
    try:
        session = async_get_clientsession(self.hass)
        
        # GET /trips mit currentlyStoppingAt=main_stop_id
        # Prüfe ob direction_id in stopovers vorkommt
        trips_url = f"{PRIM_API_ENDPOINT}/trips"
        params = {
            "currentlyStoppingAt": main_stop_id,
            "fromWhen": "today",
            "untilWhen": "next week",
            "stopovers": "true",
            "results": 100,
        }
        
        async with async_timeout.timeout(30):
            response = await session.get(trips_url, params=params)
            response.raise_for_status()
            trips = await response.json()
        
        # Durchsuche Trips nach direction_id in stopovers
        found = False
        for trip in trips:
            stopovers = trip.get("stopovers", [])
            for stopover in stopovers:
                if stopover.get("stop", {}).get("id") == direction_id:
                    found = True
                    break
            if found:
                break
        
        if found:
            # ✅ Stop ist auf der Strecke
            self.data[CONF_DEPARTURES_DIRECTION] = direction_id
            return await self.async_step_details()
        else:
            # ⚠️ Stop ist NICHT auf der Strecke
            return self.async_show_form(
                step_id="direction_validate",
                data_schema=vol.Schema({}),
                errors={"base": "direction_not_on_route"},
                description_placeholders={
                    "main_stop": self.data.get(CONF_DEPARTURES_NAME),
                    "direction_stop": direction_name,
                }
            )
    
    except Exception as ex:
        _LOGGER.warning("[config_flow] Validation failed: %s", ex)
        # Fehler? → Warnung aber nicht blockierend
        self.data[CONF_DEPARTURES_DIRECTION] = direction_id
        return await self.async_step_details()
```

**Strings (translations/de.json):**
```json
{
  "config": {
    "step": {
      "direction_input": {
        "title": "Richtungsfilter (optional)",
        "description": "Stationsnamen eingeben, um Abfahrten zu filtern.\nZ.B. 'Tegel', 'Alexanderplatz', 'Zwickauer Damm'",
        "data": {
          "direction_name": "Stationsname (leer = kein Filter)"
        }
      },
      "direction_select": {
        "title": "Welche Station?",
        "description": "Es gibt mehrere Stationen mit diesem Namen. Welche gemeint?",
        "data": {
          "selected_stop": "Station"
        }
      },
      "direction_validate": {
        "title": "⚠️ Richtung nicht gefunden",
        "description": "**Warnung:** Die Station '{direction_stop}' wird in den nächsten 7 Tagen von keiner Linie angefahren, die {main_stop} bedient.\n\nMöglicherweise ist die Station falsch oder die Linie fährt dort nicht.\n\nDie Konfiguration wird trotzdem gespeichert. Falls Probleme auftreten, ändern Sie den Richtungsfilter."
      }
    },
    "error": {
      "stop_not_found": "Station nicht gefunden. Bitte Stationsnamen prüfen.",
      "search_failed": "API-Fehler bei Stationssuche. Später nochmal versuchen.",
      "direction_not_on_route": "Stop ist nicht auf dieser Route"
    }
  }
}
```

---

### Phase 2: Auto-Migration für bestehende Konfigurationen (2-3h)

**Problem:** Alte Configs mit Stop-NAMEN (von direkter YAML) sind kaputt

**Lösung:** Bei Startup prüfen und migrieren (mit State-Tracking um mehrfache Versuche zu vermeiden)

**Konstanten (const.py):**
```python
# Migration feature gate
DIRECTION_ID_MIGRATION_ENABLED = True  # Toggle für Tests/Rollback

# Neues Config-Entry-Detail Feld
DIRECTION_MIGRATION_STATE = "direction_migration_state"  # "not_needed" | "completed" | "failed"

# DEBUG-MODE: Bestimmte Station-Namen NICHT als Stop-ID speichern (nur während Preview/Testing!)
# Vor Release: Diese Liste LEER machen oder komplett entfernen!
DIRECTION_DEBUG_KEEP_AS_TEXT = [
    # "Zwickauer Damm",  # Beispiel: Wenn hier eingetragen, wird als TEXT gespeichert
    # "Adlershof",       # statt als Stop-ID. Brauchen wir zum Testen der Migration.
]
DIRECTION_DEBUG_MODE_ENABLED = len(DIRECTION_DEBUG_KEEP_AS_TEXT) > 0
```

**Migrations-Logik (config_flow.py oder neue Datei migration.py):**

```python
async def migrate_direction_field(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """
    Migrate Stop-Names to Stop-IDs in direction field.
    
    States:
    - "not_needed": Direction ist numerische Stop-ID oder leer
    - "completed": Migration erfolgreich durchgeführt
    - "failed": Migration fehlgeschlagen (Stop nicht gefunden) - nicht nochmal versuchen!
    
    Returns:
        True wenn Migration gelungen oder nicht nötig
        False wenn Migration fehlgeschlagen
    """
    
    # Feature Gate Check
    if not DIRECTION_ID_MIGRATION_ENABLED:
        _LOGGER.debug("[migration] Feature gate disabled, skipping")
        return True
    
    # Schritt 1: Migration-State prüfen
    migration_state = entry.data.get(DIRECTION_MIGRATION_STATE)
    
    if migration_state == "completed":
        _LOGGER.debug("[migration] Already completed, skipping")
        return True
    
    if migration_state == "failed":
        _LOGGER.warning(
            "[migration] Previous migration failed for entry %s. "
            "Skipping. User must fix manually in configuration YAML.",
            entry.entry_id
        )
        return False
    
    # Schritt 2: Ist es bereits eine numerische Stop-ID?
    direction = entry.data.get(CONF_DEPARTURES_DIRECTION, "").strip()
    
    if not direction:
        # ✅ Kein Filter - Migration nicht nötig
        _update_migration_state(entry, "not_needed")
        return True
    
    if direction.isdigit():
        # ✅ Bereits numerische Stop-ID
        _update_migration_state(entry, "not_needed")
        return True
    
    # Schritt 3: Stop-Name erkannt → Versuch Migration
    _LOGGER.warning(
        "[migration] Stop-Name in direction erkannt: '%s' (entry=%s). "
        "Versuche zu Stop-ID zu konvertieren...",
        direction,
        entry.entry_id
    )
    
    try:
        session = async_get_clientsession(hass)
        stops = await get_stop_id(session, direction)
        
        if stops:
            # ✅ Erfolgreich gefunden!
            new_id = stops[0]["id"]
            
            # Update config entry
            new_data = entry.data.copy()
            new_data[CONF_DEPARTURES_DIRECTION] = str(new_id)
            hass.config_entries.async_update_entry(entry, data=new_data)
            
            # State speichern
            _update_migration_state(entry, "completed")
            
            _LOGGER.info(
                "[migration] ✅ COMPLETED: '%s' → Stop-ID '%s' (entry=%s)",
                direction, new_id, entry.entry_id
            )
            return True
        else:
            # ❌ Stop nicht gefunden
            _LOGGER.error(
                "[migration] ❌ FAILED: Station '%s' nicht gefunden (entry=%s). "
                "Stop-Name wird nicht mehr in Migrationen versucht. "
                "Bitte manuell in YAML konfigurieren oder über UI neu setzen.",
                direction, entry.entry_id
            )
            
            # State speichern: Nicht nochmal versuchen!
            _update_migration_state(entry, "failed")
            return False
    
    except Exception as ex:
        _LOGGER.error(
            "[migration] API Error during migration (entry=%s): %s. "
            "Will retry on next sensor update.",
            entry.entry_id, ex
        )
        # Nicht als "failed" markieren - API kann später wieder funktionieren
        return False

def _update_migration_state(entry: ConfigEntry, state: str) -> None:
    """Speichere Migration-State im Entry"""
    new_data = entry.data.copy()
    new_data[DIRECTION_MIGRATION_STATE] = state
    # Muss über entry.options oder extra detail field sein
    # Je nach HA Version unterschiedlich
    entry.data[DIRECTION_MIGRATION_STATE] = state
```

**Setup Entry (__init__.py):**

```python
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, ...):
    """Setup mit Migration Check"""
    
    # Schritt 1: Versuch Migration (non-blocking)
    migration_result = await migrate_direction_field(hass, entry)
    
    if migration_result is False:
        # Migration ist fehlgeschlagen und wird nicht nochmal probiert
        _LOGGER.error(
            "[setup] Direction migration FAILED for entry %s. "
            "Sensor wird mit aktivem Filter nicht funktionieren.",
            entry.entry_id
        )
    
    # Schritt 2: Weitermachen mit Setup (unabhängig von Migration-Erfolg)
    async def async_update_listener(hass, entry):
        """Reload on config changes"""
        await hass.config_entries.async_reload(entry.entry_id)
    
    entry.async_on_unload(
        entry.add_update_listener(async_update_listener)
    )
    
    # Schritt 3: Sensoren initialisieren
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    return True
```

**Logging Summary nach Migration:**

```
[2026-07-09 20:15:45] [migration] Stop-Name in direction erkannt: 'Adlershof' (entry=abc123). Versuche zu Stop-ID zu konvertieren...
[2026-07-09 20:15:45] [migration] ✅ COMPLETED: 'Adlershof' → Stop-ID '900110001' (entry=abc123)

Oder:

[2026-07-09 20:15:45] [migration] Stop-Name in direction erkannt: 'Musterstadt' (entry=xyz789). Versuche zu Stop-ID zu konvertieren...
[2026-07-09 20:15:45] [migration] ❌ FAILED: Station 'Musterstadt' nicht gefunden (entry=xyz789). Stop-Name wird nicht mehr in Migrationen versucht. Bitte manuell in YAML konfigurieren oder über UI neu setzen.
```

**Behavior:**

| State | Beschreibung | Nächster Versuch |
|-------|-------------|-----------------|
| `not_needed` | Direction ist bereits numeric oder leer | ❌ Nicht nötig |
| `completed` | Migration erfolgreich durchgeführt | ❌ Nicht nötig |
| `failed` | Stop nicht gefunden - Migration abgebrochen | ❌ Nie wieder versuchen |
| (nicht gesetzt) | Erste Migration nicht durchgeführt | ✅ Nächstes Update versuchen |

---

### Phase 3: Support für Comma-Separated (optional, später)

Wenn Nutzer mehrere Stops filtern wollen:
- **Option A:** Mehrere Sensoren anlegen (einfach, aktuell unterstützt)
- **Option B:** Comma-separated via lokales Post-Filtern (kompliziert, needs PR changes)

**Dafür → Separates Feature v0.1.7 oder später**

---

## � Mehrere Stop-IDs für einen Stop-Namen

**Szenario:** User sucht "Hauptbahnhof" oder "Friedrichstr." → API gibt mehrere Varianten zurück

### Lösung 1: Im Config-Flow (Preferred)
Der User wird **direkt gefragt**, welche Station er meint:

```
async_step_direction_select() zeigt Dropdown:
- "S+U Hauptbahnhof, Berlin-Mitte [900003101]"
- "Hauptbahnhof Zoo [900001102]"  
- "Lehrter Bahnhof [900001103]"

→ User wählt die richtige aus
→ Wir speichern die EINE Stop-ID
```

**Code (bereits oben):**
```python
if len(stops) > 1:
    return await self.async_step_direction_select()
else:
    # Eindeutig
    return await self.async_step_direction_validate()
```

### Lösung 2: Beim Sensor-Laden (Fallback) - OPTIMIERT mit Produkt-Matching
Falls trotzdem ein Stop-Name (als Text) in der Config ist und konvertiert werden muss:

**Strategie: Response iterieren, ersten Stop mit passendem Produkt nehmen**

```python
# In sensor.py beim Laden
direction = config.get(CONF_DEPARTURES_DIRECTION)
if direction and not direction.isdigit():  # Text!
    # GET /locations?query=direction&results=5
    # (Mehr Ergebnisse holen, dann filtern)
    stops = await get_stop_id(session, direction, results=5)
    
    # Aus Config: Welche Produkte sind relevant?
    # z.B. "suburban,subway" oder "tram,bus"
    config_products = config.get(CONF_PRODUCTS, "suburban,subway,tram,bus").split(",")
    
    # Iteriere Ergebnisse: Erster Stop, der ein passendes Produkt hat
    direction_id = None
    for stop in stops:
        stop_products = stop.get("products", {})
        for product in config_products:
            if stop_products.get(product, False):
                direction_id = stop["id"]
                _LOGGER.info(
                    "[sensor] Direction-Name '%s' → Stop-ID: %s [%s] (Product: %s)",
                    direction,
                    stop["name"],
                    direction_id,
                    product
                )
                break
        
        if direction_id:
            break
    
    if not direction_id:
        _LOGGER.error(
            "[sensor] Could not convert direction-name '%s' to Stop-ID "
            "(no match with products: %s)",
            direction,
            ", ".join(config_products)
        )
```

---

## 📋 Config-Flow-Anpassungsplan (gegen HA-Dokumentation geprüft)

### Aktuelle Flow-Struktur (v0.1.5):
```
async_step_user       (Stop-Name eingeben)
  ↓
async_step_stop       (Aus mehreren Stops wählen)
  ↓
async_step_details    (Direction, excluded_stops, products, etc. optional eingeben)
  ↓
async_create_entry    (Speichern)
```

**Daten-Flow:**
- `self.data`: Persistente Daten zwischen Steps (CONF_DEPARTURES_NAME, CONF_DEPARTURES_STOP_ID)
- `user_input`: Form-Daten aus aktuellem Step
- Am Ende werden beide kombiniert und in entry.data gespeichert

---

### ✅ Neue Flow-Struktur (v0.1.6):
```
async_step_user       
  ↓
async_step_stop       
  ↓
async_step_direction_input    [NEU] ← Optional: "Möchte direction-filter setzen?"
  ↓ (Je nach Ergebnis)
async_step_direction_select   [NEU] ← Falls > 1 Stop-ID gefunden
oder
async_step_direction_validate [NEU] ← Falls genau 1 Stop-ID gefunden
  ↓
async_step_details           (Bestehend)
  ↓
async_create_entry
```

---

### 📝 Erforderliche Code-Anpassungen:

#### 1️⃣ **const.py** - Neue Constants + Feature Gates
```python
# Neue Config-Keys für direction-flow
CONF_DEPARTURES_DIRECTION_INPUT = "direction_input"  # Nutzereingabe (Text)

# Feature Gates
DIRECTION_ID_MIGRATION_ENABLED = True
DIRECTION_MIGRATION_STATE = "direction_migration_state"

# DEBUG-MODE für Preview
DIRECTION_DEBUG_KEEP_AS_TEXT = []  # Beispiel: ["Zwickauer Damm", "Adlershof"]
DIRECTION_DEBUG_MODE_ENABLED = len(DIRECTION_DEBUG_KEEP_AS_TEXT) > 0
```

#### 2️⃣ **config_flow.py** - Neue Steps + Flow-Routing

**a) Neue Helper-Funktion:**
```python
async def get_direction_stops(
    session: aiohttp.ClientSession, 
    name: str,
    results: int = 5
) -> tuple[bool, list[dict[str, Any]], str | None]:
    """Suche direction-Stationen (wie get_stop_id, aber mit results-param)."""
    # Same Logik wie get_stop_id, aber mit results-Parameter
```

**b) Neuer Step: async_step_direction_input()**
```python
async def async_step_direction_input(self, user_input=None):
    """
    USER FRAGT: "Soll der Sensor auf Stationen filtern?" (Optional)
    
    Workflow:
    1. Kein Input? → Form mit optionalem Text-Feld zeigen
    2. User lässt leer → Direkt zu async_step_details()
    3. User gibt Text ein → GET /locations?query=text&results=5
    4. Falls 0 Ergebnisse → "stop_not_found" Fehler + retry
    5. Falls 1 Ergebnis → Direkt zu async_step_direction_validate()
    6. Falls >1 Ergebnisse → Zu async_step_direction_select()
    """
    
    if user_input is None:
        return self.async_show_form(
            step_id="direction_input",
            data_schema=vol.Schema({
                vol.Optional("direction_name"): cv.string,  # ← Optional!
            }),
            description_placeholders={
                "main_stop": self.data.get(CONF_DEPARTURES_NAME, "Unknown"),
            }
        )
    
    direction_name = user_input.get("direction_name", "").strip()
    
    # User hat nichts eingegeben → überspringen
    if not direction_name:
        return await self.async_step_details()
    
    # Suche Stationen
    session = async_get_clientsession(self.hass)
    success, stops, error_key = await get_direction_stops(session, direction_name, results=5)
    
    if not success:
        return self.async_show_form(
            step_id="direction_input",
            data_schema=vol.Schema({vol.Optional("direction_name"): cv.string}),
            errors={"base": error_key},
        )
    
    if not stops:
        return self.async_show_form(
            step_id="direction_input",
            data_schema=vol.Schema({vol.Optional("direction_name"): cv.string}),
            errors={"base": "stop_not_found"},
            description_placeholders={"search_query": direction_name},
        )
    
    # Speichere Kandidaten
    self.data["direction_candidates"] = stops
    self.data["direction_name"] = direction_name
    
    if len(stops) == 1:
        self._direction_stop = stops[0]
        return await self.async_step_direction_validate()
    else:
        return await self.async_step_direction_select()
```

**c) Neuer Step: async_step_direction_select()**
```python
async def async_step_direction_select(self, user_input=None):
    """User wählt aus mehreren Stationen."""
    if user_input is None:
        options = [
            f"{s['name']} [{s['id']}]" for s in self.data["direction_candidates"]
        ]
        return self.async_show_form(
            step_id="direction_select",
            data_schema=vol.Schema({
                vol.Required("selected_stop"): vol.In(options),
            })
        )
    
    selected_text = user_input["selected_stop"]
    stop_id = selected_text.split("[")[-1].rstrip("]")
    
    self._direction_stop = {
        "id": stop_id,
        "name": selected_text.split(" [")[0]
    }
    
    return await self.async_step_direction_validate()
```

**d) Neuer Step: async_step_direction_validate()**
```python
async def async_step_direction_validate(self):
    """Backend validiert dass Stop auf Route liegt."""
    
    main_stop_id = self.data.get(CONF_DEPARTURES_STOP_ID)
    direction_id = self._direction_stop["id"]
    direction_name = self._direction_stop["name"]
    
    # DEBUG-MODE: Bestimmte Stationen als TEXT speichern
    if DIRECTION_DEBUG_MODE_ENABLED and direction_name in DIRECTION_DEBUG_KEEP_AS_TEXT:
        _LOGGER.warning(
            "[config_flow] DEBUG-MODE: Direction '%s' wird als TEXT gespeichert!",
            direction_name
        )
        self.data[CONF_DEPARTURES_DIRECTION] = direction_name  # ← TEXT
        return await self.async_step_details()
    
    try:
        session = async_get_clientsession(self.hass)
        
        # GET /trips?currentlyStoppingAt=main_stop_id&...&stopovers=true
        trips_url = f"{PRIM_API_ENDPOINT}/trips"
        params = {
            "currentlyStoppingAt": main_stop_id,
            "fromWhen": "today",
            "untilWhen": "next week",
            "stopovers": "true"
        }
        
        async with async_timeout.timeout(30):
            response = await session.get(trips_url, params=params)
            response.raise_for_status()
            trips = await response.json()
        
        # Suche direction_id in Stopovers
        found = False
        for trip in trips:
            stopovers = trip.get("stopovers", [])
            if any(stop["stop"]["id"] == direction_id for stop in stopovers):
                found = True
                break
        
        if not found:
            # Warning: Station ist auf Route nicht enthalten
            _LOGGER.warning(
                "[config_flow] Direction stop '%s' not found on trips to '%s'",
                direction_name,
                self.data.get(CONF_DEPARTURES_NAME)
            )
            # Trotzdem speichern, aber warnen
        
        # Speichere die Stop-ID
        self.data[CONF_DEPARTURES_DIRECTION] = direction_id
        return await self.async_step_details()
        
    except Exception as ex:
        _LOGGER.error("[config_flow] Validation failed: %s", ex)
        # Bei Fehler trotzdem weitermachen (nicht blockieren)
        self.data[CONF_DEPARTURES_DIRECTION] = direction_id
        return await self.async_step_details()
```

**e) Modify: async_step_stop()** (Nach bestehender Auswahl)
```python
# Am Ende von async_step_stop(), nach Stop-Auswahl:
return await self.async_step_direction_input()  # Immer zur Richtung (dort entscheidet user)
```

**f) Modify: async_step_details()** (Am Anfang + Ende)
```python
async def async_step_details(self, user_input=None):
    if user_input is None:
        # Hole bisherige Werte aus self.data
        direction_value = self.data.get(CONF_DEPARTURES_DIRECTION)
        
        return self.async_show_form(
            step_id="details",
            data_schema=vol.Schema({
                vol.Optional(CONF_DEPARTURES_DIRECTION, 
                           default=direction_value): cv.string,  # ← Mit Wert aus direction-steps!
                vol.Optional(CONF_DEPARTURES_EXCLUDED_STOPS): cv.string,
                # ... weitere Felder
            }),
            errors={},
        )
    
    # Am Ende:
    data = user_input
    data[CONF_DEPARTURES_STOP_ID] = self.data[CONF_DEPARTURES_STOP_ID]
    data[CONF_DEPARTURES_NAME] = self.data[CONF_DEPARTURES_NAME]
    
    # WICHTIG: Falls direction aus direction-steps, nicht aus details überschreiben!
    if CONF_DEPARTURES_DIRECTION in self.data and self.data[CONF_DEPARTURES_DIRECTION]:
        data[CONF_DEPARTURES_DIRECTION] = self.data[CONF_DEPARTURES_DIRECTION]
    
    return self.async_create_entry(
        title=f"{data[CONF_DEPARTURES_NAME]} [{data[CONF_DEPARTURES_STOP_ID]}]",
        data=data,
    )
```

#### 3️⃣ **strings.json** - UI-Labels
```json
{
  "config": {
    "step": {
      "direction_input": {
        "title": "Richtungsfilter (optional)",
        "description": "Möchten Sie auf bestimmte Stationen filtern?\n\nZ.B. 'Zwickauer Damm' zeigt nur Züge, die dort halten.",
        "data": {
          "direction_name": "Station eingeben (optional lassen zum Überspringen)"
        }
      },
      "direction_select": {
        "title": "Station auswählen",
        "description": "Mehrere Stationen gefunden. Welche ist gemeint?",
        "data": {
          "selected_stop": "Station"
        }
      },
      "direction_validate": {
        "title": "Station wird überprüft..."
      }
    },
    "error": {
      "stop_not_found": "Station '{search_query}' nicht gefunden.",
      "search_failed": "API-Fehler bei Suche. Später wiederholen.",
      "direction_not_on_route": "⚠️ Station wird auf dieser Route nicht angefahren. Trotzdem verwenden?"
    }
  }
}
```

#### 4️⃣ **translations/de.json + en.json**
Same structure wie strings.json unter `config.step.direction_*`

---

### ✅ Best-Practices gegen HA-Dokumentation

| Punkt | HA-Empfehlung | Unsere Lösung |
|-------|---|---|
| **async_show_form()** | step_id + data_schema required | ✅ Alle haben beides |
| **self.data** | Persistent zwischen Steps | ✅ Für CONF_DEPARTURES_* |
| **user_input** | Nur aktueller Step | ✅ Nicht mischen |
| **Error-Keys** | In strings.json | ✅ stop_not_found etc. |
| **API vor Form** | Calls vor async_show_form() | ✅ Vor Form-Render |
| **Optional-Felder** | vol.Optional() | ✅ direction_name optional |
| **State Management** | Zwischen Steps via self.data | ✅ direction_candidates speichern |
| **Validierung** | Nicht blockierend | ✅ Fehler sind Warnings |
            if stop_products.get(product, False):
                # ← DIESER Stop hat das richtige Produkt!
                direction_id = stop["id"]
                _LOGGER.info(
                    "[sensor] Direction-Name '%s' → Stop-ID: %s [%s] (Product: %s)",
                    direction,
                    stop["name"],
                    direction_id,
                    product
                )
                break  # Aus den Products raus
        
        if direction_id:
            break  # Aus den Stops raus
    
    if not direction_id:
        _LOGGER.error(
            "[sensor] Could not convert direction-name '%s' to Stop-ID "
            "(no match with products: %s)",
            direction,
            ", ".join(config_products)
        )
```

**Vorteile:**
- ✅ Response reichen zur Verfügung stellen, dann **intelligent filtern**
- ✅ Nimmt den **ERSTEN Stop, der ein passendes Produkt enthält** (exakte Produkttyp-Priorisierung)
- ✅ Beispiel: User sucht "Alexanderplatz" im U-Bahn-Sensor (`products=subway`)
  - API gibt 5 Ergebnisse (alle "S+U Alexanderplatz..." + einzelne "U Alexanderplatz")
  - Wir iterieren und nehmen den ERSTEN, bei dem `products.subway = true`
  - → Korrekt gemappt! ✅
- ✅ Verhindert Mismatches, weil wir wirklich prüfen, ob der Stop das Produkt hat
- ✅ Fallback wenn kein Produkt passt: Klare Error-Message mit Details

---

| Phase | Titel | Aufwand | Files | Nutzen |
|-------|-------|---------|-------|--------|
| **1** | Config-Flow mit Stop-Suche + Validierung | 4-5h | `config_flow.py`, `strings.json`, `const.py` | Verhindert zukünftige Fehler |
| **2** | Auto-Migration für alte Configs | 2-3h | `__init__.py` | Behebt 25× bestehende HTTP 500 Fehler |
| **Total** | **v0.1.6 MVP** | **6-8h** | | **Komplette Lösung für Stop-Name-Problem** |

---

## ❓ Feedback-Punkte für dich

1. **Validierung (Schritt 3 Phase 1):** Non-blocking oder blockierend bei Stop nicht gefunden?
   - **Empfehlung:** Non-blocking mit Warnung (Nutzer kann ignorieren)

2. **Migration State-Feld:** Ist `DIRECTION_MIGRATION_STATE` der beste Name?
   - **Alternativen:** `direction_id_migration_status`, `direction_validation_status`
   - **Empfehlung:** `direction_id_migration_status` (explizit)

3. **Feature Gate:** Sollen wir noch andere Gates brauchen?
   - **Empfehlung:** Nur DIRECTION_ID_MIGRATION_ENABLED für diese Phase

4. **Comma-Separated später (v0.1.7)?** Sollen wir das notieren?
   - **Empfehlung:** Ja, separates Feature-Plan-Dokument erstellen

