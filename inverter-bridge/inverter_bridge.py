#!/usr/bin/env python3
"""
Inverter Bridge — Voltronic SolarPower → MQTT
Version: see config.yaml (single source of truth)
Podržava dva transporta (odabir via TRANSPORT env):
  - hid    : USB HID /dev/hidraw0 (VID=0665 PID=5161) — P18 protokol
  - serial : RS232 via USB-serial adapter /dev/ttyUSB0 — P18 protokol

P18 HID (reverse-engineered iz SolarPower Java app):
  - Komanda: ^P<len(cmd)+1:03d><cmd>\r  (BEZ CRC!)
  - Odgovor: ^D<len:03d><podaci><CRC(2B)>\r
  - Komande: GS (status), MOD (mode), PIRI (rating), PI (protocol ID)

P18 RS232:
  - Komanda: ^P<len:03d><cmd><CRC16/XMODEM(2B)>\r
  - Odgovor: ^D<len:03d><podaci><CRC(2B)>\r
"""
import os
import sys
import json
import time
import fcntl
import signal
import logging
import serial
import paho.mqtt.client as mqtt
import messages as msg

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
def _str_env(var: str, default: str = "") -> str:
    v = os.environ.get(var, default)
    return default if not v or v.lower() in ("null", "none") else v

MQTT_HOST     = _str_env("MQTT_HOST",    "core-mosquitto")
MQTT_PORT     = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USER     = _str_env("MQTT_USER")
MQTT_PASSWORD = _str_env("MQTT_PASSWORD")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "30"))
TRANSPORT     = _str_env("TRANSPORT",    "auto").lower()
HID_DEVICE    = _str_env("HID_DEVICE",   "/dev/hidraw0")
SERIAL_PORT   = _str_env("SERIAL_PORT",  "/dev/ttyUSB0")
SERIAL_BAUD   = int(os.environ.get("SERIAL_BAUD", "2400"))
DEVICE_NAME   = _str_env("DEVICE_NAME",  "Solar Inverter")
LOG_LEVEL     = _str_env("LOG_LEVEL",    "info").upper()

DEVICE_ID    = "solar_inverter_01"
STATE_TOPIC  = "solar_inverter/state"
AVAIL_TOPIC  = "solar_inverter/availability"
DISCO_PREFIX = "homeassistant"

# ---------------------------------------------------------------------------
# Domain constants — named values instead of magic numbers
# (infosit.standards: Code-Review-Guidelines 4.4)
# ---------------------------------------------------------------------------
MIN_VALID_BATTERY_VOLTAGE = 30.0     # V — below this, battery is disconnected/dead
MIN_VALID_BATTERY_CAPACITY = 30      # % — below this, reading is unreliable
MIN_GRID_VOLTAGE_THRESHOLD = 50.0    # V — above this, grid is present
MIN_PV_VOLTAGE_THRESHOLD = 5.0       # V — above this, PV panels are producing
MIN_AC_FREQUENCY = 40.0              # Hz — lower bound for valid AC frequency
MAX_AC_FREQUENCY = 65.0              # Hz — upper bound for valid AC frequency
MIN_AC_VOLTAGE_THRESHOLD = 50.0      # V — above this, AC output is valid
P17_GS_MIN_FIELDS = 20               # minimum fields in P17 GS response
HID_DRAIN_ITERATIONS = 50            # max iterations to drain HID buffer
HID_READ_BUFFER = 100                # bytes per HID read
HID_EXTRA_READ_BUFFER = 200          # bytes for extra read after response detected
HID_POLL_SLEEP = 0.01                # seconds between HID poll attempts
HID_EXTRA_READ_DELAY = 0.1           # seconds before extra read
SERIAL_TIMEOUT = 2                   # seconds for serial port timeout
SERIAL_WRITE_TIMEOUT = 2             # seconds for serial write timeout
MQTT_KEEPALIVE = 60                  # seconds for MQTT keepalive
MQTT_RETRY_DELAY = 10                # seconds before MQTT reconnect
TRANSPORT_OPEN_RETRY_DELAY = 15      # seconds before transport reopen
TRANSPORT_RECONNECT_DELAY = 5        # seconds before reconnect after errors
MAX_CONSECUTIVE_ERRORS = 3           # errors before closing connection

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PI30 CRC-16/XMODEM
# ---------------------------------------------------------------------------
def _crc16(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = (crc << 1) ^ 0x1021 if crc & 0x8000 else crc << 1
        crc &= 0xFFFF
    return crc

def _crc_bytes(data: bytes) -> bytes:
    crc = _crc16(data)
    hi, lo = (crc >> 8) & 0xFF, crc & 0xFF
    if hi in (0x0A, 0x0D, 0x28): hi += 1
    if lo in (0x0A, 0x0D, 0x28): lo += 1
    return bytes([hi, lo])

def build_command(cmd: str) -> bytes:
    """PI30 komanda (za HID transport)"""
    raw = cmd.encode("ascii")
    return raw + _crc_bytes(raw) + b"\r"

def build_pi18_command(cmd: str) -> bytes:
    """PI18 komanda za RS232 — ^P<nnn><cmd><CRC>\r (s CRC)"""
    raw = f"^P{len(cmd):03d}{cmd}".encode("ascii")
    crc = _crc16(raw)
    return raw + bytes([crc >> 8, crc & 0xFF]) + b"\r"

def build_p18_hid_command(cmd: str) -> bytes:
    """P18 komanda za HID — ^P<len+1:03d><cmd>\r (BEZ CRC!)
    Reverse-engineered iz SolarPower Java app (SECFormat.addPollHeader).
    """
    length = len(cmd) + 1
    return f"^P{length:03d}{cmd}\r".encode("ascii")

# ---------------------------------------------------------------------------
# USB HID komunikacija — P18 protokol bez CRC
#
# Reverse-engineered iz SolarPower Java/native koda (2026-04-11):
#   - Java: SECFormat.addPollHeader(cmd) → "^P<len+1><cmd>"
#   - Native: dodaje \r, šalje via USB control transfer (SET_REPORT)
#   - CRC je ISKLJUČEN po defaultu (isUseCRC = false)
#   - hidraw: os.open + O_NONBLOCK, os.write/os.read
# ---------------------------------------------------------------------------
HID_PACKET_SIZE = 8

def open_hid() -> int:
    fd = os.open(HID_DEVICE, os.O_RDWR | os.O_NONBLOCK)
    fl = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)
    log.info(msg.HID_OPENED.format(device=HID_DEVICE, fd=fd))
    return fd

def _hid_drain(fd) -> None:
    for _ in range(HID_DRAIN_ITERATIONS):
        try:
            os.read(fd, HID_READ_BUFFER)
        except (BlockingIOError, OSError):
            break

def _query_hid_p18(fd: int, cmd: str, timeout: float = 5.0) -> str:
    """Šalje P18 komandu preko HID i čita ^D odgovor."""
    packet = build_p18_hid_command(cmd)
    log.debug(msg.HID_TX.format(cmd=cmd, packet=repr(packet)))

    _hid_drain(fd)

    for i in range(0, len(packet), HID_PACKET_SIZE):
        chunk = packet[i:i + HID_PACKET_SIZE]
        padded = chunk + b"\x00" * (HID_PACKET_SIZE - len(chunk))
        os.write(fd, padded)

    buf = b""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            chunk = os.read(fd, HID_READ_BUFFER)
            if chunk:
                buf += chunk
                if b"\r" in buf:
                    for part in buf.split(b"\r"):
                        c = part.rstrip(b"\x00")
                        if c and not c.startswith(b"^0"):
                            time.sleep(HID_EXTRA_READ_DELAY)
                            try:
                                buf += os.read(fd, HID_EXTRA_READ_BUFFER)
                            except (BlockingIOError, OSError):
                                pass
                            deadline = 0
                            break
                    else:
                        break
        except BlockingIOError:
            time.sleep(HID_POLL_SLEEP)
        except OSError:
            time.sleep(HID_POLL_SLEEP)

    log.debug(msg.HID_RX_RAW.format(cmd=cmd, data=buf[:80].hex()))

    for part in buf.split(b"\r"):
        c = part.rstrip(b"\x00")
        if c.startswith(b"^D") and len(c) >= 7:
            payload = c[5:-2].decode("ascii", errors="ignore")
            log.debug(msg.HID_RX_PAYLOAD.format(cmd=cmd, payload=repr(payload)))
            return payload
        elif c.startswith(b"^1"):
            return "(ACK"
        elif c.startswith(b"^0"):
            continue

    log.warning(msg.HID_NO_RESPONSE.format(cmd=cmd, data=repr(buf[:40])))
    return ""

# ---------------------------------------------------------------------------
# Serijska komunikacija
# ---------------------------------------------------------------------------
def open_serial() -> serial.Serial:
    ser = serial.Serial(
        port=SERIAL_PORT,
        baudrate=SERIAL_BAUD,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=SERIAL_TIMEOUT,
        write_timeout=SERIAL_WRITE_TIMEOUT,
        dsrdtr=False,
        rtscts=False,
    )
    ser.dtr = True
    ser.rts = True
    log.info(msg.SERIAL_OPENED.format(port=SERIAL_PORT, baud=SERIAL_BAUD))
    return ser

def _fval(fields: list, idx: int, scale: float = 0.1, default: float = 0.0) -> float:
    try:
        v = fields[idx].strip() if idx < len(fields) else ""
        return round(float(v) * scale, 2) if v else default
    except (ValueError, IndexError):
        return default

def _ival(fields: list, idx: int, default: int = 0) -> int:
    try:
        v = fields[idx].strip() if idx < len(fields) else ""
        return int(v) if v else default
    except (ValueError, IndexError):
        return default

def _read_serial_broadcast(ser: serial.Serial, timeout: float = 5.0) -> list:
    """Šalje PI18 QPIGS query i čita odgovor (^D<len><data><CRC>\r).
    ^D061/^D086 nisu autonomni broadcast — to su query-response paketi.
    Vraća listu raw ^D paketa (bytes, bez terminatora \\r).
    """
    wake_cmd = build_pi18_command("QPIGS")
    ser.reset_input_buffer()
    ser.write(wake_cmd)
    log.debug(msg.SERIAL_WAKEUP_TX.format(cmd=repr(wake_cmd)))

    buf = b""
    raw_all = b""
    packets = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        chunk = ser.read(ser.in_waiting or 1)
        if chunk:
            buf += chunk
            raw_all += chunk
            while b"\r" in buf:
                pkt, buf = buf.split(b"\r", 1)
                if pkt.startswith(b"^D") and len(pkt) >= 6:
                    packets.append(pkt)
                elif pkt.startswith(b"^0"):
                    log.debug(msg.SERIAL_WAKEUP_NAK.format(packet=repr(pkt)))
    log.debug(msg.SERIAL_BROADCAST.format(count=len(packets), total_bytes=len(raw_all), raw=repr(raw_all[:80])))
    return packets

def _parse_serial_packets(packets: list) -> dict:
    """Parsira broadcast pakete i vraća dict s vrijednostima senzora.

    Potvrđeni paketi za ovaj Voltronic model:
      ^D086  Extended status: baterija(f[4]), AC izlaz(f[7]), AC freq(f[10])
      ^D061  General status:  AC ulaz(f[0,1]), PV(f[14/11]), load%(f[15])
    Sve numeričke vrijednosti ×0.1 osim integera.
    """
    data: dict = {
        "grid_voltage":              0.0,
        "grid_frequency":            0.0,
        "ac_output_voltage":         0.0,
        "ac_output_frequency":       0.0,
        "ac_output_apparent_power":  0,
        "ac_output_active_power":    0,
        "output_load_percent":       0,
        "bus_voltage":               0,
        "battery_voltage":           0.0,
        "battery_charging_current":  0,
        "battery_capacity":          0,
        "inverter_heat_sink_temp":   0,
        "pv_input_current":          0.0,
        "pv_input_voltage":          0.0,
        "pv_input_power":            0.0,
        "battery_voltage_scc":       0.0,
        "battery_discharge_current": 0,
        "load_on":     1,
        "charging_on": 0,
        "scc_charging": 0,
        "ac_charging":  0,
    }

    has_data = False
    for pkt in packets:
        if len(pkt) < 6:
            continue
        raw_len = pkt[2:5].decode("ascii", errors="ignore")
        # Payload = sve između ^DXXX prefixea i zadnja 2 bajta CRC-a
        payload = pkt[5:-2].decode("ascii", errors="ignore")

        if raw_len == "086" and "+" in payload:
            # ^D086 — extended status
            # Potvrđena polja: f[4]=bat_V, f[7]=AC_out_V, f[10]=AC_out_Hz
            f = payload.split(",")
            bat_v = _fval(f, 4)
            ac_v  = _fval(f, 7)
            ac_f  = _fval(f, 10)
            if bat_v > MIN_VALID_BATTERY_VOLTAGE:
                data["battery_voltage"] = bat_v
                has_data = True
            if ac_v > MIN_AC_VOLTAGE_THRESHOLD:
                data["ac_output_voltage"] = ac_v
            if MIN_AC_FREQUENCY < ac_f < MAX_AC_FREQUENCY:
                data["ac_output_frequency"] = ac_f

        elif raw_len == "061":
            # ^D061 — general/QPIGS status
            # f[0]=grid_V, f[1]=grid_Hz, f[14/11]=PV_V, f[15]=load%
            f = payload.split(",")
            if len(f) >= 16:
                data["grid_voltage"]   = _fval(f, 0)
                data["grid_frequency"] = _fval(f, 1)
                # PV napon: 5-znamenkasto polje preferirano, fallback na 4-znamenkasto
                pv_v = _fval(f, 14) or _fval(f, 11)
                if pv_v > 1.0:
                    data["pv_input_voltage"] = pv_v
                # SCC/MPPT napon
                scc_v = _fval(f, 10) or _fval(f, 7)
                if scc_v > 10.0:
                    data["battery_voltage_scc"] = scc_v
                data["output_load_percent"] = _ival(f, 15)
                has_data = True

    if not has_data:
        return {}

    data["pv_input_power"] = round(data["pv_input_voltage"] * data["pv_input_current"], 1)
    data["scc_charging"]   = 1 if data["pv_input_voltage"] > 5.0 else 0
    data["charging_on"]    = data["scc_charging"]
    data["ac_charging"]    = 1 if data["grid_voltage"] > 50.0 else 0
    return data

# ---------------------------------------------------------------------------
# Auto-detect i unificirani transport
# ---------------------------------------------------------------------------
import glob as _glob

_active_transport = None  # "hid" ili "serial" — postavlja se pri open_transport

def _detect_transport() -> str:
    """Auto-detect: provjeri koji uređaj je spojen. HID ima prioritet."""
    if TRANSPORT not in ("auto", ""):
        return TRANSPORT

    if os.path.exists(HID_DEVICE):
        log.info(msg.AUTODETECT_HID.format(device=HID_DEVICE))
        return "hid"

    serial_devs = _glob.glob("/dev/ttyUSB*")
    if serial_devs:
        log.info(msg.AUTODETECT_SERIAL.format(device=serial_devs[0]))
        return "serial"

    log.warning(msg.AUTODETECT_NONE)
    return "hid"  # default, open_hid će baciti grešku pa retry

def open_transport():
    global _active_transport
    _active_transport = _detect_transport()
    if _active_transport == "hid":
        return open_hid()
    return open_serial()

def close_transport(conn) -> None:
    try:
        if isinstance(conn, int):
            os.close(conn)
        else:
            conn.close()
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Parsiranje QPIGS
# ---------------------------------------------------------------------------

def _parse_pi30_qpigs(response: str) -> dict:
    """PI30 format: '(' + space-separated fields + CRC"""
    parts = response[1:].split()
    if len(parts) < 16:
        log.warning(msg.PI30_QPIGS_SHORT.format(count=len(parts), data=repr(response)))
        return {}
    try:
        status = parts[16] if len(parts) > 16 else "00000000"
        d = {
            "grid_voltage":               float(parts[0]),
            "grid_frequency":             float(parts[1]),
            "ac_output_voltage":          float(parts[2]),
            "ac_output_frequency":        float(parts[3]),
            "ac_output_apparent_power":   int(parts[4]),
            "ac_output_active_power":     int(parts[5]),
            "output_load_percent":        int(parts[6]),
            "bus_voltage":                int(parts[7]),
            "battery_voltage":            float(parts[8]),
            "battery_charging_current":   int(parts[9]),
            "battery_capacity":           int(parts[10]),
            "inverter_heat_sink_temp":    int(parts[11]),
            "pv_input_current":           float(parts[12]),
            "pv_input_voltage":           float(parts[13]),
            "battery_voltage_scc":        float(parts[14]),
            "battery_discharge_current":  int(parts[15]),
            "load_on":      int(status[4]) if len(status) > 4 else 0,
            "charging_on":  int(status[5]) if len(status) > 5 else 0,
            "scc_charging": int(status[6]) if len(status) > 6 else 0,
            "ac_charging":  int(status[7]) if len(status) > 7 else 0,
        }
        d["pv_input_power"] = round(d["pv_input_voltage"] * d["pv_input_current"], 1)
        return d
    except (ValueError, IndexError) as e:
        log.error(msg.PI30_QPIGS_ERROR.format(error=e, data=repr(response)))
        return {}


def _parse_pi18_qpigs(response: str) -> dict:
    """PI18 format: comma-separated fields.
    Potvrđeni raspored za ovaj Voltronic model:
      f[0]  AC ulazni napon  (×0.1 V)
      f[1]  AC ulazna freq   (×0.1 Hz)
      f[7]  napon baterije   (×0.1 V, 4 znamenke)
      f[10] napon baterije   (×0.1 V, 5 znamenki — preferira se)
      f[11] PV ulazni napon  (×0.1 V, 4 znamenke)
      f[14] PV ulazni napon  (×0.1 V, 5 znamenki — preferira se)
      f[15] opterećenje      (%)
      f[16..22] status bitovi
    """
    f = response.split(",")
    log.debug(msg.PI18_QPIGS_FIELDS.format(count=len(f), data=f))
    if len(f) < 16:
        log.warning(msg.PI18_QPIGS_SHORT.format(count=len(f), data=repr(response)))
        return {}

    def fv(idx, scale=0.1, default=0.0):
        try:
            v = f[idx].strip()
            return round(float(v) * scale, 2) if v else default
        except (ValueError, IndexError):
            return default

    def iv(idx, default=0):
        try:
            v = f[idx].strip()
            return int(v) if v else default
        except (ValueError, IndexError):
            return default

    grid_v    = fv(0)
    grid_f    = fv(1)
    bat_v     = fv(10) if f[10].strip() else fv(7)   # 5-znamenkasti preferiran
    pv_v      = fv(14) if f[14].strip() else fv(11)  # 5-znamenkasti preferiran
    load_pct  = iv(15)

    scc_on    = 1 if pv_v > 5.0 else 0
    ac_on     = 1 if grid_v > 50.0 else 0

    d = {
        "grid_voltage":               grid_v,
        "grid_frequency":             grid_f,
        "ac_output_voltage":          0.0,
        "ac_output_frequency":        0.0,
        "ac_output_apparent_power":   0,
        "ac_output_active_power":     0,
        "output_load_percent":        load_pct,
        "bus_voltage":                0,
        "battery_voltage":            bat_v,
        "battery_charging_current":   0,
        "battery_capacity":           0,
        "inverter_heat_sink_temp":    0,
        "pv_input_current":           0.0,
        "pv_input_voltage":           pv_v,
        "battery_voltage_scc":        bat_v,
        "battery_discharge_current":  0,
        "pv_input_power":             0.0,
        "load_on":     1,
        "charging_on": scc_on,
        "scc_charging": scc_on,
        "ac_charging":  ac_on,
    }
    return d


def parse_qpigs(response: str) -> dict:
    if not response:
        log.warning(msg.QPIGS_EMPTY)
        return {}
    if response.startswith("("):
        return _parse_pi30_qpigs(response)
    return _parse_pi18_qpigs(response)


MODE_MAP = {
    "P": "Power On", "S": "Standby", "L": "Line",
    "B": "Battery",  "F": "Fault",   "H": "Power Saving",
    "D": "Shutdown", "C": "Charge",
}

def parse_qmod(response: str) -> str:
    """PI30: '(X', PI18: ^D00XY (Y = mode char u zadnjem bajtu)"""
    if response.startswith("(") and len(response) >= 2:
        return MODE_MAP.get(response[1], f"Unknown({response[1]})")
    if len(response) == 1:
        return MODE_MAP.get(response, f"Unknown({response})")
    return "Unknown"

# ---------------------------------------------------------------------------
# MQTT auto-discovery
# ---------------------------------------------------------------------------
def _device_model() -> str:
    t = _active_transport or TRANSPORT
    return "P17 USB HID" if t == "hid" else "P17 RS232"

DEVICE_INFO = {
    "identifiers": [DEVICE_ID],
    "name": DEVICE_NAME,
    "manufacturer": "Voltronic Power",
    "model": "P17 Auto-detect",
}

SENSORS = [
    ("grid_voltage",              "Grid Voltage",              "V",   "voltage",        "measurement", None),
    ("grid_frequency",            "Grid Frequency",            "Hz",  "frequency",      "measurement", None),
    ("ac_output_voltage",         "AC Output Voltage",         "V",   "voltage",        "measurement", None),
    ("ac_output_frequency",       "AC Output Frequency",       "Hz",  "frequency",      "measurement", None),
    ("ac_output_apparent_power",  "AC Output Apparent Power",  "VA",  "apparent_power", "measurement", None),
    ("ac_output_active_power",    "AC Output Active Power",    "W",   "power",          "measurement", None),
    ("output_load_percent",       "Output Load",               "%",   None,             "measurement", "mdi:gauge"),
    ("bus_voltage",               "Bus Voltage",               "V",   "voltage",        "measurement", None),
    ("battery_voltage",           "Battery Voltage",           "V",   "voltage",        "measurement", None),
    ("battery_charging_current",  "Battery Charging Current",  "A",   "current",        "measurement", None),
    ("battery_capacity",          "Battery Capacity",          "%",   "battery",        "measurement", None),
    ("inverter_heat_sink_temp",   "Inverter Temperature",      "°C",  "temperature",    "measurement", None),
    ("pv_input_current",          "PV Input Current",          "A",   "current",        "measurement", None),
    ("pv_input_voltage",          "PV Input Voltage",          "V",   "voltage",        "measurement", None),
    ("pv_input_power",            "PV Input Power",            "W",   "power",          "measurement", "mdi:solar-power"),
    ("battery_discharge_current", "Battery Discharge Current", "A",   "current",        "measurement", None),
    ("battery_voltage_scc",       "Battery Voltage (SCC)",     "V",   "voltage",        "measurement", None),
]

BINARY_SENSORS = [
    ("load_on",      "Load",        "mdi:power-plug"),
    ("charging_on",  "Charging",    "mdi:battery-charging"),
    ("scc_charging", "SCC Charging","mdi:solar-power"),
    ("ac_charging",  "AC Charging", "mdi:transmission-tower"),
]

def publish_discovery(client: mqtt.Client) -> None:
    for key, name, unit, dev_class, state_class, icon in SENSORS:
        p = {
            "name": name, "unique_id": f"{DEVICE_ID}_{key}",
            "state_topic": STATE_TOPIC,
            "value_template": f"{{{{ value_json.{key} }}}}",
            "unit_of_measurement": unit,
            "availability_topic": AVAIL_TOPIC,
            "device": DEVICE_INFO,
        }
        if dev_class:   p["device_class"]  = dev_class
        if state_class: p["state_class"]   = state_class
        if icon:        p["icon"]          = icon
        client.publish(f"{DISCO_PREFIX}/sensor/{DEVICE_ID}/{key}/config", json.dumps(p), retain=True)

    for key, name, icon in BINARY_SENSORS:
        p = {
            "name": name, "unique_id": f"{DEVICE_ID}_{key}",
            "state_topic": STATE_TOPIC,
            "value_template": f"{{{{ value_json.{key} }}}}",
            "payload_on": 1, "payload_off": 0,
            "availability_topic": AVAIL_TOPIC,
            "icon": icon, "device": DEVICE_INFO,
        }
        client.publish(f"{DISCO_PREFIX}/binary_sensor/{DEVICE_ID}/{key}/config", json.dumps(p), retain=True)

    client.publish(
        f"{DISCO_PREFIX}/sensor/{DEVICE_ID}/mode/config",
        json.dumps({
            "name": "Inverter Mode", "unique_id": f"{DEVICE_ID}_mode",
            "state_topic": STATE_TOPIC,
            "value_template": "{{ value_json.mode }}",
            "availability_topic": AVAIL_TOPIC,
            "icon": "mdi:solar-power-variant", "device": DEVICE_INFO,
        }), retain=True
    )
    log.info(msg.DISCOVERY_PUBLISHED.format(sensors=len(SENSORS), binary=len(BINARY_SENSORS)))

# ---------------------------------------------------------------------------
# MQTT
# ---------------------------------------------------------------------------
def connect_mqtt() -> mqtt.Client:
    client = mqtt.Client(client_id=DEVICE_ID)
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    client.will_set(AVAIL_TOPIC, "offline", retain=True)

    def on_connect(c, _ud, _flags, rc):
        if rc == 0:
            log.info(msg.MQTT_CONNECTED.format(host=MQTT_HOST, port=MQTT_PORT))
            c.publish(AVAIL_TOPIC, "online", retain=True)
            publish_discovery(c)
        else:
            log.error(msg.MQTT_CONN_ERROR.format(rc=rc, reason=msg.MQTT_BAD_CREDENTIALS if rc==5 else msg.MQTT_ERROR))

    client.on_connect    = on_connect
    client.on_disconnect = lambda c, _ud, rc: log.warning(msg.MQTT_DISCONNECTED.format(rc=rc))

    while running:
        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=MQTT_KEEPALIVE)
            client.loop_start()
            return client
        except Exception as e:
            log.error(msg.MQTT_CONNECT_RETRY.format(error=e))
            time.sleep(MQTT_RETRY_DELAY)

    sys.exit(0)

# ---------------------------------------------------------------------------
# Glavni loop
# ---------------------------------------------------------------------------
running = True

def _on_signal(_sig, _frame):
    global running
    log.info(msg.SIGNAL_RECEIVED)
    running = False

signal.signal(signal.SIGTERM, _on_signal)
signal.signal(signal.SIGINT,  _on_signal)


P18_MODE_MAP = {
    "01": "Power On", "02": "Standby", "03": "Bypass",
    "04": "Battery", "05": "Line", "06": "Fault",
    "07": "Power Saving", "08": "Charge",
}

def _parse_p17_gs(gs_response: str) -> dict:
    """Parsira P17 GS (General Status) — reverse-engineered iz P17ComUSBProcessor.

    Protocol ID=17 field mapping (verified on Voltronic SolarPower hybrid inverter):
      f[0]  PV input voltage 1     (÷10 V)
      f[1]  PV input voltage 2     (÷10 V)
      f[2]  PV input current 1     (÷10 A)
      f[3]  PV input current 2     (÷10 A)
      f[4]  battery voltage         (÷10 V)
      f[5]  battery capacity        (int %)
      f[6]  charging current        (+NNNNN ÷10 A, signed)
      f[7]  grid voltage R          (÷10 V)
      f[8]  grid voltage S          (÷10 V, empty za 1-fazni)
      f[9]  grid voltage T          (÷10 V, empty za 1-fazni)
      f[10] grid frequency          (÷100 Hz)
      f[11] grid current R          (÷10 A)
      f[14] AC output voltage R     (÷10 V)
      f[17] AC output frequency     (÷100 Hz)
      f[18] AC output current R     (÷10 A)
      f[21] inner temperature       (int °C)
      f[22] max temperature         (int °C)
      f[23] ext battery temperature (int °C)
      f[24] setting change bit
    """
    f = gs_response.split(",")
    log.debug(msg.P17_GS_FIELDS.format(count=len(f), data=gs_response[:120]))
    if len(f) < P17_GS_MIN_FIELDS:
        log.warning(msg.P17_GS_TOO_FEW.format(count=len(f)))
        return {}

    def fv(idx, scale=0.1, default=0.0):
        try:
            v = f[idx].strip() if idx < len(f) else ""
            return round(float(v) * scale, 2) if v else default
        except (ValueError, IndexError):
            return default

    def iv(idx, default=0):
        try:
            v = f[idx].strip() if idx < len(f) else ""
            return int(v) if v else default
        except (ValueError, IndexError):
            return default

    pv_v1 = fv(0)
    pv_v2 = fv(1)
    pv_v = max(pv_v1, pv_v2)
    bat_v = fv(4)
    if bat_v < MIN_VALID_BATTERY_VOLTAGE:
        bat_v = 0.0
    bat_cap = iv(5)
    if bat_cap < MIN_VALID_BATTERY_CAPACITY:
        bat_cap = 0
    grid_v = fv(7)
    grid_f = fv(10, scale=0.01)
    ac_out_v = fv(14)
    ac_out_f = fv(17, scale=0.01)

    # Charging current: signed format "+NNNNN" or "-NNNNN"
    charge_str = f[6].strip() if len(f) > 6 else ""
    charge_a = 0.0
    if charge_str and len(charge_str) > 1:
        try:
            val = float(charge_str[1:]) * 0.1
            charge_a = val if charge_str[0] == "+" else -val
        except ValueError:
            pass

    scc_on = 1 if pv_v > MIN_PV_VOLTAGE_THRESHOLD else 0
    ac_on = 1 if grid_v > MIN_GRID_VOLTAGE_THRESHOLD else 0

    d = {
        "grid_voltage":               grid_v,
        "grid_frequency":             grid_f,
        "ac_output_voltage":          ac_out_v,
        "ac_output_frequency":        ac_out_f,
        "ac_output_apparent_power":   0,
        "ac_output_active_power":     0,
        "output_load_percent":        0,
        "bus_voltage":                0,
        "battery_voltage":            bat_v,
        "battery_charging_current":   max(0, int(charge_a)),
        "battery_capacity":           bat_cap,
        "inverter_heat_sink_temp":    iv(21),
        "pv_input_current":           fv(2),
        "pv_input_voltage":           pv_v,
        "pv_input_power":             0.0,
        "battery_voltage_scc":        bat_v,
        "battery_discharge_current":  max(0, int(-charge_a)) if charge_a < 0 else 0,
        "load_on":     1,
        "charging_on": 1 if charge_a > 0 else 0,
        "scc_charging": scc_on,
        "ac_charging":  ac_on,
    }
    return d


def _parse_p17_ps(ps_response: str, data: dict) -> None:
    """Parsira P17 PS (Power Status) — reverse-engineered iz P17ComUSBProcessor.
    f[0]=pvPower1 (W), f[1]=pvPower2 (W), f[7]=activePowerR (W),
    f[15]=loadPercent (%), f[16]=hasLoad
    """
    f = ps_response.split(",")
    log.debug(msg.P17_PS_FIELDS.format(count=len(f), data=ps_response[:80]))

    def iv(idx, default=0):
        try:
            v = f[idx].strip() if idx < len(f) else ""
            return int(v) if v else default
        except (ValueError, IndexError):
            return default

    pv_power1 = iv(0)
    pv_power2 = iv(1)
    data["pv_input_power"] = pv_power1 + pv_power2
    if len(f) > 7:
        data["ac_output_active_power"] = iv(7)
    if len(f) > 15:
        data["output_load_percent"] = iv(15)
    if len(f) > 16:
        data["load_on"] = iv(16)


def _mode_from_data(data: dict) -> str:
    """Fallback: izračunaj mode iz dostupnih podataka."""
    if data.get("grid_voltage", 0) > MIN_GRID_VOLTAGE_THRESHOLD:
        return "Line"
    if data.get("pv_input_voltage", 0) > MIN_PV_VOLTAGE_THRESHOLD:
        return "Battery"
    return "Battery"


def poll_and_publish(conn, client: mqtt.Client) -> bool:
    if _active_transport == "hid":
        # HID P17: aktivni query — GS za status, PS za power, MOD za mode
        gs = _query_hid_p18(conn, "GS")
        data = _parse_p17_gs(gs)
        if not data:
            log.warning(msg.HID_GS_NO_DATA)
            return False

        ps = _query_hid_p18(conn, "PS", timeout=3.0)
        if ps:
            _parse_p17_ps(ps, data)

        mod = _query_hid_p18(conn, "MOD", timeout=3.0)
        data["mode"] = P18_MODE_MAP.get(mod.strip(), _mode_from_data(data))
    else:
        # Serial: pasivni broadcast (inverter šalje ^D086/^D061 svake ~3.5s)
        packets = _read_serial_broadcast(conn, timeout=5.0)
        data = _parse_serial_packets(packets)
        if not data:
            log.warning(msg.SERIAL_NO_DATA)
            return False
        data["mode"] = _mode_from_data(data)

    client.publish(STATE_TOPIC, json.dumps(data))
    log.info(msg.POLL_STATUS.format(
        pv=data.get('pv_input_voltage', '?'),
        bat=data.get('battery_voltage', '?'),
        load=data.get('output_load_percent', '?'),
        ac=data.get('ac_output_voltage', '?'),
        mode=data['mode'],
    ))
    return True


def _preflight_checks() -> bool:
    """Validate configuration before starting. Returns True if OK."""
    ok = True
    if not MQTT_HOST:
        log.error(msg.MQTT_HOST_EMPTY)
        log.error(msg.MQTT_NOT_CONFIGURED)
        ok = False

    if TRANSPORT == "auto":
        import glob as _g
        if not os.path.exists(HID_DEVICE) and not _g.glob("/dev/ttyUSB*"):
            log.error(msg.NO_TRANSPORT_FOUND)
            ok = False

    return ok


def main():
    log.info(msg.STARTUP.format(transport=TRANSPORT, host=MQTT_HOST, port=MQTT_PORT))

    if not _preflight_checks():
        log.error(msg.SHUTDOWN)
        sys.exit(1)

    client = connect_mqtt()
    conn   = None
    errors = 0

    while running:
        if conn is None:
            try:
                conn = open_transport()
                errors = 0
            except (OSError, serial.SerialException) as e:
                log.error(msg.TRANSPORT_OPEN_ERROR.format(error=e))
                time.sleep(TRANSPORT_OPEN_RETRY_DELAY)
                continue

        try:
            ok = poll_and_publish(conn, client)
        except (OSError, serial.SerialException) as e:
            log.error(msg.TRANSPORT_ERROR.format(error=e))
            ok = False
        except Exception as e:
            log.error(msg.GENERAL_ERROR.format(error=e), exc_info=True)
            ok = False

        if ok:
            errors = 0
            client.publish(AVAIL_TOPIC, "online", retain=True)
        else:
            errors += 1
            if errors >= MAX_CONSECUTIVE_ERRORS:
                log.warning(msg.TRANSPORT_RECONNECT)
                close_transport(conn)
                conn = None
                errors = 0
                client.publish(AVAIL_TOPIC, "offline", retain=True)
                time.sleep(TRANSPORT_RECONNECT_DELAY)
                continue

        for _ in range(POLL_INTERVAL):
            if not running: break
            time.sleep(1)

    if conn:
        close_transport(conn)
    client.publish(AVAIL_TOPIC, "offline", retain=True)
    client.loop_stop()
    client.disconnect()
    log.info(msg.SHUTDOWN)


if __name__ == "__main__":
    main()
