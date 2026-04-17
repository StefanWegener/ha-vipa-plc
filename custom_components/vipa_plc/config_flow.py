"""Config flow and options flow for the VIPA PLC integration."""
from __future__ import annotations

import logging
from typing import Any
import uuid
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from .address import AddressParseError, parse_address
from .const import (
    CONF_ADDRESS,
    CONF_DEVICE_CLASS,
    CONF_ENTITIES,
    CONF_ENTITY_NAME,
    CONF_ENTITY_TYPE,
    CONF_HOST,
    CONF_INVERT,
    CONF_POLL_INTERVAL,
    CONF_PORT,
    CONF_PULSE_DURATION,
    CONF_RACK,
    CONF_SLOT,
    DEFAULT_INVERT,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_PULSE_DURATION,
    DEFAULT_RACK,
    DEFAULT_SLOT,
    DOMAIN,
    ENTITY_TYPE_BINARY_SENSOR,
    ENTITY_TYPE_BUTTON,
)
from .plc_client import PLCClient, PLCConnectionError

_LOGGER = logging.getLogger(__name__)

# Binary sensor device classes supported in the options UI
BINARY_SENSOR_DEVICE_CLASSES = [
    "",
    "battery",
    "cold",
    "connectivity",
    "door",
    "garage_door",
    "gas",
    "heat",
    "light",
    "lock",
    "moisture",
    "motion",
    "moving",
    "occupancy",
    "opening",
    "plug",
    "power",
    "presence",
    "problem",
    "running",
    "safety",
    "smoke",
    "sound",
    "tamper",
    "update",
    "vibration",
    "window",
]

# Sub-steps for the options flow
_STEP_MENU = "menu"
_STEP_ADD_BINARY_SENSOR = "add_binary_sensor"
_STEP_ADD_BUTTON = "add_button"
_STEP_LIST_ENTITIES = "list_entities"
_STEP_DELETE_ENTITY = "delete_entity"


class VipaPlcConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial PLC configuration flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the user step (connection parameters)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                await self._test_connection(user_input)
            except PLCConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during connection test")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(
                    f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}"
                    f"_r{user_input[CONF_RACK]}_s{user_input[CONF_SLOT]}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input.get("name", user_input[CONF_HOST]),
                    data={
                        CONF_HOST: user_input[CONF_HOST],
                        CONF_PORT: user_input[CONF_PORT],
                        CONF_RACK: user_input[CONF_RACK],
                        CONF_SLOT: user_input[CONF_SLOT],
                        CONF_POLL_INTERVAL: user_input[CONF_POLL_INTERVAL],
                    },
                )

        schema = vol.Schema(
            {
                vol.Required("name", default="VIPA PLC"): str,
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.Coerce(int),
                vol.Required(CONF_RACK, default=DEFAULT_RACK): vol.Coerce(int),
                vol.Required(CONF_SLOT, default=DEFAULT_SLOT): vol.Coerce(int),
                vol.Required(
                    CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL
                ): vol.Coerce(int),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def _test_connection(self, user_input: dict[str, Any]) -> None:
        """Try to connect to the PLC and immediately disconnect."""
        client = PLCClient(
            host=user_input[CONF_HOST],
            rack=user_input[CONF_RACK],
            slot=user_input[CONF_SLOT],
            port=user_input[CONF_PORT],
        )
        await self.hass.async_add_executor_job(client.connect)
        await self.hass.async_add_executor_job(client.disconnect)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "VipaPlcOptionsFlow":
        """Return the options flow handler."""
        return VipaPlcOptionsFlow(config_entry)


class VipaPlcOptionsFlow(config_entries.OptionsFlow):
    """Handle options (entity management) for an existing PLC config entry."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entities: list[dict[str, Any]] = list(
            config_entry.options.get(CONF_ENTITIES, [])
        )
        self._selected_entity_id: str | None = None

    # ------------------------------------------------------------------
    # Main menu
    # ------------------------------------------------------------------

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show the options menu."""
        return await self.async_step_menu()

    async def async_step_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show a menu with entity-management actions."""
        return self.async_show_menu(
            step_id=_STEP_MENU,
            menu_options=[
                _STEP_ADD_BINARY_SENSOR,
                _STEP_ADD_BUTTON,
                _STEP_LIST_ENTITIES,
            ],
        )

    # ------------------------------------------------------------------
    # Add binary sensor
    # ------------------------------------------------------------------

    async def async_step_add_binary_sensor(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle adding a binary sensor."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                parse_address(user_input[CONF_ADDRESS])
            except AddressParseError:
                errors[CONF_ADDRESS] = "invalid_address"
            else:
                entity: dict[str, Any] = {
                    "id": str(uuid.uuid4()),
                    CONF_ENTITY_TYPE: ENTITY_TYPE_BINARY_SENSOR,
                    CONF_ENTITY_NAME: user_input[CONF_ENTITY_NAME],
                    CONF_ADDRESS: user_input[CONF_ADDRESS],
                    CONF_DEVICE_CLASS: user_input.get(CONF_DEVICE_CLASS) or None,
                    CONF_INVERT: user_input.get(CONF_INVERT, DEFAULT_INVERT),
                }
                self._entities.append(entity)
                return self._save_and_exit()

        schema = vol.Schema(
            {
                vol.Required(CONF_ENTITY_NAME): str,
                vol.Required(CONF_ADDRESS): str,
                vol.Optional(CONF_DEVICE_CLASS, default=""): vol.In(
                    BINARY_SENSOR_DEVICE_CLASSES
                ),
                vol.Optional(CONF_INVERT, default=DEFAULT_INVERT): bool,
            }
        )

        return self.async_show_form(
            step_id=_STEP_ADD_BINARY_SENSOR,
            data_schema=schema,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Add button
    # ------------------------------------------------------------------

    async def async_step_add_button(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle adding a button."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                parse_address(user_input[CONF_ADDRESS])
            except AddressParseError:
                errors[CONF_ADDRESS] = "invalid_address"
            else:
                entity: dict[str, Any] = {
                    "id": str(uuid.uuid4()),
                    CONF_ENTITY_TYPE: ENTITY_TYPE_BUTTON,
                    CONF_ENTITY_NAME: user_input[CONF_ENTITY_NAME],
                    CONF_ADDRESS: user_input[CONF_ADDRESS],
                    CONF_PULSE_DURATION: user_input.get(
                        CONF_PULSE_DURATION, DEFAULT_PULSE_DURATION
                    ),
                }
                self._entities.append(entity)
                return self._save_and_exit()

        schema = vol.Schema(
            {
                vol.Required(CONF_ENTITY_NAME): str,
                vol.Required(CONF_ADDRESS): str,
                vol.Optional(
                    CONF_PULSE_DURATION, default=DEFAULT_PULSE_DURATION
                ): vol.Coerce(float),
            }
        )

        return self.async_show_form(
            step_id=_STEP_ADD_BUTTON,
            data_schema=schema,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # List / delete entities
    # ------------------------------------------------------------------

    async def async_step_list_entities(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show a list of configured entities and allow deletion."""
        errors: dict[str, str] = {}

        if not self._entities:
            return self.async_show_form(
                step_id=_STEP_LIST_ENTITIES,
                data_schema=vol.Schema({}),
                description_placeholders={"entities": "No entities configured yet."},
                errors=errors,
            )

        entity_choices = {
            entity["id"]: f"[{entity[CONF_ENTITY_TYPE]}] {entity[CONF_ENTITY_NAME]} ({entity[CONF_ADDRESS]})"
            for entity in self._entities
        }

        if user_input is not None:
            selected_id = user_input.get("entity_to_delete")
            if selected_id and selected_id in entity_choices:
                self._entities = [e for e in self._entities if e["id"] != selected_id]
                return self._save_and_exit()
            return self._save_and_exit()

        schema = vol.Schema(
            {
                vol.Optional("entity_to_delete"): vol.In(entity_choices),
            }
        )

        entity_list = "\n".join(f"• {label}" for label in entity_choices.values())
        return self.async_show_form(
            step_id=_STEP_LIST_ENTITIES,
            data_schema=schema,
            description_placeholders={"entities": entity_list},
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _save_and_exit(self) -> FlowResult:
        """Persist entity list and close options flow."""
        return self.async_create_entry(
            title="",
            data={CONF_ENTITIES: self._entities},
        )
