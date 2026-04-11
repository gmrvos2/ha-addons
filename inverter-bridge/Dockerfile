ARG BUILD_FROM=ghcr.io/home-assistant/aarch64-base-python:3.11-alpine3.18
FROM $BUILD_FROM

WORKDIR /app

RUN apk add --no-cache libusb libusb-dev

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY config.yaml .
COPY inverter_bridge.py .
COPY messages.py .
COPY run.sh .

RUN chmod +x /app/run.sh

# Security note (infosit.standards: Security-Baseline-Checklist):
# Container runs as root — required because /dev/hidraw0 has mode 600 (root only)
# and HAOS does not support udev rules inside add-on containers.
# Mitigated by: privileged access limited to SYS_RAWIO + SYS_ADMIN in config.yaml,
# no network server exposed, no user input accepted.

CMD ["/app/run.sh"]
