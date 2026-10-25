"""
SQLite Database Engine for freeanti (`freeanti/data/freeanti.db`).
Stores profiles, groups, proxies, settings, and launch history.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .fingerprint import generate_fingerprint_profile, normalize_kernel_name, parse_proxy_string


class FreeAntiDatabase:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        self._migrate_legacy_branding()
        self._seed_defaults_if_empty()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS groups (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    remark TEXT DEFAULT '',
                    created_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS proxies (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL DEFAULT 'direct',
                    host TEXT DEFAULT '',
                    port INTEGER DEFAULT 0,
                    username TEXT DEFAULT '',
                    password TEXT DEFAULT '',
                    exit_ip TEXT DEFAULT '',
                    country TEXT DEFAULT 'US',
                    timezone TEXT DEFAULT 'America/New_York',
                    created_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS profiles (
                    id TEXT PRIMARY KEY,
                    serial_number INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    group_id TEXT DEFAULT 'default',
                    kernel_type TEXT NOT NULL DEFAULT 'taebrowser',
                    os_platform TEXT NOT NULL DEFAULT 'Windows',
                    fingerprint_json TEXT NOT NULL,
                    proxy_json TEXT NOT NULL,
                    cookies_json TEXT NOT NULL DEFAULT '[]',
                    startup_urls_json TEXT NOT NULL DEFAULT '[]',
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    notes TEXT DEFAULT '',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    last_launched_at INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS launch_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id TEXT NOT NULL,
                    kernel_type TEXT NOT NULL,
                    pid INTEGER DEFAULT 0,
                    debug_link TEXT DEFAULT '',
                    marionette_port INTEGER DEFAULT 0,
                    window_handle TEXT DEFAULT '',
                    status TEXT NOT NULL,
                    launched_at INTEGER NOT NULL
                );
                """
            )

    def _migrate_legacy_branding(self) -> None:
        """
        Automatically migrates any existing 'sunbrowser' / 'flowerbrowser' profiles
        to 'taebrowser' (TaeBrowser) and 'yangbrowser' (YangBrowser).
        """
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM profiles").fetchall()
            for r in rows:
                old_k = r["kernel_type"]
                new_k = normalize_kernel_name(old_k)
                name = (
                    (r["name"] or "")
                    .replace("SunBrowser", "TaeBrowser")
                    .replace("sunbrowser", "taebrowser")
                    .replace("FlowerBrowser", "YangBrowser")
                    .replace("flowerbrowser", "yangbrowser")
                )
                notes = (
                    (r["notes"] or "")
                    .replace("SunBrowser", "TaeBrowser")
                    .replace("sunbrowser", "taebrowser")
                    .replace("FlowerBrowser", "YangBrowser")
                    .replace("flowerbrowser", "yangbrowser")
                )
                tags_str = (
                    (r["tags_json"] or "[]")
                    .replace("SunBrowser", "TaeBrowser")
                    .replace("FlowerBrowser", "YangBrowser")
                )
                fp_str = (
                    (r["fingerprint_json"] or "{}")
                    .replace('"sunbrowser"', '"taebrowser"')
                    .replace('"flowerbrowser"', '"yangbrowser"')
                )
                if (
                    old_k != new_k
                    or name != r["name"]
                    or notes != r["notes"]
                    or tags_str != r["tags_json"]
                    or fp_str != r["fingerprint_json"]
                ):
                    conn.execute(
                        """
                        UPDATE profiles
                        SET kernel_type = ?, name = ?, notes = ?, tags_json = ?, fingerprint_json = ?
                        WHERE id = ?
                        """,
                        (new_k, name, notes, tags_str, fp_str, r["id"]),
                    )
            conn.execute(
                "UPDATE launch_logs SET kernel_type = 'taebrowser' WHERE kernel_type = 'sunbrowser'"
            )
            conn.execute(
                "UPDATE launch_logs SET kernel_type = 'yangbrowser' WHERE kernel_type = 'flowerbrowser'"
            )
            # Backfill GPU/OpenGL & Proxy-linked TimeZone/Language/Geolocation fields on existing profiles
            rows2 = conn.execute("SELECT id, kernel_type, os_platform, fingerprint_json, proxy_json FROM profiles").fetchall()
            for r in rows2:
                fp = json.loads(r["fingerprint_json"] or "{}")
                prx = json.loads(r["proxy_json"] or "{}")
                if "graphics_api" not in fp or "follow_proxy_timezone" not in fp:
                    defaults = generate_fingerprint_profile(
                        profile_id=r["id"],
                        kernel_type=r["kernel_type"],
                        os_platform=r["os_platform"],
                    )
                    for k, v in defaults.items():
                        if k not in fp:
                            fp[k] = v
                    if "country" not in prx:
                        prx["country"] = fp.get("proxy_country", "US")
                    conn.execute(
                        "UPDATE profiles SET fingerprint_json = ?, proxy_json = ? WHERE id = ?",
                        (json.dumps(fp, ensure_ascii=False), json.dumps(prx, ensure_ascii=False), r["id"]),
                    )

    def _seed_defaults_if_empty(self) -> None:
        with self._connect() as conn:
            cnt = conn.execute("SELECT COUNT(*) FROM groups").fetchone()[0]
            now = int(time.time())
            if cnt == 0:
                conn.executemany(
                    "INSERT INTO groups (id, name, remark, created_at) VALUES (?, ?, ?, ?)",
                    [
                        ("default", "Default Group", "Default browser profile group", now),
                        ("ecommerce", "E-Commerce & Ads", "Global store, seller, and ad accounts", now),
                        ("web3", "Multi-Account & Automation", "Social media, Web3, and RPA automation profiles", now),
                    ],
                )

            pcnt = conn.execute("SELECT COUNT(*) FROM profiles").fetchone()[0]
            if pcnt == 0:
                seed_specs = [
                    {
                        "id": "fa1001win",
                        "serial_number": 1,
                        "name": "TaeBrowser 153 — Windows 11 (RTX 4070)",
                        "group_id": "default",
                        "kernel_type": "taebrowser",
                        "os_platform": "Windows",
                        "notes": "TaeBrowser 153 (Chromium 153.0.8010.27) + x-browser-validation header forgery + Canvas/WebGL/Audio/ClientRects noise",
                        "tags": ["TaeBrowser 153", "Windows", "Stealth"],
                    },
                    {
                        "id": "fa1002flw",
                        "serial_number": 2,
                        "name": "YangBrowser 153 — macOS M3 (Gecko 153)",
                        "group_id": "ecommerce",
                        "kernel_type": "yangbrowser",
                        "os_platform": "macOS",
                        "notes": "YangBrowser 153 (Firefox/Gecko 153.0.4) + 37 xul.dll custom.* hooks + macOS Fakefonts/Navigator emulation",
                        "tags": ["YangBrowser 153", "macOS", "Gecko"],
                    },
                    {
                        "id": "fa1003ios",
                        "serial_number": 3,
                        "name": "TaeBrowser 153 — iPhone 15 Pro (NewMobileMode)",
                        "group_id": "web3",
                        "kernel_type": "taebrowser",
                        "os_platform": "iPhone",
                        "notes": "Mobile viewport & touch (MaxTouchPoints=5) + Apple GPU MAX_VIEWPORT_DIMS [16384,16384] emulation",
                        "tags": ["Mobile", "iPhone", "TaeBrowser 153"],
                    },
                ]
                for spec in seed_specs:
                    fp = generate_fingerprint_profile(
                        profile_id=spec["id"],
                        kernel_type=spec["kernel_type"],
                        os_platform=spec["os_platform"],
                    )
                    proxy = {
                        "type": "direct",
                        "host": "",
                        "port": 0,
                        "username": "",
                        "password": "",
                        "exit_ip": fp["webrtc_public_ip"],
                    }
                    conn.execute(
                        """
                        INSERT INTO profiles (
                            id, serial_number, name, group_id, kernel_type, os_platform,
                            fingerprint_json, proxy_json, cookies_json, startup_urls_json,
                            tags_json, notes, created_at, updated_at, last_launched_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                        """,
                        (
                            spec["id"],
                            spec["serial_number"],
                            spec["name"],
                            spec["group_id"],
                            spec["kernel_type"],
                            spec["os_platform"],
                            json.dumps(fp, ensure_ascii=False),
                            json.dumps(proxy, ensure_ascii=False),
                            "[]",
                            "[]",
                            json.dumps(spec["tags"], ensure_ascii=False),
                            spec["notes"],
                            now,
                            now,
                        ),
                    )

    def _row_to_profile(self, row: sqlite3.Row) -> Dict[str, Any]:
        ktype = normalize_kernel_name(row["kernel_type"])
        return {
            "id": row["id"],
            "user_id": row["id"],  # Local API alias
            "serial_number": row["serial_number"],
            "name": row["name"],
            "group_id": row["group_id"],
            "kernel_type": ktype,
            "os_platform": row["os_platform"],
            "fingerprint": json.loads(row["fingerprint_json"] or "{}"),
            "proxy": json.loads(row["proxy_json"] or '{"type":"direct"}'),
            "cookies": json.loads(row["cookies_json"] or "[]"),
            "startup_urls": json.loads(row["startup_urls_json"] or "[]"),
            "tags": json.loads(row["tags_json"] or "[]"),
            "notes": row["notes"] or "",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "last_launched_at": row["last_launched_at"],
        }

    def list_profiles(
        self,
        group_id: Optional[str] = None,
        kernel_type: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM profiles WHERE 1=1"
        params: List[Any] = []
        if group_id:
            query += " AND group_id = ?"
            params.append(group_id)
        if kernel_type:
            query += " AND kernel_type = ?"
            params.append(normalize_kernel_name(kernel_type))
        if search:
            query += " AND (name LIKE ? OR id LIKE ? OR notes LIKE ?)"
            q = f"%{search}%"
            params.extend([q, q, q])
        query += " ORDER BY serial_number ASC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_profile(r) for r in rows]

    def get_profile(self, profile_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM profiles WHERE id = ? OR CAST(serial_number AS TEXT) = ?",
                (str(profile_id), str(profile_id)),
            ).fetchone()
            return self._row_to_profile(row) if row else None

    def create_profile(self, data: Dict[str, Any]) -> Dict[str, Any]:
        with self._connect() as conn:
            max_sn = conn.execute("SELECT COALESCE(MAX(serial_number), 0) FROM profiles").fetchone()[0]
            sn = int(data.get("serial_number") or (max_sn + 1))
            pid = str(data.get("id") or f"fa{1000 + sn}{uuid.uuid4().hex[:3]}")
            kernel_type = normalize_kernel_name(str(data.get("kernel_type") or "taebrowser"))

            os_platform = str(data.get("os_platform") or "Windows")
            fp_overrides = dict(data.get("fingerprint") or {})
            proxy_in = dict(data.get("proxy") or {})
            raw_phost = str(proxy_in.get("raw") or proxy_in.get("host") or "").strip()
            if raw_phost and ("://" in raw_phost or "@" in raw_phost or raw_phost.count(":") >= 1):
                parsed_prx = parse_proxy_string(raw_phost, str(proxy_in.get("type") or "socks5"))
                if parsed_prx["host"]:
                    if proxy_in.get("type") in (None, "", "direct"):
                        proxy_in["type"] = parsed_prx["type"]
                    proxy_in["host"] = parsed_prx["host"]
                    if parsed_prx["port"]:
                        proxy_in["port"] = parsed_prx["port"]
                    if parsed_prx["username"] and not proxy_in.get("username"):
                        proxy_in["username"] = parsed_prx["username"]
                    if parsed_prx["password"] and not proxy_in.get("password"):
                        proxy_in["password"] = parsed_prx["password"]
            if proxy_in.get("country") and "proxy_country" not in fp_overrides:
                fp_overrides["proxy_country"] = proxy_in["country"]
            fp = generate_fingerprint_profile(
                profile_id=pid,
                kernel_type=kernel_type,
                os_platform=os_platform,
                overrides=fp_overrides,
            )
            proxy: Dict[str, Any] = {
                "type": proxy_in.get("type") or "direct",
                "host": proxy_in.get("host") or "",
                "port": int(proxy_in.get("port") or 0),
                "username": proxy_in.get("username") or "",
                "password": proxy_in.get("password") or "",
                "exit_ip": proxy_in.get("exit_ip") or fp.get("webrtc_public_ip", "198.51.100.77"),
                "country": proxy_in.get("country") or fp.get("proxy_country", "US"),
                "timezone": proxy_in.get("timezone") or fp.get("timezone", "America/New_York"),
            }
            if proxy_in.get("latitude") is not None:
                proxy["latitude"] = float(proxy_in["latitude"])
            if proxy_in.get("longitude") is not None:
                proxy["longitude"] = float(proxy_in["longitude"])
            if proxy.get("exit_ip"):
                fp["webrtc_public_ip"] = proxy["exit_ip"]
            if proxy.get("country"):
                fp["proxy_country"] = proxy["country"]

            name = data.get("name") or f"{'YangBrowser' if kernel_type == 'yangbrowser' else 'TaeBrowser'} #{sn} ({os_platform})"
            group_id = data.get("group_id") or "default"
            cookies = data.get("cookies") or []
            startup_urls = data.get("startup_urls") or []
            tags = data.get("tags") or [
                "YangBrowser 153" if kernel_type == "yangbrowser" else "TaeBrowser 153",
                os_platform,
            ]
            notes = data.get("notes") or ""
            now = int(time.time())

            conn.execute(
                """
                INSERT INTO profiles (
                    id, serial_number, name, group_id, kernel_type, os_platform,
                    fingerprint_json, proxy_json, cookies_json, startup_urls_json,
                    tags_json, notes, created_at, updated_at, last_launched_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    pid,
                    sn,
                    name,
                    group_id,
                    kernel_type,
                    os_platform,
                    json.dumps(fp, ensure_ascii=False),
                    json.dumps(proxy, ensure_ascii=False),
                    json.dumps(cookies, ensure_ascii=False),
                    json.dumps(startup_urls, ensure_ascii=False),
                    json.dumps(tags, ensure_ascii=False),
                    notes,
                    now,
                    now,
                ),
            )
        return self.get_profile(pid)  # type: ignore[return-value]

    def update_profile(self, profile_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        existing = self.get_profile(profile_id)
        if not existing:
            return None
        pid = existing["id"]
        name = data.get("name", existing["name"])
        group_id = data.get("group_id", existing["group_id"])
        kernel_type = normalize_kernel_name(data.get("kernel_type", existing["kernel_type"]))
        os_platform = data.get("os_platform", existing["os_platform"])

        fp = dict(existing["fingerprint"])
        if "fingerprint" in data and isinstance(data["fingerprint"], dict):
            fp.update(data["fingerprint"])
        fp["kernel_type"] = kernel_type
        fp["os_platform"] = os_platform

        proxy = dict(existing["proxy"])
        if "proxy" in data and isinstance(data["proxy"], dict):
            proxy_in = dict(data["proxy"])
            raw_phost = str(proxy_in.get("raw") or proxy_in.get("host") or "").strip()
            if raw_phost and ("://" in raw_phost or "@" in raw_phost or raw_phost.count(":") >= 1):
                parsed_prx = parse_proxy_string(raw_phost, str(proxy_in.get("type") or "socks5"))
                if parsed_prx["host"]:
                    if proxy_in.get("type") in (None, "", "direct"):
                        proxy_in["type"] = parsed_prx["type"]
                    proxy_in["host"] = parsed_prx["host"]
                    if parsed_prx["port"]:
                        proxy_in["port"] = parsed_prx["port"]
                    if parsed_prx["username"] and not proxy_in.get("username"):
                        proxy_in["username"] = parsed_prx["username"]
                    if parsed_prx["password"] and not proxy_in.get("password"):
                        proxy_in["password"] = parsed_prx["password"]
            proxy.update(proxy_in)
            if proxy.get("exit_ip"):
                fp["webrtc_public_ip"] = proxy["exit_ip"]
            if proxy.get("country"):
                fp["proxy_country"] = proxy["country"]

        cookies = data.get("cookies", existing["cookies"])
        startup_urls = data.get("startup_urls", existing["startup_urls"])
        tags = data.get("tags", existing["tags"])
        notes = data.get("notes", existing["notes"])
        now = int(time.time())

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE profiles SET
                    name = ?, group_id = ?, kernel_type = ?, os_platform = ?,
                    fingerprint_json = ?, proxy_json = ?, cookies_json = ?,
                    startup_urls_json = ?, tags_json = ?, notes = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    name,
                    group_id,
                    kernel_type,
                    os_platform,
                    json.dumps(fp, ensure_ascii=False),
                    json.dumps(proxy, ensure_ascii=False),
                    json.dumps(cookies, ensure_ascii=False),
                    json.dumps(startup_urls, ensure_ascii=False),
                    json.dumps(tags, ensure_ascii=False),
                    notes,
                    now,
                    pid,
                ),
            )
        return self.get_profile(pid)

    def randomize_fingerprint(self, profile_id: str) -> Optional[Dict[str, Any]]:
        existing = self.get_profile(profile_id)
        if not existing:
            return None
        new_fp = generate_fingerprint_profile(
            profile_id=existing["id"],
            kernel_type=existing["kernel_type"],
            os_platform=existing["os_platform"],
        )
        return self.update_profile(existing["id"], {"fingerprint": new_fp})

    def delete_profile(self, profile_id: str) -> bool:
        existing = self.get_profile(profile_id)
        if not existing:
            return False
        with self._connect() as conn:
            conn.execute("DELETE FROM profiles WHERE id = ?", (existing["id"],))
        return True

    def mark_launched(
        self,
        profile_id: str,
        kernel_type: str,
        pid: int,
        debug_link: str = "",
        marionette_port: int = 0,
        window_handle: str = "",
        status: str = "Active",
    ) -> None:
        now = int(time.time())
        ktype = normalize_kernel_name(kernel_type)
        with self._connect() as conn:
            conn.execute("UPDATE profiles SET last_launched_at = ? WHERE id = ?", (now, profile_id))
            conn.execute(
                """
                INSERT INTO launch_logs (
                    profile_id, kernel_type, pid, debug_link, marionette_port, window_handle, status, launched_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (profile_id, ktype, pid, debug_link, marionette_port, window_handle, status, now),
            )

    def list_groups(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM groups ORDER BY created_at ASC").fetchall()
            return [dict(r) for r in rows]

    def create_group(self, name: str, remark: str = "") -> Dict[str, Any]:
        gid = f"grp_{uuid.uuid4().hex[:6]}"
        now = int(time.time())
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO groups (id, name, remark, created_at) VALUES (?, ?, ?, ?)",
                (gid, name, remark, now),
            )
        return {"id": gid, "name": name, "remark": remark, "created_at": now}

    def delete_group(self, group_id: str) -> bool:
        if group_id == "default":
            return False
        with self._connect() as conn:
            conn.execute("UPDATE profiles SET group_id = 'default' WHERE group_id = ?", (group_id,))
            conn.execute("DELETE FROM groups WHERE id = ?", (group_id,))
        return True

    def list_proxies(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM proxies ORDER BY created_at DESC").fetchall()
            return [dict(r) for r in rows]

    def create_proxy(self, data: Dict[str, Any]) -> Dict[str, Any]:
        pid = str(data.get("id") or f"prx_{uuid.uuid4().hex[:6]}")
        ptype = str(data.get("type") or "socks5").lower()
        host = str(data.get("host") or "").strip()
        port = int(data.get("port") or 0)
        username = str(data.get("username") or "").strip()
        password = str(data.get("password") or "").strip()
        raw_str = str(data.get("raw") or host).strip()
        if raw_str and ("://" in raw_str or "@" in raw_str or raw_str.count(":") >= 1):
            parsed_prx = parse_proxy_string(raw_str, ptype)
            if parsed_prx["host"]:
                ptype = parsed_prx["type"] or ptype
                host = parsed_prx["host"]
                if parsed_prx["port"]:
                    port = parsed_prx["port"]
                if parsed_prx["username"] and not username:
                    username = parsed_prx["username"]
                if parsed_prx["password"] and not password:
                    password = parsed_prx["password"]
        name = str(data.get("name") or f"{ptype.upper()} {host}:{port}" if host else f"Proxy {pid[-4:]}")
        exit_ip = str(data.get("exit_ip") or "")
        country = str(data.get("country") or "US")
        timezone = str(data.get("timezone") or "America/New_York")
        now = int(time.time())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO proxies (
                    id, name, type, host, port, username, password, exit_ip, country, timezone, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (pid, name, ptype, host, port, username, password, exit_ip, country, timezone, now),
            )
        return {
            "id": pid,
            "name": name,
            "type": ptype,
            "host": host,
            "port": port,
            "username": username,
            "password": password,
            "exit_ip": exit_ip,
            "country": country,
            "timezone": timezone,
            "created_at": now,
        }

    def delete_proxy(self, proxy_id: str) -> bool:
        with self._connect() as conn:
            conn.execute("DELETE FROM proxies WHERE id = ?", (proxy_id,))
        return True

    def list_launch_logs(self, limit: int = 30) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM launch_logs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]
