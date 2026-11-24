"""
DilliTransit - Single Unified Startup Script
Starts the backend server and automatically opens the browser.
"""
import os
import sys
import time
import threading
import webbrowser
from server import run_server

def open_browser():
    time.sleep(1.2)
    print("\n[+] Opening DilliTransit in your default web browser (http://localhost:8000)...")
    webbrowser.open("http://localhost:8000")

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    threading.Thread(target=open_browser, daemon=True).start()
    port_env = os.environ.get("PORT", "8000")
    try:
        port = int(port_env)
    except ValueError:
        port = 8000
    host = os.environ.get("HOST", "0.0.0.0")
    run_server(port=port, host=host)
