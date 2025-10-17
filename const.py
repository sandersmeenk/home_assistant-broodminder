DOMAIN = "broodminder"

MANUFACTURER_ID = 0x028D  # IF, LLC (BroodMinder)
# BroodMinder payload indices relative to manufacturer payload (company ID removed):
IDX_MODEL = 0  # model number (e.g., 41,42,43,47,49,...)
IDX_VER_MINOR = 1
IDX_VER_MAJOR = 2
IDX_BATTERY = 4  # battery percentage (0-100)
IDX_TEMP_L = 7  # temperature low byte (see model-specific formula)
IDX_TEMP_H = 8
IDX_HUMIDITY = 14  # %RH (0 for models without humidity per docs)

# Models with SHT-like formula (F from raw 16-bit):
SPECIAL_TEMP_MODELS_F = {41, 42, 43}
# Models without humidity in adv payload per doc:
NO_HUMIDITY_MODELS = {41, 47, 49, 52}

SENSOR_TEMP = "temperature"
SENSOR_HUM = "humidity"
SENSOR_BATT = "battery"

MANUFACTURER = "BroodMinder"
