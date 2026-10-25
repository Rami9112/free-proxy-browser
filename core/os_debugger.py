"""
Continuous Cross-OS & Cross-Architecture Debugging Engine for Free Proxy Browser.
Verifies and self-heals runtime compatibility across:
  - Host Operating Systems : Windows (`windows`), macOS (`macos`), Linux (`linux`)
  - Host CPU Architectures : x64 (`x86_64` / `amd64`), ARM64 (`aarch64` / `arm64`), x86 (`i386` / `i686`)
  - Emulated Client OSes   : Windows, macOS, Linux, Android, iPhone
  - Browser Kernels        : TaeBrowser 153 (Chromium) & YangBrowser 153 (Gecko)
  - Graphics / GPU Modes   : Direct3D11, OpenGL, Metal, Vulkan, SwiftShader, Disabled
  - Proxy Geo-Sync Locales : US, KR, JP, DE, GB, SG
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .database import FreeAntiDatabase
from .extension_builder import compute_chrome_validation_headers, ensure_freeanti_extension
from .fingerprint import (
    adspower_decode_base64,
    build_default_user_agent,
    compute_audio_noise,
    compute_client_rect_fp,
    generate_fingerprint_profile,
    generate_local_webrtc_ip,
)
from .kernel_rebrander import ensure_rebranded_kernels
from .kernels import discover_kernels
from .launcher import BrowserLauncher
from .platform_compat import (
    SUPPORTED_ARCHES,
    SUPPORTED_EMULATED_OSES,
    SUPPORTED_HOST_OSES,
    detect_host_platform,
    format_command_line,
    resolve_angle_flags,
    resolve_curl_executable,
    resolve_kernel_executable,
)

GPU_TEST_MODES: List[Dict[str, str]] = [
    {"gpu_mode": "enabled", "graphics_api": "Direct3D11", "angle_backend": "d3d11"},
    {"gpu_mode": "enabled", "graphics_api": "OpenGL", "angle_backend": "gl"},
    {"gpu_mode": "enabled", "graphics_api": "Metal", "angle_backend": "metal"},
    {"gpu_mode": "enabled", "graphics_api": "SwiftShader", "angle_backend": "swiftshader"},
    {"gpu_mode": "disabled", "graphics_api": "Direct3D11", "angle_backend": "d3d11"},
]

PROXY_TEST_COUNTRIES: List[Tuple[str, str, str]] = [
    ("US", "America/New_York", "en-US"),
    ("KR", "Asia/Seoul", "ko-KR"),
    ("JP", "Asia/Tokyo", "ja-JP"),
    ("DE", "Europe/Berlin", "de-DE"),
    ("GB", "Europe/London", "en-GB"),
    ("SG", "Asia/Singapore", "en-US"),
]


class CrossPlatformDebugger:
    """
    Executes single-pass or continuous infinite-loop verification & self-healing
    across all OS and CPU architecture combinations.
    """

    def __init__(
        self,
        base_dir: Path,
        data_dir: Path,
        db: FreeAntiDatabase,
        launcher: BrowserLauncher,
    ) -> None:
        self.base_dir = base_dir
        self.data_dir = data_dir
        self.db = db
        self.launcher = launcher
        self.status_file = data_dir / "os_debug_status.json"
        self.log_file = data_dir / "os_debug_loop.log"
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._state: Dict[str, Any] = {
            "running": False,
            "started_at": None,
            "last_cycle_at": None,
            "cycle_count": 0,
            "total_checks_run": 0,
            "total_passed": 0,
            "total_failed": 0,
            "total_repaired": 0,
            "host_platform": detect_host_platform(),
            "last_cycle_report": None,
            "recent_errors": [],
        }

    def stop(self) -> None:
        self._stop_event.set()

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            snap = dict(self._state)
        if not snap.get("running") and self.status_file.is_file():
            try:
                disk_state = json.loads(self.status_file.read_text(encoding="utf-8", errors="ignore"))
                if isinstance(disk_state, dict):
                    return disk_state
            except Exception:
                pass
        return snap

    def _append_log(self, line: str) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        entry = f"[{ts}] {line}\n"
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            with self.log_file.open("a", encoding="utf-8") as f:
                f.write(entry)
        except Exception:
            pass

    def _save_status(self) -> None:
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            with self._lock:
                payload = json.dumps(self._state, indent=2, ensure_ascii=False)
            self.status_file.write_text(payload, encoding="utf-8")
        except Exception:
            pass

    def self_heal_environment(self) -> List[str]:
        """
        Inspects and automatically repairs missing runtime artifacts, extension files,
        kernel zpart archives, and POSIX executable permissions.
        """
        repairs: List[str] = []
        kernels_dir = self.base_dir / "kernels"

        # 1. Ensure .zpart00 chunks and rebranded kernels are unpacked
        cwd_global = Path(detect_host_platform()["appdata_dir"])
        ensure_rebranded_kernels(self.base_dir, cwd_global)

        # 2. Ensure stealth extension exists
        ext_dir = self.data_dir / "extensions" / "freeanti_assistant"
        if not (ext_dir / "manifest.json").is_file() or not (ext_dir / "background.mjs").is_file():
            ensure_freeanti_extension(self.data_dir)
            repairs.append("Rebuilt missing stealth extension (freeanti_assistant)")

        # 3. On POSIX (macOS / Linux), ensure kernel binaries & drivers have +x permission
        if os.name != "nt" and kernels_dir.is_dir():
            for bin_cand in (
                kernels_dir / "taebrowser_153" / "TaeBrowser.exe",
                kernels_dir / "taebrowser_153" / "TaeBrowser",
                kernels_dir / "taebrowser_153" / "taebrowser",
                kernels_dir / "taebrowser_153" / "chromedriver",
                kernels_dir / "yangbrowser_153" / "YangBrowser.exe",
                kernels_dir / "yangbrowser_153" / "YangBrowser",
                kernels_dir / "yangbrowser_153" / "yangbrowser",
                kernels_dir / "yangbrowser_153" / "geckodriver",
                self.base_dir / "free_proxy_browser.py",
                self.base_dir / "freeanti.py",
            ):
                if bin_cand.is_file():
                    try:
                        mode = bin_cand.stat().st_mode
                        if not (mode & stat.S_IXUSR):
                            bin_cand.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                            repairs.append(f"Granted +x permission on {bin_cand.name}")
                    except Exception:
                        pass

        # 4. Ensure at least default profiles exist in SQLite DB
        profiles = self.db.list_profiles()
        if not profiles:
            self.db._seed_defaults_if_empty()
            repairs.append("Reseeded default profiles in SQLite database")

        return repairs

    def run_single_cycle(
        self,
        cycle_number: int = 1,
        live_spawn: bool = False,
    ) -> Dict[str, Any]:
        """
        Runs one full verification & self-healing pass across:
          1. Self-healing environment checks
          2. All 9 (Host OS × Host CPU Architecture) combinations
          3. All 10 (Kernel × Emulated Client OS) combinations across host OSes
          4. All 5 GPU / ANGLE rendering modes across Windows, macOS, and Linux hosts
          5. All 6 Proxy Country Geo-Sync auto-follow locales
          6. Optional live headless browser launch & handshake test
        """
        t0 = time.perf_counter()
        checks_run = 0
        passed = 0
        failed = 0
        failures: List[Dict[str, Any]] = []
        matrix_results: List[Dict[str, Any]] = []

        def record_check(name: str, ok: bool, detail: str = "", meta: Optional[Dict[str, Any]] = None) -> None:
            nonlocal checks_run, passed, failed
            checks_run += 1
            if ok:
                passed += 1
            else:
                failed += 1
                failures.append({"check": name, "detail": detail, "meta": meta or {}})

        # Phase 0: Self-heal environment
        repairs = self.self_heal_environment()

        # Phase 1: Host OS × Host Architecture Matrix (3 OS × 3 Arch = 9 combinations)
        kernels_dir = self.base_dir / "kernels"
        for h_os in SUPPORTED_HOST_OSES:
            for h_arch in SUPPORTED_ARCHES:
                plat = detect_host_platform(override_os=h_os, override_arch=h_arch)
                ok_plat = (
                    plat["host_os"] == h_os
                    and plat["host_arch"] == h_arch
                    and plat["platform_tag"] == f"{h_os}-{h_arch}"
                    and bool(plat["curl_executable"])
                    and bool(plat["appdata_dir"])
                )
                record_check(
                    f"host_platform[{h_os}-{h_arch}]",
                    ok_plat,
                    f"platform_tag={plat.get('platform_tag')}",
                )

                for ktype in ("taebrowser", "yangbrowser"):
                    rk = resolve_kernel_executable(ktype, kernels_dir, host_os=h_os, host_arch=h_arch)
                    cmd_str = format_command_line([rk["executable"], "--headless=new", "--lang=en-US"], host_os=h_os)
                    ok_rk = (
                        rk["host_os"] == h_os
                        and rk["host_arch"] == h_arch
                        and bool(rk["executable"])
                        and len(cmd_str) > 10
                    )
                    record_check(
                        f"kernel_resolve[{h_os}-{h_arch}:{ktype}]",
                        ok_rk,
                        f"exe={rk['executable']}",
                    )

        # Phase 2: Cross-OS × Emulated-OS × Kernel Sidecar & Launch Plan Matrix
        with tempfile.TemporaryDirectory(prefix="freeanti_os_dbg_") as tmp_root:
            tmp_dir = Path(tmp_root)
            for h_os in SUPPORTED_HOST_OSES:
                h_arch = "arm64" if h_os == "macos" else "x64"
                for ktype in ("taebrowser", "yangbrowser"):
                    for emu_os in SUPPORTED_EMULATED_OSES:
                        prof_id = f"dbg_{h_os[:3]}_{ktype[:3]}_{emu_os.lower()}"
                        fp = generate_fingerprint_profile(
                            profile_id=prof_id,
                            kernel_type=ktype,
                            os_platform=emu_os,
                        )
                        prof = {
                            "id": prof_id,
                            "serial_number": 900,
                            "name": f"Debug {h_os}/{h_arch} -> {emu_os} ({ktype})",
                            "kernel_type": ktype,
                            "os_platform": emu_os,
                            "proxy": {"type": "direct", "host": "", "port": 0},
                            "fingerprint": fp,
                            "cookies": [],
                            "startup_urls": [],
                        }
                        # Temporarily redirect profile dir into temp directory for clean testing
                        orig_profiles_dir = self.launcher.profiles_dir
                        try:
                            self.launcher.profiles_dir = tmp_dir
                            plan = self.launcher.build_launch_plan(
                                profile=prof,
                                headless=True,
                                write_files=True,
                                host_os=h_os,
                                host_arch=h_arch,
                            )
                        finally:
                            self.launcher.profiles_dir = orig_profiles_dir

                        compiled = plan["compiled"]
                        sc = compiled["sidecar_files"]
                        static_path = Path(sc["static_config"]["path"])
                        dynamic_path = Path(sc["dynamic_config"]["path"])
                        webgl_path = Path(sc["webgl_fp"]["path"])

                        # Verify sidecars exist and roundtrip decode cleanly
                        static_decoded = json.loads(
                            adspower_decode_base64(static_path.read_text(encoding="utf-8"))
                        )
                        dynamic_decoded = json.loads(
                            adspower_decode_base64(dynamic_path.read_text(encoding="utf-8"))
                        )
                        webgl_decoded = json.loads(webgl_path.read_text(encoding="utf-8"))
                        val_hdr = compiled["chromeValidationHeaders"]

                        ok_plan = (
                            plan["host_platform"]["host_os"] == h_os
                            and plan["host_platform"]["host_arch"] == h_arch
                            and "--lang=en-US" in plan["args"]
                            and plan["env"]["TZ"] == "America/New_York"
                            and static_decoded.get("Langs") == "en-US,en"
                            and dynamic_decoded.get("TimeZone") == "America/New_York"
                            and "UNMASKED_VENDOR_WEBGL" in webgl_decoded
                            and len(val_hdr.get("x-browser-validation", "")) == 28
                        )
                        if ktype == "yangbrowser":
                            prefs_file = Path(compiled["profile_dir"]) / "prefs.js"
                            ok_plan = ok_plan and prefs_file.is_file() and "general.useragent.override" in prefs_file.read_text(encoding="utf-8")

                        record_check(
                            f"launch_plan[{h_os}-{h_arch}:{ktype}:{emu_os}]",
                            ok_plan,
                            f"cmd_len={len(plan['command_line'])}",
                        )
                        matrix_results.append(
                            {
                                "host": f"{h_os}-{h_arch}",
                                "kernel": ktype,
                                "emulated_os": emu_os,
                                "ok": ok_plan,
                                "validation_seed": val_hdr.get("os_seed_key"),
                            }
                        )

            # Phase 3: GPU / ANGLE Backend Resolution across Windows, macOS, and Linux
            for h_os in SUPPORTED_HOST_OSES:
                for g_cfg in GPU_TEST_MODES:
                    flags = resolve_angle_flags(
                        gpu_mode=g_cfg["gpu_mode"],
                        angle_backend=g_cfg["angle_backend"],
                        graphics_api=g_cfg["graphics_api"],
                        host_os=h_os,
                    )
                    if g_cfg["gpu_mode"] == "disabled":
                        ok_gpu = "--disable-gpu" in flags
                    elif g_cfg["angle_backend"] == "swiftshader":
                        ok_gpu = "--use-angle=swiftshader" in flags
                    elif g_cfg["angle_backend"] == "gl":
                        ok_gpu = "--use-angle=gl" in flags
                    elif g_cfg["angle_backend"] == "metal":
                        expected = "--use-angle=metal" if h_os == "macos" else "--use-angle=gl"
                        ok_gpu = expected in flags
                    else:
                        expected = (
                            "--use-angle=d3d11"
                            if h_os == "windows"
                            else "--use-angle=metal"
                            if h_os == "macos"
                            else "--use-angle=gl"
                        )
                        ok_gpu = expected in flags
                    record_check(
                        f"gpu_angle[{h_os}:{g_cfg['graphics_api']}/{g_cfg['angle_backend']}]",
                        ok_gpu,
                        f"flags={flags}",
                    )

            # Phase 4: Proxy Geo-Sync Auto-Follow across Countries
            for cc, expected_tz, expected_ui_lang in PROXY_TEST_COUNTRIES:
                prof_cc = {
                    "id": f"dbg_prx_{cc.lower()}",
                    "serial_number": 950,
                    "name": f"Proxy Geo Test {cc}",
                    "kernel_type": "taebrowser",
                    "os_platform": "Windows",
                    "proxy": {
                        "type": "socks5",
                        "host": "127.0.0.1",
                        "port": 1080,
                        "country": cc,
                        "exit_ip": "198.51.100.88",
                    },
                    "fingerprint": {
                        "proxy_country": cc,
                        "follow_proxy_timezone": True,
                        "follow_proxy_language": True,
                        "follow_proxy_ui_language": True,
                        "follow_proxy_geolocation": True,
                        "geolocation_enabled": True,
                    },
                }
                plan_cc = self.launcher.build_launch_plan(prof_cc, write_files=False)
                loc = plan_cc["compiled"]["resolved_locale"]
                ok_cc = (
                    loc["proxy_country"] == cc
                    and loc["timezone"] == expected_tz
                    and loc["ui_language"] == expected_ui_lang
                    and f"--lang={expected_ui_lang}" in plan_cc["args"]
                    and plan_cc["env"]["TZ"] == expected_tz
                )
                record_check(
                    f"proxy_geosync[{cc}]",
                    ok_cc,
                    f"tz={loc['timezone']}, ui_lang={loc['ui_language']}",
                )

        # Phase 5: Optional Live Browser Headless Spawn Check on Real Host
        live_spawn_results: Dict[str, Any] = {}
        if live_spawn:
            for pid, kname in (("fa1001win", "taebrowser"), ("fa1002flw", "yangbrowser")):
                prof_obj = self.db.get_profile(pid)
                if not prof_obj:
                    continue
                try:
                    sess = self.launcher.start_profile(pid, headless=True)
                    ok_live = sess.get("status") == "Active" and int(sess.get("pid") or 0) > 0
                    live_spawn_results[kname] = {
                        "ok": ok_live,
                        "pid": sess.get("pid"),
                        "debug_port": sess.get("debug_port"),
                        "marionette_port": sess.get("marionette_port"),
                    }
                    record_check(f"live_spawn[{kname}]", ok_live, f"pid={sess.get('pid')}")
                except Exception as exc:
                    live_spawn_results[kname] = {"ok": False, "error": str(exc)}
                    record_check(f"live_spawn[{kname}]", False, str(exc))
                finally:
                    try:
                        self.launcher.stop_profile(pid)
                    except Exception:
                        pass

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        now_iso = datetime.now(timezone.utc).isoformat()

        report: Dict[str, Any] = {
            "cycle": cycle_number,
            "timestamp": now_iso,
            "elapsed_ms": elapsed_ms,
            "host_platform": detect_host_platform(),
            "checks_run": checks_run,
            "passed": passed,
            "failed": failed,
            "all_passed": failed == 0,
            "repairs": repairs,
            "live_spawn": live_spawn_results,
            "failures": failures,
            "matrix_count": len(matrix_results),
        }

        with self._lock:
            self._state["last_cycle_at"] = now_iso
            self._state["cycle_count"] = cycle_number
            self._state["total_checks_run"] += checks_run
            self._state["total_passed"] += passed
            self._state["total_failed"] += failed
            self._state["total_repaired"] += len(repairs)
            self._state["last_cycle_report"] = report
            if failures:
                self._state["recent_errors"] = (self._state["recent_errors"] + failures)[-20:]

        self._save_status()
        status_tag = "PASS" if failed == 0 else f"FAIL({failed})"
        self._append_log(
            f"Cycle #{cycle_number} [{status_tag}] host={report['host_platform']['platform_tag']} "
            f"checks={passed}/{checks_run} repairs={len(repairs)} elapsed={elapsed_ms}ms"
        )
        return report

    def run_loop(
        self,
        interval_sec: float = 5.0,
        max_cycles: int = 0,
        live_spawn_every: int = 0,
        on_cycle: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """
        Runs the continuous OS & Architecture debugging loop until `max_cycles` is reached
        (when `max_cycles > 0`) or infinitely (`max_cycles == 0`) until stopped.
        """
        self._stop_event.clear()
        started_iso = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._state["running"] = True
            self._state["started_at"] = started_iso
        self._save_status()
        self._append_log(
            f"=== OS & Architecture Infinite Debugging Loop Started "
            f"(host={detect_host_platform()['platform_tag']}, interval={interval_sec}s, max_cycles={max_cycles or 'INF'}) ==="
        )

        cycle = 0
        last_report: Dict[str, Any] = {}
        try:
            while not self._stop_event.is_set():
                cycle += 1
                do_live = bool(live_spawn_every > 0 and (cycle == 1 or cycle % live_spawn_every == 0))
                try:
                    last_report = self.run_single_cycle(cycle_number=cycle, live_spawn=do_live)
                except Exception as exc:
                    tb = traceback.format_exc()
                    self._append_log(f"Cycle #{cycle} EXCEPTION: {exc}\n{tb}")
                    with self._lock:
                        self._state["total_failed"] += 1
                        self._state["recent_errors"] = (
                            self._state["recent_errors"] + [{"cycle": cycle, "error": str(exc)}]
                        )[-20:]
                    self._save_status()

                if on_cycle and last_report:
                    on_cycle(last_report)

                if max_cycles > 0 and cycle >= max_cycles:
                    break

                if self._stop_event.wait(timeout=max(0.2, interval_sec)):
                    break
        finally:
            with self._lock:
                self._state["running"] = False
            self._save_status()
            self._append_log(f"=== OS & Architecture Debugging Loop Stopped after {cycle} cycles ===")

        return self.get_status()
