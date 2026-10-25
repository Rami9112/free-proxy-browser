"""
Cross-OS & Cross-Architecture Compatibility Layer for Free Proxy Browser.
Supports:
  - Operating Systems : Windows (`windows`), macOS (`macos`), Linux (`linux`)
  - CPU Architectures : x64 (`x86_64` / `amd64`), ARM64 (`aarch64` / `arm64`), x86 (`i386` / `i686`)
  - Environment simulation overrides (`FREEANTI_SIMULATE_OS`, `FREEANTI_SIMULATE_ARCH`)
    for deterministic multi-OS / multi-architecture debugging and CI verification.
"""

from __future__ import annotations

import os
import platform
import shlex
import shutil
import signal
import struct
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SUPPORTED_HOST_OSES: Tuple[str, ...] = ("windows", "macos", "linux")
SUPPORTED_ARCHES: Tuple[str, ...] = ("x64", "arm64", "x86")
SUPPORTED_EMULATED_OSES: Tuple[str, ...] = ("Windows", "macOS", "Linux", "Android", "iPhone")


def normalize_host_os(raw_os: Optional[str] = None) -> str:
    """
    Normalizes an OS identifier to `'windows'`, `'macos'`, or `'linux'`.
    Honors `FREEANTI_SIMULATE_OS` when `raw_os` is not explicitly provided.
    """
    val = (raw_os or os.environ.get("FREEANTI_SIMULATE_OS") or sys.platform or platform.system()).strip().lower()
    if val in ("win", "win32", "windows", "nt", "cygwin", "msys"):
        return "windows"
    if val in ("darwin", "mac", "macos", "osx", "mac os x"):
        return "macos"
    if val.startswith("linux") or val in ("posix", "freebsd", "openbsd", "ubuntu", "debian", "arch", "fedora"):
        return "linux"
    if os.name == "nt":
        return "windows"
    return "linux"


def normalize_arch(raw_arch: Optional[str] = None) -> str:
    """
    Normalizes a CPU architecture string to `'x64'`, `'arm64'`, or `'x86'`.
    Honors `FREEANTI_SIMULATE_ARCH` when `raw_arch` is not explicitly provided.
    """
    sim = (raw_arch or os.environ.get("FREEANTI_SIMULATE_ARCH") or "").strip().lower()
    if not sim:
        proc_arch = (
            os.environ.get("PROCESSOR_ARCHITEW6432")
            or os.environ.get("PROCESSOR_ARCHITECTURE")
            or platform.machine()
            or ""
        ).strip().lower()
        sim = proc_arch

    if sim in ("arm64", "aarch64", "armv8", "armv8l", "armv8b", "arm64e"):
        return "arm64"
    if sim in ("x86", "i386", "i486", "i586", "i686", "x86_32", "32bit"):
        return "x86"
    if sim in ("x64", "amd64", "x86_64", "em64t", "64bit"):
        return "x64"
    return "x86" if struct.calcsize("P") * 8 == 32 else "x64"


def detect_host_platform(
    override_os: Optional[str] = None,
    override_arch: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Returns comprehensive metadata about the current (or simulated) host OS and CPU architecture.
    """
    host_os = normalize_host_os(override_os)
    host_arch = normalize_arch(override_arch)
    real_os = normalize_host_os(sys.platform)
    real_arch = normalize_arch(platform.machine())
    pointer_bits = struct.calcsize("P") * 8

    return {
        "host_os": host_os,
        "host_arch": host_arch,
        "real_os": real_os,
        "real_arch": real_arch,
        "is_simulated": (host_os != real_os) or (host_arch != real_arch),
        "python_version": platform.python_version(),
        "python_bits": pointer_bits,
        "platform_tag": f"{host_os}-{host_arch}",
        "webview2_runtime_arch": f"win-{host_arch}" if host_os == "windows" else f"{host_os}-{host_arch}",
        "curl_executable": resolve_curl_executable(host_os),
        "appdata_dir": str(get_platform_appdata_dir(host_os)),
        "global_store_dir": str(get_platform_global_store_dir(host_os)),
        "supported_host_oses": list(SUPPORTED_HOST_OSES),
        "supported_arches": list(SUPPORTED_ARCHES),
        "supported_emulated_oses": list(SUPPORTED_EMULATED_OSES),
    }


def get_platform_appdata_dir(host_os: Optional[str] = None) -> Path:
    os_name = normalize_host_os(host_os)
    home = Path.home()
    if os_name == "windows":
        appdata = os.environ.get("APPDATA") or str(home / "AppData" / "Roaming")
        return Path(appdata) / "adspower_global" / "cwd_global"
    if os_name == "macos":
        return home / "Library" / "Application Support" / "adspower_global" / "cwd_global"
    xdg = os.environ.get("XDG_CONFIG_HOME") or str(home / ".config")
    return Path(xdg) / "adspower_global" / "cwd_global"


def get_platform_global_store_dir(host_os: Optional[str] = None) -> Path:
    os_name = normalize_host_os(host_os)
    if os_name == "windows":
        return Path(r"C:\.ADSPOWER_GLOBAL")
    return Path.home() / ".adspower_global"


def resolve_curl_executable(host_os: Optional[str] = None) -> str:
    os_name = normalize_host_os(host_os)
    if os_name == "windows":
        if os.name == "nt":
            found = shutil.which("curl.exe") or shutil.which("curl")
            return found or "curl.exe"
        return "curl.exe"
    if os.name != "nt":
        found = shutil.which("curl")
        return found or "/usr/bin/curl"
    return "/usr/bin/curl"


def get_subprocess_creationflags(host_os: Optional[str] = None) -> int:
    os_name = normalize_host_os(host_os)
    if os_name == "windows" and os.name == "nt":
        return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return 0


def format_command_line(argv: List[str], host_os: Optional[str] = None) -> str:
    """
    Formats a command-line list for display/inspection according to target OS quoting rules.
    """
    os_name = normalize_host_os(host_os)
    if os_name == "windows":
        return subprocess.list2cmdline(argv)
    return " ".join(shlex.quote(str(a)) for a in argv)


def resolve_angle_flags(
    gpu_mode: str,
    angle_backend: str,
    graphics_api: str,
    host_os: Optional[str] = None,
    emulated_os: str = "Windows",
) -> List[str]:
    """
    Computes the appropriate Chromium GPU / ANGLE / OpenGL / Direct3D / Metal / Vulkan flags
    across Windows, macOS, and Linux hosts while preserving the profile's requested graphics API.
    """
    os_name = normalize_host_os(host_os)
    g_mode = (gpu_mode or "enabled").strip().lower()
    backend = (angle_backend or "d3d11").strip().lower()
    g_api = (graphics_api or "Direct3D11").strip()

    if g_mode == "disabled":
        return ["--disable-gpu", "--disable-software-rasterizer"]

    if backend == "swiftshader" or g_api == "SwiftShader":
        return ["--use-gl=angle", "--use-angle=swiftshader"]

    if backend in ("gl", "opengl") or g_api == "OpenGL":
        return ["--use-angle=gl"]

    if backend == "gles" or g_api == "OpenGL ES":
        return ["--use-angle=gles" if os_name != "windows" else "--use-angle=gl"]

    if backend == "metal" or g_api == "Metal":
        if os_name == "macos":
            return ["--use-angle=metal"]
        return ["--use-angle=gl"]

    if backend == "d3d9" or g_api == "Direct3D9":
        if os_name == "windows":
            return ["--use-angle=d3d9"]
        return ["--use-angle=gl"]

    # Default Direct3D11 request:
    # On Windows hosts (or when explicitly testing Windows ANGLE flags), emit --use-angle=d3d11.
    # On macOS hosts without D3D11, fall back to --use-angle=metal (or gl).
    # On Linux hosts without D3D11, fall back to --use-angle=gl.
    if os_name == "windows":
        return ["--use-angle=d3d11"]
    if os_name == "macos":
        return ["--use-angle=metal"]
    return ["--use-angle=gl"]


def resolve_kernel_executable(
    kernel_type: str,
    kernels_dir: Path,
    host_os: Optional[str] = None,
    host_arch: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Resolves the executable path and WebDriver path for `taebrowser` (Chromium) or `yangbrowser` (Gecko)
    across Windows, macOS, and Linux (`x64`, `arm64`, `x86`).
    """
    os_name = normalize_host_os(host_os)
    arch_name = normalize_arch(host_arch)
    ktype = "yangbrowser" if (kernel_type or "").lower() in ("yangbrowser", "yang", "flowerbrowser", "firefox", "gecko") else "taebrowser"

    tae_dir = kernels_dir / "taebrowser_153"
    yang_dir = kernels_dir / "yangbrowser_153"

    if ktype == "yangbrowser":
        win_exe = yang_dir / "YangBrowser.exe"
        win_driver = yang_dir / "geckodriver.exe"
        mac_candidates = [
            yang_dir / "YangBrowser.app" / "Contents" / "MacOS" / "YangBrowser",
            yang_dir / "YangBrowser",
            Path("/Applications/YangBrowser.app/Contents/MacOS/YangBrowser"),
            Path("/Applications/Firefox.app/Contents/MacOS/firefox"),
            Path.home() / "Applications" / "Firefox.app" / "Contents" / "MacOS" / "firefox",
            Path("/opt/homebrew/bin/firefox"),
            Path("/usr/local/bin/firefox"),
        ]
        linux_candidates = [
            yang_dir / "yangbrowser",
            yang_dir / "YangBrowser",
            Path("/snap/bin/firefox"),
            Path("/var/lib/flatpak/exports/bin/org.mozilla.firefox"),
        ]
        if os.name != "nt":
            for bin_name in ("yangbrowser", "firefox", "firefox-esr"):
                found = shutil.which(bin_name)
                if found:
                    linux_candidates.insert(2, Path(found))

        if os_name == "windows":
            exe_path = win_exe
            drv_path = win_driver if win_driver.is_file() else (Path(shutil.which("geckodriver") or "") if shutil.which("geckodriver") else None)
        elif os_name == "macos":
            exe_path = next((p for p in mac_candidates if p.is_file()), win_exe if win_exe.is_file() else mac_candidates[0])
            drv_cand = yang_dir / "geckodriver"
            drv_path = drv_cand if drv_cand.is_file() else (Path(shutil.which("geckodriver") or "") if shutil.which("geckodriver") else (win_driver if win_driver.is_file() else None))
        else:
            exe_path = next((p for p in linux_candidates if p.is_file()), win_exe if win_exe.is_file() else linux_candidates[0])
            drv_cand = yang_dir / "geckodriver"
            drv_path = drv_cand if drv_cand.is_file() else (Path(shutil.which("geckodriver") or "") if shutil.which("geckodriver") else (win_driver if win_driver.is_file() else None))

        return {
            "kernel_type": "yangbrowser",
            "host_os": os_name,
            "host_arch": arch_name,
            "executable": str(exe_path),
            "executable_exists": exe_path.is_file(),
            "webdriver": str(drv_path) if drv_path and drv_path.is_file() else None,
        }

    # TaeBrowser (Chromium 153)
    win_exe = tae_dir / "TaeBrowser.exe"
    win_driver = tae_dir / "chromedriver.exe"
    mac_candidates = [
        tae_dir / "TaeBrowser.app" / "Contents" / "MacOS" / "TaeBrowser",
        tae_dir / "TaeBrowser",
        Path("/Applications/TaeBrowser.app/Contents/MacOS/TaeBrowser"),
        Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        Path("/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"),
        Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
        Path.home() / "Applications" / "Chromium.app" / "Contents" / "MacOS" / "Chromium",
        Path.home() / "Applications" / "Google Chrome.app" / "Contents" / "MacOS" / "Google Chrome",
        Path("/opt/homebrew/bin/chromium"),
        Path("/usr/local/bin/chromium"),
    ]
    linux_candidates = [
        tae_dir / "taebrowser",
        tae_dir / "TaeBrowser",
        Path("/snap/bin/chromium"),
        Path("/var/lib/flatpak/exports/bin/org.chromium.Chromium"),
    ]
    if os.name != "nt":
        for bin_name in (
            "taebrowser",
            "chromium",
            "chromium-browser",
            "google-chrome",
            "google-chrome-stable",
            "brave-browser",
            "microsoft-edge",
        ):
            found = shutil.which(bin_name)
            if found:
                linux_candidates.insert(2, Path(found))

    if os_name == "windows":
        exe_path = win_exe
        drv_path = win_driver if win_driver.is_file() else (Path(shutil.which("chromedriver") or "") if shutil.which("chromedriver") else None)
    elif os_name == "macos":
        exe_path = next((p for p in mac_candidates if p.is_file()), win_exe if win_exe.is_file() else mac_candidates[0])
        drv_cand = tae_dir / "chromedriver"
        drv_path = drv_cand if drv_cand.is_file() else (Path(shutil.which("chromedriver") or "") if shutil.which("chromedriver") else (win_driver if win_driver.is_file() else None))
    else:
        exe_path = next((p for p in linux_candidates if p.is_file()), win_exe if win_exe.is_file() else linux_candidates[0])
        drv_cand = tae_dir / "chromedriver"
        drv_path = drv_cand if drv_cand.is_file() else (Path(shutil.which("chromedriver") or "") if shutil.which("chromedriver") else (win_driver if win_driver.is_file() else None))

    return {
        "kernel_type": "taebrowser",
        "host_os": os_name,
        "host_arch": arch_name,
        "executable": str(exe_path),
        "executable_exists": exe_path.is_file(),
        "webdriver": str(drv_path) if drv_path and drv_path.is_file() else None,
    }


def build_process_spawn_command(
    executable: str,
    args: List[str],
    host_os: Optional[str] = None,
) -> List[str]:
    """
    Constructs the actual OS process spawn argv list.
    On macOS and Linux, if the resolved kernel executable is a Windows PE `.exe`
    (`TaeBrowser.exe` / `YangBrowser.exe`), automatically wraps it with `wine64` / `wine`
    when available, or raises a descriptive error guiding native browser installation.
    """
    os_name = normalize_host_os(host_os)
    exe_str = str(executable)
    if os_name in ("macos", "linux") and exe_str.lower().endswith(".exe"):
        if os.name != "nt":
            wine_bin = shutil.which("wine64") or shutil.which("wine")
            if wine_bin:
                return [wine_bin, exe_str] + list(args)
            raise RuntimeError(
                f"Cannot execute Windows PE binary '{Path(exe_str).name}' directly on {os_name} "
                f"without Wine or a native browser. Please install Chromium/Chrome or Firefox "
                f"(or install wine64)."
            )
    return [exe_str] + list(args)


def terminate_process_cross_platform(
    proc: subprocess.Popen,
    os_pid: int,
    host_os: Optional[str] = None,
) -> None:
    """
    Gracefully stops a browser process across Windows, macOS, and Linux so SQLite WAL cookies
    and session tabs flush cleanly before falling back to force-kill.
    """
    os_name = normalize_host_os(host_os)
    try:
        if proc.poll() is not None:
            return

        if os_name == "windows" and os.name == "nt":
            # 1. Request graceful close (WM_CLOSE) via taskkill without /F if parent is still running
            if proc.poll() is None:
                subprocess.run(
                    ["taskkill", "/PID", str(os_pid)],
                    capture_output=True,
                    timeout=3,
                    creationflags=get_subprocess_creationflags("windows"),
                )
                deadline = time.time() + 2.0
                while time.time() < deadline:
                    if proc.poll() is not None:
                        break
                    time.sleep(0.1)
            # 2. Always force-kill the process tree (/F /T) so no orphaned child renderer/crashhelper
            # holds Gecko parent.lock or Chromium SingletonLock when relaunching immediately.
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(os_pid)],
                capture_output=True,
                timeout=5,
                creationflags=get_subprocess_creationflags("windows"),
            )
        else:
            # POSIX (macOS / Linux): SIGTERM first, wait up to 3.0s, then SIGKILL
            try:
                os.kill(os_pid, signal.SIGTERM)
            except Exception:
                proc.terminate()
            deadline = time.time() + 3.0
            while time.time() < deadline:
                if proc.poll() is not None:
                    return
                time.sleep(0.15)
            if proc.poll() is None:
                sigkill = getattr(signal, "SIGKILL", signal.SIGTERM)
                try:
                    os.kill(os_pid, sigkill)
                except Exception:
                    proc.kill()
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    finally:
        try:
            proc.wait(timeout=2)
        except Exception:
            pass


def launch_desktop_gui_cross_platform(
    url: str,
    base_dir: Path,
    host_os: Optional[str] = None,
) -> Optional[subprocess.Popen]:
    """
    Launches the Free Proxy Browser desktop interface across Windows, macOS, and Linux:
      - Windows (`x64` / `ARM64` / `x86`): Spawns `FreeProxyBrowser.exe` (native WinForms + WebView2).
      - macOS (`arm64` / `x64`): Launches Chrome/Edge/Brave in `--app=<url>` desktop window mode or `open <url>`.
      - Linux (`x64` / `arm64`): Launches Chromium/Chrome in `--app=<url>` desktop window mode or `xdg-open <url>`.
    """
    os_name = normalize_host_os(host_os)

    if os_name == "windows" and os.name == "nt":
        exe_path = base_dir / "FreeProxyBrowser.exe"
        if not exe_path.is_file():
            exe_path = base_dir / "freeanti.exe"
        if exe_path.is_file():
            return subprocess.Popen([str(exe_path)], cwd=str(base_dir))

    if os_name == "macos":
        mac_app_browsers = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        ]
        for b_bin in mac_app_browsers:
            if Path(b_bin).is_file():
                return subprocess.Popen([b_bin, f"--app={url}", "--window-size=1480,920"])
        if shutil.which("open"):
            return subprocess.Popen(["open", url])

    if os_name == "linux":
        for b_name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "microsoft-edge"):
            found = shutil.which(b_name)
            if found:
                return subprocess.Popen([found, f"--app={url}", "--window-size=1480,920"])
        if shutil.which("xdg-open"):
            return subprocess.Popen(["xdg-open", url])

    webbrowser.open(url)
    return None
