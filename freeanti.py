#!/usr/bin/env python3
"""
freeanti — Standalone WebView2 Anti-Detect Browser Desktop Application & Local API Server
Supports rebranded TaeBrowser 153 (`TaeBrowser.exe`) and YangBrowser 153 (`YangBrowser.exe`).
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any, Dict

# Ensure UTF-8 stdout on Windows PowerShell/CMD
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.database import FreeAntiDatabase
from core.extension_builder import compute_chrome_validation_headers
from core.fingerprint import (
    adspower_decode_base64,
    compute_audio_noise,
    compute_client_rect_fp,
    generate_local_webrtc_ip,
    normalize_kernel_name,
)
from core.launcher import BrowserLauncher
from core.server import create_http_server


def get_app_context(port: int = 50325) -> tuple[Path, FreeAntiDatabase, BrowserLauncher]:
    data_dir = BASE_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db = FreeAntiDatabase(data_dir / "freeanti.db")
    launcher = BrowserLauncher(data_dir=data_dir, db=db, server_port=port)
    return data_dir, db, launcher


def _is_port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex((host, port)) == 0


def cmd_gui(args: argparse.Namespace) -> int:
    """
    Launches the native Microsoft Edge WebView2 Desktop Application window (`freeanti.exe`),
    backed by the embedded Local API & Control Server on 127.0.0.1:50325.
    """
    import subprocess

    host = args.host or "127.0.0.1"
    port = args.port or 50325
    srv = None

    if not _is_port_in_use(host, port):
        _, db, launcher = get_app_context(port)
        ui_dir = BASE_DIR / "ui"
        srv = create_http_server(host, port, db, launcher, ui_dir)
        srv_thread = threading.Thread(target=srv.serve_forever, daemon=True)
        srv_thread.start()

    exe_path = BASE_DIR / "FreeProxyBrowser.exe"
    if not exe_path.is_file():
        exe_path = BASE_DIR / "freeanti.exe"
    url = f"http://{host}:{port}/"

    try:
        if exe_path.is_file():
            proc = subprocess.Popen([str(exe_path)], cwd=str(BASE_DIR))
            proc.wait()
        else:
            webbrowser.open(url)
            if srv is not None:
                while True:
                    time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        if srv is not None:
            try:
                srv.shutdown()
                srv.server_close()
            except Exception:
                pass
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    _, db, launcher = get_app_context(args.port)
    kernels = launcher.kernels_info
    profiles = db.list_profiles()

    print("=" * 80)
    print("  Free Proxy Browser v2.1.0 — WebView2 Anti-Detect & Proxy Browser Engine Status")
    print("=" * 80)
    print(f"  Data Directory  : {BASE_DIR / 'data'}")
    print(f"  SQLite DB       : {BASE_DIR / 'data' / 'freeanti.db'} ({len(profiles)} profiles)")
    print(f"  Stealth Ext     : {launcher.freeanti_ext_dir}")
    print("-" * 80)

    tb = kernels.get("default_taebrowser")
    if tb:
        print(f"  [OK] TaeBrowser 153    : {tb['executable']}")
        print(f"       Chromium Version  : {tb['chromium_version']} (update_key={tb['update_version_key']})")
        print(f"       ChromeDriver      : {tb['webdriver']}")
    else:
        print("  [!!] TaeBrowser 153    : Not Found")

    yb = kernels.get("default_yangbrowser")
    if yb:
        print(f"  [OK] YangBrowser 153   : {yb['executable']}")
        print(f"       Gecko Version     : {yb['gecko_version']} (BuildID={yb['build_id']})")
        print(f"       GeckoDriver       : {yb['webdriver']}")
    else:
        print("  [!!] YangBrowser 153   : Not Found")

    print("-" * 80)
    print("  Profiles:")
    for p in profiles:
        fp = p.get("fingerprint", {})
        print(
            f"    #{p['serial_number']:<2} [{p['id']}] {p['name']:<44} "
            f"| {p['kernel_type']:<12} | {p['os_platform']:<7} | WebRTC: {fp.get('webrtc_local_ip')}"
        )
    print("=" * 80)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    _, db, _ = get_app_context(args.port)
    profiles = db.list_profiles(kernel_type=args.kernel, search=args.search)
    if args.json:
        print(json.dumps(profiles, indent=2, ensure_ascii=False))
        return 0

    print(f"{'#':<4} {'ID':<12} {'Kernel':<14} {'OS':<9} {'Screen':<11} {'Name'}")
    print("-" * 80)
    for p in profiles:
        fp = p.get("fingerprint", {})
        print(
            f"{p['serial_number']:<4} {p['id']:<12} {p['kernel_type']:<14} "
            f"{p['os_platform']:<9} {fp.get('screen_resolution', ''):<11} {p['name']}"
        )
    return 0


def cmd_create(args: argparse.Namespace) -> int:
    _, db, _ = get_app_context(args.port)
    payload: Dict[str, Any] = {
        "name": args.name,
        "kernel_type": normalize_kernel_name(args.kernel),
        "os_platform": args.os,
        "notes": args.notes or "",
        "fingerprint": {},
        "proxy": {"type": args.proxy_type, "host": args.proxy_host or "", "port": args.proxy_port or 0},
    }
    if args.webrtc_ip:
        payload["fingerprint"]["webrtc_public_ip"] = args.webrtc_ip
    if args.timezone:
        payload["fingerprint"]["timezone"] = args.timezone

    prof = db.create_profile(payload)
    print(f"[+] Created profile #{prof['serial_number']} [{prof['id']}] — {prof['name']}")
    print(json.dumps(prof, indent=2, ensure_ascii=False))
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    _, db, launcher = get_app_context(args.port)
    prof = db.get_profile(args.profile_id)
    if not prof:
        print(f"[-] Profile '{args.profile_id}' not found.", file=sys.stderr)
        return 1

    plan = launcher.build_launch_plan(prof, write_files=True)
    out = {
        "profile_id": prof["id"],
        "name": prof["name"],
        "kernel_type": prof["kernel_type"],
        "os_platform": prof["os_platform"],
        "executable": plan["executable"],
        "command_line": plan["command_line"],
        "sidecar_files": plan["compiled"]["sidecar_files"],
        "sunBrowserParams": plan["compiled"]["sunBrowserParams"],
        "staticConfig": plan["compiled"]["staticConfig"],
        "dynamicConfig": plan["compiled"]["dynamicConfig"],
        "webglConfig": plan["compiled"]["webglConfig"],
        "chromeValidationHeaders": plan["compiled"]["chromeValidationHeaders"],
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    _, _, launcher = get_app_context(args.port)
    try:
        info = launcher.start_profile(args.profile_id, headless=args.headless)
        print(json.dumps(info, indent=2, ensure_ascii=False))
        return 0
    except Exception as e:
        print(f"[-] Launch failed: {e}", file=sys.stderr)
        return 1


def cmd_stop(args: argparse.Namespace) -> int:
    _, _, launcher = get_app_context(args.port)
    res = launcher.stop_profile(args.profile_id)
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0


def cmd_dynamic_update(args: argparse.Namespace) -> int:
    _, _, launcher = get_app_context(args.port)
    res = launcher.update_dynamic_config_live(
        profile_id=args.profile_id,
        webrtc_public_ip=args.ip,
        webrtc_local_ip=args.local_ip,
        timezone=args.tz,
        latitude=args.lat,
        longitude=args.lon,
    )
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    _, db, launcher = get_app_context(args.port)
    ui_dir = BASE_DIR / "ui"
    srv = create_http_server(args.host, args.port, db, launcher, ui_dir)
    url = f"http://{args.host}:{args.port}"
    print("=" * 78)
    print(f"  🚀 Free Proxy Browser Server & Control Center Running at {url}")
    print(f"  🧪 Live Fingerprint Verification Page: {url}/verify")
    print(f"  🔌 Local API v1/v2 Compatible: {url}/api/v1/* & {url}/api/v2/*")
    print("=" * 78)

    if not getattr(args, "no_open", False):
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()

    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[!] Shutting down Free Proxy Browser server...")
        srv.server_close()
    return 0


def cmd_test(args: argparse.Namespace) -> int:
    """
    Runs an automated end-to-end verification suite of all components in `Free Proxy Browser`,
    including rebranded `TaeBrowser.exe` and `YangBrowser.exe`.
    """
    print("=" * 80)
    print("  🧪 Running Free Proxy Browser v2.1 End-to-End Verification Suite (TaeBrowser & YangBrowser)")
    print("=" * 80)

    _, db, launcher = get_app_context(port=50399)

    # Test 1: Rebranded Kernel & Extension Discovery
    kernels = launcher.kernels_info
    tb = kernels.get("default_taebrowser")
    yb = kernels.get("default_yangbrowser")
    assert tb is not None and Path(tb["executable"]).name == "TaeBrowser.exe", "TaeBrowser.exe must exist"
    assert yb is not None and Path(yb["executable"]).name == "YangBrowser.exe", "YangBrowser.exe must exist"
    print(
        f"  [PASS] 1. Rebranded Kernels Ready: TaeBrowser ({tb['chromium_version']}) "
        f"& YangBrowser ({yb['gecko_version']})"
    )

    # Test 2: Google Chrome x-browser-validation SHA-1 Header Calculation
    sample_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
    val_hdr = compute_chrome_validation_headers(sample_ua)
    assert val_hdr["os_seed_key"] == "WINDOWS"
    assert len(val_hdr["x-browser-validation"]) == 28
    assert val_hdr["x-browser-year"] == "2025"
    print(f"  [PASS] 2. Google Chrome x-browser-validation SHA-1 Forger -> {val_hdr['x-browser-validation']}")

    # Test 3: Deterministic Fingerprint Math
    rect_delta = compute_client_rect_fp("fa1001win")
    local_ip = generate_local_webrtc_ip("fa1001win")
    audio_fp = compute_audio_noise("fa1001win")
    assert -10000 <= rect_delta <= 10000
    assert local_ip.startswith(("192.168.", "172.16."))
    assert audio_fp > 0
    print(f"  [PASS] 3. Deterministic Fingerprint Seeds -> ClientRectFp={rect_delta}, AudioFp={audio_fp}, LocalWebRTC={local_ip}")

    # Test 4: Compile Sidecars for TaeBrowser 153 & YangBrowser 153
    tae_prof = db.get_profile("fa1001win")
    yang_prof = db.get_profile("fa1002flw")
    assert tae_prof and yang_prof
    assert tae_prof["kernel_type"] == "taebrowser"
    assert yang_prof["kernel_type"] == "yangbrowser"

    tae_plan = launcher.build_launch_plan(tae_prof, write_files=True)
    yang_plan = launcher.build_launch_plan(yang_prof, write_files=True)

    assert Path(tae_plan["executable"]).name == "TaeBrowser.exe"
    assert Path(yang_plan["executable"]).name == "YangBrowser.exe"
    assert "--lang=en-US" in tae_plan["args"], "Default UI language must be en-US"
    assert tae_plan["env"]["TZ"] == "America/New_York", "Default timezone must be America/New_York"
    assert tae_plan["compiled"]["staticConfig"]["Langs"] == "en-US,en", "Default browser languages must be en-US,en"

    tae_sc = tae_plan["compiled"]["sidecar_files"]
    assert Path(tae_sc["static_config"]["path"]).is_file()
    assert Path(tae_sc["dynamic_config"]["path"]).is_file()
    assert Path(tae_sc["webgl_fp"]["path"]).is_file()

    decoded_static = json.loads(
        adspower_decode_base64(Path(tae_sc["static_config"]["path"]).read_text(encoding="utf-8"))
    )
    assert "CanvasMarkEx" in decoded_static
    assert "UserAgentMetadata" in decoded_static
    print(f"  [PASS] 4. Compiled TaeBrowser 153 MD5 Sidecars ({tae_sc['static_config']['filename']}, {tae_sc['dynamic_config']['filename']})")

    yang_dir = Path(yang_plan["compiled"]["profile_dir"])
    prefs_js = (yang_dir / "prefs.js").read_text(encoding="utf-8")
    assert 'user_pref("general.platform.override", "MacIntel");' in prefs_js
    assert 'user_pref("webgl.override-unmasked-vendor"' in prefs_js
    print("  [PASS] 5. Compiled YangBrowser 153 prefs.js (configureNavigatorEmulation + WebGL overrides)")

    # Test 5: Live Dynamic Config Hot-Reload
    dyn_res = launcher.update_dynamic_config_live(
        "fa1002flw",
        webrtc_public_ip="198.51.100.77",
        timezone="America/Los_Angeles",
    )
    assert dyn_res["dynamicConfig"]["WebRTCAddress"] == "198.51.100.77"
    assert dyn_res["dynamicConfig"]["TimeZone"] == "America/Los_Angeles"
    print("  [PASS] 6. Live DynamicConfig Hot-Reload (`md5(id + '_webrtc')`) verified")

    # Test 6: GPU / OpenGL (--use-angle=gl) & Proxy-Linked TimeZone / Language / Geolocation Auto-Follow
    test_gl_prof = {
        "id": "fa9999gl",
        "serial_number": 99,
        "name": "OpenGL + JP Proxy Auto-Follow Test",
        "kernel_type": "taebrowser",
        "os_platform": "Windows",
        "proxy": {"type": "socks5", "host": "127.0.0.1", "port": 1080, "country": "JP", "exit_ip": "203.0.113.88"},
        "fingerprint": {
            "gpu_mode": "enabled",
            "graphics_api": "OpenGL",
            "angle_backend": "gl",
            "webgl_vendor": "Google Inc. (NVIDIA)",
            "webgl_renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 4080 OpenGL Engine, OpenGL 4.6.0 NVIDIA 551.86)",
            "webgl_version": "WebGL 2.0 (OpenGL 4.6.0 Chromium)",
            "webgl_shading_language": "WebGL GLSL ES 3.00 (OpenGL GLSL 4.60 Chromium)",
            "webgpu_mode": "webgl_based",
            "webgpu_vendor": "nvidia",
            "webgpu_architecture": "ada-lovelace",
            "proxy_country": "JP",
            "follow_proxy_timezone": True,
            "timezone": "Asia/Seoul",  # Should be overridden by JP -> Asia/Tokyo
            "follow_proxy_language": True,
            "languages": ["ko-KR", "ko"],  # Should be overridden by JP -> ja-JP, ja, en-US, en
            "follow_proxy_ui_language": True,
            "ui_language": "ko-KR",  # Should be overridden by JP -> ja-JP
            "follow_proxy_geolocation": True,
            "geolocation_enabled": True,
        },
    }
    gl_plan = launcher.build_launch_plan(test_gl_prof, write_files=False)
    assert "--use-angle=gl" in gl_plan["args"], "OpenGL profile must include --use-angle=gl"
    assert "--lang=ja-JP" in gl_plan["args"], "Proxy-linked UI language must set --lang=ja-JP for JP proxy"
    assert gl_plan["env"]["TZ"] == "Asia/Tokyo", "Proxy-linked TimeZone must set TZ=Asia/Tokyo for JP proxy"
    assert gl_plan["compiled"]["dynamicConfig"]["TimeZone"] == "Asia/Tokyo"
    assert gl_plan["compiled"]["staticConfig"]["Langs"] == "ja-JP,ja,en-US,en"
    assert gl_plan["compiled"]["resolved_locale"]["languages"] == ["ja-JP", "ja", "en-US", "en"]
    assert gl_plan["compiled"]["webglConfig"]["VERSION"] == "WebGL 2.0 (OpenGL 4.6.0 Chromium)"
    print(
        "  [PASS] 6b. GPU/OpenGL (`--use-angle=gl`, GL 4.6) & Proxy Auto-Follow "
        "(JP -> TimeZone=Asia/Tokyo, Languages=ja-JP, --lang=ja-JP) verified"
    )

    # Test 7: HTTP Server & Local API v1/v2 Compatibility + GPU Catalog & Proxy Check
    ui_dir = BASE_DIR / "ui"
    srv = create_http_server("127.0.0.1", 50399, db, launcher, ui_dir)
    srv_thread = threading.Thread(target=srv.serve_forever, daemon=True)
    srv_thread.start()

    try:
        with urllib.request.urlopen("http://127.0.0.1:50399/api/freeanti/status", timeout=5) as resp:
            status_json = json.loads(resp.read().decode("utf-8"))
            assert status_json["ok"] is True

        with urllib.request.urlopen("http://127.0.0.1:50399/api/freeanti/gpu-catalog", timeout=5) as resp:
            cat_json = json.loads(resp.read().decode("utf-8"))
            assert cat_json["ok"] is True
            assert len(cat_json["gpu_catalog"]) >= 20
            assert "KR" in cat_json["country_locales"] and "US" in cat_json["country_locales"]

        with urllib.request.urlopen("http://127.0.0.1:50399/api/v2/browser-profile/kernels", timeout=5) as resp:
            kernels_json = json.loads(resp.read().decode("utf-8"))
            assert kernels_json["code"] == 0
            k_types = {k["kernel_type"] for k in kernels_json["data"]}
            assert "TaeBrowser" in k_types and "YangBrowser" in k_types

        print("  [PASS] 7. HTTP Server + GPU Catalog + Local API v1 & v2 Compatibility verified")

        if args.launch_browsers:
            print("  [...] 8a. Testing real TaeBrowser 153 (TaeBrowser.exe) launch with --extended-parameters...")
            tb_session = launcher.start_profile("fa1001win", headless=True)
            assert tb_session["status"] == "Active" and tb_session["pid"] > 0
            print(f"  [PASS] 8a. TaeBrowser 153 launched! PID={tb_session['pid']}, DebugWS={tb_session['ws']['puppeteer']}")
            launcher.stop_profile("fa1001win")

            print("  [...] 8b. Testing real YangBrowser 153 (YangBrowser.exe) launch with --extended-parameters...")
            yb_session = launcher.start_profile("fa1002flw", headless=True)
            assert yb_session["status"] == "Active" and yb_session["pid"] > 0
            print(
                f"  [PASS] 8b. YangBrowser 153 launched! PID={yb_session['pid']}, "
                f"Marionette={yb_session['marionette_port']}, DebugWS={yb_session['ws']['puppeteer']}"
            )
            launcher.stop_profile("fa1002flw")
    finally:
        srv.shutdown()
        srv.server_close()

    print("=" * 80)
    print("  ✅ ALL FREEANTI (TAEBROWSER & YANGBROWSER) TESTS PASSED SUCCESSFULLY!")
    print("=" * 80)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="freeanti",
        description="freeanti — WebView2 Anti-Detect Browser Desktop App & Local API Server (TaeBrowser 153 & YangBrowser 153)",
    )
    parser.add_argument("--port", type=int, default=50325, help="Local HTTP server port (default: 50325)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Local HTTP server bind host")

    sub = parser.add_subparsers(dest="command")

    # gui / app (default)
    sub.add_parser("gui", help="Launch the native Microsoft Edge WebView2 Desktop Application (default)")
    sub.add_parser("app", help="Alias for gui — Launch the native WebView2 Desktop Application")

    # serve
    p_serve = sub.add_parser("serve", help="Run the freeanti Web Server & Local API Server")
    p_serve.add_argument("--no-open", action="store_true", help="Do not open browser window automatically")

    # status
    sub.add_parser("status", help="Show discovered TaeBrowser & YangBrowser kernels, extensions, and profile summary")

    # list
    p_list = sub.add_parser("list", help="List anti-detect browser profiles")
    p_list.add_argument("--kernel", choices=["taebrowser", "yangbrowser", "yangbrower"], help="Filter by kernel")
    p_list.add_argument("--search", help="Search keyword")
    p_list.add_argument("--json", action="store_true", help="Output as JSON")

    # create
    p_create = sub.add_parser("create", help="Create a new anti-detect browser profile")
    p_create.add_argument("--name", required=True, help="Profile name")
    p_create.add_argument(
        "--kernel",
        default="taebrowser",
        choices=["taebrowser", "yangbrowser", "yangbrower", "sunbrowser", "flowerbrowser"],
    )
    p_create.add_argument("--os", default="Windows", choices=["Windows", "macOS", "Linux", "Android", "iPhone"])
    p_create.add_argument("--proxy-type", default="direct", choices=["direct", "http", "https", "socks5"])
    p_create.add_argument("--proxy-host", default="")
    p_create.add_argument("--proxy-port", type=int, default=0)
    p_create.add_argument("--webrtc-ip", help="Spoofed public WebRTC ICE IP")
    p_create.add_argument("--timezone", help="Spoofed IANA timezone (e.g. Asia/Seoul, America/New_York)")
    p_create.add_argument("--notes", help="Profile notes")

    # inspect
    p_insp = sub.add_parser("inspect", help="Compile & inspect MD5 sidecars and --extended-parameters for a profile")
    p_insp.add_argument("profile_id", help="Profile ID or serial number")

    # start
    p_start = sub.add_parser("start", help="Launch TaeBrowser 153 or YangBrowser 153 for a profile")
    p_start.add_argument("profile_id", help="Profile ID or serial number")
    p_start.add_argument("--headless", action="store_true", help="Launch in headless mode")

    # stop
    p_stop = sub.add_parser("stop", help="Stop a running browser profile")
    p_stop.add_argument("profile_id", help="Profile ID or serial number")

    # dynamic-update
    p_dyn = sub.add_parser("dynamic-update", help="Hot-reload dynamicConfig (md5(id+'_webrtc')) while browser is running")
    p_dyn.add_argument("profile_id", help="Profile ID or serial number")
    p_dyn.add_argument("--ip", help="New public WebRTC IP")
    p_dyn.add_argument("--local-ip", help="New private LAN WebRTC IP")
    p_dyn.add_argument("--tz", help="New IANA TimeZone")
    p_dyn.add_argument("--lat", type=float, help="New Latitude")
    p_dyn.add_argument("--lon", type=float, help="New Longitude")

    # test
    p_test = sub.add_parser("test", help="Run automated verification suite")
    p_test.add_argument("--launch-browsers", action="store_true", help="Also test spawning actual TaeBrowser.exe & YangBrowser.exe")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    cmd = args.command or "gui"
    if cmd in ("gui", "app"):
        return cmd_gui(args)
    if cmd == "status":
        return cmd_status(args)
    if cmd == "list":
        return cmd_list(args)
    if cmd == "create":
        return cmd_create(args)
    if cmd == "inspect":
        return cmd_inspect(args)
    if cmd == "start":
        return cmd_start(args)
    if cmd == "stop":
        return cmd_stop(args)
    if cmd == "dynamic-update":
        return cmd_dynamic_update(args)
    if cmd == "test":
        return cmd_test(args)
    return cmd_serve(args)


if __name__ == "__main__":
    raise SystemExit(main())
