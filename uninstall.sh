#!/bin/bash
# Fan Control Uninstall Script for HiFiBerry OS
# Removes all components installed by install.sh

set -e

BEOCREATE_EXT_DIR="/opt/beocreate/beo-extensions/fan-control"
INSTALL_DIR="/opt/hifiberry/fan-control"

log() {
    echo "[INFO]: $*" >&2
    logger -t "fan-control-uninstall" "[INFO]: $*"
}

error() {
    echo "[ERROR]: $*" >&2
    logger -t "fan-control-uninstall" "[ERROR]: $*"
}

echo "Fan Control Uninstall Script"
echo "============================"
echo "This will remove:"
echo "  - Fan control services"
echo "  - Installation directory: $INSTALL_DIR"
echo "  - Beocreate extension: $BEOCREATE_EXT_DIR"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    error "Please run as root"
    exit 1
fi

# Ask for confirmation unless -y flag is passed
if [ "$1" != "-y" ] && [ "$1" != "--yes" ]; then
    read -p "Are you sure you want to uninstall Fan Control? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log "Uninstall cancelled"
        exit 0
    fi
fi

log "Starting Fan Control uninstall..."

# Stop and disable services
if command -v systemctl >/dev/null 2>&1; then
    log "Stopping systemd services..."
    
    # Stop fan-control service
    if systemctl is-active --quiet fan-control.service; then
        log "Stopping fan-control.service..."
        systemctl stop fan-control.service || error "Failed to stop fan-control.service"
    fi
    
    # Stop fan-api service
    if systemctl is-active --quiet fan-api.service; then
        log "Stopping fan-api.service..."
        systemctl stop fan-api.service || error "Failed to stop fan-api.service"
    fi
    
    # Disable services
    if systemctl is-enabled --quiet fan-control.service 2>/dev/null; then
        log "Disabling fan-control.service..."
        systemctl disable fan-control.service || error "Failed to disable fan-control.service"
    fi
    
    if systemctl is-enabled --quiet fan-api.service 2>/dev/null; then
        log "Disabling fan-api.service..."
        systemctl disable fan-api.service || error "Failed to disable fan-api.service"
    fi
    
    # Remove systemd service files
    log "Removing systemd service files..."
    [ -f /etc/systemd/system/fan-control.service ] && rm -f /etc/systemd/system/fan-control.service
    [ -f /etc/systemd/system/fan-api.service ] && rm -f /etc/systemd/system/fan-api.service
    
    systemctl daemon-reload
    log "Systemd services removed"
else
    log "Stopping init scripts..."
    
    # Stop services via init scripts
    if [ -f /etc/init.d/fan-control ]; then
        log "Stopping fan-control..."
        /etc/init.d/fan-control stop 2>/dev/null || true
    fi
    
    if [ -f /etc/init.d/fan-api ]; then
        log "Stopping fan-api..."
        /etc/init.d/fan-api stop 2>/dev/null || true
    fi
    
    # Remove init scripts
    log "Removing init scripts..."
    [ -f /etc/init.d/fan-control ] && rm -f /etc/init.d/fan-control
    [ -f /etc/init.d/fan-api ] && rm -f /etc/init.d/fan-api
    
    # Remove auto-start symlinks
    log "Removing auto-start symlinks..."
    [ -L /etc/rc.d/S98fan-control ] && rm -f /etc/rc.d/S98fan-control
    [ -L /etc/rc.d/S99fan-api ] && rm -f /etc/rc.d/S99fan-api
    [ -L /etc/rc3.d/S98fan-control ] && rm -f /etc/rc3.d/S98fan-control
    [ -L /etc/rc3.d/S99fan-api ] && rm -f /etc/rc3.d/S99fan-api
    
    log "Init scripts removed"
fi

# Remove Beocreate extension
if [ -d "$BEOCREATE_EXT_DIR" ]; then
    log "Removing Beocreate extension from $BEOCREATE_EXT_DIR..."
    rm -rf "$BEOCREATE_EXT_DIR"
    log "Beocreate extension removed"
else
    log "Beocreate extension not found (already removed or never installed)"
fi

# Remove installation directory
if [ -d "$INSTALL_DIR" ]; then
    log "Removing installation directory $INSTALL_DIR..."
    rm -rf "$INSTALL_DIR"
    log "Installation directory removed"
else
    log "Installation directory not found (already removed or never installed)"
fi

# Clean up any GPIO exports that might be left over
log "Cleaning up GPIO exports..."
if [ -d /sys/class/gpio ]; then
    # Try to unexport common GPIO pins if they were exported by fan control
    for pin in 5 6 12 13 16 18 19 20 21 26; do
        if [ -d "/sys/class/gpio/gpio${pin}" ]; then
            echo "$pin" > /sys/class/gpio/unexport 2>/dev/null || true
        fi
        # Also try with base offset (for newer kernels)
        sysfs_pin=$((512 + pin))
        if [ -d "/sys/class/gpio/gpio${sysfs_pin}" ]; then
            echo "$sysfs_pin" > /sys/class/gpio/unexport 2>/dev/null || true
        fi
    done
fi

# Restart Beocreate to unload extension
log "Restarting Beocreate 2 service to unload extension..."
if command -v systemctl >/dev/null 2>&1; then
    systemctl restart beocreate2 2>/dev/null || log "Could not restart beocreate2 (may not be running)"
else
    /etc/init.d/beocreate2 restart 2>/dev/null || log "Could not restart beocreate2 (may not be running)"
fi

log "Uninstall completed successfully!"
echo ""
echo "Fan Control has been completely removed from your system."
echo ""
echo "Files removed:"
echo "  - $INSTALL_DIR"
echo "  - $BEOCREATE_EXT_DIR"
echo "  - /etc/systemd/system/fan-control.service (or /etc/init.d/fan-control)"
echo "  - /etc/systemd/system/fan-api.service (or /etc/init.d/fan-api)"
echo ""
echo "To reinstall, run: ./install.sh"

