# Embedded Linux Socket Threading Application for iMX92

This Python application creates 3 worker threads (in addition to the main thread) for communication with a base board. Each thread manages a specific socket connection with dedicated functionality. Designed for embedded Linux systems running on iMX92 MCU.

## Features

- **3 Specialized Socket Threads**: Each thread has a specific purpose
  - **Node Update Socket**: Synchronously receives device status and broadcast node information
  - **Command Handler Socket**: Sends commands to base board from shell input
  - **Real-time Data Monitoring Socket**: Receives and stores sensor data with periodic display
- **Automatic Reconnection**: All threads automatically reconnect on connection failures
- **Thread-Safe Data Storage**: Uses proper locking mechanisms for data access
- **Command Input Interface**: Interactive shell for sending commands to base board
- **Data Display**: Automatic display of node updates and sensor data
- **Graceful Shutdown**: Handles SIGINT and SIGTERM signals for clean shutdown

## Thread Details

### Thread 1: Node Update Socket
- **Purpose**: Synchronously receives node update data from base board
- **Data Received**:
  - List of connected devices with their status (active/deactive)
  - Available broadcast node list
- **Behavior**: Blocking receive - waits for data from base board
- **Display**: Automatically displays updates when received

### Thread 2: Command Handler Socket
- **Purpose**: Sends commands to base board
- **Input**: Commands entered from shell (Forlinx terminal)
- **Behavior**: Queues commands and sends them to base board
- **Response**: Displays response from base board

### Thread 3: Real-time Data Monitoring Socket
- **Purpose**: Receives real-time sensor data from base board
- **Storage**: Maintains a list of sensor data points (configurable max size, default 1000)
- **Display**: Periodically displays recent sensor data (every 2 seconds)
- **Data Format**: Supports JSON or simple key-value format

## Requirements

- Python 3.6 or higher
- Standard library only (no external dependencies)
- Network connectivity to base board

## Configuration

Edit the configuration section in the `main()` function:

```python
# Node Update Socket
NODE_UPDATE_HOST = '192.168.1.100'  # Base board IP
NODE_UPDATE_PORT = 8001

# Command Handler Socket
COMMAND_HANDLER_HOST = '192.168.1.100'  # Base board IP
COMMAND_HANDLER_PORT = 8002

# Real-time Data Monitoring Socket
REALTIME_DATA_HOST = '192.168.1.100'  # Base board IP
REALTIME_DATA_PORT = 8003
```

## Usage

### Running the application:

```bash
python3 socket_threads.py
```

### Using the Command Interface:

Once the application starts, you can enter commands in the shell:

```
> help          # Show available commands
> status        # Show connection status
> <command>     # Send any command to base board
> exit          # Exit the application
```

### Stopping the application:

- Type `exit` or `quit` in the command interface, or
- Press `Ctrl+C` in the terminal

## Data Formats

### Node Update Data Format

The application supports two formats:

**JSON Format:**
```json
{
  "devices": {
    "device1": "active",
    "device2": "deactive",
    "device3": "active"
  },
  "broadcast_nodes": ["node1", "node2", "node3"]
}
```

**Simple Format:**
```
device1:active,device2:deactive,device3:active|node1,node2,node3
```

### Sensor Data Format

**JSON Format:**
```json
{
  "sensor1": 25.5,
  "sensor2": 100,
  "sensor3": "on"
}
```

**Simple Format:**
```
sensor1:25.5,sensor2:100,sensor3:on
```

## Protocol Details

### Data Transmission Protocol

All sockets use a length-prefixed protocol:
1. First 4 bytes: Data length (big-endian)
2. Remaining bytes: Actual data (UTF-8 encoded)

### Socket Behavior

- **Node Update**: Client socket that connects to base board and synchronously receives data
- **Command Handler**: Client socket that connects to base board and sends commands
- **Real-time Data**: Client socket that connects to base board and continuously receives sensor data

## Customization

### Adjust Sensor Data Storage Size

In `RealTimeDataThread.__init__()`:
```python
self.sensor_data_list = deque(maxlen=1000)  # Change 1000 to desired size
```

### Adjust Display Interval

In `RealTimeDataThread.__init__()`:
```python
self.display_interval = 2.0  # Change to desired interval in seconds
```

### Adjust Socket Timeouts

When creating threads, modify timeout values:
```python
NodeUpdateThread(host, port, timeout=10.0)  # 10 second timeout
```

## Example Output

```
============================================================
Embedded Linux Socket Threading Application
iMX92 MCU - Base Board Communication
============================================================
Thread 1 - Node Update: 192.168.1.100:8001
Thread 2 - Command Handler: 192.168.1.100:8002
Thread 3 - Real-time Data: 192.168.1.100:8003
============================================================

[Node Update] Starting node update socket thread
[Command Handler] Starting command handler socket thread
[Real-time Data] Starting real-time data monitoring socket thread

[Command Input] Ready to accept commands. Type 'help' for available commands.

> 
```

## Notes for iMX92 / Forlinx

- Ensure network interfaces are properly configured
- Check firewall rules if connections fail
- Monitor system resources (memory, CPU) with multiple threads
- Consider using `systemd` service for auto-start on boot
- Test socket connections independently before running full application
- Ensure base board is configured to accept connections on specified ports

## Troubleshooting

### Connection Failures
- Verify base board IP address and port numbers
- Check network connectivity: `ping <base_board_ip>`
- Verify base board is listening on specified ports
- Check firewall/iptables rules

### Data Not Displaying
- Verify data format matches expected format (JSON or simple)
- Check if data is being received (check thread status)
- Verify socket connections are established

### Commands Not Working
- Verify command handler thread is connected
- Check base board is accepting commands
- Verify command format matches base board expectations
