# Goran's Home Assistant Add-ons

[![License: MIT](https://img.shields.io/github/license/gmrvos2/ha-addons)](LICENSE)
[![GitHub last commit](https://img.shields.io/github/last-commit/gmrvos2/ha-addons)](https://github.com/gmrvos2/ha-addons/commits/main)

Custom Home Assistant add-ons for solar energy monitoring.

## Add-ons

| Add-on | Description | Version |
|--------|-------------|---------|
| [Inverter Bridge](inverter-bridge/) | Voltronic SolarPower inverter MQTT bridge | 3.2.3 |

## Installation

### Prerequisites

Before installing, make sure you have:

1. **MQTT broker** — Install the **Mosquitto broker** add-on from the official HA add-on store:
   - Go to **Settings** > **Add-ons** > **Add-on Store**
   - Search for "Mosquitto broker" and install it
   - Start the Mosquitto add-on
   - Go to **Settings** > **Devices & Services** > **MQTT** and configure it
   - *The Inverter Bridge will not work without an MQTT broker*

2. **Inverter connected via USB** — Connect your Voltronic inverter to your HA machine with either:
   - USB HID cable (the one that came with the inverter) — appears as `/dev/hidraw0`
   - USB-to-RS232 serial adapter — appears as `/dev/ttyUSB0`

### Install the add-on

1. Open Home Assistant
2. Go to **Settings** > **Add-ons** > **Add-on Store**
3. Click the menu (top right) > **Repositories**
4. Add this URL: `https://github.com/gmrvos2/ha-addons`
5. Click **Close**, then find **Inverter Bridge** in the store
6. Click **Install**
7. Go to the **Configuration** tab and verify MQTT settings (defaults work if you use Mosquitto)
8. Click **Start**
9. Check the **Log** tab — you should see `⚡ Inverter Bridge v3.2.3` and sensor readings

---

## Inverter Bridge

MQTT bridge for Voltronic Power solar inverters. Reads real-time data via USB HID or RS232 and publishes to Home Assistant through MQTT auto-discovery.

### How it works

The add-on communicates with the inverter using the **P17 protocol** (reverse-engineered from Voltronic's SolarPower desktop application). It sends GS (General Status), PS (Power Status), and MOD (Mode) commands, then publishes parsed sensor data to MQTT with Home Assistant auto-discovery — sensors appear automatically, no YAML configuration needed.

### Supported inverters

This add-on works with **Voltronic Power** hybrid inverters and their OEM variants:

- Axpert (King, MKS, VM, MAX series)
- MPP Solar (PIP, LV, MPI series)
- SolarPower (hybrid series)
- Easun, Kodak, Effekta, Voltacon, and other Voltronic OEMs

**Tested on:** Voltronic SolarPower hybrid, Protocol ID 17, firmware 00001.01

> **Note:** Currently verified with P17 protocol. Other Voltronic protocols (PI30, PI18, P16, P20) may work but are untested. If you have a different model, please open an issue with your `PI` command output.

### Supported transports

| Transport | Device | How it works |
|-----------|--------|-------------|
| **USB HID** (default) | `/dev/hidraw0` | Direct USB connection, VID `0665` PID `5161` |
| **RS232 Serial** | `/dev/ttyUSB0` | USB-to-serial adapter (PL2303, CH340, etc.) |

**Auto-detect** (default): The add-on checks for HID first, falls back to serial. No configuration needed — just plug in the cable.

### Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `mqtt_host` | `core-mosquitto` | MQTT broker hostname |
| `mqtt_port` | `1883` | MQTT broker port |
| `mqtt_user` | _(empty)_ | MQTT username |
| `mqtt_password` | _(empty)_ | MQTT password |
| `poll_interval` | `30` | Seconds between readings |
| `transport` | `auto` | `auto`, `hid`, or `serial` |
| `hid_device` | `/dev/hidraw0` | HID device path |
| `serial_port` | `/dev/ttyUSB0` | Serial port path |
| `serial_baud` | `2400` | Serial baud rate |
| `device_name` | `Solar Inverter` | Device name in HA |
| `log_level` | `info` | `debug`, `info`, `warning`, `error` |

### Sensors

The add-on creates these sensors automatically via MQTT discovery:

| Sensor | Unit | Description |
|--------|------|-------------|
| Grid Voltage | V | Utility grid voltage |
| Grid Frequency | Hz | Utility grid frequency |
| AC Output Voltage | V | Inverter AC output voltage |
| AC Output Frequency | Hz | Inverter AC output frequency |
| AC Output Apparent Power | VA | Apparent power output |
| AC Output Active Power | W | Active (real) power output |
| Output Load | % | Load as percentage of capacity |
| Bus Voltage | V | Internal DC bus voltage |
| Battery Voltage | V | Battery bank voltage |
| Battery Charging Current | A | Current flowing into battery |
| Battery Capacity | % | Estimated battery state of charge |
| Inverter Temperature | °C | Heat sink temperature |
| PV Input Current | A | Solar panel input current |
| PV Input Voltage | V | Solar panel input voltage |
| PV Input Power | W | Solar power generation (PV1 + PV2) |
| Battery Discharge Current | A | Current flowing from battery |
| Battery Voltage (SCC) | V | Battery voltage at solar charge controller |
| Inverter Mode | — | Current mode (Line, Battery, Standby, Fault...) |

**Binary sensors:** Load (on/off), Charging, SCC Charging, AC Charging

### Known limitations

- Only P17 protocol is fully tested (Protocol ID 17)
- RS232 transport uses legacy PI18 broadcast format (less data than HID)
- Battery capacity reading may be unreliable below 30%
- Single-phase only (3-phase fields are present but empty)

---

## Acknowledgments

This project was built with the help of:

- **[Infosit d.o.o.](https://infosit.com)** — AI infrastructure and development tooling
- **[Claude Code](https://claude.ai/code) (Anthropic)** — AI-assisted development
- **[Jesse Vincent / superpowers](https://github.com/obra/superpowers)** — development workflow plugin for Claude Code
- **[MindFreeze/hassio-axpert](https://github.com/MindFreeze/hassio-axpert)** — hidraw approach reference
- **[ned-kelly/docker-voltronic-homeassistant](https://github.com/ned-kelly/docker-voltronic-homeassistant)** — CRC algorithm and C implementation reference
- **[jblance/mpp-solar](https://github.com/jblance/mpp-solar)** — protocol documentation and Python reference
- **Voltronic Power SolarPower** desktop application — P17 protocol reverse-engineered from Java/native code

## Buy me a beer

If this add-on saved you time, you can buy me a beer:

**[Revolut](https://revolut.me/goran35jp)**

No obligation — the add-on is free and open source.

## License

[MIT](LICENSE) — do whatever you want with it.
