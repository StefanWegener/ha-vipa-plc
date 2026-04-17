"""Constants for the VIPA PLC integration."""

DOMAIN = "vipa_plc"

# Config entry data keys
CONF_HOST = "host"
CONF_PORT = "port"
CONF_RACK = "rack"
CONF_SLOT = "slot"
CONF_POLL_INTERVAL = "poll_interval"

# Defaults
DEFAULT_PORT = 102
DEFAULT_RACK = 0
DEFAULT_SLOT = 2
DEFAULT_POLL_INTERVAL = 5  # seconds

# Options keys
CONF_ENTITIES = "entities"

# Entity types
ENTITY_TYPE_BINARY_SENSOR = "binary_sensor"
ENTITY_TYPE_BUTTON = "button"

# Entity config keys
CONF_ENTITY_TYPE = "entity_type"
CONF_ENTITY_NAME = "entity_name"
CONF_ADDRESS = "address"
CONF_DEVICE_CLASS = "device_class"
CONF_INVERT = "invert"
CONF_PULSE_DURATION = "pulse_duration_seconds"

# Defaults for entities
DEFAULT_PULSE_DURATION = 0.5
DEFAULT_INVERT = False
