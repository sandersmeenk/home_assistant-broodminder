# BroodMinder integration for Home Assistant

The BroodMinder integration allows you to monitor BroodMinder devices through Home Assistant.

If your BroodMinder device is within Bluetooth range of your Bluetooth capable Home Assistant server and the Bluetooth integration is loaded, the BroodMinder should be discovered automatically. If there are multiple BroodMinders nearby, each device will be represented as an individual device within Home Assistant.

Home Assistant can then be used to draw plots with the provided hive's weight, temperature, humidity and swarm indicator. It can also be used to set up automations, alarms and notifications in case of specific events.

Once the integration is set up, Home Assistant will receive and parse the Bluetooth advertisements of each BroodMinder device. The BroodMinder device does not need to be paired with Home Assistant, so long as the device implements the Bluetooth advertisement according to [BroodMinder's documentation](https://doc.mybroodminder.com/87_physics_and_tech_stuff).

This integration works alongside the official BroodMinder mobile apps (e.g. 'Bees') and BroodMinder hubs.

## What is BroodMinder?

BroodMinder is a series of products designed to track different activities in a beehive.

**Temperature and brood**
Bees excel at thermoregulating their hive, and they do so primarily for one reason: to raise brood. When there’s no brood, there's little incentive to regulate temperature (with rare exceptions). When the colony is strong and full of brood, it maintains a stable internal temperature of 35°C / 95°F. This is what we call the Optimal Brood Zone. Conversely, when there is no brood, the bees let the internal temperature follow ambient conditions. In this case, the values will be closer to outside temperatures. Hence, by measuring the temperature with a BroodMinder device, it is possible to get a sense of the brood activity of the hive.

**Weight and brood**
Tracking and experiencing nectar flows is an interesting aspect of beekeeping. Plants release nectar, bees find it, and bring it home. A hive scale can provides insights in when a nectar flow starts, how long it lasts,
how intense it is, and in the winter: how rapidly the bees are consuming their winter stores. By monitoring the weight of the hive with a BroodMinder device, it is possible to quantify and visualize these effects.

**Temperature, weight and swarming**
The BroodMinder contains a feature called SwarmMinder, that helps detecting a colony swarming.
For more documentation on the SwarmMinder feature, see [BroodMinder documentation](https://doc.mybroodminder.com/31_sensors_T_TH), chapter "SwarmMinder Details".

## Increasing Bluetooth range

When the bee hives are outside of the Bluetooth range of the Home Assistant server, a Bluetooth repeater or proxy can be set up to increase the Bluetooth range.

One solution to increase the Bluetooth range is to set up an Espressif's ESP32 board as Bluetooth proxy using ESPHome. This then relays the Bluetooth data over the Wi-Fi network to which the Home Assistant server is connected. This BroodMinder integration is out-of-the-box compatible with ESPHome's Bluetooth proxy; no changes or configuration is required for the BroodMinder integration. For more information, see [ESPHome documentation](https://esphome.io/components/bluetooth_proxy).


## Supported BroodMinder devices

This integration supports any BroodMinder model that broadcasts weight, temperature, humidity, and battery in the standard format according to the [BroodMinder documentation](https://doc.mybroodminder.com/87_physics_and_tech_stuff).
Humidity is not present for models `41`, `47`, `49`, `52` (see [model information](https://doc.mybroodminder.com/30_sensors)), as per the format documentation.

In theory this means it should work with the following devices (model numbers in brackets):

* BroodMinder-T internal hive monitor (`41`, `47`)
* BroodMinder-TH internal hive monitor (`42`, `56`)
* BroodMinder-W hive scale: the original W (`43`) and the W+ (`57`)
* BroodMinder-W3 and W4 hive scales (`49`)
* BroodMinder DIY scales (`58`)

Partially supported:

* BroodMinder SubHub (`52`)
* Hub 4G (`54`)
* Hub WiFi (`60`)
* BeeDar (`63`)  
These partially supported devices are recognised and show up as devices, but only with basic sensors. Their advertisements are still unknown, so the values may not be meaningful, and the BeeDar's bee count isn't shown.

Not supported (yet):

* BroodMinder-W5 hive scale  
Its model number is unknown, so it shows up as an "Unknown" device without weight sensors.

Physically verified:

* BroodMinder-TH internal hive monitor

If you are able to test the other devices, feel free to create a GitHub issue to indicate which
devices were tested succesfully, or any issues you have found. The documentation will then be updated, and issues found will be fixed.

If you are technical, you can ofcourse make your own improvements and create a pull request for integration.

## Entities per device

Which sensors are created depends on the BroodMinder model. The number in brackets is the
BroodMinder model number.

| Sensor          | T (41) | T (47) | TH (42) | TH (56) | W (43) | W (57) | W3/W4 (49) | DIY (58) | SubHub (52) | Hub 4G (54), Hub Wifi (60), BeeDar (63), other |
|-----------------|:------:|:------:|:-------:|:-------:|:------:|:------:|:----------:|:--------:|:-----------:|:----------------------------------------------:|
| Battery         | ✓      | ✓      | ✓       | ✓       | ✓      | ✓      | ✓          | ✓        | ✓           | ✓                                              |
| Brood           | ✓      | ✓      | ✓       | ✓       |        |        |            |          |             |                                                |
| Humidity        |        |        | ✓       | ✓       | ✓      | ✓      |            | ✓        |             | ✓                                              |
| Temperature     | ✓      | ✓      | ✓       | ✓       | ✓      | ✓      | ✓          | ✓        | ✓           | ✓                                              |
| Realtime Temp   |        | ✓      |         | ✓       |        | ✓      | ✓          | ✓        |             |                                                |
| Sample count    | ✓      | ✓      | ✓       | ✓       | ✓      | ✓      | ✓          | ✓        | ✓           | ✓                                              |
| Swarm State     | ✓      | ✓      | ✓       | ✓       |        |        |            |          |             |                                                |
| Swarm Time      | ✓      | ✓      | ✓       | ✓       |        |        |            |          |             |                                                |
| Weight Left     |        |        |         |         | ✓      | ✓      | ✓          | ✓        |             |                                                |
| Weight Right    |        |        |         |         | ✓      | ✓      | ✓          | ✓        |             |                                                |
| Weight Left 2   |        |        |         |         |        | ✓      | ✓          | ✓        |             |                                                |
| Weight Right 2  |        |        |         |         |        | ✓      | ✓          | ✓        |             |                                                |
| Weight Realtime |        |        |         |         | ✓ ¹    | ✓      | ✓          | ✓        |             |                                                |

¹ The original BroodMinder-W (model 43) doesn't send a total weight. It sits under one side of
the hive and measures half its weight, so the integration calculates Weight Realtime as
2 × (Weight Left + Weight Right). It only appears when both sides report a weight.

The SubHub, hubs and BeeDar haven't been tested: their sensors use the standard
advertisement format, which these devices may not follow.


## Entity descriptions

This section decribes the entities that the BroodMinder integration adds to Home Assistant.

The BroodMinder integration provides the following sensor entities:

* **Battery**  
  This provides the state of charge of the battery in percentage from 0 to 100%, based on the
  battery voltage. Newer firmware also sends the remaining battery life based on how long the
  device has been running, in steps of 4%, in place of roughly every other voltage reading.
  Battery then shows the lower of the two, so it doesn't jump back and forth and a battery
  that's running low by either measure shows. The voltage drops on a cold night and recovers
  when it warms up, so Battery can dip overnight when the voltage reading is the lower one.  
  The `voltage_based` and `charge_remaining` attributes show the last reading of each kind;
  `charge_remaining` stays empty on older firmware. Home Assistant remembers both across a
  restart.

* **Brood**  
  An estimate from 0 to 100% of the brood near the sensor, from the hive temperature and the
  outdoor temperature. See [Brood estimate](#brood-estimate).

* **Humidity**  
  This provides the measured humidity of the BroodMinder in percentage from 0 to 100%.

* **Realtime temperature**  
  This provides the measured realtime temperature of the BroodMinder in degrees Celcius.
  
* **Temperature**  
  This provides the measured and filtered temperature of the BroodMinder in degrees Celcius.

* **Sample count**  
  This provides the total number of samples that the BroodMinder has taken.

* **Swarm state**  
  This indicates the swarm detection state of the BroodMinder, for the SwarmMinder feature.
  The state is the numeric code below; the `description` attribute holds its description
  (*Unknown* for an undocumented code).
  From the [documentation](https://doc.mybroodminder.com/31_sensors_T_TH):
  | Swarm State  | Description                                                    |
  |--------------|----------------------------------------------------------------|
  | 0            | Stopped                                                        |
  | 1            | Stopped - initialization complete                              |
  | 2            | Stopped - by stop request                                      |
  | 20           | Started - checking for swarm event                             |
  | 21           | Started - buffering temperature data                           |
  | 22           | Started - temperature < hive base temperature (32.5C, 90.5F)   |
  | 25           | Started - buffered hive temperature < hive base temperature    |
  | 29           | Swarm event detected                                           |
  | 40           | Swarm event detected - start logging                           |
  | 41           | Swarm event detected - still logging swarm data                |
  | 60           | Swarm event logging complete - start waiting - swarm detection |
  | 61           | Swarm event logging complete - still waiting                   |

* **Swarm time**  
  This indicates the swarm time detection of the BroodMinder, for the SwarmMinder feature.
  It shows *Unknown* until the sensor's clock has been set by a sync with the BroodMinder Bees app, for example after a battery change.

* **Weight left, weight right**  
  This indicates the measured weight of the hive, per side of the scale, in kilograms.

* **Weight left 2, weight right 2**  
  The weight on the extra load cells of scales that have them (models `49`, `57` and `58`).

* **Weight realtime**  
  The total weight of the hive in kilograms, as sent by the scale.
  The original BroodMinder-W (model `43`) weighs one side of the hive and doesn't send a total,
  so for this scale it is calculated as 2 × (weight left + weight right).


## Brood estimate

BroodMinder-T and -TH hives get a **Brood** sensor: an estimate from 0 to 100% of the brood the
colony raises near the sensor, like the brood level in BroodMinder's Bees app. It needs no scale:
it compares the hive temperature with the outdoor temperature.

### How it works

A colony with brood keeps the brood nest at about 35 °C, whatever the weather. Without brood, the
hive temperature follows the weather. Every hour, the integration scores how far the colony keeps
the hive above what the outdoor temperature alone would give, towards 35 °C. The day's score is
lowered when the hive temperature swings along with the outdoor temperature.

The estimate covers the last 24 hours and is updated every hour. It needs at least 18 hours with
both temperatures, so a new hive shows *unknown* for most of its first day. The hours are stored,
so a restart of Home Assistant doesn't start the count over.

Like BroodMinder's own brood level, the percentage is relative. Compare hives with each other and
over time, and learn what it means for your hives, for example "80% is usually 6 frames of
brood". Below about 20% it's rough, because the brood can be far from the sensor.

The formulas, settings and design decisions are described in detail in
[BROOD_ESTIMATE.md](BROOD_ESTIMATE.md).

### Settings

Each T and TH hive has its own settings: go to **Settings** > **Devices & services** >
**BroodMinder** and select **Configure** on the hive.

* **Sensor position**
  * *On top of the frames* (default): BroodMinder's standard placement, on the top bars near the
    middle of the brood box. The temperature there drops off gradually as the brood nest shrinks
    or moves away, so the estimate rises and falls with the amount of brood.
  * *In the comb, between frames at brood height*: in the comb, the sensor reads about 35 °C
    whenever brood surrounds it, however big the brood nest is. The estimate then shows whether
    the brood nest reaches the sensor: high for most of the season, and dropping during a brood
    break, after losing the queen, or when the brood nest shrinks in autumn.
* **Outdoor temperature**  
  A temperature sensor or weather entity. Leave it empty to use Home Assistant's weather: the
  Met.no *Forecast Home* weather entity that Home Assistant creates during setup, or else your
  only weather entity.

### Outdoor temperature from Home Assistant's weather

* Set your home location and elevation under **Settings** > **System** > **General**. Met.no
  uses both, and without the elevation its temperature can be off in hilly areas.
* The weather is for your home location. For hives somewhere else, choose a temperature sensor
  near them in the hive's settings.

When there's no outdoor temperature, Home Assistant shows a repair under **Settings** >
**System** > **Repairs**:

* *BroodMinder brood estimate has no outdoor temperature*: there's no Met.no *Forecast Home*
  entity, and not exactly one other weather entity. Add the Met.no integration, or choose an
  outdoor temperature in the hive's settings.
* *Outdoor temperature for (hive) is unavailable*: the outdoor temperature has had no value for
  more than 3 hours.

### Brood sensor attributes

* `status`: `ok`, or why the sensor shows *unknown*:
  * `not_enough_data`: fewer than 18 of the last 24 hours have both temperatures.
  * `no_outdoor_temperature`: there's no outdoor temperature, see above.
  * `too_hot`: it was so warm outdoors that 35 °C in the hive says nothing about brood. In
    climates that stay at about 31 °C or warmer day and night, the sensor often shows *unknown*.
* `level`: the average hourly score, from 0 to 1.
* `stability`: from 0 to 1, where 1 means the hive stays steady while the weather swings.
* `hours_used`: the number of hours in the estimate.
* `outdoor_entity`: the outdoor temperature in use.
* `sensor_position`: the sensor position from the settings.


## Installation and setup

The steps below can be followed to install and setup the BroodMinder integration.

1. Install Home Assistant Community Store (HACS).
The BroodMinder integration can be installed through HACS (Home Assistant Community Store).
Therefore, HACS first needs to be installed in Home Assistant.
Follow the instructions on the [HACS website](https://www.hacs.xyz/docs/use/download/download).



2. Install the BroodMinder integration through the badge (recommended).
To Install the BroodMinder integration, click the badge below:
[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=sandersmeenk&repository=home_assistant-broodminder&category=integration)


3. Install the BroodMinder integration manually (fallback for 2).
To install the BroodMinder integration manually:
    - Inside Home Assistant, select HACS in the menu on the left
    - Click on the three dots in the top-right corner -> Custom repositories
    - In the `repository` field, enter the GitHub URL `https://github.com/sandersmeenk/home_assistant-broodminder`
    - In the `type` field, select `integration`
    - Click on `Add`


3. View devices in Home Assistant
    - Inside Home Assistant, select Settings in the menu on the left
    - Click on `Devices and Services`
    - Click on `BroodMinder`
    - If BroodMinder devices are turned on and within Bluetooth range, they will show up on this screen

