# Product Backlog

**Last Updated:** 2026-07-08  
**Total Items:** 13  
**High Priority:** 1 (Direction Stop Management)

---

## High Priority (v0.1.6)

### Improve direction stop selection ⚠️ PRIORITÄT ERHÖHT
- **Status:** Planning → See [v0.1.6_direction_management.md](v0.1.6_direction_management.md)
- **Ziel:** UX für Direction-Filterung verbessern (aktuell: manuelle Stop-ID-Eingabe erforderlich)
- **Problem gefunden** (API-Log-Analyse): Nutzer geben Stop-NAMEN statt Stop-IDs ein!
  - Nutzer schreiben z.B. `direction=Tegel` oder `direction=S Heiligensee`
  - API antwortet mit HTTP 500 "direction must be an IBNR"
  - Müssen Stop-IDs sein: `direction=900091203`
- **Lösung:** Subentry-Pattern + Stop-Name Lookup + Auto-Migration
- **Priorität:** **HOCH** (Nutzer-Fehler, HTTP 500 im Feld, dokumentierte Funktionalität)
- **Effort:** 14-18h
- **Target Release:** v0.1.6

---

## Medium Priority (v0.1.7+)

### Make domain unique
- **Ziel:** Domain in Home Assistant eindeutig machen (derzeit "berlin_transport")
- **Kontext:** Könnte mit anderen Integrations kollidieren; unique prefix (z.B. "bvg_transport") empfohlen
- **Impact:** Migration guide für bestehende Nutzer benötigt
- **Priorität:** Mittelhoch (vor Bronze Rating)
- **Effort:** 4-6h

### Reach HA bronze, silver, gold rating
- **Ziel:** Integration durch Community Feedback und kontinuierliche Verbesserungen nach oben bewerten lassen
- **Bronze → Silver → Gold:** Stellt höhere Standards für Code Quality, Documentation, Testing dar
- **Scope:** Code Quality, Error Handling, Logging, Documentation, User Experience
- **Priorität:** Long-term Roadmap Item
- **Effort:** Ongoing

### Konfigurierbare Schalter für Resilienz-Parameter
- **Ziel:** Fallback-Zeit (stale cache) und maximale Backoff-Dauer pro Entität über Config Flow einstellbar machen
- **Nutzen:** Feintuning je nach API-Stabilität und persönlicher Update-Präferenz
- **Scope:**
  - Neue optionale Felder im Config Flow
  - Persistenz in Config Entry
  - Verwendung im Sensor-Update-Pfad (Fallback/Backoff)
  - Kurze Doku-Ergänzung
- **Priorität:** Medium (Quality of Life)
- **Effort:** 6-8h

### Editieren vorhandener Stops erlauben
- **Ziel:** Benutzer sollen existierende Stops/Sensoren direkt in der UI editieren können
- **Features:** Ändern von Name, Direction, excluded_stops, etc.
- **Nutzen:** Bessere UX statt Delete + Neuanlage
- **Kontext:** Benötigt Erweiterung des Config Flow mit Edit-Funktion
- **Priorität:** Medium
- **Effort:** 4-6h

### Löschen vorhandener Entitäten erlauben
- **Ziel:** Benutzer sollen Stops/Sensoren direkt aus der Integration UI löschen können
- **Nutzen:** Bessere UX statt manuelle YAML-Bearbeitung oder Config Entry Löschen
- **Kontext:** Benötigt Config Flow Erweiterung mit Delete-Funktion pro Stop
- **Priorität:** Medium
- **Effort:** 2-3h

---

## Upstream PRs (Evaluation & Integration)

### PR #70: Selfhost fixes (Hub hinzufügen prüfen)
- **Link:** https://github.com/vas3k/home-assistant-berlin-transport/pull/70
- **Scope:** Review changes for hub support in self-hosted environments
- **Status:** Pending Review
- **Effort:** 1-2h Review

### PR #65: Add reconfigure flow for existing sensors
- **Link:** https://github.com/vas3k/home-assistant-berlin-transport/pull/65
- **Status:** Pending Review
- **Effort:** 1-2h Review

### PR #64: Set unique ID from config flow entry to allow multiple sensors per stop
- **Link:** https://github.com/vas3k/home-assistant-berlin-transport/pull/64
- **Status:** Pending Review
- **Effort:** 1-2h Review

### PR #63: Expose warnings
- **Link:** https://github.com/vas3k/home-assistant-berlin-transport/pull/63
- **Status:** Pending Review
- **Effort:** 1h Review

### PR #61: Allow exclusion of specific lines
- **Link:** https://github.com/vas3k/home-assistant-berlin-transport/pull/61
- **Status:** Pending Review
- **Effort:** 1-2h Review

### PR #60: Add latitude and longitude attributes to TransportSensor
- **Link:** https://github.com/vas3k/home-assistant-berlin-transport/pull/60
- **Status:** Pending Review
- **Effort:** 1-2h Review

---

## Low Priority / Deferred

### Rollback task: Re-enable configurable `duration`
- **Ziel:** `duration` wieder als nutzerseitige Option im Config Flow und in YAML verfügbar machen
- **Kontext:** 30-Minuten-Hardcode ist nur als temporäre Stabilitätsmassnahme aktiv
- **Priorität:** Low (nach API-Stabilität Verbesserungen)
- **Effort:** 1-2h

---

## Completed (v0.1.5)

✅ Dual-API failover system (Primary → Secondary → BVG)  
✅ Endpoint-aware ETag caching  
✅ Feature gates for independent API enable/disable  
✅ Data source attribution  
✅ Direction parameter bug fix (HTTP 500)  
✅ BVG fallback integration  
✅ Enhanced logging and documentation  

