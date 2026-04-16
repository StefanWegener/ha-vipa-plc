"""DataUpdateCoordinator for the VIPA PLC integration."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_ADDRESS, CONF_ADDRESS_STATE, CONF_ENTITY_TYPE, CONF_ENTITIES, ENTITY_TYPE_BINARY_SENSOR, ENTITY_TYPE_SWITCH
from .plc_client import PLCClient, PLCCommunicationError

_LOGGER = logging.getLogger(__name__)


class VipaPlcCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that polls binary sensor states from the PLC."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: PLCClient,
        entity_configs: list[dict[str, Any]],
        poll_interval: int,
    ) -> None:
        self._client = client
        self._entity_configs = entity_configs
        super().__init__(
            hass,
            _LOGGER,
            name="VIPA PLC",
            update_interval=timedelta(seconds=poll_interval),
        )

    def update_entity_configs(self, entity_configs: list[dict[str, Any]]) -> None:
        """Update the list of entity configs (called on options update)."""
        self._entity_configs = entity_configs

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch binary sensor and switch states from the PLC."""
        data: dict[str, Any] = {}

        if not self._client.is_connected():
            _LOGGER.debug("PLC not connected, attempting reconnect")
            try:
                await self.hass.async_add_executor_job(self._client.connect)
            except Exception as exc:  # noqa: BLE001
                raise UpdateFailed(f"PLC not connected and reconnect failed: {exc}") from exc

        # Collect all addresses to poll: binary sensors + switch state addresses
        addresses_to_poll: set[str] = set()

        for cfg in self._entity_configs:
            entity_type = cfg.get(CONF_ENTITY_TYPE)
            if entity_type == ENTITY_TYPE_BINARY_SENSOR:
                addresses_to_poll.add(cfg[CONF_ADDRESS])
            elif entity_type == ENTITY_TYPE_SWITCH:
                state_addr = cfg.get(CONF_ADDRESS_STATE)
                if state_addr:
                    addresses_to_poll.add(state_addr)

        for address in addresses_to_poll:
            try:
                value = await self.hass.async_add_executor_job(
                    self._client.read_bool, address
                )
                data[address] = value
            except PLCCommunicationError as exc:
                _LOGGER.warning("Failed to read %s: %s", address, exc)
                data[address] = None

        return data
