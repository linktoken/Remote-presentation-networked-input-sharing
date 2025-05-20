# spotlight_client.py
# Run this script on Computer 1 (where the Logitech Spotlight is connected)

import socket
import time
from pynput import keyboard  # For listening to global key presses

# Configuration
DISCOVERY_PORT = 50000
DISCOVERY_TIMEOUT = 5  # seconds to wait for server discovery
BROADCAST_ADDRESS = '<broadcast>'  # Special address for broadcasting
# For some systems, you might need to use a specific broadcast IP like '192.168.1.255'
# if '<broadcast>' doesn't work.
BUFFER_SIZE = 1024

# --- Key Mappings ---
# Map specific keys to commands to be sent to the server.
# You'll need to identify which keys your Logitech Spotlight presenter sends.
# This configuration assumes your Spotlight sends right arrow for next and left for previous.
KEYS_TO_COMMANDS = {
    keyboard.Key.right: "NEXT",  # If Spotlight sends 'right arrow' for next
    keyboard.Key.left: "PREVIOUS",  # If Spotlight sends 'left arrow' for previous
    keyboard.Key.f5: "START_PRESENTATION",
    keyboard.KeyCode.from_char('b'): "BLACK_SCREEN",
    keyboard.KeyCode.from_char('B'): "BLACK_SCREEN",  # Case-insensitive for 'b'
    # Add more mappings here if your Spotlight has other buttons/keys
    # e.g., if a button sends 'g', and you want to map it:
    # keyboard.KeyCode.from_char('g'): "LASER_ON",
}

# Global variable to store the client socket
client_socket = None
server_address_global = None


def discover_server():
    """Broadcasts to find the server and returns its IP and port."""
    print("[DISCOVERY] Looking for Spotlight Receiver Server...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(DISCOVERY_TIMEOUT)

    message = "SPOTLIGHT_CLIENT_DISCOVERY".encode()

    discovered_servers = []

    try:
        # Send a few discovery packets in case of UDP packet loss
        for i in range(3):
            sock.sendto(message, (BROADCAST_ADDRESS, DISCOVERY_PORT))
            print(f"[DISCOVERY] Sent discovery broadcast ({i + 1}/3) to {BROADCAST_ADDRESS}:{DISCOVERY_PORT}")
            time.sleep(0.2)  # Small delay between broadcasts

        print(f"[DISCOVERY] Listening for responses for {DISCOVERY_TIMEOUT} seconds...")
        start_time = time.time()
        while time.time() - start_time < DISCOVERY_TIMEOUT:
            try:
                # Check remaining time for recvfrom timeout
                remaining_time = DISCOVERY_TIMEOUT - (time.time() - start_time)
                if remaining_time <= 0:
                    break
                sock.settimeout(remaining_time)

                data, server_addr_info = sock.recvfrom(BUFFER_SIZE)  # server_addr_info is (ip, port)
                response = data.decode()
                print(f"[DISCOVERY] Received response: '{response}' from {server_addr_info}")
                if response.startswith("SPOTLIGHT_SERVER_RESPONSE:"):
                    parts = response.split(':', 3)  # Split max 3 times for RESPONSE_TYPE:IP:PORT:NAME
                    if len(parts) == 4:
                        server_ip = parts[1]
                        try:
                            server_cmd_port = int(parts[2])
                            server_name = parts[3]
                            print(f"[DISCOVERY] Found server '{server_name}' at {server_ip}:{server_cmd_port}")
                            # For simplicity, connect to the first one found.
                            # You could extend this to list all and let user choose.
                            # Store it, but we will return the first valid one outside loop if needed.
                            discovered_servers.append({'ip': server_ip, 'port': server_cmd_port, 'name': server_name})
                            # Return immediately with the first server found
                            return server_ip, server_cmd_port
                        except ValueError:
                            print(f"[DISCOVERY] Invalid port in response: {parts[2]}")
                    else:
                        print(f"[DISCOVERY] Malformed response: {response}")
            except socket.timeout:
                # This is expected if no more responses are coming in the remaining time
                break  # Break from while loop if overall DISCOVERY_TIMEOUT is reached
            except Exception as e:
                print(f"[DISCOVERY] Error receiving discovery response: {e}")
                # Continue trying to receive other responses until DISCOVERY_TIMEOUT
                pass


    except socket.gaierror as e:
        print(f"[DISCOVERY] Socket error during discovery (check broadcast address or network): {e}")
        print(
            f"[DISCOVERY] Tip: If '{BROADCAST_ADDRESS}' fails, try your network's specific broadcast IP (e.g., '192.168.1.255').")
    except Exception as e:
        print(f"[DISCOVERY] Error during discovery: {e}")
    finally:
        sock.close()

    if not discovered_servers:  # Should not happen if we return early
        print("[DISCOVERY] No servers found after timeout.")
        return None, None

    # This part is mostly redundant if we return immediately upon finding a server above.
    # If for some reason we collected servers and didn't return, this would pick the first.
    if discovered_servers:
        first_server = discovered_servers[0]
        return first_server['ip'], first_server['port']

    return None, None


def connect_to_server(server_ip, server_port):
    """Connects to the server via TCP."""
    global client_socket
    global server_address_global

    if not server_ip or not server_port:
        print("[TCP CLIENT] No server address provided. Cannot connect.")
        return False

    server_address_global = (server_ip, server_port)
    if client_socket:  # Close existing socket if any before creating new one
        try:
            client_socket.close()
        except:
            pass  # Ignore errors on close

    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.settimeout(5)  # Set a timeout for connection attempts

    try:
        print(f"[TCP CLIENT] Attempting to connect to {server_ip}:{server_port}...")
        client_socket.connect(server_address_global)
        print(f"[TCP CLIENT] Successfully connected to server at {server_ip}:{server_port}")
        client_socket.settimeout(None)  # Remove timeout for subsequent operations if needed, or keep for send/recv
        return True
    except socket.timeout:
        print(f"[TCP CLIENT] Connection attempt timed out to {server_ip}:{server_port}.")
        client_socket = None
        return False
    except socket.error as e:
        print(f"[TCP CLIENT] Failed to connect to server {server_ip}:{server_port}: {e}")
        client_socket = None
        return False


def send_command(command):
    """Sends a command to the connected server."""
    global client_socket
    if client_socket:
        try:
            print(f"[TCP CLIENT] Sending command: {command}")
            client_socket.sendall(command.encode())
            # It's good practice to set a timeout for recv if you expect a timely response
            client_socket.settimeout(3)  # Timeout for ACK/NACK
            response = client_socket.recv(BUFFER_SIZE).decode()
            client_socket.settimeout(None)  # Reset timeout
            print(f"[TCP CLIENT] Server response: {response}")
        except socket.timeout:
            print(f"[TCP CLIENT] Timeout waiting for ACK/NACK from server for command '{command}'.")
            # Consider this a failure, may need to reconnect
            client_socket.close()
            client_socket = None
            attempt_reconnect_and_send(command)
        except socket.error as e:
            print(f"[TCP CLIENT] Error sending command '{command}': {e}. Attempting to reconnect...")
            client_socket.close()
            client_socket = None
            attempt_reconnect_and_send(command)
    else:
        print("[TCP CLIENT] Not connected to server. Command not sent.")
        attempt_reconnect_and_send(command)


def attempt_reconnect_and_send(original_command=None):
    """Attempts to rediscover, reconnect, and optionally resend a command."""
    global server_address_global
    print("[TCP CLIENT] Attempting to rediscover and connect...")
    # Try reconnecting with last known address first if available
    if server_address_global:
        print(
            f"[TCP CLIENT] Retrying connection to last known server: {server_address_global[0]}:{server_address_global[1]}")
        if connect_to_server(server_address_global[0], server_address_global[1]):
            if original_command:
                print("[TCP CLIENT] Reconnected. Retrying command...")
                send_command(original_command)  # Retry sending after reconnect
            return True  # Reconnected

    # If last known failed or not available, try full discovery
    print("[TCP CLIENT] Last known server connection failed or address unknown. Starting full discovery...")
    server_ip, server_port = discover_server()
    if server_ip and server_port:
        if connect_to_server(server_ip, server_port):
            if original_command:
                print("[TCP CLIENT] Rediscovered and reconnected. Retrying command...")
                send_command(original_command)  # Retry after successful connection
            return True  # Rediscovered and reconnected
    else:
        print("[TCP CLIENT] Rediscovery failed. Please ensure server is running.")
    return False


# --- pynput Key Listener Callbacks ---
def on_press(key):
    """Callback function for when a key is pressed."""
    # print(f"Key pressed: {key}") # For debugging what keys are detected
    command = KEYS_TO_COMMANDS.get(key)
    if command:
        print(f"\n[KEY EVENT] Mapped key {key} to command: {command}")
        send_command(command)
    # else:
    #     print(f"Key {key} is not mapped to any command.") # Enable for debugging unmapped keys


def on_release(key):
    """Callback function for when a key is released."""
    if key == keyboard.Key.esc:
        print("[KEY EVENT] Escape key detected. To stop client, use Ctrl+C in terminal.")
        # If you want Esc to stop the listener thread (but not necessarily the client app):
        # print("Escape key pressed, stopping listener.")
        # return False # This would stop the listener thread.
        pass


if __name__ == "__main__":
    print("--- Logitech Spotlight Client ---")
    print(f"Ensure pynput is installed: pip install pynput")
    print(f"This will listen for global key presses defined in KEYS_TO_COMMANDS.")
    print(f"Press Ctrl+C in the terminal to stop the client.")

    # 1. Discover the server and connect
    if not attempt_reconnect_and_send():  # Initial attempt to connect (no command to send yet)
        print("Could not connect to server during initial setup. Exiting.")
        exit()

    # 2. Start listening for key presses
    print("\n[KEY LISTENER] Starting key listener. Press mapped keys to send commands.")
    # Making the displayed keys more readable
    readable_keys_to_commands = {}
    for k, v in KEYS_TO_COMMANDS.items():
        key_name = ""
        if isinstance(k, keyboard.Key):
            key_name = k.name
        elif isinstance(k, keyboard.KeyCode):
            key_name = k.char
        readable_keys_to_commands[key_name] = v
    print(f"Mapped keys: {readable_keys_to_commands}")
    print("Ensure the window of the application you want to control on Computer 2 is active on that machine.")

    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()

    try:
        while True:  # Keep main thread alive
            time.sleep(1)
            # You could add a periodic check here to see if client_socket is still valid
            # and if not, trigger attempt_reconnect_and_send(None)
            if not client_socket:
                print("[MAIN LOOP] Client socket is not connected. Attempting to reconnect...")
                if not attempt_reconnect_and_send():
                    print("[MAIN LOOP] Reconnect attempt failed. Will try again later.")
                    time.sleep(5)  # Wait before next auto-reconnect attempt
                else:
                    print("[MAIN LOOP] Successfully reconnected.")


    except KeyboardInterrupt:
        print("\nClient interrupted by Ctrl+C. Shutting down.")
    finally:
        if listener.is_alive():
            listener.stop()
            listener.join()  # Wait for listener thread to finish
        if client_socket:
            try:
                client_socket.close()
            except Exception as e:
                print(f"Error closing client socket: {e}")
        print("Client stopped.")