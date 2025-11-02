# Debugging Guide for Fan Control

This guide helps you test and debug the fan control service step-by-step.

## Quick Debug Workflow

### 1. Deploy Updated Code

From your local machine:

```bash
# Copy updated files to Pi
scp fan_control.py root@hifiberry:/opt/hifiberry/fan-control/
```

### 2. Test Script Manually (Before Running as Service)

SSH into your Pi and test the script directly:

```bash
# SSH to Pi
ssh root@hifiberry

# Stop the service first (if running)
systemctl stop fan-control.service

# Run script manually to see all output
cd /opt/hifiberry/fan-control
python3 fan_control.py
```

**What to look for:**
- `gpiod available` message
- `Initialized GPIO 13 using gpiod (libgpiod)` 
- `Using gpiod for GPIO 13`
- Temperature readings
- Fan control loop starting

Press `Ctrl+C` to stop when done testing.

### 3. Check Service Status

If running as a service:

```bash
# Check service status
systemctl status fan-control.service

# View live logs
journalctl -u fan-control.service -f

# View last 50 lines
journalctl -u fan-control.service -n 50

# View logs with timestamps
journalctl -u fan-control.service -o short-iso
```

## Step-by-Step Testing

### Pre-flight Checks

```bash
# 1. Check Python version
python3 --version

# 2. Verify gpiod is available
python3 -c "import gpiod; print('gpiod available')"

# 3. Check if gpiochip0 exists
ls -la /dev/gpiochip0

# 4. Test temperature reading
cat /sys/class/thermal/thermal_zone0/temp

# 5. Check GPIO chip info
ls -la /sys/class/gpio/

# 6. Check if another process is using the GPIO
lsof 2>/dev/null | grep gpio || echo "lsof not available"
```

### Test GPIO with gpiod Directly

Test GPIO control before running the full script:

```bash
# Create a simple test script
cat > /tmp/test_gpiod.py << 'EOF'
import gpiod
import time

GPIO_PIN = 13  # Change to your pin

print(f"Testing GPIO {GPIO_PIN} with gpiod...")

try:
    # Initialize
    chip = gpiod.Chip("/dev/gpiochip0")
    line = chip.get_line(GPIO_PIN)
    line.request(consumer="test", type=gpiod.LINE_REQ_DIR_OUT)
    print(f"GPIO {GPIO_PIN} initialized successfully")
    
    # Turn on
    print("Setting GPIO HIGH...")
    line.set_value(1)
    time.sleep(2)
    
    # Turn off
    print("Setting GPIO LOW...")
    line.set_value(0)
    time.sleep(2)
    
    # Cleanup
    line.release()
    print("Test completed successfully!")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
EOF

python3 /tmp/test_gpiod.py
```

**Expected output:**
```
Testing GPIO 13 with gpiod...
GPIO 13 initialized successfully
Setting GPIO HIGH...
Setting GPIO LOW...
Test completed successfully!
```

### Test Fan Control Script with Debug Logging

Run the script with more verbose output:

```bash
# Enable debug logging temporarily
cd /opt/hifiberry/fan-control

# Edit the script to set DEBUG level (or create a test version)
python3 -c "
import sys
sys.path.insert(0, '.')

# Patch logging level to DEBUG
import logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Now import and run
import fan_control
"
```

Or modify the script temporarily:

```bash
# Backup original
cp fan_control.py fan_control.py.backup

# Change logging level
sed -i 's/level=logging.INFO/level=logging.DEBUG/' fan_control.py

# Test
python3 fan_control.py

# Restore original
mv fan_control.py.backup fan_control.py
```

### Monitor System Resources

While the script is running:

```bash
# Monitor CPU usage
top -b -n 1 | head -20

# Check memory usage
free -h

# Monitor temperature in real-time
watch -n 1 'cat /sys/class/thermal/thermal_zone0/temp'

# Check for GPIO-related processes
ps aux | grep -E 'gpio|fan'
```

## Common Issues and Solutions

### Issue 1: "gpiod module not found"

**Symptoms:**
```
ModuleNotFoundError: No module named 'gpiod'
```

**Solution:**
```bash
# Check if gpiod library is installed
python3 -c "import gpiod" 2>&1

# On HiFiBerry OS, gpiod should be available
# If not, check Python packages
python3 -c "import sys; print(sys.path)"

# Try reinstalling HiFiBerry OS or check package list
```

### Issue 2: "Permission denied" on /dev/gpiochip0

**Symptoms:**
```
PermissionError: [Errno 13] Permission denied
```

**Solution:**
```bash
# Check permissions
ls -la /dev/gpiochip0

# Should be accessible by root
# Run as root or check service user
whoami  # Should be 'root'

# Check service runs as root
systemctl show fan-control.service | grep User
```

### Issue 3: GPIO Pin Already in Use

**Symptoms:**
```
Device or resource busy
```

**Solution:**
```bash
# Check if pin is already exported via sysfs
ls -la /sys/class/gpio/ | grep gpio

# Unexport if needed (replace 13 with your pin)
echo 13 > /sys/class/gpio/unexport 2>/dev/null || true
echo 525 > /sys/class/gpio/unexport 2>/dev/null || true  # With base offset

# Check if another service is using the pin
systemctl list-units | grep gpio
ps aux | grep gpio

# Stop other GPIO services if found
```

### Issue 4: Service Keeps Restarting

**Symptoms:**
```
systemctl status shows "Restarting" or "Failed"
```

**Debug:**
```bash
# Check full service logs
journalctl -u fan-control.service --no-pager -n 100

# Check for initialization errors
journalctl -u fan-control.service | grep -E "ERROR|FAILED|Exception"

# Disable auto-restart temporarily to see the error
systemctl stop fan-control.service
systemctl edit fan-control.service
# Add:
# [Service]
# Restart=no

# Try starting manually
systemctl start fan-control.service
journalctl -u fan-control.service -f
```

### Issue 5: Temperature Reading Fails

**Symptoms:**
```
Failed to read CPU temperature
```

**Debug:**
```bash
# Test temperature reading
cat /sys/class/thermal/thermal_zone0/temp

# Check available thermal zones
ls -la /sys/class/thermal/

# Try different thermal zone if zone0 doesn't exist
cat /sys/class/thermal/thermal_zone*/temp
```

### Issue 6: Fan Not Running

**Physical Check:**
1. Verify fan is connected to the correct GPIO pin
2. Check fan power supply
3. Verify fan ground connection
4. Test fan with direct 3.3V/5V connection

**Software Check:**
```bash
# Test GPIO output directly
python3 << 'EOF'
import gpiod
import time

chip = gpiod.Chip("/dev/gpiochip0")
line = chip.get_line(13)  # Your GPIO pin
line.request(consumer="test", type=gpiod.LINE_REQ_DIR_OUT)

print("Turning fan ON for 5 seconds...")
line.set_value(1)
time.sleep(5)

print("Turning fan OFF...")
line.set_value(0)
line.release()
print("Done")
EOF
```

## Advanced Debugging

### Enable Verbose Systemd Logging

```bash
# Edit service file
systemctl edit fan-control.service

# Add these lines:
[Service]
Environment="PYTHONUNBUFFERED=1"
StandardOutput=journal+console
StandardError=journal+console

# Reload and restart
systemctl daemon-reload
systemctl restart fan-control.service
```

### Trace System Calls

```bash
# Install strace if available
which strace

# Trace the script
strace -f -e trace=open,openat,read,write python3 /opt/hifiberry/fan-control/fan_control.py 2>&1 | grep -E "gpio|thermal"
```

### Check for Kernel Messages

```bash
# Check kernel logs for GPIO-related messages
dmesg | grep -i gpio

# Check for thermal messages
dmesg | grep -i thermal

# Watch kernel logs in real-time
dmesg -w
```

### Validate Status File and API

```bash
# Check status file is being updated
watch -n 1 'cat /opt/hifiberry/fan-control/status.json'

# Test API server
curl -v http://localhost:8088/api/status
curl -v http://localhost:8088/api/logs

# Check API service
systemctl status fan-api.service
journalctl -u fan-api.service -f
```

## Performance Testing

### Test PWM Frequency

```bash
# Create PWM frequency test
python3 << 'EOF'
import gpiod
import time

chip = gpiod.Chip("/dev/gpiochip0")
line = chip.get_line(13)
line.request(consumer="pwm_test", type=gpiod.LINE_REQ_DIR_OUT)

# Test 100Hz PWM at 50% duty cycle
freq = 100
period = 1.0 / freq
on_time = period * 0.5
off_time = period * 0.5

print(f"Testing {freq}Hz PWM at 50% duty cycle for 10 seconds...")
start = time.time()
cycles = 0

while time.time() - start < 10:
    line.set_value(1)
    time.sleep(on_time)
    line.set_value(0)
    time.sleep(off_time)
    cycles += 1

print(f"Completed {cycles} cycles")
print(f"Actual frequency: {cycles / 10:.2f}Hz")

line.set_value(0)
line.release()
EOF
```

## Clean Slate Testing

If you want to start completely fresh:

```bash
# 1. Uninstall everything
./uninstall.sh -y

# 2. Clean up any leftover processes
pkill -f fan_control
pkill -f fan_api_server

# 3. Clean GPIO
for pin in 5 6 12 13 16 18 19 20 21 26; do
    echo $pin > /sys/class/gpio/unexport 2>/dev/null || true
    echo $((512 + pin)) > /sys/class/gpio/unexport 2>/dev/null || true
done

# 4. Test script manually first
python3 fan_control.py

# 5. If manual test works, install as service
./install.sh
```

## Logging Tips

### Save logs for analysis

```bash
# Save current logs
journalctl -u fan-control.service --no-pager > /tmp/fan-control.log

# Save with timestamps
journalctl -u fan-control.service -o short-iso --no-pager > /tmp/fan-control-timestamped.log

# Copy logs to your dev machine
scp root@hifiberry:/tmp/fan-control.log ./
```

### Watch multiple logs simultaneously

```bash
# In one terminal
journalctl -u fan-control.service -f

# In another terminal  
journalctl -u fan-api.service -f

# Or combine them
journalctl -u fan-control.service -u fan-api.service -f
```

## Getting Help

When asking for help, provide:

1. **System info:**
   ```bash
   uname -a
   python3 --version
   systemctl --version || echo "No systemd"
   ```

2. **Service logs:**
   ```bash
   journalctl -u fan-control.service -n 100 --no-pager
   ```

3. **GPIO status:**
   ```bash
   ls -la /dev/gpiochip*
   ls -la /sys/class/gpio/
   python3 -c "import gpiod; print('gpiod OK')"
   ```

4. **Test results:**
   - Output from manual script run
   - GPIO test results
   - Temperature reading results

