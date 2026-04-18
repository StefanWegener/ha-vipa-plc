"""Cover platform for the VIPA PLC integration (blinds/shutters)."""
from __future__ import annotations

import asyncio
import logging
import time
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
    CONF_HOLD_MODE,
    CONF_PULSE_DURATION,
    CONF_TRAVEL_TIME_DOWN,
    CONF_TRAVEL_TIME_UP,
    DEFAULT_HOLD_MODE,
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

    Operates in optimistic mode. If travel_time_down and travel_time_up are
    configured, position tracking (0–100) is enabled via timed travel
    simulation and SET_POSITION is supported.
    """

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
        self._hold_mode: bool = cfg.get(CONF_HOLD_MODE, DEFAULT_HOLD_MODE)

        self._travel_time_down: float | None = cfg.get(CONF_TRAVEL_TIME_DOWN) or None
        self._travel_time_up: float | None = cfg.get(CONF_TRAVEL_TIME_UP) or None

        device_class_str: str | None = cfg.get(CONF_DEVICE_CLASS) or None
        self._attr_device_class: CoverDeviceClass | None = (
            CoverDeviceClass(device_class_str) if device_class_str else CoverDeviceClass.SHUTTER
        )

        entity_id_safe = cfg["id"].replace("-", "_")
        self._attr_unique_id = f"{entry.entry_id}_{entity_id_safe}"
        self._attr_name = cfg[CONF_ENTITY_NAME]
        self._attr_has_entity_name = False

        # Position tracking (only active when travel times are configured)
        # position: 0 = closed, 100 = fully open; None = unknown
        self._current_position: int | None = None

        # Optimistic closed state (used when no travel times configured)
        self._optimistic_is_closed: bool | None = None

        # asyncio Task tracking the current travel
        self._travel_task: asyncio.Task | None = None

        # Time when the current travel started and in which direction
        self._travel_start_time: float | None = None
        self._travel_direction: str | None = None  # "open" | "close"
        self._travel_start_position: int | None = None

    # ------------------------------------------------------------------
    # Features
    # ------------------------------------------------------------------

    @property
    def supported_features(self) -> CoverEntityFeature:
        features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
        if self._has_travel_times:
            features |= CoverEntityFeature.SET_POSITION
        return features

    @property
    def _has_travel_times(self) -> bool:
        return self._travel_time_down is not None and self._travel_time_up is not None

    # ------------------------------------------------------------------
    # Device info
    # ------------------------------------------------------------------

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title,
            manufacturer="VIPA / YASKAWA",
            model="SPEED7 CPU",
        )

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def current_cover_position(self) -> int | None:
        """Return current position (0=closed, 100=open). None if unknown."""
        if not self._has_travel_times:
            return None
        return self._current_position

    @property
    def is_closed(self) -> bool | None:
        """Return True if cover is closed."""
        if self._has_travel_times:
            if self._current_position is None:
                return None
            return self._current_position == 0
        return self._optimistic_is_closed

    @property
    def is_opening(self) -> bool:
        return self._travel_direction == "open"

    @property
    def is_closing(self) -> bool:
        return self._travel_direction == "close"

    @property
    def assumed_state(self) -> bool:
        return True

    async def async_will_remove_from_hass(self) -> None:
        """Cancel any running travel task when the entity is removed."""
        self._cancel_travel()

    # ------------------------------------------------------------------
    # Travel position helpers
    # ------------------------------------------------------------------

    def _position_at_stop(self) -> int | None:
        """Calculate the position where the cover currently is based on elapsed travel time."""
        if (
            self._travel_start_time is None
            or self._travel_direction is None
            or self._travel_start_position is None
        ):
            return self._current_position

        elapsed = time.monotonic() - self._travel_start_time

        if self._travel_direction == "open":
            travel_time = self._travel_time_up
            delta = int(elapsed / travel_time * 100) if travel_time else 100
            return min(100, self._travel_start_position + delta)
        else:  # close
            travel_time = self._travel_time_down
            delta = int(elapsed / travel_time * 100) if travel_time else 100
            return max(0, self._travel_start_position - delta)

    def _cancel_travel(self) -> None:
        """Cancel any running travel task and snapshot the current position."""
        if self._travel_task and not self._travel_task.done():
            self._travel_task.cancel()
            if self._has_travel_times:
                self._current_position = self._position_at_stop()
        self._travel_task = None
        self._travel_direction = None
        self._travel_start_time = None
        self._travel_start_position = None

    async def _travel_to_position(self, target: int) -> None:
        """Internal coroutine: travel until target position reached, then stop.

        Updates current_cover_position every second so the HA UI shows a
        live animation while the cover is moving.
        """
        _UPDATE_INTERVAL = 1.0  # seconds between position updates

        try:
            start_pos = self._current_position if self._current_position is not None else (
                100 if self._travel_direction == "open" else 0
            )
            if self._travel_direction == "open":
                travel_time = self._travel_time_up
                remaining_fraction = (target - start_pos) / 100.0
            else:
                travel_time = self._travel_time_down
                remaining_fraction = (start_pos - target) / 100.0

            # Guard: if already at target skip travel
            if remaining_fraction <= 0:
                self._current_position = target
                self._travel_direction = None
                self._travel_start_time = None
                self._travel_start_position = None
                self._travel_task = None
                self.async_write_ha_state()
                return

            total_sleep = (travel_time or 0) * remaining_fraction

            _LOGGER.debug(
                "Cover '%s': travelling %s for %.1fs to reach position %d",
                self._attr_name, self._travel_direction, total_sleep, target,
            )

            # Sleep in 1-second steps, updating position each tick for UI animation
            elapsed = 0.0
            while elapsed < total_sleep:
                step = min(_UPDATE_INTERVAL, total_sleep - elapsed)
                await asyncio.sleep(step)
                elapsed += step

                # Update intermediate position
                if travel_time and travel_time > 0:
                    travelled_fraction = elapsed / total_sleep
                    if self._travel_direction == "open":
                        self._current_position = min(
                            target,
                            start_pos + int(travelled_fraction * (target - start_pos))
                        )
                    else:
                        self._current_position = max(
                            target,
                            start_pos - int(travelled_fraction * (start_pos - target))
                        )
                    self.async_write_ha_state()

            # Send stop when travel complete
            if self._hold_mode:
                try:
                    await self.hass.async_add_executor_job(
                        self._client.write_bool, self._address_open, False
                    )
                    await self.hass.async_add_executor_job(
                        self._client.write_bool, self._address_close, False
                    )
                except Exception as exc:  # noqa: BLE001
                    _LOGGER.warning(
                        "Cover '%s': stop write failed after travel: %s",
                        self._attr_name, exc,
                    )
            elif self._address_stop:
                try:
                    await self.hass.async_add_executor_job(
                        self._client.pulse_bool, self._address_stop, self._pulse_duration
                    )
                except Exception as exc:  # noqa: BLE001
                    _LOGGER.warning(
                        "Cover '%s': stop pulse failed after travel: %s",
                        self._attr_name, exc,
                    )

            self._current_position = target
            self._travel_direction = None
            self._travel_start_time = None
            self._travel_start_position = None
            self._travel_task = None
            self.async_write_ha_state()
        except asyncio.CancelledError:
            _LOGGER.debug("Cover '%s': travel task cancelled", self._attr_name)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error(
                "Cover '%s': unexpected error in travel task: %s",
                self._attr_name, exc,
            )
            self._travel_direction = None
            self._travel_start_time = None
            self._travel_start_position = None
            self._travel_task = None
            self.async_write_ha_state()

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def _async_cancel_travel(self) -> None:
        """Cancel any running travel task, snapshot position, and release PLC bits in hold mode."""
        self._cancel_travel()
        if self._hold_mode:
            try:
                await self.hass.async_add_executor_job(
                    self._client.write_bool, self._address_open, False
                )
                await self.hass.async_add_executor_job(
                    self._client.write_bool, self._address_close, False
                )
            except Exception as exc:  # noqa: BLE001
                _LOGGER.warning("Cover '%s': failed to release PLC bits on cancel: %s", self._attr_name, exc)

    async def _start_movement(self, address: str) -> bool:
        """Start cover movement: pulse or hold depending on mode.

        In hold mode, ensures the opposite direction is off first, then sets
        the given address to True (held until stop).
        In pulse mode, sends a short pulse.

        Returns True on success, False on failure.
        """
        if self._hold_mode:
            try:
                # Ensure opposite direction is off
                opposite = self._address_close if address == self._address_open else self._address_open
                await self.hass.async_add_executor_job(
                    self._client.write_bool, opposite, False
                )
                await self.hass.async_add_executor_job(
                    self._client.write_bool, address, True
                )
            except Exception as exc:  # noqa: BLE001
                _LOGGER.error("Cover '%s': hold write failed: %s", self._attr_name, exc)
                return False
        else:
            try:
                await self.hass.async_add_executor_job(
                    self._client.pulse_bool, address, self._pulse_duration
                )
            except Exception as exc:  # noqa: BLE001
                _LOGGER.error("Cover '%s': pulse failed: %s", self._attr_name, exc)
                return False
        return True

    async def _stop_movement(self) -> None:
        """Stop cover movement.

        In hold mode, sets both open and close addresses to False.
        In pulse mode with a stop address, sends a pulse to the stop address.
        """
        if self._hold_mode:
            try:
                await self.hass.async_add_executor_job(
                    self._client.write_bool, self._address_open, False
                )
                await self.hass.async_add_executor_job(
                    self._client.write_bool, self._address_close, False
                )
            except Exception as exc:  # noqa: BLE001
                _LOGGER.error("Cover '%s': stop write failed: %s", self._attr_name, exc)
        elif self._address_stop:
            try:
                await self.hass.async_add_executor_job(
                    self._client.pulse_bool, self._address_stop, self._pulse_duration
                )
            except Exception as exc:  # noqa: BLE001
                _LOGGER.error("Cover '%s': stop pulse failed: %s", self._attr_name, exc)

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover fully."""
        _LOGGER.debug("Cover '%s' open – %s %s", self._attr_name,
                       "holding" if self._hold_mode else "pulsing", self._address_open)
        self._cancel_travel()

        if not await self._start_movement(self._address_open):
            return

        if self._has_travel_times:
            start_pos = self._current_position if self._current_position is not None else 0
            self._travel_direction = "open"
            self._travel_start_time = time.monotonic()
            self._travel_start_position = start_pos
            self._current_position = start_pos
            self._travel_task = self.hass.async_create_task(
                self._travel_to_position(100)
            )
        else:
            self._optimistic_is_closed = False

        self.async_write_ha_state()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover fully."""
        _LOGGER.debug("Cover '%s' close – %s %s", self._attr_name,
                       "holding" if self._hold_mode else "pulsing", self._address_close)
        self._cancel_travel()

        if not await self._start_movement(self._address_close):
            return

        if self._has_travel_times:
            start_pos = self._current_position if self._current_position is not None else 100
            self._travel_direction = "close"
            self._travel_start_time = time.monotonic()
            self._travel_start_position = start_pos
            self._current_position = start_pos
            self._travel_task = self.hass.async_create_task(
                self._travel_to_position(0)
            )
        else:
            self._optimistic_is_closed = True

        self.async_write_ha_state()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        _LOGGER.debug("Cover '%s' stop", self._attr_name)
        self._cancel_travel()
        await self._stop_movement()
        self.async_write_ha_state()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Move cover to a specific position (0–100)."""
        if not self._has_travel_times:
            return

        target: int = kwargs.get("position", 0)
        current = self._current_position

        if current is None:
            # Unknown position — go to extremes first to calibrate
            if target >= 50:
                await self.async_open_cover()
                return
            else:
                await self.async_close_cover()
                return

        if target == current:
            return

        _LOGGER.debug(
            "Cover '%s': set_position %d -> %d", self._attr_name, current, target
        )

        self._cancel_travel()

        if target > current:
            # Need to open
            if not await self._start_movement(self._address_open):
                return
            self._travel_direction = "open"
        else:
            # Need to close
            if not await self._start_movement(self._address_close):
                return
            self._travel_direction = "close"

        self._travel_start_time = time.monotonic()
        self._travel_start_position = current
        self._current_position = current
        self._travel_task = self.hass.async_create_task(
            self._travel_to_position(target)
        )
        self.async_write_ha_state()
