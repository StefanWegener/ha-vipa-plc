# ha-vipa-plc

A Home Assistant custom integration for VIPA / Siemens S7 PLCs (SPEED7 CPUs), distributed as a HACS custom integration.

## Features

- One config entry = one PLC connection
- One Home Assistant device per PLC
- UI-based entity management (no YAML required)
- Supported entity types:
  - **Binary Sensor** – reads a DB bit from the PLC (with optional invert and device class)
  - **Button** – pulses a DB bit (write True → sleep → write False)
  - **Switch** – dual-address impulse switch (separate ON and OFF addresses, optional state feedback address)
  - **Cover** – shutter/blind control with open, close, and optional stop addresses (optimistic mode)
- Communication via [`python-snap7`](https://python-snap7.readthedocs.io/)

## Supported Address Format

Only S7 DB bit addresses in the form `DB<number>,X<byte>.<bit>` are supported:

```
DB1,X0.0    → DB 1, byte 0, bit 0
DB10,X4.3   → DB 10, byte 4, bit 3
```

## Requirements

- Home Assistant 2024.1 or newer
- `python-snap7==2.1.0` (installed automatically)
- A VIPA / S7-compatible PLC accessible on the network

## Installation via HACS

1. Add this repository as a custom HACS repository (category: Integration)
2. Install **VIPA PLC** from HACS
3. Restart Home Assistant
4. Go to **Settings → Devices & Services → Add Integration** and search for *VIPA PLC*

## Configuration

### Connection Parameters

| Parameter     | Default  | Description                         |
|---------------|----------|-------------------------------------|
| Name          | VIPA PLC | Display name for the device         |
| Host          | –        | IP address of the PLC               |
| Port          | 102      | ISO-on-TCP port (S7 default)        |
| Rack          | 0        | PLC rack number                     |
| Slot          | 2        | PLC slot number (CPU slot)          |
| Poll interval | 5        | Sensor update interval in seconds   |

## Adding Entities

After the PLC is configured, open **Options** to manage entities:

### Binary Sensor

Reads a single DB bit from the PLC.

| Field        | Required | Description                                          |
|--------------|----------|------------------------------------------------------|
| Name         | yes      | Entity display name                                  |
| Address      | yes      | S7 address, e.g. `DB1,X0.0`                         |
| Device class | no       | HA binary sensor device class (door, window, …)      |
| Invert       | no       | Invert the read value                                |

### Button

Sends a momentary pulse to a DB bit.

| Field          | Required | Description                              |
|----------------|----------|------------------------------------------|
| Name           | yes      | Entity display name                      |
| Address        | yes      | S7 address, e.g. `DB1,X0.0`             |
| Pulse duration | no       | High time in seconds (default: 0.5 s)    |

### Switch

Controls a device via two separate impulse addresses (ON and OFF), with optional state feedback.

| Field         | Required | Description                                        |
|---------------|----------|----------------------------------------------------|
| Name          | yes      | Entity display name                                |
| Address ON    | yes      | S7 address to pulse for turning on                 |
| Address OFF   | yes      | S7 address to pulse for turning off                |
| Address state | no       | S7 address to read the actual state (feedback bit) |
| Pulse duration| no       | High time in seconds (default: 0.5 s)              |

If no state address is provided the switch operates in optimistic mode.

### Cover

Controls shutters, blinds, or similar devices.

| Field         | Required | Description                                    |
|---------------|----------|------------------------------------------------|
| Name          | yes      | Entity display name                            |
| Address OPEN  | yes      | S7 address to pulse for opening                |
| Address CLOSE | yes      | S7 address to pulse for closing                |
| Address STOP  | no       | S7 address to pulse for stopping               |
| Device class  | no       | HA cover device class (shutter, blind, …)      |
| Pulse duration| no       | High time in seconds (default: 0.5 s)          |

Cover always operates in optimistic mode (no position feedback from PLC).

## Notes

- The integration has been tested on Home Assistant Green (aarch64) running HAOS.
- `libsnap7.so` is loaded explicitly from the python-snap7 wheel to ensure compatibility with HAOS (no `ldconfig` available).
- After editing or deleting entities via Options, Home Assistant may need to be reloaded manually for changes to take effect.

## License

MIT
