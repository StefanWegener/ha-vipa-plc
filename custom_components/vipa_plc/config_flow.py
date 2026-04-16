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
    CONF_ADDRESS_CLOSE,
    CONF_ADDRESS_OFF,
    CONF_ADDRESS_ON,
    CONF_ADDRESS_OPEN,
    CONF_ADDRESS_STATE,
    CONF_ADDRESS_STOP,
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
    ENTITY_TYPE_COVER,
    ENTITY_TYPE_SWITCH,
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

# Cover device classes supported in the options UI
COVER_DEVICE_CLASSES = [
    "",
    "awning",
    "blind",
    "curtain",
    "damper",
    "door",
    "garage",
    "gate",
    "shade",
    "shutter",
    "window",
]

# Sub-steps for the options flow
_STEP_MENU = "menu"
_STEP_ADD_BINARY_SENSOR = "add_binary_sensor"
_STEP_ADD_BUTTON = "add_button"
_STEP_ADD_SWITCH = "add_switch"
_STEP_ADD_COVER = "add_cover"
_STEP_LIST_ENTITIES = "list_entities"
_STEP_EDIT_ENTITY = "edit_entity"
_STEP_EDIT_BINARY_SENSOR = "edit_binary_sensor"
_STEP_EDIT_BUTTON = "edit_button"
_STEP_EDIT_SWITCH = "edit_switch"
_STEP_EDIT_COVER = "edit_cover"


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
                _STEP_ADD_SWITCH,
                _STEP_ADD_COVER,
                _STEP_EDIT_ENTITY,
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
    # Add switch
    # ------------------------------------------------------------------

    async def async_step_add_switch(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle adding a switch (dual-address impulse)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate ON address
            try:
                parse_address(user_input[CONF_ADDRESS_ON])
            except AddressParseError:
                errors[CONF_ADDRESS_ON] = "invalid_address"

            # Validate OFF address
            try:
                parse_address(user_input[CONF_ADDRESS_OFF])
            except AddressParseError:
                errors[CONF_ADDRESS_OFF] = "invalid_address"

            # Validate optional state address
            state_addr = user_input.get(CONF_ADDRESS_STATE, "").strip()
            if state_addr:
                try:
                    parse_address(state_addr)
                except AddressParseError:
                    errors[CONF_ADDRESS_STATE] = "invalid_address"
            else:
                state_addr = None

            if not errors:
                entity: dict[str, Any] = {
                    "id": str(uuid.uuid4()),
                    CONF_ENTITY_TYPE: ENTITY_TYPE_SWITCH,
                    CONF_ENTITY_NAME: user_input[CONF_ENTITY_NAME],
                    CONF_ADDRESS_ON: user_input[CONF_ADDRESS_ON],
                    CONF_ADDRESS_OFF: user_input[CONF_ADDRESS_OFF],
                    CONF_ADDRESS_STATE: state_addr,
                    CONF_PULSE_DURATION: user_input.get(
                        CONF_PULSE_DURATION, DEFAULT_PULSE_DURATION
                    ),
                }
                self._entities.append(entity)
                return self._save_and_exit()

        schema = vol.Schema(
            {
                vol.Required(CONF_ENTITY_NAME): str,
                vol.Required(CONF_ADDRESS_ON): str,
                vol.Required(CONF_ADDRESS_OFF): str,
                vol.Optional(CONF_ADDRESS_STATE, default=""): str,
                vol.Optional(
                    CONF_PULSE_DURATION, default=DEFAULT_PULSE_DURATION
                ): vol.Coerce(float),
            }
        )

        return self.async_show_form(
            step_id=_STEP_ADD_SWITCH,
            data_schema=schema,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Add cover
    # ------------------------------------------------------------------

    async def async_step_add_cover(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle adding a cover (shutter/blind)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            for key in (CONF_ADDRESS_OPEN, CONF_ADDRESS_CLOSE):
                try:
                    parse_address(user_input[key])
                except AddressParseError:
                    errors[key] = "invalid_address"

            stop_addr = user_input.get(CONF_ADDRESS_STOP, "").strip()
            if stop_addr:
                try:
                    parse_address(stop_addr)
                except AddressParseError:
                    errors[CONF_ADDRESS_STOP] = "invalid_address"
            else:
                stop_addr = None

            if not errors:
                entity: dict[str, Any] = {
                    "id": str(uuid.uuid4()),
                    CONF_ENTITY_TYPE: ENTITY_TYPE_COVER,
                    CONF_ENTITY_NAME: user_input[CONF_ENTITY_NAME],
                    CONF_ADDRESS_OPEN: user_input[CONF_ADDRESS_OPEN],
                    CONF_ADDRESS_CLOSE: user_input[CONF_ADDRESS_CLOSE],
                    CONF_ADDRESS_STOP: stop_addr,
                    CONF_DEVICE_CLASS: user_input.get(CONF_DEVICE_CLASS) or None,
                    CONF_PULSE_DURATION: user_input.get(CONF_PULSE_DURATION, DEFAULT_PULSE_DURATION),
                }
                self._entities.append(entity)
                return self._save_and_exit()

        schema = vol.Schema(
            {
                vol.Required(CONF_ENTITY_NAME): str,
                vol.Required(CONF_ADDRESS_OPEN): str,
                vol.Required(CONF_ADDRESS_CLOSE): str,
                vol.Optional(CONF_ADDRESS_STOP): str,
                vol.Optional(CONF_DEVICE_CLASS): vol.In(COVER_DEVICE_CLASSES),
                vol.Optional(CONF_PULSE_DURATION): vol.Coerce(float),
            }
        )
        return self.async_show_form(
            step_id=_STEP_ADD_COVER,
            data_schema=self.add_suggested_values_to_schema(
                schema, {CONF_PULSE_DURATION: DEFAULT_PULSE_DURATION}
            ),
            errors=errors,
        )

    def _entity_label(self, entity: dict[str, Any]) -> str:
        """Return a human-readable label for an entity."""
        etype = entity[CONF_ENTITY_TYPE]
        name = entity[CONF_ENTITY_NAME]
        if etype == ENTITY_TYPE_SWITCH:
            return f"[{etype}] {name} (ON:{entity.get(CONF_ADDRESS_ON,'?')} / OFF:{entity.get(CONF_ADDRESS_OFF,'?')})"
        if etype == ENTITY_TYPE_COVER:
            return f"[{etype}] {name} (open:{entity.get(CONF_ADDRESS_OPEN,'?')} / close:{entity.get(CONF_ADDRESS_CLOSE,'?')})"
        return f"[{etype}] {name} ({entity.get(CONF_ADDRESS,'?')})"

    # ------------------------------------------------------------------
    # Edit entity — step 1: select which entity to edit
    # ------------------------------------------------------------------

    async def async_step_edit_entity(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Let the user pick an entity to edit."""
        if not self._entities:
            return self.async_show_form(
                step_id=_STEP_EDIT_ENTITY,
                data_schema=vol.Schema({}),
                description_placeholders={"entities": "No entities configured yet."},
            )

        entity_choices = {e["id"]: self._entity_label(e) for e in self._entities}

        if user_input is not None:
            selected_id = user_input.get("entity_to_edit")
            if selected_id:
                self._selected_entity_id = selected_id
                entity = next(e for e in self._entities if e["id"] == selected_id)
                etype = entity[CONF_ENTITY_TYPE]
                if etype == ENTITY_TYPE_BINARY_SENSOR:
                    return await self.async_step_edit_binary_sensor()
                if etype == ENTITY_TYPE_BUTTON:
                    return await self.async_step_edit_button()
                if etype == ENTITY_TYPE_SWITCH:
                    return await self.async_step_edit_switch()
                if etype == ENTITY_TYPE_COVER:
                    return await self.async_step_edit_cover()
            return self._save_and_exit()

        schema = vol.Schema(
            {vol.Required("entity_to_edit"): vol.In(entity_choices)}
        )
        return self.async_show_form(step_id=_STEP_EDIT_ENTITY, data_schema=schema)

    # ------------------------------------------------------------------
    # Edit binary sensor
    # ------------------------------------------------------------------

    async def async_step_edit_binary_sensor(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle editing a binary sensor."""
        errors: dict[str, str] = {}
        entity = next(e for e in self._entities if e["id"] == self._selected_entity_id)

        if user_input is not None:
            try:
                parse_address(user_input[CONF_ADDRESS])
            except AddressParseError:
                errors[CONF_ADDRESS] = "invalid_address"
            else:
                entity.update(
                    {
                        CONF_ENTITY_NAME: user_input[CONF_ENTITY_NAME],
                        CONF_ADDRESS: user_input[CONF_ADDRESS],
                        CONF_DEVICE_CLASS: user_input.get(CONF_DEVICE_CLASS) or None,
                        CONF_INVERT: user_input.get(CONF_INVERT, DEFAULT_INVERT),
                    }
                )
                return self._save_and_exit()

        schema = vol.Schema(
            {
                vol.Required(CONF_ENTITY_NAME): str,
                vol.Required(CONF_ADDRESS): str,
                vol.Optional(CONF_DEVICE_CLASS): vol.In(BINARY_SENSOR_DEVICE_CLASSES),
                vol.Optional(CONF_INVERT): bool,
            }
        )
        return self.async_show_form(
            step_id=_STEP_EDIT_BINARY_SENSOR,
            data_schema=self.add_suggested_values_to_schema(
                schema,
                {
                    CONF_ENTITY_NAME: entity[CONF_ENTITY_NAME],
                    CONF_ADDRESS: entity[CONF_ADDRESS],
                    CONF_DEVICE_CLASS: entity.get(CONF_DEVICE_CLASS) or "",
                    CONF_INVERT: entity.get(CONF_INVERT, DEFAULT_INVERT),
                },
            ),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Edit button
    # ------------------------------------------------------------------

    async def async_step_edit_button(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle editing a button."""
        errors: dict[str, str] = {}
        entity = next(e for e in self._entities if e["id"] == self._selected_entity_id)

        if user_input is not None:
            try:
                parse_address(user_input[CONF_ADDRESS])
            except AddressParseError:
                errors[CONF_ADDRESS] = "invalid_address"
            else:
                entity.update(
                    {
                        CONF_ENTITY_NAME: user_input[CONF_ENTITY_NAME],
                        CONF_ADDRESS: user_input[CONF_ADDRESS],
                        CONF_PULSE_DURATION: user_input.get(
                            CONF_PULSE_DURATION, DEFAULT_PULSE_DURATION
                        ),
                    }
                )
                return self._save_and_exit()

        schema = vol.Schema(
            {
                vol.Required(CONF_ENTITY_NAME): str,
                vol.Required(CONF_ADDRESS): str,
                vol.Optional(CONF_PULSE_DURATION): vol.Coerce(float),
            }
        )
        return self.async_show_form(
            step_id=_STEP_EDIT_BUTTON,
            data_schema=self.add_suggested_values_to_schema(
                schema,
                {
                    CONF_ENTITY_NAME: entity[CONF_ENTITY_NAME],
                    CONF_ADDRESS: entity[CONF_ADDRESS],
                    CONF_PULSE_DURATION: entity.get(CONF_PULSE_DURATION, DEFAULT_PULSE_DURATION),
                },
            ),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Edit switch
    # ------------------------------------------------------------------

    async def async_step_edit_switch(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle editing a switch."""
        errors: dict[str, str] = {}
        entity = next(e for e in self._entities if e["id"] == self._selected_entity_id)

        if user_input is not None:
            try:
                parse_address(user_input[CONF_ADDRESS_ON])
            except AddressParseError:
                errors[CONF_ADDRESS_ON] = "invalid_address"

            try:
                parse_address(user_input[CONF_ADDRESS_OFF])
            except AddressParseError:
                errors[CONF_ADDRESS_OFF] = "invalid_address"

            state_addr = user_input.get(CONF_ADDRESS_STATE, "").strip()
            if state_addr:
                try:
                    parse_address(state_addr)
                except AddressParseError:
                    errors[CONF_ADDRESS_STATE] = "invalid_address"
            else:
                state_addr = None

            if not errors:
                entity.update(
                    {
                        CONF_ENTITY_NAME: user_input[CONF_ENTITY_NAME],
                        CONF_ADDRESS_ON: user_input[CONF_ADDRESS_ON],
                        CONF_ADDRESS_OFF: user_input[CONF_ADDRESS_OFF],
                        CONF_ADDRESS_STATE: state_addr,
                        CONF_PULSE_DURATION: user_input.get(
                            CONF_PULSE_DURATION, DEFAULT_PULSE_DURATION
                        ),
                    }
                )
                return self._save_and_exit()

        schema = vol.Schema(
            {
                vol.Required(CONF_ENTITY_NAME): str,
                vol.Required(CONF_ADDRESS_ON): str,
                vol.Required(CONF_ADDRESS_OFF): str,
                vol.Optional(CONF_ADDRESS_STATE): str,
                vol.Optional(CONF_PULSE_DURATION): vol.Coerce(float),
            }
        )
        return self.async_show_form(
            step_id=_STEP_EDIT_SWITCH,
            data_schema=self.add_suggested_values_to_schema(
                schema,
                {
                    CONF_ENTITY_NAME: entity[CONF_ENTITY_NAME],
                    CONF_ADDRESS_ON: entity[CONF_ADDRESS_ON],
                    CONF_ADDRESS_OFF: entity[CONF_ADDRESS_OFF],
                    CONF_ADDRESS_STATE: entity.get(CONF_ADDRESS_STATE) or "",
                    CONF_PULSE_DURATION: entity.get(CONF_PULSE_DURATION, DEFAULT_PULSE_DURATION),
                },
            ),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # List / delete entities
    # ------------------------------------------------------------------

    async def async_step_list_entities(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show a list of configured entities and allow deletion."""
        if not self._entities:
            return self.async_show_form(
                step_id=_STEP_LIST_ENTITIES,
                data_schema=vol.Schema({}),
                description_placeholders={"entities": "No entities configured yet."},
            )

        entity_choices = {e["id"]: self._entity_label(e) for e in self._entities}

        if user_input is not None:
            selected_id = user_input.get("entity_to_delete")
            if selected_id and selected_id in entity_choices:
                self._entities = [e for e in self._entities if e["id"] != selected_id]
            return self._save_and_exit()

        schema = vol.Schema(
            {vol.Required("entity_to_delete"): vol.In(entity_choices)}
        )
        entity_list = "\n".join(f"• {label}" for label in entity_choices.values())
        return self.async_show_form(
            step_id=_STEP_LIST_ENTITIES,
            data_schema=schema,
            description_placeholders={"entities": entity_list},
        )

    # ------------------------------------------------------------------
    # Edit cover
    # ------------------------------------------------------------------

    async def async_step_edit_cover(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle editing a cover."""
        errors: dict[str, str] = {}
        entity = next(e for e in self._entities if e["id"] == self._selected_entity_id)

        if user_input is not None:
            for key in (CONF_ADDRESS_OPEN, CONF_ADDRESS_CLOSE):
                try:
                    parse_address(user_input[key])
                except AddressParseError:
                    errors[key] = "invalid_address"

            stop_addr = user_input.get(CONF_ADDRESS_STOP, "").strip()
            if stop_addr:
                try:
                    parse_address(stop_addr)
                except AddressParseError:
                    errors[CONF_ADDRESS_STOP] = "invalid_address"
            else:
                stop_addr = None

            if not errors:
                entity.update(
                    {
                        CONF_ENTITY_NAME: user_input[CONF_ENTITY_NAME],
                        CONF_ADDRESS_OPEN: user_input[CONF_ADDRESS_OPEN],
                        CONF_ADDRESS_CLOSE: user_input[CONF_ADDRESS_CLOSE],
                        CONF_ADDRESS_STOP: stop_addr,
                        CONF_DEVICE_CLASS: user_input.get(CONF_DEVICE_CLASS) or None,
                        CONF_PULSE_DURATION: user_input.get(CONF_PULSE_DURATION, DEFAULT_PULSE_DURATION),
                    }
                )
                return self._save_and_exit()

        schema = vol.Schema(
            {
                vol.Required(CONF_ENTITY_NAME): str,
                vol.Required(CONF_ADDRESS_OPEN): str,
                vol.Required(CONF_ADDRESS_CLOSE): str,
                vol.Optional(CONF_ADDRESS_STOP): str,
                vol.Optional(CONF_DEVICE_CLASS): vol.In(COVER_DEVICE_CLASSES),
                vol.Optional(CONF_PULSE_DURATION): vol.Coerce(float),
            }
        )
        return self.async_show_form(
            step_id=_STEP_EDIT_COVER,
            data_schema=self.add_suggested_values_to_schema(
                schema,
                {
                    CONF_ENTITY_NAME: entity[CONF_ENTITY_NAME],
                    CONF_ADDRESS_OPEN: entity[CONF_ADDRESS_OPEN],
                    CONF_ADDRESS_CLOSE: entity[CONF_ADDRESS_CLOSE],
                    CONF_ADDRESS_STOP: entity.get(CONF_ADDRESS_STOP) or "",
                    CONF_DEVICE_CLASS: entity.get(CONF_DEVICE_CLASS) or "",
                    CONF_PULSE_DURATION: entity.get(CONF_PULSE_DURATION, DEFAULT_PULSE_DURATION),
                },
            ),
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
