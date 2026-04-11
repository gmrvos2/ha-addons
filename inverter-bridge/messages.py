"""
Inverter Bridge — centralized message strings.

All user-facing log messages are defined here.
Prefix ⚡ identifies messages originating from this application.

Version is read from config.yaml (single source of truth).
"""
import os as _os
import json as _json

# Prefix for all app messages
P = "⚡"

# Version — read from config.yaml at import time
_config_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "config.yaml")
VERSION = "unknown"
try:
    with open(_config_path) as _f:
        for _line in _f:
            if _line.strip().startswith("version:"):
                VERSION = _line.split(":", 1)[1].strip().strip('"').strip("'")
                break
except FileNotFoundError:
    pass

# --- Startup / Shutdown ---
STARTUP              = f"{P} Inverter Bridge v{VERSION} | transport={{transport}} | MQTT={{host}}:{{port}}"
SHUTDOWN             = f"{P} Inverter Bridge stopped"
SIGNAL_RECEIVED      = f"{P} Signal received — shutting down..."

# --- Transport: auto-detect ---
AUTODETECT_HID       = f"{P} Auto-detect: found HID device {{device}}"
AUTODETECT_SERIAL    = f"{P} Auto-detect: found serial device {{device}}"
AUTODETECT_NONE      = f"{P} Auto-detect: no HID or serial device found"

# --- Transport: HID ---
HID_OPENED           = f"{P} USB HID opened: {{device}} (fd={{fd}}, O_NONBLOCK)"
HID_TX               = f"{P} TX [{{cmd}}]: {{packet}}"
HID_RX_RAW           = f"{P} RX raw [{{cmd}}]: {{data}}"
HID_RX_PAYLOAD       = f"{P} RX [{{cmd}}]: {{payload}}"
HID_NO_RESPONSE      = f"{P} HID [{{cmd}}]: no response | raw={{data}}"
HID_GS_NO_DATA       = f"{P} HID: GS command returned no data"

# --- Transport: Serial ---
SERIAL_OPENED        = f"{P} Serial opened: {{port}} @ {{baud}} baud (DTR=True RTS=True)"
SERIAL_WAKEUP_TX     = f"{P} Wake-up TX: {{cmd}}"
SERIAL_WAKEUP_NAK    = f"{P} Wake-up NAK ignored: {{packet}}"
SERIAL_BROADCAST     = f"{P} Broadcast: {{count}} packets | {{total_bytes}} bytes | raw[:80]: {{raw}}"
SERIAL_NO_DATA       = f"{P} No valid data in broadcast"

# --- Transport: open/close errors ---
TRANSPORT_OPEN_ERROR = f"{P} Cannot open transport: {{error}} — waiting 15s"
TRANSPORT_ERROR      = f"{P} Transport error: {{error}}"
TRANSPORT_RECONNECT  = f"{P} 3 consecutive errors — closing connection, will retry"
GENERAL_ERROR        = f"{P} Error: {{error}}"

# --- MQTT ---
MQTT_CONNECTED       = f"{P} MQTT connected to {{host}}:{{port}}"
MQTT_CONN_ERROR      = f"{P} MQTT rc={{rc}} ({{reason}})"
MQTT_DISCONNECTED    = f"{P} MQTT disconnected rc={{rc}}"
MQTT_CONNECT_RETRY   = f"{P} MQTT connect: {{error}} — retry 10s"
MQTT_BAD_CREDENTIALS = "bad credentials"
MQTT_ERROR           = "error"

# --- Discovery ---
DISCOVERY_PUBLISHED  = f"{P} Auto-discovery: {{sensors}} sensors + {{binary}} binary + mode"

# --- Polling ---
POLL_STATUS          = f"{P} PV={{pv}}V  Bat={{bat}}V  Load={{load}}%  AC={{ac}}V  Mode={{mode}}"

# --- Parsing: P17 ---
P17_GS_FIELDS        = f"{P} P17 GS: {{count}} fields: {{data}}"
P17_GS_TOO_FEW       = f"{P} P17 GS: too few fields ({{count}})"
P17_PS_FIELDS        = f"{P} P17 PS: {{count}} fields: {{data}}"

# --- Parsing: PI30/PI18 (legacy serial) ---
PI30_QPIGS_SHORT     = f"{P} Short PI30 QPIGS ({{count}} fields): {{data}}"
PI30_QPIGS_ERROR     = f"{P} Parse PI30 QPIGS: {{error}} | {{data}}"
PI18_QPIGS_FIELDS    = f"{P} PI18 QPIGS fields ({{count}}): {{data}}"
PI18_QPIGS_SHORT     = f"{P} Short PI18 QPIGS ({{count}} fields): {{data}}"
QPIGS_EMPTY          = f"{P} QPIGS: empty response"
