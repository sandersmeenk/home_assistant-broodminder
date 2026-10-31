# Changelog

All notable changes to the BroodMinder integration for Home Assistant are listed here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - Unreleased

### Added

- The swarm state sensor now explains what its number means, for example
  "Started - checking for swarm event" or "Swarm event detected". You'll find this as a
  description on the sensor.
- BroodMinder DIY scales now show their weight: Weight Left, Weight Right, Weight Left 2,
  Weight Right 2 and Weight Realtime.
- The original BroodMinder-W scale (model 43) now shows the total hive weight as Weight
  Realtime. This scale weighs one side of the hive, so the total is twice the left plus right
  weight.

### Changed

- Temperatures are shown with one decimal and weights with two, instead of a long string of
  digits.
- A device's model is shown by name (for example "TH") instead of a code number.

### Fixed

- If a BroodMinder's clock was never set through the BroodMinder Bees app, the swarm time
  sensor now shows "Unknown" instead of a date around 1970 ("56 years ago").
- Setup messages, such as "Device is already configured", now show properly in Home
  Assistant.
- The original BroodMinder-W scale (model 43) no longer shows a realtime temperature of
  −40 °C, or impossible weights such as −327 kg for Weight Left 2, Weight Right 2 and Weight
  Realtime.
- Realtime temperature is only shown for BroodMinders that measure it. The original
  BroodMinder-T and -TH (models 41 and 42), the SubHub, the hubs and the BeeDar no longer show
  a meaningless value.
- Scale weights of 0.00 kg and 0.06 kg, for example on an empty scale, are no longer ignored.
- Sensors that are no longer created stay listed in Home Assistant as no longer provided: Realtime
  Temp on the models above, and Weight Left 2 and Weight Right 2 on the BroodMinder-W
  (model 43). You can delete them from the device page.

### Documentation

- The README has a table showing which sensors each BroodMinder model gets.
- The README's list of supported devices now includes model numbers and DIY scales, and says
  which devices are only partly supported or not supported yet.

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
