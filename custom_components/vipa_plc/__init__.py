"""The VIPA PLC integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    CONF_ENTITIES,
    CONF_HOST,
    CONF_POLL_INTERVAL,
    CONF_PORT,
    CONF_RACK,
    CONF_SLOT,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
)
from .coordinator import VipaPlcCoordinator
from .plc_client import PLCClient, PLCConnectionError

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["binary_sensor", "button", "cover", "switch"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up VIPA PLC from a config entry."""
    data = entry.data
    options = entry.options

    client = PLCClient(
        host=data[CONF_HOST],
        rack=data[CONF_RACK],
        slot=data[CONF_SLOT],
        port=data[CONF_PORT],
    )

    try:
        await hass.async_add_executor_job(client.connect)
    except PLCConnectionError as exc:
        raise ConfigEntryNotReady(f"Cannot connect to VIPA PLC: {exc}") from exc

    entity_configs: list[dict[str, Any]] = list(options.get(CONF_ENTITIES, []))

    _LOGGER.debug(
        "Loading %d entities from options for entry %s",
        len(entity_configs),
        entry.entry_id,
    )
    for cfg in entity_configs:
        _LOGGER.debug("  Entity: %s (type=%s)", cfg.get("entity_name"), cfg.get("entity_type"))

    coordinator = VipaPlcCoordinator(
        hass=hass,
        client=client,
        entity_configs=entity_configs,
        poll_interval=data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
    )

    # Perform an initial data fetch
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options updates (entity list changed)."""
    _LOGGER.debug("Options updated for entry %s – reloading", entry.entry_id)
    # Disconnect the PLC client before reloading to avoid connection conflicts
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    client: PLCClient | None = entry_data.get("client")
    if client is not None:
        try:
            await hass.async_add_executor_job(client.disconnect)
        except Exception:  # noqa: BLE001
            pass
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        entry_data = hass.data[DOMAIN].pop(entry.entry_id, {})
        client: PLCClient | None = entry_data.get("client")
        if client is not None:
            await hass.async_add_executor_job(client.disconnect)

    return unload_ok

