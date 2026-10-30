# Changelog

All notable changes to the BroodMinder integration for Home Assistant are listed here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - Unreleased

### Added

- The swarm state sensor now explains what its number means, for example
  "Started - checking for swarm event" or "Swarm event detected". You'll find this as a
  description on the sensor.

### Changed

- Temperatures are shown with one decimal and weights with two, instead of a long string of
  digits.
- A device's model is shown by name (for example "TH") instead of a code number.

### Fixed

- If a BroodMinder's clock was never set through the BroodMinder Bees app, the swarm time
  sensor now shows "Unknown" instead of a date around 1970 ("56 years ago").
- Setup messages, such as "Device is already configured", now show properly in Home
  Assistant.

### Internal

- Internal fixes and cleanups that don't change how the integration works: automated tests,
  automatic code checks on GitHub, code style fixes and developer tooling.

## [0.3.0] - 2025-11-20

### Changed

- Device names now include the BroodMinder model and the last part of its Bluetooth
  address, so you can tell several BroodMinders apart more easily.

### Documentation

- The README lists what each swarm state number means.

## [0.2.0] - 2025-11-19

First release.

### Added

- Automatic discovery of BroodMinder devices within Bluetooth range of Home Assistant,
  including through ESPHome Bluetooth proxies. No pairing needed, and it works alongside
  the BroodMinder apps and hubs.
- Sensors for battery, temperature, realtime temperature, humidity, weight (per scale side
  and total), sample count, swarm state and swarm time, depending on the BroodMinder model.

[0.4.0]: https://github.com/sandersmeenk/home_assistant-broodminder/compare/0.3.0...develop
[0.3.0]: https://github.com/sandersmeenk/home_assistant-broodminder/compare/0.2.0...0.3.0
[0.2.0]: https://github.com/sandersmeenk/home_assistant-broodminder/releases/tag/0.2.0
