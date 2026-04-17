"""Binary sensor platform for the VIPA PLC integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_ADDRESS,
    CONF_DEVICE_CLASS,
    CONF_ENTITIES,
    CONF_ENTITY_NAME,
    CONF_ENTITY_TYPE,
    CONF_INVERT,
    DEFAULT_INVERT,
    DOMAIN,
    ENTITY_TYPE_BINARY_SENSOR,
)
from .coordinator import VipaPlcCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensor entities for this config entry."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinator: VipaPlcCoordinator = entry_data["coordinator"]

    entity_configs = entry.options.get(CONF_ENTITIES, [])
    entities = [
        VipaBinarySensor(coordinator, entry, cfg)
        for cfg in entity_configs
        if cfg.get(CONF_ENTITY_TYPE) == ENTITY_TYPE_BINARY_SENSOR
    ]
    async_add_entities(entities)


class VipaBinarySensor(CoordinatorEntity[VipaPlcCoordinator], BinarySensorEntity):
    """A binary sensor entity that reads a bit from the PLC."""

    def __init__(
        self,
        coordinator: VipaPlcCoordinator,
        entry: ConfigEntry,
        cfg: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._cfg = cfg
        self._address: str = cfg[CONF_ADDRESS]

        device_class_str: str | None = cfg.get(CONF_DEVICE_CLASS)
        self._attr_device_class: BinarySensorDeviceClass | None = (
            BinarySensorDeviceClass(device_class_str)
            if device_class_str
            else None
        )

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

    @property
    def is_on(self) -> bool | None:
        """Return the sensor state."""
        if self.coordinator.data is None:
            return None
        value = self.coordinator.data.get(self._address)
        if value is None:
            return None
        invert: bool = self._cfg.get(CONF_INVERT, DEFAULT_INVERT)
        return (not value) if invert else value
