"""Switch platform for the VIPA PLC integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_ADDRESS_OFF,
    CONF_ADDRESS_ON,
    CONF_ADDRESS_STATE,
    CONF_ENTITIES,
    CONF_ENTITY_NAME,
    CONF_ENTITY_TYPE,
    CONF_PULSE_DURATION,
    DEFAULT_PULSE_DURATION,
    DOMAIN,
    ENTITY_TYPE_SWITCH,
)
from .coordinator import VipaPlcCoordinator
from .plc_client import PLCClient, PLCCommunicationError

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switch entities for this config entry."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    client: PLCClient = entry_data["client"]
    coordinator: VipaPlcCoordinator = entry_data["coordinator"]

    entity_configs = entry.options.get(CONF_ENTITIES, [])
    entities = [
        VipaSwitch(coordinator, client, entry, cfg)
        for cfg in entity_configs
        if cfg.get(CONF_ENTITY_TYPE) == ENTITY_TYPE_SWITCH
    ]
    async_add_entities(entities)


class VipaSwitch(CoordinatorEntity[VipaPlcCoordinator], SwitchEntity):
    """A switch entity that sends ON/OFF impulses to the PLC.

    If address_state is configured, the switch reads its state from the PLC
    via the coordinator. Otherwise it operates in optimistic mode.
    """

    def __init__(
        self,
        coordinator: VipaPlcCoordinator,
        client: PLCClient,
        entry: ConfigEntry,
        cfg: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._client = client
        self._entry = entry
        self._cfg = cfg
        self._address_on: str = cfg[CONF_ADDRESS_ON]
        self._address_off: str = cfg[CONF_ADDRESS_OFF]
        self._address_state: str | None = cfg.get(CONF_ADDRESS_STATE) or None
        self._pulse_duration: float = cfg.get(CONF_PULSE_DURATION, DEFAULT_PULSE_DURATION)

        entity_id_safe = cfg["id"].replace("-", "_")
        self._attr_unique_id = f"{entry.entry_id}_{entity_id_safe}"
        self._attr_name = cfg[CONF_ENTITY_NAME]
        self._attr_has_entity_name = False

        # Optimistic mode when no state address is configured
        self._attr_assumed_state = self._address_state is None
        self._optimistic_state: bool = False

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
        """Return the switch state."""
        if self._address_state is None:
            return self._optimistic_state
        if self.coordinator.data is None:
            return None
        value = self.coordinator.data.get(self._address_state)
        if value is None:
            return None
        return bool(value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on by pulsing the ON address."""
        _LOGGER.debug("Switch '%s' turn_on – pulsing %s", self._attr_name, self._address_on)
        try:
            await self.hass.async_add_executor_job(
                self._client.pulse_bool, self._address_on, self._pulse_duration
            )
        except PLCCommunicationError as exc:
            raise HomeAssistantError(
                f"Failed to turn on {self._attr_name}: {exc}"
            ) from exc
        if self._address_state is None:
            self._optimistic_state = True
            self.async_write_ha_state()
        else:
            await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off by pulsing the OFF address."""
        _LOGGER.debug("Switch '%s' turn_off – pulsing %s", self._attr_name, self._address_off)
        try:
            await self.hass.async_add_executor_job(
                self._client.pulse_bool, self._address_off, self._pulse_duration
            )
        except PLCCommunicationError as exc:
            raise HomeAssistantError(
                f"Failed to turn off {self._attr_name}: {exc}"
            ) from exc
        if self._address_state is None:
            self._optimistic_state = False
            self.async_write_ha_state()
        else:
            await self.coordinator.async_request_refresh()
