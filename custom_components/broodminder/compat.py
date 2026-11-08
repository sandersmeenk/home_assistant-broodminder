"""Differences between the Home Assistant versions this integration supports.

The oldest supported version is the "homeassistant" version in hacs.json. Each difference names
the version that brought the newer behaviour: remove it once the oldest supported version has
it.
"""

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr

try:
    # Since 2026.3, Store refuses a file with a newer major version before migrating it
    from homeassistant.exceptions import UnsupportedStorageVersionError
except ImportError:  # Home Assistant before 2026.3

    class UnsupportedStorageVersionError(HomeAssistantError):  # type: ignore[no-redef]
        """Never raised: before 2026.3, Store leaves a newer major version to the migration."""

        found_version: int


def async_get_device_by_connection(
    hass: HomeAssistant, connection: tuple[str, str], config_entry_id: str
) -> dr.DeviceEntry | None:
    """Return the device with this connection that belongs to the config entry."""
    registry = dr.async_get(hass)
    # Since 2026.8; async_get_device is deprecated since 2026.9 and stops working in 2027.8
    if hasattr(registry, "async_get_device_by_connection"):
        return registry.async_get_device_by_connection(connection, config_entry_id)
    return registry.async_get_device(connections={connection})
