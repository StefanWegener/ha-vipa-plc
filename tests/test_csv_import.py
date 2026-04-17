"""Tests for the VIPA PLC CSV import parser (csv_import.py).

These tests import csv_import and its dependencies (const, address) directly,
bypassing the integration __init__.py which requires a running Home Assistant
environment.  We use a meta-path finder to auto-stub any homeassistant.* and
snap7.* import so that no real HA installation is needed.
"""
from __future__ import annotations

import sys
import types
from importlib.abc import MetaPathFinder, Loader
from importlib.machinery import ModuleSpec

import pytest


# ---------------------------------------------------------------------------
# Auto-stub helper
# ---------------------------------------------------------------------------

def _make_pkg(name: str, attrs: dict | None = None) -> types.ModuleType:
    """Create a stub module and register it in sys.modules."""
    m = types.ModuleType(name)
    m.__path__ = []          # marks it as a package so sub-imports work
    m.__package__ = name
    m.__spec__ = ModuleSpec(name, None)
    for k, v in (attrs or {}).items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


def _stub_all() -> None:
    """Pre-populate sys.modules with all HA / snap7 / voluptuous stubs."""

    # ---- homeassistant (top-level package) --------------------------------
    ha = _make_pkg("homeassistant")

    _make_pkg("homeassistant.config_entries", {
        "ConfigEntry": type("ConfigEntry", (), {}),
        "ConfigFlow": type("ConfigFlow", (), {
            "__init_subclass__": classmethod(lambda cls, **kw: None),
        }),
        "OptionsFlow": type("OptionsFlow", (), {}),
    })
    _make_pkg("homeassistant.core", {
        "HomeAssistant": type("HomeAssistant", (), {}),
        "callback": lambda f: f,
    })
    _make_pkg("homeassistant.exceptions", {
        "ConfigEntryNotReady": type("ConfigEntryNotReady", (Exception,), {}),
        "HomeAssistantError": type("HomeAssistantError", (Exception,), {}),
    })
    _make_pkg("homeassistant.helpers")
    _make_pkg("homeassistant.helpers.update_coordinator", {
        "DataUpdateCoordinator": type("DataUpdateCoordinator", (), {
            "__class_getitem__": classmethod(lambda cls, item: cls),
        }),
        "UpdateFailed": type("UpdateFailed", (Exception,), {}),
    })
    _make_pkg("homeassistant.helpers.config_validation", {
        "multi_select": lambda choices: choices,
        "string": str,
    })
    _make_pkg("homeassistant.helpers.entity", {
        "DeviceInfo": dict,
        "Entity": type("Entity", (), {}),
    })
    _make_pkg("homeassistant.helpers.entity_platform", {
        "AddEntitiesCallback": None,
        "async_get_current_platform": lambda: None,
    })
    _make_pkg("homeassistant.data_entry_flow", {
        "FlowResult": dict,
    })
    _make_pkg("homeassistant.components")
    _make_pkg("homeassistant.components.binary_sensor", {
        "BinarySensorEntity": type("BinarySensorEntity", (), {}),
        "BinarySensorDeviceClass": type("BinarySensorDeviceClass", (), {}),
    })
    _make_pkg("homeassistant.components.button", {
        "ButtonEntity": type("ButtonEntity", (), {}),
    })
    _make_pkg("homeassistant.components.switch", {
        "SwitchEntity": type("SwitchEntity", (), {}),
    })
    _make_pkg("homeassistant.components.cover", {
        "CoverEntity": type("CoverEntity", (), {}),
        "CoverDeviceClass": type("CoverDeviceClass", (), {}),
        "CoverEntityFeature": type("CoverEntityFeature", (), {
            "OPEN": 1, "CLOSE": 2, "STOP": 4,
        }),
    })

    # ---- snap7 ------------------------------------------------------------
    _make_pkg("snap7")
    _make_pkg("snap7.client", {"Client": type("Client", (), {})})
    _make_pkg("snap7.util", {"get_bool": lambda *a: False, "set_bool": lambda *a: None})
    _make_pkg("snap7.error", {"S7ConnectionError": type("S7ConnectionError", (RuntimeError,), {})})
    _make_pkg("snap7.exceptions", {"Snap7Exception": type("Snap7Exception", (Exception,), {})})

    # ---- voluptuous -------------------------------------------------------
    class _Schema:
        def __init__(self, schema, **kw): self._schema = schema
        def __call__(self, data): return data

    vol = _make_pkg("voluptuous", {
        "Schema": _Schema,
        "Required": lambda k, **kw: k,
        "Optional": lambda k, **kw: k,
        "Coerce": lambda t: t,
        "In": lambda choices: choices,
        "All": lambda *a: a[0],
        "Invalid": type("Invalid", (Exception,), {}),
    })


_stub_all()

# ---------------------------------------------------------------------------
# Real imports (work now that stubs are in place)
# ---------------------------------------------------------------------------

from custom_components.vipa_plc.const import (  # noqa: E402
    CONF_ADDRESS,
    CONF_ADDRESS_STATE,
    CONF_ADDRESS_ON,
    CONF_ADDRESS_OFF,
    CONF_ADDRESS_OPEN,
    CONF_ADDRESS_CLOSE,
    CONF_ADDRESS_STOP,
    CONF_DEVICE_CLASS,
    CONF_ENTITY_NAME,
    CONF_ENTITY_TYPE,
    CONF_INVERT,
    CONF_PULSE_DURATION,
    CONF_TRAVEL_TIME_DOWN,
    CONF_TRAVEL_TIME_UP,
    DEFAULT_PULSE_DURATION,
    ENTITY_TYPE_BINARY_SENSOR,
    ENTITY_TYPE_BUTTON,
    ENTITY_TYPE_COVER,
    ENTITY_TYPE_SWITCH,
)
from custom_components.vipa_plc.csv_import import merge_entities, parse_csv  # noqa: E402


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _first(text: str):
    """Parse *text* and return the first entity dict (asserts exactly one entity)."""
    result = parse_csv(text)
    assert not result.errors, f"Unexpected errors: {result.errors}"
    assert len(result.entities) == 1
    return result.entities[0]


# ---------------------------------------------------------------------------
# binary_sensor
# ---------------------------------------------------------------------------

class TestBinarySensor:
    def test_minimal(self):
        """Only required fields; device_class and invert fall back to defaults."""
        e = _first("binary_sensor;Sensor A;DB2,X0.0;;;; ")
        assert e[CONF_ENTITY_TYPE] == ENTITY_TYPE_BINARY_SENSOR
        assert e[CONF_ENTITY_NAME] == "Sensor A"
        assert e[CONF_ADDRESS] == "DB2,X0.0"
        assert e[CONF_DEVICE_CLASS] is None
        assert e[CONF_INVERT] is False
        assert "id" in e

    def test_device_class(self):
        e = _first("binary_sensor;Window Sensor;DB2,X0.1;;;window;;")
        assert e[CONF_DEVICE_CLASS] == "window"

    def test_invert_true(self):
        e = _first("binary_sensor;Door Sensor;DB2,X0.2;;;door;true;")
        assert e[CONF_INVERT] is True

    def test_invert_numeric_one(self):
        e = _first("binary_sensor;Door Sensor;DB2,X0.3;;;door;1;")
        assert e[CONF_INVERT] is True

    def test_invert_false_explicit(self):
        e = _first("binary_sensor;Motion Sensor;DB2,X0.4;;;motion;false;")
        assert e[CONF_INVERT] is False

    def test_safety_device_class(self):
        e = _first("binary_sensor;Alarm Active;DB2,X24.0;;;safety;;")
        assert e[CONF_DEVICE_CLASS] == "safety"

    def test_sound_device_class(self):
        e = _first("binary_sensor;Doorbell;DB2,X58.1;;;sound;;")
        assert e[CONF_DEVICE_CLASS] == "sound"


# ---------------------------------------------------------------------------
# button
# ---------------------------------------------------------------------------

class TestButton:
    def test_minimal(self):
        e = _first("button;Scene Off;DB12,X10.2;;;;")
        assert e[CONF_ENTITY_TYPE] == ENTITY_TYPE_BUTTON
        assert e[CONF_ENTITY_NAME] == "Scene Off"
        assert e[CONF_ADDRESS] == "DB12,X10.2"
        assert e[CONF_PULSE_DURATION] == DEFAULT_PULSE_DURATION

    def test_custom_pulse_duration(self):
        e = _first("button;Gate Open;DB12,X15.1;;;;;2.0")
        assert e[CONF_PULSE_DURATION] == pytest.approx(2.0)

    def test_pulse_duration_float(self):
        e = _first("button;Gate Open;DB12,X15.1;;;;;0.25")
        assert e[CONF_PULSE_DURATION] == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# switch
# ---------------------------------------------------------------------------

class TestSwitch:
    def test_with_state_address(self):
        e = _first("switch;Light Room A;DB12,X6.0;DB12,X6.1;DB2,X4.5;;")
        assert e[CONF_ENTITY_TYPE] == ENTITY_TYPE_SWITCH
        assert e[CONF_ADDRESS_ON] == "DB12,X6.0"
        assert e[CONF_ADDRESS_OFF] == "DB12,X6.1"
        assert e[CONF_ADDRESS_STATE] == "DB2,X4.5"
        assert e[CONF_PULSE_DURATION] == DEFAULT_PULSE_DURATION

    def test_without_state_address(self):
        """Omitting address3 sets address_state to None (optimistic mode)."""
        e = _first("switch;Light Room B;DB12,X6.2;DB12,X6.3;;;")
        assert e[CONF_ADDRESS_STATE] is None

    def test_custom_pulse_duration(self):
        e = _first("switch;Light Outdoor;DB12,X8.4;DB12,X8.5;;;;1.5")
        assert e[CONF_PULSE_DURATION] == pytest.approx(1.5)

    def test_missing_address_off_is_error(self):
        result = parse_csv("switch;Light Room C;DB12,X6.4;;;;")
        assert result.errors
        assert not result.entities


# ---------------------------------------------------------------------------
# cover
# ---------------------------------------------------------------------------

class TestCover:
    def test_with_stop(self):
        e = _first("cover;Shutter Room A;DB12,X10.3;DB12,X10.4;DB12,X10.5;shutter;;")
        assert e[CONF_ENTITY_TYPE] == ENTITY_TYPE_COVER
        assert e[CONF_ADDRESS_OPEN] == "DB12,X10.3"
        assert e[CONF_ADDRESS_CLOSE] == "DB12,X10.4"
        assert e[CONF_ADDRESS_STOP] == "DB12,X10.5"
        assert e[CONF_DEVICE_CLASS] == "shutter"
        assert e[CONF_PULSE_DURATION] == DEFAULT_PULSE_DURATION
        assert e[CONF_TRAVEL_TIME_DOWN] is None
        assert e[CONF_TRAVEL_TIME_UP] is None

    def test_without_stop(self):
        e = _first("cover;Shutter Room B;DB12,X10.6;DB12,X10.7;;shutter;;")
        assert e[CONF_ADDRESS_STOP] is None

    def test_awning_device_class(self):
        e = _first("cover;Awning Terrace;DB12,X8.2;DB12,X8.3;;awning;;")
        assert e[CONF_DEVICE_CLASS] == "awning"

    def test_gate_device_class(self):
        e = _first("cover;Garage Gate;DB12,X14.7;DB12,X15.0;;gate;;")
        assert e[CONF_DEVICE_CLASS] == "gate"

    def test_no_device_class(self):
        e = _first("cover;Blind Office;DB12,X11.1;DB12,X11.2;DB12,X11.3;;;")
        assert e[CONF_DEVICE_CLASS] is None

    def test_custom_pulse_duration(self):
        e = _first("cover;Shutter Room C;DB12,X12.2;DB12,X12.3;DB12,X12.4;shutter;;1.5")
        assert e[CONF_PULSE_DURATION] == pytest.approx(1.5)

    def test_travel_times(self):
        """travel_time_down and travel_time_up are parsed from columns 9 and 10."""
        e = _first("cover;Rollo WZ;DB12,X10.3;DB12,X10.4;DB12,X10.5;shutter;;0.5;25;28")
        assert e[CONF_TRAVEL_TIME_DOWN] == pytest.approx(25.0)
        assert e[CONF_TRAVEL_TIME_UP] == pytest.approx(28.0)

    def test_travel_times_partial(self):
        """Only travel_time_down set; travel_time_up stays None."""
        e = _first("cover;Rollo AZ;DB12,X11.7;DB12,X12.0;DB12,X12.1;;; ;18;")
        assert e[CONF_TRAVEL_TIME_DOWN] == pytest.approx(18.0)
        assert e[CONF_TRAVEL_TIME_UP] is None

    def test_travel_times_missing(self):
        """Omitting travel times entirely yields None (backwards compatibility)."""
        e = _first("cover;Shutter Room A;DB12,X10.3;DB12,X10.4;DB12,X10.5;shutter;;")
        assert e[CONF_TRAVEL_TIME_DOWN] is None
        assert e[CONF_TRAVEL_TIME_UP] is None

    def test_travel_time_invalid_non_numeric(self):
        """Invalid travel_time produces a warning but entity is still created."""
        result = parse_csv("cover;Rollo;DB12,X10.3;DB12,X10.4;DB12,X10.5;;;0.5;bad;28")
        assert result.errors
        assert len(result.entities) == 1
        assert result.entities[0][CONF_TRAVEL_TIME_DOWN] is None
        assert result.entities[0][CONF_TRAVEL_TIME_UP] == pytest.approx(28.0)

    def test_missing_address_close_is_error(self):
        result = parse_csv("cover;Shutter Room D;DB12,X12.5;;;;shutter;;")
        assert result.errors
        assert not result.entities


# ---------------------------------------------------------------------------
# Comment and blank line handling
# ---------------------------------------------------------------------------

class TestCommentAndBlankLines:
    def test_comment_lines_ignored(self):
        csv = (
            "# This is a comment\n"
            "binary_sensor;Sensor A;DB2,X0.0;;;;\n"
            "# Another comment\n"
        )
        result = parse_csv(csv)
        assert not result.errors
        assert len(result.entities) == 1

    def test_blank_lines_ignored(self):
        csv = "\n\nbinary_sensor;Sensor A;DB2,X0.0;;;;\n\n"
        result = parse_csv(csv)
        assert len(result.entities) == 1

    def test_mixed_comments_blanks_data(self):
        csv = (
            "# Section header\n"
            "\n"
            "button;Scene Off;DB12,X10.2;;;;\n"
            "\n"
            "# Another section\n"
            "cover;Shutter A;DB12,X10.3;DB12,X10.4;DB12,X10.5;shutter;;\n"
        )
        result = parse_csv(csv)
        assert not result.errors
        assert len(result.entities) == 2

    def test_only_comments_returns_empty(self):
        csv = "# comment 1\n# comment 2\n"
        result = parse_csv(csv)
        assert not result.entities
        assert not result.errors  # comments are not errors

    def test_empty_string_returns_empty(self):
        result = parse_csv("")
        assert not result.entities
        assert not result.errors


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrors:
    def test_unknown_entity_type(self):
        result = parse_csv("sensor;Broken;DB2,X0.0;;;;")
        assert result.errors
        assert not result.entities
        assert "unknown entity_type" in result.errors[0].lower()

    def test_invalid_address_format(self):
        result = parse_csv("binary_sensor;Bad Addr;NOT_AN_ADDR;;;;")
        assert result.errors
        assert not result.entities
        assert "invalid" in result.errors[0].lower()

    def test_invalid_address_wrong_db(self):
        result = parse_csv("binary_sensor;Bad Addr;X0.0;;;;")
        assert result.errors
        assert not result.entities

    def test_missing_name(self):
        result = parse_csv("binary_sensor;;DB2,X0.0;;;;")
        assert result.errors
        assert not result.entities

    def test_missing_address1(self):
        result = parse_csv("binary_sensor;Sensor A;;;;;")
        assert result.errors
        assert not result.entities

    def test_line_number_in_error(self):
        csv = "# comment\nbinary_sensor;Bad;WRONG;;;;;"
        result = parse_csv(csv)
        assert "Line 2" in result.errors[0]

    def test_invalid_pulse_duration_non_numeric(self):
        """Non-numeric pulse_duration produces a warning but still imports the entity."""
        result = parse_csv("button;Gate;DB12,X15.1;;;;;abc")
        assert result.errors  # warning present
        assert len(result.entities) == 1  # entity still created with default duration
        assert result.entities[0][CONF_PULSE_DURATION] == DEFAULT_PULSE_DURATION

    def test_negative_pulse_duration(self):
        result = parse_csv("button;Gate;DB12,X15.1;;;;;-1.0")
        assert result.errors
        assert len(result.entities) == 1
        assert result.entities[0][CONF_PULSE_DURATION] == DEFAULT_PULSE_DURATION

    def test_mixed_valid_and_invalid_lines(self):
        """Valid rows are returned even when other rows have errors."""
        csv = (
            "binary_sensor;Good Sensor;DB2,X0.0;;;window;;\n"
            "sensor;Bad Type;DB2,X0.1;;;;\n"  # error
            "button;Good Button;DB12,X10.2;;;;\n"
        )
        result = parse_csv(csv)
        assert len(result.entities) == 2
        assert len(result.errors) == 1

    def test_too_few_columns_no_address(self):
        """Row with only entity_type and name but no address → error."""
        result = parse_csv("binary_sensor;No Address")
        assert result.errors
        assert not result.entities


# ---------------------------------------------------------------------------
# CsvImportResult helpers
# ---------------------------------------------------------------------------

class TestCsvImportResult:
    def test_summary_single_entity(self):
        result = parse_csv("button;Gate;DB12,X15.1;;;;")
        assert "1 entity" in result.summary
        assert "button" in result.summary

    def test_summary_multiple_types(self):
        csv = (
            "binary_sensor;Sensor A;DB2,X0.0;;;;\n"
            "button;Gate;DB12,X15.1;;;;\n"
            "switch;Light;DB12,X6.0;DB12,X6.1;;;\n"
            "cover;Shutter;DB12,X10.3;DB12,X10.4;DB12,X10.5;shutter;;\n"
        )
        result = parse_csv(csv)
        assert "4 entities" in result.summary
        for t in ("binary_sensor", "button", "switch", "cover"):
            assert t in result.summary

    def test_has_errors_false_when_clean(self):
        result = parse_csv("button;Gate;DB12,X15.1;;;;")
        assert not result.has_errors

    def test_has_errors_true_when_errors(self):
        result = parse_csv("sensor;Bad;DB2,X0.0;;;;")
        assert result.has_errors


# ---------------------------------------------------------------------------
# merge_entities
# ---------------------------------------------------------------------------

class TestMergeEntities:
    def _make_entity(self, name: str, etype: str = ENTITY_TYPE_BUTTON, eid: str | None = None) -> dict:
        return {
            "id": eid or f"id-{name}",
            CONF_ENTITY_TYPE: etype,
            CONF_ENTITY_NAME: name,
            CONF_ADDRESS: "DB12,X10.2",
            CONF_PULSE_DURATION: DEFAULT_PULSE_DURATION,
        }

    def test_new_entity_appended(self):
        existing = [self._make_entity("Existing")]
        imported = [self._make_entity("New")]
        merged = merge_entities(existing, imported)
        assert len(merged) == 2
        names = [e[CONF_ENTITY_NAME] for e in merged]
        assert "Existing" in names
        assert "New" in names

    def test_duplicate_name_overwrites(self):
        """Imported entity with same name replaces existing; original id is preserved."""
        existing = [self._make_entity("Light A", eid="original-id")]
        imp = self._make_entity("Light A", eid="import-id")
        imp[CONF_ADDRESS] = "DB12,X9.9"  # changed address
        merged = merge_entities(existing, [imp])
        assert len(merged) == 1
        assert merged[0]["id"] == "original-id"       # original id kept
        assert merged[0][CONF_ADDRESS] == "DB12,X9.9"  # new data applied

    def test_skip_ids_excluded(self):
        existing: list = []
        a = self._make_entity("A", eid="id-a")
        b = self._make_entity("B", eid="id-b")
        merged = merge_entities(existing, [a, b], skip_ids={"id-a"})
        assert len(merged) == 1
        assert merged[0][CONF_ENTITY_NAME] == "B"

    def test_order_preserved_existing_before_new(self):
        existing = [self._make_entity("First"), self._make_entity("Second")]
        imported = [self._make_entity("Third")]
        merged = merge_entities(existing, imported)
        names = [e[CONF_ENTITY_NAME] for e in merged]
        assert names == ["First", "Second", "Third"]

    def test_empty_existing(self):
        imported = [self._make_entity("Only")]
        merged = merge_entities([], imported)
        assert len(merged) == 1

    def test_empty_imported(self):
        existing = [self._make_entity("Only")]
        merged = merge_entities(existing, [])
        assert len(merged) == 1
