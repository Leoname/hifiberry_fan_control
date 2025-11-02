#!/bin/bash
# Fan Control Installation Script for HiFiBerry OS
# Modeled after tidal-connect-docker installation approach

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BEOCREATE_EXT_DIR="/opt/beocreate/beo-extensions/fan-control"
INSTALL_DIR="/opt/hifiberry/fan-control"
FRIENDLY_NAME="${FRIENDLY_NAME:-$(hostname)}"

log() {
    echo "[INFO]: $*" >&2
    logger -t "fan-control-install" "[INFO]: $*"
}

echo "Running environment:"
echo "  FRIENDLY_NAME:            $FRIENDLY_NAME"
echo "  BEOCREATE_EXT_DIR:        $BEOCREATE_EXT_DIR"
echo "  INSTALL_DIR:              $INSTALL_DIR"
echo "  PWD:                      $SCRIPT_DIR"
echo ""

log "Starting Fan Control installation..."

# Pre-flight checks
log "Pre-flight checks."
log "Checking if running as root..."
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root"
    exit 1
fi

log "Checking if Python 3 is available..."
if ! command -v python3 >/dev/null 2>&1; then
    log "ERROR: Python 3 is not installed"
    exit 1
fi
PYTHON_VERSION=$(python3 --version)
log "Found: $PYTHON_VERSION"

log "Creating installation directory..."
mkdir -p "$INSTALL_DIR"

log "Copying fan control script..."
cp "$SCRIPT_DIR/fan_control.py" "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/fan_control.py"

log "Copying API server..."
cp "$SCRIPT_DIR/fan_api_server.py" "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/fan_api_server.py"

log "Creating status file..."
touch "$INSTALL_DIR/status.json"
chmod 644 "$INSTALL_DIR/status.json"

log "Installing service files..."

# Check if systemd is available
if command -v systemctl >/dev/null 2>&1; then
    log "Installing systemd services..."
    cp "$SCRIPT_DIR/fan-control.service" /etc/systemd/system/
    cp "$SCRIPT_DIR/fan-api.service" /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable fan-control.service
    systemctl enable fan-api.service
    log "Systemd services installed and enabled"
else
    log "Systemd not found, using init scripts..."
    cp "$SCRIPT_DIR/fan-control-busybox.init" /etc/init.d/fan-control
    cp "$SCRIPT_DIR/fan-api-busybox.init" /etc/init.d/fan-api
    chmod +x /etc/init.d/fan-control
    chmod +x /etc/init.d/fan-api
    
    # Create symlinks for auto-start
    if [ -d /etc/rc.d ]; then
        ln -sf /etc/init.d/fan-control /etc/rc.d/S98fan-control
        ln -sf /etc/init.d/fan-api /etc/rc.d/S99fan-api
    elif [ -d /etc/rc3.d ]; then
        ln -sf /etc/init.d/fan-control /etc/rc3.d/S98fan-control
        ln -sf /etc/init.d/fan-api /etc/rc3.d/S99fan-api
    fi
    log "Init scripts installed"
fi

log "Installing Beocreate extension..."

# Remove previous installation if exists
if [ -d "$BEOCREATE_EXT_DIR" ]; then
    log "Fan control extension found, removing previous install..."
    rm -rf "$BEOCREATE_EXT_DIR"
fi

log "Adding Fan Control extension to Beocreate UI."
mkdir -p "$BEOCREATE_EXT_DIR"

cp "$SCRIPT_DIR/beocreate/beo-extensions/fan-control/index.js" "$BEOCREATE_EXT_DIR/"
cp "$SCRIPT_DIR/beocreate/beo-extensions/fan-control/menu.html" "$BEOCREATE_EXT_DIR/"
cp "$SCRIPT_DIR/beocreate/beo-extensions/fan-control/fan-control-client.js" "$BEOCREATE_EXT_DIR/"
cp "$SCRIPT_DIR/beocreate/beo-extensions/fan-control/package.json" "$BEOCREATE_EXT_DIR/"

chmod 644 "$BEOCREATE_EXT_DIR"/*

log "Finished adding Fan Control extension to Beocreate UI."

log "Installation completed."

log "Starting services..."

if command -v systemctl >/dev/null 2>&1; then
    systemctl start fan-control.service
    systemctl start fan-api.service
    log "Services started via systemd"
else
    /etc/init.d/fan-control start
    /etc/init.d/fan-api start
    log "Services started via init scripts"
fi

log "Restarting Beocreate 2 service..."

# Restart beocreate2 to load extension
if command -v systemctl >/dev/null 2>&1; then
    systemctl restart beocreate2 2>/dev/null || log "Could not restart beocreate2 (may not be running)"
else
    /etc/init.d/beocreate2 restart 2>/dev/null || log "Could not restart beocreate2 (may not be running)"
fi

log "Installation completed successfully!"
echo ""
echo "Fan Control is now installed and running."
echo "Access it through the HiFiBerry OS web interface."
echo "The API server is running on http://localhost:8088"

