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
