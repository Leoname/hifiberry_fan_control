#!/usr/bin/env python3
"""
Simple HTTP API server for fan control status
Modeled after beocreate extension patterns
"""
import json
import os
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

STATUS_FILE = '/opt/hifiberry/fan-control/status.json'
CONFIG_FILE = '/opt/hifiberry/fan-control/config.json'
LOG_FILE = '/var/log/fan-control.log'

class FanControlHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        """Handle CORS preflight requests"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_GET(self):
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        if path == '/api/status':
            self.send_status()
        elif path == '/api/logs':
            self.send_logs()
        elif path == '/api/config':
            self.send_config()
        else:
            self.send_error(404, "Not Found")
    
    def do_POST(self):
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        if path == '/api/config':
            self.update_config()
        else:
            self.send_error(404, "Not Found")
    
    def send_status(self):
        """Send current status JSON"""
        try:
            if os.path.exists(STATUS_FILE):
                with open(STATUS_FILE, 'r') as f:
                    status = json.load(f)
            else:
                status = {
                    'temperature': None,
                    'duty_cycle': 0,
                    'pwm_mode': 'unknown',
                    'error': 'Status file not found'
                }
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(status).encode())
        except Exception as e:
            self.send_error(500, f"Error reading status: {str(e)}")
    
    def send_logs(self):
        """Send recent logs"""
        try:
            logs = []
            
            # Try to get logs from journalctl if available
            try:
                result = subprocess.run(
                    ['journalctl', '-u', 'fan-control.service', '-n', '50', '--no-pager'],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if line.strip():
                            logs.append(line)
            except (FileNotFoundError, subprocess.TimeoutExpired):
                # Fallback to log file if journalctl not available
                if os.path.exists(LOG_FILE):
                    with open(LOG_FILE, 'r') as f:
                        logs = f.readlines()[-50:]  # Last 50 lines
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'logs': logs}).encode())
        except Exception as e:
            self.send_error(500, f"Error reading logs: {str(e)}")
    
    def send_config(self):
        """Send current configuration"""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
            else:
                config = {
                    'manual_mode': False,
                    'manual_duty_cycle': 0
                }
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(json.dumps(config).encode())
        except Exception as e:
            self.send_error(500, f"Error reading config: {str(e)}")
    
    def update_config(self):
        """Update configuration from POST request"""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': 'No data provided'}).encode())
                return
            
            post_data = self.rfile.read(content_length)
            config = json.loads(post_data.decode('utf-8'))
            
            print(f"Received config update: {config}")  # Debug logging
            
            # Validate config
            if 'manual_mode' in config:
                config['manual_mode'] = bool(config['manual_mode'])
            if 'manual_duty_cycle' in config:
                duty = int(config['manual_duty_cycle'])
                if duty < 0 or duty > 100:
                    self.send_response(400)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(json.dumps({'success': False, 'error': 'Duty cycle must be between 0 and 100'}).encode())
                    return
                config['manual_duty_cycle'] = duty
            
            # Write config file
            os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config, f)
            
            print(f"Config saved to {CONFIG_FILE}")  # Debug logging
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True, 'config': config}).encode())
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'success': False, 'error': f'Invalid JSON: {str(e)}'}).encode())
        except Exception as e:
            print(f"Error updating config: {e}")
            import traceback
            traceback.print_exc()
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode())
    
    def log_message(self, format, *args):
        """Suppress default logging"""
        pass

def run(port=8088):
    server_address = ('', port)
    httpd = HTTPServer(server_address, FanControlHandler)
    print(f'Fan Control API server running on port {port}')
    httpd.serve_forever()

if __name__ == '__main__':
    run()

