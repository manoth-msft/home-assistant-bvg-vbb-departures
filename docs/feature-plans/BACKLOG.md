# Product Backlog

**Last Updated:** 2026-07-09  
**Total Items:** 13  
**High Priority:** 3 (P1)

---

## High Priority (P1)

### Editieren vorhandener Stops erlauben
- **Ziel:** Benutzer sollen existierende Stops/Sensoren direkt in der UI editieren können
- **Features:** Ändern von Name, Direction, excluded_stops, etc.
- **Nutzen:** Bessere UX statt Delete + Neuanlage
- **Kontext:** Benötigt Erweiterung des Config Flow mit Edit-Funktion
- **Priorität:** Medium
- **Effort:** 4-6h

### Ausschließen von Stops in modernen Workflow integrieren
- **Ziel:** Excluded Stops nicht mehr über manuelle Stop-ID-Listen, sondern über einen geführten Auswahl-Workflow konfigurieren
- **Nutzen:** Weniger Fehler bei IDs, bessere Bedienbarkeit und schnellere Konfiguration
- **Kontext:** Erweiterung des Config Flow um Suche/Mehrfachauswahl für auszuschließende Haltestellen
- **Priorität:** High (P1)
- **Effort:** 4-6h

### Auswahl von Verkehrsmitteln direkt nach Stationsangabe (neuer KonfigFlow)
- **Ziel:** Reihenfolge im KonfigFlow modernisieren und klar führen
- **Neuer Flow:** Station → Filter 1: Transport types → Filter 2: Direction → Filter 3: Ausschlüsse → Anzeigeoptionen
- **Nutzen:** Schnellere Einrichtung, weniger Fehlkonfigurationen, bessere UX
- **Kontext:** Umbau der Schrittreihenfolge im Config Flow inkl. passender Übersetzungs-/Hilfetexte
- **Priorität:** High (P1)
- **Effort:** 4-6h

---

## Medium Priority (v0.1.7+)

### Löschen vorhandener Entitäten erlauben (P2)
- **Ziel:** Benutzer sollen Stops/Sensoren direkt aus der Integration UI löschen können
- **Nutzen:** Bessere UX statt manuelle YAML-Bearbeitung oder Config Entry Löschen
- **Kontext:** Benötigt Config Flow Erweiterung mit Delete-Funktion pro Stop
- **Priorität:** P2
- **Effort:** 2-3h

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

## Completed (v0.1.5 - v0.1.6)

✅ Dual-API failover system (Primary → Secondary → BVG)  
✅ Endpoint-aware ETag caching  
✅ Feature gates for independent API enable/disable  
✅ Data source attribution  
✅ Direction parameter bug fix (HTTP 500)  
✅ BVG fallback integration  
✅ Enhanced logging and documentation  
✅ Direction stop selection overhaul (guided station search in config flow, no manual Stop-ID lookup)

