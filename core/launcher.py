"""
Browser Process Launcher & Live Dynamic Config Manager for freeanti.
Spawns TaeBrowser 153 (`taebrowser_153/TaeBrowser.exe`) and YangBrowser 153 (`yangbrowser_153/YangBrowser.exe`)
with reverse-engineered `--extended-parameters` and MD5 sidecar files, tracks `BrowserMessage`
handshakes, and supports live runtime `dynamicConfig` hot-reloading.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .database import FreeAntiDatabase
from .extension_builder import ensure_freeanti_extension
from .fingerprint import (
    adspower_encode_base64,
    check_proxy_and_resolve_geo,
    compile_profile_configs,
    format_proxy_host_port,
    md5_hex,
    normalize_kernel_name,
    parse_proxy_string,
)
from .kernels import discover_kernels
from .platform_compat import (
    build_process_spawn_command,
    detect_host_platform,
    format_command_line,
    resolve_angle_flags,
    resolve_kernel_executable,
    terminate_process_cross_platform,
)


class BrowserLauncher:
    def __init__(self, data_dir: Path, db: FreeAntiDatabase, server_port: int = 50325) -> None:
        self.data_dir = data_dir
        self.profiles_dir = data_dir / "profiles"
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self.db = db
        self.server_port = server_port
        self.kernels_info = discover_kernels()
        self.freeanti_ext_dir = ensure_freeanti_extension(data_dir)
        self._active: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def refresh_kernels(self) -> Dict[str, Any]:
        self.kernels_info = discover_kernels()
        return self.kernels_info

    def get_profile_dir(self, profile: Dict[str, Any]) -> Path:
        pid = str(profile["id"])
        kernel_type = normalize_kernel_name(profile.get("kernel_type", "taebrowser"))
        suffix = "_yang" if kernel_type == "yangbrowser" else "_tae"
        return self.profiles_dir / f"{pid}{suffix}"

    def _has_saved_session(self, profile_dir: Path, kernel_type: str) -> bool:
        """
        Checks whether the profile directory already has saved session/tabs on disk
        (`Default/Sessions/Session_*` or `Tabs_*` for TaeBrowser,
        `sessionstore.jsonlz4` or `sessionstore-backups/` for YangBrowser).
        """
        if not profile_dir.is_dir():
            return False
        if kernel_type == "yangbrowser":
            if (profile_dir / "sessionstore.jsonlz4").is_file():
                return True
            sb = profile_dir / "sessionstore-backups"
            return sb.is_dir() and any(sb.iterdir())
        sessions_dir = profile_dir / "Default" / "Sessions"
        if sessions_dir.is_dir():
            try:
                return any(
                    f.is_file() and f.name.startswith(("Session_", "Tabs_")) and f.stat().st_size > 0
                    for f in sessions_dir.iterdir()
                )
            except Exception:
                return False
        return False

    def build_launch_plan(
        self,
        profile: Dict[str, Any],
        headless: bool = False,
        extra_args: Optional[List[str]] = None,
        write_files: bool = True,
        host_os: Optional[str] = None,
        host_arch: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Compiles all sidecars and returns the full launch command, arguments,
        environment variables, and compiled configurations across any target OS & CPU architecture.
        """
        plat = detect_host_platform(host_os, host_arch)
        pid = str(profile["id"])
        kernel_type = normalize_kernel_name(profile.get("kernel_type", "taebrowser"))
        fp = profile.get("fingerprint") or {}
        proxy = dict(profile.get("proxy") or {"type": "direct"})
        raw_phost = str(proxy.get("host") or "").strip()
        if raw_phost and ("://" in raw_phost or "@" in raw_phost or raw_phost.count(":") >= 1):
            parsed_prx = parse_proxy_string(raw_phost, str(proxy.get("type") or "socks5"))
            if parsed_prx["host"]:
                if proxy.get("type") in (None, "", "direct"):
                    proxy["type"] = parsed_prx["type"]
                proxy["host"] = parsed_prx["host"]
                if parsed_prx["port"]:
                    proxy["port"] = parsed_prx["port"]
                if parsed_prx["username"] and not proxy.get("username"):
                    proxy["username"] = parsed_prx["username"]
                if parsed_prx["password"] and not proxy.get("password"):
                    proxy["password"] = parsed_prx["password"]
        profile_dir = self.get_profile_dir(profile)

        # Extensions to load on TaeBrowser
        ext_paths: List[str] = []
        if kernel_type == "taebrowser":
            if fp.get("chrome_validation_headers", True):
                ext_paths.append(str(self.freeanti_ext_dir.resolve()))
            if fp.get("load_paste_assistant") and "paste_assistant" in self.kernels_info.get("extensions", {}):
                ext_paths.append(self.kernels_info["extensions"]["paste_assistant"]["path"])
            if fp.get("load_totp_authenticator") and "totp_authenticator" in self.kernels_info.get("extensions", {}):
                ext_paths.append(self.kernels_info["extensions"]["totp_authenticator"]["path"])

        compiled = compile_profile_configs(
            profile=profile,
            profile_dir=profile_dir,
            extension_paths=ext_paths,
            write_files=write_files,
        )

        resolved_loc = compiled.get("resolved_locale") or {}
        ui_lang = resolved_loc.get("ui_language") or fp.get("ui_language") or (fp.get("languages") or ["en-US"])[0]
        tz = str(resolved_loc.get("timezone") or fp.get("timezone") or "America/New_York").replace(" ", "_")
        ua = fp.get("user_agent") or ""
        os_platform = fp.get("os_platform", "Windows")
        screen_res = str(fp.get("screen_resolution", "1920_1080")).replace("_", ",")

        env_vars: Dict[str, str] = {
            "ISOLATE_DEFAULT_LOCALE": ui_lang,
            "TZ": tz,
        }

        has_saved_session = self._has_saved_session(profile_dir, kernel_type)
        startup_urls = list(profile.get("startup_urls") or [])
        if not startup_urls and not has_saved_session:
            startup_urls = [f"http://127.0.0.1:{self.server_port}/verify?profile_id={pid}"]

        args: List[str] = []
        executable = ""
        webdriver_path = None

        proxy_type = (proxy.get("type") or "direct").lower()
        proxy_host = proxy.get("host") or ""
        proxy_port = proxy.get("port") or ""

        kernels_dir = self.data_dir.parent / "kernels"
        resolved_k = resolve_kernel_executable(kernel_type, kernels_dir, plat["host_os"], plat["host_arch"])

        if kernel_type == "yangbrowser":
            yb_info = self.kernels_info.get("default_yangbrowser")
            if yb_info and not host_os and not host_arch and not plat["is_simulated"]:
                executable = yb_info["executable"]
                webdriver_path = yb_info.get("webdriver")
            else:
                executable = resolved_k["executable"]
                webdriver_path = resolved_k["webdriver"]
            env_vars["MOZ_CRASHREPORTER_NO_REPORT"] = "1"
            env_vars["MOZ_DISABLE_CONTENT_SANDBOX"] = "1"
            env_vars["MOZ_NO_REMOTE"] = "1"
            env_vars["MOZ_LEGACY_PROFILES"] = "1"
            if fp.get("gpu_mode") == "disabled":
                env_vars["MOZ_WEBRENDER"] = "0"
            args.extend(
                [
                    "-foreground",
                    "--marionette",
                    "--remote-debugging-port",
                    "0",
                    "--profile",
                    str(profile_dir.resolve()),
                    f"--lang={ui_lang}",
                ]
            )
            if proxy_type != "direct" and proxy_host and proxy_port:
                args.append(f"--proxy-server={proxy_type}://{format_proxy_host_port(proxy_host, proxy_port)}")
            args.append(compiled["extended_parameters_flag"])
            if headless:
                args.append("-headless")
        else:
            tb_info = self.kernels_info.get("default_taebrowser")
            if tb_info and not host_os and not host_arch and not plat["is_simulated"]:
                executable = tb_info["executable"]
                webdriver_path = tb_info.get("webdriver")
            else:
                executable = resolved_k["executable"]
                webdriver_path = resolved_k["webdriver"]

            args.extend(
                [
                    f"--user-data-dir={profile_dir.resolve()}",
                    f"--lang={ui_lang}",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-background-mode",
                    "--remote-debugging-port=0",
                    "--force-color-profile=srgb",
                ]
            )
            if plat["host_os"] == "macos":
                args.extend(["--use-mock-keychain", "--password-store=basic"])
            elif plat["host_os"] == "linux":
                args.extend(["--disable-dev-shm-usage", "--password-store=basic"])
            if has_saved_session and not startup_urls:
                args.append("--restore-last-session")
            if ua:
                args.append(f"--user-agent={ua}")

            if os_platform not in ("Android", "iPhone") and "," in screen_res:
                args.append(f"--window-size={screen_res}")

            if os_platform in ("Android", "iPhone"):
                args.append("--enable-blink-features=IdleDetection")
            else:
                args.append("--enable-blink-features=IdleDetection,Fledge")

            # Graphics Card (GPU) & OpenGL / ANGLE / Direct3D / Metal / Vulkan / WebGPU Flags
            gpu_mode = str(fp.get("gpu_mode") or "enabled").lower()
            angle_backend = str(fp.get("angle_backend") or "d3d11").lower()
            graphics_api = str(fp.get("graphics_api") or "Direct3D11")
            args.extend(
                resolve_angle_flags(
                    gpu_mode=gpu_mode,
                    angle_backend=angle_backend,
                    graphics_api=graphics_api,
                    host_os=plat["host_os"],
                    emulated_os=os_platform,
                )
            )

            if fp.get("webgpu_mode") == "disabled":
                args.append("--disable-features=Vulkan,WebGPU")

            # Proxy flag
            if proxy_type != "direct" and proxy_host and proxy_port:
                args.append(f"--proxy-server={proxy_type}://{format_proxy_host_port(proxy_host, proxy_port)}")

            # TLS Cipher Suite Blacklist
            if fp.get("tls_switch") and fp.get("tls_cipher_blacklist"):
                args.append(f"--cipher-suite-blacklist={fp['tls_cipher_blacklist']}")

            # Extensions
            if ext_paths:
                args.append(f"--load-extension={','.join(ext_paths)}")

            if headless:
                args.append("--headless=new")

            args.append(compiled["extended_parameters_flag"])

        if extra_args:
            args.extend(extra_args)

        args.extend(startup_urls)

        return {
            "host_platform": plat,
            "executable": executable,
            "executable_exists": Path(executable).is_file(),
            "webdriver": webdriver_path,
            "args": args,
            "command_line": format_command_line([executable] + args, host_os=plat["host_os"]),
            "env": env_vars,
            "compiled": compiled,
        }

    def start_profile(
        self,
        profile_id: str,
        headless: bool = False,
        extra_args: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Launches TaeBrowser 153 (`TaeBrowser.exe`) or YangBrowser 153 (`YangBrowser.exe`)
        for the given profile_id, waits up to 6 seconds for the C++ `BrowserMessage` /
        `DevToolsActivePort` / `stderr` handshake, and registers the active session.
        """
        profile = self.db.get_profile(profile_id)
        if not profile:
            raise ValueError(f"Profile '{profile_id}' not found")

        pid = str(profile["id"])
        ktype = normalize_kernel_name(profile.get("kernel_type", "taebrowser"))

        # Check if already active and alive
        with self._lock:
            if pid in self._active:
                proc: subprocess.Popen = self._active[pid]["proc"]
                if proc.poll() is None:
                    return self._format_active_info(pid)
                else:
                    del self._active[pid]

        # Auto-resolve live exit IP & GeoIP when launching through a SOCKS5/HTTP proxy
        prx = dict(profile.get("proxy") or {})
        fp = dict(profile.get("fingerprint") or {})
        if prx.get("type", "direct") != "direct" and prx.get("host") and prx.get("port"):
            geo = check_proxy_and_resolve_geo(proxy=prx)
            if geo.get("ok") and geo.get("source") == "proxy_tunnel_geoip":
                prx["exit_ip"] = geo["exit_ip"]
                prx["country"] = geo["country_code"]
                prx["timezone"] = geo["timezone"]
                prx["latitude"] = geo["latitude"]
                prx["longitude"] = geo["longitude"]
                fp["webrtc_public_ip"] = geo["exit_ip"]
                fp["proxy_country"] = geo["country_code"]
                if fp.get("follow_proxy_timezone", True):
                    fp["timezone"] = geo["timezone"]
                if fp.get("follow_proxy_language", True):
                    fp["languages"] = geo["languages"]
                if fp.get("follow_proxy_ui_language", True):
                    fp["ui_language"] = geo["ui_language"]
                if fp.get("follow_proxy_geolocation", True):
                    fp["latitude"] = geo["latitude"]
                    fp["longitude"] = geo["longitude"]
                updated = self.db.update_profile(pid, {"proxy": prx, "fingerprint": fp})
                if updated:
                    profile = updated

        plan = self.build_launch_plan(
            profile=profile,
            headless=headless,
            extra_args=extra_args,
            write_files=True,
        )
        if not plan["executable_exists"]:
            raise FileNotFoundError(f"Browser kernel executable not found: {plan['executable']}")

        profile_dir = Path(plan["compiled"]["profile_dir"])
        browser_msg_file = profile_dir / "BrowserMessage"
        devtools_port_file = profile_dir / "DevToolsActivePort"
        marionette_port_file = profile_dir / "MarionetteActivePort"
        bidi_server_file = profile_dir / "WebDriverBiDiServer.json"
        parent_lock_file = profile_dir / "parent.lock"
        singleton_lock_file = profile_dir / "SingletonLock"

        # Remove stale handshake and lock files before launch
        for f in (
            browser_msg_file,
            devtools_port_file,
            marionette_port_file,
            bidi_server_file,
            parent_lock_file,
            singleton_lock_file,
        ):
            try:
                if f.is_file() or f.is_symlink():
                    f.unlink()
            except Exception:
                pass

        full_env = os.environ.copy()
        full_env.update(plan["env"])

        spawn_argv = build_process_spawn_command(plan["executable"], plan["args"])
        proc = subprocess.Popen(
            spawn_argv,
            cwd=str(Path(plan["executable"]).parent),
            env=full_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )

        session_info: Dict[str, Any] = {
            "profile_id": pid,
            "serial_number": profile["serial_number"],
            "name": profile["name"],
            "kernel_type": ktype,
            "proc": proc,
            "pid": proc.pid,
            "debug_link": "",
            "debug_port": 0,
            "marionette_port": 0,
            "window_handle": "",
            "webdriver": plan["webdriver"],
            "profile_dir": str(profile_dir),
            "started_at": int(time.time()),
            "stderr_lines": [],
        }

        # Background thread to read stderr for MainWindowHandle, MarionettePort, DevTools listening
        def _stderr_reader() -> None:
            if not proc.stderr:
                return
            for line in proc.stderr:
                s = line.strip()
                if not s:
                    continue
                session_info["stderr_lines"].append(s)
                if "MainWindowHandle=" in s:
                    m = re.search(r"MainWindowHandle=(\S+)", s)
                    if m:
                        session_info["window_handle"] = m.group(1)
                if "DevTools listening on " in s or "WebDriver BiDi listening on " in s:
                    m = re.search(r"listening on (ws://\S+)", s)
                    if m:
                        session_info["debug_link"] = m.group(1)
                        pm = re.search(r":(\d+)", session_info["debug_link"])
                        if pm:
                            session_info["debug_port"] = int(pm.group(1))
                if "MarionettePort on " in s or "Marionette\tINFO\tListening on port " in s:
                    m = re.search(r"port\s+(\d+)|MarionettePort on\s+(\d+)", s)
                    if m:
                        port_str = m.group(1) or m.group(2)
                        session_info["marionette_port"] = int(port_str)

        t = threading.Thread(target=_stderr_reader, daemon=True)
        t.start()

        # Poll up to 6.0s for BrowserMessage or DevToolsActivePort or stderr handshake
        deadline = time.time() + 6.0
        while time.time() < deadline:
            if proc.poll() is not None:
                break
            if browser_msg_file.is_file():
                try:
                    bm = json.loads(browser_msg_file.read_text(encoding="utf-8", errors="ignore"))
                    if bm.get("debug_link"):
                        session_info["debug_link"] = bm["debug_link"]
                        pm = re.search(r":(\d+)", session_info["debug_link"])
                        if pm:
                            session_info["debug_port"] = int(pm.group(1))
                    if bm.get("marionette"):
                        session_info["marionette_port"] = int(bm["marionette"])
                    if bm.get("pid"):
                        session_info["pid"] = int(bm["pid"])
                except Exception:
                    pass
            if not session_info["debug_link"] and devtools_port_file.is_file():
                try:
                    lines = devtools_port_file.read_text(encoding="utf-8", errors="ignore").splitlines()
                    if len(lines) >= 2 and lines[0].strip().isdigit():
                        port = int(lines[0].strip())
                        path_part = lines[1].strip()
                        session_info["debug_port"] = port
                        session_info["debug_link"] = f"ws://127.0.0.1:{port}{path_part}"
                except Exception:
                    pass
            if not session_info["marionette_port"] and marionette_port_file.is_file():
                try:
                    m_txt = marionette_port_file.read_text(encoding="utf-8", errors="ignore").strip()
                    if m_txt.isdigit() and int(m_txt) > 0:
                        session_info["marionette_port"] = int(m_txt)
                except Exception:
                    pass
            if not session_info["debug_link"] and bidi_server_file.is_file():
                try:
                    bidi = json.loads(bidi_server_file.read_text(encoding="utf-8", errors="ignore"))
                    ws_host = str(bidi.get("ws_host") or "127.0.0.1").strip()
                    ws_port = int(bidi.get("ws_port") or 0)
                    if ws_port > 0:
                        session_info["debug_port"] = ws_port
                        session_info["debug_link"] = f"ws://{ws_host}:{ws_port}"
                except Exception:
                    pass
            if ktype == "yangbrowser":
                if session_info["debug_link"] and session_info["marionette_port"]:
                    break
            else:
                if session_info["debug_link"]:
                    break
            time.sleep(0.2)

        with self._lock:
            self._active[pid] = session_info

        if not headless and os.name == "nt":
            threading.Thread(
                target=self._apply_browser_window_icon,
                args=(session_info,),
                daemon=True,
            ).start()

        self.db.mark_launched(
            profile_id=pid,
            kernel_type=ktype,
            pid=session_info["pid"],
            debug_link=session_info["debug_link"],
            marionette_port=session_info["marionette_port"],
            window_handle=session_info["window_handle"],
            status="Active",
        )

        return self._format_active_info(pid)

    def _apply_browser_window_icon(self, session_info: Dict[str, Any]) -> None:
        """
        Applies the Free Proxy Browser custom window icon (ICON_SMALL & ICON_BIG)
        to the launched browser window on Windows via WM_SETICON.
        """
        try:
            import ctypes
            from ctypes import wintypes

            icon_path = self.data_dir.parent / "assets" / "icon.ico"
            if not icon_path.is_file():
                icon_path = self.data_dir.parent / "icon.ico"
            if not icon_path.is_file():
                return

            user32 = ctypes.windll.user32
            IMAGE_ICON = 1
            LR_LOADFROMFILE = 0x00000010
            WM_SETICON = 0x0080

            h_small = user32.LoadImageW(0, str(icon_path), IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
            h_big = user32.LoadImageW(0, str(icon_path), IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
            if not h_small and not h_big:
                return

            target_pid = int(session_info.get("pid") or 0)
            WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

            for _ in range(12):
                proc: subprocess.Popen = session_info.get("proc")  # type: ignore[assignment]
                if proc and proc.poll() is not None:
                    break

                hwnd_str = str(session_info.get("window_handle") or "").strip()
                if hwnd_str:
                    try:
                        hwnd_val = int(hwnd_str, 16) if hwnd_str.startswith("0x") else int(hwnd_str)
                        if hwnd_val:
                            if h_small:
                                user32.SendMessageW(hwnd_val, WM_SETICON, 0, h_small)
                            if h_big:
                                user32.SendMessageW(hwnd_val, WM_SETICON, 1, h_big)
                    except Exception:
                        pass

                def _enum_cb(hwnd: int, _lparam: int) -> bool:
                    if user32.IsWindowVisible(hwnd):
                        win_pid = wintypes.DWORD(0)
                        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(win_pid))
                        if win_pid.value == target_pid:
                            if h_small:
                                user32.SendMessageW(hwnd, WM_SETICON, 0, h_small)
                            if h_big:
                                user32.SendMessageW(hwnd, WM_SETICON, 1, h_big)
                    return True

                user32.EnumWindows(WNDENUMPROC(_enum_cb), 0)
                time.sleep(0.5)
        except Exception:
            pass

    def _format_active_info(self, pid: str) -> Dict[str, Any]:
        info = self._active.get(pid)
        if not info:
            return {"status": "Inactive", "profile_id": pid}
        proc: subprocess.Popen = info["proc"]
        alive = proc.poll() is None
        if not alive:
            return {"status": "Inactive", "profile_id": pid}

        debug_port = info.get("debug_port") or 0
        selenium_addr = f"127.0.0.1:{debug_port}" if debug_port else ""

        return {
            "status": "Active",
            "profile_id": pid,
            "user_id": pid,
            "serial_number": info["serial_number"],
            "name": info["name"],
            "kernel_type": info["kernel_type"],
            "pid": info["pid"],
            "window_handle": info["window_handle"],
            "debug_port": debug_port,
            "marionette_port": info["marionette_port"],
            "webdriver": info["webdriver"],
            "ws": {
                "puppeteer": info["debug_link"],
                "selenium": selenium_addr,
                "marionette": info["marionette_port"],
            },
            "started_at": info["started_at"],
        }

    def get_active_status(self, profile_id: str) -> Dict[str, Any]:
        profile = self.db.get_profile(profile_id)
        pid = str(profile["id"]) if profile else str(profile_id)
        with self._lock:
            if pid not in self._active:
                return {"status": "Inactive", "profile_id": pid}
            res = self._format_active_info(pid)
            if res["status"] == "Inactive":
                del self._active[pid]
            return res

    def list_active_profiles(self) -> List[Dict[str, Any]]:
        active_list: List[Dict[str, Any]] = []
        with self._lock:
            stale: List[str] = []
            for pid in list(self._active.keys()):
                res = self._format_active_info(pid)
                if res["status"] == "Active":
                    active_list.append(res)
                else:
                    stale.append(pid)
            for pid in stale:
                del self._active[pid]
        return active_list

    def stop_profile(self, profile_id: str) -> Dict[str, Any]:
        profile = self.db.get_profile(profile_id)
        pid = str(profile["id"]) if profile else str(profile_id)
        with self._lock:
            info = self._active.pop(pid, None)
        if not info:
            return {"stopped": False, "profile_id": pid, "message": "Profile is not running"}

        proc: subprocess.Popen = info["proc"]
        os_pid = int(info.get("pid") or proc.pid)
        terminate_process_cross_platform(proc, os_pid)
        return {"stopped": True, "profile_id": pid, "pid": os_pid}

    def stop_all_profiles(self) -> List[Dict[str, Any]]:
        with self._lock:
            pids = list(self._active.keys())
        return [self.stop_profile(pid) for pid in pids]

    def update_dynamic_config_live(
        self,
        profile_id: str,
        webrtc_public_ip: Optional[str] = None,
        webrtc_local_ip: Optional[str] = None,
        timezone: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        accuracy: Optional[int] = None,
        disable_webrtc: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Live-updates `<profile_dir>/<md5(id + "_webrtc")>` (Base64 JSON) while the browser
        is running! Both YangBrowser (`custom.dynamic::TimerCallbackHolder` in `xul.dll`)
        and TaeBrowser (`SunBrowserPolicys` in `chrome.dll`) poll this file periodically
        and hot-reload WebRTC IP, TimeZone, and Geolocation without restarting the browser.
        """
        profile = self.db.get_profile(profile_id)
        if not profile:
            raise ValueError(f"Profile '{profile_id}' not found")

        pid = str(profile["id"])
        fp = dict(profile["fingerprint"])
        if webrtc_public_ip is not None:
            fp["webrtc_public_ip"] = webrtc_public_ip
        if webrtc_local_ip is not None:
            fp["webrtc_local_ip"] = webrtc_local_ip
        if timezone is not None:
            fp["timezone"] = timezone
        if latitude is not None:
            fp["latitude"] = float(latitude)
        if longitude is not None:
            fp["longitude"] = float(longitude)
        if accuracy is not None:
            fp["accuracy"] = int(accuracy)
        if disable_webrtc is not None:
            fp["webrtc_mode"] = "disabled" if disable_webrtc else "proxy"

        self.db.update_profile(pid, {"fingerprint": fp})

        profile_dir = self.get_profile_dir(profile)
        profile_dir.mkdir(parents=True, exist_ok=True)
        dynamic_file = profile_dir / md5_hex(f"{pid}_webrtc")

        dynamic_payload: Dict[str, Any] = {
            "TimeZone": str(fp.get("timezone") or "America/New_York").replace(" ", "_"),
        }
        if fp.get("webrtc_mode") == "disabled":
            dynamic_payload["DisableWebRTC"] = True
        else:
            if fp.get("webrtc_public_ip"):
                dynamic_payload["WebRTCAddress"] = fp["webrtc_public_ip"]
            if fp.get("webrtc_local_ip"):
                dynamic_payload["WebRTCLocalAddress"] = fp["webrtc_local_ip"]

        if fp.get("geolocation_enabled", True) and fp.get("latitude") is not None and fp.get("longitude") is not None:
            dynamic_payload["Geoposition"] = f"{fp['latitude']},{fp['longitude']},{fp.get('accuracy', 50)}"

        dynamic_json = json.dumps(dynamic_payload, ensure_ascii=False)
        dynamic_b64 = adspower_encode_base64(dynamic_json)
        dynamic_file.write_text(dynamic_b64, encoding="utf-8")

        return {
            "profile_id": pid,
            "dynamic_file": str(dynamic_file.resolve()),
            "dynamicConfig": dynamic_payload,
            "encoded_b64": dynamic_b64,
        }

    def clear_profile_cache(self, profile_id: str) -> bool:
        profile = self.db.get_profile(profile_id)
        if not profile:
            return False
        self.stop_profile(profile["id"])
        profile_dir = self.get_profile_dir(profile)
        if profile_dir.is_dir():
            shutil.rmtree(profile_dir, ignore_errors=True)
        return True
