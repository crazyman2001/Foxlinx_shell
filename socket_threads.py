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
                self.sock.close()
                self.sock = None
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
                
                # Synchronous blocking receive from client
                try:
                    # Receive data length first (assuming 4-byte length prefix)
                    length_data = self.client_sock.recv(4)
                    if not length_data or len(length_data) < 4:
                        raise ConnectionError("Failed to receive data length")
                    
                    data_length = int.from_bytes(length_data, byteorder='big')
                    
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
            
            with self.lock:
                # Update connected devices
                if 'devices' in update_data:
                    self.connected_devices = update_data['devices']
                
                # Update broadcast node list
                if 'broadcast_nodes' in update_data:
                    self.broadcast_node_list = update_data['broadcast_nodes']
            
            # Display update
            self._display_node_update()
            
        except json.JSONDecodeError:
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
            except Exception as e:
                print(f"[Node Update] Parse error: {e}")
                print(f"[Node Update] Raw data: {data}")
    
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
        
        while self.running:
            try:
                # Accept connection from base board
                if not self.connected:
                    try:
                        self.client_sock, addr = self.sock.accept()
                        self.connected = True
                        self.client_sock.settimeout(self.timeout)
                        print(f"[Command Handler] Base board connected from {addr}")
                    except socket.timeout:
                        # Timeout is normal when waiting for connections
                        pass
                    except Exception as e:
                        print(f"[Command Handler] Accept error: {e}")
                        if self.running:
                            time.sleep(1)
                        continue
                
                # Process command queue
                with self.command_lock:
                    if self.command_queue and self.connected:
                        command = self.command_queue.popleft()
                        self._send_command(command)
                    else:
                        time.sleep(0.1)  # Small delay when no commands
                
            except Exception as e:
                print(f"[Command Handler] Error: {e}")
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
    
    def _send_command(self, command: str):
        """Send command to base board"""
        if not self.client_sock or not self.connected:
            print(f"[Command Handler] Not connected, cannot send command")
            return
            
        try:
            # Send command with length prefix
            command_bytes = command.encode('utf-8')
            length_bytes = len(command_bytes).to_bytes(4, byteorder='big')
            
            self.client_sock.sendall(length_bytes)
            self.client_sock.sendall(command_bytes)
            
            # Wait for response
            try:
                response_length_data = self.client_sock.recv(4)
                if response_length_data and len(response_length_data) == 4:
                    response_length = int.from_bytes(response_length_data, byteorder='big')
                    response_data = self.client_sock.recv(response_length)
                    response = response_data.decode('utf-8', errors='ignore')
                    print(f"[Command Handler] Response: {response}")
                else:
                    print(f"[Command Handler] No response received")
            except socket.timeout:
                print(f"[Command Handler] Timeout waiting for response")
            except Exception as e:
                print(f"[Command Handler] Error receiving response: {e}")
            
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
                self.sock.close()
                self.sock = None
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
                
                # Receive sensor data from client
                try:
                    # Receive data length
                    length_data = self.client_sock.recv(4)
                    if not length_data or len(length_data) < 4:
                        raise ConnectionError("Failed to receive data length")
                    
                    data_length = int.from_bytes(length_data, byteorder='big')
                    
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
            sensor_data['timestamp'] = datetime.now().isoformat()
            
            with self.lock:
                self.sensor_data_list.append(sensor_data)
            
        except json.JSONDecodeError:
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
                    
            except Exception as e:
                print(f"[Real-time Data] Parse error: {e}")
                print(f"[Real-time Data] Raw data: {data}")
    
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
                for key, value in data.items():
                    if key != 'timestamp':
                        print(f"    {key}: {value}")
                if 'timestamp' in data:
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
    
    print("=" * 60)
    print("Embedded Linux Socket Threading Application")
    print("iMX92 MCU - Server Sockets (Waiting for Base Board)")
    print("=" * 60)
    print(f"Thread 1 - Node Update Server: {NODE_UPDATE_HOST}:{NODE_UPDATE_PORT}")
    print(f"Thread 2 - Command Handler Server: {COMMAND_HANDLER_HOST}:{COMMAND_HANDLER_PORT}")
    print(f"Thread 3 - Real-time Data Server: {REALTIME_DATA_HOST}:{REALTIME_DATA_PORT}")
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
