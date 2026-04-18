"""CSV import parser for the VIPA PLC integration.

Expected format (semicolon-separated, up to 10 columns):
    entity_type;name;address1;address2;address3;device_class;invert;pulse_duration;travel_time_down;travel_time_up

Column mapping by entity type:
    binary_sensor : address1=address,  address2=–,            address3=–,            device_class, invert, –,             –,                 –
    button        : address1=address,  address2=–,            address3=–,            –,            –,      pulse_duration, –,                 –
    switch        : address1=address_on, address2=address_off, address3=address_state, –,           –,      pulse_duration, –,                 –
    cover         : address1=address_open, address2=address_close, address3=address_stop, device_class, –,  pulse_duration, travel_time_down,  travel_time_up

Rules:
    - Lines starting with # (after stripping) are treated as comments and ignored.
    - Empty lines are ignored.
    - Trailing semicolons / missing columns are padded with empty strings.
    - At least 3 columns (entity_type, name, address1) are required.
    - invert accepts "true" / "1" (case-insensitive) as True; anything else is False.
    - pulse_duration must be a positive float; defaults to DEFAULT_PULSE_DURATION when empty.
    - Addresses are validated with parse_address(); empty optional addresses are stored as None.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

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
    CONF_HOLD_MODE,
    CONF_INVERT,
    CONF_PULSE_DURATION,
    CONF_TRAVEL_TIME_DOWN,
    CONF_TRAVEL_TIME_UP,
    DEFAULT_HOLD_MODE,
    DEFAULT_INVERT,
    DEFAULT_PULSE_DURATION,
    ENTITY_TYPE_BINARY_SENSOR,
    ENTITY_TYPE_BUTTON,
    ENTITY_TYPE_COVER,
    ENTITY_TYPE_SWITCH,
)

# All supported entity types
_VALID_ENTITY_TYPES = {
    ENTITY_TYPE_BINARY_SENSOR,
    ENTITY_TYPE_BUTTON,
    ENTITY_TYPE_SWITCH,
    ENTITY_TYPE_COVER,
}

# Valid device classes (must match config_flow lists)
_VALID_BINARY_SENSOR_DEVICE_CLASSES = {
    "battery", "cold", "connectivity", "door", "garage_door", "gas", "heat",
    "light", "lock", "moisture", "motion", "moving", "occupancy", "opening",
    "plug", "power", "presence", "problem", "running", "safety", "smoke",
    "sound", "tamper", "update", "vibration", "window",
}
_VALID_COVER_DEVICE_CLASSES = {
    "awning", "blind", "curtain", "damper", "door", "garage", "gate",
    "shade", "shutter", "window",
}

# Minimum number of non-empty columns required per data row
_MIN_COLUMNS = 3


@dataclass
class CsvImportResult:
    """Result of parsing a CSV import text."""

    entities: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    @property
    def summary(self) -> str:
        """Human-readable summary of what was parsed successfully."""
        if not self.entities:
            return "No entities recognised."
        counts: dict[str, int] = {}
        for e in self.entities:
            t = e[CONF_ENTITY_TYPE]
            counts[t] = counts.get(t, 0) + 1
        parts = [f"{v} {k}" for k, v in sorted(counts.items())]
        total = len(self.entities)
        return f"{total} entit{'y' if total == 1 else 'ies'} recognised: {', '.join(parts)}"


def _pad(columns: list[str], length: int) -> list[str]:
    """Return *columns* extended with empty strings to at least *length* items."""
    return columns + [""] * max(0, length - len(columns))


def _optional_address(raw: str, column_name: str, line_no: int) -> tuple[str | None, str | None]:
    """Validate an optional address field.

    Returns (parsed_address_str, error_message) where exactly one is None.
    """
    raw = raw.strip()
    if not raw:
        return None, None
    try:
        parse_address(raw)
        return raw, None
    except AddressParseError:
        return None, f"Line {line_no}: invalid S7 address '{raw}' in column '{column_name}'."


def _required_address(raw: str, column_name: str, line_no: int) -> tuple[str | None, str | None]:
    """Validate a required address field.

    Returns (parsed_address_str, error_message) where exactly one is None.
    """
    raw = raw.strip()
    if not raw:
        return None, f"Line {line_no}: column '{column_name}' is required but empty."
    try:
        parse_address(raw)
        return raw, None
    except AddressParseError:
        return None, f"Line {line_no}: invalid S7 address '{raw}' in column '{column_name}'."


def _parse_invert(raw: str) -> bool:
    """Parse the *invert* column; default False."""
    return raw.strip().lower() in {"true", "1"}


def _parse_pulse_duration(raw: str, line_no: int) -> tuple[float, str | None]:
    """Parse the *pulse_duration* column.

    Returns (value, error_message).  Defaults to DEFAULT_PULSE_DURATION when empty.
    """
    raw = raw.strip()
    if not raw:
        return DEFAULT_PULSE_DURATION, None
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_PULSE_DURATION, f"Line {line_no}: pulse_duration '{raw}' is not a valid number; using default {DEFAULT_PULSE_DURATION}."
    if value <= 0:
        return DEFAULT_PULSE_DURATION, f"Line {line_no}: pulse_duration must be > 0; got '{raw}'; using default {DEFAULT_PULSE_DURATION}."
    return value, None


def _parse_optional_float(raw: str, column_name: str, line_no: int) -> tuple[float | None, str | None]:
    """Parse an optional positive float column.

    Returns (value_or_None, error_message_or_None).
    """
    raw = raw.strip()
    if not raw:
        return None, None
    try:
        value = float(raw)
    except ValueError:
        return None, f"Line {line_no}: {column_name} '{raw}' is not a valid number; ignoring."
    if value <= 0:
        return None, f"Line {line_no}: {column_name} must be > 0; got '{raw}'; ignoring."
    return value, None


def _build_binary_sensor(cols: list[str], line_no: int) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []

    address, err = _required_address(cols[2], "address1", line_no)
    if err:
        errors.append(err)

    if errors:
        return None, errors

    device_class = cols[5].strip() or None
    if device_class and device_class not in _VALID_BINARY_SENSOR_DEVICE_CLASSES:
        errors.append(f"Line {line_no}: unknown binary sensor device_class '{device_class}'; ignoring.")
        device_class = None
    invert = _parse_invert(cols[6])

    entity: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        CONF_ENTITY_TYPE: ENTITY_TYPE_BINARY_SENSOR,
        CONF_ENTITY_NAME: cols[1].strip(),
        CONF_ADDRESS: address,
        CONF_DEVICE_CLASS: device_class,
        CONF_INVERT: invert,
    }
    return entity, errors


def _build_button(cols: list[str], line_no: int) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []

    address, err = _required_address(cols[2], "address1", line_no)
    if err:
        errors.append(err)

    pulse_duration, warn = _parse_pulse_duration(cols[7], line_no)
    if warn:
        errors.append(warn)  # non-fatal; treated as warning but still reported

    if any(e for e in errors if "invalid" in e or "required" in e):
        return None, errors

    entity: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        CONF_ENTITY_TYPE: ENTITY_TYPE_BUTTON,
        CONF_ENTITY_NAME: cols[1].strip(),
        CONF_ADDRESS: address,
        CONF_PULSE_DURATION: pulse_duration,
    }
    return entity, errors  # may include non-fatal pulse_duration warning


def _build_switch(cols: list[str], line_no: int) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []

    addr_on, err = _required_address(cols[2], "address1 (address_on)", line_no)
    if err:
        errors.append(err)

    addr_off, err = _required_address(cols[3], "address2 (address_off)", line_no)
    if err:
        errors.append(err)

    addr_state, err = _optional_address(cols[4], "address3 (address_state)", line_no)
    if err:
        errors.append(err)

    pulse_duration, warn = _parse_pulse_duration(cols[7], line_no)
    if warn:
        errors.append(warn)

    fatal = [e for e in errors if "invalid" in e or "required" in e]
    if fatal:
        return None, errors

    entity: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        CONF_ENTITY_TYPE: ENTITY_TYPE_SWITCH,
        CONF_ENTITY_NAME: cols[1].strip(),
        CONF_ADDRESS_ON: addr_on,
        CONF_ADDRESS_OFF: addr_off,
        CONF_ADDRESS_STATE: addr_state,
        CONF_PULSE_DURATION: pulse_duration,
    }
    return entity, errors


def _build_cover(cols: list[str], line_no: int) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []

    addr_open, err = _required_address(cols[2], "address1 (address_open)", line_no)
    if err:
        errors.append(err)

    addr_close, err = _required_address(cols[3], "address2 (address_close)", line_no)
    if err:
        errors.append(err)

    addr_stop, err = _optional_address(cols[4], "address3 (address_stop)", line_no)
    if err:
        errors.append(err)

    pulse_duration, warn = _parse_pulse_duration(cols[7], line_no)
    if warn:
        errors.append(warn)

    travel_time_down, warn = _parse_optional_float(cols[8], "travel_time_down", line_no)
    if warn:
        errors.append(warn)

    travel_time_up, warn = _parse_optional_float(cols[9], "travel_time_up", line_no)
    if warn:
        errors.append(warn)

    fatal = [e for e in errors if "invalid" in e or "required" in e]
    if fatal:
        return None, errors

    device_class = cols[5].strip() or None
    if device_class and device_class not in _VALID_COVER_DEVICE_CLASSES:
        errors.append(f"Line {line_no}: unknown cover device_class '{device_class}'; ignoring.")
        device_class = None

    entity: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        CONF_ENTITY_TYPE: ENTITY_TYPE_COVER,
        CONF_ENTITY_NAME: cols[1].strip(),
        CONF_ADDRESS_OPEN: addr_open,
        CONF_ADDRESS_CLOSE: addr_close,
        CONF_ADDRESS_STOP: addr_stop,
        CONF_DEVICE_CLASS: device_class,
        CONF_PULSE_DURATION: pulse_duration,
        CONF_HOLD_MODE: DEFAULT_HOLD_MODE,
        CONF_TRAVEL_TIME_DOWN: travel_time_down,
        CONF_TRAVEL_TIME_UP: travel_time_up,
    }
    return entity, errors


_BUILDERS = {
    ENTITY_TYPE_BINARY_SENSOR: _build_binary_sensor,
    ENTITY_TYPE_BUTTON: _build_button,
    ENTITY_TYPE_SWITCH: _build_switch,
    ENTITY_TYPE_COVER: _build_cover,
}


def parse_csv(text: str) -> CsvImportResult:
    """Parse *text* in the VIPA PLC import CSV format.

    Returns a :class:`CsvImportResult` containing valid entity dicts and any
    error messages.  Errors are non-fatal at the file level: valid rows are
    always returned even when other rows fail.
    """
    result = CsvImportResult()

    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()

        # Skip comments and empty lines
        if not line or line.startswith("#"):
            continue

        cols = [c for c in line.split(";")]
        cols = _pad(cols, 10)

        entity_type = cols[0].strip().lower()
        name = cols[1].strip()

        # Validate entity type
        if entity_type not in _VALID_ENTITY_TYPES:
            result.errors.append(
                f"Line {line_no}: unknown entity_type '{cols[0].strip()}'. "
                f"Allowed values: {', '.join(sorted(_VALID_ENTITY_TYPES))}."
            )
            continue

        # Validate name
        if not name:
            result.errors.append(f"Line {line_no}: name (column 2) is required but empty.")
            continue

        # Validate minimum columns
        if not cols[2].strip():
            result.errors.append(
                f"Line {line_no}: address1 (column 3) is required but empty."
            )
            continue

        builder = _BUILDERS[entity_type]
        entity, errors = builder(cols, line_no)

        for err in errors:
            result.errors.append(err)

        if entity is not None:
            result.entities.append(entity)

    return result


def merge_entities(
    existing: list[dict[str, Any]],
    imported: list[dict[str, Any]],
    skip_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Merge *imported* entities into *existing*, overwriting by name.

    Entities whose ``"id"`` is in *skip_ids* are not imported.
    When an imported entity has the same :data:`CONF_ENTITY_NAME` as an
    existing one, the existing entry is replaced (preserving its ``"id"``).

    Returns the new combined list.
    """
    skip_ids = skip_ids or set()

    # Build mutable copy indexed by name for O(1) lookup
    by_name: dict[str, dict[str, Any]] = {e[CONF_ENTITY_NAME]: e for e in existing}
    # Preserve original insertion order
    order: list[str] = [e[CONF_ENTITY_NAME] for e in existing]

    for imp in imported:
        if imp["id"] in skip_ids:
            continue

        imp_name = imp[CONF_ENTITY_NAME]
        if imp_name in by_name:
            # Overwrite in-place, keep original id so HA entity registry is stable
            original_id = by_name[imp_name]["id"]
            by_name[imp_name] = {**imp, "id": original_id}
        else:
            by_name[imp_name] = imp
            order.append(imp_name)

    return [by_name[n] for n in order if n in by_name]
