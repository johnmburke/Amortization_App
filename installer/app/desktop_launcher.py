from __future__ import annotations

import ctypes
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


APP_NAME = "Amortization Calculator"
APP_FILE = Path(__file__).with_name("app.py")


def show_error(message: str) -> None:
    try:
        ctypes.windll.user32.MessageBoxW(None, message, APP_NAME, 0x10)
    except Exception:
        pass


def find_available_port(start_port: int = 8501) -> int:
    for port in range(start_port, start_port + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port

    raise RuntimeError("Could not find an available local port.")


def wait_for_app(url: str, timeout_seconds: int = 30) -> bool:
    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1):
                return True
        except (OSError, urllib.error.URLError):
            time.sleep(0.5)

    return False


def start_streamlit(port: int) -> subprocess.Popen:
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(APP_FILE),
            "--server.address=127.0.0.1",
            f"--server.port={port}",
            "--server.headless=true",
            "--browser.gatherUsageStats=false",
        ],
        cwd=APP_FILE.parent,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )


def stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return

    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def main() -> None:
    if not APP_FILE.exists():
        show_error("Could not find app.py. Please reinstall the application.")
        return

    try:
        import webview
    except ImportError:
        show_error("pywebview is not installed. Please run the installer again.")
        return

    try:
        port = find_available_port()
        app_url = f"http://127.0.0.1:{port}"
        streamlit_process = start_streamlit(port)
    except Exception as error:
        show_error(f"The app could not be started.\n\n{error}")
        return

    try:
        if not wait_for_app(app_url):
            show_error("The app did not finish starting. Please try again.")
            return

        webview.create_window(
            APP_NAME,
            app_url,
            width=1280,
            height=850,
            min_size=(900, 650),
        )
        webview.start()
    finally:
        stop_process(streamlit_process)


if __name__ == "__main__":
    main()
