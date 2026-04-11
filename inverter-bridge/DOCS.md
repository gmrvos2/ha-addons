# Inverter Bridge — Documentation

## Prerequisites

Before starting this add-on, you need:

### 1. MQTT Broker (required)

This add-on publishes sensor data via MQTT. You need an MQTT broker running.

**Recommended:** Install the official **Mosquitto broker** add-on:

1. Go to **Settings** → **Add-ons** → **Add-on Store**
2. Search for **"Mosquitto broker"** and install it
3. Start the Mosquitto add-on
4. Go to **Settings** → **Devices & Services** → **MQTT** and configure the integration

> **Need MQTT credentials?** Go to **Settings** → **People** → **Users** → **Add User**.
> Create a dedicated user (e.g., `mqtt`) and use those credentials in this add-on's Configuration tab.

### 2. Inverter connected via USB (required)

Connect your Voltronic inverter to your Home Assistant machine using one of:

| Cable | Appears as | Notes |
|-------|-----------|-------|
| **USB HID** (came with inverter) | `/dev/hidraw0` | Recommended, auto-detected |
| **USB-to-RS232 adapter** | `/dev/ttyUSB0` | PL2303, CH340, FTDI adapters work |

> **Not sure if it's connected?** Check **Settings** → **System** → **Hardware** → **All Hardware** and look for `hidraw0` or `ttyUSB0`.

## Configuration

After installing, go to the **Configuration** tab and set:

| Option | What to enter |
|--------|--------------|
| **MQTT Host** | Keep `core-mosquitto` if using the Mosquitto add-on |
| **MQTT Username** | The username you created for MQTT |
| **MQTT Password** | The password for that user |
| **Transport** | Keep `auto` — it detects your cable type automatically |

All other options can stay at their defaults.

## After starting

Once the add-on starts successfully, you should see:

1. **Log tab** shows `⚡ Inverter Bridge v... | transport=... | MQTT=...`
2. **Sensors appear automatically** in **Settings** → **Devices & Services** → **MQTT** → **Solar Inverter**
3. **Energy Dashboard** — you can add PV Input Power as a solar production source

## Troubleshooting

### "MQTT authentication failed"
→ Set `mqtt_user` and `mqtt_password` in the Configuration tab. Use the same credentials as your MQTT broker.

### "No inverter found"
→ Check that your USB cable is plugged in. Look for `/dev/hidraw0` or `/dev/ttyUSB0` in **Settings** → **System** → **Hardware**.

### "HID: GS command returned no data"
→ Your inverter may use a different protocol. Open an issue on [GitHub](https://github.com/gmrvos2/ha-addons/issues) with your inverter model.

### Sensors show "unavailable"
→ Check the Log tab for errors. Most common cause: MQTT credentials not set.

## Supported inverters

This add-on works with **Voltronic Power** hybrid inverters (Protocol ID 17):

- Axpert (King, MKS, VM, MAX series)
- MPP Solar (PIP, LV, MPI series)
- SolarPower (hybrid series)
- Easun, Kodak, Effekta, Voltacon, and other Voltronic OEMs

> **Other protocols** (PI30, PI18, P16, P20) are not yet supported. If your inverter uses a different protocol, please open an issue — contributions welcome!
