# Combined Spotlight Server and Client Script
# Run this script and choose to operate in 'server' or 'client' mode.

import socket
import threading
import time

# --- PyAutoGUI is server-specific, import conditionally or handle if not present ---
try:
    import pyautogui
except ImportError:
    pyautogui = None  # Will be checked in server mode

# --- Pynput is client-specific, import conditionally or handle if not present ---
try:
    from pynput import keyboard
except ImportError:
    keyboard = None  # Will be checked in client mode

# --- Common Configuration ---
DISCOVERY_PORT = 50000
COMMAND_PORT = 50001  # Server listens on this, client gets it via discovery
BUFFER_SIZE = 1024
RETRY_DELAY = 2  # Client uses this

# --- Server Specific Globals & Config ---
SERVER_NAME = "SpotlightReceiverPC"
SERVER_PAIRING_ID_GLOBAL = ""  # Global for server's pairing ID
COMMAND_ACTIONS = {
    "NEXT": lambda: pyautogui.press('right') if pyautogui else print("[SERVER] PyAutoGUI not available"),
    "PREVIOUS": lambda: pyautogui.press('left') if pyautogui else print("[SERVER] PyAutoGUI not available"),
    "BLACK_SCREEN": lambda: pyautogui.press('b') if pyautogui else print("[SERVER] PyAutoGUI not available"),
    "START_PRESENTATION": lambda: pyautogui.press('f5') if pyautogui else print("[SERVER] PyAutoGUI not available"),
    "EXIT_SLIDESHOW": lambda: pyautogui.press('esc') if pyautogui else print("[SERVER] PyAutoGUI not available"),
    "LASER_ON": lambda: print("[SERVER] Laser ON command received (action not implemented)"),
    "LASER_OFF": lambda: print("[SERVER] Laser OFF command received (action not implemented)"),
}

# --- Client Specific Globals & Config ---
CLIENT_PAIRING_ID_GLOBAL = ""  # Global for client's pairing ID
DISCOVERY_TIMEOUT_CLIENT = 5  # Client specific
KEYS_TO_COMMANDS_CLIENT = {}  # Will be populated if keyboard is available
tcp_socket_client_global = None
keyboard_listener_client_global = None
client_running_flag = True


# --- Server Mode Functions ---

def handle_client_connection_for_server(conn, addr):
    """Handles an incoming TCP connection for the server."""
    # Uses SERVER_PAIRING_ID_GLOBAL
    print(f"[TCP SERVER] Accepted connection from {addr}")
    paired = False
    try:
        pairing_data = conn.recv(BUFFER_SIZE)
        if not pairing_data:
            print(f"[TCP SERVER] Connection closed by {addr} before pairing attempt.")
            return

        client_pairing_message = pairing_data.decode().strip()
        print(f"[TCP SERVER] Received pairing message: '{client_pairing_message}' from {addr}")

        expected_pairing_prefix = "PAIR_WITH_SERVER:"
        if client_pairing_message.startswith(expected_pairing_prefix):
            client_pairing_id = client_pairing_message[len(expected_pairing_prefix):]
            if client_pairing_id == SERVER_PAIRING_ID_GLOBAL:
                paired = True
                conn.sendall(f"ACK:PAIRING_SUCCESSFUL".encode())
                print(f"[TCP SERVER] Pairing successful with {addr}")
            else:
                conn.sendall(f"NACK:PAIRING_FAILED_MISMATCH".encode())
                print(
                    f"[TCP SERVER] Pairing failed with {addr}: ID mismatch. Expected '{SERVER_PAIRING_ID_GLOBAL}', got '{client_pairing_id}'.")
                return
        else:
            conn.sendall(f"NACK:PAIRING_FAILED_BAD_FORMAT".encode())
            print(f"[TCP SERVER] Pairing failed with {addr}: Bad pairing message format.")
            return

        if not paired:
            print(f"[TCP SERVER] Pairing not established with {addr}. Closing connection.")
            return

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
                    print(f"[TCP SERVER] Ensure PyAutoGUI is working and the target window is active.")
                    conn.sendall(f"NACK:{command} - Error: {e}".encode())
            else:
                print(f"[TCP SERVER] Unknown command: {command}")
                conn.sendall(f"NACK:Unknown command {command}".encode())
    except ConnectionResetError:
        print(f"[TCP SERVER] Connection reset by {addr}")
    except socket.timeout:
        print(f"[TCP SERVER] Socket timeout during communication with {addr}.")
    except Exception as e:
        print(f"[TCP SERVER] Error during TCP communication with {addr}: {e}")
    finally:
        conn.close()
        print(f"[TCP SERVER] Closed connection from {addr}")


def start_tcp_server_mode():
    """Starts the TCP server to listen for commands in server mode."""
    # Uses SERVER_PAIRING_ID_GLOBAL
    if not pyautogui:
        print(
            "[SERVER ERROR] PyAutoGUI library is not installed or failed to import. Server cannot simulate key presses.")
        return

    host_ip = '0.0.0.0'
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((host_ip, COMMAND_PORT))
        server_socket.listen(5)
        print(f"[TCP SERVER] Listening for commands on TCP port {COMMAND_PORT}")
        print(
            f"[TCP SERVER] Server Pairing ID for this session: '{SERVER_PAIRING_ID_GLOBAL}'. Clients must match this.")

        while True:
            conn, addr = server_socket.accept()
            client_thread = threading.Thread(target=handle_client_connection_for_server, args=(conn, addr))
            client_thread.daemon = True
            client_thread.start()
    except OSError as e:
        print(f"[TCP SERVER] Error binding to port {COMMAND_PORT}: {e}. Is another program using it?")
    except Exception as e:
        print(f"[TCP SERVER] An unexpected error occurred in TCP server: {e}")
    finally:
        server_socket.close()
        print("[TCP SERVER] TCP Server stopped.")


def start_udp_discovery_server_mode():
    """Starts the UDP server to listen for discovery broadcasts in server mode."""
    # Uses SERVER_PAIRING_ID_GLOBAL
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    server_ip_determined = "0.0.0.0"  # Default
    try:
        hostname = socket.gethostname()
        try:
            s_temp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s_temp.settimeout(1)
            s_temp.connect(("8.8.8.8", 80))
            server_ip_determined = s_temp.getsockname()[0]
            s_temp.close()
        except (OSError, socket.timeout):
            server_ip_determined = socket.gethostbyname(hostname)
            if server_ip_determined == "127.0.0.1":
                all_ips = socket.getaddrinfo(hostname, None, socket.AF_INET)
                for item in all_ips:
                    if not item[4][0].startswith("127."):
                        server_ip_determined = item[4][0]
                        break
    except socket.gaierror:
        server_ip_determined = "127.0.0.1"
        print("[UDP DISCOVERY] Warning: Could not determine reliable local IP. Responding with localhost.")
    except Exception as e:
        print(f"[UDP DISCOVERY] Error determining server IP: {e}. Will rely on client seeing UDP source IP.")

    try:
        udp_socket.bind(('', DISCOVERY_PORT))
        print(f"[UDP DISCOVERY] Listening for discovery broadcasts on UDP port {DISCOVERY_PORT}")
        print(f"[UDP DISCOVERY] Server Pairing ID: '{SERVER_PAIRING_ID_GLOBAL}'.")
        print(f"[UDP DISCOVERY] Server will respond with IP: {server_ip_determined}")
    except OSError as e:
        print(f"[UDP DISCOVERY] Error binding to UDP port {DISCOVERY_PORT}: {e}.")
        udp_socket.close()
        return

    while True:
        try:
            message, client_address = udp_socket.recvfrom(BUFFER_SIZE)
            message_str = message.decode().strip()
            print(f"[UDP DISCOVERY] Received discovery: '{message_str}' from {client_address}")

            discovery_prefix = "SPOTLIGHT_CLIENT_DISCOVERY:"
            if message_str.startswith(discovery_prefix):
                client_pairing_id = message_str[len(discovery_prefix):]
                if client_pairing_id == SERVER_PAIRING_ID_GLOBAL:
                    ip_to_respond = server_ip_determined if server_ip_determined != "0.0.0.0" else client_address[0]
                    response = f"SPOTLIGHT_SERVER_RESPONSE:{ip_to_respond}:{COMMAND_PORT}:{SERVER_NAME}"
                    udp_socket.sendto(response.encode(), client_address)
                    print(f"[UDP DISCOVERY] Correct Pairing ID. Sent response to {client_address}: {response}")
                else:
                    print(
                        f"[UDP DISCOVERY] Incorrect Pairing ID from {client_address}. Expected '{SERVER_PAIRING_ID_GLOBAL}', got '{client_pairing_id}'. Ignoring.")
            else:
                print(f"[UDP DISCOVERY] Message from {client_address} not in expected format. Ignoring.")
        except ConnectionResetError:
            print(f"[UDP DISCOVERY] Connection reset error (UDP) from {client_address}. Ignoring.")
        except Exception as e:
            print(f"[UDP DISCOVERY] Error in discovery loop: {e}")
            time.sleep(1)


# --- Client Mode Functions ---

def discover_server_for_client(pairing_id_to_use):
    """Attempts to discover the server in client mode."""
    print(f"\n[CLIENT UDP DISCOVERY] Attempting discovery with Pairing ID: {pairing_id_to_use}...")
    discover_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    discover_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    discover_socket.settimeout(DISCOVERY_TIMEOUT_CLIENT)

    discovery_message = f"SPOTLIGHT_CLIENT_DISCOVERY:{pairing_id_to_use}"
    server_details = None
    try:
        discover_socket.sendto(discovery_message.encode(), ('<broadcast>', DISCOVERY_PORT))
        print(f"[CLIENT UDP DISCOVERY] Sent: '{discovery_message}'")
        while True:
            try:
                data, addr = discover_socket.recvfrom(BUFFER_SIZE)
                response = data.decode().strip()
                print(f"[CLIENT UDP DISCOVERY] Received: '{response}' from {addr}")
                response_prefix = "SPOTLIGHT_SERVER_RESPONSE:"
                if response.startswith(response_prefix):
                    parts = response[len(response_prefix):].split(':')
                    if len(parts) == 3:
                        server_ip, port_str, name = parts
                        server_details = (server_ip, int(port_str), name)
                        print(f"[CLIENT UDP DISCOVERY] Server '{name}' found at {server_ip}:{port_str}")
                        break
            except socket.timeout:
                print(f"[CLIENT UDP DISCOVERY] No server responded.")
                break
    except Exception as e:
        print(f"[CLIENT UDP DISCOVERY] Error: {e}")
    finally:
        discover_socket.close()
    return server_details


def send_command_from_client(command):
    """Sends a command to the server in client mode."""
    global tcp_socket_client_global, client_running_flag, keyboard_listener_client_global
    if tcp_socket_client_global:
        try:
            print(f"[CLIENT KEY CAPTURE] Sending: {command}")
            tcp_socket_client_global.sendall(command.encode())
            tcp_socket_client_global.settimeout(5.0)
            response_data = tcp_socket_client_global.recv(BUFFER_SIZE)
            tcp_socket_client_global.settimeout(None)
            if not response_data:
                print("[CLIENT TCP] Server disconnected after command.")
                if keyboard_listener_client_global and keyboard_listener_client_global.is_alive():
                    keyboard_listener_client_global.stop()
                client_running_flag = False
                return False
            print(f"[CLIENT TCP] Server response: {response_data.decode().strip()}")
            return True
        except socket.timeout:
            print("[CLIENT TCP] Timeout waiting for server ACK/NACK.")
            return False
        except socket.error as e:
            print(f"[CLIENT TCP] Socket error sending '{command}': {e}")
            if keyboard_listener_client_global and keyboard_listener_client_global.is_alive():
                keyboard_listener_client_global.stop()
            client_running_flag = False
            return False
    return False


def on_press_for_client(key):
    """Callback for key presses in client mode."""
    # Uses KEYS_TO_COMMANDS_CLIENT
    command = KEYS_TO_COMMANDS_CLIENT.get(key)
    if command:
        send_command_from_client(command)


def connect_and_listen_as_client(server_ip, server_port, pairing_id_to_use):
    """Connects to server, pairs, and starts key listener in client mode."""
    global tcp_socket_client_global, keyboard_listener_client_global, client_running_flag
    client_running_flag = True
    tcp_socket_client_global = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        print(f"\n[CLIENT TCP] Connecting to server at {server_ip}:{server_port}...")
        tcp_socket_client_global.connect((server_ip, server_port))
        print(f"[CLIENT TCP] Connected.")

        tcp_pairing_msg = f"PAIR_WITH_SERVER:{pairing_id_to_use}"
        print(f"[CLIENT TCP] Sending pairing: '{tcp_pairing_msg}'")
        tcp_socket_client_global.sendall(tcp_pairing_msg.encode())
        tcp_socket_client_global.settimeout(10.0)
        pairing_response_data = tcp_socket_client_global.recv(BUFFER_SIZE)
        tcp_socket_client_global.settimeout(None)

        if not pairing_response_data:
            print("[CLIENT TCP] Server disconnected during pairing.")
            client_running_flag = False
            return

        pairing_response = pairing_response_data.decode().strip()
        print(f"[CLIENT TCP] Pairing response: '{pairing_response}'")

        if pairing_response == "ACK:PAIRING_SUCCESSFUL":
            print("[CLIENT TCP] Pairing successful!")
            print("\n--- CLIENT LISTENING FOR KEYS ---")
            print("Press mapped keys to send commands. To STOP: Ctrl+C or close terminal.")

            if keyboard_listener_client_global and keyboard_listener_client_global.is_alive():
                keyboard_listener_client_global.stop()
            keyboard_listener_client_global = keyboard.Listener(on_press=on_press_for_client)
            keyboard_listener_client_global.start()
            while client_running_flag and keyboard_listener_client_global.is_alive():
                time.sleep(0.1)
            print("[CLIENT TCP] Exited listening loop.")
        else:
            print(f"[CLIENT TCP] Pairing failed: {pairing_response}.")
            client_running_flag = False
    except socket.timeout:
        print(f"[CLIENT TCP] Timeout during pairing.")
        client_running_flag = False
    except socket.error as e:
        print(f"[CLIENT TCP] Socket error: {e}")
        client_running_flag = False
    finally:
        print("[CLIENT TCP] Cleaning up client session...")
        if keyboard_listener_client_global and keyboard_listener_client_global.is_alive():
            keyboard_listener_client_global.stop()
        if tcp_socket_client_global:
            tcp_socket_client_global.close()
        tcp_socket_client_global = None
        keyboard_listener_client_global = None


# --- Main Execution Logic ---
if __name__ == "__main__":
    print("--- Combined Spotlight Server & Client ---")

    selected_mode = ""
    while selected_mode not in ["server", "client"]:
        selected_mode = input("Run as 'server' or 'client'?: ").strip().lower()

    if selected_mode == "server":
        print("\n--- Starting in SERVER Mode ---")
        if not pyautogui:
            print(
                "[FATAL SERVER ERROR] PyAutoGUI library is required for server mode but not found. Please install it (`pip install pyautogui`) and try again.")
            exit()

        while not SERVER_PAIRING_ID_GLOBAL:
            temp_id = input("Enter Pairing ID for this server session (cannot be empty): ").strip()
            if temp_id:
                SERVER_PAIRING_ID_GLOBAL = temp_id
            else:
                print("Pairing ID cannot be empty.")
        print(f"Server Pairing ID set to: '{SERVER_PAIRING_ID_GLOBAL}'")
        print("Ensure client uses this exact ID.")
        print("Server will simulate key presses based on received commands.")
        print("To stop server: Ctrl+C in this terminal.")

        # Start UDP discovery in a separate thread
        discovery_thread = threading.Thread(target=start_udp_discovery_server_mode)
        discovery_thread.daemon = True
        discovery_thread.start()

        # Start TCP command server in the main thread (blocks here)
        start_tcp_server_mode()
        print("Server mode has shut down.")

    elif selected_mode == "client":
        print("\n--- Starting in CLIENT Mode ---")
        print(
            "IMPORTANT: Ensure your presentation remote (e.g., Logitech Spotlight) is connected to THIS computer.")  # ADDED THIS LINE
        if not keyboard:
            print(
                "[FATAL CLIENT ERROR] Pynput library is required for client mode but not found. Please install it (`pip install pynput`) and try again.")
            exit()

        # Populate client key mappings now that we know pynput.keyboard is available
        KEYS_TO_COMMANDS_CLIENT = {
            keyboard.Key.right: "NEXT",
            keyboard.Key.left: "PREVIOUS",
            keyboard.Key.f5: "START_PRESENTATION",
            keyboard.KeyCode.from_char('b'): "BLACK_SCREEN",
            keyboard.KeyCode.from_char('B'): "BLACK_SCREEN",
            keyboard.Key.esc: "EXIT_SLIDESHOW",
        }

        while not CLIENT_PAIRING_ID_GLOBAL:
            temp_id = input("Enter Pairing ID to connect to server (must match server's, cannot be empty): ").strip()
            if temp_id:
                CLIENT_PAIRING_ID_GLOBAL = temp_id
            else:
                print("Pairing ID cannot be empty.")
        print(f"Client will use Pairing ID: '{CLIENT_PAIRING_ID_GLOBAL}'")
        print(
            "Client will capture key presses from the connected remote and send commands to the server.")  # Slightly rephrased
        print("To stop client: Ctrl+C in this terminal.")

        # Main client loop
        while client_running_flag:
            server_info = discover_server_for_client(CLIENT_PAIRING_ID_GLOBAL)
            if server_info:
                ip, port, name = server_info
                connect_and_listen_as_client(ip, port, CLIENT_PAIRING_ID_GLOBAL)

                if not client_running_flag:  # If connect_and_listen set it to False (e.g. error)
                    retry_choice = input(
                        "Session ended or error. Attempt new discovery & connection? (y/n): ").strip().lower()
                    if retry_choice == 'y':
                        client_running_flag = True  # Reset for new attempt
                        CLIENT_PAIRING_ID_GLOBAL = ""  # Prompt for new pairing ID for a fresh session
                        while not CLIENT_PAIRING_ID_GLOBAL:
                            temp_id = input("Enter Pairing ID for new session: ").strip()
                            if temp_id:
                                CLIENT_PAIRING_ID_GLOBAL = temp_id
                            else:
                                print("Pairing ID cannot be empty.")
                        print(f"Using new Pairing ID: '{CLIENT_PAIRING_ID_GLOBAL}'")
                    else:
                        break  # Exit main client loop
            else:  # Server not found
                print("Server not found with current Pairing ID.")

            if client_running_flag:  # If still running (no critical error, or user chose to retry current ID)
                retry_choice = input(
                    f"Retry discovery with Pairing ID '{CLIENT_PAIRING_ID_GLOBAL}'? (y/n): ").strip().lower()
                if retry_choice != 'y':
                    break  # Exit main client loop
                print(f"Waiting {RETRY_DELAY} seconds before retrying...")
                time.sleep(RETRY_DELAY)
        print("Client mode has shut down.")

    else:
        print("Invalid mode selected. Exiting.")
