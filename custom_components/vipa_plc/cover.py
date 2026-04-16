"""Cover platform for the VIPA PLC integration (blinds/shutters)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_ADDRESS_CLOSE,
    CONF_ADDRESS_OPEN,
    CONF_ADDRESS_STOP,
    CONF_DEVICE_CLASS,
    CONF_ENTITIES,
    CONF_ENTITY_NAME,
    CONF_ENTITY_TYPE,
    CONF_PULSE_DURATION,
    DEFAULT_PULSE_DURATION,
    DOMAIN,
    ENTITY_TYPE_COVER,
)
from .plc_client import PLCClient

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up cover entities for this config entry."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    client: PLCClient = entry_data["client"]

    entity_configs = entry.options.get(CONF_ENTITIES, [])
    entities = [
        VipaCover(client, entry, cfg)
        for cfg in entity_configs
        if cfg.get(CONF_ENTITY_TYPE) == ENTITY_TYPE_COVER
    ]
    async_add_entities(entities)


class VipaCover(CoverEntity):
    """A cover entity that sends open/close/stop impulses to the PLC.

    Operates in optimistic mode — no position feedback from PLC.
    """

    _attr_supported_features = (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
    )

    def __init__(
        self,
        client: PLCClient,
        entry: ConfigEntry,
        cfg: dict[str, Any],
    ) -> None:
        self._client = client
        self._entry = entry
        self._cfg = cfg
        self._address_open: str = cfg[CONF_ADDRESS_OPEN]
        self._address_close: str = cfg[CONF_ADDRESS_CLOSE]
        self._address_stop: str | None = cfg.get(CONF_ADDRESS_STOP) or None
        self._pulse_duration: float = cfg.get(CONF_PULSE_DURATION, DEFAULT_PULSE_DURATION)

        device_class_str: str | None = cfg.get(CONF_DEVICE_CLASS) or None
        self._attr_device_class: CoverDeviceClass | None = (
            CoverDeviceClass(device_class_str) if device_class_str else CoverDeviceClass.SHUTTER
        )

        entity_id_safe = cfg["id"].replace("-", "_")
        self._attr_unique_id = f"{entry.entry_id}_{entity_id_safe}"
        self._attr_name = cfg[CONF_ENTITY_NAME]
        self._attr_has_entity_name = False

        # Optimistic state: None = unknown, True = open, False = closed
        self._optimistic_is_closed: bool | None = None

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title,
            manufacturer="VIPA / YASKAWA",
            model="SPEED7 CPU",
        )

    @property
    def is_closed(self) -> bool | None:
        """Return True if cover is closed."""
        return self._optimistic_is_closed

    @property
    def assumed_state(self) -> bool:
        return True

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        _LOGGER.debug("Cover '%s' open – pulsing %s", self._attr_name, self._address_open)
        await self.hass.async_add_executor_job(
            self._client.pulse_bool, self._address_open, self._pulse_duration
        )
        self._optimistic_is_closed = False
        self.async_write_ha_state()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        _LOGGER.debug("Cover '%s' close – pulsing %s", self._attr_name, self._address_close)
        await self.hass.async_add_executor_job(
            self._client.pulse_bool, self._address_close, self._pulse_duration
        )
        self._optimistic_is_closed = True
        self.async_write_ha_state()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        if self._address_stop is None:
            return
        _LOGGER.debug("Cover '%s' stop – pulsing %s", self._attr_name, self._address_stop)
        await self.hass.async_add_executor_job(
            self._client.pulse_bool, self._address_stop, self._pulse_duration
        )
