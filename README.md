# Embedded Linux Socket Threading Application for iMX92

This Python application creates 3 worker threads (in addition to the main thread) for communication with a base board. Each thread manages a specific socket connection with dedicated functionality. Designed for embedded Linux systems running on iMX92 MCU.

## Features

- **3 Specialized Socket Threads**: Each thread has a specific purpose
  - **Node Update Socket**: Synchronously receives device status and broadcast node information
  - **Command Handler Socket**: Sends commands to base board from shell input or terminal clients
  - **Real-time Data Monitoring Socket**: Receives and stores sensor data with periodic display
- **Automatic Reconnection**: All threads automatically reconnect on connection failures
- **Thread-Safe Data Storage**: Uses proper locking mechanisms for data access
- **Command Input Interface**: Interactive shell for sending commands to base board
- **Comprehensive Status Command**: View all thread status, connected devices, broadcast nodes, and sensor data
- **Data Display**: Automatic display of node updates and sensor data
- **Dual Protocol Support**: Supports both length-prefixed (production) and raw text (testing) protocols
- **Graceful Shutdown**: Handles SIGINT and SIGTERM signals, plus exit/quit commands for clean shutdown

## Thread Details

### Thread 1: Node Update Socket (Server)
- **Purpose**: Server socket that synchronously receives node update data from base board
- **Data Received**:
  - List of connected devices with their status (active/deactive)
  - Available broadcast node list
- **Behavior**: Server listens for connections from base board, blocking receive - waits for data
- **Display**: Automatically displays updates when received
- **Port**: Default 8001

### Thread 2: Command Handler Socket (Server)
- **Purpose**: Server socket that sends commands to base board and handles responses
- **Input**: Commands entered from shell (Forlinx terminal) or from connected clients (PuTTY/Tera Term)
- **Behavior**: Server listens for base board connection, accepts commands from shell or clients and sends them as raw text to connected base board
- **Command Format**: Commands are sent as-is (raw text), no length prefix. Example: `"CMD:REQ_CONN:21001A0012505037 5555"`
- **Response Handling**: 
  - Automatically detects and distinguishes between commands and responses
  - Responses are parsed and displayed in formatted format (NOT sent back to terminal client)
  - Supports both length-prefixed and raw text response protocols
  - Response format: JSON with fields like `N_id`, `GN`, `GU`, `zC`, `sC`, `sCon`, `sR`, `lCD`
- **Port**: Default 8002

### Thread 3: Real-time Data Monitoring Socket (Server)
- **Purpose**: Server socket that receives real-time sensor data from base board
- **Storage**: Maintains a list of sensor data points (configurable max size, default 1000)
- **Display**: Periodically displays recent sensor data (every 2 seconds)
- **Data Format**: Supports JSON format with device IDs (e.g., `{"21001A0012505037":"1195.0"}`) or simple key-value format
- **Features**: Automatically converts numeric string values to floats, adds timestamps to all data points
- **Port**: Default 8003

## Requirements

- Python 3.6 or higher
- Standard library only (no external dependencies)
- Network connectivity to base board

## Configuration

Edit the configuration section in the `main()` function:

```python
# Node Update Socket (Server)
NODE_UPDATE_HOST = '0.0.0.0'  # Listen on all interfaces
NODE_UPDATE_PORT = 8001

# Command Handler Socket (Server)
COMMAND_HANDLER_HOST = '0.0.0.0'  # Listen on all interfaces
COMMAND_HANDLER_PORT = 8002

# Real-time Data Monitoring Socket (Server)
REALTIME_DATA_HOST = '0.0.0.0'  # Listen on all interfaces
REALTIME_DATA_PORT = 8003
```

**Note**: All sockets are configured as servers. The base board will connect to these server sockets. Use `0.0.0.0` to listen on all network interfaces, or specify a specific IP address to listen on a particular interface.

## Usage

### Running the application:

```bash
python3 socket_threads.py
```

### Using the Command Interface:

Once the application starts, you can enter commands in the shell:

```
> help          # Show available commands
> status        # Show comprehensive status of all threads, connected devices, broadcast nodes, and sensor data
> <command>     # Send any command to base board (e.g., "CMD:REQ_CONN:21001A0012505037 5555")
> exit          # Exit the application gracefully
> quit          # Exit the application gracefully (same as exit)
```

#### Status Command Details:

The `status` command provides a comprehensive overview:
- **Thread Connection Status**: Shows if each of the 3 threads is connected
- **Connected Devices**: Lists all devices with their status (active/deactive)
- **Broadcast Nodes**: Shows available broadcast nodes
- **Sensor Data**: Displays count of stored data points and most recent sensor reading

### Stopping the application:

- Type `exit` or `quit` in the command interface - this will gracefully stop all threads and exit
- Press `Ctrl+C` in the terminal - this will also gracefully shutdown the application

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

**JSON Format (Real-time Data):**
```json
{
  "21001A0012505037": "1195.0"
}
```

The format uses device IDs as keys and sensor values as strings. Numeric values are automatically converted to floats for processing.

**Alternative JSON Format:**
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

### Command Response Format

**JSON Format (Command Response):**
```json
{
  "N_id": "21001A0012505037",
  "GN": "   CO   ",
  "GU": "0",
  "zC": "1738",
  "sC": "2542",
  "sCon": "200",
  "sR": "1000",
  "lCD": "15-10-24"
}
```

The command handler automatically detects responses and displays them in a formatted, readable format with field labels:
- `N_id` → Node ID
- `GN` → Group Name
- `GU` → Group Unit
- `zC` → Zero Count
- `sC` → Scale Count
- `sCon` → Scale Connection
- `sR` → Scale Rate
- `lCD` → Last Connection Date

**Important**: Responses are only displayed in the server terminal and are NOT sent back to the terminal client.

## Protocol Details

### Data Transmission Protocol

All sockets support both protocols:

**Length-Prefixed Protocol (Production):**
1. First 4 bytes: Data length (big-endian)
2. Remaining bytes: Actual data (UTF-8 encoded)

**Raw Text Protocol (Testing):**
- Data sent directly as UTF-8 text (no length prefix)
- Automatically detected and handled
- Useful for testing with PuTTY, Tera Term, or other terminal clients

### Socket Behavior

- **Node Update**: Server socket that listens for base board connections and synchronously receives data
- **Command Handler**: Server socket that listens for base board connections and sends commands
- **Real-time Data**: Server socket that listens for base board connections and continuously receives sensor data

**All sockets operate as servers** - the base board acts as the client and connects to these server sockets.

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

### Application Startup:

```
============================================================
Embedded Linux Socket Threading Application
iMX92 MCU - Server Sockets (Waiting for Base Board)
============================================================
Thread 1 - Node Update Server: Listening on 0.0.0.0:8001
Thread 2 - Command Handler Server: Listening on 0.0.0.0:8002
Thread 3 - Real-time Data Server: Listening on 0.0.0.0:8003
------------------------------------------------------------
Client Connection Information:
  Use these IP addresses to connect from client software:
    • 127.0.0.1 (localhost)
      - Node Update: 127.0.0.1:8001
      - Command Handler: 127.0.0.1:8002
      - Real-time Data: 127.0.0.1:8003
============================================================

[Node Update] Starting node update server socket thread
[Command Handler] Starting command handler server socket thread
[Real-time Data] Starting real-time data monitoring server socket thread

[Command Input] Ready to accept commands. Type 'help' for available commands.

> 
```

### Status Command Output:

```
> status

============================================================
Thread Status:
------------------------------------------------------------
  Node Update Thread: Connected

  Connected Devices:
    ✓ 21001A0012505037: active

  Available Broadcast Nodes:
    • 2D000A0012505037

  Command Handler Thread: Connected

  Real-time Data Thread: Connected
  Sensor Data Points Stored: 15
  Most Recent Data:
    21001A0012505037: 1195.00
============================================================
```

### Node Update Display:

```
============================================================
[Node Update] Update received at 2026-01-06 12:08:59
------------------------------------------------------------
Connected Devices:
  ✓ 21001A0012505037: active

Available Broadcast Nodes:
  • 2D000A0012505037
============================================================
```

### Real-time Sensor Data Display:

```
============================================================
[Real-time Data] Sensor Data Update - 2026-01-06 12:09:01
------------------------------------------------------------
Total data points stored: 15

Most Recent Data Points:

  Data Point 1:
    Device ID: 21001A0012505037  |  Value: 1195.00
    Time: 12:09:01

  Data Point 2:
    Device ID: 21001A0012505037  |  Value: 1196.50
    Time: 12:09:02
============================================================
```

### Command Response Display:

```
[Command Handler] Received command from terminal: CMD:REQ_CONN:21001A0012505037 5555
[Command Handler] Sent command to base board: CMD:REQ_CONN:21001A0012505037 5555
[Command Handler] Received response from base board

============================================================
[Command Handler] Command Response Received:
------------------------------------------------------------
  Node ID                  : 21001A0012505037
  Group Name               : CO
  Group Unit               : 0
  Zero Count               : 1738
  Scale Count              : 2542
  Scale Connection         : 200
  Scale Rate               : 1000
  Last Connection Date     : 15-10-24
============================================================
```

## Notes for iMX92 / Forlinx

- Ensure network interfaces are properly configured
- Check firewall rules if connections fail (servers need ports open for incoming connections)
- Monitor system resources (memory, CPU) with multiple threads
- Consider using `systemd` service for auto-start on boot
- Test socket connections independently before running full application
- **Base board must be configured to connect to these server sockets** (as clients)
- Ensure ports 8001, 8002, 8003 are not blocked by firewall
- Use `netstat -tuln` or `ss -tuln` to verify servers are listening

## Troubleshooting

### Connection Failures
- Verify server sockets are listening: `netstat -tuln | grep 800`
- Check firewall/iptables rules to ensure ports are open for incoming connections
- Verify base board can reach the iMX92 device
- Check network connectivity: `ping <imx92_ip>` from base board
- Ensure base board is configured to connect to the correct IP and ports

### Data Not Displaying
- Verify data format matches expected format (JSON or simple)
- Use `status` command to check thread connection status and see if data is being received
- Verify socket connections are established
- Check terminal output for error messages
- For real-time data, ensure data is being sent in the correct format: `{"device_id":"value"}`

### Commands Not Working
- Verify command handler thread is connected
- Check base board is accepting commands
- Verify command format matches base board expectations
- Ensure commands are sent as raw text (no length prefix required)
- Check that responses are being received (they should appear in server terminal, not sent back to client)

### Response Handling
- Responses are automatically detected and displayed in formatted format
- Responses are NOT sent back to terminal clients (PuTTY/Tera Term)
- If responses appear in terminal client, check that response detection is working correctly
- Verify response format matches expected JSON structure with response fields
