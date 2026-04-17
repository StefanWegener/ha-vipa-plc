"""Button platform for the VIPA PLC integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_ADDRESS,
    CONF_ENTITIES,
    CONF_ENTITY_NAME,
    CONF_ENTITY_TYPE,
    CONF_PULSE_DURATION,
    DEFAULT_PULSE_DURATION,
    DOMAIN,
    ENTITY_TYPE_BUTTON,
)
from .plc_client import PLCClient, PLCCommunicationError

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up button entities for this config entry."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    client: PLCClient = entry_data["client"]

    entity_configs = entry.options.get(CONF_ENTITIES, [])
    entities = [
        VipaButton(client, entry, cfg)
        for cfg in entity_configs
        if cfg.get(CONF_ENTITY_TYPE) == ENTITY_TYPE_BUTTON
    ]
    async_add_entities(entities)


class VipaButton(ButtonEntity):
    """A button entity that pulses a bit on the PLC."""

    def __init__(
        self,
        client: PLCClient,
        entry: ConfigEntry,
        cfg: dict[str, Any],
    ) -> None:
        self._client = client
        self._entry = entry
        self._cfg = cfg
        self._address: str = cfg[CONF_ADDRESS]
        self._pulse_duration: float = cfg.get(CONF_PULSE_DURATION, DEFAULT_PULSE_DURATION)

        entity_id_safe = cfg["id"].replace("-", "_")
        self._attr_unique_id = f"{entry.entry_id}_{entity_id_safe}"
        self._attr_name = cfg[CONF_ENTITY_NAME]
        self._attr_has_entity_name = False

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info so this entity appears under the PLC device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title,
            manufacturer="VIPA / YASKAWA",
            model="SPEED7 CPU",
        )

    async def async_press(self) -> None:
        """Handle button press: pulse the configured PLC bit."""
        _LOGGER.debug(
            "Button '%s' pressed – pulsing %s for %.2f s",
            self._attr_name,
            self._address,
            self._pulse_duration,
        )
        try:
            await self.hass.async_add_executor_job(
                self._client.pulse_bool, self._address, self._pulse_duration
            )
        except PLCCommunicationError as exc:
            raise HomeAssistantError(
                f"Failed to pulse {self._attr_name}: {exc}"
            ) from exc
