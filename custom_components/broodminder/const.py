"""Constants for the BroodMinder integration."""

from datetime import timedelta

DOMAIN = "broodminder"

MANUFACTURER_ID = 0x028D  # IF, LLC (BroodMinder)

# BroodMinder payload indices relative to manufacturer payload (company ID removed):
# (Doc bytes 10..30 → indices 0..20 here)
IDX_MODEL = 0
IDX_VER_MINOR = 1
IDX_VER_MAJOR = 2

# Realtime temp LSB (doc byte 13 overall → index 3 here)
IDX_RT_TEMP1_L = 3
# Battery %
IDX_BATTERY = 4  # byte 14 overall
# Shortest payload we accept: model, version and battery must be present
MIN_PAYLOAD_LEN = IDX_BATTERY + 1
# Elapsed seconds, little-endian
IDX_ELAPSED_L = 5  # byte 15 overall
IDX_ELAPSED_H = 6  # byte 16 overall
# Primary temperature (centi°C + 5000 for most models; SHT-like for 41/42/43)
IDX_TEMP_L = 7  # byte 17 overall
IDX_TEMP_H = 8  # byte 18 overall
# Realtime temp MSB (doc byte 19 overall → index 9 here)
IDX_RT_TEMP2_L = 9
# Weight channels (little-endian 16-bit with -32767 offset; model-dependent)
IDX_WEIGHT_L_L = 10  # byte 20 overall
IDX_WEIGHT_L_H = 11  # byte 21 overall
IDX_WEIGHT_R_L = 12  # byte 22 overall
IDX_WEIGHT_R_H = 13  # byte 23 overall
# Humidity (%RH, 0..100; some models send 0)
IDX_HUMIDITY = 14  # byte 24 overall
# Either extra weight channels OR SM time bytes (model-dependent)
IDX_WL2_SM0 = 15  # byte 25 overall (LSB)
IDX_WL2_SM1 = 16  # byte 26
IDX_WR2_SM2 = 17  # byte 27
IDX_WR2_SM3 = 18  # byte 28 (MSB)
# Realtime total weight (low) OR swarm-state (model-dependent), plus high byte
IDX_RT_TOTAL_L_OR_SWARM_STATE = 19  # byte 29 overall
IDX_RT_TOTAL_H = 20  # byte 30 overall

# Model descriptions
MODEL_T = {41, 47}
MODEL_TH = {42, 56}
MODEL_W = {43, 57}
MODEL_W3_W4 = {49}
MODEL_SUBHUB = {52}
MODEL_HUB_4G = {54}
MODEL_DIY = {58}
MODEL_HUB_WIFI = {60}
MODEL_BEEDAR = {63}

# Models measuring in-hive temperature, the only ones with a brood estimate
BROOD_MODELS = MODEL_T | MODEL_TH

# Models with SHT-like temperature formula:
SPECIAL_TEMP_MODELS_F = {41, 42, 43}

# Models without humidity in adv payload:
NO_HUMIDITY_MODELS = {41, 47, 49, 52}

# Models with weight channels in adv payload:
SCALE_MODELS = MODEL_W | MODEL_W3_W4 | MODEL_DIY

# Models with realtime temperature and realtime total weight (docs: "SM & XLR"):
REALTIME_MODELS = {47, 49, 56, 57, 58}

# Models with extra weight channels instead of SM time (docs: "XLR"):
EXTRA_WEIGHT_MODELS = {49, 57, 58}

# Scale W (43) sends no total: it measures half the hive, so total = 2 x (left + right)
CALCULATED_TOTAL_WEIGHT_MODELS = {43}
HALF_HIVE_WEIGHT_FACTOR = 2

# Raw temperature value without a reading
TEMP_RAW_INVALID = 0xFFFF

# Raw weight values without a reading
WEIGHT_RAW_NO_READING = 0xFFFF
# Raw 0x7FFF is 0.00 kg, but on an extra weight channel it means no load cell is connected
WEIGHT_RAW_NOT_CONNECTED = 0x7FFF

# Model names
MODELS: dict[str, set[int]] = {
    "T": MODEL_T,
    "TH": MODEL_TH,
    "Scale W": MODEL_W,
    "Scale W3/W4": MODEL_W3_W4,
    "SubHub": MODEL_SUBHUB,
    "Hub 4G": MODEL_HUB_4G,
    "DIY": MODEL_DIY,
    "Hub Wifi": MODEL_HUB_WIFI,
    "BeeDar": MODEL_BEEDAR,
}

ID_TO_MODEL: dict[int, str] = {model_id: name for name, ids in MODELS.items() for model_id in ids}

# Entity keys
SENSOR_TEMP = "temperature"
SENSOR_TEMP_RT = "temperature_realtime"
SENSOR_HUM = "humidity"
SENSOR_BATT = "battery"
# Readings behind the Battery sensor, passed on without entities of their own
BATTERY_VOLTAGE_BASED = "battery_voltage_based"
BATTERY_CHARGE_REMAINING = "battery_charge_remaining"

SENSOR_SAMPLE_COUNT = "sample_count"
SENSOR_WEIGHT_L = "weight_left"
SENSOR_WEIGHT_R = "weight_right"
SENSOR_WEIGHT_L2 = "weight_left_2"
SENSOR_WEIGHT_R2 = "weight_right_2"
SENSOR_WEIGHT_REALTIME = "weight_realtime_total"
SENSOR_SWARM_STATE = "swarm_state"
SENSOR_SWARM_TIME = "swarm_time"  # may be time since boot if not synced
# Older swarm times are time since boot: the clock was never set by a Bees app sync
SWARM_TIME_MIN_VALID_UNIX = 1420070400  # 2015-01-01T00:00:00Z

# Battery attributes: the last reading of each kind, the lower of which is the battery level
ATTR_VOLTAGE_BASED = "voltage_based"
ATTR_CHARGE_REMAINING = "charge_remaining"

# Swarm state attribute: human readable SwarmMinder state
ATTR_DESCRIPTION = "description"
# From https://doc.mybroodminder.com/31_sensors_T_TH, "SwarmMinder Details"
SWARM_STATE_DESCRIPTIONS: dict[int, str] = {
    0: "Stopped",
    1: "Stopped - initialization complete",
    2: "Stopped - by stop request",
    20: "Started - checking for swarm event",
    21: "Started - buffering temperature data",
    22: "Started - temperature < hive base temperature (32.5C, 90.5F)",
    25: "Started - buffered hive temperature < hive base temperature",
    29: "Swarm event detected",
    40: "Swarm event detected - start logging",
    41: "Swarm event detected - still logging swarm data",
    60: "Swarm event logging complete - start waiting - swarm detection",
    61: "Swarm event logging complete - still waiting",
}
SWARM_STATE_DESCRIPTION_UNKNOWN = "Unknown"

SENSOR_PERCENTAGE_MINIMUM = 0
SENSOR_PERCENTAGE_MAXIMUM = 100

# Newer firmware sends charge remaining (runtime based) in the battery byte as 100 + percent / 4
CHARGE_REMAINING_RAW_MINIMUM = 101
CHARGE_REMAINING_RAW_MAXIMUM = 125
CHARGE_REMAINING_RAW_SCALE = 4

MANUFACTURER = "BroodMinder"

# Config entry data: the model id, so a hive gets its brood sensor before it advertises
CONF_MODEL = "model"

# Hive settings (config entry options)
CONF_SENSOR_POSITION = "sensor_position"
CONF_OUTDOOR_ENTITY = "outdoor_entity"
POSITION_TOP_OF_FRAMES = "top_of_frames"  # BroodMinder's standard placement
POSITION_IN_COMB = "in_comb"  # between frames, at brood height
SENSOR_POSITIONS = [POSITION_TOP_OF_FRAMES, POSITION_IN_COMB]
DEFAULT_SENSOR_POSITION = POSITION_TOP_OF_FRAMES

# Brood estimate
SENSOR_BROOD = "brood"
BROOD_TEMP_C = 35.0  # temperature the colony keeps the brood nest at
# Below this an hour counts as no brood; on top of the frames runs cooler than in the comb
BROOD_EDGE_TEMP_C: dict[str, float] = {POSITION_TOP_OF_FRAMES: 30.0, POSITION_IN_COMB: 32.0}
# How much warmer than outdoors the colony keeps the hive without raising brood
COLONY_WARMING_C = 4.0
# A hive swinging at most this share of the outdoor swing counts as fully stable
STABLE_SWING_RATIO = 0.2
# On days with a smaller outdoor swing (overcast), stability tells nothing and is skipped
MIN_OUTDOOR_SWING_C = 3.0
BROOD_WINDOW_HOURS = 24
BROOD_MIN_HOURS = 18  # hours in the window with both temperatures
BROOD_HISTORY_HOURS = 48  # hours kept in storage
BROOD_SAMPLE_INTERVAL = timedelta(minutes=5)
# Increase with every change of the brood history file's format, and migrate the previous one
BROOD_STORAGE_VERSION = 2
# Short outages of the outdoor temperature are normal; only longer ones raise a repair
OUTDOOR_UNAVAILABLE_ISSUE_AFTER = timedelta(hours=3)

# Likely brood break: the Brood % stays low for days
SENSOR_BROOD_BREAK = "brood_break"
# At or below this an estimate is low; a broodless hive scores higher on top of the frames
BROOD_BREAK_LOW_PERCENT: dict[str, int] = {POSITION_TOP_OF_FRAMES: 30, POSITION_IN_COMB: 15}
# Above this an estimate counts towards the end of a break; higher than low, so it can't flicker
BROOD_BREAK_END_PERCENT: dict[str, int] = {POSITION_TOP_OF_FRAMES: 45, POSITION_IN_COMB: 30}
BROOD_BREAK_START_HOURS = 48  # low estimates that start a break
BROOD_BREAK_END_HOURS = 24  # estimates in a row above the end level that end it
# After a longer time without an estimate, a count in progress starts over: an outage of a day,
# plus the hours the window needs before the next estimate
BROOD_BREAK_MAX_GAP_HOURS = BROOD_WINDOW_HOURS + BROOD_MIN_HOURS

# Automatic outdoor temperature: Met.no's weather entity for the home location, created
# during onboarding
MET_DOMAIN = "met"
MET_HOME_UNIQUE_ID = "home"

# Brood status: why the estimate may be unknown
BROOD_STATUS_OK = "ok"
BROOD_STATUS_NOT_ENOUGH_DATA = "not_enough_data"
BROOD_STATUS_TOO_HOT = "too_hot"
BROOD_STATUS_NO_OUTDOOR_TEMPERATURE = "no_outdoor_temperature"

# Brood sensor attributes
ATTR_STATUS = "status"
ATTR_LEVEL = "level"
ATTR_STABILITY = "stability"
ATTR_HOURS_USED = "hours_used"
ATTR_OUTDOOR_ENTITY = "outdoor_entity"
ATTR_SENSOR_POSITION = "sensor_position"

# Repair issues
ISSUE_NO_WEATHER_ENTITY = "no_weather_entity"
ISSUE_OUTDOOR_UNAVAILABLE = "outdoor_temperature_unavailable"
