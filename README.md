# 🚉 Berlin (BVG) & Brandenburg (VBB) Public Transport Departures for Home Assistant

> ℹ️ [Hier klicken](./docs/liesmich.md) für eine deutsche Beschreibung.

**Live public transport data** from Berlin and Brandenburg in your Home Assistant dashboard. Real-time departures, line numbers, destinations, delays — updated every 120 seconds.

Whether you're commuting, picking up your kids, or just wondering when the next Ringbahn arrives, this integration shows upcoming departures in a clean, readable format.

![Example of a real-time public transport display](./docs/screenshots/timetable_card1s.jpg)

## ✨ Features
- **Real-time departures** from Berlin and Brandenburg transport stops with line numbers, destinations, delays, and platforms
- **Dashboard card integration** for clean, user-friendly display
- **Smart filtering**: direction, excluded stops, transport types (bus, tram, ferry, etc.)
- **Customization**: walking time offset, official VBB colors, Ringbahn ⟳/⟲ toggle
- **Dual-API failover**: Redundant fallback chain — Primary → Secondary → BVG API — ensures maximum uptime
- **Resilient caching**: Last successful departures stay visible during API outages
- **Languages**: German and English support

## 💿 Installation

This integration consists of two components:  
1. **Integration** – fetches real-time departure data from Berlin and Brandenburg transport stops  
1. **Dashboard card** – displays the data in a clean, user-friendly format  

You need both components. The recommended way to install is via [HACS](https://hacs.xyz/) for easy updates and seamless integration. The setup takes less than 10 minutes.

If you prefer manual installation, please see the [manual installation guide](./docs/manual_install.md).

### 1️⃣ Add repositories to HACS

Open Home Assistant and go to **HACS → Three dots in top right corner → Custom repositories**. Add both of the following repositories:

- `https://github.com/manoth-msft/home-assistant-bvg-vbb-departures` → Type: **Integration**  
- `https://github.com/manoth-msft/home-assistant-dashboard-card-bvg-vbb-departures` → Type: **Dashboard**

Click **Add**, then reload the HACS page (hit `F5`) to make sure both repositories are available.

### 2️⃣ Search and install components via HACS

1. After refreshing the HACS page, use the search bar and type **bvg**.  
1. We need the following components:
   - **BVG/VBB real-time departures** (Integration)  
   - **Card for BVG/VBB real-time departures integration** (dashboard)
1. Open each entry and select **Download** from the lower‑right corner.
1. Wait for the download to finish. Then refresh the page and restart Home Assistant to activate both components.

### 3️⃣ Add and configure integration

1. Go to **Settings → Devices & services** → **Add Integration**
2. Search for **bvg** and select **BVG/VBB Departures**
3. Enter your stop name (partial names work)
4. Pick your station from the suggestions
5. (Optional) Configure filters, walking time, transport types, etc. → See [Configuration Guide](./docs/configuration.md)
6. Done! First update arrives in 1–2 minutes

### 4️⃣ Add card to dashboard

1. Open any dashboard and add a new card
2. Choose **Custom cards** → **BVG/VBB departures card**
3. Select your entity
4. Adjust display options if needed (delays, relative/absolute time, walking time, etc.)
5. Save!

Done 🎉

## 📖 Documentation

For detailed information, see our guides:

- **[Configuration Guide](./docs/configuration.md)** – All settings explained with examples and scenarios
- **[FAQ](./docs/faq.md)** – Common questions and answers
- **[Troubleshooting](./docs/troubleshooting.md)** – Fixes for common issues

## 🤝 Credits

This project is a fork of the original Berlin Transport integration by [vas3k](https://github.com/vas3k/home-assistant-berlin-transport), with additional filtering, customization options, and ongoing independent maintenance.

## 🤝 Contributions, Bugs & Feature Requests

This project is a small side project, so while I cannot guarantee full support or help with dashboard configuration, I truly appreciate your understanding — and even more your contributions!

- **Contributions**: Pull requests are always welcome. Feel free to [open a PR](https://github.com/manoth-msft/home-assistant-bvg-vbb-departures/pulls) for review.
  If you're unsure about an idea, simply [open an issue](https://github.com/manoth-msft/home-assistant-bvg-vbb-departures/issues) and ask for advice.

- **Bug reports**: If you discover a bug, please [open an issue](https://github.com/manoth-msft/home-assistant-bvg-vbb-departures/issues) and describe the exact steps to reproduce it. Screenshots, logs, and details are very helpful to track down the problem.

- **Feature requests**: Missing a feature? Share your idea in issues — or feel free to try coding it yourself and submit a PR.

## 👮‍♀️ License

- [MIT](./LICENSE.md)
