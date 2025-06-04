# spotlight_client.py
# Run this script on Computer 1 (the control machine)
# Now with direct key capture for presenter controls!

import socket
import time
import threading  # For handling listener in a way that allows main thread to manage connection
from pynput import keyboard  # For capturing key presses

# --- Configuration ---
DISCOVERY_PORT = 50000
BUFFER_SIZE = 1024
DISCOVERY_TIMEOUT = 5
RETRY_DELAY = 2

# --- Client Specific ---
CLIENT_PAIRING_ID = ""  # Will be set from user input

# --- Key Mappings (from user) ---
# Map specific keys to commands to be sent to the server.
KEYS_TO_COMMANDS = {
    keyboard.Key.right: "NEXT",
    keyboard.Key.left: "PREVIOUS",
    keyboard.Key.f5: "START_PRESENTATION",
    keyboard.KeyCode.from_char('b'): "BLACK_SCREEN",
    keyboard.KeyCode.from_char('B'): "BLACK_SCREEN",  # Case-insensitive for 'b'
    # Add more mappings here if your Spotlight has other buttons/keys
    # e.g., if a button sends 'g', and you want to map it:
    # keyboard.KeyCode.from_char('g'): "LASER_ON",
}

# Global variable to hold the active TCP socket and listener
tcp_socket_global = None
keyboard_listener_global = None
client_running = True  # Flag to control the main loop and listener


def discover_server(pairing_id_to_use):
    """
    Attempts to discover the Spotlight server on the network using UDP broadcast.
    """
    print(f"\n[UDP DISCOVERY] Attempting to discover server with Pairing ID: {pairing_id_to_use}...")
    print(f"[UDP DISCOVERY] Broadcasting on port {DISCOVERY_PORT} for {DISCOVERY_TIMEOUT} seconds...")

    discover_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    discover_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    discover_socket.settimeout(DISCOVERY_TIMEOUT)

    discovery_message = f"SPOTLIGHT_CLIENT_DISCOVERY:{pairing_id_to_use}"
    server_details = None

    try:
        discover_socket.sendto(discovery_message.encode(), ('<broadcast>', DISCOVERY_PORT))
        print(f"[UDP DISCOVERY] Sent: '{discovery_message}'")

        while True:
            try:
                data, addr = discover_socket.recvfrom(BUFFER_SIZE)
                response = data.decode().strip()
                print(f"[UDP DISCOVERY] Received response: '{response}' from {addr}")

                response_prefix = "SPOTLIGHT_SERVER_RESPONSE:"
                if response.startswith(response_prefix):
                    parts = response[len(response_prefix):].split(':')
                    if len(parts) == 3:
                        server_ip, command_port_str, server_name = parts
                        try:
                            command_port = int(command_port_str)
                            print(f"[UDP DISCOVERY] Server '{server_name}' found at {server_ip}:{command_port}")
                            server_details = (server_ip, command_port, server_name)
                            break
                        except ValueError:
                            print(f"[UDP DISCOVERY] Invalid port in response: {command_port_str}")
                    else:
                        print(f"[UDP DISCOVERY] Malformed server response: {response}")
                else:
                    print(f"[UDP DISCOVERY] Unknown response format: {response}")
            except socket.timeout:
                print(f"[UDP DISCOVERY] No server responded within the timeout period.")
                break
            except Exception as e:
                print(f"[UDP DISCOVERY] Error receiving discovery response: {e}")
                break
    except Exception as e:
        print(f"[UDP DISCOVERY] Error during discovery broadcast: {e}")
    finally:
        discover_socket.close()
        print("[UDP DISCOVERY] Discovery socket closed.")
    return server_details


def send_command_to_server(command):
    """Sends a command to the globally connected server if available."""
    global tcp_socket_global
    if tcp_socket_global:
        try:
            print(f"[KEY CAPTURE] Sending command: {command}")
            tcp_socket_global.sendall(command.encode())
            # Wait for ACK/NACK
            # Set a timeout for receiving command responses
            tcp_socket_global.settimeout(5.0)  # 5 seconds timeout
            response_data = tcp_socket_global.recv(BUFFER_SIZE)
            tcp_socket_global.settimeout(None)  # Reset timeout
            if not response_data:
                print("[TCP CLIENT] Server closed connection unexpectedly after command.")
                # Potentially try to reconnect or signal main thread to stop
                return False
            response = response_data.decode().strip()
            print(f"[TCP CLIENT] Server response: {response}")
            return True
        except socket.timeout:
            print("[TCP CLIENT] Timeout waiting for server response to command.")
            return False
        except socket.error as e:
            print(f"[TCP CLIENT] Socket error sending command '{command}': {e}")
            # Consider this a connection failure, might need to stop listener
            global client_running, keyboard_listener_global
            if keyboard_listener_global:
                print("[KEY CAPTURE] Stopping listener due to socket error.")
                keyboard_listener_global.stop()
            client_running = False  # Signal main loop to exit
            return False
        except Exception as e:
            print(f"[TCP CLIENT] Error sending/receiving for command '{command}': {e}")
            return False
    else:
        print("[KEY CAPTURE] No active server connection to send command.")
        return False


def on_press(key):
    """Callback function for when a key is pressed."""
    global keyboard_listener_global, client_running

    # --- Check for Exit Key (ESC) ---
    if key == keyboard.Key.esc:
        print("[KEY CAPTURE] Escape key pressed. Stopping listener and client...")
        if keyboard_listener_global:
            keyboard_listener_global.stop()  # Stop the pynput listener
        client_running = False  # Signal main loop to exit
        return False  # Stop listener callback chain

    # --- Check for Mapped Presentation Keys ---
    command = KEYS_TO_COMMANDS.get(key)
    if command:
        if not send_command_to_server(command):
            # If sending command failed critically, on_press might be called again
            # before client_running is processed by the main loop.
            # The socket error handling in send_command_to_server should stop the listener.
            pass  # Error already printed by send_command_to_server
    # else:
    # print(f"Key pressed: {key} (not mapped to a command)") # Optional: for debugging unmapped keys


def connect_and_listen(server_ip, command_port, pairing_id_to_use):
    """
    Connects to the server, performs pairing, and starts listening for key presses.
    """
    global tcp_socket_global, keyboard_listener_global, client_running
    client_running = True  # Reset flag for new session

    tcp_socket_global = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        print(f"\n[TCP CLIENT] Attempting to connect to server at {server_ip}:{command_port}...")
        tcp_socket_global.connect((server_ip, command_port))
        print(f"[TCP CLIENT] Connected to server.")

        # --- Perform TCP Pairing ---
        tcp_pairing_message = f"PAIR_WITH_SERVER:{pairing_id_to_use}"
        print(f"[TCP CLIENT] Sending TCP pairing message: '{tcp_pairing_message}'")
        tcp_socket_global.sendall(tcp_pairing_message.encode())

        pairing_response_data = tcp_socket_global.recv(BUFFER_SIZE)
        if not pairing_response_data:
            print("[TCP CLIENT] Server closed connection during TCP pairing.")
            return

        pairing_response = pairing_response_data.decode().strip()
        print(f"[TCP CLIENT] Received pairing response: '{pairing_response}'")

        if pairing_response == "ACK:PAIRING_SUCCESSFUL":
            print("[TCP CLIENT] TCP Pairing successful with server!")
            print("\n--- Listening for Presentation Key Presses ---")
            print("Press mapped keys (e.g., Right Arrow for NEXT, Left Arrow for PREVIOUS).")
            print("Press 'ESC' to disconnect and stop the client.")

            # Setup and start the keyboard listener
            # Using non-daemon thread for listener.join() to work as expected if needed,
            # but listener.start() and then checking client_running in a loop is often cleaner.
            keyboard_listener_global = keyboard.Listener(on_press=on_press)
            keyboard_listener_global.start()

            # Keep the main thread alive while the listener is running and client is active
            # The listener runs in its own thread(s).
            while client_running and keyboard_listener_global.is_alive():
                time.sleep(0.1)  # Keep main thread responsive

            print("[TCP CLIENT] Listener stopped or client signalled to exit.")

        else:
            print(f"[TCP CLIENT] TCP Pairing failed: {pairing_response}. Aborting.")
            return

    except socket.error as e:
        print(f"[TCP CLIENT] Socket error during connection/pairing: {e}")
    except Exception as e:
        print(f"[TCP CLIENT] An unexpected error occurred: {e}")
    finally:
        print("[TCP CLIENT] Cleaning up session...")
        if keyboard_listener_global and keyboard_listener_global.is_alive():
            print("[TCP CLIENT] Ensuring listener is stopped.")
            keyboard_listener_global.stop()
            # keyboard_listener_global.join() # Wait for listener thread to finish
        if tcp_socket_global:
            print("[TCP CLIENT] Closing TCP connection.")
            tcp_socket_global.close()
            tcp_socket_global = None  # Clear global
        keyboard_listener_global = None  # Clear global


if __name__ == "__main__":
    print("--- Logitech Spotlight Client (with Key Capture) ---")
    print("IMPORTANT: Ensure 'pynput' is installed: pip install pynput")

    while not CLIENT_PAIRING_ID:
        temp_id = input("Enter the Pairing ID for this session (must match server's ID, cannot be empty): ").strip()
        if temp_id:
            CLIENT_PAIRING_ID = temp_id
        else:
            print("Pairing ID cannot be empty. Please try again.")
    print(f"Using Pairing ID for this session: '{CLIENT_PAIRING_ID}'")

    # Main application loop
    while client_running:  # This loop allows for restarting sessions after ESC
        server_info = discover_server(CLIENT_PAIRING_ID)

        if server_info:
            ip, port, name = server_info
            connect_and_listen(ip, port, CLIENT_PAIRING_ID)  # This function now blocks until ESC or error

            if not client_running:  # If ESC was pressed or critical error
                print("\nClient has been stopped.")
                break  # Exit main application loop
            else:  # This case might not be reached if connect_and_listen handles its loop fully
                print("\nSession ended. Listener stopped.")
        else:
            print("Could not find a server or discovery failed with the current Pairing ID.")

        if client_running:  # Only ask to retry if not explicitly stopped by ESC
            retry_choice = input("Try to discover and connect again? (y/n): ").strip().lower()
            if retry_choice != 'y':
                print("Exiting client.")
                break
            print(f"Waiting {RETRY_DELAY} seconds before retrying...")
            time.sleep(RETRY_DELAY)
        else:
            print("Exiting client program.")
