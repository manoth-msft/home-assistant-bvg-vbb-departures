# 🚉 Berlin (BVG) & Brandenburg (VBB) ÖPNV Abfahrten für Home Assistant

Diese Integration bringt **Live-Daten des öffentlichen Nahverkehrs** aus Berlin und Brandenburg direkt in dein Home Assistant Dashboard. Sie nutzt die offizielle VBB API, um Echtzeit-Abfahrten von BVG- und VBB-Haltestellen abzurufen – inklusive Liniennummern, Zielorten, Abfahrtszeiten und Verspätungen.

Ob auf dem Weg zur Arbeit, beim Abholen der Kinder oder einfach, um zu wissen, wann die nächste Ringbahn kommt – diese Integration zeigt die kommenden Abfahrten deiner gewählten Haltestellen in einem klaren, gut lesbaren Format.

> 🛠️ Dieses Projekt ist ein Fork der ursprünglichen Berlin Transport Integration von [vas3k](https://github.com/vas3k/home-assistant-berlin-transport) — mit erweiterten Filtermöglichkeiten, zusätzlichen Anpassungen und unabhängiger Pflege.

![Beispiel einer Echtzeit-Anzeige am S+U Gesundbrunnen Bahnhof in Berlin, ähnlich wie die Darstellung im Home Assistant Dashboard.](./screenshots/timetable_card2s.jpg)![Weiteres Beispiel](./screenshots/timetable_card3s.jpg)![Weiteres Beispiel](./screenshots/timetable_card1s.jpg)

## ✨ Funktionen
- **Echtzeit-Abfahrten** von BVG- & VBB-Haltestellen, inklusive Liniennummern, Zielorten und Verspätungen, aktualisiert alle 90 Sekunden  
- **Dashboard-Kartenintegration** für eine klare, benutzerfreundliche Anzeige der kommenden Abfahrten  
- **Erweiterte Filteroptionen**: Richtung, ausgeschlossene Haltestellen, Verkehrsmitteltypen (Bus, Tram, Fähre usw.)  
- **Anpassungen**: Wegezeiten-Berücksichtigung, Zeitfenster, offizielle VBB-Linienfarben, Ringbahn ⟳/⟲-Filter
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

1. Unter `Einstellungen → Geräte & Dienste` wähle **Integration hinzufügen**, suche nach **bvg** und wähle **BVG/VBB Departures**.  
1. Gib den Namen der Haltestelle ein, die du überwachen möchtest. Teilnamen werden unterstützt. Klicke auf **OK**, wähle deine Station aus der Trefferliste und bestätige mit **OK**.  
1. (Optional) Konfiguriere zusätzliche Parameter wie Richtungsfilter, ausgeschlossene Haltestellen, Gehzeit, Ringbahn-Optionen und mehr.  
   → Siehe [Zusätzliche Konfigurationsdetails](#integration) für eine vollständige Übersicht.  
1. Klicke abschließend auf **OK** und **Fertig**. Die Entität wird erstellt und erhält ihr erstes Update innerhalb von 1–2 Minuten.  

### 4️⃣ Karte zum Dashboard hinzufügen

1. Öffne das Dashboard deiner Wahl und füge eine neue Karte hinzu.  
1. Unter **Custom cards** wähle die **BVG/VBB departures card**.  
1. Wähle die gerade erstellte Entität aus und passe die Konfiguration bei Bedarf an.  
   → Konfigurationsoptionen sind [hier](#card) beschrieben.  
1. Speichere die Karte. Innerhalb weniger Minuten wird sie aktualisiert und zeigt die Echtzeit-Abfahrten von BVG/VBB an.  

Fertig 🎉

## ⚙️ Zusätzliche Konfigurationsdetails
### 🔧 Integration

- **Richtung**: Verwende `stop_id`, um Abfahrten nach Richtung zu filtern. Gib die `stop_id` einer Haltestelle entlang der gewünschten Linie oder des Endziels an. Mehrere Werte können als kommaseparierte Liste angegeben werden. Siehe [unten](#how-do-i-find-my-stop_id), wie du die `stop_id` findest.  
- **Haltestellen ausschließen**: Liste von `stop_id`‑Werten, um nahegelegene Haltestellen auszuschließen. Mehrere Werte können als kommaseparierte Liste angegeben werden.  
- **Zeitraum**: Legt fest, wie viele Minuten in die Zukunft Abfahrten abgerufen werden (Standard: 10).  
- **Gehminuten**: Gib die benötigte Zeit ein, um zur Haltestelle zu laufen. Dadurch werden nicht erreichbare Abfahrten ausgeblendet.  
- **Offizielle VBB‑Linienfarben verwenden**: Optional können die offiziellen VBB‑Linienfarben aktiviert werden. Standardmäßig werden vordefinierte Farben genutzt.  
- **Ringbahn ⟳/⟲ ausblenden**: Optional können Ringbahn‑Verbindungen im Uhrzeigersinn oder gegen den Uhrzeigersinn ausgeblendet werden.  
- **Zusatz (Berlin) aus Stationsnamen entfernen**: Entfernt automatisch das Suffix „(Berlin)“ aus Stationsnamen.  
- **Verkehrsmitteloptionen**: Wähle, welche Verkehrsmitteltypen (z. B. Bus, Fähre) angezeigt oder ausgeblendet werden sollen.  

#### 📝 Beispielkonfiguration

Angenommen, du möchtest die S‑Bahn‑Abfahrten von **S Treptower Park** überwachen.  
Du willst nur Züge sehen, die nach **S+U Neukölln** fahren, Abfahrten von der nahegelegenen Bushaltestelle ausschließen und die nächsten 30 Minuten erfassen.  
Da du etwa 10 Minuten bis zur Station benötigst, sollen nicht erreichbare Abfahrten ausgeblendet werden.  
Außerdem möchtest du die Ringbahn ⟲ (die technisch ebenfalls nach S+U Neukölln fährt) nicht sehen und bevorzugst die Anzeige ohne das Suffix **(Berlin)**.  

Deine zusätzliche Konfiguration würde dann so aussehen:

- **Richtung**: `900078201` (S+U Neukölln)  
- **Ausgeschlossene Haltestellen**: `900190702` (Bushaltestelle am S Treptower Park)  
- **Zeitraum**: `30` Minuten  
- **Gehminuten**: `10` Minuten  
- **Ringbahn ⟲ ausblenden**: aktiviert  
- **Suffix (Berlin) entfernen**: aktiviert  
- **Verkehrsmitteloptionen**: alle deaktiviert außer **S‑Bahn**  

### 🗂️ Karte

- **Stornierte Abfahrten anzeigen**: Entscheide, ob stornierte Abfahrten angezeigt werden sollen.  
  Wenn aktiviert, erscheinen sie durchgestrichen in der Liste; andernfalls werden sie ausgeblendet.  

- **Verspätungen anzeigen**: Wähle, ob gemeldete Verspätungen angezeigt werden sollen.  
  Wenn aktiviert, wird die Verspätung neben der Abfahrtszeit dargestellt.  

- **Absolute Abfahrtszeit anzeigen**: Zeigt die exakte geplante Abfahrtszeit.  

- **Relative Abfahrtszeit anzeigen**: Zeigt den Countdown bis zur Abfahrt (z. B. „in 5 Minuten“).  

- **Gehzeit von relativer Abfahrtszeit abziehen**: Zieht deine Gehzeit zur Haltestelle vom Countdown ab.  
  Beispiel: Wenn der Bus in 15 Minuten fährt und du 10 Minuten Gehzeit konfiguriert hast, zeigt die Karte an, dass du in 5 Minuten losgehen musst, um den Bus zu erreichen.

## ❓ FAQ
### Q: Wie finde ich meine stop_id?

Die primäre Haltestelle, die du auswählst, wird automatisch von der Integration aufgelöst.  
Nur für erweiterte Konfigurationsoptionen wie **Richtung** oder **Ausgeschlossene Haltestellen** musst du die `stop_id` nachschlagen.

Um eine `stop_id` zu finden, kannst du die VBB API abfragen. Öffne den folgenden Link in einem neuen Fenster und ersetze `alexanderplatz` durch den Namen deiner Haltestelle. Teilweise Übereinstimmungen werden unterstützt.

**https://v6.vbb.transport.rest/locations?results=1&query=alexanderplatz**

Die API liefert eine Antwort ähnlich wie:

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
Das erste `"id"`‑Feld enthält die benötigte `stop_id` — in diesem Beispiel: **900100003**.

---

### Q: Welche Datenquelle nutzt dieser Sensor?
A: Der Sensor verwendet die öffentliche VBB API, um alle Verkehrsdaten abzurufen.  
- API‑Dokumentation: [https://v6.vbb.transport.rest/api.html](https://v6.vbb.transport.rest/api.html)  
- Rate Limit: 100 Anfragen pro Minute  
- Datenformat: [HAFAS](https://github.com/public-transport/hafas-client)

---

### Q: Wie oft aktualisiert sich die Komponente?
A: Die Komponente aktualisiert sich alle 90 Sekunden. Für jede Haltestelle wird eine separate Anfrage gestellt. Das ist in der Regel ausreichend, aber es wird nicht empfohlen, Dutzende von Haltestellen hinzuzufügen, um das Rate Limit nicht zu überschreiten.

---

### Q: Was passiert, wenn die VBB API Fehler zurückgibt?
A: Die API kann gelegentlich 503‑ oder Timeout‑Fehler zurückgeben, bedingt durch temporäre Instabilität. Diese beeinträchtigen die Funktionalität der Integration nicht, außer dass Warnmeldungen im Home Assistant Log erscheinen. Derzeit gibt es dafür keine zuverlässige Lösung.

---

### Q: Welche Entitäten werden durch die Integration erstellt?
A: Für jede Haltestelle erstellt die Integration eine Entität. Die kommenden Abfahrten werden in `attributes.departures` gespeichert. Der Entitätszustand selbst dient hauptsächlich der menschenlesbaren Anzeige der nächsten Abfahrt.

---

### Q: Wie kann ich Konfigurationsoptionen später ändern?
A: Gehe zu **Einstellungen > Geräte & Dienste**, wähle die Integration **BVG/VBB Abfahrten** und klicke auf die drei Punkte neben der Entität, die du aktualisieren möchtest. Lösche den Eintrag.  
Wähle anschließend **Dienst hinzufügen** und füge die Haltestelle mit der angepassten Konfiguration erneut hinzu.  
Die neue Entität erhält dieselbe ID wie die vorherige, sodass deine Dashboards nicht angepasst werden müssen.

---

### Q: Kann ich die Integration auch außerhalb von Berlin und Brandenburg nutzen?
A: Ja. Die Integration basiert auf dem standardisierten HAFAS‑Format, das auch in vielen anderen Städten verwendet wird. Dadurch lässt sich die Komponente prinzipiell auch für andere Orte anpassen.

---

## 🤝 Beiträge, Fehlerberichte & Feature Requests

Dies ist ein kleines Nebenprojekt, daher kann ich keinen vollständigen Support oder Hilfe bei der Dashboard‑Konfiguration garantieren. Ich freue mich aber über dein Verständnis — und noch mehr über deine Beiträge!

- **Beiträge**: Pull Requests sind jederzeit willkommen. Du kannst gerne einen [PR eröffnen](https://github.com/manoth-msft/home-assistant-bvg-vbb-departures/pulls) und zur Überprüfung einreichen.  
  Falls du dir bei einer Idee unsicher bist, eröffne einfach ein [Issue](https://github.com/manoth-msft/home-assistant-bvg-vbb-departures/issues) und frage nach Rat.  

- **Fehlerberichte**: Wenn du einen Fehler entdeckst, eröffne bitte ein [Issue](https://github.com/manoth-msft/home-assistant-bvg-vbb-departures/issues) und beschreibe die genauen Schritte zur Reproduktion. Screenshots, Logs und Details helfen sehr bei der Problemlösung.  

- **Feature Requests**: Dir fehlt eine Funktion? Teile deine Idee in den Issues — oder probiere, sie selbst zu implementieren und reiche einen PR ein.  

---

## 👮‍♀️ Lizenz

- [MIT](./LICENSE.md)
