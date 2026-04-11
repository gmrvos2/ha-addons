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

# Auto-detect serial port ako konfigurirani port ne postoji
# (dogodi se kad kernel prebroji USB uređaje drugačije nakon reconnecta)
if [ "${TRANSPORT}" = "serial" ] && [ ! -e "${SERIAL_PORT}" ]; then
    bashio::log.warning "Port ${SERIAL_PORT} ne postoji — tražim PL2303 adapter (067b:23a3)..."
    for sysdev in /sys/class/tty/ttyUSB*/; do
        vid=$(cat "${sysdev}device/../../idVendor" 2>/dev/null)
        pid=$(cat "${sysdev}device/../../idProduct" 2>/dev/null)
        if [ "${vid}" = "067b" ] && [ "${pid}" = "23a3" ]; then
            detected="/dev/$(basename "${sysdev%/}")"
            bashio::log.warning "Pronađen adapter na ${detected} — koristim umjesto ${SERIAL_PORT}"
            export SERIAL_PORT="${detected}"
            break
        fi
    done
fi

VERSION=$(grep '^version:' /app/config.yaml 2>/dev/null | sed 's/version: *"*//;s/"$//' || echo "unknown")
bashio::log.info "Starting Inverter Bridge v${VERSION}"
bashio::log.info "Transport: ${TRANSPORT} | HID: ${HID_DEVICE} | Serial: ${SERIAL_PORT}@${SERIAL_BAUD}"
bashio::log.info "MQTT: ${MQTT_HOST}:${MQTT_PORT} | Poll: ${POLL_INTERVAL}s"
bashio::log.info "UID: $(id)"
bashio::log.info "HID devices: $(ls -la /dev/hidraw* 2>&1)"
bashio::log.info "Serial devices: $(ls -la /dev/ttyUSB* 2>&1)"

exec python3 /app/inverter_bridge.py
