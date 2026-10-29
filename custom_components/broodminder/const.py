"""Constants for the BroodMinder integration."""

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

# Models with SHT-like temperature formula:
SPECIAL_TEMP_MODELS_F = {41, 42, 43}

# Models without humidity in adv payload:
NO_HUMIDITY_MODELS = {41, 47, 49, 52}

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

MANUFACTURER = "BroodMinder"
