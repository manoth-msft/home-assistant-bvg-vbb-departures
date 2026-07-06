# Changelog

All notable changes to this project will be documented in this file.

## [Upcoming]
### Fixed
- Fixed expired departures appearing on dashboard

### Changed
- Increased departures fetch duration from 30 to 60 minutes
- Increased API result limit from 15 to 30 departures per request

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
