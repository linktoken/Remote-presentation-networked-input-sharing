# spotlight_server.py
# Run this script on Computer 2 (the presentation machine)

import socket
import threading
import pyautogui
import time

# Configuration
DISCOVERY_PORT = 50000  # UDP port for discovery
COMMAND_PORT = 50001  # TCP port for receiving commands
BUFFER_SIZE = 1024
SERVER_NAME = "SpotlightReceiverPC"  # Identifiable name for this server
# --- MODIFIED: Custom Pairing ID to be set at runtime ---
SERVER_PAIRING_ID = ""  # Will be set from user input when script runs

# --- Key Mappings ---
# These are the commands the server expects from the client.
# The client (with key capture) maps actual key presses to these command strings.
COMMAND_ACTIONS = {
    "NEXT": lambda: pyautogui.press('right'),
    "PREVIOUS": lambda: pyautogui.press('left'),
    "BLACK_SCREEN": lambda: pyautogui.press('b'),
    "START_PRESENTATION": lambda: pyautogui.press('f5'),
    "LASER_ON": lambda: print("Server: Laser ON command received (action not implemented)"),  # Placeholder
    "LASER_OFF": lambda: print("Server: Laser OFF command received (action not implemented)"),  # Placeholder
}


def handle_client_connection(conn, addr):
    """Handles an incoming TCP connection from a client."""
    global SERVER_PAIRING_ID  # Ensure access to the runtime-set global
    print(f"[TCP SERVER] Accepted connection from {addr}")
    paired = False
    try:
        # --- Pairing ID Verification over TCP ---
        # Expect the first message to be the pairing ID
        pairing_data = conn.recv(BUFFER_SIZE)
        if not pairing_data:
            print(f"[TCP SERVER] Connection closed by {addr} before pairing attempt.")
            return

        client_pairing_message = pairing_data.decode().strip()
        print(f"[TCP SERVER] Received pairing message: '{client_pairing_message}' from {addr}")

        expected_pairing_prefix = "PAIR_WITH_SERVER:"
        if client_pairing_message.startswith(expected_pairing_prefix):
            client_pairing_id = client_pairing_message[len(expected_pairing_prefix):]
            if client_pairing_id == SERVER_PAIRING_ID:
                paired = True
                conn.sendall(f"ACK:PAIRING_SUCCESSFUL".encode())
                print(f"[TCP SERVER] Pairing successful with {addr}")
            else:
                conn.sendall(f"NACK:PAIRING_FAILED_MISMATCH".encode())
                print(
                    f"[TCP SERVER] Pairing failed with {addr}: ID mismatch. Expected '{SERVER_PAIRING_ID}', got '{client_pairing_id}'.")
                return  # Close connection if pairing fails
        else:
            conn.sendall(f"NACK:PAIRING_FAILED_BAD_FORMAT".encode())
            print(f"[TCP SERVER] Pairing failed with {addr}: Bad pairing message format.")
            return  # Close connection

        if not paired:
            # Should have already returned, but as a safeguard
            print(f"[TCP SERVER] Pairing not established with {addr}. Closing connection.")
            return

        # Proceed with command handling if paired
        while True:
            data = conn.recv(BUFFER_SIZE)
            if not data:
                print(f"[TCP SERVER] Connection closed by {addr} after pairing.")
                break
            command = data.decode().strip()
            print(f"[TCP SERVER] Received command: {command} from {addr}")

            action = COMMAND_ACTIONS.get(command)
            if action:
                try:
                    action()
                    print(f"[TCP SERVER] Executed: {command}")
                    conn.sendall(f"ACK:{command}".encode())
                except Exception as e:
                    print(f"[TCP SERVER] Error executing command {command}: {e}")
                    print(
                        f"[TCP SERVER] Ensure the target application window (e.g., PowerPoint) is active and in the foreground.")
                    print(
                        f"[TCP SERVER] If issues persist, try running this server script with Administrator privileges.")
                    conn.sendall(f"NACK:{command} - Error: {e}".encode())
            else:
                print(f"[TCP SERVER] Unknown command: {command}")
                conn.sendall(f"NACK:Unknown command {command}".encode())
    except ConnectionResetError:
        print(f"[TCP SERVER] Connection reset by {addr}")
    except socket.timeout:  # Catch socket timeouts specifically if they occur
        print(f"[TCP SERVER] Socket timeout during communication with {addr}.")
    except Exception as e:
        print(f"[TCP SERVER] Error during TCP communication with {addr}: {e}")
    finally:
        conn.close()
        print(f"[TCP SERVER] Closed connection from {addr}")


def start_tcp_server():
    """Starts the TCP server to listen for commands."""
    global SERVER_PAIRING_ID  # Ensure access to the runtime-set global
    host_ip = '0.0.0.0'  # Listen on all available network interfaces

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # Allow address reuse
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((host_ip, COMMAND_PORT))
        server_socket.listen(5)  # Allow up to 5 queued connections
        print(f"[TCP SERVER] Listening for commands on TCP port {COMMAND_PORT}")
        print(f"[TCP SERVER] Server Pairing ID for this session: '{SERVER_PAIRING_ID}'. Clients must match this.")

        while True:
            conn, addr = server_socket.accept()
            # Set a timeout for individual client connections if desired
            # conn.settimeout(60) # e.g., 60 seconds timeout for inactivity on a connection
            client_thread = threading.Thread(target=handle_client_connection, args=(conn, addr))
            client_thread.daemon = True  # Allows main program to exit even if thread is running
            client_thread.start()
    except OSError as e:
        print(
            f"[TCP SERVER] Error binding to port {COMMAND_PORT}: {e}. Is another program (or this script already) using it?")
        print(f"[TCP SERVER] On Windows, check Task Manager for conflicting processes or try a different port.")
        print(
            f"[TCP SERVER] If the error is 'Address already in use', please wait a moment and try again, or ensure no other instance of this server is running.")
    except Exception as e:
        print(f"[TCP SERVER] An unexpected error occurred in TCP server: {e}")
    finally:
        server_socket.close()
        print("[TCP SERVER] TCP Server stopped.")


def start_udp_discovery_server():
    """Starts the UDP server to listen for discovery broadcasts."""
    global SERVER_PAIRING_ID  # Ensure access to the runtime-set global
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    # Allow address reuse for UDP socket as well, can be helpful on some systems
    udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        hostname = socket.gethostname()
        # Try to get an IP address that is likely on the LAN
        try:
            s_temp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s_temp.settimeout(1)  # Add a timeout for the dummy connection
            s_temp.connect(("8.8.8.8", 80))  # Google's DNS server, common practice
            server_ip = s_temp.getsockname()[0]
            s_temp.close()
        except (OSError, socket.timeout):  # Fallback if the above fails (e.g. no internet, or 8.8.8.8 blocked)
            server_ip = socket.gethostbyname(hostname)  # This might return 127.0.0.1
            if server_ip == "127.0.0.1":  # Try to find a non-loopback IP
                # Get all address info for AF_INET (IPv4)
                all_ips = socket.getaddrinfo(hostname, None, socket.AF_INET)
                for item in all_ips:
                    # item[4][0] is the IP address
                    if not item[4][0].startswith("127."):
                        server_ip = item[4][0]
                        break
    except socket.gaierror:
        server_ip = "127.0.0.1"  # Fallback IP
        print(
            "[UDP DISCOVERY] Warning: Could not determine a reliable local IP via hostname or dummy connection. Responding with localhost.")
        print(
            "[UDP DISCOVERY] Client might not be able to connect if it's on a different machine and this IP is 127.0.0.1.")
    except Exception as e:  # Catch any other unexpected errors during IP detection
        server_ip = "0.0.0.0"  # Fallback, client will see the source IP of UDP packet
        print(f"[UDP DISCOVERY] Error determining server IP: {e}. Will rely on client seeing UDP source IP.")

    try:
        udp_socket.bind(('', DISCOVERY_PORT))  # Bind to all interfaces for receiving
        print(f"[UDP DISCOVERY] Listening for discovery broadcasts on UDP port {DISCOVERY_PORT}")
        print(
            f"[UDP DISCOVERY] Server Pairing ID for this session: '{SERVER_PAIRING_ID}'. Will only respond to clients sending the correct ID.")
        print(
            f"[UDP DISCOVERY] Server will respond indicating its IP as: {server_ip} (ensure this is reachable by client if not 0.0.0.0)")
    except OSError as e:
        print(f"[UDP DISCOVERY] Error binding to UDP port {DISCOVERY_PORT}: {e}. Is another program using it?")
        print(
            f"[UDP DISCOVERY] On Windows, check Task Manager or use 'netstat -ano' in cmd to find conflicting processes.")
        udp_socket.close()
        return

    while True:
        try:
            message, client_address = udp_socket.recvfrom(BUFFER_SIZE)
            message_str = message.decode().strip()
            print(f"[UDP DISCOVERY] Received discovery message: '{message_str}' from {client_address}")

            # Expected client discovery message format: "SPOTLIGHT_CLIENT_DISCOVERY:<pairing_id>"
            discovery_prefix = "SPOTLIGHT_CLIENT_DISCOVERY:"
            if message_str.startswith(discovery_prefix):
                client_pairing_id = message_str[len(discovery_prefix):]
                if client_pairing_id == SERVER_PAIRING_ID:
                    # If server_ip was determined as 0.0.0.0, the client will use the source IP of the UDP packet.
                    # Otherwise, use the determined server_ip.
                    ip_to_respond_with = server_ip if server_ip != "0.0.0.0" else client_address[0]
                    response = f"SPOTLIGHT_SERVER_RESPONSE:{ip_to_respond_with}:{COMMAND_PORT}:{SERVER_NAME}"
                    udp_socket.sendto(response.encode(), client_address)
                    print(f"[UDP DISCOVERY] Correct Pairing ID. Sent response to {client_address}: {response}")
                else:
                    print(
                        f"[UDP DISCOVERY] Incorrect Pairing ID from {client_address}. Expected '{SERVER_PAIRING_ID}', got '{client_pairing_id}'. Ignoring.")
            else:
                print(
                    f"[UDP DISCOVERY] Message from {client_address} not in expected format ('{discovery_prefix}...'). Ignoring.")

        except ConnectionResetError:  # client_address might not be fully established for UDP "connections"
            print(f"[UDP DISCOVERY] Connection reset error likely from {client_address} (UDP). Ignoring.")
        except Exception as e:
            print(f"[UDP DISCOVERY] Error in discovery loop: {e}")
            time.sleep(1)  # Prevent rapid looping on persistent error

    # This part will likely not be reached in normal operation as the loop above is infinite
    udp_socket.close()
    print("[UDP DISCOVERY] UDP Discovery Server stopped.")


if __name__ == "__main__":
    print("--- Logitech Spotlight Receiver Server (Runtime Pairing ID) ---")

    # --- Get Pairing ID from user input ---
    while not SERVER_PAIRING_ID:  # Loop until a non-empty ID is provided
        temp_id = input("Enter the custom Pairing ID for this server session (cannot be empty): ").strip()
        if temp_id:
            SERVER_PAIRING_ID = temp_id
        else:
            print("Pairing ID cannot be empty. Please try again.")

    print(f"IMPORTANT: SERVER PAIRING ID FOR THIS SESSION IS SET TO: '{SERVER_PAIRING_ID}'")
    print("The client application MUST be configured to use this exact Pairing ID.")
    print("This script listens for commands from the Spotlight Client and simulates key presses.")
    print(f"Ensure 'pyautogui' is installed: pip install pyautogui")
    print("\n--- Windows Specific Notes ---")
    print(f"1. Windows Firewall: You may be prompted to allow Python/this script network access.")
    print(f"   Ensure inbound rules are allowed for Python on UDP port {DISCOVERY_PORT} and TCP port {COMMAND_PORT}.")
    print(f"2. Administrator Privileges: If controlling certain applications (e.g., those running as admin),")
    print(f"   you might need to run this script as an Administrator for 'pyautogui' to function correctly.")
    print(
        f"   To do this, right-click your command prompt/PowerShell and select 'Run as administrator', then run the script.")
    print(f"3. Active Window: For commands like 'NEXT' or 'PREVIOUS' to work, the target application")
    print(f"   (e.g., PowerPoint slideshow) must be the active, focused window on this computer (Computer 2).")
    print(f"4. Network: Ensure Computer 1 (client) and Computer 2 (server) are on the SAME NETWORK.")
    print(
        f"5. If 'Address already in use' error persists, ensure no other instance of this server is running or wait a minute for the OS to release the port.")
    print("--- Starting Server ---")

    discovery_thread = threading.Thread(target=start_udp_discovery_server)
    discovery_thread.daemon = True
    discovery_thread.start()

    # Run TCP command server in the main thread
    # This will block until an error or the script is interrupted (e.g., Ctrl+C)
    start_tcp_server()

    print("Server shutting down.")

