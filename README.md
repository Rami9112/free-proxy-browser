<div align="center">

<img src="assets/hero-banner.svg" alt="Free Proxy Browser — Open-Source Anti-Detect & Multi-Profile Proxy Browser" width="100%" />

<br />

# 🛡️ Free Proxy Browser

**Open-Source Anti-Detect & Multi-Profile Proxy Browser Desktop Suite for Windows (`x64` & `ARM64`)**  
*Dual C++ Browser Kernels (`TaeBrowser 153` Chromium & `YangBrowser 153` Gecko) · Auto Proxy Geo-Sync · GPU/OpenGL Spoofing · Local Automation API*

[![Platform](https://img.shields.io/badge/Platform-Windows%20x64%20%7C%20ARM64-0ea5e9?style=for-the-badge&logo=windows&logoColor=white)](https://github.com/Rami9112/free-proxy-browser)
[![Chromium Kernel](https://img.shields.io/badge/TaeBrowser-Chromium%20153.0.8010.27-38bdf8?style=for-the-badge&logo=googlechrome&logoColor=white)](https://github.com/Rami9112/free-proxy-browser)
[![Gecko Kernel](https://img.shields.io/badge/YangBrowser-Gecko%20153.0.4-a855f7?style=for-the-badge&logo=firefoxbrowser&logoColor=white)](https://github.com/Rami9112/free-proxy-browser)
[![Local API](https://img.shields.io/badge/Local%20API-127.0.0.1%3A50325-10b981?style=for-the-badge)](https://github.com/Rami9112/free-proxy-browser)
[![License](https://img.shields.io/badge/License-MIT-f59e0b?style=for-the-badge)](LICENSE)

</div>

---

## ✨ Overview

**Free Proxy Browser** (`FreeProxyBrowser.exe`) is a 100% standalone, open-source **anti-detect & multi-profile proxy browser desktop application** that runs locally without cloud accounts, telemetry, or subscriptions.

- 🖥️ **Native Windows `x64` & `ARM64` Compatibility**: Automatically detects your system architecture (`win-x64`, `win-arm64`, or `win-x86`) and preloads the matching native `WebView2Loader.dll` and Python runtime.
- 🌐 **One-Line Proxy Parsing & Automatic Geo-Sync**: Paste a single proxy string (`socks5://user:pass@host:port` or `host:port:user:pass`) to automatically populate proxy credentials and tunnel through the proxy to auto-match **Exit Public IP, Country, IANA TimeZone, Browser Languages (`Accept-Language` / `--lang`), and GPS Geolocation**.
- 🎮 **Hardware GPU & OpenGL / Direct3D11 / Metal / WebGPU Spoofing**: Includes 20+ real GPU presets (NVIDIA RTX 4090/4070/3080, AMD Radeon RX 7900 XTX, Intel Iris Xe, Apple M1/M2/M3 Metal, Mobile Adreno/Mali) and per-profile ANGLE backend flags (`--use-angle=gl`, `d3d11`, `d3d9`, `swiftshader`).
- 🟦🟪 **Dual Native C++ Browser Kernels (`TaeBrowser 153` & `YangBrowser 153`)**: Built-in C++ binary-level hooks inside `chrome.dll` and `xul.dll` spoof Canvas 2D, WebGL, AudioContext, DOMRect (`ClientRects`), WebRTC ICE candidates, Navigator properties, and OS font tables without fragile JavaScript monkey-patching.

---

## 🏗️ System Architecture

```mermaid
flowchart LR
    subgraph Desktop["🖥️ FreeProxyBrowser.exe (WinForms + WebView2 x64/ARM64)"]
        UI["Profile Studio & Proxy Manager"]
        Verify["Live C++ Fingerprint Probe (/verify)"]
    end

    subgraph Server["⚡ Local Control & API Server (127.0.0.1:50325)"]
        DB[("SQLite DB\n(data/freeanti.db)")]
        Geo["Proxy Tunnel GeoIP Resolver\n(TimeZone · Lang · GPS Auto-Sync)"]
        Compiler["MD5 Sidecar Compiler\n(_static · _webrtc · _webgl · prefs.js)"]
    end

    subgraph Kernels["🛡️ Dual Native C++ Anti-Detect Kernels"]
        Tae["🟦 TaeBrowser 153 (Chromium 153)\n• SunBrowserPolicys C++ Hooks\n• ANGLE D3D11 / OpenGL 4.6\n• SHA-1 x-browser-validation"]
        Yang["🟪 YangBrowser 153 (Gecko 153)\n• xul.dll 37 custom.* C++ Hooks\n• Navigator & Fakefonts Emulation\n• Live _webrtc Timer Polling"]
    end

    UI <-->|REST / Local API v1 & v2| Server
    Server --> DB
    Server --> Geo
    Geo --> Compiler
    Compiler -->|--extended-parameters| Tae
    Compiler -->|--extended-parameters + prefs.js| Yang
    Tae -.->|Probe| Verify
    Yang -.->|Probe| Verify
```

---

## 🔥 Key Features

| Category | Capabilities |
| :--- | :--- |
| **🌐 Proxy & Auto Locale Sync** | • **SOCKS5 / HTTP / HTTPS / Direct** protocols with automatic `ProxyUser` / `ProxyPassword` authentication<br>• **SOCKS5 UDP Proxy (`WebRTCSocks5UdpProxy`)** and public/private WebRTC ICE IP replacement<br>• Automatic **TimeZone, `navigator.languages`, UI Language (`--lang`), and Geolocation GPS** matching based on the proxy exit IP |
| **🎮 GPU & OpenGL / WebGL** | • Choose between **Direct3D11 (`d3d11`)**, **OpenGL 4.6 (`gl`)**, **Direct3D9Ex (`d3d9`)**, **Apple Metal (`metal`)**, **OpenGL ES 3.2 (`gles`)**, and **SwiftShader**<br>• Custom `UNMASKED_VENDOR_WEBGL` (37445), `UNMASKED_RENDERER_WEBGL` (37446), `VERSION` (7938), and `SHADING_LANGUAGE_VERSION` (35724) injection<br>• WebGL `ReadPixels` noise (`WebGLMarkEx`) and `navigator.gpu` WebGPU adapter vendor/architecture spoofing |
| **🧬 C++ Engine Fingerprint Isolation** | • Deterministic per-profile seeds for **Canvas 2D (`CanvasMarkEx`)**, **AudioContext (`AudioFp`)**, and **DOMRect (`ClientRectFp`)**<br>• **Cross-OS Emulation**: Windows 11, macOS 14 Sonoma (Apple Silicon), Linux Ubuntu, Android 14, and iPhone 15 Pro (`NewMobileMode`, `MaxTouchPoints=5`)<br>• **Google Chrome `x-browser-validation`**: OS-specific SHA-1 validation header generator plus `Alt+P` human-like paste assistant |
| **⚡ Zero-Downtime Hot-Reload & API** | • Live-updates the `<profile_dir>/<md5(id + "_webrtc")>` sidecar while the browser is running to **hot-reload WebRTC IP, TimeZone, and GPS coordinates without restarting**<br>• Local REST API on `127.0.0.1:50325` (`v1` & `v2` compatible) for instant **Selenium, Puppeteer, and Playwright** attachment |

---

## 🚀 Quick Start

### 1. Clone the Repository
```powershell
git clone https://github.com/Rami9112/free-proxy-browser.git
cd free-proxy-browser
```

### 2. Launch the Desktop Application (`Windows x64` & `ARM64`)
Requires only **Python 3.9+** and the standard **Microsoft Edge WebView2 Runtime** (pre-installed on Windows 10/11). No third-party Python packages are required.

```powershell
# Option 1: Launch the native Windows desktop executable (Recommended)
.\FreeProxyBrowser.exe

# Option 2: Launch via batch script
.\start_free_proxy_browser.bat

# Option 3: Launch directly via Python
python free_proxy_browser.py
```
> 💡 **First-Run Note**: To comply with GitHub's 100 MB file size limit, large kernel binaries (`chrome.dll.zpart*`, `xul.dll.zpart*`) are stored as compressed chunks and are automatically reassembled on first launch (~2–3 seconds).

---

## 🛠️ CLI & Automation Usage

### Command-Line Interface (CLI)
```powershell
# Check discovered kernels (TaeBrowser 153 & YangBrowser 153) and profile summary
python free_proxy_browser.py status

# List all profiles
python free_proxy_browser.py list

# Create a new proxy browser profile
python free_proxy_browser.py create --name "US Store #1" --kernel taebrowser --os Windows --proxy-type socks5 --proxy-host proxy.example.com --proxy-port 1080

# Start / stop a profile
python free_proxy_browser.py start fa1001win
python free_proxy_browser.py stop fa1001win

# Hot-reload WebRTC Public IP & TimeZone while the browser is running
python free_proxy_browser.py dynamic-update fa1001win --ip 198.51.100.77 --tz America/New_York

# Run the automated end-to-end verification suite
python free_proxy_browser.py test --launch-browsers
```

### Python Selenium Example
```python
import urllib.request
import json
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

# 1. Start a browser profile via the Local API
with urllib.request.urlopen("http://127.0.0.1:50325/api/v1/browser/start?user_id=fa1001win") as res:
    data = json.loads(res.read().decode("utf-8"))["data"]

# 2. Connect Selenium directly to the returned ChromeDriver and debugger port
opts = Options()
opts.add_experimental_option("debuggerAddress", data["ws"]["selenium"])
driver = webdriver.Chrome(service=Service(data["webdriver"]), options=opts)
print("Connected Browser Title:", driver.title)
```

---

## 📁 Project Structure

```text
free-proxy-browser/
├── FreeProxyBrowser.exe           # Native Windows desktop executable (x64 & ARM64 AnyCPU, custom icon)
├── free_proxy_browser.py          # Main CLI & desktop launcher entrypoint
├── start_free_proxy_browser.bat   # One-click launcher batch script
├── assets/
│   ├── hero-banner.svg            # Animated SVG motion-graphic hero banner
│   ├── icon.ico                   # Multi-resolution (16px–256px) executable & window icon
│   ├── icon.png                   # High-resolution (512x512) application icon
│   └── icon.svg                   # Vector application icon
├── core/
│   ├── FreeAntiDesktopLauncher.cs # C# WinForms + WebView2 desktop host source (x64/ARM64 compatible)
│   ├── database.py                # SQLite profile, group, and proxy database engine
│   ├── fingerprint.py             # GPU/OpenGL catalog, proxy GeoIP resolver & MD5 sidecar compiler
│   ├── kernel_rebrander.py        # TaeBrowser 153 & YangBrowser 153 kernel builder and chunk unpacker
│   ├── kernels.py                 # Kernel & extension discovery module
│   ├── launcher.py                # Browser process spawner, handshake & live hot-reload manager
│   ├── extension_builder.py       # Google Chrome x-browser-validation SHA-1 header extension builder
│   └── server.py                  # Embedded HTTP control server & Local API (v1/v2) compatibility layer
├── ui/
│   ├── index.html                 # Desktop Profile Studio & Proxy Manager UI (English default)
│   └── verify.html                # Live C++ fingerprint hook verification suite (/verify)
├── runtimes/                      # Architecture-specific WebView2Loader.dll (win-x64, win-arm64, win-x86)
└── kernels/                       # Standalone rebranded TaeBrowser 153 & YangBrowser 153 kernel binaries
```

---

## 📄 License

Distributed under the open-source **MIT License**. See [LICENSE](LICENSE) for details.
