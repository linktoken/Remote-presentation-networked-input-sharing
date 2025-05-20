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

# --- Key Mappings ---
# These are the commands the server expects and the corresponding pyautogui actions.
# On Windows, for pyautogui to control an application (e.g., PowerPoint),
# that application's window typically needs to be active and in the foreground.
# If commands don't seem to work, ensure the target application window is selected.
# In some cases, if controlling privileged applications, this script might
# need to be run with Administrator privileges on Windows.
COMMAND_ACTIONS = {
    "NEXT": lambda: pyautogui.press('right'),         # MODIFIED: Was 'pagedown'
    "PREVIOUS": lambda: pyautogui.press('left'),       # MODIFIED: Was 'pageup'
    "BLACK_SCREEN": lambda: pyautogui.press('b'),      # 'b' key often toggles black screen in presentations
    "START_PRESENTATION": lambda: pyautogui.press('f5'), # F5 often starts slideshows
    "LASER_ON": lambda: print("Server: Laser ON command received (action not implemented)"),  # Placeholder
    "LASER_OFF": lambda: print("Server: Laser OFF command received (action not implemented)"), # Placeholder
    # Add more commands if your clicker has them, e.g., volume controls
}


def handle_client_connection(conn, addr):
    """Handles an incoming TCP connection from a client."""
    print(f"[TCP SERVER] Accepted connection from {addr}")
    try:
        while True:
            data = conn.recv(BUFFER_SIZE)
            if not data:
                print(f"[TCP SERVER] Connection closed by {addr}")
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
                    # On Windows, pyautogui actions can sometimes fail due to permissions
                    # or the target window not being active.
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
    except Exception as e:
        print(f"[TCP SERVER] Error during TCP communication with {addr}: {e}")
    finally:
        conn.close()
        print(f"[TCP SERVER] Closed connection from {addr}")


def start_tcp_server():
    """Starts the TCP server to listen for commands."""
    host_ip = '0.0.0.0'  # Listen on all available network interfaces

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server_socket.bind((host_ip, COMMAND_PORT))
        server_socket.listen(5)  # Allow up to 5 queued connections
        print(f"[TCP SERVER] Listening for commands on TCP port {COMMAND_PORT}")

        while True:
            conn, addr = server_socket.accept()
            client_thread = threading.Thread(target=handle_client_connection, args=(conn, addr))
            client_thread.daemon = True
            client_thread.start()
    except OSError as e:
        print(
            f"[TCP SERVER] Error binding to port {COMMAND_PORT}: {e}. Is another program (or this script already) using it?")
        print(f"[TCP SERVER] On Windows, check Task Manager for conflicting processes or try a different port.")
    except Exception as e:
        print(f"[TCP SERVER] An unexpected error occurred in TCP server: {e}")
    finally:
        server_socket.close()
        print("[TCP SERVER] TCP Server stopped.")


def start_udp_discovery_server():
    """Starts the UDP server to listen for discovery broadcasts."""
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    try:
        hostname = socket.gethostname()
        # This gets one of the machine's IP addresses. Ensure it's the one on the same LAN as the client.
        server_ip = socket.gethostbyname(hostname)
    except socket.gaierror:
        server_ip = "127.0.0.1"
        print("[UDP DISCOVERY] Warning: Could not determine local IP via hostname. Responding with localhost.")
        print("[UDP DISCOVERY] Client might not be able to connect if it's on a different machine.")

    try:
        udp_socket.bind(('', DISCOVERY_PORT))
        print(f"[UDP DISCOVERY] Listening for discovery broadcasts on UDP port {DISCOVERY_PORT}")
        print(f"[UDP DISCOVERY] Server will respond with IP: {server_ip} (ensure this is reachable by client)")
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

            if message_str == "SPOTLIGHT_CLIENT_DISCOVERY":
                response = f"SPOTLIGHT_SERVER_RESPONSE:{server_ip}:{COMMAND_PORT}:{SERVER_NAME}"
                udp_socket.sendto(response.encode(), client_address)
                print(f"[UDP DISCOVERY] Sent response to {client_address}: {response}")
        except ConnectionResetError: # client_address might not be fully established for UDP "connections"
            print(f"[UDP DISCOVERY] Connection reset error likely from {client_address} (UDP). Ignoring.")
        except Exception as e:
            print(f"[UDP DISCOVERY] Error in discovery loop: {e}")
            time.sleep(1) # Prevent rapid looping on persistent error

    # This part will likely not be reached in normal operation as the loop above is infinite
    udp_socket.close()
    print("[UDP DISCOVERY] UDP Discovery Server stopped.")


if __name__ == "__main__":
    print("--- Logitech Spotlight Receiver Server (Windows Enhanced) ---")
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
    print("--- Starting Server ---")

    discovery_thread = threading.Thread(target=start_udp_discovery_server)
    discovery_thread.daemon = True # Allows main program to exit even if this thread is running
    discovery_thread.start()

    # Run TCP command server in the main thread
    # This will block until an error or the script is interrupted
    start_tcp_server()

    print("Server shutting down.")