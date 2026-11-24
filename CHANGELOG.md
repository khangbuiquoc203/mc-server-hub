# Changelog

All notable changes to this project are documented here. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-11-24

### Added

- Dark desktop window for many Minecraft servers started from existing BAT files.
- One console with per-server colors, filter, search, export, and a bounded in-memory view.
- Console commands sent to the selected server's stdin.
- Crash detection from the process tree, including a BAT file stopped on `pause`.
- Per-server auto restart with delay, a maximum attempt count, and an unlimited option.
- A background supervisor so closing the window can leave servers running without orphaning them.
- Portable PyInstaller onedir build via `build.bat`.
- MIT license for this source, with third-party and Minecraft trademark notices.
