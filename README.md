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

## Home Assistant entities

This section decribes the entities that the BroodMinder integration adds to Home Assistant. 

### Sensors

The BroodMinder integration provides the following sensor entities:

* **Battery**  
  This provides the state of charge of the battery in percentage from 0 to 100%. 

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

* **Swarm time**  
  This indicates the swarm time detection of the BroodMinder, for the SwarmMinder feature.   

* **Weight left, weight right**  
  This indicates the measured weight of the hive. 

## Supported devices

This integration supports any BroodMinder model that broadcasts weight, temperature, humidity, and battery in the standard format according to the [BroodMinder documentation](https://doc.mybroodminder.com/87_physics_and_tech_stuff).
Humidity is not present for models `41`, `47`, `49`, `52` (see [model information](https://doc.mybroodminder.com/30_sensors)), as per the format documentation.

In theory this means it should work with the following devices:

* BroodMinder-T internal hive monitor
* BroodMinder-TH internal hive monitor
* BroodMinder-W hive scale
* BroodMinder-W3 hive scale
* BroodMinder-W4 hive scale
* BroodMinder-W5 hive scale

In practise, only these devices have been physically tested:

* BroodMinder-TH internal hive monitor

If you are able to test the other devices, feel free to create a GitHub issue to indicate which
devices were tested succesfully, or any issues you have found. The documentation will then be updated, and issues found will be fixed.

If you are technical, you can ofcourse make your own improvements and create a pull request for integration.


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

