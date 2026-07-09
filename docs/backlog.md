# Backlog

## Open Ideas

- Make domain unique
  - Ziel: Domain in Home Assistant eindeutig machen (derzeit "berlin_transport")
  - Kontext: Könnte mit anderen Integrations kollidieren; unique prefix (z.B. "bvg_transport") empfohlen
  - Impact: Migration guide für bestehende Nutzer benötigt
  - Priorität: Mittelhoch (vor Bronze Rating)

- Improve direction stop selection ⚠️ PRIORITÄT ERHÖHT
  - Ziel: UX für Direction-Filterung verbessern (aktuell: manuelle Stop-ID-Eingabe erforderlich)
  - **Problem gefunden** (API-Log-Analyse): Nutzer geben Stop-NAMEN statt Stop-IDs ein!
    - Nutzer schreiben z.B. `direction=Tegel` oder `direction=S Heiligensee`
    - API antwortet mit HTTP 500 "direction must be an IBNR"
    - Müssen Stop-IDs sein: `direction=900091203`
  - Nutzen: 
    - Dropdown-Liste mit Stop-ID Suggestions nach Stationsnamen-Eingabe
    - Validierung im Config Flow (Fehler wenn Stop-Name eingegeben)
    - Hilfetexte verstärken (z.B. "Stop-ID erforderlich, nicht Stationsname")
  - Kontext: Config Flow könnte Richtungs-Suggestions von API laden und anzeigen
  - Priorität: **HOCH** (Nutzer-Fehler, HTTP 500 im Feld, UX-Verbesserung)

- Reach HA bronze, silver, gold rating
  - Ziel: Integration durch Community Feedback und kontinuierliche Verbesserungen nach oben bewerten lassen
  - Bronze → Silver → Gold: Stellt höhere Standards für Code Quality, Documentation, Testing dar
  - Scope: Code Quality, Error Handling, Logging, Documentation, User Experience
  - Roadmap-Item für Long-Term Integration Health

- Evaluate upstream PR: Selfhost fixes (Hub hinzufügen prüfen)
  - Link: https://github.com/vas3k/home-assistant-berlin-transport/pull/70
  - Scope: Review changes for hub support in self-hosted environments

- Editieren vorhandener stops erlauben
  - Ziel: Benutzer sollen existierende Stops/Sensoren direkt in der UI editieren können (z.B. Name, Direction, excluded_stops ändern)
  - Nutzen: Bessere UX statt Delete + Neuanlage
  - Kontext: Benötigt wahrscheinlich Erweiterung des Config Flow mit Edit-Funktion

- Löschen vorhandener Entitäten erlauben
  - Ziel: Benutzer sollen Stops/Sensoren direkt aus der Integration UI löschen können
  - Nutzen: Bessere UX statt manuelle YAML-Bearbeitung oder Config Entry Löschen
  - Kontext: Benötigt Config Flow Erweiterung mit Delete-Funktion pro Stop

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

- Direction-Sanitizing: Mehrere Stop-IDs per Komma auf erste ID reduzieren
  - Ziel: Falls `direction` als kommagetrennte Liste gespeichert ist (z. B. `900001203,900003201`), nur die erste Stop-ID behalten
  - Kontext: Kommt aus Legacy-/Fehlkonfigurationen; API erwartet genau eine IBNR
  - Akzeptanzkriterium: Nach Migration/Sanitizing ist `direction` immer genau eine einzelne numerische Stop-ID oder leer
