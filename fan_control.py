#!/usr/bin/env python3
"""
Fan Control Service - Compatible with HiFiBerry OS
Uses gpiod (libgpiod) if available, falls back to sysfs GPIO interface
Modeled after HiFiBerry audiocontrol2 powercontroller approach
"""
import os
import time
import logging
import signal
import json

# Try to import gpiod (modern GPIO interface, used by HiFiBerry OS)
try:
    import gpiod
    GPIOD_AVAILABLE = True
except ImportError:
    GPIOD_AVAILABLE = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,  # Use INFO for normal operation, DEBUG for troubleshooting
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('fan_control')

# GPIO pin configuration (BCM numbering)
# GPIO 12 is a hardware PWM pin, ideal for fan control
# Can be overridden via environment variable: GPIO_PIN=12
GPIO_PIN = int(os.environ.get('GPIO_PIN', '12'))  # Default to GPIO 12 (hardware PWM capable)
PWM_FREQ = 100  # PWM frequency in Hz

# Global variables for cleanup
gpio_exported = False
gpio_line = None  # For gpiod
pwm_enabled = False
pwm_path = None
running = True
use_gpiod = False

# Status and config files for webserver/UI
STATUS_FILE = '/opt/hifiberry/fan-control/status.json'
CONFIG_FILE = '/opt/hifiberry/fan-control/config.json'
current_temp = None
current_duty_cycle = 0
pwm_mode = 'unknown'

# Manual override settings
manual_mode = False
manual_duty_cycle = 0

def signal_handler(sig, frame):
    """Handle shutdown signals"""
    global running
    logger.info("Received shutdown signal, stopping fan control...")
    running = False

# Register signal handlers
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

def init_gpiod(pin):
    """Initialize GPIO using gpiod (modern approach, used by HiFiBerry OS)"""
    global gpio_line
    try:
        chip = gpiod.Chip("/dev/gpiochip0")
        # Request line as output (offset is BCM pin number on gpiochip0)
        gpio_line = chip.get_line(pin)
        gpio_line.request(consumer="fan_control", type=gpiod.LINE_REQ_DIR_OUT)
        logger.info(f"Initialized GPIO {pin} using gpiod (libgpiod)")
        return True
    except Exception as e:
        logger.warning(f"Failed to initialize GPIO {pin} with gpiod: {e}")
        return False

def set_gpiod_value(pin, value):
    """Set GPIO value using gpiod"""
    global gpio_line
    try:
        if gpio_line:
            gpio_line.set_value(1 if value else 0)
            return True
    except Exception as e:
        logger.error(f"Failed to set GPIO value via gpiod: {e}")
    return False

def get_gpiochip_base():
    """Get the base GPIO number for the main GPIO chip (usually gpiochip512 on RPi)
    Returns the base number, or None if not found
    """
    try:
        # Look for gpiochip files in /sys/class/gpio/
        for entry in os.listdir('/sys/class/gpio/'):
            if entry.startswith('gpiochip'):
                chip_path = f'/sys/class/gpio/{entry}'
                base_path = f'{chip_path}/base'
                if os.path.exists(base_path):
                    try:
                        with open(base_path, 'r') as f:
                            base = int(f.read().strip())
                            # On Raspberry Pi, the main GPIO chip is usually base 512
                            # Check if this is the main GPIO controller (not firmware GPIO)
                            label_path = f'{chip_path}/label'
                            label = ""
                            if os.path.exists(label_path):
                                with open(label_path, 'r') as f:
                                    label = f.read().strip()
                            
                            # Main GPIO bank on RPi is usually base 512
                            # gpiochip570 is usually firmware GPIO (base 0)
                            if base == 512:
                                logger.debug(f"Found main GPIO chip base: {base} (from {entry}, label: {label})")
                                return base
                    except (ValueError, IOError):
                        continue
        logger.warning("Could not find GPIO chip with base 512")
        return None
    except Exception as e:
        logger.warning(f"Error detecting GPIO chip base: {e}")
        return None

def bcm_to_sysfs(bcm_pin):
    """Convert BCM GPIO pin number to sysfs GPIO number"""
    # On newer Raspberry Pi kernels, BCM GPIO numbers need base offset
    # gpiochip512 typically has base 512, so BCM 5 = 512 + 5 = 517
    base = get_gpiochip_base()
    if base is None:
        # Fallback: assume base 512 for Raspberry Pi
        base = 512
        logger.debug(f"Using default base {base} for BCM to sysfs conversion")
    sysfs_pin = base + bcm_pin
    logger.debug(f"BCM GPIO {bcm_pin} -> sysfs GPIO {sysfs_pin} (base: {base})")
    return sysfs_pin

def check_gpio_available(pin):
    """Check if a GPIO pin might be available by checking if it's already exported"""
    # Try both BCM pin number and sysfs pin number
    sysfs_pin = bcm_to_sysfs(pin)
    for test_pin in [pin, sysfs_pin]:
        gpio_path = f'/sys/class/gpio/gpio{test_pin}'
        if os.path.exists(gpio_path):
            return True
    return False

def export_gpio(pin):
    """Export GPIO pin via sysfs (BCM numbering)
    Simplified approach: try sysfs offset first, then direct BCM number
    """
    if not os.path.exists('/sys/class/gpio/export'):
        logger.error("GPIO sysfs interface not available")
        return False
    
    # Get sysfs pin number (BCM + base offset)
    sysfs_pin = bcm_to_sysfs(pin)
    
    # Check if already exported
    for test_pin in [sysfs_pin, pin]:
        if os.path.exists(f'/sys/class/gpio/gpio{test_pin}'):
            logger.debug(f"GPIO {pin} already exported as sysfs {test_pin}")
            return True
    
    # Try exporting with sysfs offset (newer kernels)
    for test_pin in [sysfs_pin, pin]:
        try:
            with open('/sys/class/gpio/export', 'w') as f:
                f.write(str(test_pin))
            time.sleep(0.1)
            if os.path.exists(f'/sys/class/gpio/gpio{test_pin}'):
                logger.info(f"Exported GPIO {pin} as sysfs {test_pin}")
                return True
        except OSError as e:
            if e.errno == 22:  # Invalid argument
                continue
            raise
    
    logger.debug(f"Failed to export GPIO {pin} (tried sysfs {sysfs_pin} and direct {pin})")
    return False

def find_available_gpio():
    """Try to find an available GPIO pin by testing common pins"""
    # List of GPIO pins to try (common GPIOs that are usually available)
    # Excluding I2C, SPI, UART pins
    test_pins = [5, 6, 13, 19, 26, 16, 20, 21]  # Common GPIO pins on Raspberry Pi (BCM numbering)
    
    logger.info("Scanning for available GPIO pins (BCM numbering)...")
    available_pins = []
    
    # Get GPIO chip base for proper numbering
    base = get_gpiochip_base()
    logger.debug(f"Using GPIO chip base: {base}")
    
    for pin in test_pins:
        try:
            if export_gpio(pin):
                # Successfully exported, now try to set direction
                gpio_num = get_gpio_path(pin)
                try:
                    direction_path = f'/sys/class/gpio/gpio{gpio_num}/direction'
                    with open(direction_path, 'w') as f:
                        f.write('out')
                    available_pins.append(pin)
                    logger.info(f"GPIO {pin} (BCM) / sysfs {gpio_num} is available!")
                    # Unexport it for now - we'll export the chosen one later
                    unexport_gpio(pin)
                except Exception as e:
                    logger.debug(f"Could not set direction for GPIO {pin}: {e}")
                    unexport_gpio(pin)
            else:
                logger.debug(f"GPIO {pin} (BCM) not available")
        except Exception as e:
            logger.debug(f"Error testing GPIO {pin}: {e}")
            continue
    
    if available_pins:
        logger.info(f"Found {len(available_pins)} available GPIO pin(s): {', '.join(map(str, available_pins))}")
        return available_pins[0]  # Return first available
    else:
        logger.warning("No available GPIO pins found in common pins")
        return None

def unexport_gpio(pin):
    """Unexport GPIO pin via sysfs"""
    try:
        sysfs_pin = bcm_to_sysfs(pin)
        # Try both numbering schemes
        for test_pin in [sysfs_pin, pin]:
            if os.path.exists(f'/sys/class/gpio/gpio{test_pin}'):
                try:
                    with open('/sys/class/gpio/unexport', 'w') as f:
                        f.write(str(test_pin))
                    logger.debug(f"Unexported GPIO {pin} (sysfs {test_pin})")
                    return True
                except Exception:
                    continue
        return True
    except Exception as e:
        logger.warning(f"Failed to unexport GPIO {pin}: {e}")
        return False

def get_gpio_path(pin):
    """Get the actual GPIO sysfs path (may be offset)"""
    sysfs_pin = bcm_to_sysfs(pin)
    # Check which one exists
    if os.path.exists(f'/sys/class/gpio/gpio{sysfs_pin}'):
        return sysfs_pin
    elif os.path.exists(f'/sys/class/gpio/gpio{pin}'):
        return pin
    else:
        # Return sysfs_pin as default (newer kernel)
        return sysfs_pin

def setup_gpio_output(pin):
    """Set GPIO pin as output"""
    try:
        gpio_num = get_gpio_path(pin)
        direction_path = f'/sys/class/gpio/gpio{gpio_num}/direction'
        with open(direction_path, 'w') as f:
            f.write('out')
        logger.debug(f"Set GPIO {pin} (sysfs {gpio_num}) as output")
        return True
    except Exception as e:
        logger.error(f"Failed to set GPIO {pin} as output: {e}")
        return False

def set_gpio_value(pin, value):
    """Set GPIO pin value (0 or 1)"""
    try:
        gpio_num = get_gpio_path(pin)
        value_path = f'/sys/class/gpio/gpio{gpio_num}/value'
        with open(value_path, 'w') as f:
            f.write('1' if value else '0')
        return True
    except Exception as e:
        logger.error(f"Failed to set GPIO {pin} value: {e}")
        return False

def setup_hardware_pwm():
    """
    Setup hardware PWM (only works for GPIO 12/18 which are PWM0/PWM1)
    GPIO 12 is PWM0 channel 0, GPIO 18 is PWM0 channel 1
    Returns pwm_path if successful, False otherwise
    """
    try:
        # Hardware PWM only available for GPIO 12 (PWM0 channel 0) and GPIO 18 (PWM0 channel 1)
        if GPIO_PIN == 12:
            pwmchip_path = '/sys/class/pwm/pwmchip0'
            pwm_channel = 0
        elif GPIO_PIN == 18:
            pwmchip_path = '/sys/class/pwm/pwmchip0'
            pwm_channel = 1
        else:
            logger.debug(f"Hardware PWM not available for GPIO {GPIO_PIN} (only GPIO 12 and 18 support hardware PWM)")
            return False
        
        if not os.path.exists(pwmchip_path):
            logger.debug(f"Hardware PWM chip0 not found at {pwmchip_path}")
            return False
        
        # Check if we can access the chip
        try:
            with open(f'{pwmchip_path}/npwm', 'r') as f:
                npwm = int(f.read().strip())
                logger.debug(f"PWM chip has {npwm} channels")
                if pwm_channel >= npwm:
                    logger.warning(f"PWM channel {pwm_channel} not available (chip only has {npwm} channels)")
                    return False
        except Exception as e:
            logger.warning(f"Could not read PWM chip info: {e}")
            return False
        
        pwm_path = f'{pwmchip_path}/pwm{pwm_channel}'
        
        # Export PWM channel
        if not os.path.exists(pwm_path):
            try:
                logger.debug(f"Exporting PWM channel {pwm_channel}")
                with open(f'{pwmchip_path}/export', 'w') as f:
                    f.write(str(pwm_channel))
                time.sleep(0.2)  # Give it more time to create
                
                # Verify it was created
                if not os.path.exists(pwm_path):
                    logger.warning(f"PWM channel {pwm_channel} export succeeded but path not created")
                    return False
            except (IOError, PermissionError) as e:
                logger.warning(f"Failed to export PWM channel {pwm_channel}: {e}")
                return False
            except Exception as e:
                logger.warning(f"Unexpected error exporting PWM channel: {e}")
                return False
        else:
            logger.debug(f"PWM channel {pwm_channel} already exists")
        
        # Set period (1/frequency in nanoseconds)
        period_ns = int(1000000000 / PWM_FREQ)  # Convert Hz to nanoseconds
        try:
            with open(f'{pwm_path}/period', 'w') as f:
                f.write(str(period_ns))
            logger.debug(f"Set PWM period to {period_ns}ns ({PWM_FREQ}Hz)")
        except Exception as e:
            logger.warning(f"Failed to set PWM period: {e}")
            return False
        
        # Enable PWM
        try:
            with open(f'{pwm_path}/enable', 'w') as f:
                f.write('1')
            logger.debug(f"Enabled hardware PWM")
        except Exception as e:
            logger.warning(f"Failed to enable PWM: {e}")
            return False
        
        logger.info(f"Hardware PWM enabled on {pwm_path}")
        return pwm_path
        
    except Exception as e:
        logger.warning(f"Hardware PWM setup failed: {e}")
        return False

def set_hardware_pwm_duty_cycle(pwm_path, duty_cycle_percent):
    """Set hardware PWM duty cycle (0-100%)"""
    try:
        # Read period
        with open(f'{pwm_path}/period', 'r') as f:
            period_ns = int(f.read().strip())
        
        # Calculate duty cycle in nanoseconds
        duty_ns = int(period_ns * duty_cycle_percent / 100.0)
        
        # Set duty cycle
        with open(f'{pwm_path}/duty_cycle', 'w') as f:
            f.write(str(duty_ns))
        
        return True
    except Exception as e:
        logger.error(f"Failed to set PWM duty cycle: {e}")
        return False

def gpiod_software_pwm(pin, duty_cycle_percent, duration_seconds):
    """Software PWM using gpiod (more efficient than sysfs)"""
    if duty_cycle_percent == 0:
        set_gpiod_value(pin, 0)
        time.sleep(duration_seconds)
        return
    elif duty_cycle_percent == 100:
        set_gpiod_value(pin, 1)
        time.sleep(duration_seconds)
        return
    
    period_ms = 1000.0 / PWM_FREQ
    on_time_ms = period_ms * (duty_cycle_percent / 100.0)
    off_time_ms = period_ms - on_time_ms
    
    end_time = time.time() + duration_seconds
    
    while time.time() < end_time and running:
        set_gpiod_value(pin, 1)
        time.sleep(on_time_ms / 1000.0)
        set_gpiod_value(pin, 0)
        time.sleep(off_time_ms / 1000.0)

def software_pwm(pin, duty_cycle_percent, duration_seconds):
    """
    Software PWM using sysfs GPIO
    This is less efficient but works when hardware PWM isn't available
    """
    if duty_cycle_percent == 0:
        set_gpio_value(pin, 0)
        time.sleep(duration_seconds)
        return
    elif duty_cycle_percent == 100:
        set_gpio_value(pin, 1)
        time.sleep(duration_seconds)
        return
    
    period_ms = 1000.0 / PWM_FREQ  # Period in milliseconds
    on_time_ms = period_ms * (duty_cycle_percent / 100.0)
    off_time_ms = period_ms - on_time_ms
    
    end_time = time.time() + duration_seconds
    
    while time.time() < end_time and running:
        set_gpio_value(pin, 1)
        time.sleep(on_time_ms / 1000.0)
        set_gpio_value(pin, 0)
        time.sleep(off_time_ms / 1000.0)

# Initialize GPIO
logger.info(f"Initializing GPIO pin {GPIO_PIN}...")

# Try gpiod first (modern approach, used by HiFiBerry audiocontrol2)
if GPIOD_AVAILABLE:
    logger.debug("Attempting GPIO initialization with gpiod (libgpiod)...")
    if init_gpiod(GPIO_PIN):
        use_gpiod = True
        gpio_setup_success = True
        logger.info(f"Using gpiod for GPIO {GPIO_PIN}")
    else:
        logger.warning("gpiod initialization failed, falling back to sysfs GPIO")
        use_gpiod = False

# Fall back to sysfs GPIO if gpiod not available or failed
if not use_gpiod:
    logger.debug("Using sysfs GPIO interface...")
    if not os.path.exists('/sys/class/gpio/export'):
        logger.error("GPIO sysfs interface not available!")
        logger.error("Both gpiod and sysfs GPIO interfaces are unavailable.")
        gpio_setup_success = False
    else:
        # For GPIO 12/18, try hardware PWM first (since they might be reserved for PWM)
        # If hardware PWM fails or GPIO is not 12/18, then try to export via sysfs
        gpio_exported = False
        gpio_setup_success = False
        
        # Try to setup hardware PWM first (only for GPIO 12 or 18, and only if PWM is available)
        logger.debug(f"Attempting hardware PWM setup for GPIO {GPIO_PIN}...")
        pwm_path = setup_hardware_pwm()
        if pwm_path:
            pwm_enabled = True
            use_hardware_pwm = True
            pwm_mode = 'hardware'
            gpio_setup_success = True
            logger.info(f"Using hardware PWM for GPIO {GPIO_PIN} (no sysfs export needed)")
        else:
            if GPIO_PIN in [12, 18]:
                logger.debug("Hardware PWM setup failed. Checking if PWM chip exists...")
                # Check if PWM chip exists
                if os.path.exists('/sys/class/pwm/pwmchip0'):
                    logger.warning("PWM chip exists but setup failed. This may be normal if PWM is not enabled in kernel.")
                else:
                    logger.info("PWM chip0 not found - hardware PWM not available in this kernel. Using sysfs GPIO instead.")
            
            # Hardware PWM not available, try sysfs GPIO export
            logger.debug(f"Attempting sysfs GPIO export for GPIO {GPIO_PIN}...")
            if export_gpio(GPIO_PIN):
                gpio_exported = True
                if setup_gpio_output(GPIO_PIN):
                    gpio_setup_success = True
                    logger.info(f"GPIO {GPIO_PIN} exported and configured via sysfs")
                else:
                    logger.error(f"Failed to setup GPIO {GPIO_PIN} as output")
                    unexport_gpio(GPIO_PIN)
            else:
                logger.warning(f"GPIO {GPIO_PIN} export failed. Attempting to find available GPIO pin...")
                # Try to find an available GPIO
                available_gpio = find_available_gpio()
                if available_gpio:
                    logger.warning(f"Switching to GPIO {available_gpio} which is available")
                    GPIO_PIN = available_gpio
                    if export_gpio(GPIO_PIN):
                        gpio_exported = True
                        if setup_gpio_output(GPIO_PIN):
                            gpio_setup_success = True
                            logger.info(f"GPIO {GPIO_PIN} exported and configured via sysfs (auto-selected)")
                        else:
                            logger.error(f"Failed to setup GPIO {GPIO_PIN} as output")
                            unexport_gpio(GPIO_PIN)
                else:
                    if GPIO_PIN in [12, 18]:
                        logger.warning(f"GPIO {GPIO_PIN} export failed - this pin is reserved for PWM.")
                    else:
                        logger.error(f"GPIO {GPIO_PIN} export failed and no alternative GPIO found.")

# If neither method worked, exit with helpful message
if not gpio_setup_success:
    logger.error("=" * 60)
    logger.error(f"FAILED TO INITIALIZE GPIO")
    logger.error("=" * 60)
    if not os.path.exists('/sys/class/gpio/export'):
        logger.error("GPIO sysfs interface not available at /sys/class/gpio/export")
        logger.error("This HiFiBerry OS system may not support legacy sysfs GPIO interface")
        logger.error("")
        logger.error("Possible solutions:")
        logger.error("1. Check if gpiod/libgpiod tools are available:")
        logger.error("   which gpioset")
        logger.error("   gpioinfo")
        logger.error("2. HiFiBerry OS may require different GPIO access method")
        logger.error("3. Check HiFiBerry OS documentation for GPIO usage")
    else:
        if GPIO_PIN in [12, 18]:
            logger.error(f"GPIO {GPIO_PIN} cannot be exported via sysfs (reserved for PWM)")
            logger.error("Hardware PWM setup also failed (PWM not available in kernel)")
        else:
            logger.error(f"GPIO {GPIO_PIN} export failed")
        logger.error("")
        logger.error("Possible solutions:")
        logger.error(f"1. Check if another service is using GPIO {GPIO_PIN}")
        logger.error("2. Verify GPIO pin is available: gpioinfo (if gpiod tools installed)")
        logger.error("3. Check /sys/kernel/debug/gpio for GPIO status")
        logger.error("")
        logger.error("To test GPIO manually:")
        logger.error(f"  echo {GPIO_PIN} > /sys/class/gpio/export")
        logger.error(f"  ls -la /sys/class/gpio/gpio{GPIO_PIN}")
    logger.error("=" * 60)
    exit(1)

# Hardware PWM setup was already attempted above
# If it failed and GPIO was exported, set up for software PWM
if not pwm_path and gpio_exported:
    use_hardware_pwm = False
    pwm_mode = 'software'
    logger.info("Using software PWM (hardware PWM not available, using sysfs GPIO)")
elif not pwm_path and not gpio_exported:
    # Neither hardware PWM nor GPIO export worked
    # This should not happen as we check gpio_setup_success above, but handle it anyway
    use_hardware_pwm = False
    pwm_mode = 'software'
    logger.warning("Neither hardware PWM nor GPIO export available - service may not function correctly")

logger.info("Fan control service started")

def read_cpu_temp():
    """Read CPU temperature from thermal zone (compatible with HiFiBerry OS)"""
    try:
        with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
            temp_millidegrees = int(f.read().strip())
            temp_celsius = temp_millidegrees / 1000.0
            return temp_celsius
    except (IOError, ValueError) as e:
        logger.error(f"Failed to read temperature: {e}")
        return None

def read_config():
    """Read configuration from JSON file"""
    global manual_mode, manual_duty_cycle
    
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                manual_mode = config.get('manual_mode', False)
                manual_duty_cycle = config.get('manual_duty_cycle', 0)
                logger.debug(f"Config loaded: manual_mode={manual_mode}, manual_duty_cycle={manual_duty_cycle}")
                return True
    except Exception as e:
        logger.debug(f"Failed to read config file: {e}")
    return False

def update_status_file(temp, duty_cycle, mode, error=None):
    """Update status JSON file for webserver/UI"""
    global current_temp, current_duty_cycle, pwm_mode
    current_temp = temp
    current_duty_cycle = duty_cycle
    pwm_mode = mode
    
    status = {
        'temperature': round(temp, 1) if temp is not None else None,
        'duty_cycle': duty_cycle,
        'pwm_mode': mode,
        'gpio_pin': GPIO_PIN,
        'manual_mode': manual_mode,
        'manual_duty_cycle': manual_duty_cycle if manual_mode else None,
        'last_update': time.time(),
        'error': error
    }
    
    try:
        with open(STATUS_FILE, 'w') as f:
            json.dump(status, f)
    except Exception as e:
        logger.warning(f"Failed to update status file: {e}")

# Initialize status file after functions are defined
update_status_file(None, 0, pwm_mode, "Initializing...")

try:
    while running:
        # Check for config changes
        read_config()
        
        temp = read_cpu_temp()
        if temp is None:
            logger.error("Could not read CPU temperature, retrying in 30 seconds...")
            update_status_file(None, current_duty_cycle, pwm_mode, "Temperature read failed")
            time.sleep(30.0)
            continue
        
        try:
            temp_rounded = round(temp)
            
            # Determine duty cycle based on mode
            if manual_mode:
                # Manual override mode
                dc = manual_duty_cycle
                sleep_time = 5.0  # Check config more frequently in manual mode
                logger.info(f"Manual mode: Temp: {temp}°C, Fan: {dc}%")
            else:
                # Automatic temperature-based control
                if temp_rounded >= 50:
                    dc = 100
                    sleep_time = 180.0
                elif temp_rounded >= 40:
                    dc = 85
                    sleep_time = 120.0
                else:
                    dc = 60
                    sleep_time = 60.0
                logger.info(f"Auto mode: Temp: {temp}°C, Fan: {dc}%")
            
            # Update status file
            update_status_file(temp, dc, pwm_mode)
            
            # Set PWM duty cycle
            if use_hardware_pwm:
                set_hardware_pwm_duty_cycle(pwm_path, dc)
                time.sleep(sleep_time)
            elif use_gpiod:
                # Use gpiod for software PWM (more efficient than sysfs)
                gpiod_software_pwm(GPIO_PIN, dc, sleep_time)
            else:
                software_pwm(GPIO_PIN, dc, sleep_time)
        except Exception as e:
            logger.error(f"Error processing temperature: {e}")
            update_status_file(current_temp, current_duty_cycle, pwm_mode, str(e))
            time.sleep(30.0)  # Wait a bit before retrying

except Exception as e:
    logger.error(f"Unexpected error: {e}", exc_info=True)
finally:
    # Cleanup
    logger.info("Cleaning up GPIO...")
    if pwm_enabled and pwm_path:
        try:
            with open(f'{pwm_path}/enable', 'w') as f:
                f.write('0')
            # Unexport PWM
            pwmchip_path = os.path.dirname(os.path.dirname(pwm_path))
            pwm_channel = int(os.path.basename(pwm_path).replace('pwm', ''))
            with open(f'{pwmchip_path}/unexport', 'w') as f:
                f.write(str(pwm_channel))
        except Exception as e:
            logger.warning(f"Failed to cleanup PWM: {e}")
    
    if use_gpiod and gpio_line:
        try:
            set_gpiod_value(GPIO_PIN, 0)  # Turn off GPIO
            gpio_line.release()
            logger.debug("Released gpiod line")
        except Exception as e:
            logger.warning(f"Failed to cleanup gpiod: {e}")
    elif gpio_exported:
        set_gpio_value(GPIO_PIN, 0)  # Turn off GPIO
        unexport_gpio(GPIO_PIN)
    
    # Final status update
    update_status_file(current_temp, 0, pwm_mode, "Service stopped")
    logger.info("Fan control service stopped")
