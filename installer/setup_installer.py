from __future__ import annotations

import ctypes
import io
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath


APP_NAME = "Amortization Calculator"
REPOSITORY_ARCHIVE_URL = (
    "https://github.com/johnmburke/Amortization_App/archive/refs/heads/main.zip"
)
MINIMUM_PYTHON_VERSION = (3, 10, 0)
INSTALL_ROOT = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "AmortizationCalculator"
APP_DIR = INSTALL_ROOT / "app"
LAUNCHER_PS1 = INSTALL_ROOT / "run_amortization_app.ps1"
LAUNCHER_VBS = INSTALL_ROOT / "launch_amortization_app.vbs"


def write_line(message: str = "") -> None:
    print(message, flush=True)


def show_error(message: str) -> None:
    try:
        ctypes.windll.user32.MessageBoxW(None, message, APP_NAME, 0x10)
    except Exception:
        pass


def pause() -> None:
    if "--quiet" in sys.argv:
        return

    try:
        input("\nPress Enter to close this installer...")
    except EOFError:
        pass


def run_command(command: list[str], check: bool = True) -> subprocess.CompletedProcess:
    write_line(f"> {' '.join(command)}")
    return subprocess.run(command, check=check)


def run_command_capture(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def parse_version(value: str) -> tuple[int, int, int] | None:
    try:
        parts = tuple(int(part) for part in value.strip().split(".")[:3])
    except ValueError:
        return None

    if len(parts) != 3:
        return None

    return parts


def python_version(command: list[str]) -> tuple[int, int, int] | None:
    result = run_command_capture(
        command
        + ["-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))"]
    )
    if result.returncode != 0:
        return None

    return parse_version(result.stdout)


def find_python() -> list[str] | None:
    candidates = [["py", "-3"], ["python"]]

    for candidate in candidates:
        if shutil.which(candidate[0]) is None:
            continue

        version = python_version(candidate)
        if version is not None and version >= MINIMUM_PYTHON_VERSION:
            return candidate

    return None


def refresh_path() -> None:
    result = run_command_capture(
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            "[Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + "
            "[Environment]::GetEnvironmentVariable('Path', 'User')",
        ]
    )
    if result.returncode == 0 and result.stdout.strip():
        os.environ["PATH"] = result.stdout.strip()


def get_desktop_shortcut() -> Path:
    result = run_command_capture(
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            "[Environment]::GetFolderPath('Desktop')",
        ]
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip()) / f"{APP_NAME}.lnk"

    return Path.home() / "Desktop" / f"{APP_NAME}.lnk"


def prompt_for_python_install() -> None:
    write_line()
    write_line("Python 3.10 or newer was not found on this computer.")
    write_line("This app needs Python before it can install Streamlit, pandas, and Plotly.")
    write_line()

    if shutil.which("winget"):
        answer = input("Install Python 3.12 now using Windows Package Manager? (Y/N): ")
        if answer.strip().lower().startswith("y"):
            write_line()
            write_line("Installing Python 3.12. This may take a few minutes...")
            run_command(
                [
                    "winget",
                    "install",
                    "--id",
                    "Python.Python.3.12",
                    "-e",
                    "--source",
                    "winget",
                    "--accept-package-agreements",
                    "--accept-source-agreements",
                ]
            )
            refresh_path()
            return
    else:
        write_line("Windows Package Manager (winget) was not found.")

    write_line()
    write_line("Please install Python 3.10 or newer from:")
    write_line("https://www.python.org/downloads/")
    write_line()
    write_line("During Python setup, check: Add Python to PATH")
    write_line("Then run this installer again.")
    raise RuntimeError("Python is required before installation can continue.")


def fetch_repository_archive() -> bytes:
    request = urllib.request.Request(
        REPOSITORY_ARCHIVE_URL,
        headers={"User-Agent": "AmortizationCalculatorSetup/1.0"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def archive_member_suffix(member_name: str, marker: str) -> str | None:
    normalized = member_name.replace("\\", "/")
    marker_path = f"/{marker.strip('/')}/"
    if marker_path not in f"/{normalized}":
        return None

    return normalized.split(marker_path, 1)[1]


def write_archive_file(archive: zipfile.ZipFile, member_name: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with archive.open(member_name) as source, destination.open("wb") as target:
        shutil.copyfileobj(source, target)


def install_app_files(archive_bytes: bytes) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    settings_path = APP_DIR / "settings.json"
    settings_backup_path = INSTALL_ROOT / "settings.json.backup"

    if settings_path.exists():
        shutil.copy2(settings_path, settings_backup_path)

    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        copied_app_files = 0
        copied_launcher_files = 0

        for member in archive.infolist():
            if member.is_dir():
                continue

            member_path = PurePosixPath(member.filename)
            if ".." in member_path.parts:
                continue

            app_suffix = archive_member_suffix(member.filename, "installer/app")
            if app_suffix:
                relative_path = PurePosixPath(app_suffix)
                if relative_path.name == "settings.json":
                    continue

                write_archive_file(archive, member.filename, APP_DIR / Path(*relative_path.parts))
                copied_app_files += 1
                continue

            if member.filename.endswith("/installer/run_amortization_app.ps1"):
                write_archive_file(archive, member.filename, LAUNCHER_PS1)
                copied_launcher_files += 1
                continue

            if member.filename.endswith("/installer/launch_amortization_app.vbs"):
                write_archive_file(archive, member.filename, LAUNCHER_VBS)
                copied_launcher_files += 1

    if copied_app_files == 0:
        raise RuntimeError("The GitHub download did not include installer/app files.")

    if copied_launcher_files < 2:
        write_line("Warning: script launchers were not found in the download.")

    if not settings_path.exists() and settings_backup_path.exists():
        shutil.copy2(settings_backup_path, settings_path)


def ensure_virtual_environment(python_command: list[str]) -> Path:
    venv_dir = INSTALL_ROOT / ".venv"
    venv_python = venv_dir / "Scripts" / "python.exe"

    if not venv_python.exists():
        run_command(python_command + ["-m", "venv", str(venv_dir)])

    if not venv_python.exists():
        raise RuntimeError("Could not create Python virtual environment.")

    return venv_python


def install_python_requirements(venv_python: Path) -> None:
    requirements_file = APP_DIR / "requirements.txt"
    if not requirements_file.exists():
        raise RuntimeError("The downloaded app did not include requirements.txt.")

    run_command([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"])
    run_command([str(venv_python), "-m", "pip", "install", "-r", str(requirements_file)])


def powershell_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def create_desktop_shortcut() -> None:
    launcher_exe = APP_DIR / "Amortization Calculator.exe"
    icon_path = APP_DIR / "app_icon.ico"
    desktop_shortcut = get_desktop_shortcut()

    if launcher_exe.exists():
        shortcut_target = launcher_exe
        shortcut_args = ""
        shortcut_working_dir = APP_DIR
    else:
        shortcut_target = Path(os.environ.get("SystemRoot", "C:\\Windows")) / "System32" / "wscript.exe"
        shortcut_args = f'//B //Nologo "{LAUNCHER_VBS}"'
        shortcut_working_dir = INSTALL_ROOT

    icon_location = str(icon_path) if icon_path.exists() else "%SystemRoot%\\System32\\shell32.dll,44"
    ps_command = "\n".join(
        [
            f"$shortcutPath = {powershell_quote(str(desktop_shortcut))}",
            "$shell = New-Object -ComObject WScript.Shell",
            "$shortcut = $shell.CreateShortcut($shortcutPath)",
            f"$shortcut.TargetPath = {powershell_quote(str(shortcut_target))}",
            f"$shortcut.Arguments = {powershell_quote(shortcut_args)}",
            f"$shortcut.WorkingDirectory = {powershell_quote(str(shortcut_working_dir))}",
            f"$shortcut.IconLocation = {powershell_quote(icon_location)}",
            "$shortcut.Save()",
        ]
    )

    run_command(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            ps_command,
        ]
    )


def install() -> None:
    write_line(f"{APP_NAME} Setup")
    write_line("=" * (len(APP_NAME) + 6))
    write_line()

    python_command = find_python()
    if python_command is None:
        prompt_for_python_install()
        python_command = find_python()

    if python_command is None:
        raise RuntimeError("Python still was not found. Restart this installer after Python finishes installing.")

    write_line(f"Using Python command: {' '.join(python_command)}")
    write_line("Downloading the latest app files from GitHub...")
    archive_bytes = fetch_repository_archive()

    write_line("Installing app files...")
    INSTALL_ROOT.mkdir(parents=True, exist_ok=True)
    install_app_files(archive_bytes)

    write_line("Preparing Python environment...")
    venv_python = ensure_virtual_environment(python_command)
    install_python_requirements(venv_python)

    write_line("Creating desktop shortcut...")
    create_desktop_shortcut()

    write_line()
    write_line(f"{APP_NAME} installed successfully.")
    write_line(f"Use the Desktop shortcut named '{APP_NAME}' to start the app.")


def main() -> int:
    try:
        install()
    except (
        OSError,
        RuntimeError,
        subprocess.CalledProcessError,
        urllib.error.URLError,
        urllib.error.HTTPError,
        zipfile.BadZipFile,
    ) as error:
        message = f"Installation did not complete.\n\n{error}"
        write_line()
        write_line("Installation did not complete.")
        write_line(str(error))
        show_error(message)
        pause()
        return 1

    pause()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
