# Remote Presentation Networked Input Sharing

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) [![Python Version](https://img.shields.io/badge/python-3.x-blue.svg)]() Control your presentations from anywhere on your local network! This lightweight Python application shares input from a physical presentation remote connected to one computer, allowing you to control slideshow software running on another machine. It also enables a networked client device (like another laptop, tablet, or phone) to act as an advanced presentation clicker, complete with a **virtual spotlight feature** to highlight content and engage your audience.

## ✨ Key Features

* **Cross-Computer Control:** Use a presentation remote connected to one computer (server) to control a slideshow on another (client).
* **Client as Advanced Remote:** Transform a networked device (laptop, tablet, phone) into a powerful remote control.
* **Virtual Spotlight:** Engage your audience by highlighting parts of your presentation with a network-controlled virtual spotlight.
* **Networked Input Sharing:** Seamlessly transmits commands like next/previous slide, blank screen, and spotlight controls over the local network.
* **Lightweight & Python-Based:** Built with Python for ease of use, modification, and cross-platform potential.

## 🚀 How It Works

This application uses a client-server architecture:

1.  **Server Application:**
    * Runs on the computer with the physical presentation remote connected.
    * Listens for inputs from the physical remote.
    * Relays these commands over the network to the presentation client.
    * Alternatively, can act as the receiving end for a "Spotlight Clicker Client" if no physical remote is central.

2.  **Presentation Client Application (Display Machine):**
    * Runs on the computer displaying the actual slideshow.
    * Receives commands from the Server Application or the Spotlight Clicker Client.
    * Translates these commands into actions (e.g., changing slides in PowerPoint, Keynote, Google Slides, etc.).
    * Renders the virtual spotlight effect on the screen when commanded.

3.  **Spotlight Clicker Client Application (Controller Device):**
    * Runs on a separate device (e.g., a laptop, tablet).
    * Provides a user interface for standard presentation controls and spotlight manipulation (activation, movement).
    * Sends these commands over the network to the Presentation Client Application (or a central server).

Communication primarily occurs over your local TCP/IP network.

## 🎯 Use Cases

* Presenting in large rooms where the presentation computer is out of reach.
* Complex setups with multiple displays or computers.
* Using a tablet or secondary laptop as a feature-rich remote control, including a dynamic spotlight.
* Enhancing audience engagement with visual cues without needing specialized hardware.
* Scenarios where direct USB/Bluetooth connection of a remote to the presentation machine is inconvenient or impossible.

## 🛠️ Prerequisites

* Python 3.x (e.g., Python 3.7+)
* A local network (Wi-Fi or Ethernet) connecting all participating devices.
* _[List any other major Python libraries your project depends on, e.g., `tkinter`, `PyQt5`, `pynput`, `mouse`, `websockets`, etc._
    * Example: `pip install pynput`

## ⚙️ Installation

1.  **Clone the repository:**


2.  **Set up a virtual environment (recommended):**
    ```bash
    python -m venv venv
    # On Windows:
    # venv\Scripts\activate
    # On macOS/Linux:
    # source venv/bin/activate
    ```

3.  **Install dependencies:**
    _(If you have a `requirements.txt` file):_
    ```bash
    pip install -r requirements.txt
    ```
    _(Or, install them manually):_
    ```bash
    # pip install library1 library2 ...  <-- List your project's specific libraries here
    ```

## ▶️ Usage

_**YOU NEED TO PROVIDE SPECIFIC INSTRUCTIONS HERE. Be clear about which script to run on which machine and any necessary command-line arguments (like IP addresses or ports).**_

For example:

**1. Running the Server Application (on the machine with the physical remote OR the central hub):**
   ```bash
   python server.py
