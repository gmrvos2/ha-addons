#!/usr/bin/with-contenv bashio

export MQTT_HOST=$(bashio::config 'mqtt_host')
export MQTT_PORT=$(bashio::config 'mqtt_port')
export MQTT_USER=$(bashio::config 'mqtt_user')
export MQTT_PASSWORD=$(bashio::config 'mqtt_password')
export POLL_INTERVAL=$(bashio::config 'poll_interval')
export SERIAL_PORT=$(bashio::config 'serial_port')
export SERIAL_BAUD=$(bashio::config 'serial_baud')
export DEVICE_NAME=$(bashio::config 'device_name')
export LOG_LEVEL=$(bashio::config 'log_level')

export TRANSPORT=$(bashio::config 'transport')
export HID_DEVICE=$(bashio::config 'hid_device' 2>/dev/null || echo "/dev/hidraw0")

VERSION=$(grep '^version:' /app/config.yaml 2>/dev/null | sed 's/version: *"*//;s/"$//' || echo "unknown")

# ---------------------------------------------------------------------------
# Preflight checks — help the user before Python even starts
# ---------------------------------------------------------------------------

# Check MQTT credentials
if [ -z "${MQTT_USER}" ] || [ "${MQTT_USER}" = "null" ]; then
    bashio::log.warning "------------------------------------------------------------"
    bashio::log.warning "⚡ MQTT username is not set!"
    bashio::log.warning ""
    bashio::log.warning "  Most MQTT brokers require authentication."
    bashio::log.warning "  Go to this add-on's Configuration tab and set:"
    bashio::log.warning "    - MQTT Username"
    bashio::log.warning "    - MQTT Password"
    bashio::log.warning ""
    bashio::log.warning "  If you use the Mosquitto add-on, create a user at:"
    bashio::log.warning "    Settings > People > Users > Add User"
    bashio::log.warning ""
    bashio::log.warning "  See the Documentation tab for full setup guide."
    bashio::log.warning "------------------------------------------------------------"
fi

# Check inverter USB connection
if [ ! -e "/dev/hidraw0" ] && ! ls /dev/ttyUSB* >/dev/null 2>&1; then
    bashio::log.warning "------------------------------------------------------------"
    bashio::log.warning "⚡ No inverter USB device found!"
    bashio::log.warning ""
    bashio::log.warning "  Make sure your Voltronic inverter is connected via USB:"
    bashio::log.warning "    - USB HID cable → appears as /dev/hidraw0"
    bashio::log.warning "    - USB-to-RS232 adapter → appears as /dev/ttyUSB0"
    bashio::log.warning ""
    bashio::log.warning "  Check: Settings > System > Hardware > All Hardware"
    bashio::log.warning "------------------------------------------------------------"
fi

# Auto-detect serial port if configured port doesn't exist
if [ "${TRANSPORT}" = "serial" ] && [ ! -e "${SERIAL_PORT}" ]; then
    bashio::log.warning "Port ${SERIAL_PORT} not found — scanning for PL2303 adapter (067b:23a3)..."
    for sysdev in /sys/class/tty/ttyUSB*/; do
        vid=$(cat "${sysdev}device/../../idVendor" 2>/dev/null)
        pid=$(cat "${sysdev}device/../../idProduct" 2>/dev/null)
        if [ "${vid}" = "067b" ] && [ "${pid}" = "23a3" ]; then
            detected="/dev/$(basename "${sysdev%/}")"
            bashio::log.warning "Found adapter at ${detected} — using instead of ${SERIAL_PORT}"
            export SERIAL_PORT="${detected}"
            break
        fi
    done
fi

# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------
bashio::log.info "⚡ Starting Inverter Bridge v${VERSION}"
bashio::log.info "⚡ Transport: ${TRANSPORT} | HID: ${HID_DEVICE} | Serial: ${SERIAL_PORT}@${SERIAL_BAUD}"
bashio::log.info "⚡ MQTT: ${MQTT_HOST}:${MQTT_PORT} | Poll: ${POLL_INTERVAL}s"
bashio::log.info "⚡ HID devices: $(ls -la /dev/hidraw* 2>&1)"
bashio::log.info "⚡ Serial devices: $(ls -la /dev/ttyUSB* 2>&1)"

exec python3 /app/inverter_bridge.py
