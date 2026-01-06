#!/usr/bin/env python3
"""
Simple test client for socket_threads.py
Tests the Node Update socket with proper data format
"""

import socket
import json
import sys

def send_node_update(host='127.0.0.1', port=8001, use_length_prefix=False):
    """Send node update data to the server"""
    
    # Prepare test data
    test_data = {
        "devices": {
            "device1": "active",
            "device2": "deactive",
            "device3": "active"
        },
        "broadcast_nodes": ["node1", "node2", "node3"]
    }
    
    # Convert to JSON string
    json_data = json.dumps(test_data)
    print(f"Connecting to {host}:{port}...")
    print(f"Sending data: {json_data}")
    
    try:
        # Create socket and connect
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect((host, port))
        print("Connected!")
        
        if use_length_prefix:
            # Send with length prefix (4 bytes)
            data_bytes = json_data.encode('utf-8')
            length_bytes = len(data_bytes).to_bytes(4, byteorder='big')
            sock.sendall(length_bytes)
            sock.sendall(data_bytes)
            print("Sent data with length prefix")
        else:
            # Send raw text (for testing)
            sock.sendall(json_data.encode('utf-8'))
            print("Sent raw text data")
        
        sock.close()
        print("Connection closed")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


def send_realtime_data(host='127.0.0.1', port=8003, use_length_prefix=False):
    """Send real-time sensor data to the server"""
    
    # Prepare test data in the format: {"21001A0012505037":"1195.0"}
    test_data = {
        "21001A0012505037": "1195.0"
    }
    
    # Convert to JSON string
    json_data = json.dumps(test_data)
    print(f"Connecting to {host}:{port}...")
    print(f"Sending real-time data: {json_data}")
    
    try:
        # Create socket and connect
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect((host, port))
        print("Connected!")
        
        if use_length_prefix:
            # Send with length prefix (4 bytes)
            data_bytes = json_data.encode('utf-8')
            length_bytes = len(data_bytes).to_bytes(4, byteorder='big')
            sock.sendall(length_bytes)
            sock.sendall(data_bytes)
            print("Sent data with length prefix")
        else:
            # Send raw text (for testing)
            sock.sendall(json_data.encode('utf-8'))
            print("Sent raw text data")
        
        sock.close()
        print("Connection closed")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Test client for socket_threads.py')
    parser.add_argument('--host', default='127.0.0.1', help='Server host (default: 127.0.0.1)')
    parser.add_argument('--port', type=int, default=8001, help='Server port (default: 8001)')
    parser.add_argument('--length-prefix', action='store_true', help='Use length-prefixed protocol')
    parser.add_argument('--realtime', action='store_true', help='Send real-time data (port 8003)')
    
    args = parser.parse_args()
    
    if args.realtime:
        # Override port to 8003 for real-time data
        send_realtime_data(args.host, 8003, args.length_prefix)
    else:
        send_node_update(args.host, args.port, args.length_prefix)

