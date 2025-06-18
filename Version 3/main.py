# Combined Spotlight Server and Client Script (REVERSED LOGIC)
# Version 3.1 - Bug Fix for repeated key sends
# Server now captures keys and sends commands.
# Client now receives commands and simulates key presses.

import socket
import threading
import time

# --- Pynput is now server-specific ---
try:
    from pynput import keyboard
except ImportError:
    keyboard = None  # Will be checked in server mode

# --- PyAutoGUI is now client-specific ---
try:
    import pyautogui
except ImportError:
    pyautogui = None  # Will be checked in client mode

# --- Common Configuration ---
DISCOVERY_PORT = 50000
COMMAND_PORT = 50001
BUFFER_SIZE = 1024
RETRY_DELAY = 2

# --- Server Specific Globals & Config ---
SERVER_NAME = "SpotlightSenderPC"
SERVER_PAIRING_ID_GLOBAL = ""
PAIRED_CLIENTS = []
PAIRED_CLIENTS_LOCK = threading.Lock()
KEYS_TO_COMMANDS_SERVER = {}
PRESSED_KEYS = set()  # NEW: To track currently held-down keys and prevent repeats

# --- Client Specific Globals & Config ---
CLIENT_PAIRING_ID_GLOBAL = ""
DISCOVERY_TIMEOUT_CLIENT = 5
COMMAND_ACTIONS_CLIENT = {}
client_running_flag = True


# --- Server Mode Functions ---

def broadcast_command_to_clients(command):
    """Sends a command to all paired clients."""
    with PAIRED_CLIENTS_LOCK:
        if not PAIRED_CLIENTS:
            print(f"[SERVER KEY CAPTURE] No paired clients to send '{command}' to.")
            return

        print(f"[SERVER KEY CAPTURE] Sending '{command}' to {len(PAIRED_CLIENTS)} client(s).")
        for client_conn in list(PAIRED_CLIENTS):
            try:
                client_conn.sendall(command.encode())
            except socket.error as e:
                print(f"[SERVER KEY CAPTURE] Error sending to client: {e}. Removing client.")
                client_conn.close()
                PAIRED_CLIENTS.remove(client_conn)


# MODIFIED: on_press now checks for key repeats
def on_press_for_server(key):
    """Callback for initial key presses, ignoring repeats."""
    # If the key is already in our set of pressed keys, it's a repeat. Ignore it.
    if key in PRESSED_KEYS:
        return

    # This is a new press. Add it to the set and process the command.
    PRESSED_KEYS.add(key)

    command = KEYS_TO_COMMANDS_SERVER.get(key)
    if command:
        broadcast_command_to_clients(command)


# NEW: Callback for key releases
def on_release_for_server(key):
    """Callback for key releases to reset its state."""
    try:
        PRESSED_KEYS.remove(key)
    except KeyError:
        # Key was not in the set, which is fine.
        pass


# MODIFIED: The listener now uses both on_press and on_release
def start_keyboard_listener_for_server():
    """Starts the pynput keyboard listener in a thread."""
    if not keyboard:
        return

    print("\n[SERVER KEY CAPTURE] Starting keyboard listener...")
    print("Press mapped keys on this server to send commands to client(s).")

    listener = keyboard.Listener(
        on_press=on_press_for_server,
        on_release=on_release_for_server
    )
    listener.start()
    listener.join()


def handle_client_connection_for_server(conn, addr):
    """Handles an incoming client connection, pairing, and listens for disconnect."""
    global PAIRED_CLIENTS, PAIRED_CLIENTS_LOCK
    print(f"[TCP SERVER] Accepted connection from {addr}")
    paired = False
    try:
        # --- Pairing Process (unchanged) ---
        pairing_data = conn.recv(BUFFER_SIZE)
        if not pairing_data:
            print(f"[TCP SERVER] Connection closed by {addr} before pairing attempt.")
            return

        client_pairing_message = pairing_data.decode().strip()
        expected_prefix = "PAIR_WITH_SERVER:"
        if client_pairing_message.startswith(expected_prefix):
            client_pairing_id = client_pairing_message[len(expected_prefix):]
            if client_pairing_id == SERVER_PAIRING_ID_GLOBAL:
                paired = True
                conn.sendall(b"ACK:PAIRING_SUCCESSFUL")
                print(f"[TCP SERVER] Pairing successful with {addr}")
                with PAIRED_CLIENTS_LOCK:
                    PAIRED_CLIENTS.append(conn)
            else:
                conn.sendall(b"NACK:PAIRING_FAILED_MISMATCH")
                print(f"[TCP SERVER] Pairing failed with {addr}: ID mismatch.")
                return
        else:
            conn.sendall(b"NACK:PAIRING_FAILED_BAD_FORMAT")
            print(f"[TCP SERVER] Pairing failed with {addr}: Bad format.")
            return

        # --- Wait for Disconnect (unchanged) ---
        if paired:
            print(f"[TCP SERVER] Client {addr} is now paired.")
            while True:
                data = conn.recv(BUFFER_SIZE)
                if not data:
                    print(f"[TCP SERVER] Client {addr} disconnected.")
                    break
    except ConnectionResetError:
        print(f"[TCP SERVER] Connection reset by {addr}")
    except Exception as e:
        print(f"[TCP SERVER] Error with client {addr}: {e}")
    finally:
        # --- Cleanup (unchanged) ---
        with PAIRED_CLIENTS_LOCK:
            if conn in PAIRED_CLIENTS:
                PAIRED_CLIENTS.remove(conn)
        conn.close()
        print(f"[TCP SERVER] Closed connection and cleaned up for {addr}")


# --- All other functions (start_tcp_server_mode, start_udp_discovery_server_mode, and all client-side functions) remain exactly the same. ---
def start_tcp_server_mode():
    if not keyboard:
        print("[FATAL SERVER ERROR] Pynput library is not installed. Server cannot capture key presses.")
        return
    host_ip = '0.0.0.0'
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((host_ip, COMMAND_PORT))
        server_socket.listen(5)
        print(f"[TCP SERVER] Listening for client connections on TCP port {COMMAND_PORT}")
        while True:
            conn, addr = server_socket.accept()
            client_thread = threading.Thread(target=handle_client_connection_for_server, args=(conn, addr))
            client_thread.daemon = True
            client_thread.start()
    except Exception as e:
        print(f"[TCP SERVER] An unexpected error occurred: {e}")
    finally:
        server_socket.close()
        print("[TCP SERVER] TCP Server stopped.")


def start_udp_discovery_server_mode():
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_ip_determined = "0.0.0.0"
    try:
        hostname = socket.gethostname()
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s_temp:
                s_temp.settimeout(1)
                s_temp.connect(("8.8.8.8", 80))
                server_ip_determined = s_temp.getsockname()[0]
        except (OSError, socket.timeout):
            server_ip_determined = socket.gethostbyname(hostname)
    except Exception:
        server_ip_determined = "127.0.0.1"
    try:
        udp_socket.bind(('', DISCOVERY_PORT))
        print(f"[UDP DISCOVERY] Listening for discovery broadcasts on UDP port {DISCOVERY_PORT}")
        while True:
            message, client_address = udp_socket.recvfrom(BUFFER_SIZE)
            message_str = message.decode().strip()
            discovery_prefix = "SPOTLIGHT_CLIENT_DISCOVERY:"
            if message_str.startswith(discovery_prefix):
                client_pairing_id = message_str[len(discovery_prefix):]
                if client_pairing_id == SERVER_PAIRING_ID_GLOBAL:
                    response = f"SPOTLIGHT_SERVER_RESPONSE:{server_ip_determined}:{COMMAND_PORT}:{SERVER_NAME}"
                    udp_socket.sendto(response.encode(), client_address)
                    print(f"[UDP DISCOVERY] Correct Pairing ID. Sent response to {client_address}")
                else:
                    print(f"[UDP DISCOVERY] Incorrect Pairing ID from {client_address}. Ignoring.")
    except Exception as e:
        print(f"[UDP DISCOVERY] Error in discovery loop: {e}")
    finally:
        udp_socket.close()


def discover_server_for_client(pairing_id_to_use):
    print(f"\n[CLIENT UDP DISCOVERY] Attempting discovery with Pairing ID: {pairing_id_to_use}...")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as discover_socket:
        discover_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        discover_socket.settimeout(DISCOVERY_TIMEOUT_CLIENT)
        discovery_message = f"SPOTLIGHT_CLIENT_DISCOVERY:{pairing_id_to_use}"
        server_details = None
        try:
            discover_socket.sendto(discovery_message.encode(), ('<broadcast>', DISCOVERY_PORT))
            while True:
                try:
                    data, addr = discover_socket.recvfrom(BUFFER_SIZE)
                    response = data.decode().strip()
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
        return server_details


def connect_and_listen_as_client(server_ip, server_port, pairing_id_to_use):
    global client_running_flag
    client_running_flag = True
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_socket:
        try:
            print(f"\n[CLIENT TCP] Connecting to server at {server_ip}:{server_port}...")
            tcp_socket.connect((server_ip, server_port))
            print("[CLIENT TCP] Connected.")
            tcp_pairing_msg = f"PAIR_WITH_SERVER:{pairing_id_to_use}"
            tcp_socket.sendall(tcp_pairing_msg.encode())
            tcp_socket.settimeout(10.0)
            pairing_response = tcp_socket.recv(BUFFER_SIZE).decode().strip()
            tcp_socket.settimeout(None)
            if pairing_response != "ACK:PAIRING_SUCCESSFUL":
                print(f"[CLIENT TCP] Pairing failed: {pairing_response}.")
                client_running_flag = False
                return
            print("[CLIENT TCP] Pairing successful! Now listening for commands from the server.")
            print("--- CLIENT NOW EXECUTING COMMANDS ---")
            while True:
                data = tcp_socket.recv(BUFFER_SIZE)
                if not data:
                    print("[CLIENT TCP] Server disconnected.")
                    client_running_flag = False
                    break
                command = data.decode().strip()
                print(f"[CLIENT TCP] Received command: {command}")
                action = COMMAND_ACTIONS_CLIENT.get(command)
                if action:
                    try:
                        action()
                        print(f"[CLIENT TCP] Executed: {command}")
                    except Exception as e:
                        print(f"[CLIENT TCP] Error executing command {command}: {e}")
                else:
                    print(f"[CLIENT TCP] Unknown command: {command}")
        except socket.timeout:
            print("[CLIENT TCP] Timeout during connection or pairing.")
            client_running_flag = False
        except socket.error as e:
            print(f"[CLIENT TCP] Socket error: {e}")
            client_running_flag = False
        except Exception as e:
            print(f"[CLIENT TCP] An unexpected error occurred: {e}")
            client_running_flag = False
        finally:
            print("[CLIENT TCP] Client session ended.")


if __name__ == "__main__":
    print("--- Combined Spotlight Server & Client (REVERSED LOGIC) ---")
    print("--- Version 3.1 ---")

    selected_mode = ""
    while selected_mode not in ["server", "client"]:
        selected_mode = input("Run as 'server' (captures keys) or 'client' (runs presentation)?: ").strip().lower()

    if selected_mode == "server":
        print("\n--- Starting in SERVER Mode ---")
        print("IMPORTANT: Ensure your presentation remote is connected to THIS computer.")
        if not keyboard:
            print(
                "[FATAL SERVER ERROR] Pynput library is required for server mode. Please install it (`pip install pynput`).")
            exit()
        KEYS_TO_COMMANDS_SERVER = {
            keyboard.Key.right: "NEXT",
            keyboard.Key.left: "PREVIOUS",
            keyboard.Key.f5: "START_PRESENTATION",
            keyboard.KeyCode.from_char('b'): "BLACK_SCREEN",
            keyboard.KeyCode.from_char('B'): "BLACK_SCREEN",
            keyboard.Key.esc: "EXIT_SLIDESHOW",
        }
        while not SERVER_PAIRING_ID_GLOBAL:
            temp_id = input("Enter Pairing ID for this server session: ").strip()
            if temp_id: SERVER_PAIRING_ID_GLOBAL = temp_id
        print(f"Server will use Pairing ID: '{SERVER_PAIRING_ID_GLOBAL}'")
        print("To stop server: Ctrl+C in this terminal.")
        discovery_thread = threading.Thread(target=start_udp_discovery_server_mode, daemon=True)
        discovery_thread.start()
        keyboard_thread = threading.Thread(target=start_keyboard_listener_for_server, daemon=True)
        keyboard_thread.start()
        start_tcp_server_mode()
        print("Server mode has shut down.")

    elif selected_mode == "client":
        print("\n--- Starting in CLIENT Mode ---")
        print("IMPORTANT: Ensure your presentation software (e.g., PowerPoint) is running on THIS computer.")
        if not pyautogui:
            print(
                "[FATAL CLIENT ERROR] PyAutoGUI library is required for client mode. Please install it (`pip install pyautogui`).")
            exit()
        COMMAND_ACTIONS_CLIENT = {
            "NEXT": lambda: pyautogui.press('right'),
            "PREVIOUS": lambda: pyautogui.press('left'),
            "BLACK_SCREEN": lambda: pyautogui.press('b'),
            "START_PRESENTATION": lambda: pyautogui.press('f5'),
            "EXIT_SLIDESHOW": lambda: pyautogui.press('esc'),
        }
        while not CLIENT_PAIRING_ID_GLOBAL:
            temp_id = input("Enter Pairing ID to connect to server: ").strip()
            if temp_id: CLIENT_PAIRING_ID_GLOBAL = temp_id
        while True:
            server_info = discover_server_for_client(CLIENT_PAIRING_ID_GLOBAL)
            if server_info:
                ip, port, name = server_info
                connect_and_listen_as_client(ip, port, CLIENT_PAIRING_ID_GLOBAL)
            else:
                print("Server not found with current Pairing ID.")
            retry_choice = input(f"Retry discovery and connection? (y/n): ").strip().lower()
            if retry_choice != 'y':
                break
            print(f"Waiting {RETRY_DELAY} seconds before retrying...")
            time.sleep(RETRY_DELAY)
        print("Client mode has shut down.")

    else:
        print("Invalid mode selected. Exiting.")