# Changelog

All notable changes to this project will be documented in this file.

## [0.1.4.0] - Upcoming
### Fixed
- Improved network error handling in stop search and departures fetch by also catching generic request failures
- Improved log granularity for API failures (timeouts, connection errors, HTTP errors, and explicit 429 rate limits with `Retry-After`)
- Prevented crashes when API responses contain missing or malformed departures payloads
- Prevented config flow crashes on unexpected stop selection mismatches
- Normalized comma-separated excluded stop IDs (whitespace is now ignored)
- Fixed type annotation mismatch for departure time (`time` is stored as string)
- Reduced debug log verbosity by avoiding full raw API payload logging
- Sensor is now marked unavailable when fallback data expires or no cached departures remain during API outages
- Cached departures are now pruned continuously even while retry backoff is active

### Changed
- Reduced default polling frequency from 90s to 120s to lower API pressure
- Added stale-if-error behavior: keep and serve last successful departures for up to 15 minutes when API calls fail
- Added adaptive retry backoff after repeated API failures to avoid hammering an unstable endpoint
- Migrated network I/O to async (`aiohttp`) and sensor refresh to `async_update` to avoid blocking Home Assistant (@mrueg)
- Updated config flow stop search to non-blocking async HTTP requests
- Exposed warning remarks from departures (`attributes.departures[].warnings`) (@mrueg)

## [0.1.3.1] - 2026-01-14
### Changed
- Fixed broken URLs in documentation (@tom71)

## [0.1.3] - 2025-11-14
### Added
- Option to hide the "(Berlin)" suffix in stop and direction names
- Installation instructions localized in German

### Changed
- Improved accessibility by replacing JSON screenshots with embedded code examples
- Completely rewrite of documentation for improved clarity and consistency

---

## [0.1.2] - 2025-11-06
### Added
- Option to filter Ringbahn departures by direction (`exclude_ringbahn_clockwise`/`exclude_ringbahn_counterclockwise`)

### Changed
- Forked integration from https://github.com/vas3k/home-assistant-berlin-transport
- Renamed integration

---

## [0.1.1] - 2025-10-28

### Changed
- Improved stop search matching during initial configuration
- Updated UI translations for German and English
