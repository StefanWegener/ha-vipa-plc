# ha-vipa-plc

A Home Assistant custom integration for VIPA / S7 PLCs (SPEED7 CPUs), distributed as a HACS custom integration.

## Features

- One config entry = one PLC connection
- One Home Assistant device per PLC
- UI-based entity management (no YAML required)
- Supported entity types:
  - **Binary Sensor** – reads a DB bit from the PLC (with optional invert)
  - **Button** – pulses a DB bit (write True → sleep → write False)
- Communication via [`python-snap7`](https://python-snap7.readthedocs.io/)

## Supported Address Format

Only S7 DB bit addresses in the form `DB<number>,X<byte>.<bit>` are supported:

```
DB2,X0.0    → DB 2, byte 0, bit 0
DB12,X6.0   → DB 12, byte 6, bit 0
```

## Requirements

- Home Assistant 2024.1 or newer
- `python-snap7==1.3` (installed automatically)
- A VIPA / S7-compatible PLC accessible on the network

## Installation via HACS

1. Add this repository as a custom HACS repository (category: Integration)
2. Install **VIPA PLC** from HACS
3. Restart Home Assistant
4. Go to **Settings → Devices & Services → Add Integration** and search for *VIPA PLC*

## Configuration

### Connection Parameters

| Parameter        | Default | Description                          |
|-----------------|---------|--------------------------------------|
| Name             | VIPA PLC | Display name for the device         |
| Host             | –       | IP address of the PLC                |
| Port             | 102     | ISO-on-TCP port                      |
| Rack             | 0       | PLC rack number                      |
| Slot             | 2       | PLC slot number                      |
| Poll interval    | 5       | Binary sensor update interval (s)    |

### Known-good VIPA CPU 313-5BF13 settings

```
host: 192.168.3.125
port: 102
rack: 0
slot: 2
```

## Adding Entities

After the PLC is configured, open **Options** to add entities:

- **Add binary sensor** – name, S7 address, optional device class, optional invert
- **Add button** – name, S7 address, pulse duration (default 0.5 s)
- **View / delete entities** – list and remove existing entities

## License

MIT
