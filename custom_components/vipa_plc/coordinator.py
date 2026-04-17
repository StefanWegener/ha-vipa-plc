"""DataUpdateCoordinator for the VIPA PLC integration."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_ADDRESS, CONF_ENTITY_TYPE, CONF_ENTITIES, ENTITY_TYPE_BINARY_SENSOR
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
        """Fetch binary sensor states from the PLC."""
        data: dict[str, Any] = {}

        if not self._client.is_connected():
            _LOGGER.debug("PLC not connected, attempting reconnect")
            try:
                await self.hass.async_add_executor_job(self._client.connect)
            except Exception as exc:  # noqa: BLE001
                raise UpdateFailed(f"PLC not connected and reconnect failed: {exc}") from exc

        binary_sensor_configs = [
            cfg
            for cfg in self._entity_configs
            if cfg.get(CONF_ENTITY_TYPE) == ENTITY_TYPE_BINARY_SENSOR
        ]

        for cfg in binary_sensor_configs:
            address = cfg[CONF_ADDRESS]
            try:
                value = await self.hass.async_add_executor_job(
                    self._client.read_bool, address
                )
                data[address] = value
            except PLCCommunicationError as exc:
                _LOGGER.warning("Failed to read %s: %s", address, exc)
                data[address] = None

        return data
