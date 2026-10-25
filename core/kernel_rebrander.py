"""
Kernel Rebranding Builder for freeanti.
Transforms the locally installed SunBrowser 153 (`chrome_153`) and FlowerBrowser 153 (`flower_153`)
kernels into standalone, rebranded `TaeBrowser` (`taebrowser_153/TaeBrowser.exe`) and
`YangBrowser` (`yangbrowser_153/YangBrowser.exe`) distributions inside `freeanti/kernels/`.

Uses NTFS hardlinks for large untouched binaries (0 extra disk usage, sub-second build)
and applies binary-safe in-place patches to:
  - Executables (`TaeBrowser.exe`, `YangBrowser.exe` PE VersionInfo & window class strings)
  - Chromium Locale `.pak` files (`ko.pak`, `en-US.pak` `SunBrowser` -> `TaeBrowser`, exact 10-byte match)
  - Gecko `omni.ja` & `browser/omni.ja` (`AppConstants.sys.mjs`, `brand.ftl`, `brand.dtd`, `brand.properties`
    with exact byte-length preservation + ZIP Local/Central Directory CRC-32 recalculation)
  - Gecko `application.ini` and `langpack-ko@firefox.mozilla.org.xpi` (`YangBrowser`)
"""

from __future__ import annotations

import os
import shutil
import struct
import zlib
import zipfile
from pathlib import Path
from typing import Dict, Tuple


def _link_or_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return
    try:
        os.link(str(src), str(dst))
    except Exception:
        shutil.copy2(str(src), str(dst))


def _mirror_tree_hardlinked(src_root: Path, dst_root: Path, skip_rel_paths: set[str]) -> None:
    for item in src_root.rglob("*"):
        rel = item.relative_to(src_root)
        rel_posix = rel.as_posix()
        if any(rel_posix == s or rel_posix.startswith(s + "/") for s in skip_rel_paths):
            continue
        target = dst_root / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif item.is_file():
            _link_or_copy(item, target)


def _patch_zip_stored_entries_inplace(zip_path: Path, replacements: Dict[str, bytes]) -> None:
    """
    Patches uncompressed (`STORED`, compress_type == 0) entries inside a ZIP / `omni.ja`
    archive in-place without shifting any offsets, and updates the 4-byte CRC-32 in both
    the Local File Header (`PK\\x03\\x04` + 14) and Central Directory Header (`PK\\x01\\x02` + 16).
    """
    raw = bytearray(zip_path.read_bytes())

    # Locate End of Central Directory (EOCD) `PK\x05\x06`
    eocd_pos = raw.rfind(b"PK\x05\x06")
    if eocd_pos < 0:
        raise ValueError(f"Invalid ZIP/omni.ja archive: {zip_path}")

    cd_size = struct.unpack_from("<I", raw, eocd_pos + 12)[0]
    cd_offset = struct.unpack_from("<I", raw, eocd_pos + 16)[0]

    pos = cd_offset
    end_cd = cd_offset + cd_size
    while pos < end_cd:
        if raw[pos : pos + 4] != b"PK\x01\x02":
            break
        comp_method = struct.unpack_from("<H", raw, pos + 10)[0]
        comp_size = struct.unpack_from("<I", raw, pos + 20)[0]
        uncomp_size = struct.unpack_from("<I", raw, pos + 24)[0]
        fname_len = struct.unpack_from("<H", raw, pos + 28)[0]
        extra_len = struct.unpack_from("<H", raw, pos + 30)[0]
        comment_len = struct.unpack_from("<H", raw, pos + 32)[0]
        local_hdr_offset = struct.unpack_from("<I", raw, pos + 42)[0]

        fname = bytes(raw[pos + 46 : pos + 46 + fname_len]).decode("utf-8", errors="ignore")
        if fname in replacements and comp_method == 0:
            new_content = replacements[fname]
            if len(new_content) != uncomp_size:
                raise ValueError(
                    f"Length mismatch for {fname}: expected {uncomp_size}, got {len(new_content)}"
                )
            new_crc = zlib.crc32(new_content) & 0xFFFFFFFF
            # Update Central Directory CRC-32
            struct.pack_into("<I", raw, pos + 16, new_crc)

            # Locate Local File Header `PK\x03\x04`
            if raw[local_hdr_offset : local_hdr_offset + 4] == b"PK\x03\x04":
                lf_fname_len = struct.unpack_from("<H", raw, local_hdr_offset + 26)[0]
                lf_extra_len = struct.unpack_from("<H", raw, local_hdr_offset + 28)[0]
                data_start = local_hdr_offset + 30 + lf_fname_len + lf_extra_len
                # Update Local File Header CRC-32
                struct.pack_into("<I", raw, local_hdr_offset + 14, new_crc)
                # Write new content bytes in-place
                raw[data_start : data_start + uncomp_size] = new_content

        pos += 46 + fname_len + extra_len + comment_len

    zip_path.write_bytes(bytes(raw))


def build_taebrowser_kernel(src_chrome_dir: Path, dst_tae_dir: Path) -> Dict[str, str]:
    """
    Builds `taebrowser_153` (`TaeBrowser.exe`) from `chrome_153` (`SunBrowser.exe`).
    Since `SunBrowser` (10 chars) and `TaeBrowser` (10 chars) have the exact same byte length,
    binary patching preserves all PE and Chromium `.pak` offsets 100%.
    """
    dst_tae_dir.mkdir(parents=True, exist_ok=True)
    marker = dst_tae_dir / ".freeanti_taebrowser_v1"

    exe_dst = dst_tae_dir / "TaeBrowser.exe"
    if not marker.is_file() or not exe_dst.is_file():
        skip = {
            "SunBrowser.exe",
            "153.0.8010.27/Locales/ko.pak",
            "153.0.8010.27/Locales/en-US.pak",
        }
        _mirror_tree_hardlinked(src_chrome_dir, dst_tae_dir, skip)

        # 1. Patch SunBrowser.exe -> TaeBrowser.exe (and keep SunBrowser.exe hardlink for internal child spawns if needed)
        src_exe = src_chrome_dir / "SunBrowser.exe"
        exe_bytes = src_exe.read_bytes()
        # Replace UTF-16LE VersionInfo strings ("SunBrowser" -> "TaeBrowser")
        exe_bytes = exe_bytes.replace("SunBrowser".encode("utf-16le"), "TaeBrowser".encode("utf-16le"))
        exe_bytes = exe_bytes.replace(b"SunBrowser.exe", b"TaeBrowser.exe")
        exe_dst.write_bytes(exe_bytes)

        # Also copy to SunBrowser.exe inside dst_tae_dir in case chrome.dll references SunBrowser.exe
        sun_alias = dst_tae_dir / "SunBrowser.exe"
        if not sun_alias.exists():
            shutil.copy2(str(exe_dst), str(sun_alias))

        # 2. Patch Locales/*.pak (`ko.pak`, `en-US.pak`) replacing `SunBrowser` -> `TaeBrowser` (10 bytes -> 10 bytes)
        for loc_name in ("ko.pak", "en-US.pak"):
            src_pak = src_chrome_dir / "153.0.8010.27" / "Locales" / loc_name
            dst_pak = dst_tae_dir / "153.0.8010.27" / "Locales" / loc_name
            if src_pak.is_file():
                dst_pak.parent.mkdir(parents=True, exist_ok=True)
                pak_bytes = src_pak.read_bytes()
                pak_bytes = pak_bytes.replace(b"SunBrowser", b"TaeBrowser")
                pak_bytes = pak_bytes.replace(b"sunbrowser", b"taebrowser")
                dst_pak.write_bytes(pak_bytes)

        marker.write_text("taebrowser_153=ready\n", encoding="utf-8")

    return {
        "id": "taebrowser_153",
        "kernel_type": "taebrowser",
        "display_name": "TaeBrowser 153",
        "executable": str(exe_dst.resolve()),
    }


def _pad_replace(raw: bytes, old: bytes, new: bytes) -> bytes:
    """
    Replaces `old` with `new` and pads each replacement on the same line or end of file
    with spaces so the total byte count remains 100% identical.
    """
    if len(new) > len(old):
        raise ValueError("new bytes must be <= old bytes for padded replacement")
    diff = len(old) - len(new)
    out = bytearray()
    idx = 0
    n = len(raw)
    while idx < n:
        pos = raw.find(old, idx)
        if pos < 0:
            out.extend(raw[idx:])
            break
        out.extend(raw[idx:pos])
        out.extend(new)
        # Find end of current line to insert harmless trailing spaces before \r or \n
        nl_pos = raw.find(b"\n", pos + len(old))
        if nl_pos < 0:
            out.extend(raw[pos + len(old) :])
            out.extend(b" " * diff)
            break
        line_rest = raw[pos + len(old) : nl_pos]
        if line_rest.endswith(b"\r"):
            out.extend(line_rest[:-1])
            out.extend(b" " * diff)
            out.extend(b"\r\n")
        else:
            out.extend(line_rest)
            out.extend(b" " * diff)
            out.extend(b"\n")
        idx = nl_pos + 1
    assert len(out) == len(raw), f"Length changed: {len(out)} != {len(raw)}"
    return bytes(out)


def build_yangbrowser_kernel(src_flower_dir: Path, dst_yang_dir: Path) -> Dict[str, str]:
    """
    Builds `yangbrowser_153` (`YangBrowser.exe`) from `flower_153` (`flowerbrowser.exe`).
    Patches:
      - `YangBrowser.exe` PE VersionInfo (`FlowerBrowser` -> `YangBrowser\x00\x00`)
      - `application.ini` & `updater.ini`
      - `omni.ja` (`modules/AppConstants.sys.mjs` with `MOZ_APP_NAME: "YangBrowser"` & `MOZ_REQUIRE_SIGNING: false`)
      - `browser/omni.ja` (`brand.ftl`, `brand.dtd`, `brand.properties` -> `YangBrowser`)
      - `distribution/extensions/langpack-ko@firefox.mozilla.org.xpi` & `langpack-en-US@firefox.mozilla.org.xpi` (`YangBrowser`)
    """
    dst_yang_dir.mkdir(parents=True, exist_ok=True)
    marker = dst_yang_dir / ".freeanti_yangbrowser_v1"

    exe_dst = dst_yang_dir / "YangBrowser.exe"
    if not marker.is_file() or not exe_dst.is_file():
        skip = {
            "flowerbrowser.exe",
            "application.ini",
            "updater.ini",
            "omni.ja",
            "browser/omni.ja",
            "distribution/extensions/langpack-ko@firefox.mozilla.org.xpi",
            "distribution/extensions/langpack-en-US@firefox.mozilla.org.xpi",
        }
        _mirror_tree_hardlinked(src_flower_dir, dst_yang_dir, skip)

        # 1. Patch flowerbrowser.exe -> YangBrowser.exe
        src_exe = src_flower_dir / "flowerbrowser.exe"
        exe_bytes = src_exe.read_bytes()
        # UTF-16LE "FlowerBrowser" (13 chars) -> "YangBrowser\x00\x00" in VersionInfo
        exe_bytes = exe_bytes.replace(
            "FlowerBrowser.exe\x00".encode("utf-16le"),
            "YangBrowser.exe\x00\x00\x00".encode("utf-16le"),
        )
        exe_bytes = exe_bytes.replace(
            "FlowerBrowser\x00".encode("utf-16le"),
            "YangBrowser\x00\x00\x00".encode("utf-16le"),
        )
        exe_bytes = exe_bytes.replace(
            "FlowerBrowser Launcher".encode("utf-16le"),
            "YangBrowser Launcher  ".encode("utf-16le"),
        )
        exe_bytes = exe_bytes.replace(b"FlowerBrowser-default\x00", b"YangBrowser-default\x00\x00\x00")
        exe_dst.write_bytes(exe_bytes)

        flower_alias = dst_yang_dir / "flowerbrowser.exe"
        if not flower_alias.exists():
            shutil.copy2(str(exe_dst), str(flower_alias))

        # 2. Patch application.ini & updater.ini
        app_ini = (src_flower_dir / "application.ini").read_text(encoding="utf-8", errors="ignore")
        app_ini = (
            app_ini.replace("Name=Firefox", "Name=YangBrowser")
            .replace("RemotingName=FlowerBrowser-default", "RemotingName=YangBrowser-default")
            .replace("CodeName=FlowerBrowser", "CodeName=YangBrowser")
            .replace("Vendor=Mozilla", "Vendor=freeanti")
        )
        (dst_yang_dir / "application.ini").write_text(app_ini, encoding="utf-8")

        if (src_flower_dir / "updater.ini").is_file():
            upd_ini = (src_flower_dir / "updater.ini").read_text(encoding="utf-8", errors="ignore")
            upd_ini = upd_ini.replace("FlowerBrowser", "YangBrowser")
            (dst_yang_dir / "updater.ini").write_text(upd_ini, encoding="utf-8")

        # 3. Patch omni.ja (`modules/AppConstants.sys.mjs`) in-place
        src_omni = src_flower_dir / "omni.ja"
        dst_omni = dst_yang_dir / "omni.ja"
        shutil.copy2(str(src_omni), str(dst_omni))
        with zipfile.ZipFile(src_omni, "r") as zf:
            app_const_raw = zf.read("modules/AppConstants.sys.mjs")
        app_const_patched = _pad_replace(app_const_raw, b'"FlowerBrowser"', b'"YangBrowser"')
        app_const_patched = _pad_replace(
            app_const_patched,
            b"MOZ_REQUIRE_SIGNING: true,",
            b"MOZ_REQUIRE_SIGNING:false,",
        )
        _patch_zip_stored_entries_inplace(dst_omni, {"modules/AppConstants.sys.mjs": app_const_patched})

        # 4. Patch browser/omni.ja (`brand.ftl`, `brand.dtd`, `brand.properties`) in-place
        src_bomni = src_flower_dir / "browser" / "omni.ja"
        dst_bomni = dst_yang_dir / "browser" / "omni.ja"
        dst_bomni.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src_bomni), str(dst_bomni))
        with zipfile.ZipFile(src_bomni, "r") as zf:
            b_ftl = zf.read("localization/en-US/branding/brand.ftl")
            b_dtd = zf.read("chrome/en-US/locale/branding/brand.dtd")
            b_prop = zf.read("chrome/en-US/locale/branding/brand.properties")

        b_ftl_p = _pad_replace(b_ftl, b"FlowerBrowser", b"YangBrowser")
        b_ftl_p = _pad_replace(b_ftl_p, b"Flower Browser", b"YangBrowser")
        b_dtd_p = _pad_replace(b_dtd, b"FlowerBrowser", b"YangBrowser")
        b_dtd_p = _pad_replace(b_dtd_p, b"Flower Browser", b"YangBrowser")
        b_prop_p = _pad_replace(b_prop, b"FlowerBrowser", b"YangBrowser")
        b_prop_p = _pad_replace(b_prop_p, b"Flower Browser", b"YangBrowser")

        _patch_zip_stored_entries_inplace(
            dst_bomni,
            {
                "localization/en-US/branding/brand.ftl": b_ftl_p,
                "chrome/en-US/locale/branding/brand.dtd": b_dtd_p,
                "chrome/en-US/locale/branding/brand.properties": b_prop_p,
            },
        )

        # 5. Patch Korean & English langpack XPIs so Korean UI also shows "YangBrowser" instead of "Firefox"
        for xpi_name in ("langpack-ko@firefox.mozilla.org.xpi", "langpack-en-US@firefox.mozilla.org.xpi"):
            src_xpi = src_flower_dir / "distribution" / "extensions" / xpi_name
            dst_xpi = dst_yang_dir / "distribution" / "extensions" / xpi_name
            if src_xpi.is_file():
                dst_xpi.parent.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(src_xpi, "r") as zin, zipfile.ZipFile(
                    dst_xpi, "w", compression=zipfile.ZIP_DEFLATED
                ) as zout:
                    for item in zin.infolist():
                        data = zin.read(item.filename)
                        if "branding/brand." in item.filename or "browser/profiles.ftl" in item.filename:
                            txt = data.decode("utf-8", errors="ignore")
                            txt = (
                                txt.replace("Mozilla Firefox", "YangBrowser")
                                .replace("FlowerBrowser", "YangBrowser")
                                .replace("Flower Browser", "YangBrowser")
                                .replace("= Firefox", "= YangBrowser")
                            )
                            data = txt.encode("utf-8")
                        zout.writestr(item.filename, data)

        marker.write_text("yangbrowser_153=ready\n", encoding="utf-8")

    return {
        "id": "yangbrowser_153",
        "kernel_type": "yangbrowser",
        "display_name": "YangBrowser 153",
        "executable": str(exe_dst.resolve()),
    }


def _ensure_unpacked_zparts(kernels_root: Path) -> None:
    """
    Automatically reassembles and decompresses any split `.zpart00` archives inside `kernels/`
    on first run after cloning from GitHub (where files >100MB like `chrome.dll` and `xul.dll`
    are stored as <50MB `.zpart*` chunks).
    """
    if not kernels_root.is_dir():
        return
    for part0 in kernels_root.rglob("*.zpart00"):
        target_name = part0.name[: -len(".zpart00")]
        target_path = part0.parent / target_name
        if target_path.is_file() and target_path.stat().st_size > 0:
            continue
        parts = sorted(part0.parent.glob(f"{target_name}.zpart*"))
        if not parts:
            continue
        compressed = bytearray()
        for p in parts:
            compressed.extend(p.read_bytes())
        raw = zlib.decompress(bytes(compressed))
        target_path.write_bytes(raw)


def ensure_rebranded_kernels(base_dir: Path, cwd_global: Path) -> Tuple[Optional[Dict[str, str]], Optional[Dict[str, str]]]:
    kernels_root = base_dir / "kernels"
    _ensure_unpacked_zparts(kernels_root)
    tae_info = None
    yang_info = None

    src_chrome = cwd_global / "chrome_153"
    if (src_chrome / "SunBrowser.exe").is_file():
        tae_info = build_taebrowser_kernel(src_chrome, kernels_root / "taebrowser_153")

    src_flower = cwd_global / "flower_153"
    if (src_flower / "flowerbrowser.exe").is_file():
        yang_info = build_yangbrowser_kernel(src_flower, kernels_root / "yangbrowser_153")

    return tae_info, yang_info
