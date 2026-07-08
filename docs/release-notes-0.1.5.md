# 🚀 v0.1.5 - Redundancy & Reliability Update

## 🎯 Highlights

### ✨ Dual-API Failover System (New)
Your integration is now **bulletproof**. We implemented a resilient failover chain to ensure maximum uptime:

```
🔴 Primary (v6.vbb.transport.rest)
    ↓ fails immediately
🟡 Secondary (we1external.dynv6.net:8500)
    ↓ fails immediately  
🟢 BVG Fallback API (with exponential backoff)
```

- **No delays between failovers** — instant fallback when primary goes down
- **Endpoint-aware caching** — separate ETags prevent API conflicts
- **Stop search resilience** — Config UI also uses dual-API for better UX
- **Smart data retention** — Last successful departures stay visible during outages

### 🔧 Critical Fixes

**Direction Parameter Bug (HTTP 500 errors)**
Fixed a showstopper where empty direction parameters were sent as `direction=` instead of being omitted. This caused API rejects with "direction must be an IBNR" for ~70% of sensors without direction filtering.

### 📊 What's New

- **BVG Fallback Integration** — When transport.rest is down, data flows from BVG API with smart merge of delay info
- **Better Error Messages** — Config UI now shows specific errors ("API rate limited", "timeout", "unreachable") instead of vague messages
- **Optimized Backoff** — Reduced max backoff from 15→10 minutes, smarter retry strategy
- **Enhanced Logging** — See which API is serving data, cache hits, merge statistics

## 📚 Documentation

- Updated **README** with dual-failover feature
- New **FAQ**: "What happens if the primary API fails?"
- Enhanced **Troubleshooting**: Failover sequence explained
- **docs/liesmich.md** (German): Full dual-API description

---

**Need Help?** Check the [FAQ](./faq.md#q-what-happens-if-the-primary-api-fails) or [Troubleshooting](./troubleshooting.md) guides.
