"""
Fingerprint Generator, GPU/OpenGL/WebGL/WebGPU Catalog & Proxy Geo-Locale Resolver for freeanti.
Faithfully implements the reverse-engineered TaeBrowser 153 (`SunBrowserPolicys`)
and YangBrowser 153 (`xul.dll` `custom.*` / `custom.static.*` / `custom.dynamic.*`) protocols.
"""

from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import random
import re
import socket
import struct
import subprocess
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .extension_builder import compute_chrome_validation_headers
from .platform_compat import get_subprocess_creationflags, resolve_curl_executable

# ---------------------------------------------------------------------------
# Country -> TimeZone, Browser Languages (Accept-Language), UI Lang, GPS Map
# Used when `follow_proxy_timezone`, `follow_proxy_language`, or
# `follow_proxy_geolocation` is enabled on a profile.
# ---------------------------------------------------------------------------
COUNTRY_LOCALE_MAP: Dict[str, Dict[str, Any]] = {
    "US": {
        "country_name": "United States (East / NY)",
        "timezone": "America/New_York",
        "languages": ["en-US", "en"],
        "ui_language": "en-US",
        "latitude": 40.7128,
        "longitude": -74.0060,
    },
    "US_WEST": {
        "country_name": "United States (West / LA)",
        "timezone": "America/Los_Angeles",
        "languages": ["en-US", "en"],
        "ui_language": "en-US",
        "latitude": 34.0522,
        "longitude": -118.2437,
    },
    "KR": {
        "country_name": "South Korea",
        "timezone": "Asia/Seoul",
        "languages": ["ko-KR", "ko", "en-US", "en"],
        "ui_language": "ko-KR",
        "latitude": 37.5665,
        "longitude": 126.9780,
    },
    "JP": {
        "country_name": "Japan",
        "timezone": "Asia/Tokyo",
        "languages": ["ja-JP", "ja", "en-US", "en"],
        "ui_language": "ja-JP",
        "latitude": 35.6762,
        "longitude": 139.6503,
    },
    "CN": {
        "country_name": "China",
        "timezone": "Asia/Shanghai",
        "languages": ["zh-CN", "zh", "en-US", "en"],
        "ui_language": "zh-CN",
        "latitude": 31.2304,
        "longitude": 121.4737,
    },
    "TW": {
        "country_name": "Taiwan",
        "timezone": "Asia/Taipei",
        "languages": ["zh-TW", "zh", "en-US", "en"],
        "ui_language": "zh-TW",
        "latitude": 25.0330,
        "longitude": 121.5654,
    },
    "HK": {
        "country_name": "Hong Kong",
        "timezone": "Asia/Hong_Kong",
        "languages": ["zh-HK", "zh-TW", "en-US", "en"],
        "ui_language": "zh-HK",
        "latitude": 22.3193,
        "longitude": 114.1694,
    },
    "SG": {
        "country_name": "Singapore",
        "timezone": "Asia/Singapore",
        "languages": ["en-SG", "en-US", "zh-SG", "en"],
        "ui_language": "en-US",
        "latitude": 1.3521,
        "longitude": 103.8198,
    },
    "VN": {
        "country_name": "Vietnam",
        "timezone": "Asia/Ho_Chi_Minh",
        "languages": ["vi-VN", "vi", "en-US", "en"],
        "ui_language": "vi-VN",
        "latitude": 10.8231,
        "longitude": 106.6297,
    },
    "TH": {
        "country_name": "Thailand",
        "timezone": "Asia/Bangkok",
        "languages": ["th-TH", "th", "en-US", "en"],
        "ui_language": "th-TH",
        "latitude": 13.7563,
        "longitude": 100.5018,
    },
    "PH": {
        "country_name": "Philippines",
        "timezone": "Asia/Manila",
        "languages": ["en-PH", "fil-PH", "en-US", "en"],
        "ui_language": "en-US",
        "latitude": 14.5995,
        "longitude": 120.9842,
    },
    "ID": {
        "country_name": "Indonesia",
        "timezone": "Asia/Jakarta",
        "languages": ["id-ID", "id", "en-US", "en"],
        "ui_language": "id-ID",
        "latitude": -6.2088,
        "longitude": 106.8456,
    },
    "MY": {
        "country_name": "Malaysia",
        "timezone": "Asia/Kuala_Lumpur",
        "languages": ["ms-MY", "en-MY", "en-US", "en"],
        "ui_language": "en-US",
        "latitude": 3.1390,
        "longitude": 101.6869,
    },
    "IN": {
        "country_name": "India",
        "timezone": "Asia/Kolkata",
        "languages": ["en-IN", "hi-IN", "en-US", "en"],
        "ui_language": "en-US",
        "latitude": 19.0760,
        "longitude": 72.8777,
    },
    "DE": {
        "country_name": "Germany",
        "timezone": "Europe/Berlin",
        "languages": ["de-DE", "de", "en-US", "en"],
        "ui_language": "de-DE",
        "latitude": 52.5200,
        "longitude": 13.4050,
    },
    "GB": {
        "country_name": "United Kingdom",
        "timezone": "Europe/London",
        "languages": ["en-GB", "en-US", "en"],
        "ui_language": "en-GB",
        "latitude": 51.5074,
        "longitude": -0.1278,
    },
    "FR": {
        "country_name": "France",
        "timezone": "Europe/Paris",
        "languages": ["fr-FR", "fr", "en-US", "en"],
        "ui_language": "fr-FR",
        "latitude": 48.8566,
        "longitude": 2.3522,
    },
    "NL": {
        "country_name": "Netherlands",
        "timezone": "Europe/Amsterdam",
        "languages": ["nl-NL", "nl", "en-US", "en"],
        "ui_language": "nl-NL",
        "latitude": 52.3676,
        "longitude": 4.9041,
    },
    "ES": {
        "country_name": "Spain",
        "timezone": "Europe/Madrid",
        "languages": ["es-ES", "es", "en-US", "en"],
        "ui_language": "es-ES",
        "latitude": 40.4168,
        "longitude": -3.7038,
    },
    "IT": {
        "country_name": "Italy",
        "timezone": "Europe/Rome",
        "languages": ["it-IT", "it", "en-US", "en"],
        "ui_language": "it-IT",
        "latitude": 41.9028,
        "longitude": 12.4964,
    },
    "RU": {
        "country_name": "Russia",
        "timezone": "Europe/Moscow",
        "languages": ["ru-RU", "ru", "en-US", "en"],
        "ui_language": "ru-RU",
        "latitude": 55.7558,
        "longitude": 37.6173,
    },
    "CA": {
        "country_name": "Canada",
        "timezone": "America/Toronto",
        "languages": ["en-CA", "en-US", "fr-CA", "en"],
        "ui_language": "en-US",
        "latitude": 43.6532,
        "longitude": -79.3832,
    },
    "BR": {
        "country_name": "Brazil",
        "timezone": "America/Sao_Paulo",
        "languages": ["pt-BR", "pt", "en-US", "en"],
        "ui_language": "pt-BR",
        "latitude": -23.5505,
        "longitude": -46.6333,
    },
    "AU": {
        "country_name": "Australia",
        "timezone": "Australia/Sydney",
        "languages": ["en-AU", "en-US", "en"],
        "ui_language": "en-US",
        "latitude": -33.8688,
        "longitude": 151.2093,
    },
    "ZA": {
        "country_name": "South Africa",
        "timezone": "Africa/Johannesburg",
        "languages": ["en-ZA", "en-US", "en"],
        "ui_language": "en-US",
        "latitude": -26.2041,
        "longitude": 28.0473,
    },
    "CO": {
        "country_name": "Colombia",
        "timezone": "America/Bogota",
        "languages": ["es-CO", "es", "en-US", "en"],
        "ui_language": "es-ES",
        "latitude": 4.7110,
        "longitude": -74.0721,
    },
    "MX": {
        "country_name": "Mexico",
        "timezone": "America/Mexico_City",
        "languages": ["es-MX", "es", "en-US", "en"],
        "ui_language": "es-ES",
        "latitude": 19.4326,
        "longitude": -99.1332,
    },
    "AR": {
        "country_name": "Argentina",
        "timezone": "America/Argentina/Buenos_Aires",
        "languages": ["es-AR", "es", "en-US", "en"],
        "ui_language": "es-ES",
        "latitude": -34.6037,
        "longitude": -58.3816,
    },
    "CL": {
        "country_name": "Chile",
        "timezone": "America/Santiago",
        "languages": ["es-CL", "es", "en-US", "en"],
        "ui_language": "es-ES",
        "latitude": -33.4489,
        "longitude": -70.6693,
    },
    "PE": {
        "country_name": "Peru",
        "timezone": "America/Lima",
        "languages": ["es-PE", "es", "en-US", "en"],
        "ui_language": "es-ES",
        "latitude": -12.0464,
        "longitude": -77.0428,
    },
    "PL": {
        "country_name": "Poland",
        "timezone": "Europe/Warsaw",
        "languages": ["pl-PL", "pl", "en-US", "en"],
        "ui_language": "pl-PL",
        "latitude": 52.2297,
        "longitude": 21.0122,
    },
    "TR": {
        "country_name": "Turkey",
        "timezone": "Europe/Istanbul",
        "languages": ["tr-TR", "tr", "en-US", "en"],
        "ui_language": "tr-TR",
        "latitude": 41.0082,
        "longitude": 28.9784,
    },
    "AE": {
        "country_name": "United Arab Emirates (UAE)",
        "timezone": "Asia/Dubai",
        "languages": ["ar-AE", "en-US", "en"],
        "ui_language": "en-US",
        "latitude": 25.2048,
        "longitude": 55.2708,
    },
    "SA": {
        "country_name": "Saudi Arabia",
        "timezone": "Asia/Riyadh",
        "languages": ["ar-SA", "en-US", "en"],
        "ui_language": "en-US",
        "latitude": 24.7136,
        "longitude": 46.6753,
    },
    "SE": {
        "country_name": "Sweden",
        "timezone": "Europe/Stockholm",
        "languages": ["sv-SE", "sv", "en-US", "en"],
        "ui_language": "sv-SE",
        "latitude": 59.3293,
        "longitude": 18.0686,
    },
    "CH": {
        "country_name": "Switzerland",
        "timezone": "Europe/Zurich",
        "languages": ["de-CH", "fr-CH", "de", "en-US", "en"],
        "ui_language": "de-DE",
        "latitude": 47.3769,
        "longitude": 8.5417,
    },
    "AT": {
        "country_name": "Austria",
        "timezone": "Europe/Vienna",
        "languages": ["de-AT", "de", "en-US", "en"],
        "ui_language": "de-DE",
        "latitude": 48.2082,
        "longitude": 16.3738,
    },
    "BE": {
        "country_name": "Belgium",
        "timezone": "Europe/Brussels",
        "languages": ["nl-BE", "fr-BE", "en-US", "en"],
        "ui_language": "nl-NL",
        "latitude": 50.8503,
        "longitude": 4.3517,
    },
    "PT": {
        "country_name": "Portugal",
        "timezone": "Europe/Lisbon",
        "languages": ["pt-PT", "pt", "en-US", "en"],
        "ui_language": "pt-PT",
        "latitude": 38.7223,
        "longitude": -9.1393,
    },
    "CZ": {
        "country_name": "Czechia",
        "timezone": "Europe/Prague",
        "languages": ["cs-CZ", "cs", "en-US", "en"],
        "ui_language": "cs-CZ",
        "latitude": 50.0755,
        "longitude": 14.4378,
    },
    "RO": {
        "country_name": "Romania",
        "timezone": "Europe/Bucharest",
        "languages": ["ro-RO", "ro", "en-US", "en"],
        "ui_language": "ro-RO",
        "latitude": 44.4268,
        "longitude": 26.1025,
    },
    "UA": {
        "country_name": "Ukraine",
        "timezone": "Europe/Kyiv",
        "languages": ["uk-UA", "uk", "en-US", "en"],
        "ui_language": "uk-UA",
        "latitude": 50.4501,
        "longitude": 30.5234,
    },
    "KZ": {
        "country_name": "Kazakhstan",
        "timezone": "Asia/Almaty",
        "languages": ["kk-KZ", "ru-RU", "en-US", "en"],
        "ui_language": "ru-RU",
        "latitude": 43.2220,
        "longitude": 76.8512,
    },
    "NZ": {
        "country_name": "New Zealand",
        "timezone": "Pacific/Auckland",
        "languages": ["en-NZ", "en-US", "en"],
        "ui_language": "en-US",
        "latitude": -36.8485,
        "longitude": 174.7633,
    },
}

# ---------------------------------------------------------------------------
# Comprehensive GPU / Graphics Card / OpenGL / Direct3D / Metal / Vulkan Catalog
# ---------------------------------------------------------------------------
GPU_CATALOG: List[Dict[str, Any]] = [
    # Windows — NVIDIA Direct3D11 (ANGLE D3D11)
    {
        "id": "win_rtx4090_d3d11",
        "os": "Windows",
        "brand": "NVIDIA",
        "model": "NVIDIA GeForce RTX 4090",
        "api": "Direct3D11",
        "angle_backend": "d3d11",
        "label": "NVIDIA GeForce RTX 4090 (Direct3D11 vs_5_0 ps_5_0)",
        "UNMASKED_VENDOR_WEBGL": "Google Inc. (NVIDIA)",
        "UNMASKED_RENDERER_WEBGL": "ANGLE (NVIDIA, NVIDIA GeForce RTX 4090 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "webgl_version": "WebGL 2.0 (OpenGL ES 3.0 Chromium)",
        "shading_language_version": "WebGL GLSL ES 3.00 (OpenGL ES GLSL ES 3.0 Chromium)",
        "GPUAdapterInfo": {"vendor": "nvidia", "architecture": "ada-lovelace"},
    },
    {
        "id": "win_rtx4070_d3d11",
        "os": "Windows",
        "brand": "NVIDIA",
        "model": "NVIDIA GeForce RTX 4070",
        "api": "Direct3D11",
        "angle_backend": "d3d11",
        "label": "NVIDIA GeForce RTX 4070 (Direct3D11 vs_5_0 ps_5_0)",
        "UNMASKED_VENDOR_WEBGL": "Google Inc. (NVIDIA)",
        "UNMASKED_RENDERER_WEBGL": "ANGLE (NVIDIA, NVIDIA GeForce RTX 4070 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "webgl_version": "WebGL 2.0 (OpenGL ES 3.0 Chromium)",
        "shading_language_version": "WebGL GLSL ES 3.00 (OpenGL ES GLSL ES 3.0 Chromium)",
        "GPUAdapterInfo": {"vendor": "nvidia", "architecture": "ada-lovelace"},
    },
    {
        "id": "win_rtx3080_d3d11",
        "os": "Windows",
        "brand": "NVIDIA",
        "model": "NVIDIA GeForce RTX 3080",
        "api": "Direct3D11",
        "angle_backend": "d3d11",
        "label": "NVIDIA GeForce RTX 3080 (Direct3D11 vs_5_0 ps_5_0)",
        "UNMASKED_VENDOR_WEBGL": "Google Inc. (NVIDIA)",
        "UNMASKED_RENDERER_WEBGL": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "webgl_version": "WebGL 2.0 (OpenGL ES 3.0 Chromium)",
        "shading_language_version": "WebGL GLSL ES 3.00 (OpenGL ES GLSL ES 3.0 Chromium)",
        "GPUAdapterInfo": {"vendor": "nvidia", "architecture": "ampere"},
    },
    {
        "id": "win_rtx3060_d3d11",
        "os": "Windows",
        "brand": "NVIDIA",
        "model": "NVIDIA GeForce RTX 3060",
        "api": "Direct3D11",
        "angle_backend": "d3d11",
        "label": "NVIDIA GeForce RTX 3060 (Direct3D11 vs_5_0 ps_5_0)",
        "UNMASKED_VENDOR_WEBGL": "Google Inc. (NVIDIA)",
        "UNMASKED_RENDERER_WEBGL": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "webgl_version": "WebGL 2.0 (OpenGL ES 3.0 Chromium)",
        "shading_language_version": "WebGL GLSL ES 3.00 (OpenGL ES GLSL ES 3.0 Chromium)",
        "GPUAdapterInfo": {"vendor": "nvidia", "architecture": "ampere"},
    },
    {
        "id": "win_gtx1660s_d3d11",
        "os": "Windows",
        "brand": "NVIDIA",
        "model": "NVIDIA GeForce GTX 1660 SUPER",
        "api": "Direct3D11",
        "angle_backend": "d3d11",
        "label": "NVIDIA GeForce GTX 1660 SUPER (Direct3D11 vs_5_0 ps_5_0)",
        "UNMASKED_VENDOR_WEBGL": "Google Inc. (NVIDIA)",
        "UNMASKED_RENDERER_WEBGL": "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 SUPER Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "webgl_version": "WebGL 2.0 (OpenGL ES 3.0 Chromium)",
        "shading_language_version": "WebGL GLSL ES 3.00 (OpenGL ES GLSL ES 3.0 Chromium)",
        "GPUAdapterInfo": {"vendor": "nvidia", "architecture": "turing"},
    },
    # Windows — OpenGL Backend (ANGLE OpenGL 4.6)
    {
        "id": "win_rtx4070_opengl",
        "os": "Windows",
        "brand": "NVIDIA",
        "model": "NVIDIA GeForce RTX 4070",
        "api": "OpenGL",
        "angle_backend": "gl",
        "label": "NVIDIA GeForce RTX 4070 (OpenGL 4.6.0 NVIDIA 551.86)",
        "UNMASKED_VENDOR_WEBGL": "Google Inc. (NVIDIA Corporation)",
        "UNMASKED_RENDERER_WEBGL": "ANGLE (NVIDIA Corporation, NVIDIA GeForce RTX 4070/PCIe/SSE2, OpenGL 4.6.0 NVIDIA 551.86)",
        "webgl_version": "WebGL 2.0 (OpenGL ES 3.0 Chromium)",
        "shading_language_version": "WebGL GLSL ES 3.00 (OpenGL ES GLSL ES 3.0 Chromium)",
        "GPUAdapterInfo": {"vendor": "nvidia", "architecture": "ada-lovelace"},
    },
    {
        "id": "win_rtx3060_opengl",
        "os": "Windows",
        "brand": "NVIDIA",
        "model": "NVIDIA GeForce RTX 3060",
        "api": "OpenGL",
        "angle_backend": "gl",
        "label": "NVIDIA GeForce RTX 3060 (OpenGL 4.6.0 NVIDIA 546.33)",
        "UNMASKED_VENDOR_WEBGL": "Google Inc. (NVIDIA Corporation)",
        "UNMASKED_RENDERER_WEBGL": "ANGLE (NVIDIA Corporation, NVIDIA GeForce RTX 3060/PCIe/SSE2, OpenGL 4.6.0 NVIDIA 546.33)",
        "webgl_version": "WebGL 2.0 (OpenGL ES 3.0 Chromium)",
        "shading_language_version": "WebGL GLSL ES 3.00 (OpenGL ES GLSL ES 3.0 Chromium)",
        "GPUAdapterInfo": {"vendor": "nvidia", "architecture": "ampere"},
    },
    # Windows — AMD Radeon (Direct3D11 & OpenGL)
    {
        "id": "win_rx7900xtx_d3d11",
        "os": "Windows",
        "brand": "AMD",
        "model": "AMD Radeon RX 7900 XTX",
        "api": "Direct3D11",
        "angle_backend": "d3d11",
        "label": "AMD Radeon RX 7900 XTX (Direct3D11 vs_5_0 ps_5_0)",
        "UNMASKED_VENDOR_WEBGL": "Google Inc. (AMD)",
        "UNMASKED_RENDERER_WEBGL": "ANGLE (AMD, AMD Radeon RX 7900 XTX Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "webgl_version": "WebGL 2.0 (OpenGL ES 3.0 Chromium)",
        "shading_language_version": "WebGL GLSL ES 3.00 (OpenGL ES GLSL ES 3.0 Chromium)",
        "GPUAdapterInfo": {"vendor": "amd", "architecture": "rdna-3"},
    },
    {
        "id": "win_rx6700xt_d3d11",
        "os": "Windows",
        "brand": "AMD",
        "model": "AMD Radeon RX 6700 XT",
        "api": "Direct3D11",
        "angle_backend": "d3d11",
        "label": "AMD Radeon RX 6700 XT (Direct3D11 vs_5_0 ps_5_0)",
        "UNMASKED_VENDOR_WEBGL": "Google Inc. (AMD)",
        "UNMASKED_RENDERER_WEBGL": "ANGLE (AMD, AMD Radeon RX 6700 XT Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "webgl_version": "WebGL 2.0 (OpenGL ES 3.0 Chromium)",
        "shading_language_version": "WebGL GLSL ES 3.00 (OpenGL ES GLSL ES 3.0 Chromium)",
        "GPUAdapterInfo": {"vendor": "amd", "architecture": "rdna-2"},
    },
    {
        "id": "win_rx6700xt_opengl",
        "os": "Windows",
        "brand": "AMD",
        "model": "AMD Radeon RX 6700 XT",
        "api": "OpenGL",
        "angle_backend": "gl",
        "label": "AMD Radeon RX 6700 XT (OpenGL 4.6.0 Core Profile)",
        "UNMASKED_VENDOR_WEBGL": "Google Inc. (ATI Technologies Inc.)",
        "UNMASKED_RENDERER_WEBGL": "ANGLE (ATI Technologies Inc., AMD Radeon RX 6700 XT, OpenGL 4.6.0 Core Profile Context)",
        "webgl_version": "WebGL 2.0 (OpenGL ES 3.0 Chromium)",
        "shading_language_version": "WebGL GLSL ES 3.00 (OpenGL ES GLSL ES 3.0 Chromium)",
        "GPUAdapterInfo": {"vendor": "amd", "architecture": "rdna-2"},
    },
    # Windows — Intel (Direct3D11, Direct3D9Ex, Vulkan)
    {
        "id": "win_intel_iris_xe_d3d11",
        "os": "Windows",
        "brand": "Intel",
        "model": "Intel(R) Iris(R) Xe Graphics",
        "api": "Direct3D11",
        "angle_backend": "d3d11",
        "label": "Intel(R) Iris(R) Xe Graphics (Direct3D11 vs_5_0 ps_5_0)",
        "UNMASKED_VENDOR_WEBGL": "Google Inc. (Intel)",
        "UNMASKED_RENDERER_WEBGL": "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "webgl_version": "WebGL 2.0 (OpenGL ES 3.0 Chromium)",
        "shading_language_version": "WebGL GLSL ES 3.00 (OpenGL ES GLSL ES 3.0 Chromium)",
        "GPUAdapterInfo": {"vendor": "intel", "architecture": "gen-12lp"},
    },
    {
        "id": "win_intel_uhd770_d3d11",
        "os": "Windows",
        "brand": "Intel",
        "model": "Intel(R) UHD Graphics 770",
        "api": "Direct3D11",
        "angle_backend": "d3d11",
        "label": "Intel(R) UHD Graphics 770 (Direct3D11 vs_5_0 ps_5_0)",
        "UNMASKED_VENDOR_WEBGL": "Google Inc. (Intel)",
        "UNMASKED_RENDERER_WEBGL": "ANGLE (Intel, Intel(R) UHD Graphics 770 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "webgl_version": "WebGL 2.0 (OpenGL ES 3.0 Chromium)",
        "shading_language_version": "WebGL GLSL ES 3.00 (OpenGL ES GLSL ES 3.0 Chromium)",
        "GPUAdapterInfo": {"vendor": "intel", "architecture": "gen-12lp"},
    },
    {
        "id": "win_intel_hd620_d3d9",
        "os": "Windows",
        "brand": "Intel",
        "model": "Intel(R) HD Graphics 620",
        "api": "Direct3D9",
        "angle_backend": "d3d9",
        "label": "Intel(R) HD Graphics 620 (Direct3D9Ex vs_3_0 ps_3_0)",
        "UNMASKED_VENDOR_WEBGL": "Google Inc.",
        "UNMASKED_RENDERER_WEBGL": "ANGLE (Intel(R) HD Graphics 620 Direct3D9Ex vs_3_0 ps_3_0)",
        "webgl_version": "WebGL 1.0 (OpenGL ES 2.0 Chromium)",
        "shading_language_version": "WebGL GLSL ES 1.0 (OpenGL ES GLSL ES 1.0 Chromium)",
        "GPUAdapterInfo": {"vendor": "intel", "architecture": "gen-9"},
    },
    # macOS — Apple Metal & OpenGL Engine
    {
        "id": "mac_apple_m3_max_metal",
        "os": "macOS",
        "brand": "Apple",
        "model": "Apple M3 Max",
        "api": "Metal",
        "angle_backend": "metal",
        "label": "Apple M3 Max (ANGLE Metal Renderer)",
        "UNMASKED_VENDOR_WEBGL": "Google Inc. (Apple)",
        "UNMASKED_RENDERER_WEBGL": "ANGLE (Apple, ANGLE Metal Renderer: Apple M3 Max, Unspecified Version)",
        "webgl_version": "WebGL 2.0 (OpenGL ES 3.0 Chromium)",
        "shading_language_version": "WebGL GLSL ES 3.00 (OpenGL ES GLSL ES 3.0 Chromium)",
        "GPUAdapterInfo": {"vendor": "apple", "architecture": "apple-m3"},
    },
    {
        "id": "mac_apple_m3_metal",
        "os": "macOS",
        "brand": "Apple",
        "model": "Apple M3",
        "api": "Metal",
        "angle_backend": "metal",
        "label": "Apple M3 (ANGLE Metal Renderer)",
        "UNMASKED_VENDOR_WEBGL": "Google Inc. (Apple)",
        "UNMASKED_RENDERER_WEBGL": "ANGLE (Apple, ANGLE Metal Renderer: Apple M3, Unspecified Version)",
        "webgl_version": "WebGL 2.0 (OpenGL ES 3.0 Chromium)",
        "shading_language_version": "WebGL GLSL ES 3.00 (OpenGL ES GLSL ES 3.0 Chromium)",
        "GPUAdapterInfo": {"vendor": "apple", "architecture": "apple-m3"},
    },
    {
        "id": "mac_apple_m2_pro_metal",
        "os": "macOS",
        "brand": "Apple",
        "model": "Apple M2 Pro",
        "api": "Metal",
        "angle_backend": "metal",
        "label": "Apple M2 Pro (ANGLE Metal Renderer)",
        "UNMASKED_VENDOR_WEBGL": "Google Inc. (Apple)",
        "UNMASKED_RENDERER_WEBGL": "ANGLE (Apple, ANGLE Metal Renderer: Apple M2 Pro, Unspecified Version)",
        "webgl_version": "WebGL 2.0 (OpenGL ES 3.0 Chromium)",
        "shading_language_version": "WebGL GLSL ES 3.00 (OpenGL ES GLSL ES 3.0 Chromium)",
        "GPUAdapterInfo": {"vendor": "apple", "architecture": "apple-m2"},
    },
    {
        "id": "mac_apple_m1_metal",
        "os": "macOS",
        "brand": "Apple",
        "model": "Apple M1",
        "api": "Metal",
        "angle_backend": "metal",
        "label": "Apple M1 (ANGLE Metal Renderer)",
        "UNMASKED_VENDOR_WEBGL": "Google Inc. (Apple)",
        "UNMASKED_RENDERER_WEBGL": "ANGLE (Apple, ANGLE Metal Renderer: Apple M1, Unspecified Version)",
        "webgl_version": "WebGL 2.0 (OpenGL ES 3.0 Chromium)",
        "shading_language_version": "WebGL GLSL ES 3.00 (OpenGL ES GLSL ES 3.0 Chromium)",
        "GPUAdapterInfo": {"vendor": "apple", "architecture": "apple-m1"},
    },
    {
        "id": "mac_intel_iris_opengl",
        "os": "macOS",
        "brand": "Intel",
        "model": "Intel(R) Iris(TM) Plus Graphics",
        "api": "OpenGL",
        "angle_backend": "gl",
        "label": "Intel(R) Iris(TM) Plus Graphics (macOS OpenGL Engine)",
        "UNMASKED_VENDOR_WEBGL": "Intel Inc.",
        "UNMASKED_RENDERER_WEBGL": "Intel(R) Iris(TM) Plus Graphics OpenGL Engine",
        "webgl_version": "WebGL 2.0 (OpenGL ES 3.0 Chromium)",
        "shading_language_version": "WebGL GLSL ES 3.00 (OpenGL ES GLSL ES 3.0 Chromium)",
        "GPUAdapterInfo": {"vendor": "intel", "architecture": "gen-11"},
    },
    {
        "id": "mac_amd_r9_opengl",
        "os": "macOS",
        "brand": "AMD",
        "model": "AMD Radeon R9 M370X",
        "api": "OpenGL",
        "angle_backend": "gl",
        "label": "AMD Radeon R9 M370X (macOS OpenGL Engine)",
        "UNMASKED_VENDOR_WEBGL": "ATI Technologies Inc.",
        "UNMASKED_RENDERER_WEBGL": "AMD Radeon R9 M370X OpenGL Engine",
        "webgl_version": "WebGL 2.0 (OpenGL ES 3.0 Chromium)",
        "shading_language_version": "WebGL GLSL ES 3.00 (OpenGL ES GLSL ES 3.0 Chromium)",
        "GPUAdapterInfo": {"vendor": "amd", "architecture": "gcn-1"},
    },
    # Linux — OpenGL 4.5 / 4.6 Mesa & NVIDIA
    {
        "id": "linux_rtx3080_opengl",
        "os": "Linux",
        "brand": "NVIDIA",
        "model": "NVIDIA GeForce RTX 3080",
        "api": "OpenGL",
        "angle_backend": "gl",
        "label": "NVIDIA GeForce RTX 3080 (Linux OpenGL 4.5.0)",
        "UNMASKED_VENDOR_WEBGL": "Google Inc. (NVIDIA Corporation)",
        "UNMASKED_RENDERER_WEBGL": "ANGLE (NVIDIA Corporation, NVIDIA GeForce RTX 3080/PCIe/SSE2, OpenGL 4.5.0)",
        "webgl_version": "WebGL 2.0 (OpenGL ES 3.0 Chromium)",
        "shading_language_version": "WebGL GLSL ES 3.00 (OpenGL ES GLSL ES 3.0 Chromium)",
        "GPUAdapterInfo": {"vendor": "nvidia", "architecture": "ampere"},
    },
    {
        "id": "linux_intel_uhd770_opengl",
        "os": "Linux",
        "brand": "Intel",
        "model": "Mesa Intel(R) UHD Graphics 770",
        "api": "OpenGL",
        "angle_backend": "gl",
        "label": "Mesa Intel(R) UHD Graphics 770 (Linux OpenGL 4.6)",
        "UNMASKED_VENDOR_WEBGL": "Google Inc. (Intel)",
        "UNMASKED_RENDERER_WEBGL": "ANGLE (Intel, Mesa Intel(R) UHD Graphics 770 (ADL-S GT1), OpenGL 4.6)",
        "webgl_version": "WebGL 2.0 (OpenGL ES 3.0 Chromium)",
        "shading_language_version": "WebGL GLSL ES 3.00 (OpenGL ES GLSL ES 3.0 Chromium)",
        "GPUAdapterInfo": {"vendor": "intel", "architecture": "gen-12lp"},
    },
    # Android — Qualcomm Adreno & ARM Mali (OpenGL ES 3.2)
    {
        "id": "android_adreno740_gles",
        "os": "Android",
        "brand": "Qualcomm",
        "model": "Adreno (TM) 740",
        "api": "OpenGL ES",
        "angle_backend": "gles",
        "label": "Qualcomm Adreno (TM) 740 (OpenGL ES 3.2)",
        "UNMASKED_VENDOR_WEBGL": "Qualcomm",
        "UNMASKED_RENDERER_WEBGL": "Adreno (TM) 740",
        "webgl_version": "WebGL 2.0 (OpenGL ES 3.2 Chromium)",
        "shading_language_version": "WebGL GLSL ES 3.00 (OpenGL ES GLSL ES 3.2 Chromium)",
        "GPUAdapterInfo": {"vendor": "qualcomm", "architecture": "adreno-7xx"},
    },
    {
        "id": "android_adreno650_gles",
        "os": "Android",
        "brand": "Qualcomm",
        "model": "Adreno (TM) 650",
        "api": "OpenGL ES",
        "angle_backend": "gles",
        "label": "Qualcomm Adreno (TM) 650 (OpenGL ES 3.2)",
        "UNMASKED_VENDOR_WEBGL": "Qualcomm",
        "UNMASKED_RENDERER_WEBGL": "Adreno (TM) 650",
        "webgl_version": "WebGL 2.0 (OpenGL ES 3.2 Chromium)",
        "shading_language_version": "WebGL GLSL ES 3.00 (OpenGL ES GLSL ES 3.2 Chromium)",
        "GPUAdapterInfo": {"vendor": "qualcomm", "architecture": "adreno-6xx"},
    },
    {
        "id": "android_mali_g715_gles",
        "os": "Android",
        "brand": "ARM",
        "model": "Mali-G715 Immortalis MC11",
        "api": "OpenGL ES",
        "angle_backend": "gles",
        "label": "ARM Mali-G715 Immortalis MC11 (OpenGL ES 3.2)",
        "UNMASKED_VENDOR_WEBGL": "ARM",
        "UNMASKED_RENDERER_WEBGL": "Mali-G715 Immortalis MC11",
        "webgl_version": "WebGL 2.0 (OpenGL ES 3.2 Chromium)",
        "shading_language_version": "WebGL GLSL ES 3.00 (OpenGL ES GLSL ES 3.2 Chromium)",
        "GPUAdapterInfo": {"vendor": "arm", "architecture": "valhall"},
    },
    # iPhone — Apple GPU (Metal / WebKit OpenGL ES)
    {
        "id": "ios_apple_gpu_metal",
        "os": "iPhone",
        "brand": "Apple",
        "model": "Apple GPU (A17 Pro)",
        "api": "Metal",
        "angle_backend": "metal",
        "label": "Apple GPU — iPhone 15 Pro (Metal / MAX_VIEWPORT_DIMS 16384)",
        "UNMASKED_VENDOR_WEBGL": "Apple Inc.",
        "UNMASKED_RENDERER_WEBGL": "Apple GPU",
        "webgl_version": "WebGL 2.0 (OpenGL ES 3.0 Metal - 99)",
        "shading_language_version": "WebGL GLSL ES 3.00 (OpenGL ES GLSL ES 3.0 Metal - 99)",
        "GPUAdapterInfo": {"vendor": "apple", "architecture": "apple-a17"},
        "MAX_VIEWPORT_DIMS": [16384, 16384],
    },
]

# Group presets by OS for fast lookup
WEBGL_PRESETS: Dict[str, List[Dict[str, Any]]] = {
    os_name: [item for item in GPU_CATALOG if item["os"] == os_name]
    for os_name in ("Windows", "macOS", "Linux", "Android", "iPhone")
}

# Cross-OS font pools for Fakefonts substitution & DisabledFonts masking
WIN32_FONTS = [
    "Arial", "Calibri", "Cambria", "Candara", "Comic Sans MS", "Consolas",
    "Constantia", "Corbel", "Courier New", "Ebrima", "Franklin Gothic Medium",
    "Gabriola", "Gadugi", "Georgia", "Impact", "Javanese Text", "Leelawadee UI",
    "Lucida Console", "Lucida Sans Unicode", "Malgun Gothic", "Microsoft Himalaya",
    "Microsoft JhengHei", "Microsoft New Tai Lue", "Microsoft PhagsPa",
    "Microsoft Sans Serif", "Microsoft Tai Le", "Microsoft YaHei", "Microsoft Yi Baiti",
    "MingLiU-ExtB", "Mongolian Baiti", "MS Gothic", "MV Boli", "Myanmar Text",
    "Nirmala UI", "Palatino Linotype", "Segoe Print", "Segoe Script", "Segoe UI",
    "Segoe UI Historic", "Segoe UI Emoji", "Segoe UI Symbol", "SimSun", "Sitka",
    "Sylfaen", "Symbol", "Tahoma", "Times New Roman", "Trebuchet MS", "Verdana",
    "Webdings", "Wingdings", "Yu Gothic",
]

DARWIN_FONTS = [
    "American Typewriter", "Andale Mono", "Apple Chancery", "Apple Color Emoji",
    "Apple SD Gothic Neo", "Apple Symbols", "AppleGothic", "AppleMyungjo",
    "Avenir", "Avenir Next", "Baskerville", "Big Caslon", "Brush Script MT",
    "Chalkboard", "Chalkboard SE", "Cochin", "Copperplate", "Courier",
    "Didot", "Futura", "Geneva", "Gill Sans", "Helvetica", "Helvetica Neue",
    "Herculanum", "Hoefler Text", "Lucida Grande", "Luminari", "Marker Felt",
    "Menlo", "Monaco", "Noteworthy", "Optima", "Palatino", "Papyrus",
    "Phosphate", "PingFang HK", "PingFang SC", "PingFang TC", "Rockwell",
    "Savoye LET", "SignPainter", "Skia", "Snell Roundhand", "STHeiti",
    "Zapfino",
]

LINUX_FONTS = [
    "DejaVu Sans", "DejaVu Sans Mono", "DejaVu Serif", "Droid Sans Fallback",
    "FreeMono", "FreeSans", "FreeSerif", "Liberation Mono", "Liberation Sans",
    "Liberation Serif", "Noto Color Emoji", "Noto Mono", "Noto Sans",
    "Noto Sans CJK KR", "Noto Sans CJK SC", "Noto Serif", "Ubuntu", "Ubuntu Mono",
]

MOBILE_SAFE_FONTS = [
    "Roboto", "Droid Sans", "Droid Serif", "Droid Sans Mono", "Noto Sans",
    "Noto Serif", "Noto Color Emoji", "Helvetica", "Helvetica Neue", "Arial",
    "Courier New", "Georgia", "Times New Roman", "Trebuchet MS", "Verdana",
]

SCREEN_RESOLUTIONS = {
    "Windows": ["1920_1080", "2560_1440", "1536_864", "1366_768", "1600_900"],
    "macOS": ["1440_900", "1680_1050", "1728_1117", "1920_1080", "2560_1600"],
    "Linux": ["1920_1080", "2560_1440", "1600_900"],
    "Android": ["412_915", "393_873", "360_800", "384_854"],
    "iPhone": ["393_852", "430_932", "390_844", "375_812"],
}


ADSPOWER_B64_STD = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
ADSPOWER_B64_CUSTOM = "hTy1bfRJz4nLPcBCO7WtmNIaGvVeul5Zo8kq32UxrYw_-0gsjp96SDFXQiEMKdHA"
_B64_ENC_TRANS = str.maketrans(ADSPOWER_B64_STD, ADSPOWER_B64_CUSTOM)
_B64_DEC_TRANS = str.maketrans(ADSPOWER_B64_CUSTOM, ADSPOWER_B64_STD)


def adspower_encode_base64(text: str) -> str:
    """
    Exact custom-alphabet Base64 encoder expected by `TaeBrowser.exe` (`chrome.dll`)
    and `YangBrowser.exe` (`xul.dll`) for `--extended-parameters`, `_static`, and `_webrtc`.
    """
    std_b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
    return std_b64.translate(_B64_ENC_TRANS)


def adspower_decode_base64(encoded: str) -> str:
    if not encoded:
        return ""
    std_b64 = encoded.translate(_B64_DEC_TRANS)
    return base64.b64decode(std_b64.encode("ascii")).decode("utf-8", errors="replace")


def md5_hex(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def js_hashcode(text: str) -> int:
    h = 0
    for ch in text:
        h = (((h << 5) - h) + ord(ch)) & 0xFFFFFFFF
        if h & 0x80000000:
            h -= 0x100000000
    return h


def compute_client_rect_fp(profile_id: str, custom_id: Optional[int] = None) -> int:
    if custom_id is not None and abs(int(custom_id)) > 0:
        return int(custom_id)
    rem = abs(js_hashcode(profile_id)) % 20000
    val = rem - 10000
    return val if val != 0 else 1


def compute_audio_noise(profile_id: str, custom_id: Optional[int] = None) -> int:
    if custom_id is not None and abs(int(custom_id)) > 0:
        return int(custom_id)
    return (abs(js_hashcode(profile_id)) % 9999) + 1


def generate_local_webrtc_ip(profile_id: str) -> str:
    if not profile_id:
        return "192.168.1.2"
    char_sum = sum(ord(ch) for ch in profile_id)
    prefix = ["192.168", "172.16", "192.168"][char_sum % 3]
    octet3 = char_sum % 255
    octet4 = octet3 + 1
    return f"{prefix}.{octet3}.{octet4}"


def normalize_kernel_name(kernel_type: str) -> str:
    s = (kernel_type or "taebrowser").strip().lower()
    if s in ("yangbrowser", "yangbrower", "yang", "yang_153", "flowerbrowser", "flower", "flower_153", "firefox", "gecko"):
        return "yangbrowser"
    return "taebrowser"


def resolve_country_locale(country_code: Optional[str], fallback_ip: str = "") -> Dict[str, Any]:
    """
    Resolves Country Code (or IP prefix) to TimeZone, Languages (`Accept-Language`),
    UI Language (`--lang`), and GPS coordinates.
    """
    code = (country_code or "").strip().upper()
    if not code and fallback_ip:
        # Heuristic fallback by common residential/test IP prefixes
        if fallback_ip.startswith(("211.", "210.", "175.", "121.", "59.", "220.")):
            code = "KR"
        elif fallback_ip.startswith(("198.51.", "203.0.113.", "8.", "4.", "64.")):
            code = "US"
        elif fallback_ip.startswith(("126.", "133.", "153.")):
            code = "JP"
        elif fallback_ip.startswith(("85.", "88.", "91.")):
            code = "DE"
    if code in COUNTRY_LOCALE_MAP:
        info = COUNTRY_LOCALE_MAP[code]
        return {
            "country_code": code,
            "country_name": info["country_name"],
            "timezone": info["timezone"],
            "languages": list(info["languages"]),
            "accept_language": format_accept_language(info["languages"]),
            "ui_language": info["ui_language"],
            "latitude": info["latitude"],
            "longitude": info["longitude"],
        }
    if len(code) == 2 and code.isalpha():
        langs = ["en-US", "en"]
        return {
            "country_code": code,
            "country_name": code,
            "timezone": "UTC",
            "languages": langs,
            "accept_language": format_accept_language(langs),
            "ui_language": "en-US",
            "latitude": 40.7128,
            "longitude": -74.0060,
        }
    info = COUNTRY_LOCALE_MAP["US"]
    return {
        "country_code": "US",
        "country_name": info["country_name"],
        "timezone": info["timezone"],
        "languages": list(info["languages"]),
        "accept_language": format_accept_language(info["languages"]),
        "ui_language": info["ui_language"],
        "latitude": info["latitude"],
        "longitude": info["longitude"],
    }


def parse_proxy_string(raw: str, default_type: str = "socks5") -> Dict[str, Any]:
    """
    Parses common proxy string formats into structured fields:
      - `socks5://user:pass@host:port` / `http://user:pass@host:port`
      - `user:pass@host:port`
      - `host:port:user:pass`
      - `host:port@user:pass`
      - `host:port`
    Returns: `{"type", "host", "port", "username", "password"}`
    """
    s = (raw or "").strip()
    ptype = (default_type or "socks5").strip().lower()
    if ptype not in ("socks5", "http", "https", "direct"):
        ptype = "socks5"
    if not s:
        return {"type": ptype, "host": "", "port": 0, "username": "", "password": ""}

    m_scheme = re.match(r"^([a-zA-Z0-9]+):\/\/(.*)$", s)
    if m_scheme:
        scheme = m_scheme.group(1).lower()
        if scheme in ("socks5", "socks5h", "socks"):
            ptype = "socks5"
        elif scheme in ("http", "https"):
            ptype = scheme
        s = m_scheme.group(2).strip().rstrip("/")

    username = ""
    password = ""
    host = ""
    port = 0

    if "@" in s:
        left, right = s.rsplit("@", 1)
        # Check whether right side is host:port (standard user:pass@host:port) or user:pass (host:port@user:pass)
        r_parts = right.split(":")
        l_parts = left.split(":")
        if len(r_parts) == 2 and r_parts[1].isdigit():
            host = r_parts[0].strip()
            port = int(r_parts[1])
            if ":" in left:
                username, password = left.split(":", 1)
            else:
                username = left
        elif len(l_parts) == 2 and l_parts[1].isdigit():
            host = l_parts[0].strip()
            port = int(l_parts[1])
            if ":" in right:
                username, password = right.split(":", 1)
            else:
                username = right
    else:
        parts = s.split(":")
        if len(parts) >= 4 and parts[1].isdigit():
            host = parts[0].strip()
            port = int(parts[1])
            username = parts[2].strip()
            password = ":".join(parts[3:]).strip()
        elif len(parts) == 2 and parts[1].isdigit():
            host = parts[0].strip()
            port = int(parts[1])
        else:
            host = s

    return {
        "type": ptype,
        "host": host,
        "port": port,
        "username": username,
        "password": password,
    }


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Unexpected EOF from proxy socket")
        buf.extend(chunk)
    return bytes(buf)


def _tunnel_http_get_pure_python(
    ptype: str,
    phost: str,
    pport: int,
    puser: str = "",
    ppass: str = "",
    target_host: str = "ip-api.com",
    target_port: int = 80,
    target_path: str = "/json/",
    timeout: float = 5.0,
) -> Optional[str]:
    """
    Zero-dependency pure-Python SOCKS5 (RFC 1928 + RFC 1929 auth + remote DNS ATYP=0x03)
    and HTTP proxy client fallback. Ensures proxy GeoIP tunneling works on all OSes and
    architectures even when external `curl` is unavailable.
    """
    scheme = (ptype or "socks5").strip().lower()
    if scheme in ("http", "https"):
        auth_str = f"{urllib.parse.quote(puser)}:{urllib.parse.quote(ppass)}@" if puser else ""
        proxy_url = f"{scheme}://{auth_str}{phost}:{pport}"
        handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
        opener = urllib.request.build_opener(handler)
        url = f"http://{target_host}:{target_port}{target_path}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Connection": "close"})
        with opener.open(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="ignore")

    # SOCKS5 / SOCKS5h protocol (RFC 1928 & RFC 1929)
    with socket.create_connection((phost, int(pport)), timeout=timeout) as sock:
        sock.settimeout(timeout)
        if puser:
            sock.sendall(b"\x05\x02\x00\x02")
        else:
            sock.sendall(b"\x05\x01\x00")
        ver, method = _recv_exact(sock, 2)
        if ver != 5 or method == 0xFF:
            raise PermissionError("SOCKS5 proxy rejected authentication methods")
        if method == 0x02:
            u_bytes = puser.encode("utf-8")[:255]
            p_bytes = ppass.encode("utf-8")[:255]
            sock.sendall(b"\x01" + bytes([len(u_bytes)]) + u_bytes + bytes([len(p_bytes)]) + p_bytes)
            auth_ver, auth_status = _recv_exact(sock, 2)
            if auth_status != 0x00:
                raise PermissionError(f"SOCKS5 RFC 1929 auth failed with status {auth_status}")

        host_bytes = target_host.encode("idna")[:255]
        req_pkt = b"\x05\x01\x00\x03" + bytes([len(host_bytes)]) + host_bytes + struct.pack(">H", int(target_port))
        sock.sendall(req_pkt)
        r_ver, r_rep, _r_rsv, r_atyp = _recv_exact(sock, 4)
        if r_ver != 5 or r_rep != 0x00:
            raise ConnectionError(f"SOCKS5 CONNECT failed with reply code {r_rep}")
        if r_atyp == 0x01:
            _recv_exact(sock, 4 + 2)
        elif r_atyp == 0x03:
            d_len = _recv_exact(sock, 1)[0]
            _recv_exact(sock, d_len + 2)
        elif r_atyp == 0x04:
            _recv_exact(sock, 16 + 2)

        http_req = (
            f"GET {target_path} HTTP/1.1\r\n"
            f"Host: {target_host}\r\n"
            f"User-Agent: Mozilla/5.0\r\n"
            f"Accept: application/json\r\n"
            f"Connection: close\r\n\r\n"
        ).encode("ascii")
        sock.sendall(http_req)

        raw_resp = bytearray()
        while len(raw_resp) < 65536:
            chunk = sock.recv(4096)
            if not chunk:
                break
            raw_resp.extend(chunk)
        resp_text = raw_resp.decode("utf-8", errors="ignore")
        if "\r\n\r\n" in resp_text:
            return resp_text.split("\r\n\r\n", 1)[1].strip()
        return resp_text.strip()


def check_proxy_and_resolve_geo(
    proxy: Optional[Dict[str, Any]] = None,
    target_ip: Optional[str] = None,
    country_hint: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Checks the proxy / exit IP against GeoIP (`ip-api.com`).
    1. When `proxy` has `type != "direct"`, `host`, and `port` (and no explicit `target_ip`),
       tunnels directly through the SOCKS5/HTTP proxy using `curl.exe -x ...` to detect the real
       exit IP, Country, TimeZone, Languages, and GPS coordinates.
    2. Otherwise queries `ip-api.com/json/{target_ip}` directly and falls back to `COUNTRY_LOCALE_MAP`.
    """
    prx = dict(proxy or {})
    raw_host = str(prx.get("host") or "").strip()
    if raw_host and ("://" in raw_host or "@" in raw_host or raw_host.count(":") >= 1):
        parsed = parse_proxy_string(raw_host, str(prx.get("type") or "socks5"))
        if parsed["host"]:
            prx["type"] = parsed["type"] if prx.get("type") in (None, "", "direct") else prx.get("type")
            prx["host"] = parsed["host"]
            if parsed["port"]:
                prx["port"] = parsed["port"]
            if parsed["username"] and not prx.get("username"):
                prx["username"] = parsed["username"]
            if parsed["password"] and not prx.get("password"):
                prx["password"] = parsed["password"]

    ptype = str(prx.get("type") or "direct").strip().lower()
    phost = str(prx.get("host") or "").strip()
    try:
        pport = int(prx.get("port") or 0)
    except (ValueError, TypeError):
        pport = 0
    puser = str(prx.get("username") or "").strip()
    ppass = str(prx.get("password") or "").strip()

    ip_to_check = (target_ip or prx.get("exit_ip") or "").strip()
    country_code = (country_hint or prx.get("country") or "").strip().upper()
    fields_qs = "fields=status,country,countryCode,regionName,city,lat,lon,timezone,isp,query"

    # 1. Live tunnel check through configured SOCKS5 / HTTP proxy via system curl or pure-Python fallback
    if ptype in ("socks5", "http", "https") and phost and pport > 0 and not target_ip:
        curl_scheme = "socks5h" if ptype == "socks5" else ptype
        auth_part = f"{puser}:{ppass}@" if puser else ""
        proxy_url = f"{curl_scheme}://{auth_part}{phost}:{pport}"
        curl_bin = resolve_curl_executable()
        raw_json_str = ""
        try:
            proc = subprocess.run(
                [
                    curl_bin,
                    "-s",
                    "-m",
                    "6",
                    "-x",
                    proxy_url,
                    f"http://ip-api.com/json/?{fields_qs}",
                ],
                capture_output=True,
                text=True,
                timeout=7.5,
                creationflags=get_subprocess_creationflags(),
            )
            if proc.returncode == 0 and proc.stdout.strip():
                raw_json_str = proc.stdout.strip()
        except Exception:
            pass

        if not raw_json_str:
            try:
                raw_json_str = (
                    _tunnel_http_get_pure_python(
                        ptype=ptype,
                        phost=phost,
                        pport=pport,
                        puser=puser,
                        ppass=ppass,
                        target_host="ip-api.com",
                        target_port=80,
                        target_path=f"/json/?{fields_qs}",
                        timeout=5.0,
                    )
                    or ""
                )
            except Exception:
                raw_json_str = ""

        if raw_json_str:
            try:
                data = json.loads(raw_json_str)
                if data.get("status") == "success":
                    cc = str(data.get("countryCode") or country_code or "US").upper()
                    base_locale = resolve_country_locale(cc, data.get("query", ""))
                    tz = str(data.get("timezone") or base_locale["timezone"])
                    return {
                        "ok": True,
                        "source": "proxy_tunnel_geoip",
                        "exit_ip": str(data.get("query") or ip_to_check or "198.51.100.77"),
                        "country_code": cc,
                        "country_name": f"{data.get('country', '')} ({data.get('city', '')})".strip(),
                        "timezone": tz,
                        "languages": base_locale["languages"],
                        "accept_language": base_locale["accept_language"],
                        "ui_language": base_locale["ui_language"],
                        "latitude": float(data.get("lat") or base_locale["latitude"]),
                        "longitude": float(data.get("lon") or base_locale["longitude"]),
                        "isp": str(data.get("isp") or ""),
                    }
            except Exception:
                pass

    # 2. Direct GeoIP lookup if a public IP is provided or if direct connection check is requested
    query_target = ip_to_check if ip_to_check and not ip_to_check.startswith(("127.", "192.168.", "10.", "198.51.100.")) else ""
    url = f"http://ip-api.com/json/{query_target}?{fields_qs}"

    if query_target or (ptype == "direct" and not country_code):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                if data.get("status") == "success":
                    cc = str(data.get("countryCode") or country_code or "US").upper()
                    base_locale = resolve_country_locale(cc, data.get("query", ""))
                    tz = str(data.get("timezone") or base_locale["timezone"])
                    return {
                        "ok": True,
                        "source": "live_geoip",
                        "exit_ip": str(data.get("query") or ip_to_check or "198.51.100.77"),
                        "country_code": cc,
                        "country_name": f"{data.get('country', '')} ({data.get('city', '')})".strip(),
                        "timezone": tz,
                        "languages": base_locale["languages"],
                        "accept_language": base_locale["accept_language"],
                        "ui_language": base_locale["ui_language"],
                        "latitude": float(data.get("lat") or base_locale["latitude"]),
                        "longitude": float(data.get("lon") or base_locale["longitude"]),
                        "isp": str(data.get("isp") or ""),
                    }
        except Exception:
            pass

    base_locale = resolve_country_locale(country_code, ip_to_check)
    return {
        "ok": True,
        "source": "country_table",
        "exit_ip": ip_to_check or "198.51.100.77",
        "country_code": base_locale["country_code"],
        "country_name": base_locale["country_name"],
        "timezone": prx.get("timezone") or base_locale["timezone"],
        "languages": base_locale["languages"],
        "accept_language": base_locale["accept_language"],
        "ui_language": base_locale["ui_language"],
        "latitude": base_locale["latitude"],
        "longitude": base_locale["longitude"],
        "isp": "Local / Preset",
    }


def build_default_user_agent(
    kernel_type: str,
    os_platform: str,
    chromium_version: str = "153.0.8010.27",
    gecko_version: str = "153.0",
    cpu_arch: Optional[str] = None,
) -> Tuple[str, Dict[str, Any]]:
    major_chrome = chromium_version.split(".")[0] if chromium_version else "153"
    major_gecko = gecko_version.split(".")[0] if gecko_version else "153"
    ktype = normalize_kernel_name(kernel_type)
    norm_cpu = (cpu_arch or "").strip().lower()

    if ktype == "yangbrowser":
        if os_platform == "macOS":
            ua = f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:{major_gecko}.0) Gecko/20100101 Firefox/{major_gecko}.0"
            platform_nav = "MacIntel"
            platform_ch = "macOS"
            platform_ver = "14.5.0"
            arch = "x86" if norm_cpu in ("x64", "x86", "amd64") else "arm"
            mobile = "0"
            model = ""
        elif os_platform == "Linux":
            linux_token = "Linux aarch64" if norm_cpu in ("arm64", "aarch64") else ("Linux i686" if norm_cpu == "x86" else "Linux x86_64")
            ua = f"Mozilla/5.0 (X11; Ubuntu; {linux_token}; rv:{major_gecko}.0) Gecko/20100101 Firefox/{major_gecko}.0"
            platform_nav = linux_token
            platform_ch = "Linux"
            platform_ver = "6.8.0"
            arch = "arm" if norm_cpu in ("arm64", "aarch64") else "x86"
            mobile = "0"
            model = ""
        elif os_platform == "Android":
            ua = f"Mozilla/5.0 (Android 14; Mobile; rv:{major_gecko}.0) Gecko/{major_gecko}.0 Firefox/{major_gecko}.0"
            platform_nav = "Linux armv81"
            platform_ch = "Android"
            platform_ver = "14.0.0"
            arch = "arm"
            mobile = "1"
            model = "Pixel 8 Pro"
        elif os_platform == "iPhone":
            ua = f"Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) FxiOS/{major_gecko}.0 Mobile/15E148 Safari/605.1.15"
            platform_nav = "iPhone"
            platform_ch = "iPhone"
            platform_ver = "17.5.0"
            arch = "arm"
            mobile = "1"
            model = "iPhone"
        else:
            win_tok = "WOW64" if norm_cpu == "x86" else "Win64; x64"
            ua = f"Mozilla/5.0 (Windows NT 10.0; {win_tok}; rv:{major_gecko}.0) Gecko/20100101 Firefox/{major_gecko}.0"
            platform_nav = "Win32"
            platform_ch = "Windows"
            platform_ver = "15.0.0"
            arch = "arm" if norm_cpu in ("arm64", "aarch64") else "x86"
            mobile = "0"
            model = ""
    else:
        if os_platform == "macOS":
            ua = f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major_chrome}.0.0.0 Safari/537.36"
            platform_nav = "MacIntel"
            platform_ch = "macOS"
            platform_ver = "14.5.0"
            arch = "x86" if norm_cpu in ("x64", "x86", "amd64") else "arm"
            mobile = "0"
            model = ""
        elif os_platform == "Linux":
            linux_token = "Linux aarch64" if norm_cpu in ("arm64", "aarch64") else ("Linux i686" if norm_cpu == "x86" else "Linux x86_64")
            ua = f"Mozilla/5.0 (X11; {linux_token}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major_chrome}.0.0.0 Safari/537.36"
            platform_nav = linux_token
            platform_ch = "Linux"
            platform_ver = "6.8.0"
            arch = "arm" if norm_cpu in ("arm64", "aarch64") else "x86"
            mobile = "0"
            model = ""
        elif os_platform == "Android":
            ua = f"Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major_chrome}.0.0.0 Mobile Safari/537.36"
            platform_nav = "Linux armv81"
            platform_ch = "Android"
            platform_ver = "14.0.0"
            arch = "arm"
            mobile = "1"
            model = "Pixel 8 Pro"
        elif os_platform == "iPhone":
            ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/153.0.8010.27 Mobile/15E148 Safari/604.1"
            platform_nav = "iPhone"
            platform_ch = "iPhone"
            platform_ver = "17.5.0"
            arch = "arm"
            mobile = "1"
            model = "iPhone"
        else:
            win_tok = "WOW64" if norm_cpu == "x86" else "Win64; x64"
            ua = f"Mozilla/5.0 (Windows NT 10.0; {win_tok}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major_chrome}.0.0.0 Safari/537.36"
            platform_nav = "Win32"
            platform_ch = "Windows"
            platform_ver = "15.0.0"
            arch = "arm" if norm_cpu in ("arm64", "aarch64") else "x86"
            mobile = "0"
            model = ""

    bitness = "32" if norm_cpu == "x86" else "64"
    wow64 = "1" if (os_platform == "Windows" and norm_cpu == "x86") else "0"
    client_hints = {
        "platform": platform_ch,
        "platform_navigator": platform_nav,
        "platform_version": platform_ver,
        "architecture": arch,
        "model": model,
        "mobile": mobile,
        "wow64": wow64,
        "ua_full_version": chromium_version,
        "bitness": bitness,
    }
    return ua, client_hints


def generate_fingerprint_profile(
    profile_id: Optional[str] = None,
    kernel_type: str = "taebrowser",
    os_platform: str = "Windows",
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generates a complete anti-detect fingerprint dictionary including:
      - GPU / Graphics Card / OpenGL / Direct3D11 / Metal / Vulkan settings
      - Proxy-based automatic TimeZone / Language / Geolocation switches
    """
    pid = profile_id or uuid.uuid4().hex[:8]
    kernel_type = normalize_kernel_name(kernel_type)
    rng = random.Random(f"{pid}_{time.time_ns()}")

    ua, client_hints = build_default_user_agent(kernel_type, os_platform)
    presets = WEBGL_PRESETS.get(os_platform, WEBGL_PRESETS["Windows"])
    char_sum = sum(ord(c) for c in pid)
    gpu_preset = presets[char_sum % len(presets)]

    res_list = SCREEN_RESOLUTIONS.get(os_platform, SCREEN_RESOLUTIONS["Windows"])
    screen_res = res_list[char_sum % len(res_list)]

    hw_concurrency = 0 if os_platform == "iPhone" else rng.choice([4, 8, 12, 16])
    device_memory = 0 if os_platform == "iPhone" else rng.choice([4, 8, 16, 32])

    disabled_fonts = rng.sample(WIN32_FONTS[5:], k=min(5, len(WIN32_FONTS) - 5))
    if os_platform in ("Android", "iPhone"):
        disabled_fonts = [f for f in WIN32_FONTS if f not in MOBILE_SAFE_FONTS]

    mac_bytes = [0x00, 0x16, 0x3E, rng.randint(0x00, 0x7F), rng.randint(0x00, 0xFF), rng.randint(0x00, 0xFF)]
    mac_addr = ":".join(f"{b:02X}" for b in mac_bytes)

    fp: Dict[str, Any] = {
        "profile_id": pid,
        "kernel_type": kernel_type,
        "os_platform": os_platform,
        "user_agent": ua,
        "client_hints": client_hints,
        # Canvas 2D
        "canvas_noise": True,
        "canvas_id": f"{pid}_canvas_{rng.randint(1000, 9999)}",
        "dis_canvas_url": [],
        # GPU / Graphics Card / WebGL / OpenGL / ANGLE / WebGPU
        "gpu_mode": "enabled",  # "enabled" | "disabled"
        "graphics_api": gpu_preset.get("api", "Direct3D11"),  # "Direct3D11" | "OpenGL" | "Direct3D9" | "Metal" | "Vulkan" | "OpenGL ES"
        "angle_backend": gpu_preset.get("angle_backend", "d3d11"),  # "d3d11" | "gl" | "d3d9" | "metal" | "vulkan" | "swiftshader" | "default"
        "gpu_preset_id": gpu_preset.get("id", "win_rtx3060_d3d11"),
        "gpu_brand": gpu_preset.get("brand", "NVIDIA"),
        "gpu_model": gpu_preset.get("model", "NVIDIA GeForce RTX 3060"),
        "webgl_image_noise": True,
        "webgl_image_id": f"{pid}_webgl_{rng.randint(1000, 9999)}",
        "webgl_metadata_mode": "custom",  # "custom" | "real"
        "webgl_vendor": gpu_preset["UNMASKED_VENDOR_WEBGL"],
        "webgl_renderer": gpu_preset["UNMASKED_RENDERER_WEBGL"],
        "webgl_version": gpu_preset.get("webgl_version", "WebGL 2.0 (OpenGL ES 3.0 Chromium)"),
        "webgl_shading_language": gpu_preset.get(
            "shading_language_version",
            "WebGL GLSL ES 3.00 (OpenGL ES GLSL ES 3.0 Chromium)",
        ),
        "webgpu_mode": "webgl_based",  # "webgl_based" | "custom" | "real" | "disabled"
        "webgpu_vendor": gpu_preset["GPUAdapterInfo"]["vendor"],
        "webgpu_architecture": gpu_preset["GPUAdapterInfo"]["architecture"],
        # Audio & ClientRects
        "audio_noise": True,
        "audio_id": compute_audio_noise(pid),
        "client_rects_noise": True,
        "client_rects_id": compute_client_rect_fp(pid),
        # Hardware & Screen
        "hardware_concurrency": hw_concurrency,
        "device_memory": device_memory,
        "screen_resolution": screen_res,
        "dpr": 2.0 if os_platform in ("macOS", "Android", "iPhone") else 1.0,
        # Proxy-Based Auto Matching Switches (TimeZone / Language / UI Language / Geolocation)
        "proxy_country": "US",
        "follow_proxy_timezone": True,
        "timezone": "America/New_York",
        "follow_proxy_language": True,
        "languages": ["en-US", "en"],
        "follow_proxy_ui_language": False,
        "ui_language": "en-US",
        "follow_proxy_geolocation": True,
        "geolocation_enabled": True,
        "latitude": round(40.7128 + rng.uniform(-0.02, 0.02), 6),
        "longitude": round(-74.0060 + rng.uniform(-0.02, 0.02), 6),
        "accuracy": rng.choice([25, 50, 100]),
        # WebRTC
        "webrtc_mode": "proxy",  # "proxy" | "forward" | "disable_udp" | "disabled" | "real"
        "webrtc_public_ip": "198.51.100.77",
        "webrtc_local_ip": generate_local_webrtc_ip(pid),
        # Fonts, Device & Stealth
        "disabled_fonts": disabled_fonts,
        "enable_fake_fonts": os_platform != "Windows",
        "do_not_track": False,
        "device_name": f"DESKTOP-{pid.upper()[:7]}",
        "mac_address": mac_addr,
        "port_scan_protection": True,
        "allow_scan_ports": "",
        "cdp_stealth": True,
        "automation_controlled": False,
        "chrome_validation_headers": True,
        "https_only_mode": False,
        "tls_switch": False,
        "tls_cipher_blacklist": "",
        "media_devices": [
            {"kind": "audioinput", "label": "Microphone (Realtek High Definition Audio)"},
            {"kind": "videoinput", "label": "HD Pro Webcam C920"},
            {"kind": "audiooutput", "label": "Speakers (Realtek High Definition Audio)"},
        ],
    }

    if overrides:
        for k, v in overrides.items():
            if v is not None:
                fp[k] = v

    return fp


def format_accept_language(langs: List[str]) -> str:
    if not langs:
        return "en-US,en;q=0.9"
    parts = [langs[0]]
    for idx, lang in enumerate(langs[1:], start=1):
        q = max(0.1, round(1.0 - idx * 0.1, 1))
        parts.append(f"{lang};q={q}")
    return ",".join(parts)


def build_fake_fonts_map(os_platform: str) -> Dict[str, str]:
    if os_platform == "macOS":
        return {font: WIN32_FONTS[idx % len(WIN32_FONTS)] for idx, font in enumerate(DARWIN_FONTS)}
    if os_platform in ("Linux", "Android"):
        return {font: WIN32_FONTS[idx % len(WIN32_FONTS)] for idx, font in enumerate(LINUX_FONTS)}
    return {}


def build_firefox_prefs_js(
    existing_content: str,
    fp: Dict[str, Any],
    resolved_langs: List[str],
    proxy: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Builds `prefs.js` for YangBrowser 153 (`xul.dll`) and cross-OS Gecko browsers,
    including Navigator OS emulation, WebGL/OpenGL vendor & renderer overrides,
    WebGPU toggle, proxy-matched Accept-Language, and native Gecko proxy preferences.
    """
    lines = [
        line
        for line in existing_content.splitlines()
        if not any(
            key in line
            for key in [
                "dom.security.https_only_mode",
                "dom.oscpu.enabled",
                "dom.buildid.enabled",
                "dom.donottrack.enabled",
                "general.vendor.override",
                "general.appversion.override",
                "general.oscpu.override",
                "general.platform.override",
                "general.useragent.override",
                "webgl.override-unmasked-vendor",
                "webgl.override-unmasked-renderer",
                "webgl.disabled",
                "dom.webgpu.enabled",
                "intl.accept_languages",
                "media.peerconnection.enabled",
                "toolkit.startup.max_resumed_crashes",
                "browser.shell.checkDefaultBrowser",
                "browser.startup.page",
                "browser.sessionstore.resume_from_crash",
                "browser.sessionstore.restore_on_demand",
                "privacy.sanitize.sanitizeOnShutdown",
                "network.cookie.lifetimePolicy",
                "marionette.port",
                "network.proxy.type",
                "network.proxy.socks",
                "network.proxy.socks_port",
                "network.proxy.socks_version",
                "network.proxy.socks_remote_dns",
                "network.proxy.http",
                "network.proxy.http_port",
                "network.proxy.ssl",
                "network.proxy.ssl_port",
                "network.proxy.share_proxy_settings",
            ]
        )
    ]

    def add_pref(key: str, val: Any) -> None:
        lines.append(f"user_pref({json.dumps(key)}, {json.dumps(val)});")

    add_pref("browser.startup.page", 3)  # 3 = Restore previous session tabs automatically
    add_pref("browser.sessionstore.resume_from_crash", True)
    add_pref("browser.sessionstore.restore_on_demand", False)
    add_pref("toolkit.startup.max_resumed_crashes", 3)
    add_pref("privacy.sanitize.sanitizeOnShutdown", False)
    add_pref("network.cookie.lifetimePolicy", 0)
    add_pref("signon.rememberSignons", True)
    add_pref("browser.shell.checkDefaultBrowser", False)
    add_pref("extensions.lastAppBuildId", "20260825153431")
    add_pref("extensions.lastAppVersion", "153.0.4")
    add_pref("extensions.lastPlatformVersion", "153.0.4")

    if resolved_langs:
        add_pref("intl.accept_languages", ",".join(resolved_langs))

    if fp.get("https_only_mode"):
        add_pref("dom.security.https_only_mode", True)

    ua = fp.get("user_agent", "")
    if ua:
        add_pref("general.useragent.override", ua)

    os_plat = fp.get("os_platform", "Windows")
    if os_plat == "Windows":
        add_pref("general.appversion.override", "5.0 (Windows)")
        add_pref("general.oscpu.override", "Windows NT 10.0; Win64; x64")
        add_pref("general.platform.override", "Win32")
    elif os_plat == "macOS":
        add_pref("general.appversion.override", "5.0 (Macintosh)")
        add_pref("general.oscpu.override", "Intel Mac OS X 10.15")
        add_pref("general.platform.override", "MacIntel")
    elif os_plat == "Android":
        add_pref("general.platform.override", "Linux armv81")
        add_pref("general.oscpu.override", "Linux armv81")
        add_pref("general.appversion.override", "5.0 (Android 14)")
    elif os_plat == "iPhone":
        add_pref("dom.oscpu.enabled", False)
        add_pref("dom.buildid.enabled", False)
        add_pref("dom.donottrack.enabled", False)
        add_pref("general.platform.override", "iPhone")
        add_pref("general.vendor.override", "Apple Computer, Inc.")
        add_pref("general.appversion.override", ua.replace("Mozilla/", ""))
    elif os_plat == "Linux":
        app_ver = "5.0 (X11; Ubuntu)" if "Ubuntu" in ua else "5.0 (X11)"
        add_pref("general.appversion.override", app_ver)
        add_pref("general.oscpu.override", "Linux x86_64")
        add_pref("general.platform.override", "Linux x86_64")

    if fp.get("gpu_mode") == "disabled":
        add_pref("webgl.disabled", True)
    elif fp.get("webgl_metadata_mode", "custom") != "real":
        if fp.get("webgl_vendor"):
            add_pref("webgl.override-unmasked-vendor", fp["webgl_vendor"])
        if fp.get("webgl_renderer"):
            add_pref("webgl.override-unmasked-renderer", fp["webgl_renderer"])

    if fp.get("webgpu_mode") == "disabled":
        add_pref("dom.webgpu.enabled", False)

    if fp.get("webrtc_mode") == "disabled":
        add_pref("media.peerconnection.enabled", False)

    if proxy:
        ptype = str(proxy.get("type") or "direct").strip().lower()
        phost = str(proxy.get("host") or "").strip()
        try:
            pport = int(proxy.get("port") or 0)
        except (ValueError, TypeError):
            pport = 0
        if ptype == "socks5" and phost and pport > 0:
            add_pref("network.proxy.type", 1)
            add_pref("network.proxy.socks", phost)
            add_pref("network.proxy.socks_port", pport)
            add_pref("network.proxy.socks_version", 5)
            add_pref("network.proxy.socks_remote_dns", True)
        elif ptype in ("http", "https") and phost and pport > 0:
            add_pref("network.proxy.type", 1)
            add_pref("network.proxy.http", phost)
            add_pref("network.proxy.http_port", pport)
            add_pref("network.proxy.ssl", phost)
            add_pref("network.proxy.ssl_port", pport)
            add_pref("network.proxy.share_proxy_settings", True)

    return "\n".join(lines) + "\n"


def compile_profile_configs(
    profile: Dict[str, Any],
    profile_dir: Path,
    extension_paths: Optional[List[str]] = None,
    write_files: bool = True,
) -> Dict[str, Any]:
    """
    Compiles all sidecar files (`_static`, `_webrtc`, `_webgl`, `_cookies`, `prefs.js`)
    and `--extended-parameters` for `TaeBrowser` and `YangBrowser`.
    Automatically applies proxy-linked TimeZone, Languages, UI Language, and Geolocation
    when `follow_proxy_timezone`, `follow_proxy_language`, `follow_proxy_ui_language`,
    or `follow_proxy_geolocation` is enabled!
    """
    pid = str(profile["id"])
    kernel_type = normalize_kernel_name(profile.get("kernel_type", "taebrowser"))
    fp: Dict[str, Any] = dict(profile.get("fingerprint") or generate_fingerprint_profile(pid, kernel_type))
    proxy: Dict[str, Any] = dict(profile.get("proxy") or {"type": "direct"})
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
    cookies: List[Dict[str, Any]] = profile.get("cookies") or []

    os_platform = fp.get("os_platform", "Windows")
    ch = fp.get("client_hints") or build_default_user_agent(kernel_type, os_platform)[1]
    platform_nav = ch.get("platform_navigator") or (
        "MacIntel"
        if os_platform == "macOS"
        else "Linux x86_64"
        if os_platform == "Linux"
        else "Linux armv81"
        if os_platform == "Android"
        else "iPhone"
        if os_platform == "iPhone"
        else "Win32"
    )

    if write_files:
        profile_dir.mkdir(parents=True, exist_ok=True)

    # 0. Resolve Proxy Country / IP -> TimeZone, Languages, UI Language, Geolocation
    proxy_country = str(proxy.get("country") or fp.get("proxy_country") or "").upper()
    public_ip = str(proxy.get("exit_ip") or fp.get("webrtc_public_ip") or "198.51.100.77")
    proxy_locale = resolve_country_locale(proxy_country, public_ip)

    # TimeZone resolution (`follow_proxy_timezone` / `tzAuto`)
    if fp.get("follow_proxy_timezone", False):
        effective_tz = str(proxy.get("timezone") or proxy_locale["timezone"] or fp.get("timezone") or "America/New_York")
    else:
        effective_tz = str(fp.get("timezone") or "America/New_York")
    effective_tz = effective_tz.replace(" ", "_")

    # Browser Languages (`Accept-Language` & `navigator.languages`) resolution (`follow_proxy_language`)
    if fp.get("follow_proxy_language", False):
        effective_langs = list(proxy_locale["languages"])
    else:
        effective_langs = list(fp.get("languages") or ["en-US", "en"])

    # UI Language (`--lang`) resolution (`follow_proxy_ui_language`)
    if fp.get("follow_proxy_ui_language", False):
        effective_ui_lang = str(
            proxy_locale.get("ui_language") or (effective_langs[0] if effective_langs else "en-US")
        )
    else:
        effective_ui_lang = str(fp.get("ui_language") or (effective_langs[0] if effective_langs else "en-US"))

    # Geolocation resolution (`follow_proxy_geolocation`)
    char_offset = ((sum(ord(c) for c in pid) % 40) - 20) * 0.0005
    if fp.get("follow_proxy_geolocation", False):
        base_lat = float(proxy["latitude"]) if proxy.get("latitude") is not None else float(proxy_locale["latitude"])
        base_lon = float(proxy["longitude"]) if proxy.get("longitude") is not None else float(proxy_locale["longitude"])
        effective_lat = round(base_lat + char_offset, 6)
        effective_lon = round(base_lon + char_offset, 6)
    else:
        effective_lat = float(fp.get("latitude") if fp.get("latitude") is not None else 40.7128)
        effective_lon = float(fp.get("longitude") if fp.get("longitude") is not None else -74.0060)
    effective_acc = int(fp.get("accuracy") or 50)

    # Sidecar file paths using exact MD5 convention
    static_md5_name = md5_hex(f"{pid}_static")
    dynamic_md5_name = md5_hex(f"{pid}_webrtc")
    webgl_md5_name = f"{md5_hex(f'{pid}_webgl')}_{os_platform}"
    cookies_md5_name = md5_hex(f"{pid}_cookies")

    static_path = profile_dir / static_md5_name
    dynamic_path = profile_dir / dynamic_md5_name
    webgl_path = profile_dir / webgl_md5_name
    cookies_path = profile_dir / cookies_md5_name

    # 1. Construct sunBrowserParams, staticConfig, dynamicConfig
    sun_params: Dict[str, Any] = {
        "UserId": str(profile.get("serial_number", 1)),
        "StartTime": int(time.time()),
        "Platform": platform_nav,
        "DisableContainer": True,
        "DisableBackgroundMode": True,
        "LoadExtensionErrorBox": False,
        "ForceProcessExit": True,
    }
    static_config: Dict[str, Any] = {
        "command_line": {
            "do-not-de-elevate": "",
        },
        "MaxTouchPoints": 5 if os_platform in ("Android", "iPhone") else 0,
    }
    dynamic_config: Dict[str, Any] = {}

    # Canvas 2D & WebGL Image Noise
    if fp.get("canvas_noise", True):
        canvas_mark = str(fp.get("canvas_id") or pid)
        sun_params["CanvasMark"] = canvas_mark
        static_config["CanvasMarkEx"] = canvas_mark
        if fp.get("dis_canvas_url"):
            static_config["DisCanvasUrl"] = fp["dis_canvas_url"]

    if fp.get("webgl_image_noise", True):
        webgl_mark = str(fp.get("webgl_image_id") or pid)
        sun_params["WebGLMark"] = webgl_mark
        static_config["WebGLMarkEx"] = webgl_mark

    # GPU / OpenGL / Direct3D / Metal / WebGL & WebGPU (`WebGLFP`)
    webgl_fp_payload: Dict[str, Any] = {
        "UNMASKED_VENDOR_WEBGL": fp.get("webgl_vendor", "Google Inc. (NVIDIA)"),
        "UNMASKED_RENDERER_WEBGL": fp.get(
            "webgl_renderer",
            "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        ),
        "SUPPORTED_EXTENSIONS": [],
    }
    if fp.get("webgl_version"):
        webgl_fp_payload["VERSION"] = fp["webgl_version"]
    if fp.get("webgl_shading_language"):
        webgl_fp_payload["SHADING_LANGUAGE_VERSION"] = fp["webgl_shading_language"]

    webgpu_mode = fp.get("webgpu_mode", "webgl_based")
    if webgpu_mode in ("webgl_based", "custom") and fp.get("webgpu_vendor"):
        webgl_fp_payload["GPUAdapterInfo"] = {
            "vendor": fp.get("webgpu_vendor", "nvidia"),
            "architecture": fp.get("webgpu_architecture", "ampere"),
        }
    if os_platform == "iPhone":
        webgl_fp_payload["MAX_VIEWPORT_DIMS"] = [16384, 16384]

    if fp.get("webgl_metadata_mode", "custom") != "real" and fp.get("gpu_mode", "enabled") != "disabled":
        sun_params["WebGLFP"] = str(webgl_path.resolve())
        if write_files:
            webgl_path.write_text(json.dumps(webgl_fp_payload, ensure_ascii=False), encoding="utf-8")

    # AudioFp & ClientRectFp
    if fp.get("audio_noise", True):
        sun_params["AudioFp"] = compute_audio_noise(pid, fp.get("audio_id"))
    if fp.get("client_rects_noise", True):
        sun_params["ClientRectFp"] = compute_client_rect_fp(pid, fp.get("client_rects_id"))

    # HardwareConcurrency, DeviceMemory, DoNotTrack
    if fp.get("do_not_track"):
        sun_params["EnableDoNotTrack"] = True
    hw_conc = fp.get("hardware_concurrency", 8)
    dev_mem = fp.get("device_memory", 8)
    sun_params["HardwareConcurrency"] = 0 if os_platform == "iPhone" else int(hw_conc)
    sun_params["DeviceMemory"] = 0 if os_platform == "iPhone" else int(dev_mem)

    # ScreenSize & Mobile Emulation (`NewMobileMode`)
    screen_res = str(fp.get("screen_resolution", "1920_1080")).replace("_", ",")
    if os_platform in ("Android", "iPhone"):
        parts = [int(x) for x in screen_res.split(",") if x.strip().isdigit()]
        w, h = (parts[0], parts[1]) if len(parts) == 2 else (393, 852)
        static_config["MaxTouchPoints"] = 5
        if kernel_type == "taebrowser":
            static_config["NewMobileMode"] = True
            sun_params["MobileModeFixedResolution"] = f"{w},{h + 170}"
        if os_platform == "iPhone":
            sun_params["Vendor"] = "Apple Computer, Inc."
            static_config["command_line"]["disable-blink-features"] = (
                "BatteryStatus,WebBluetooth,NetworkInformation"
            )
    else:
        sun_params["ScreenSize"] = screen_res

    # Languages & Accept-Language (Proxy-linked or Manual)
    sun_params["Langs"] = ",".join(effective_langs)
    sun_params["AcceptLang"] = format_accept_language(effective_langs)

    # TimeZone & Geolocation (Proxy-linked or Manual, written to both static and live dynamicConfig!)
    sun_params["TimeZone"] = effective_tz
    dynamic_config["TimeZone"] = effective_tz

    if fp.get("geolocation_enabled", True):
        geo_str = f"{effective_lat},{effective_lon},{effective_acc}"
        sun_params["Geoposition"] = geo_str
        sun_params["GeolocationSetting"] = "allow"
        dynamic_config["Geoposition"] = geo_str
    else:
        sun_params["GeolocationSetting"] = "block"

    # Fonts (`DisabledFonts` & `Fakefonts`)
    if fp.get("disabled_fonts"):
        static_config["DisabledFonts"] = list(fp["disabled_fonts"])
        sun_params["DisabledFonts"] = list(fp["disabled_fonts"])
    if fp.get("enable_fake_fonts") and os_platform != "Windows":
        fake_map = build_fake_fonts_map(os_platform)
        if fake_map:
            static_config["Fakefonts"] = fake_map

    # Client Hints (`UserAgentMetadata`), DeviceName, MacAddress, MediaDevices
    static_config["UserAgentMetadata"] = {
        "platform": ch.get("platform", "Windows"),
        "platformVersion": ch.get("platform_version", "15.0.0"),
        "architecture": ch.get("architecture", "x86"),
        "model": ch.get("model", ""),
        "mobile": ch.get("mobile") == "1" or os_platform in ("Android", "iPhone"),
        "wow64": ch.get("wow64") == "1",
        "uaFullVersion": ch.get("ua_full_version", "153.0.8010.27"),
        "bitness": ch.get("bitness", "64"),
    }
    dev_name = fp.get("device_name") or f"DESKTOP-{pid.upper()[:7]}"
    static_config["DeviceName"] = dev_name
    static_config["ProductType"] = dev_name.replace("TOP", "")
    if fp.get("mac_address"):
        static_config["MacAddress"] = fp["mac_address"]

    if os_platform in ("macOS", "Android", "iPhone"):
        static_config["MediaDevices"] = [
            {"kind": "audioinput", "label": ""},
            {"kind": "videoinput", "label": ""},
            {"kind": "audiooutput", "label": ""},
        ]
    elif fp.get("media_devices"):
        static_config["MediaDevices"] = fp["media_devices"]

    # Port scan protection & CDP Stealth
    if fp.get("port_scan_protection", True):
        ports = str(fp.get("allow_scan_ports") or "0").strip() or "0"
        sun_params["AllowScanPorts"] = ports
        static_config["WebRTCAllowScanPorts"] = ports
    static_config["AutomationControlled"] = bool(fp.get("automation_controlled", False))

    # Proxy & WebRTC (including SOCKS5 UDP Proxy support!)
    proxy_type = (proxy.get("type") or "direct").lower()
    proxy_host = proxy.get("host") or ""
    proxy_port = proxy.get("port") or ""
    proxy_user = proxy.get("username") or ""
    proxy_pass = proxy.get("password") or ""

    if proxy_type != "direct" and proxy_host and proxy_port:
        if proxy_user and proxy_pass:
            sun_params["ProxyUser"] = proxy_user
            sun_params["ProxyPassword"] = proxy_pass

    webrtc_mode = fp.get("webrtc_mode", "proxy")
    local_ip = fp.get("webrtc_local_ip") or generate_local_webrtc_ip(pid)

    if webrtc_mode == "disabled":
        sun_params["DisableWebRTC"] = True
        dynamic_config["DisableWebRTC"] = True
    elif webrtc_mode == "disable_udp":
        if kernel_type == "taebrowser" and proxy_type == "socks5" and proxy_host and proxy_port:
            static_config["WebRTCSocks5UdpProxy"] = {
                "host": str(proxy_host),
                "port": str(proxy_port),
                "account": str(proxy_user),
                "password": str(proxy_pass),
            }
        else:
            static_config["command_line"]["webrtc-ip-handling-policy"] = "disable_non_proxied_udp"
    elif webrtc_mode in ("proxy", "forward"):
        if public_ip:
            sun_params["WebRTCAddress"] = public_ip
            dynamic_config["WebRTCAddress"] = public_ip
        else:
            dynamic_config["DisableWebRTC"] = True
        sun_params["WebRTCLocalAddress"] = local_ip
        dynamic_config["WebRTCLocalAddress"] = local_ip

    # Startup Cookies sidecar (`md5(fbccId + "_cookies")`)
    if cookies:
        sun_params["CookiesFile"] = str(cookies_path.resolve())
        if write_files:
            cookies_path.write_text(json.dumps(cookies, ensure_ascii=False), encoding="utf-8")

    # Extension settings
    if extension_paths:
        static_config["ExtensionSetting"] = [
            {"path": str(Path(p).resolve()), "pinned": 1} for p in extension_paths
        ]

    # FinalizeTask: Copy top-level sunBrowserParams into staticConfig
    excluded_from_static = {
        "CustomIcon",
        "WebGLFP",
        "StaticConfig",
        "CookiesFile",
        "DynamicConfig",
        "Geoposition",
        "TimeZone",
    }
    for k, v in sun_params.items():
        if k not in excluded_from_static:
            static_config[k] = v

    # Encode dynamicConfig & staticConfig using custom-alphabet Base64
    dynamic_json = json.dumps(dynamic_config, ensure_ascii=False)
    dynamic_b64 = adspower_encode_base64(dynamic_json)
    if write_files:
        dynamic_path.write_text(dynamic_b64, encoding="utf-8")
    sun_params["DynamicConfig"] = str(dynamic_path.resolve())

    static_json = json.dumps(static_config, ensure_ascii=False)
    static_b64 = adspower_encode_base64(static_json)
    if write_files:
        static_path.write_text(static_b64, encoding="utf-8")
    sun_params["StaticConfig"] = str(static_path.resolve())

    # Encode `--extended-parameters=<CustomBase64(JSON)>`
    sun_params_json = json.dumps(sun_params, ensure_ascii=False)
    extended_params_b64 = adspower_encode_base64(sun_params_json)

    # Browser-specific preference files (`prefs.js` for YangBrowser, `Default/Preferences` for TaeBrowser)
    firefox_prefs_content = ""
    if kernel_type == "yangbrowser":
        prefs_file = profile_dir / "prefs.js"
        existing_prefs = ""
        if prefs_file.is_file():
            try:
                existing_prefs = prefs_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                pass
        firefox_prefs_content = build_firefox_prefs_js(existing_prefs, fp, effective_langs, proxy=proxy)
        if write_files:
            prefs_file.write_text(firefox_prefs_content, encoding="utf-8")
            (profile_dir / "user.js").write_text(firefox_prefs_content, encoding="utf-8")
    else:
        if write_files:
            default_dir = profile_dir / "Default"
            default_dir.mkdir(parents=True, exist_ok=True)
            prefs_file = default_dir / "Preferences"
            chrome_prefs: Dict[str, Any] = {}
            if prefs_file.is_file():
                try:
                    chrome_prefs = json.loads(prefs_file.read_text(encoding="utf-8", errors="ignore"))
                except Exception:
                    chrome_prefs = {}
            chrome_prefs.setdefault("profile", {})["exit_type"] = "Normal"
            chrome_prefs["profile"]["exited_cleanly"] = True
            chrome_prefs["profile"].setdefault("password_manager_enabled", True)
            chrome_prefs.setdefault("credentials_enable_service", True)
            chrome_prefs.setdefault("session", {})["restore_on_startup"] = 1
            chrome_prefs.setdefault("intl", {})["accept_languages"] = ",".join(effective_langs)
            prefs_file.write_text(json.dumps(chrome_prefs, ensure_ascii=False), encoding="utf-8")

    validation_headers = compute_chrome_validation_headers(fp.get("user_agent", ""))

    return {
        "profile_id": pid,
        "kernel_type": kernel_type,
        "profile_dir": str(profile_dir.resolve()),
        "resolved_locale": {
            "proxy_country": proxy_locale["country_code"],
            "timezone": effective_tz,
            "languages": effective_langs,
            "accept_language": format_accept_language(effective_langs),
            "ui_language": effective_ui_lang,
            "latitude": effective_lat,
            "longitude": effective_lon,
            "follow_proxy_timezone": bool(fp.get("follow_proxy_timezone", False)),
            "follow_proxy_language": bool(fp.get("follow_proxy_language", False)),
            "follow_proxy_ui_language": bool(fp.get("follow_proxy_ui_language", False)),
            "follow_proxy_geolocation": bool(fp.get("follow_proxy_geolocation", False)),
        },
        "sidecar_files": {
            "static_config": {
                "filename": static_md5_name,
                "path": str(static_path.resolve()),
                "encoding": "Base64(JSON)",
            },
            "dynamic_config": {
                "filename": dynamic_md5_name,
                "path": str(dynamic_path.resolve()),
                "encoding": "Base64(JSON)",
            },
            "webgl_fp": {
                "filename": webgl_md5_name,
                "path": str(webgl_path.resolve()),
                "encoding": "Plain JSON",
            },
            "cookies": {
                "filename": cookies_md5_name,
                "path": str(cookies_path.resolve()),
                "encoding": "Plain JSON",
            },
        },
        "sunBrowserParams": sun_params,
        "staticConfig": static_config,
        "dynamicConfig": dynamic_config,
        "webglConfig": webgl_fp_payload,
        "firefoxPrefsJs": firefox_prefs_content,
        "chromeValidationHeaders": validation_headers,
        "extended_parameters_b64": extended_params_b64,
        "extended_parameters_flag": f"--extended-parameters={extended_params_b64}",
    }
