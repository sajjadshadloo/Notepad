"""Windows Task Scheduler entries, so a reminder still arrives when the
editor is closed.

Tasks are registered from an XML definition rather than the ``/SC ONCE /SD``
flags: those flags take the date in the *user's locale* format, which reads
04/09 as April or September depending on the machine. The XML form is
ISO 8601 and unambiguous.

Everything lives under one ``NotepadPlus`` task folder so the whole set can
be listed and removed without touching anyone else's scheduled tasks.
"""
import hashlib
import logging
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

log = logging.getLogger(__name__)

FOLDER = "NotepadPlus"
# Registering costs a process spawn each, and nobody plans a year ahead in a
# notes app; past this the in-app reminder still covers things.
MAX_TASKS = 60
# How long after its moment a reminder stays valid, and after which Windows
# is free to delete the entry.
EXPIRY_WINDOW = timedelta(days=7)

# CREATE_NO_WINDOW: schtasks must never flash a console over the editor.
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _task_name(identifier: str) -> str:
    return FOLDER + "\\" + identifier


_XML_TEMPLATE = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>{description}</Description>
  </RegistrationInfo>
  <Triggers>
    <TimeTrigger>
      <StartBoundary>{start}</StartBoundary>
      <EndBoundary>{end}</EndBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT10M</ExecutionTimeLimit>
    <DeleteExpiredTaskAfter>P1D</DeleteExpiredTaskAfter>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{command}</Command>
      <Arguments>{arguments}</Arguments>
    </Exec>
  </Actions>
</Task>
"""


def available() -> bool:
    """Scheduling needs Windows and a packaged build.

    From source the command would be ``python main.py``, whose interpreter
    and working directory cannot be relied on weeks later when the task fires.
    """
    return sys.platform == "win32" and getattr(sys, "frozen", False)


def executable() -> str:
    return sys.executable


def task_id(key: str) -> str:
    """Short stable id for a task key, safe to use as a task name."""
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def _run(arguments: list[str]) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(
            ["schtasks", *arguments],
            capture_output=True,
            text=True,
            creationflags=_NO_WINDOW,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        log.warning("schtasks failed: %s", " ".join(arguments), exc_info=True)
        return None


def build_xml(description: str, when: datetime, arguments: str) -> str:
    # An EndBoundary is mandatory whenever DeleteExpiredTaskAfter is set, and
    # that pairing is what stops one-shot reminders piling up in Windows
    # forever. The window is generous so a machine that was off still fires
    # the reminder when it next starts.
    return _XML_TEMPLATE.format(
        description=escape(description),
        start=when.strftime("%Y-%m-%dT%H:%M:%S"),
        end=(when + EXPIRY_WINDOW).strftime("%Y-%m-%dT%H:%M:%S"),
        command=escape(executable()),
        arguments=escape(arguments),
    )


def register(key: str, description: str, when: datetime, temp_dir: Path) -> bool:
    """Schedule one reminder. Returns whether Windows accepted it."""
    if not available():
        return False
    identifier = task_id(key)
    xml_path = Path(temp_dir) / (identifier + ".xml")
    try:
        xml_path.parent.mkdir(parents=True, exist_ok=True)
        # UTF-16 with a BOM: schtasks rejects the file otherwise.
        xml_path.write_text(
            build_xml(description, when, '--remind "' + identifier + '"'),
            encoding="utf-16",
        )
    except OSError:
        log.warning("Could not write the task definition", exc_info=True)
        return False
    result = _run(
        ["/Create", "/TN", _task_name(identifier), "/XML", str(xml_path), "/F"]
    )
    try:
        xml_path.unlink(missing_ok=True)
    except OSError:
        pass
    return bool(result and result.returncode == 0)


def unregister(identifier: str) -> bool:
    if not available():
        return False
    result = _run(["/Delete", "/TN", _task_name(identifier), "/F"])
    return bool(result and result.returncode == 0)


def registered_ids() -> set[str]:
    """Ids of the reminders currently scheduled with Windows."""
    if not available():
        return set()
    result = _run(["/Query", "/FO", "CSV", "/NH"])
    if result is None or result.returncode != 0:
        return set()
    found = set()
    marker = "\\" + FOLDER + "\\"
    for line in result.stdout.splitlines():
        name = line.split(",")[0].strip('"')
        if marker in name:
            found.add(name.rsplit("\\", 1)[-1])
    return found


def clear_all():
    """Remove every reminder this app scheduled — used when it is switched off."""
    if not available():
        return
    _run(["/Delete", "/TN", FOLDER, "/F"])
