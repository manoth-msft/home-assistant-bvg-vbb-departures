# Backlog

## Open Ideas

- Konfigurierbare Schalter fuer Resilienz-Parameter in der Integration
  - Ziel: Fallback-Zeit (stale cache) und maximale Backoff-Dauer pro Entitaet ueber den Config Flow einstellbar machen.
  - Nutzen: Feintuning je nach API-Stabilitaet und persoenlicher Update-Praeferenz.
  - Scope (spaeter):
    - Neue optionale Felder im Config Flow
    - Persistenz in Config Entry
    - Verwendung im Sensor-Update-Pfad (Fallback/Backoff)
    - Kurze Doku-Ergaenzung und Changelog-Eintrag

- Evaluate upstream PR: Add latitude and longitude attributes to TransportSensor
  - Link: https://github.com/vas3k/home-assistant-berlin-transport/pull/60

- Evaluate upstream PR: Add reconfigure flow for existing sensors
  - Link: https://github.com/vas3k/home-assistant-berlin-transport/pull/65

- Evaluate upstream PR: Set unique ID from config flow entry to allow multiple sensors per stop
  - Link: https://github.com/vas3k/home-assistant-berlin-transport/pull/64

- Evaluate upstream PR: Expose warnings
  - Link: https://github.com/vas3k/home-assistant-berlin-transport/pull/63

- Evaluate upstream PR: Allow exclusion of specific lines
  - Link: https://github.com/vas3k/home-assistant-berlin-transport/pull/61

- Rollback task: Remove temporary hardcoded 30-minute departures fetch and re-enable configurable `duration`
  - Ziel: `duration` wieder als nutzerseitige Option im Config Flow und in YAML verfuegbar machen
  - Kontext: 30-Minuten-Hardcode ist nur als temporaere Stabilitaetsmassnahme aktiv
