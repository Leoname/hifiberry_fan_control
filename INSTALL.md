# Fan Control Service Installation for HiFiBerry OS

This guide explains how to install the fan control service on HiFiBerry OS (Buildroot-based).

## Important Notes About HiFiBerry OS

HiFiBerry OS is a minimal Buildroot-based system optimized for audio playback. It has several limitations:

- **No `pip3`**: Python package manager is not available
- **No `vcgencmd`**: Raspberry Pi utilities are not included
- **No `RPi.GPIO`**: Python GPIO library is not available
- **Minimal init system**: May use BusyBox init instead of systemd
- **Temperature reading**: Uses `/sys/class/thermal/thermal_zone0/temp` instead of `vcgencmd`
- **GPIO control**: Uses sysfs GPIO interface (no Python libraries required)

## Prerequisites

- HiFiBerry OS running on Raspberry Pi
- Python 3 installed (check with `python3 --version`)
- Root access to the system

**Note**: The `fan_control.py` script uses **sysfs GPIO interface** and does **NOT require RPi.GPIO library**. This makes it compatible with HiFiBerry OS without needing to install additional Python packages.

## Installation Steps

### 1. Copy Files to the System

Create the directory and copy the fan control script:

```bash
# On the Raspberry Pi
mkdir -p /opt/hifiberry/fan-control
# Copy fan_control.py to /opt/hifiberry/fan-control/
```

You can use `scp` from your development machine:

```bash
# On your development machine (replace IP_ADDRESS with your Pi's IP)
scp fan_control.py root@IP_ADDRESS:/opt/hifiberry/fan-control/
```

### 2. Make Script Executable

```bash
chmod +x /opt/hifiberry/fan-control/fan_control.py
```

### 3. Verify Temperature Reading Works

Test that temperature can be read:

```bash
cat /sys/class/thermal/thermal_zone0/temp
```

This should return a number in millidegrees Celsius (e.g., `45000` = 45.0°C).

### 4. Test Script Manually

Before setting up as a service, test the script manually:

```bash
/usr/bin/python3 /opt/hifiberry/fan-control/fan_control.py
```

Press Ctrl+C to stop. Verify it reads temperature and controls the fan correctly.

### 5. Choose Your Init System

HiFiBerry OS may use either **systemd** or **BusyBox init**. Check which one you have:

```bash
# Check for systemd
which systemctl

# Check for BusyBox init
ls /etc/init.d/
```

Follow the appropriate section below:

## Option A: Systemd Installation (if systemctl exists)

### Copy Service File

```bash
scp fan-control.service root@IP_ADDRESS:/etc/systemd/system/
```

Or manually create `/etc/systemd/system/fan-control.service` with the contents from `fan-control.service`.

### Enable and Start the Service

```bash
# Reload systemd to recognize the new service
systemctl daemon-reload

# Enable the service to start on boot
systemctl enable fan-control.service

# Start the service
systemctl start fan-control.service
```

### Service Management (Systemd)

**Stop the service:**
```bash
systemctl stop fan-control.service
```

**Start the service:**
```bash
systemctl start fan-control.service
```

**Restart the service:**
```bash
systemctl restart fan-control.service
```

**Disable auto-start on boot:**
```bash
systemctl disable fan-control.service
```

**View logs:**
```bash
# View all logs
journalctl -u fan-control.service

# View logs with live tail
journalctl -u fan-control.service -f

# View recent logs (last 50 lines)
journalctl -u fan-control.service -n 50
```

## Option B: BusyBox Init Installation (if systemctl doesn't exist)

### Copy Init Script

```bash
scp fan-control-busybox.init root@IP_ADDRESS:/etc/init.d/fan-control
```

Or manually create `/etc/init.d/fan-control` with the contents from `fan-control-busybox.init`.

### Make Init Script Executable

```bash
chmod +x /etc/init.d/fan-control
```

### Enable Service to Start on Boot

Create a symlink in the runlevel directory:

```bash
# For most BusyBox systems
ln -s /etc/init.d/fan-control /etc/rc.d/S99fan-control

# Or if /etc/rc.d doesn't exist, check which runlevel directories exist
ls -d /etc/rc*.d/

# Then create symlink with appropriate number (higher = starts later)
# Example: ln -s /etc/init.d/fan-control /etc/rc3.d/S99fan-control
```

### Service Management (BusyBox Init)

**Start the service:**
```bash
/etc/init.d/fan-control start
```

**Stop the service:**
```bash
/etc/init.d/fan-control stop
```

**Restart the service:**
```bash
/etc/init.d/fan-control restart
```

**Check status:**
```bash
/etc/init.d/fan-control status
```

**View logs:**
```bash
# Logs are written to /var/log/fan-control.log
tail -f /var/log/fan-control.log

# Or view recent logs
tail -n 50 /var/log/fan-control.log
```

## Configuration

The fan control service uses the following temperature thresholds:

- **≥ 50°C**: Fan at 100% duty cycle, check every 180 seconds
- **≥ 40°C**: Fan at 85% duty cycle, check every 120 seconds
- **< 40°C**: Fan at 60% duty cycle, check every 60 seconds

To modify these thresholds, edit `/opt/hifiberry/fan-control/fan_control.py` and restart the service.

## GPIO Pin

The service uses GPIO pin 12 (BCM numbering) for PWM fan control. Make sure your fan is connected to this pin.

To use a different GPIO pin, modify line 33 in `fan_control.py`:

```python
GPIO.setup(12, GPIO.OUT)  # Change 12 to your desired GPIO pin
pwm = GPIO.PWM(12, 100)   # Change 12 to your desired GPIO pin
```

## Troubleshooting

### Service won't start

**For systemd:**
1. Check service status: `systemctl status fan-control.service`
2. Check logs: `journalctl -u fan-control.service`
3. Verify Python script is executable: `ls -l /opt/hifiberry/fan-control/fan_control.py`
4. Test script manually: `/usr/bin/python3 /opt/hifiberry/fan-control/fan_control.py`

**For BusyBox init:**
1. Check service status: `/etc/init.d/fan-control status`
2. Check logs: `tail -f /var/log/fan-control.log`
3. Verify Python script is executable: `ls -l /opt/hifiberry/fan-control/fan_control.py`
4. Test script manually: `/usr/bin/python3 /opt/hifiberry/fan-control/fan_control.py`

### GPIO Control Methods

The `fan_control.py` script uses **sysfs GPIO interface** directly, which doesn't require any Python libraries. It will:

1. **Try to use hardware PWM** (if `/sys/class/pwm/pwmchip0` is available)
2. **Fall back to software PWM** using sysfs GPIO if hardware PWM isn't available

**Note**: Software PWM is less precise but functional for fan control. Hardware PWM is preferred if available.

If you want to use RPi.GPIO instead (not recommended for HiFiBerry OS):

1. **Rebuild HiFiBerry OS image** with RPi.GPIO included in the Buildroot configuration, OR
2. **Install from source manually** (if Python development tools are available):
   ```bash
   # Download and install RPi.GPIO from source
   wget https://files.pythonhosted.org/packages/source/R/RPi.GPIO/RPi.GPIO-0.7.0.tar.gz
   tar xzf RPi.GPIO-0.7.0.tar.gz
   cd RPi.GPIO-0.7.0
   python3 setup.py install
   ```

**Warning**: Some users report that RPi.GPIO can interfere with HiFiBerry DAC operations. The sysfs-based approach in this script avoids this issue.

### GPIO permission issues

The service runs as root by default, which should have GPIO access. If you encounter issues:

**For sysfs GPIO (used by this script):**
- Verify you're running as root: `whoami` should return `root`
- Test GPIO export manually:
  ```bash
  echo 12 > /sys/class/gpio/export
  echo out > /sys/class/gpio/gpio12/direction
  echo 1 > /sys/class/gpio/gpio12/value
  cat /sys/class/gpio/gpio12/value
  echo 0 > /sys/class/gpio/gpio12/value
  echo 12 > /sys/class/gpio/unexport
  ```
- If you see "Permission denied", you're not running as root

### Temperature reading fails

The script uses `/sys/class/thermal/thermal_zone0/temp` instead of `vcgencmd` (which is not available on HiFiBerry OS).

Test temperature reading manually:
```bash
cat /sys/class/thermal/thermal_zone0/temp
```

This should return a number (temperature in millidegrees Celsius). If it fails:
- Check if thermal zone exists: `ls -la /sys/class/thermal/`
- Check system logs: `dmesg | grep thermal`

### Python3 not found

Verify Python 3 is installed:
```bash
python3 --version
which python3
```

If not available, you'll need to rebuild HiFiBerry OS with Python 3 included.

### Checking what's actually available

Run these commands to see what's available on your HiFiBerry OS system:

```bash
# Check Python
python3 --version
which python3

# Check for hardware PWM (optional)
ls -la /sys/class/pwm/

# Check init system
which systemctl
ls -la /etc/init.d/

# Check temperature reading
cat /sys/class/thermal/thermal_zone0/temp
```

## Uninstallation

To completely remove Fan Control and start fresh:

```bash
# On the HiFiBerry OS device (from where you have the scripts)
./uninstall.sh

# Or with auto-confirm (no prompt)
./uninstall.sh -y
```

The uninstall script will:
- Stop and disable fan-control and fan-api services
- Remove service files (systemd or init scripts)
- Delete `/opt/hifiberry/fan-control` directory
- Remove Beocreate extension from `/opt/beocreate/beo-extensions/fan-control`
- Clean up any GPIO exports
- Restart Beocreate to unload the extension

### Manual Uninstallation

If you prefer to manually uninstall:

```bash
# Stop services
systemctl stop fan-control.service fan-api.service 2>/dev/null || true
/etc/init.d/fan-control stop 2>/dev/null || true
/etc/init.d/fan-api stop 2>/dev/null || true

# Disable services
systemctl disable fan-control.service fan-api.service 2>/dev/null || true

# Remove service files
rm -f /etc/systemd/system/fan-control.service
rm -f /etc/systemd/system/fan-api.service
rm -f /etc/init.d/fan-control
rm -f /etc/init.d/fan-api
rm -f /etc/rc.d/S*fan-control /etc/rc.d/S*fan-api
rm -f /etc/rc3.d/S*fan-control /etc/rc3.d/S*fan-api

# Remove directories
rm -rf /opt/hifiberry/fan-control
rm -rf /opt/beocreate/beo-extensions/fan-control

# Reload systemd
systemctl daemon-reload 2>/dev/null || true

# Restart Beocreate
systemctl restart beocreate2 2>/dev/null || /etc/init.d/beocreate2 restart 2>/dev/null || true
```

After uninstallation, you can reinstall by running `install.sh` again.
