"""
HTTP Control Server for freeanti.
Provides:
  1. WebView2 Desktop App UI (`GET /`) & Live Fingerprint Verification Suite (`GET /verify`)
  2. Native freeanti REST API (`/api/freeanti/*`)
  3. Local API v1 & v2 Compatibility Layer (`/api/v1/*`, `/api/v2/*`)
  4. Loopback Extension Assistant Endpoints (`/api/tabAssistant/features`, `/api/getTabUrls`, `/api/getExtensionList`, `/api/log`)
"""

from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict
from urllib.parse import parse_qs, urlparse

from .database import FreeAntiDatabase
from .extension_builder import compute_chrome_validation_headers
from .fingerprint import COUNTRY_LOCALE_MAP, GPU_CATALOG, check_proxy_and_resolve_geo
from .launcher import BrowserLauncher


class FreeAntiRequestHandler(BaseHTTPRequestHandler):
    server_version = "freeanti/2.0"

    def log_message(self, format: str, *args: Any) -> None:
        # Keep console output quiet for polling requests
        pass

    @property
    def db(self) -> FreeAntiDatabase:
        return self.server.db  # type: ignore[attr-defined]

    @property
    def launcher(self) -> BrowserLauncher:
        return self.server.launcher  # type: ignore[attr-defined]

    @property
    def ui_dir(self) -> Path:
        return self.server.ui_dir  # type: ignore[attr-defined]

    def _send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, api-key, x-freeanti-client")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html_text: str, status: int = 200) -> None:
        body = html_text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, file_path: Path, content_type: str) -> None:
        if not file_path.is_file():
            self._send_json({"ok": False, "error": "Asset not found"}, 404)
            return
        body = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8", errors="ignore")
        try:
            return json.loads(raw) if raw.strip() else {}
        except Exception:
            return {}

    def _get_query_dict(self) -> Dict[str, str]:
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        return {k: v[0] for k, v in qs.items() if v}

    def do_OPTIONS(self) -> None:
        self._send_json({"ok": True})

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        q = self._get_query_dict()

        # 1. Desktop WebView2 UI & Verification Page
        if path == "/":
            index_file = self.ui_dir / "index.html"
            if index_file.is_file():
                self._send_html(index_file.read_text(encoding="utf-8"))
                return
            self._send_html("<h1>freeanti UI not found</h1>", 404)
            return

        if path == "/verify":
            verify_file = self.ui_dir / "verify.html"
            if verify_file.is_file():
                self._send_html(verify_file.read_text(encoding="utf-8"))
                return
            self._send_html("<h1>verify.html not found</h1>", 404)
            return

        if path == "/favicon.ico" or path == "/assets/icon.ico":
            assets_dir = self.ui_dir.parent / "assets"
            ico = assets_dir / "icon.ico"
            if not ico.is_file():
                ico = self.ui_dir.parent / "icon.ico"
            self._send_file(ico, "image/x-icon")
            return

        if path == "/assets/icon.png":
            self._send_file(self.ui_dir.parent / "assets" / "icon.png", "image/png")
            return

        if path == "/assets/icon.svg":
            self._send_file(self.ui_dir.parent / "assets" / "icon.svg", "image/svg+xml; charset=utf-8")
            return

        if path == "/assets/hero-banner.svg":
            self._send_file(self.ui_dir.parent / "assets" / "hero-banner.svg", "image/svg+xml; charset=utf-8")
            return

        # 2. Native Free Proxy Browser API
        if path == "/api/freeanti/status":
            self._send_json(
                {
                    "ok": True,
                    "app": "Free Proxy Browser",
                    "version": "2.1.0",
                    "kernels": self.launcher.kernels_info,
                    "active_profiles": self.launcher.list_active_profiles(),
                    "profile_count": len(self.db.list_profiles()),
                }
            )
            return

        if path == "/api/freeanti/profiles":
            profiles = self.db.list_profiles(
                group_id=q.get("group_id"),
                kernel_type=q.get("kernel_type"),
                search=q.get("search"),
            )
            self._send_json({"ok": True, "profiles": profiles})
            return

        m_prof = re.match(r"^/api/freeanti/profiles/([^/]+)$", path)
        if m_prof:
            pid = m_prof.group(1)
            prof = self.db.get_profile(pid)
            if not prof:
                self._send_json({"ok": False, "error": "Profile not found"}, 404)
                return
            self._send_json(
                {
                    "ok": True,
                    "profile": prof,
                    "active": self.launcher.get_active_status(pid),
                }
            )
            return

        m_insp = re.match(r"^/api/freeanti/profiles/([^/]+)/inspect$", path)
        if m_insp:
            pid = m_insp.group(1)
            prof = self.db.get_profile(pid)
            if not prof:
                self._send_json({"ok": False, "error": "Profile not found"}, 404)
                return
            plan = self.launcher.build_launch_plan(prof, write_files=True)
            self._send_json(
                {
                    "ok": True,
                    "profile": prof,
                    "launch_plan": {
                        "executable": plan["executable"],
                        "executable_exists": plan["executable_exists"],
                        "webdriver": plan["webdriver"],
                        "args": plan["args"],
                        "command_line": plan["command_line"],
                        "env": plan["env"],
                    },
                    "compiled": plan["compiled"],
                }
            )
            return

        if path == "/api/freeanti/groups":
            self._send_json({"ok": True, "groups": self.db.list_groups()})
            return

        if path == "/api/freeanti/proxies":
            self._send_json({"ok": True, "proxies": self.db.list_proxies()})
            return

        if path == "/api/freeanti/logs":
            self._send_json({"ok": True, "logs": self.db.list_launch_logs()})
            return

        if path == "/api/freeanti/gpu-catalog":
            self._send_json(
                {
                    "ok": True,
                    "gpu_catalog": GPU_CATALOG,
                    "country_locales": COUNTRY_LOCALE_MAP,
                }
            )
            return

        # 3. Loopback Extension Assistant Endpoints (`127.0.0.1:20725` compatible)
        if path == "/api/tabAssistant/features":
            self._send_json(
                {
                    "code": 0,
                    "msg": "success",
                    "data": ["chromeValidationHeaders", "tabAssistant"],
                }
            )
            return

        if path == "/api/getTabUrls":
            bid = q.get("id", "")
            prof = self.db.get_profile(bid) if bid else None
            urls = (prof.get("startup_urls") if prof else None) or []
            self._send_json({"code": 0, "msg": "success", "data": urls})
            return

        if path == "/api/getExtensionList":
            self._send_json({"code": 0, "msg": "success", "data": []})
            return

        # 4. Local API v1 & v2 Compatibility Routes (GET)
        if path in ("/api/v1/browser/start", "/api/v2/browser-profile/start"):
            uid = q.get("user_id") or q.get("profile_id") or q.get("serial_number") or ""
            headless = q.get("headless") in ("1", "true")
            try:
                info = self.launcher.start_profile(uid, headless=headless)
                self._send_json({"code": 0, "msg": "success", "data": info})
            except Exception as e:
                self._send_json({"code": -1, "msg": str(e), "data": None})
            return

        if path in ("/api/v1/browser/stop", "/api/v2/browser-profile/stop"):
            uid = q.get("user_id") or q.get("profile_id") or q.get("serial_number") or ""
            res = self.launcher.stop_profile(uid)
            self._send_json({"code": 0, "msg": "success", "data": res})
            return

        if path in ("/api/v1/browser/active", "/api/v2/browser-profile/active"):
            uid = q.get("user_id") or q.get("profile_id") or q.get("serial_number") or ""
            res = self.launcher.get_active_status(uid)
            self._send_json({"code": 0, "msg": "success", "data": res})
            return

        if path in ("/api/v1/browser/local-active", "/api/v1/browser/cloud-active"):
            self._send_json(
                {"code": 0, "msg": "success", "data": {"list": self.launcher.list_active_profiles()}}
            )
            return

        if path in ("/api/v1/user/list", "/api/v2/browser-profile/list"):
            profiles = self.db.list_profiles()
            self._send_json(
                {
                    "code": 0,
                    "msg": "success",
                    "data": {"list": profiles, "page": 1, "page_size": len(profiles)},
                }
            )
            return

        if path == "/api/v2/browser-profile/kernels":
            k_info = self.launcher.kernels_info
            kernels_out = []
            for tb in k_info.get("taebrowser", []):
                kernels_out.append(
                    {
                        "kernel_type": "TaeBrowser",
                        "kernel": tb["kernel_version"],
                        "version": tb["chromium_version"],
                        "executable": tb["executable"],
                        "is_downloaded": True,
                    }
                )
            for yb in k_info.get("yangbrowser", []):
                kernels_out.append(
                    {
                        "kernel_type": "YangBrowser",
                        "kernel": yb["kernel_version"],
                        "version": yb["gecko_version"],
                        "executable": yb["executable"],
                        "is_downloaded": True,
                    }
                )
            self._send_json({"code": 0, "msg": "success", "data": kernels_out})
            return

        self._send_json({"ok": False, "error": f"Unknown endpoint: {path}"}, 404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        body = self._read_json_body()
        q = self._get_query_dict()

        if path == "/api/freeanti/profiles":
            prof = self.db.create_profile(body)
            self._send_json({"ok": True, "profile": prof}, 201)
            return

        if path == "/api/freeanti/profiles/stop-all":
            res = self.launcher.stop_all_profiles()
            self._send_json({"ok": True, "stopped": res})
            return

        m_start = re.match(r"^/api/freeanti/profiles/([^/]+)/start$", path)
        if m_start:
            pid = m_start.group(1)
            headless = bool(body.get("headless", False))
            try:
                session = self.launcher.start_profile(pid, headless=headless)
                self._send_json({"ok": True, "session": session})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 500)
            return

        m_stop = re.match(r"^/api/freeanti/profiles/([^/]+)/stop$", path)
        if m_stop:
            pid = m_stop.group(1)
            res = self.launcher.stop_profile(pid)
            self._send_json({"ok": True, "result": res})
            return

        m_rand = re.match(r"^/api/freeanti/profiles/([^/]+)/randomize$", path)
        if m_rand:
            pid = m_rand.group(1)
            prof = self.db.randomize_fingerprint(pid)
            self._send_json({"ok": True, "profile": prof})
            return

        m_dyn = re.match(r"^/api/freeanti/profiles/([^/]+)/dynamic-update$", path)
        if m_dyn:
            pid = m_dyn.group(1)
            try:
                updated = self.launcher.update_dynamic_config_live(
                    profile_id=pid,
                    webrtc_public_ip=body.get("webrtc_public_ip"),
                    webrtc_local_ip=body.get("webrtc_local_ip"),
                    timezone=body.get("timezone"),
                    latitude=body.get("latitude"),
                    longitude=body.get("longitude"),
                    accuracy=body.get("accuracy"),
                    disable_webrtc=body.get("disable_webrtc"),
                )
                self._send_json({"ok": True, "updated": updated})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 400)
            return

        if path == "/api/freeanti/chrome-validation":
            ua = body.get("user_agent") or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
            headers_info = compute_chrome_validation_headers(ua)
            self._send_json({"ok": True, "user_agent": ua, "headers": headers_info})
            return

        if path == "/api/freeanti/proxy-check":
            res = check_proxy_and_resolve_geo(
                proxy=body.get("proxy"),
                target_ip=body.get("exit_ip"),
                country_hint=body.get("country") or "US",
            )
            self._send_json({"ok": True, "resolved": res})
            return

        if path == "/api/freeanti/groups":
            grp = self.db.create_group(body.get("name", "New Group"), body.get("remark", ""))
            self._send_json({"ok": True, "group": grp}, 201)
            return

        if path == "/api/freeanti/proxies":
            prx = self.db.create_proxy(body)
            self._send_json({"ok": True, "proxy": prx}, 201)
            return

        if path == "/api/log":
            self._send_json({"code": 0, "msg": "success"})
            return

        # Local API v1 & v2 Compatibility Routes (POST)
        if path in ("/api/v1/browser/start", "/api/v2/browser-profile/start"):
            uid = (
                body.get("profile_id")
                or body.get("user_id")
                or body.get("serial_number")
                or q.get("user_id")
                or q.get("profile_id")
                or ""
            )
            headless = str(body.get("headless", "0")) in ("1", "true", "True")
            try:
                info = self.launcher.start_profile(str(uid), headless=headless)
                self._send_json({"code": 0, "msg": "success", "data": info})
            except Exception as e:
                self._send_json({"code": -1, "msg": str(e), "data": None})
            return

        if path in ("/api/v1/browser/stop", "/api/v2/browser-profile/stop"):
            uid = (
                body.get("profile_id")
                or body.get("user_id")
                or body.get("serial_number")
                or q.get("user_id")
                or q.get("profile_id")
                or ""
            )
            res = self.launcher.stop_profile(str(uid))
            self._send_json({"code": 0, "msg": "success", "data": res})
            return

        if path == "/api/v2/browser-profile/stop-all":
            res = self.launcher.stop_all_profiles()
            self._send_json({"code": 0, "msg": "success", "data": res})
            return

        if path in ("/api/v1/user/create", "/api/v2/browser-profile/create"):
            prof = self.db.create_profile(body)
            self._send_json(
                {
                    "code": 0,
                    "msg": "success",
                    "data": {
                        "id": prof["id"],
                        "profile_id": prof["id"],
                        "serial_number": prof["serial_number"],
                    },
                }
            )
            return

        if path == "/api/v2/browser-profile/new-fingerprint":
            pids = body.get("profile_id") or []
            if isinstance(pids, str):
                pids = [pids]
            updated = [self.db.randomize_fingerprint(p) for p in pids]
            self._send_json({"code": 0, "msg": "success", "data": updated})
            return

        self._send_json({"ok": False, "error": f"Unknown POST endpoint: {path}"}, 404)

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        body = self._read_json_body()

        m_prof = re.match(r"^/api/freeanti/profiles/([^/]+)$", path)
        if m_prof:
            pid = m_prof.group(1)
            prof = self.db.update_profile(pid, body)
            if not prof:
                self._send_json({"ok": False, "error": "Profile not found"}, 404)
                return
            self._send_json({"ok": True, "profile": prof})
            return

        self._send_json({"ok": False, "error": f"Unknown PUT endpoint: {path}"}, 404)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        m_prof = re.match(r"^/api/freeanti/profiles/([^/]+)$", path)
        if m_prof:
            pid = m_prof.group(1)
            self.launcher.clear_profile_cache(pid)
            deleted = self.db.delete_profile(pid)
            self._send_json({"ok": deleted})
            return

        m_grp = re.match(r"^/api/freeanti/groups/([^/]+)$", path)
        if m_grp:
            gid = m_grp.group(1)
            deleted = self.db.delete_group(gid)
            self._send_json({"ok": deleted})
            return

        m_prx = re.match(r"^/api/freeanti/proxies/([^/]+)$", path)
        if m_prx:
            prx_id = m_prx.group(1)
            deleted = self.db.delete_proxy(prx_id)
            self._send_json({"ok": deleted})
            return

        self._send_json({"ok": False, "error": f"Unknown DELETE endpoint: {path}"}, 404)


class QuietThreadingHTTPServer(ThreadingHTTPServer):
    def handle_error(self, request: Any, client_address: Any) -> None:
        import sys
        _, exc, _ = sys.exc_info()
        if isinstance(exc, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)


def create_http_server(
    host: str,
    port: int,
    db: FreeAntiDatabase,
    launcher: BrowserLauncher,
    ui_dir: Path,
) -> ThreadingHTTPServer:
    srv = QuietThreadingHTTPServer((host, port), FreeAntiRequestHandler)
    srv.db = db  # type: ignore[attr-defined]
    srv.launcher = launcher  # type: ignore[attr-defined]
    srv.ui_dir = ui_dir  # type: ignore[attr-defined]
    return srv
