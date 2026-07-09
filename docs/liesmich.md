# 🚉 Berlin (BVG) & Brandenburg (VBB) ÖPNV Abfahrten für Home Assistant

Diese Integration bringt **Live-Daten des öffentlichen Nahverkehrs** aus Berlin und Brandenburg direkt in dein Home Assistant Dashboard. Sie ruft Echtzeit-Abfahrten von BVG- und VBB-Haltestellen ab – inklusive Liniennummern, Zielorten, Abfahrtszeiten und Verspätungen. Egal ob zur Arbeit, zum Abholen der Kinder oder einfach, um zu wissen, wann die nächste Ringbahn kommt – diese Integration zeigt die kommenden Abfahrten in einem klaren, gut lesbaren Format.

![Beispiel einer Echtzeit-Anzeige](./screenshots/timetable_card1s.jpg)

## ✨ Funktionen
- **Echtzeit-Abfahrten** von BVG- & VBB-Haltestellen, inklusive Liniennummern, Zielorten und Verspätungen, aktualisiert alle 120 Sekunden
- **Dashboard-Kartenintegration** für eine klare, benutzerfreundliche Anzeige der kommenden Abfahrten
- **Erweiterte Filteroptionen**: 
  - **Richtungsfilter** (mit dedizierter Config-Flow UI, ab v0.1.6): Einfache Suche nach Stationsnamen statt numerischer Stop-IDs
  - Automatische Validierung, ob die Station auf der Strecke existiert
  - Automatische Migration von alten Configs mit Stop-Namen zu numerischen Stop-IDs
  - Ausgeschlossene Haltestellen, Verkehrsmitteltypen (Bus, Tram, Fähre usw.)
- **Anpassungen**: Wegezeiten-Berücksichtigung, offizielle VBB-Linienfarben, Ringbahn ⟳/⟲-Filter
- **Dual-API-Failover**: Redundante Fallback-Kette — Primär → Sekundär → BVG-API — für maximale Verfügbarkeit
- **Resiliente Zwischenspeicherung**: Letzte erfolgreiche Abfahrten bleiben sichtbar während API-Ausfällen
- **Sprachunterstützung** mit deutschen und englischen Übersetzungen

## 💿 Installation

Diese Integration besteht aus zwei Komponenten:  
1. **Integration** – ruft Echtzeit-Abfahrtsdaten von BVG/VBB ab  
1. **Dashboard-Karte** – zeigt die Daten in einem klaren, benutzerfreundlichen Format an  

Beide Komponenten werden benötigt. Die empfohlene Installationsmethode ist über [HACS](https://hacs.xyz/) für einfache Updates und nahtlose Integration. Die Einrichtung dauert weniger als 10 Minuten.

Falls du eine manuelle Installation bevorzugst, siehe die [Anleitung zur manuellen Installation (englisch)](./manual_install.md).

### 1️⃣ Repositories zu HACS hinzufügen

Öffne Home Assistant und gehe zu **HACS → Drei Punkte oben rechts → Custom repositories**.  
Füge beide der folgenden Repositories hinzu:

- `https://github.com/manoth-msft/home-assistant-bvg-vbb-departures` → Typ: **Integration**  
- `https://github.com/manoth-msft/home-assistant-dashboard-card-bvg-vbb-departures` → Typ: **Dashboard**

Klicke auf **Add** und lade anschließend die HACS-Seite neu (Taste `F5`), um sicherzustellen, dass beide Repositories verfügbar sind.

### 2️⃣ Komponenten über HACS suchen und installieren

1. Nach dem Aktualisieren der HACS-Seite nutze die Suchleiste und gib **bvg** ein.  
1. Wir benötigen die folgenden Komponenten:
    - **BVG/VBB real-time departures** (Integration)
    - **Card for BVG/VBB real-time departures integration** (Dashboard)  
1. Öffne jeden Eintrag und wähle **Download** unten rechts.  
1. Warte, bis der Download abgeschlossen ist. Aktualisiere die Seite und starte Home Assistant neu, um beide Komponenten zu aktivieren.  

### 3️⃣ Integration hinzufügen und konfigurieren

1. Gehe zu **Einstellungen → Geräte & Dienste** → **Integration hinzufügen**
2. Suche nach **bvg** und wähle **BVG/VBB Departures**
3. Gib den Namen der Haltestelle ein (Teilnamen werden unterstützt)
4. Wähle deine Station aus den Vorschlägen
5. (Optional) Konfiguriere Filter, Gehzeit, Verkehrsmitteltypen usw. → Siehe [Konfigurationsanleitung](./configuration.md)
6. Fertig! Erste Aktualisierung kommt in 1–2 Minuten

### 4️⃣ Karte zum Dashboard hinzufügen

1. Öffne ein Dashboard und füge eine neue Karte hinzu
2. Wähle **Custom cards** → **BVG/VBB departures card**
3. Wähle deine Entität
4. Passe Anzeigeoptionen bei Bedarf an (Verspätungen, relative/absolute Zeit, Gehzeit usw.)
5. Speichern!

Fertig 🎉

## 📖 Dokumentation

Für detaillierte Informationen siehe unsere Anleitungen:

- **[Konfigurationsanleitung](./configuration.md)** – Alle Einstellungen mit Beispielen und Szenarien erklärt
- **[Häufig gestellte Fragen](./faq.md)** – Antworten auf häufige Fragen
- **[Fehlerbehebung](./troubleshooting.md)** – Lösungen für häufige Probleme

## 🤝 Credits

Dieses Projekt ist ein Fork der ursprünglichen Berlin Transport Integration von [vas3k](https://github.com/vas3k/home-assistant-berlin-transport), mit erweiterten Filtermöglichkeiten, zusätzlichen Anpassungen und unabhängiger Pflege.

## 🤝 Beiträge, Fehlerberichte & Feature Requests

Dies ist ein kleines Nebenprojekt, daher kann ich keinen vollständigen Support oder Hilfe bei der Dashboard‑Konfiguration garantieren. Ich freue mich aber über dein Verständnis — und noch mehr über deine Beiträge!

- **Beiträge**: Pull Requests sind jederzeit willkommen. Du kannst gerne einen [PR eröffnen](https://github.com/manoth-msft/home-assistant-bvg-vbb-departures/pulls) und zur Überprüfung einreichen.  
  Falls du dir bei einer Idee unsicher bist, eröffne einfach ein [Issue](https://github.com/manoth-msft/home-assistant-bvg-vbb-departures/issues) und frage nach Rat.  

- **Fehlerberichte**: Wenn du einen Fehler entdeckst, eröffne bitte ein [Issue](https://github.com/manoth-msft/home-assistant-bvg-vbb-departures/issues) und beschreibe die genauen Schritte zur Reproduktion. Screenshots, Logs und Details helfen sehr bei der Problemlösung.  

- **Feature Requests**: Dir fehlt eine Funktion? Teile deine Idee in den Issues — oder probiere, sie selbst zu implementieren und reiche einen PR ein.  

## 👮‍♀️ Lizenz

- [MIT](./LICENSE.md)
