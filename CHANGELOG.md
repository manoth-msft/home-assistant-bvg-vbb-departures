# Changelog

All notable changes to this project will be documented in this file.

## [0.1.5] - 2026-07-07

### Fixed
- **CRITICAL:** Fixed API query parameter bug where empty direction values were sent as `direction=` (empty string) instead of omitting the parameter entirely. This caused HTTP 500 errors "direction must be an IBNR" for all sensors without direction filtering. Direction parameter is now only included when it contains a valid value.

### Changed
- Set a proper `User-Agent` header for all API requests, dynamically built from `manifest.json` (version + documentation URL). Previously, transport.rest requests used the generic Home Assistant User-Agent; BVG API requests used a static placeholder string.
- **Enabled BVG fallback API** when transport.rest experiences outages. BVG now serves as an active fallback during transport.rest failures, applying only transport type filters (bus, subway, etc.). Direction filtering is not possible due to limitations of the API used. BVG API integration based on the work by [@select](https://github.com/select).
- **Smart merge of BVG delays into cached departures**: When transport.rest fails but we have cached data, the integration now merges fresh delay information from BVG API into the previously filtered departures. This preserves the user's direction filtering while keeping delays up-to-date.
- **Optimized backoff strategy**: Reduced maximum backoff from 15 to 10 minutes. BVG fallback is now called immediately on transport.rest failure, but subsequent retries respect the backoff period (no redundant API calls every 120 seconds during backoff).
- Improved fallback logging to show the impact of transport type filters (raw departures vs. after filtering) and data merge statistics (matched/unmatched departures).
- **Improved config flow error messages**: When stop search fails, the UI now shows specific error details (e.g., "API rate limited", "timeout", "unreachable") and actionable guidance ("Try again in a few minutes") instead of a generic error. Also distinguishes between API failures and "no stops found" scenarios with appropriate guidance.

## [0.1.4.2] - 2026-07-07

### Known Limitations (API Availability)
Due to the transport.rest API's unstable availability and rate limiting, the following limitations apply:
- Creating new sensors may fail if the config UI cannot load stops from the API. If this happens, wait a few minutes and try again.
- Lovelace cards will not display until at least one successful sensor update has completed. This is expected behavior as the integration requires initial data before rendering UI elements.

### Fixed
- Optimized departure deduplication performance with hash caching (reduces CPU cycles).
- Optimized state attribute regeneration with caching (reduces CPU cycles and I/O).
- Improved ETag cache cleanup with time-based TTL to prevent memory bloat.
- Fixed race condition in async state updates.
- Added proper resource cleanup when sensors are removed.
- Refactored magic numbers into named constants for maintainability.
- Improved logging with comprehensive debug information (200 OK, 304 Not Modified) and standardized formatting across all modules.
- Added comprehensive docstrings and type hints following modern Python 3.10+ syntax.
- Added UTC timezone validation to prevent datetime comparison bugs.
- Improved sensor availability handling: entity stays available even when no departures are displayed, ensuring debug attributes (health_status, last_updated, health_details) remain visible during API outages.

### Added
- Direction name collection from transport.rest API for sensors with single-direction filters (v0.1.5 preparation for improved BVG fallback filtering).


## [0.1.4.1] - 2026-07-06
### ⚠️ Breaking Change
If you updated to 0.1.4.0 and adjusted your dashboards to use the `_2` suffixed sensors (e.g., `sensor.s_wannsee_bhf_berlin_2`), you will need to update them back to the original sensor names (e.g., `sensor.s_wannsee_bhf_berlin`) after updating to 0.1.4.1. The fix restores backward compatibility with 0.1.3.x, which means sensor entity IDs return to their original names.

### Fixed
- **CRITICAL:** Fixed sensor recreation issue when updating from 0.1.3.x to 0.1.4.x. Sensor entity IDs are now preserved during updates (no more `_2` suffix)
- Fixed timezone crash in expired departures pruning (naive vs timezone-aware datetime comparison)
- Fixed UTC inconsistency throughout codebase (replaced deprecated `datetime.utcnow()` with `datetime.now(timezone.utc)`)
- Fixed unbounded memory growth in ETag cache (now keeps max 10 recent request keys with automatic cleanup)
- Fixed expired departures appearing on dashboard
- Improved logging with proper % formatting instead of f-strings for better Home Assistant structured logging
- Increased departures duration from 30 to 60 minutes
- Increased API results from 15 to 20 per request

## [0.1.4] - 2026-07-05
### Fixed
- Improved network error handling in stop search and departures fetch by also catching generic request failures
- Improved log granularity for API failures (timeouts, connection errors, HTTP errors, and explicit 429 rate limits with `Retry-After`)
- Prevented crashes when API responses contain missing or malformed departures payloads
- Prevented config flow crashes on unexpected stop selection mismatches
- Normalized comma-separated excluded stop IDs (whitespace is now ignored)
- Fixed type annotation mismatch for departure time (`time` is stored as string)
- Reduced debug log verbosity by avoiding full raw API payload logging
- Kept the last successful departures cache visible during API outages instead of dropping it, with `data_is_stale`, `last_updated`, `last_updated_ago`, `health_status`, and `health_details` attributes for UI visibility
- Fixed departures request crashes on newer aiohttp/yarl versions by converting boolean transport filters to API-safe query values

### Added
- New sensor attribute `last_updated` with the timestamp of the last successful API update (`datetime` or `null`)
- New sensor attribute `last_updated_ago` as human-readable age (`"gerade eben"`, `"vor X Minuten"`, or `null`)
- New sensor attribute `data_is_stale` with explicit stale flag (`true` or `false`)
- New sensor attribute `health_status` with values: `ok`, `stale`, `backoff`, `degraded`, `no_data`
- New sensor attribute `health_details` with a short explanatory text for the current health state

### Changed
- Reduced default polling frequency from 90s to 120s to lower API pressure
- Increased API request timeout from 30s to 240s for both sensor updates and stop search in the configuration flow
- Temporarily hardcoded departures fetch duration to 30 minutes and removed the user-facing duration setting
- Added stale-if-error behavior: keep and serve last successful departures indefinitely during API failures, while marking the sensor stale via attributes
- Added ETag-based conditional requests (`If-None-Match`) and 304 cache reuse per request variant to reduce payload and parsing overhead, with debug logging for request/cache behavior
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
