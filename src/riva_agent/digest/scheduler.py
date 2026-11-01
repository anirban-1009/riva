import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from riva_agent import config

logger = logging.getLogger(__name__)

LAUNCHD_LABEL = "com.riva.digest"
LAUNCHD_PLIST_NAME = f"{LAUNCHD_LABEL}.plist"
LAUNCHD_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"


def parse_schedule_time(time_str: str) -> tuple[int, int]:
    """Parse 'HH:MM' string into (hour, minute). Defaults to (8, 0) on invalid input."""
    match = re.match(r"^(\d{1,2}):(\d{2})$", time_str.strip())
    if not match:
        return (8, 0)
    hour = int(match.group(1)) % 24
    minute = int(match.group(2)) % 60
    return (hour, minute)


def generate_launchd_plist(
    schedule_time: str = "08:00",
    project_dir: Path | None = None,
    log_dir: Path | None = None,
) -> str:
    """Generate macOS launchd XML plist content for periodic digest generation."""
    hour, minute = parse_schedule_time(schedule_time)
    proj_dir = project_dir or Path(__file__).resolve().parent.parent.parent.parent
    logs = log_dir or (config.DATA_DIR / "logs")
    logs.mkdir(parents=True, exist_ok=True)
    digest_log = logs / "digest.log"

    uv_path = shutil.which("uv") or "/usr/local/bin/uv"

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LAUNCHD_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{uv_path}</string>
        <string>run</string>
        <string>--directory</string>
        <string>{proj_dir}</string>
        <string>riva</string>
        <string>digest</string>
        <string>generate</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>{hour}</integer>
        <key>Minute</key>
        <integer>{minute}</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>{digest_log}</string>
    <key>StandardErrorPath</key>
    <string>{digest_log}</string>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
"""


def install_launchd_schedule(
    schedule_time: str = "08:00",
    project_dir: Path | None = None,
    *,
    dry_run: bool = False,
    agents_dir: Path | None = None,
) -> tuple[bool, str]:
    """Write and register launchd agent for scheduled daily digest execution."""
    target_dir = agents_dir or LAUNCHD_AGENTS_DIR
    plist_path = target_dir / LAUNCHD_PLIST_NAME
    plist_content = generate_launchd_plist(schedule_time=schedule_time, project_dir=project_dir)

    if dry_run:
        return True, f"[dry-run] Would write plist to {plist_path} with daily time {schedule_time}"

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        plist_path.write_text(plist_content, encoding="utf-8")

        # Unload previous registration if active, then load
        subprocess.run(["launchctl", "unload", "-w", str(plist_path)], capture_output=True)
        load_proc = subprocess.run(["launchctl", "load", "-w", str(plist_path)], capture_output=True, text=True)

        if load_proc.returncode != 0:
            err = load_proc.stderr.strip() or f"exit code {load_proc.returncode}"
            logger.warning("launchctl load warning: %s", err)
            return True, f"Installed {plist_path} for daily {schedule_time} (launchctl note: {err})"

        return True, f"Successfully installed launchd agent {LAUNCHD_LABEL} for daily {schedule_time}"
    except Exception as e:
        logger.error("Failed to install launchd schedule: %s", e)
        return False, f"Failed to install launchd schedule: {e}"


def uninstall_launchd_schedule(
    *,
    dry_run: bool = False,
    agents_dir: Path | None = None,
) -> tuple[bool, str]:
    """Unload and remove launchd agent plist file."""
    target_dir = agents_dir or LAUNCHD_AGENTS_DIR
    plist_path = target_dir / LAUNCHD_PLIST_NAME

    if not plist_path.exists():
        return True, f"No launchd agent file found at {plist_path}"

    if dry_run:
        return True, f"[dry-run] Would unload and remove {plist_path}"

    try:
        subprocess.run(["launchctl", "unload", "-w", str(plist_path)], capture_output=True)
        plist_path.unlink(missing_ok=True)
        return True, f"Successfully uninstalled launchd agent {LAUNCHD_LABEL}"
    except Exception as e:
        logger.error("Failed to uninstall launchd schedule: %s", e)
        return False, f"Failed to uninstall launchd schedule: {e}"


def get_launchd_schedule_status(agents_dir: Path | None = None) -> dict[str, Any]:
    """Query status of the launchd digest agent."""
    target_dir = agents_dir or LAUNCHD_AGENTS_DIR
    plist_path = target_dir / LAUNCHD_PLIST_NAME

    status: dict[str, Any] = {
        "installed": plist_path.exists(),
        "plist_path": str(plist_path),
        "loaded": False,
        "schedule_time": None,
        "detail": None,
    }

    if not plist_path.exists():
        status["detail"] = "Schedule not installed."
        return status

    # Parse schedule time from plist file
    try:
        text = plist_path.read_text(encoding="utf-8")
        h_match = re.search(r"<key>Hour</key>\s*<integer>(\d+)</integer>", text)
        m_match = re.search(r"<key>Minute</key>\s*<integer>(\d+)</integer>", text)
        if h_match and m_match:
            status["schedule_time"] = f"{int(h_match.group(1)):02d}:{int(m_match.group(1)):02d}"
    except Exception:
        pass

    # Check launchctl list
    try:
        proc = subprocess.run(["launchctl", "list", LAUNCHD_LABEL], capture_output=True, text=True)
        status["loaded"] = proc.returncode == 0
        if status["loaded"]:
            status["detail"] = "Agent is active and loaded in launchd."
        else:
            status["detail"] = "Plist exists but agent is currently not loaded in launchctl."
    except Exception as e:
        status["detail"] = f"Unable to check launchctl: {e}"

    return status
