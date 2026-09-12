from __future__ import annotations

import ctypes
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Callable

from .docling_cli import CommandPlan


def is_user_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _batch_quote(value: str) -> str:
    return value.replace("^", "^^").replace("&", "^&").replace("<", "^<").replace(">", "^>")


def _drain_log(
    log_path: Path,
    offset: int,
    pending: str,
    log: Callable[[str], None],
    *,
    final: bool = False,
) -> tuple[int, str]:
    """Read only complete newly-written log lines while the elevated command runs."""
    if not log_path.exists():
        return offset, pending

    try:
        with log_path.open("rb") as stream:
            stream.seek(offset)
            chunk = stream.read()
    except PermissionError:
        # The elevated cmd process can briefly hold its redirected log exclusively.
        # Leave the offset unchanged and pick up the same content on the next poll.
        return offset, pending
    except OSError:
        return offset, pending
    offset += len(chunk)
    if not chunk and not (final and pending):
        return offset, pending

    content = pending + chunk.decode("utf-8", errors="replace")
    lines = content.splitlines(keepends=True)
    if lines and not lines[-1].endswith(("\n", "\r")):
        pending = lines.pop()
    else:
        pending = ""

    message = "".join(lines).strip()
    if message:
        log(message)
    if final and pending.strip():
        log(pending.strip())
        pending = ""
    return offset, pending


def run_elevated_batch(plans: list[CommandPlan], log: Callable[[str], None]) -> int:
    temp_dir = Path(tempfile.mkdtemp(prefix="docling_launcher_admin_"))
    script_path = temp_dir / "run_docling_batch.cmd"
    combined_log = temp_dir / "docling_elevated_output.log"

    lines = [
        "@echo off",
        "setlocal EnableExtensions",
        'set "BATCH_EXIT_CODE=0"',
        f'echo Elevated Docling batch started. > "{combined_log}"',
    ]
    if plans:
        path_value = plans[0].env.get("PATH")
        tessdata = plans[0].env.get("TESSDATA_PREFIX")
        if path_value:
            lines.append(f'set "PATH={_batch_quote(path_value)}"')
        if tessdata:
            lines.append(f'set "TESSDATA_PREFIX={_batch_quote(tessdata)}"')

    for index, plan in enumerate(plans, start=1):
        command_line = subprocess.list2cmdline(plan.command)
        lines.extend(
            [
                f'echo. >> "{combined_log}"',
                f'echo [{index}/{len(plans)}] {len(plan.sources)} file(s) -^> {plan.output_dir} >> "{combined_log}"',
                command_line + f' >> "{combined_log}" 2>&1',
                'set "FILE_EXIT_CODE=%ERRORLEVEL%"',
                f'echo Exit code: %FILE_EXIT_CODE% >> "{combined_log}"',
                'if not "%FILE_EXIT_CODE%"=="0" set "BATCH_EXIT_CODE=1"',
            ]
        )
    lines.extend(
        [
            f'echo. >> "{combined_log}"',
            f'echo Elevated Docling batch finished. >> "{combined_log}"',
            "exit /b %BATCH_EXIT_CODE%",
        ]
    )
    script_path.write_text("\r\n".join(lines), encoding="utf-8")

    escaped_script = str(script_path).replace("'", "''")
    ps_command = (
        "$p = Start-Process -FilePath 'cmd.exe' "
        f"-ArgumentList @('/c', '{escaped_script}') "
        "-Verb RunAs -Wait -PassThru; exit $p.ExitCode"
    )
    log("Requesting Windows administrator approval for the batch.")
    process = subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_command],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    log("Waiting for the elevated batch to start. Progress will appear below.")

    offset = 0
    pending = ""
    while process.poll() is None:
        offset, pending = _drain_log(combined_log, offset, pending, log)
        time.sleep(0.25)
    offset, pending = _drain_log(combined_log, offset, pending, log, final=True)
    stdout, stderr = process.communicate()

    if stdout.strip():
        log(stdout.strip())
    if stderr.strip():
        log(stderr.strip())
    return process.returncode
