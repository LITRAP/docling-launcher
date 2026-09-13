"""Small favours only Windows can do: keep the machine awake while a batch runs, show a
notification when it ends, tell which look the system uses, and put a "Convert with
Docling" entry into Explorer's right-click menu. Each is a few lines of the Windows API,
nothing to install, and each does nothing at all when not asked.
"""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
import subprocess
import sys
import winreg

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def keep_awake(on: bool) -> None:
    """Stops Windows going to sleep while a batch runs. Per thread: the batch thread calls
    keep_awake(True) at its start and keep_awake(False) before it ends."""
    if os.name != "nt":
        return
    flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED if on else ES_CONTINUOUS
    ctypes.windll.kernel32.SetThreadExecutionState(flags)


def notify(title: str, message: str) -> bool:
    """A Windows notification (toast), through PowerShell's own notification identity —
    the one way that needs no installation and no registration. Returns False on failure."""
    if os.name != "nt":
        return False
    safe_title = title.replace("&", "&amp;").replace("<", "&lt;")
    safe_message = message.replace("&", "&amp;").replace("<", "&lt;")
    script = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null;"
        "$xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
        "[Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
        "$t = $xml.GetElementsByTagName('text');"
        f"$t.Item(0).AppendChild($xml.CreateTextNode('{safe_title}')) | Out-Null;"
        f"$t.Item(1).AppendChild($xml.CreateTextNode('{safe_message}')) | Out-Null;"
        "$toast = [Windows.UI.Notifications.ToastNotification]::new($xml);"
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
        "'{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe').Show($toast)"
    )
    try:
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True
    except Exception:
        return False


def system_theme() -> str:
    """'light' or 'dark', as Windows' own apps show it."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return "light" if value else "dark"
    except OSError:
        return "light"


MENU_KEYS = (
    r"Software\Classes\Directory\shell\DoclingLauncher",
    r"Software\Classes\Directory\Background\shell\DoclingLauncher",
)


def explorer_menu_installed() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, MENU_KEYS[0] + r"\command") as key:
            command, _ = winreg.QueryValueEx(key, "")
            return bool(command)
    except OSError:
        return False


def set_explorer_menu(enabled: bool, exe: Path | None = None) -> None:
    """'Convert with Docling' on a folder's right-click menu (and on the empty space inside
    a folder). Current user only; no administrator needed."""
    exe = exe or (Path(sys.executable) if getattr(sys, "frozen", False) else None)
    if enabled and not exe:
        return
    for key_path in MENU_KEYS:
        if enabled:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "Convert with Docling")
                winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, f'"{exe}",0')
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path + r"\command") as key:
                argument = "%1" if "Background" not in key_path else "%V"
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, f'"{exe}" "{argument}"')
        else:
            for sub in (key_path + r"\command", key_path):
                try:
                    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
                except OSError:
                    pass
