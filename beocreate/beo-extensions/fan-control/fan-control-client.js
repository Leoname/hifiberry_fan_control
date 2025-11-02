// Fan Control Client-Side JavaScript
// This runs in the browser

var fanControl = (function() {
    var statusRequest = null;
    var logRequest = null;
    var updateInterval = 2000; // Update every 2 seconds
    var currentConfig = {
        manual_mode: false,
        manual_duty_cycle: 0
    };
    var configJustSaved = false; // Flag to prevent status from overriding UI immediately after save
    var statusPollingPaused = false; // Flag to completely pause status polling during config changes
    
    // Get API base URL - use current hostname, not localhost
    var API_BASE = window.location.protocol + '//' + window.location.hostname + ':8088';
    console.log('API Base URL:', API_BASE);
    
    // Start updates when the extension is shown
    function startStatusUpdates() {
        if (statusRequest) clearInterval(statusRequest);
        if (logRequest) clearInterval(logRequest);
        
        statusRequest = setInterval(updateStatus, updateInterval);
        logRequest = setInterval(updateLogs, updateInterval * 2);
        
        // Initial update
        updateStatus();
        updateLogs();
        loadConfig();
    }
    
    function updateStatus() {
        // Skip status update if polling is paused (during config save)
        if (statusPollingPaused) {
            console.log('Status polling paused, skipping update');
            return;
        }
        
        console.log('Fetching status from API...');
        
        var xhr = new XMLHttpRequest();
        xhr.open("GET", API_BASE + "/api/status", true);
        
        xhr.onreadystatechange = function() {
            if (xhr.readyState === 4) {
                if (xhr.status === 200) {
                    try {
                        var status = JSON.parse(xhr.responseText);
                        processStatus(status);
                    } catch (e) {
                        console.error("Error parsing status:", e);
                        showError("Failed to parse status data");
                    }
                } else {
                    console.error("Failed to fetch status, status code:", xhr.status);
                    showError("Cannot connect to fan control API (port 8088)");
                }
            }
        };
        
        xhr.onerror = function() {
            console.error("XHR error occurred");
            showError("Network error connecting to API");
        };
        
        xhr.send();
    }
    
    function showError(message) {
        var errorEl = document.getElementById('fan-error');
        if (errorEl) {
            errorEl.textContent = message;
            errorEl.style.display = 'block';
        }
    }
    
    function updateLogs() {
        var xhr = new XMLHttpRequest();
        xhr.open("GET", API_BASE + "/api/logs", true);
        
        xhr.onreadystatechange = function() {
            if (xhr.readyState === 4 && xhr.status === 200) {
                try {
                    var data = JSON.parse(xhr.responseText);
                    if (data.logs) {
                        processLogs(data.logs);
                    }
                } catch (e) {
                    console.error("Error parsing logs:", e);
                }
            }
        };
        
        xhr.onerror = function() {
            console.error("Failed to fetch logs");
        };
        
        xhr.send();
    }
    
    function processStatus(status) {
        console.log('Processing status:', status);
        
        var tempEl = document.getElementById('fan-temperature');
        var dutyEl = document.getElementById('fan-duty-cycle');
        var modeEl = document.getElementById('fan-pwm-mode');
        var gpioEl = document.getElementById('fan-gpio-pin');
        var errorEl = document.getElementById('fan-error');
        
        if (tempEl) {
            tempEl.textContent = status.temperature !== null ? 
                status.temperature.toFixed(1) + '°C' : 'N/A';
        }
        
        if (dutyEl) {
            dutyEl.textContent = status.duty_cycle + '%';
        }
        
        if (modeEl) {
            modeEl.textContent = status.pwm_mode.charAt(0).toUpperCase() + status.pwm_mode.slice(1);
        }
        
        if (gpioEl) {
            gpioEl.textContent = 'GPIO ' + (status.gpio_pin || '?');
        }
        
        if (errorEl) {
            if (status.error) {
                errorEl.textContent = status.error;
                errorEl.style.display = 'block';
            } else {
                errorEl.style.display = 'none';
            }
        }
        
        // Update manual mode display from status
        // Only update if we have the manual_mode field (newer status format)
        // Skip updating if we just saved config (prevents race condition)
        if (status.manual_mode !== undefined && !configJustSaved) {
            currentConfig.manual_mode = status.manual_mode;
            if (status.manual_duty_cycle !== undefined && status.manual_duty_cycle !== null) {
                currentConfig.manual_duty_cycle = status.manual_duty_cycle;
            }
            updateManualModeUI();
        }
    }
    
    function processLogs(logs) {
        var logContainer = document.getElementById('fan-logs');
        if (logContainer) {
            var recentLogs = logs.slice(-20);
            logContainer.innerHTML = '';
            
            if (recentLogs.length === 0) {
                var emptyMsg = document.createElement('div');
                emptyMsg.style.opacity = '0.5';
                emptyMsg.textContent = 'No logs available';
                logContainer.appendChild(emptyMsg);
                return;
            }
            
            recentLogs.forEach(function(log) {
                var logLine = document.createElement('div');
                logLine.style.marginBottom = '4px';
                logLine.style.paddingBottom = '4px';
                logLine.style.borderBottom = '1px solid rgba(0,0,0,0.05)';
                logLine.style.wordWrap = 'break-word';
                logLine.style.fontSize = '11px';
                logLine.textContent = log;
                
                // Highlight different log levels
                if (log.includes('ERROR')) {
                    logLine.style.color = '#d32f2f';
                    logLine.style.fontWeight = '500';
                } else if (log.includes('WARNING')) {
                    logLine.style.color = '#f57c00';
                } else if (log.includes('INFO')) {
                    logLine.style.opacity = '0.8';
                }
                
                logContainer.appendChild(logLine);
            });
            logContainer.scrollTop = logContainer.scrollHeight;
        }
    }
    
    function loadConfig() {
        var xhr = new XMLHttpRequest();
        xhr.open("GET", API_BASE + "/api/config", true);
        
        xhr.onreadystatechange = function() {
            if (xhr.readyState === 4 && xhr.status === 200) {
                try {
                    var config = JSON.parse(xhr.responseText);
                    currentConfig = config;
                    updateManualModeUI();
                } catch (e) {
                    console.error("Error parsing config:", e);
                }
            }
        };
        
        xhr.send();
    }
    
    function updateManualModeUI() {
        var toggle = document.getElementById('manual-mode-toggle');
        var controls = document.getElementById('manual-controls');
        var dutyDisplay = document.getElementById('manual-duty-display');
        
        if (toggle) {
            if (currentConfig.manual_mode) {
                toggle.classList.add('on');
            } else {
                toggle.classList.remove('on');
            }
        }
        
        if (controls) {
            if (currentConfig.manual_mode) {
                controls.classList.remove('hidden');
            } else {
                controls.classList.add('hidden');
            }
        }
        
        if (dutyDisplay) {
            dutyDisplay.textContent = currentConfig.manual_duty_cycle + '%';
        }
    }
    
    function toggleManualMode() {
        currentConfig.manual_mode = !currentConfig.manual_mode;
        // Update UI immediately for better responsiveness
        updateManualModeUI();
        saveConfig();
    }
    
    function setDutyCycle() {
        // Use simple prompt - more reliable than Beocreate text input API
        var duty = prompt("Enter fan speed (0-100%):", currentConfig.manual_duty_cycle);
        if (duty !== null && duty !== '') {
            duty = parseInt(duty);
            if (!isNaN(duty) && duty >= 0 && duty <= 100) {
                currentConfig.manual_duty_cycle = duty;
                // Update UI immediately for better responsiveness
                updateManualModeUI();
                saveConfig();
            } else {
                alert("Please enter a value between 0 and 100");
            }
        }
    }
    
    function saveConfig() {
        console.log('Saving config:', currentConfig);
        
        // Pause status polling to prevent race conditions
        statusPollingPaused = true;
        console.log('Status polling PAUSED during config save');
        
        var xhr = new XMLHttpRequest();
        xhr.open("POST", API_BASE + "/api/config", true);
        xhr.setRequestHeader("Content-Type", "application/json");
        
        xhr.onreadystatechange = function() {
            if (xhr.readyState === 4) {
                console.log('Save config response status:', xhr.status);
                console.log('Save config response:', xhr.responseText);
                
                if (xhr.status === 200) {
                    try {
                        var response = JSON.parse(xhr.responseText);
                        if (response.success) {
                            console.log("Config saved successfully");
                            // Config already applied to UI immediately by toggle/setDutyCycle
                            // Just set flag to ignore status updates temporarily
                            configJustSaved = true;
                            
                            // Wait for service to read config, then verify it's applied
                            setTimeout(function() {
                                verifyConfigApplied();
                            }, 3000);
                        } else {
                            console.error("Save failed:", response.error);
                            alert("Failed to save configuration: " + (response.error || "Unknown error"));
                            // Resume polling even on failure
                            statusPollingPaused = false;
                            configJustSaved = false;
                        }
                    } catch (e) {
                        console.error("Error parsing response:", e);
                        alert("Failed to save configuration: Invalid response");
                        // Resume polling even on failure
                        statusPollingPaused = false;
                        configJustSaved = false;
                    }
                } else {
                    console.error("Failed to save config, status:", xhr.status);
                    try {
                        var errorResponse = JSON.parse(xhr.responseText);
                        alert("Failed to save configuration: " + (errorResponse.error || xhr.statusText));
                    } catch (e) {
                        alert("Failed to save configuration: " + xhr.statusText);
                    }
                    // Resume polling even on failure
                    statusPollingPaused = false;
                    configJustSaved = false;
                }
            }
        };
        
        xhr.onerror = function() {
            console.error("XHR error saving config");
            alert("Network error: Could not connect to API server");
            // Resume polling even on failure
            statusPollingPaused = false;
            configJustSaved = false;
        };
        
        var jsonData = JSON.stringify(currentConfig);
        console.log('Sending JSON:', jsonData);
        xhr.send(jsonData);
    }
    
    function verifyConfigApplied() {
        console.log('Verifying config is applied by service...');
        
        var xhr = new XMLHttpRequest();
        xhr.open("GET", API_BASE + "/api/status", true);
        
        xhr.onreadystatechange = function() {
            if (xhr.readyState === 4 && xhr.status === 200) {
                try {
                    var status = JSON.parse(xhr.responseText);
                    
                    // Check if the status reflects our saved config
                    var configMatches = (
                        status.manual_mode === currentConfig.manual_mode &&
                        status.manual_duty_cycle === currentConfig.manual_duty_cycle
                    );
                    
                    if (configMatches) {
                        console.log('✓ Config verified! Service has applied changes. Resuming polling.');
                        statusPollingPaused = false;
                        configJustSaved = false;
                        // Process this status update
                        processStatus(status);
                    } else {
                        console.log('Config not yet applied, checking again in 2s...');
                        // Check again in 2 seconds
                        setTimeout(verifyConfigApplied, 2000);
                    }
                } catch (e) {
                    console.error("Error verifying config:", e);
                    // Resume polling anyway after max wait time
                    statusPollingPaused = false;
                    configJustSaved = false;
                }
            } else if (xhr.readyState === 4) {
                console.error("Failed to verify config");
                // Resume polling anyway
                statusPollingPaused = false;
                configJustSaved = false;
            }
        };
        
        xhr.send();
    }
    
    // Start updates when ready
    function init() {
        console.log('Fan Control client initializing...');
        startStatusUpdates();
    }
    
    // Try different initialization methods
    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        // DOM is already loaded
        setTimeout(init, 100);
    } else {
        // Wait for DOM
        document.addEventListener('DOMContentLoaded', init);
    }
    
    // Also start when menu is shown
    if (typeof beo !== 'undefined' && beo.bus) {
        beo.bus.on('ui', 'navigatedToMenu', function(data) {
            console.log('Navigated to menu:', data.menu);
            if (data.menu === 'fan-control') {
                setTimeout(startStatusUpdates, 500);
            }
        });
    }
    
    // Public API
    return {
        toggleManualMode: toggleManualMode,
        setDutyCycle: setDutyCycle
    };
    
})();
