#!/usr/bin/env python3
"""
Embedded Linux Socket Threading Application for iMX92
3 Threads: Node Update, Command Handler, Real-time Data Monitoring
"""

import socket
import threading
import time
import signal
import sys
import json
from typing import Optional, Dict, List
from collections import deque
from datetime import datetime


def get_local_ip_addresses():
    """Get list of local IP addresses that clients can use to connect"""
    ip_addresses = []
    
    # Add localhost
    ip_addresses.append(('127.0.0.1', 'localhost'))
    
    # Get actual network IP addresses
    try:
        # Connect to a remote address to determine local IP
        # This doesn't actually send data, just determines the route
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Connect to a public DNS server (doesn't actually connect)
            s.connect(('8.8.8.8', 80))
            local_ip = s.getsockname()[0]
            ip_addresses.append((local_ip, 'network interface'))
        except Exception:
            pass
        finally:
            s.close()
    except Exception:
        pass
    
    # Try to get all network interfaces
    try:
        import subprocess
        if sys.platform == 'win32':
            # Windows: ipconfig
            result = subprocess.run(['ipconfig'], capture_output=True, text=True, timeout=2)
            for line in result.stdout.split('\n'):
                if 'IPv4 Address' in line or 'IPv4' in line:
                    parts = line.split(':')
                    if len(parts) > 1:
                        ip = parts[1].strip().split()[0]
                        if ip and ip not in [ip[0] for ip in ip_addresses]:
                            ip_addresses.append((ip, 'network interface'))
    except Exception:
        pass
    
    return ip_addresses


class NodeUpdateThread(threading.Thread):
    """Thread 1: Server socket - synchronously receives node update data from base board"""
    
    def __init__(self, host: str, port: int, timeout: float = 10.0):
        super().__init__(name="NodeUpdateThread", daemon=True)
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None
        self.client_sock: Optional[socket.socket] = None
        self.running = False
        self.connected = False
        self.lock = threading.Lock()
        
        # Data storage
        self.connected_devices: Dict[str, str] = {}  # device_id: status (active/deactive)
        self.broadcast_node_list: List[str] = []  # List of available broadcast nodes
        
    def run(self):
        """Main thread execution loop - server mode"""
        self.running = True
        print(f"[Node Update] Starting node update server socket thread")
        print(f"[Node Update] Listening on {self.host}:{self.port}")
        
        # Create server socket
        if not self.sock:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.settimeout(self.timeout)
            
            try:
                self.sock.bind((self.host, self.port))
                self.sock.listen(1)
                print(f"[Node Update] Server listening on {self.host}:{self.port}")
            except Exception as e:
                print(f"[Node Update] Bind error: {e}")
                if self.sock:
                    self.sock.close()
                self.sock = None
                return
        
        # Check if server socket was created successfully
        if not self.sock:
            print(f"[Node Update] Server socket not initialized, thread stopping")
            return
        
        while self.running:
            try:
                # Accept connection from base board
                if not self.connected:
                    try:
                        self.client_sock, addr = self.sock.accept()
                        self.connected = True
                        self.client_sock.settimeout(self.timeout)
                        print(f"[Node Update] Base board connected from {addr}")
                    except socket.timeout:
                        # Timeout is normal when waiting for connections
                        continue
                    except Exception as e:
                        print(f"[Node Update] Accept error: {e}")
                        if self.running:
                            time.sleep(1)
                        continue
                
                # Only process if we have a connected client
                if not self.client_sock or not self.connected:
                    time.sleep(0.1)
                    continue
                
                # Synchronous blocking receive from client
                try:
                    # Try to receive with length prefix first, fallback to raw text
                    # Peek at first 4 bytes to determine protocol
                    if not self.client_sock:
                        continue
                    self.client_sock.settimeout(0.5)
                    try:
                        peek_data = self.client_sock.recv(4, socket.MSG_PEEK)
                        if len(peek_data) == 4:
                            # Check if first 4 bytes look like a length prefix (reasonable size)
                            try:
                                potential_length = int.from_bytes(peek_data, byteorder='big')
                                # If it's a reasonable length (less than 64KB), try length-prefixed
                                if 0 < potential_length < 65536:
                                    # Consume the 4 bytes we peeked
                                    length_data = self.client_sock.recv(4)
                                    data_length = potential_length
                                    
                                    # Receive actual data
                                    received = 0
                                    data_parts = []
                                    while received < data_length:
                                        chunk = self.client_sock.recv(min(4096, data_length - received))
                                        if not chunk:
                                            raise ConnectionError("Connection closed during data receive")
                                        data_parts.append(chunk)
                                        received += len(chunk)
                                    
                                    data = b''.join(data_parts)
                                    self._process_node_update(data.decode('utf-8', errors='ignore'))
                                    self.client_sock.settimeout(self.timeout)
                                    continue
                            except (ValueError, OverflowError):
                                # Not a valid length, treat as raw text
                                pass
                    except socket.timeout:
                        # No data available yet
                        self.client_sock.settimeout(self.timeout)
                        continue
                    
                    # Fallback: Receive raw text (for testing with PuTTY/Tera Term)
                    self.client_sock.settimeout(self.timeout)
                    raw_data = self.client_sock.recv(4096)
                    if not raw_data:
                        raise ConnectionError("Connection closed")
                    
                    # Decode and process
                    data = raw_data.decode('utf-8', errors='ignore').strip()
                    if data:
                        print(f"[Node Update] Received raw text data (length: {len(data)} bytes)")
                        self._process_node_update(data)
                    
                except socket.timeout:
                    # Timeout is acceptable, continue waiting
                    pass
                except Exception as e:
                    print(f"[Node Update] Receive error: {e}")
                    self.connected = False
                    if self.client_sock:
                        try:
                            self.client_sock.close()
                        except:
                            pass
                        self.client_sock = None
                    if self.running:
                        time.sleep(1)
                        
            except Exception as e:
                print(f"[Node Update] Error: {e}")
                self.connected = False
                if self.client_sock:
                    try:
                        self.client_sock.close()
                    except:
                        pass
                    self.client_sock = None
                if self.running:
                    time.sleep(1)
        
        # Cleanup
        if self.client_sock:
            try:
                self.client_sock.close()
            except:
                pass
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
        print(f"[Node Update] Thread stopped")
    
    def _process_node_update(self, data: str):
        """Process received node update data"""
        try:
            # Try to parse as JSON
            update_data = json.loads(data)
            
            # Validate data structure
            if not isinstance(update_data, dict):
                raise ValueError("JSON root must be an object")
            
            with self.lock:
                # Update connected devices
                if 'devices' in update_data:
                    if isinstance(update_data['devices'], dict):
                        self.connected_devices = update_data['devices']
                    else:
                        print(f"[Node Update] Warning: 'devices' should be an object, got {type(update_data['devices'])}")
                
                # Update broadcast node list
                if 'broadcast_nodes' in update_data:
                    if isinstance(update_data['broadcast_nodes'], list):
                        # Ensure all items are strings
                        self.broadcast_node_list = [str(node) for node in update_data['broadcast_nodes']]
                    elif isinstance(update_data['broadcast_nodes'], dict):
                        # Convert dict to list of keys (for compatibility)
                        print(f"[Node Update] Warning: 'broadcast_nodes' should be a list, converting dict keys to list")
                        self.broadcast_node_list = list(update_data['broadcast_nodes'].keys())
                    else:
                        print(f"[Node Update] Warning: 'broadcast_nodes' should be a list, got {type(update_data['broadcast_nodes'])}")
            
            # Display update
            self._display_node_update()
            
        except json.JSONDecodeError as e:
            print(f"[Node Update] JSON decode error: {e}")
            print(f"[Node Update] Invalid JSON at line {e.lineno}, column {e.colno}")
            print(f"[Node Update] Received data: {data[:200]}...")
            # If not JSON, try to parse as simple format
            # Format: "device1:active,device2:deactive|node1,node2,node3"
            try:
                parts = data.split('|')
                if len(parts) >= 1:
                    devices_str = parts[0]
                    devices = {}
                    for device_entry in devices_str.split(','):
                        if ':' in device_entry:
                            device_id, status = device_entry.split(':', 1)
                            devices[device_id.strip()] = status.strip()
                    with self.lock:
                        self.connected_devices = devices
                
                if len(parts) >= 2:
                    nodes = [n.strip() for n in parts[1].split(',') if n.strip()]
                    with self.lock:
                        self.broadcast_node_list = nodes
                
                self._display_node_update()
            except Exception as e2:
                print(f"[Node Update] Parse error: {e2}")
                print(f"[Node Update] Raw data: {data}")
        except Exception as e:
            print(f"[Node Update] Processing error: {e}")
            print(f"[Node Update] Raw data: {data[:200]}...")
    
    def _display_node_update(self):
        """Display current node update information"""
        with self.lock:
            print("\n" + "=" * 60)
            print(f"[Node Update] Update received at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("-" * 60)
            print("Connected Devices:")
            if self.connected_devices:
                for device_id, status in self.connected_devices.items():
                    status_icon = "✓" if status.lower() == "active" else "✗"
                    print(f"  {status_icon} {device_id}: {status}")
            else:
                print("  No devices connected")
            
            print("\nAvailable Broadcast Nodes:")
            if self.broadcast_node_list:
                for node in self.broadcast_node_list:
                    print(f"  • {node}")
            else:
                print("  No broadcast nodes available")
            print("=" * 60 + "\n")
    
    def get_node_info(self) -> tuple:
        """Get current node information (thread-safe)"""
        with self.lock:
            return (self.connected_devices.copy(), self.broadcast_node_list.copy())
    
    def stop(self):
        """Stop the thread gracefully"""
        self.running = False
        self.connected = False
        if self.client_sock:
            try:
                self.client_sock.close()
            except:
                pass
            self.client_sock = None
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
            self.sock = None


class CommandHandlerThread(threading.Thread):
    """Thread 2: Server socket - command handler - sends commands to base board"""
    
    def __init__(self, host: str, port: int, timeout: float = 5.0):
        super().__init__(name="CommandHandlerThread", daemon=True)
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None
        self.client_sock: Optional[socket.socket] = None
        self.running = False
        self.connected = False
        self.lock = threading.Lock()
        self.command_queue = deque()
        self.command_lock = threading.Lock()
        
    def run(self):
        """Main thread execution loop - server mode"""
        self.running = True
        print(f"[Command Handler] Starting command handler server socket thread")
        print(f"[Command Handler] Listening on {self.host}:{self.port}")
        
        # Create server socket
        if not self.sock:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.settimeout(self.timeout)
            
            try:
                self.sock.bind((self.host, self.port))
                self.sock.listen(1)
                print(f"[Command Handler] Server listening on {self.host}:{self.port}")
            except Exception as e:
                print(f"[Command Handler] Bind error: {e}")
                self.sock.close()
                self.sock = None
                return
        
        # Check if server socket was created successfully
        if not self.sock:
            print(f"[Command Handler] Server socket not initialized, thread stopping")
            return
        
        while self.running:
            try:
                # Accept connection from base board or terminal client
                if not self.connected:
                    if not self.sock:
                        print(f"[Command Handler] Server socket is None, cannot accept connections")
                        time.sleep(1)
                        continue
                    try:
                        self.client_sock, addr = self.sock.accept()
                        self.connected = True
                        if self.client_sock:
                            self.client_sock.settimeout(self.timeout)
                            print(f"[Command Handler] Client connected from {addr}")
                    except socket.timeout:
                        # Timeout is normal when waiting for connections
                        continue
                    except Exception as e:
                        print(f"[Command Handler] Accept error: {e}")
                        if self.running:
                            time.sleep(1)
                        continue
                
                # Only process if we have a connected client
                if not self.client_sock or not self.connected:
                    time.sleep(0.1)
                    continue
                
                # Check for incoming commands from connected client (raw text from PuTTY/Tera Term)
                # Commands received from client are sent as-is (raw text) to the base board
                try:
                    if self.client_sock:
                        self.client_sock.settimeout(0.1)  # Short timeout for non-blocking check
                        raw_data = self.client_sock.recv(4096)
                        if raw_data:
                            # Received command from client (PuTTY/Tera Term), send as raw text to base board
                            command = raw_data.decode('utf-8', errors='ignore').strip()
                            if command:
                                print(f"[Command Handler] Received command from client: {command}")
                                # Send command as raw text (as-is, no length prefix)
                                self._send_raw_command(command)
                        if self.client_sock:
                            self.client_sock.settimeout(self.timeout)
                except socket.timeout:
                    # No data from client, continue
                    if self.client_sock:
                        self.client_sock.settimeout(self.timeout)
                except Exception as e:
                    print(f"[Command Handler] Error receiving from client: {e}")
                    if self.client_sock:
                        try:
                            self.client_sock.settimeout(self.timeout)
                        except:
                            pass
                
                # Process command queue (from shell input)
                with self.command_lock:
                    if self.command_queue and self.connected and self.client_sock:
                        command = self.command_queue.popleft()
                        # Send command from shell input as raw text
                        self._send_raw_command(command)
                    else:
                        time.sleep(0.1)  # Small delay when no commands
                
            except Exception as e:
                print(f"[Command Handler] Error: {e}")
                import traceback
                traceback.print_exc()
                self.connected = False
                if self.client_sock:
                    try:
                        self.client_sock.close()
                    except:
                        pass
                    self.client_sock = None
                if self.running:
                    time.sleep(1)
        
        # Cleanup
        if self.client_sock:
            try:
                self.client_sock.close()
            except:
                pass
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
        print(f"[Command Handler] Thread stopped")
    
    def _send_raw_command(self, command: str):
        """Send command as raw text (as-is, no length prefix) to connected client/base board"""
        if not self.client_sock or not self.connected:
            print(f"[Command Handler] Not connected, cannot send command")
            return
            
        try:
            # Send command as raw text (as-is, no length prefix)
            # This allows commands like "CMD:REQ_CONN:21001A0012505037 5555" to be sent directly
            command_bytes = command.encode('utf-8')
            self.client_sock.sendall(command_bytes)
            print(f"[Command Handler] Sent command (raw text): {command}")
            
            # Try to receive response (non-blocking, short timeout)
            try:
                self.client_sock.settimeout(1.0)  # Short timeout for response
                # Try length-prefixed response first
                response_length_data = self.client_sock.recv(4, socket.MSG_PEEK)
                if len(response_length_data) == 4:
                    try:
                        response_length = int.from_bytes(response_length_data, byteorder='big')
                        if 0 < response_length < 65536:
                            # Consume the 4 bytes
                            self.client_sock.recv(4)
                            response_data = self.client_sock.recv(response_length)
                            response = response_data.decode('utf-8', errors='ignore')
                            print(f"[Command Handler] Response (length-prefixed): {response}")
                            self.client_sock.settimeout(self.timeout)
                            return
                    except (ValueError, OverflowError):
                        pass
                
                # Fallback: receive raw text response
                raw_response = self.client_sock.recv(4096)
                if raw_response:
                    response = raw_response.decode('utf-8', errors='ignore').strip()
                    print(f"[Command Handler] Response (raw text): {response}")
                else:
                    print(f"[Command Handler] No response received")
                self.client_sock.settimeout(self.timeout)
            except socket.timeout:
                # No response received, that's okay
                self.client_sock.settimeout(self.timeout)
            except Exception as e:
                print(f"[Command Handler] Error receiving response: {e}")
                self.client_sock.settimeout(self.timeout)
            
        except Exception as e:
            print(f"[Command Handler] Error sending command: {e}")
            self.connected = False
            if self.client_sock:
                try:
                    self.client_sock.close()
                except:
                    pass
                self.client_sock = None
    
    def send_command(self, command: str):
        """Add command to queue (thread-safe)"""
        with self.command_lock:
            self.command_queue.append(command)
            print(f"[Command Handler] Command queued: {command}")
    
    def stop(self):
        """Stop the thread gracefully"""
        self.running = False
        self.connected = False
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
            self.sock = None


class RealTimeDataThread(threading.Thread):
    """Thread 3: Server socket - real-time data monitoring - receives sensor data from base board"""
    
    def __init__(self, host: str, port: int, max_data_points: int = 1000, timeout: float = 5.0):
        super().__init__(name="RealTimeDataThread", daemon=True)
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None
        self.client_sock: Optional[socket.socket] = None
        self.running = False
        self.connected = False
        self.lock = threading.Lock()
        
        # Data storage - using deque for efficient append/pop
        self.sensor_data_list = deque(maxlen=max_data_points)
        self.display_interval = 2.0  # Display every 2 seconds
        self.last_display_time = time.time()
        
    def run(self):
        """Main thread execution loop - server mode"""
        self.running = True
        print(f"[Real-time Data] Starting real-time data monitoring server socket thread")
        print(f"[Real-time Data] Listening on {self.host}:{self.port}")
        
        # Create server socket
        if not self.sock:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.settimeout(self.timeout)
            
            try:
                self.sock.bind((self.host, self.port))
                self.sock.listen(1)
                print(f"[Real-time Data] Server listening on {self.host}:{self.port}")
            except Exception as e:
                print(f"[Real-time Data] Bind error: {e}")
                if self.sock:
                    self.sock.close()
                self.sock = None
                return
        
        # Check if server socket was created successfully
        if not self.sock:
            print(f"[Real-time Data] Server socket not initialized, thread stopping")
            return
        
        while self.running:
            try:
                # Accept connection from base board
                if not self.connected:
                    try:
                        self.client_sock, addr = self.sock.accept()
                        self.connected = True
                        self.client_sock.settimeout(self.timeout)
                        print(f"[Real-time Data] Base board connected from {addr}")
                    except socket.timeout:
                        # Timeout is normal when waiting for connections
                        continue
                    except Exception as e:
                        print(f"[Real-time Data] Accept error: {e}")
                        if self.running:
                            time.sleep(1)
                        continue
                
                # Only process if we have a connected client
                if not self.client_sock or not self.connected:
                    time.sleep(0.1)
                    continue
                
                # Receive sensor data from client
                try:
                    # Try to receive with length prefix first, fallback to raw text
                    # Peek at first 4 bytes to determine protocol
                    if not self.client_sock:
                        continue
                    self.client_sock.settimeout(0.5)
                    try:
                        peek_data = self.client_sock.recv(4, socket.MSG_PEEK)
                        if len(peek_data) == 4:
                            # Check if first 4 bytes look like a length prefix (reasonable size)
                            try:
                                potential_length = int.from_bytes(peek_data, byteorder='big')
                                # If it's a reasonable length (less than 64KB), try length-prefixed
                                if 0 < potential_length < 65536:
                                    # Consume the 4 bytes we peeked
                                    length_data = self.client_sock.recv(4)
                                    data_length = potential_length
                                    
                                    # Receive actual data
                                    received = 0
                                    data_parts = []
                                    while received < data_length:
                                        chunk = self.client_sock.recv(min(4096, data_length - received))
                                        if not chunk:
                                            raise ConnectionError("Connection closed during data receive")
                                        data_parts.append(chunk)
                                        received += len(chunk)
                                    
                                    data = b''.join(data_parts)
                                    self._process_sensor_data(data.decode('utf-8', errors='ignore'))
                                    
                                    # Display data periodically
                                    current_time = time.time()
                                    if current_time - self.last_display_time >= self.display_interval:
                                        self._display_sensor_data()
                                        self.last_display_time = current_time
                                    
                                    self.client_sock.settimeout(self.timeout)
                                    continue
                            except (ValueError, OverflowError):
                                # Not a valid length, treat as raw text
                                pass
                    except socket.timeout:
                        # No data available yet
                        self.client_sock.settimeout(self.timeout)
                        continue
                    
                    # Fallback: Receive raw text (for testing with PuTTY/Tera Term)
                    self.client_sock.settimeout(self.timeout)
                    raw_data = self.client_sock.recv(4096)
                    if not raw_data:
                        raise ConnectionError("Connection closed")
                    
                    # Decode and process
                    data = raw_data.decode('utf-8', errors='ignore').strip()
                    if data:
                        print(f"[Real-time Data] Received raw text data (length: {len(data)} bytes)")
                        self._process_sensor_data(data)
                        
                        # Display data periodically
                        current_time = time.time()
                        if current_time - self.last_display_time >= self.display_interval:
                            self._display_sensor_data()
                            self.last_display_time = current_time
                    
                except socket.timeout:
                    # Timeout is acceptable, continue waiting
                    pass
                except Exception as e:
                    print(f"[Real-time Data] Receive error: {e}")
                    self.connected = False
                    if self.client_sock:
                        try:
                            self.client_sock.close()
                        except:
                            pass
                        self.client_sock = None
                    if self.running:
                        time.sleep(1)
                        
            except Exception as e:
                print(f"[Real-time Data] Error: {e}")
                self.connected = False
                if self.client_sock:
                    try:
                        self.client_sock.close()
                    except:
                        pass
                    self.client_sock = None
                if self.running:
                    time.sleep(1)
        
        # Cleanup
        if self.client_sock:
            try:
                self.client_sock.close()
            except:
                pass
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
        print(f"[Real-time Data] Thread stopped")
    
    def _process_sensor_data(self, data: str):
        """Process received sensor data"""
        try:
            # Try to parse as JSON
            sensor_data = json.loads(data)
            
            # Handle format: {"21001A0012505037":"1195.0"} or {"device_id": "value"}
            # Convert string values to appropriate types (float if numeric)
            processed_data = {}
            for device_id, value in sensor_data.items():
                # Try to convert value to float if it's a numeric string
                if isinstance(value, str):
                    try:
                        # Try to convert to float
                        processed_data[device_id] = float(value)
                    except ValueError:
                        # Keep as string if not numeric
                        processed_data[device_id] = value
                else:
                    processed_data[device_id] = value
            
            # Add timestamp
            processed_data['timestamp'] = datetime.now().isoformat()
            
            with self.lock:
                self.sensor_data_list.append(processed_data)
            
            # Print immediate confirmation
            print(f"[Real-time Data] Received data: {json.dumps({k: v for k, v in processed_data.items() if k != 'timestamp'})}")
            
        except json.JSONDecodeError as e:
            # If not JSON, try to parse as simple format
            # Format: "sensor1:value1,sensor2:value2,..."
            try:
                sensor_dict = {}
                for entry in data.split(','):
                    if ':' in entry:
                        sensor_name, value = entry.split(':', 1)
                        try:
                            sensor_dict[sensor_name.strip()] = float(value.strip())
                        except ValueError:
                            sensor_dict[sensor_name.strip()] = value.strip()
                
                sensor_dict['timestamp'] = datetime.now().isoformat()
                
                with self.lock:
                    self.sensor_data_list.append(sensor_dict)
                
                print(f"[Real-time Data] Received data (simple format): {sensor_dict}")
                    
            except Exception as e:
                print(f"[Real-time Data] Parse error: {e}")
                print(f"[Real-time Data] Raw data: {data}")
        except Exception as e:
            print(f"[Real-time Data] Processing error: {e}")
            print(f"[Real-time Data] Raw data: {data[:200]}...")
    
    def _display_sensor_data(self):
        """Display recent sensor data"""
        with self.lock:
            if not self.sensor_data_list:
                return
            
            print("\n" + "=" * 60)
            print(f"[Real-time Data] Sensor Data Update - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("-" * 60)
            print(f"Total data points stored: {len(self.sensor_data_list)}")
            print("\nMost Recent Data Points:")
            
            # Display last 5 data points
            recent_data = list(self.sensor_data_list)[-5:]
            for i, data in enumerate(recent_data, 1):
                print(f"\n  Data Point {i}:")
                # Display device ID and sensor value pairs
                device_data = {k: v for k, v in data.items() if k != 'timestamp'}
                if device_data:
                    for device_id, sensor_value in device_data.items():
                        # Format numeric values nicely
                        if isinstance(sensor_value, float):
                            print(f"    Device ID: {device_id}  |  Value: {sensor_value:.2f}")
                        else:
                            print(f"    Device ID: {device_id}  |  Value: {sensor_value}")
                else:
                    print("    (No device data)")
                
                if 'timestamp' in data:
                    # Extract just the time part for cleaner display
                    try:
                        time_str = data['timestamp'].split('T')[1].split('.')[0] if 'T' in data['timestamp'] else data['timestamp']
                        print(f"    Time: {time_str}")
                    except:
                        print(f"    Time: {data['timestamp']}")
            
            print("=" * 60 + "\n")
    
    def get_sensor_data(self, count: int = None) -> List[Dict]:
        """Get sensor data (thread-safe)"""
        with self.lock:
            data_list = list(self.sensor_data_list)
            if count:
                return data_list[-count:]
            return data_list.copy()
    
    def clear_sensor_data(self):
        """Clear all sensor data (thread-safe)"""
        with self.lock:
            self.sensor_data_list.clear()
    
    def stop(self):
        """Stop the thread gracefully"""
        self.running = False
        self.connected = False
        if self.client_sock:
            try:
                self.client_sock.close()
            except:
                pass
            self.client_sock = None
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
            self.sock = None


class CommandInputThread(threading.Thread):
    """Separate thread to handle command input from shell"""
    
    def __init__(self, command_handler: CommandHandlerThread):
        super().__init__(name="CommandInputThread", daemon=True)
        self.command_handler = command_handler
        self.running = False
        
    def run(self):
        """Read commands from stdin"""
        self.running = True
        print("\n[Command Input] Ready to accept commands. Type 'help' for available commands.")
        print("[Command Input] Enter commands below:\n")
        
        try:
            while self.running:
                try:
                    # Read command from stdin
                    command = input("> ").strip()
                    
                    if not command:
                        continue
                    
                    if command.lower() == 'help':
                        self._show_help()
                        continue
                    
                    if command.lower() == 'exit' or command.lower() == 'quit':
                        print("[Command Input] Exiting...")
                        break
                    
                    if command.lower() == 'status':
                        self._show_status()
                        continue
                    
                    # Send command to base board
                    if self.command_handler.connected:
                        self.command_handler.send_command(command)
                    else:
                        print("[Command Input] Error: Not connected to base board")
                        
                except EOFError:
                    # Handle Ctrl+D
                    break
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    print(f"[Command Input] Error: {e}")
                    
        except Exception as e:
            print(f"[Command Input] Thread error: {e}")
        
        self.running = False
    
    def _show_help(self):
        """Display help information"""
        print("\n" + "=" * 60)
        print("Available Commands:")
        print("  <command>     - Send command to base board")
        print("  status        - Show connection status of all threads")
        print("  help          - Show this help message")
        print("  exit/quit     - Exit the application")
        print("=" * 60 + "\n")
    
    def _show_status(self):
        """Show status of all threads"""
        print("\n" + "=" * 60)
        print("Thread Status:")
        print(f"  Node Update: {'Connected' if self.command_handler.connected else 'Disconnected'}")
        print("=" * 60 + "\n")
    
    def stop(self):
        """Stop the thread"""
        self.running = False


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    print(f"\nReceived signal {signum}, shutting down...")
    global manager
    if manager:
        manager.stop_all()
    sys.exit(0)


class SocketManager:
    """Manages all socket threads"""
    
    def __init__(self):
        self.node_update_thread: Optional[NodeUpdateThread] = None
        self.command_handler_thread: Optional[CommandHandlerThread] = None
        self.realtime_data_thread: Optional[RealTimeDataThread] = None
        self.command_input_thread: Optional[CommandInputThread] = None
        self.running = False
        
    def start_all(self, node_update_host: str, node_update_port: int,
                  command_handler_host: str, command_handler_port: int,
                  realtime_data_host: str, realtime_data_port: int):
        """Start all threads"""
        self.running = True
        
        # Create and start threads
        self.node_update_thread = NodeUpdateThread(node_update_host, node_update_port)
        self.command_handler_thread = CommandHandlerThread(command_handler_host, command_handler_port)
        self.realtime_data_thread = RealTimeDataThread(realtime_data_host, realtime_data_port)
        self.command_input_thread = CommandInputThread(self.command_handler_thread)
        
        # Start threads
        self.node_update_thread.start()
        time.sleep(0.2)
        self.command_handler_thread.start()
        time.sleep(0.2)
        self.realtime_data_thread.start()
        time.sleep(0.2)
        self.command_input_thread.start()
        
    def stop_all(self):
        """Stop all threads gracefully"""
        print("\nStopping all threads...")
        self.running = False
        
        if self.command_input_thread:
            self.command_input_thread.stop()
        
        if self.node_update_thread:
            self.node_update_thread.stop()
        
        if self.command_handler_thread:
            self.command_handler_thread.stop()
        
        if self.realtime_data_thread:
            self.realtime_data_thread.stop()
        
        # Wait for threads to finish
        threads = [self.node_update_thread, self.command_handler_thread, 
                  self.realtime_data_thread, self.command_input_thread]
        for thread in threads:
            if thread:
                thread.join(timeout=2.0)
                if thread.is_alive():
                    print(f"Warning: {thread.name} did not stop gracefully")
    
    def is_any_alive(self):
        """Check if any thread is still alive"""
        threads = [self.node_update_thread, self.command_handler_thread, 
                  self.realtime_data_thread, self.command_input_thread]
        return any(t.is_alive() for t in threads if t)


def main():
    """Main function"""
    global manager
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create socket manager
    manager = SocketManager()
    
    # Configuration - Server sockets listening on these addresses
    # Node Update Socket (Server)
    NODE_UPDATE_HOST = '0.0.0.0'  # Listen on all interfaces
    NODE_UPDATE_PORT = 8001
    
    # Command Handler Socket (Server)
    COMMAND_HANDLER_HOST = '0.0.0.0'  # Listen on all interfaces
    COMMAND_HANDLER_PORT = 8002
    
    # Real-time Data Monitoring Socket (Server)
    REALTIME_DATA_HOST = '0.0.0.0'  # Listen on all interfaces
    REALTIME_DATA_PORT = 8003
    
    # Get local IP addresses for client connections
    local_ips = get_local_ip_addresses()
    
    print("=" * 60)
    print("Embedded Linux Socket Threading Application")
    print("iMX92 MCU - Server Sockets (Waiting for Base Board)")
    print("=" * 60)
    print(f"Thread 1 - Node Update Server: Listening on {NODE_UPDATE_HOST}:{NODE_UPDATE_PORT}")
    print(f"Thread 2 - Command Handler Server: Listening on {COMMAND_HANDLER_HOST}:{COMMAND_HANDLER_PORT}")
    print(f"Thread 3 - Real-time Data Server: Listening on {REALTIME_DATA_HOST}:{REALTIME_DATA_PORT}")
    print("-" * 60)
    print("Client Connection Information:")
    print("  Use these IP addresses to connect from client software:")
    for ip, desc in local_ips:
        print(f"    • {ip} ({desc})")
        print(f"      - Node Update: {ip}:{NODE_UPDATE_PORT}")
        print(f"      - Command Handler: {ip}:{COMMAND_HANDLER_PORT}")
        print(f"      - Real-time Data: {ip}:{REALTIME_DATA_PORT}")
    print("=" * 60)
    
    # Start all threads
    manager.start_all(
        NODE_UPDATE_HOST, NODE_UPDATE_PORT,
        COMMAND_HANDLER_HOST, COMMAND_HANDLER_PORT,
        REALTIME_DATA_HOST, REALTIME_DATA_PORT
    )
    
    # Main loop - monitor threads
    try:
        while manager.running and manager.is_any_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        manager.stop_all()
        print("Application stopped")


if __name__ == "__main__":
    manager = None
    main()
