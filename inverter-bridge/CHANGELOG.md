## 3.1.0 (2026-04-11)
- feat: auto-detect transport — HID prioritized over RS232, no config change needed
- feat: externalized all log messages to `messages.py` with ⚡ prefix (infosit.standards compliance)
- feat: all messages in English
- feat: 20+ magic numbers replaced with named domain constants (infosit.standards: Code-Review-Guidelines 4.4)
- feat: 28 unit tests for P17 GS/PS parsers, CRC, command builders (Given-When-Then format)
- docs: Dockerfile documents root requirement with mitigations (Security-Baseline-Checklist)
- docs: global CLAUDE.md references infosit.standards repo for all future projects

## 3.0.0 (2026-04-11)
- feat: **HID USB communication working** — reverse-engineered from SolarPower Java/native code
- feat: protocol P17 (Protocol ID=17), not P18 or PI30
- feat: P18-style headers (`^P<len+1><cmd>\r`) without CRC (key finding!)
- feat: GS (General Status) — PV voltages, battery, grid, AC output, temperatures
- feat: PS (Power Status) — PV power, active power, load percent
- feat: MOD (Mode) — Line/Battery/Standby/Fault
- fix: P17 field mapping differs from P18 (f[0]=PV, f[4]=bat, f[7]=grid, f[10]=freq÷100)
- fix: open_hid uses os.open + O_NONBLOCK (MindFreeze approach)
- fix: root cause — we sent PI30/PI18 commands (QPIGS, QMOD) instead of P17 (GS, PS, MOD)
- fix: confirmed `^0` NAK is response to unknown commands, not periodic heartbeat

## 2.4.0 (2026-04-10)
- refactor: protocol research — reverse engineering SolarPower Java app (CRCUtil, SECFormat, SECUSBHandler)
- fix: confirmed CRC algorithm CRC16/XMODEM over `^P<cmd>` (including prefix)
- fix: wake_cmd sent CRC as ASCII hex string instead of binary bytes
- feat: build_pi18_command with length field (`^P<nnn><cmd><CRC>\r`) per PI18 spec
- chore: transport switched to HID (USB cable on HA Yellow, hidraw0 available)
- fix: removed QPIGS query fallback that falsely reported NAK
- docs: confirmed `^0\x1b\xe3\r` is autonomous heartbeat (~17s interval)
- docs: all PI18 commands (QID, QPIRI, QPIGS, QMOD...) return NAK — cause unknown at the time
- security: reviewed alternative integrations (ned-kelly, MindFreeze, GitGab19) — no phone-home code

## 2.3.0
- feat: hidraw HID transport, serial auto-detect, debug logging

## 2.0.0
- BREAKING: switched to RS232/serial (/dev/ttyUSB0) — USB HID blocked in HAOS
- refactor: replaced pyusb with pyserial
- chore: removed all USB HID/hidraw code, full_access, apparmor hacks
- feat: configurable baud rate (default 2400)

## 1.7.0
- feat: dual-mode communication — hidraw (primary) + pyusb (fallback)
- feat: run.sh dynamically binds usbhid driver and sets HIDRAW_PATH

## 1.6.0
- fix: run.sh mounts usbfs inside container (fix for EPERM/EIO on /dev/bus/usb)

## 1.5.0
- fix: added `apparmor: false` — resolves EPERM block on /dev/bus/usb

## 1.4.0
- feat: diagnostics — log uid/gid and open() test for each USB node
- fix: full_access: true instead of SYS_RAWIO only

## 1.3.0
- fix: USB reset before communication
- fix: claim interface before ctrl_transfer (fix for EIO)
- feat: fallback OUTPUT→FEATURE HID report type

## 1.2.0
- refactor: replaced hidraw with pyusb (libusb)
- fix: robust parsing of null env variables from bashio

## 1.1.0
- refactor: migration from /dev/hidraw0 to /dev/bus/usb (pyusb)
- fix: ValueError for null USB_VENDOR_ID/USB_PRODUCT_ID

## 1.0.0
- feat: initial add-on version
- feat: PI30 protocol (QPIGS + QMOD), MQTT auto-discovery
- feat: 17 sensors, 4 binary sensors, mode sensor
