# spotlight_client.py
# Run this script on Computer 1 (the control machine)
# Now with direct key capture for presenter controls!
# ESC key no longer exits this client script. It can be mapped to a command.

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
    # To make ESC key send a command to exit slideshow on the server:
    # 1. Uncomment the line below (or add it).
    # 2. Ensure your server's COMMAND_ACTIONS has "EXIT_SLIDESHOW": lambda: pyautogui.press('esc')
    keyboard.Key.esc: "EXIT_SLIDESHOW",  # Example: Map ESC to send "EXIT_SLIDESHOW"
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

        while True:  # Keep listening until timeout or valid response
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
                            break  # Found a valid server
                        except ValueError:
                            print(f"[UDP DISCOVERY] Invalid port in response: {command_port_str}")
                    else:
                        print(f"[UDP DISCOVERY] Malformed server response: {response}")
                else:
                    print(f"[UDP DISCOVERY] Unknown response format: {response}")
            except socket.timeout:
                print(f"[UDP DISCOVERY] No server responded within the timeout period.")
                break  # Exit while loop on timeout
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
    global tcp_socket_global, client_running, keyboard_listener_global
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
                if keyboard_listener_global and keyboard_listener_global.is_alive():  # Attempt to stop listener
                    print("[KEY CAPTURE] Stopping listener due to server disconnect.")
                    keyboard_listener_global.stop()
                client_running = False  # Signal main loop to exit
                return False
            response = response_data.decode().strip()
            print(f"[TCP CLIENT] Server response: {response}")
            return True
        except socket.timeout:
            print("[TCP CLIENT] Timeout waiting for server response to command.")
            return False  # Command likely not received or acknowledged
        except socket.error as e:  # Covers ConnectionResetError, BrokenPipeError, etc.
            print(f"[TCP CLIENT] Socket error sending/receiving for command '{command}': {e}")
            if keyboard_listener_global and keyboard_listener_global.is_alive():
                print("[KEY CAPTURE] Stopping listener due to socket error.")
                keyboard_listener_global.stop()
            client_running = False  # Signal main loop to exit
            return False
        except Exception as e:
            print(f"[TCP CLIENT] Unexpected error sending/receiving for command '{command}': {e}")
            # For unexpected errors, also try to gracefully shut down
            if keyboard_listener_global and keyboard_listener_global.is_alive():
                keyboard_listener_global.stop()
            client_running = False
            return False  # Indicate failure
    else:
        print("[KEY CAPTURE] No active server connection to send command.")
        return False


def on_press(key):
    """Callback function for when a key is pressed."""
    global keyboard_listener_global, client_running

    # --- MODIFIED: ESC no longer exits the client script directly. ---
    # It will be handled by the KEYS_TO_COMMANDS mapping if present.
    #
    # if key == keyboard.Key.esc: # OLD LOGIC
    #     print("[KEY CAPTURE] Escape key pressed. Stopping listener and client...")
    #     if keyboard_listener_global:
    #         keyboard_listener_global.stop() # Stop the pynput listener
    #     client_running = False # Signal main loop to exit
    #     return False # Stop listener callback chain

    command = KEYS_TO_COMMANDS.get(key)
    if command:
        if not send_command_to_server(command):
            # If sending command failed critically (e.g., socket error),
            # client_running might be set to False by send_command_to_server.
            # The listener should also be stopped in that case by send_command_to_server.
            print(f"[KEY CAPTURE] Failed to send command '{command}' or critical error occurred.")
    # else: # Optional: for debugging unmapped keys
    #     try:
    #         print(f"Key pressed: {key.char} (not mapped to a command)")
    #     except AttributeError:
    #         print(f"Special key pressed: {key} (not mapped to a command)")


def connect_and_listen(server_ip, command_port, pairing_id_to_use):
    """
    Connects to the server, performs pairing, and starts listening for key presses.
    """
    global tcp_socket_global, keyboard_listener_global, client_running
    # Ensure client_running is true at the start of a new connection attempt
    client_running = True

    tcp_socket_global = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        print(f"\n[TCP CLIENT] Attempting to connect to server at {server_ip}:{command_port}...")
        tcp_socket_global.connect((server_ip, command_port))
        print(f"[TCP CLIENT] Connected to server.")

        # --- Perform TCP Pairing ---
        tcp_pairing_message = f"PAIR_WITH_SERVER:{pairing_id_to_use}"
        print(f"[TCP CLIENT] Sending TCP pairing message: '{tcp_pairing_message}'")
        tcp_socket_global.sendall(tcp_pairing_message.encode())

        # Set a timeout for receiving the pairing response
        tcp_socket_global.settimeout(10.0)  # 10 seconds for pairing response
        pairing_response_data = tcp_socket_global.recv(BUFFER_SIZE)
        tcp_socket_global.settimeout(None)  # Reset timeout after recv

        if not pairing_response_data:
            print("[TCP CLIENT] Server closed connection during TCP pairing.")
            client_running = False  # Ensure main loop knows to exit
            return

        pairing_response = pairing_response_data.decode().strip()
        print(f"[TCP CLIENT] Received pairing response: '{pairing_response}'")

        if pairing_response == "ACK:PAIRING_SUCCESSFUL":
            print("[TCP CLIENT] TCP Pairing successful with server!")
            print("\n--- Listening for Presentation Key Presses ---")
            print("Press mapped keys (e.g., Right Arrow for NEXT, Left Arrow for PREVIOUS).")
            print("To STOP this client: Close the terminal window or press Ctrl+C.")

            # Ensure no old listener is running if retrying
            if keyboard_listener_global and keyboard_listener_global.is_alive():
                keyboard_listener_global.stop()

            keyboard_listener_global = keyboard.Listener(on_press=on_press)
            keyboard_listener_global.start()

            # Keep the main thread alive while the listener is running and client is active
            while client_running and keyboard_listener_global.is_alive():
                time.sleep(0.1)  # Keep main thread responsive, check flags

            print("[TCP CLIENT] Exited listening loop.")

        else:
            print(f"[TCP CLIENT] TCP Pairing failed: {pairing_response}. Aborting session.")
            client_running = False  # Ensure main loop knows to exit if pairing fails
            return

    except socket.timeout:  # Catch timeout specifically for pairing
        print(f"[TCP CLIENT] Timeout during TCP pairing with server.")
        client_running = False
    except socket.error as e:
        print(f"[TCP CLIENT] Socket error during connection/pairing: {e}")
        client_running = False  # Signal main loop to exit
    except Exception as e:
        print(f"[TCP CLIENT] An unexpected error occurred during connection/listen setup: {e}")
        client_running = False  # Signal main loop to exit
    finally:
        print("[TCP CLIENT] Cleaning up session...")
        if keyboard_listener_global and keyboard_listener_global.is_alive():
            print("[TCP CLIENT] Ensuring listener is stopped.")
            keyboard_listener_global.stop()
            # keyboard_listener_global.join() # Optionally wait for listener thread to fully finish
        if tcp_socket_global:
            print("[TCP CLIENT] Closing TCP connection.")
            tcp_socket_global.close()
            tcp_socket_global = None  # Clear global for next session
        keyboard_listener_global = None  # Clear global for next session
        # client_running might be True here if loop exited due to listener stopping but not error
        # The main loop will decide based on client_running if to retry or exit.


if __name__ == "__main__":
    print("--- Logitech Spotlight Client (ESC key sends command, does not exit client) ---")
    print("IMPORTANT: Ensure 'pynput' is installed: pip install pynput")

    while not CLIENT_PAIRING_ID:  # Loop until a valid pairing ID is entered
        temp_id = input("Enter the Pairing ID for this session (must match server's ID, cannot be empty): ").strip()
        if temp_id:
            CLIENT_PAIRING_ID = temp_id
        else:
            print("Pairing ID cannot be empty. Please try again.")
    print(f"Using Pairing ID for this session: '{CLIENT_PAIRING_ID}'")

    # Main application loop
    # client_running is True initially. It's set to False on critical errors or if user chooses not to retry.
    while client_running:
        server_info = discover_server(CLIENT_PAIRING_ID)

        if server_info:
            ip, port, name = server_info
            connect_and_listen(ip, port, CLIENT_PAIRING_ID)

            # After connect_and_listen returns, client_running might have been set to False
            # by an error within it or by the listener stopping.
            if not client_running:
                print("\nClient session ended or was stopped due to an error.")
                # Ask if user wants to try a completely new attempt if it wasn't a clean exit choice
                retry_choice = input("Attempt to start a new discovery and connection? (y/n): ").strip().lower()
                if retry_choice == 'y':
                    client_running = True  # Allow the loop to try again
                    CLIENT_PAIRING_ID = ""  # Reset pairing ID to prompt again for a new session
                    while not CLIENT_PAIRING_ID:
                        temp_id = input("Enter Pairing ID for the new session: ").strip()
                        if temp_id:
                            CLIENT_PAIRING_ID = temp_id
                        else:
                            print("Pairing ID cannot be empty.")
                    print(f"Using new Pairing ID: '{CLIENT_PAIRING_ID}'")
                else:
                    break  # Exit main application loop
            else:  # This case implies connect_and_listen exited but client_running is still true (e.g. listener stopped but no error)
                # This path might be less common with current logic but good to have a clear distinction.
                print("\nSession ended.")
        else:  # Server not found
            print("Could not find a server or discovery failed with the current Pairing ID.")

        if client_running:  # Only ask to retry current pairing ID if not explicitly stopped or choosing new session
            retry_choice = input(f"Retry discovery with Pairing ID '{CLIENT_PAIRING_ID}'? (y/n): ").strip().lower()
            if retry_choice != 'y':
                print("Exiting client.")
                break  # Exit main application loop
            print(f"Waiting {RETRY_DELAY} seconds before retrying...")
            time.sleep(RETRY_DELAY)
        # If client_running became false inside the loop, it will exit here.

    print("Client program terminated.")
