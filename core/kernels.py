"""
Kernel & Extension Discovery Module for freeanti.
Automatically builds and exposes the rebranded `TaeBrowser` (`taebrowser_153/TaeBrowser.exe`)
and `YangBrowser` (`yangbrowser_153/YangBrowser.exe`) kernels.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

from .kernel_rebrander import ensure_rebranded_kernels


def get_default_cwd_global() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "adspower_global" / "cwd_global"


def get_default_global_store() -> Path:
    return Path(r"C:\.ADSPOWER_GLOBAL")


def _read_text_safe(path: Path) -> str:
    try:
        if path.is_file():
            return path.read_text(encoding="utf-8", errors="ignore").strip()
    except Exception:
        pass
    return ""


def normalize_kernel_type(raw: Optional[str]) -> str:
    """
    Normalizes any kernel name to either `'taebrowser'` (Chromium 153) or `'yangbrowser'` (Gecko 153).
    """
    s = (raw or "taebrowser").strip().lower()
    if s in ("yangbrowser", "yangbrower", "yang", "yang_153", "flowerbrowser", "flower", "flower_153", "firefox", "gecko"):
        return "yangbrowser"
    return "taebrowser"


def discover_kernels(
    cwd_global: Optional[Path] = None,
    freeanti_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Builds/verifies `taebrowser_153` (`TaeBrowser.exe`) and `yangbrowser_153` (`YangBrowser.exe`)
    inside `freeanti/kernels/` and returns their full metadata.
    """
    base = cwd_global or get_default_cwd_global()
    root = freeanti_root or Path(__file__).resolve().parent.parent

    # Ensure rebranded TaeBrowser & YangBrowser kernels are built
    ensure_rebranded_kernels(root, base)

    kernels_dir = root / "kernels"
    tae_dir = kernels_dir / "taebrowser_153"
    yang_dir = kernels_dir / "yangbrowser_153"

    result: Dict[str, Any] = {
        "kernels_root": str(kernels_dir),
        "taebrowser": [],
        "yangbrowser": [],
        "default_taebrowser": None,
        "default_yangbrowser": None,
        # Aliases for backward compatibility
        "sunbrowser": [],
        "flowerbrowser": [],
        "default_sunbrowser": None,
        "default_flowerbrowser": None,
        "extensions": discover_extensions(base),
    }

    # 1. TaeBrowser 153 (Chromium 153.0.8010.27)
    tae_exe = tae_dir / "TaeBrowser.exe"
    if tae_exe.is_file():
        update_ver = _read_text_safe(tae_dir / "update_version_key") or "20260918"
        chromium_subver = "153.0.8010.27"
        chrome_dll_path = None
        for sub in tae_dir.iterdir():
            if sub.is_dir() and re.match(r"^\d+\.\d+\.\d+\.\d+$", sub.name):
                chromium_subver = sub.name
                dll_candidate = sub / "chrome.dll"
                if dll_candidate.is_file():
                    chrome_dll_path = str(dll_candidate)
                break
        driver_path = tae_dir / "chromedriver.exe"
        components_dir = tae_dir / "components"
        tae_info = {
            "id": "taebrowser_153",
            "name": "TaeBrowser 153",
            "kernel_type": "taebrowser",
            "browser_type": "chrome",
            "kernel_version": "153",
            "chromium_version": chromium_subver,
            "update_version_key": update_ver,
            "executable": str(tae_exe),
            "chrome_dll": chrome_dll_path,
            "webdriver": str(driver_path) if driver_path.is_file() else None,
            "components_dir": str(components_dir) if components_dir.is_dir() else None,
        }
        result["taebrowser"].append(tae_info)
        result["sunbrowser"].append(tae_info)
        result["default_taebrowser"] = tae_info
        result["default_sunbrowser"] = tae_info

    # 2. YangBrowser 153 (Gecko 153.0.4)
    yang_exe = yang_dir / "YangBrowser.exe"
    if yang_exe.is_file():
        update_ver = _read_text_safe(yang_dir / "update_version_key") or "20260907"
        xul_dll = yang_dir / "xul.dll"
        driver_path = yang_dir / "geckodriver.exe"
        app_ini = _read_text_safe(yang_dir / "application.ini")
        gecko_ver = "153.0.4"
        build_id = "20260825153431"
        for line in app_ini.splitlines():
            if line.startswith("Version="):
                gecko_ver = line.split("=", 1)[1].strip()
            elif line.startswith("BuildID="):
                build_id = line.split("=", 1)[1].strip()

        yang_info = {
            "id": "yangbrowser_153",
            "name": "YangBrowser 153",
            "kernel_type": "yangbrowser",
            "browser_type": "firefox",
            "kernel_version": "153",
            "gecko_version": gecko_ver,
            "build_id": build_id,
            "update_version_key": update_ver,
            "executable": str(yang_exe),
            "xul_dll": str(xul_dll) if xul_dll.is_file() else None,
            "webdriver": str(driver_path) if driver_path.is_file() else None,
        }
        result["yangbrowser"].append(yang_info)
        result["flowerbrowser"].append(yang_info)
        result["default_yangbrowser"] = yang_info
        result["default_flowerbrowser"] = yang_info

    return result


def discover_extensions(cwd_global: Optional[Path] = None) -> Dict[str, Any]:
    base = cwd_global or get_default_cwd_global()
    global_store = get_default_global_store()
    exts: Dict[str, Any] = {}

    ba_dir = base / "lib" / "browser_assistant"
    if (ba_dir / "manifest.json").is_file():
        exts["browser_assistant"] = {
            "id": "clhciefikpofkbdlkeacdkaplhhlmhjd",
            "name": "Chrome Validation Header Spoofer",
            "path": str(ba_dir),
            "available": True,
        }

    ext_assistant = global_store / "ext_env" / "11440805"
    if not (ext_assistant / "manifest.json").is_file():
        ext_assistant = global_store / "extension" / "11440805" / "gcaiimgaiohlnlflkjjmcohobkpbbnfi"
    if (ext_assistant / "manifest.json").is_file():
        exts["paste_assistant"] = {
            "id": "gcaiimgaiohlnlflkjjmcohobkpbbnfi",
            "name": "Human Typing Paste & Clipboard Assistant",
            "path": str(ext_assistant),
            "available": True,
        }

    ext_auth = global_store / "ext_env" / "11440806"
    if not (ext_auth / "manifest.json").is_file():
        ext_auth = global_store / "extension" / "11440806" / "chcmmdbpbocmnmbhpbjchdgjjhbnfige"
    if (ext_auth / "manifest.json").is_file():
        exts["totp_authenticator"] = {
            "id": "chcmmdbpbocmnmbhpbjchdgjjhbnfige",
            "name": "2FA TOTP & QR Scanner",
            "path": str(ext_auth),
            "available": True,
        }

    return exts
