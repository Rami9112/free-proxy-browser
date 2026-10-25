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

## ✨ 소개 (Overview)

**Free Proxy Browser**는 클라우드 로그인이나 유료 구독 없이 로컬 환경에서 100% 독립적으로 동작하는 **오픈소스 프록시 & 안티디텍트 멀티 프로파일 브라우저 데스크톱 프로그램(`FreeProxyBrowser.exe`)**입니다.

- 🖥️ **Windows `x64` 및 `ARM64` 완벽 지원**: 실행 환경의 아키텍처(`win-x64` / `win-arm64` / `win-x86`)를 자동 감지하여 네이티브 `WebView2Loader.dll` 및 Python 런타임을 연결합니다.
- 🌐 **원클릭 프록시 파싱 & 국가별 자동 동기화**: `socks5://user:pass@host:port` 또는 `host:port:user:pass` 한 줄 붙여넣기만으로 프록시 인증 정보를 자동 분리하고, 실제 프록시 터널링을 통해 **출구 공인 IP · 국가 · 타임존(`TimeZone`) · 브라우저 언어(`Accept-Language` / `--lang`) · GPS 위도/경도**를 자동으로 매칭합니다.
- 🎮 **그래픽카드(GPU) & OpenGL / Direct3D11 / Metal / WebGPU 하드웨어 위조**: NVIDIA RTX 4090/4070/3080, AMD Radeon RX 7900 XTX, Intel Iris Xe, Apple M1/M2/M3 Metal, 모바일 Adreno/Mali 등 20종 이상의 실제 GPU 프리셋과 `--use-angle=gl` / `d3d11` / `d3d9` 렌더링 백엔드를 프로파일별로 격리합니다.
- 🟦🟪 **듀얼 네이티브 C++ 커널 내장 (`TaeBrowser 153` & `YangBrowser 153`)**: JS 인젝션 방식이 아닌 C++ 바이너리 레벨(`chrome.dll` & `xul.dll`)에서 Canvas, WebGL, AudioContext, ClientRects, WebRTC, Navigator, 폰트 지문을 변조합니다.

---

## 🏗️ 시스템 아키텍처 (Architecture)

```mermaid
flowchart LR
    subgraph Desktop["🖥️ FreeProxyBrowser.exe (WinForms + WebView2 x64/ARM64)"]
        UI["프로파일 스튜디오 & 프록시 매니저"]
        Verify["실시간 C++ 지문 검증기 (/verify)"]
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

## 🔥 핵심 기능 (Key Features)

| 카테고리 | 지원 기능 상세 |
| :--- | :--- |
| **🌐 프록시 & 자동 로케일 매칭** | • **SOCKS5 / HTTP / HTTPS / Direct** 프로토콜 및 아이디·비밀번호(`ProxyUser` / `ProxyPassword`) 자동 인증<br>• **SOCKS5 UDP 프록시 (`WebRTCSocks5UdpProxy`)** 및 WebRTC 공인/사설 IP 완벽 치환<br>• 프록시 출구 IP 기반 **TimeZone · `navigator.languages` · UI 언어(`--lang`) · Geolocation GPS** 자동 따라가기 |
| **🎮 GPU & OpenGL / WebGL** | • **Direct3D11 (`d3d11`)**, **OpenGL 4.6 (`gl`)**, **Direct3D9Ex (`d3d9`)**, **Apple Metal (`metal`)**, **OpenGL ES 3.2 (`gles`)**, **SwiftShader** 선택<br>• `UNMASKED_VENDOR_WEBGL` (37445), `UNMASKED_RENDERER_WEBGL` (37446), `VERSION` (7938), `SHADING_LANGUAGE_VERSION` (35724) 커스텀 주입<br>• WebGL 픽셀 노이즈(`WebGLMarkEx`) 및 `navigator.gpu` WebGPU 어댑터 아키텍처 위조 |
| **🧬 C++ 엔진 지문 격리** | • **Canvas 2D (`CanvasMarkEx`)**, **AudioContext (`AudioFp`)**, **DOMRect (`ClientRectFp`)** 프로파일별 결정론적 시드 변조<br>• **OS 교차 에뮬레이션**: Windows 11, macOS 14 Sonoma (Apple Silicon), Linux Ubuntu, Android 14, iPhone 15 Pro (`NewMobileMode`, `MaxTouchPoints=5`)<br>• **Google Chrome `x-browser-validation`**: OS별 공식 시드 기반 SHA-1 헤더 자동 생성 및 `Alt+P` 인간 타이핑 붙여넣기 내장 |
| **⚡ 무중단 Hot-Reload & API** | • 브라우저 실행 중 재시작 없이 `<profile_dir>/<md5(id + "_webrtc")>` 사이드카를 갱신하여 **WebRTC IP · 타임존 · GPS 위치 즉시 변경**<br>• `127.0.0.1:50325` Local API (`v1` / `v2` 호환)로 **Selenium / Puppeteer / Playwright** 즉시 연결 |

---

## 🚀 빠른 시작 (Quick Start)

### 1. 저장소 클론
```powershell
git clone https://github.com/Rami9112/free-proxy-browser.git
cd free-proxy-browser
```

### 2. 데스크톱 프로그램 실행 (`Windows x64` & `ARM64`)
별도의 외부 패키지 설치 없이 **Python 3.9+** 와 **Windows Edge WebView2 런타임**(Windows 10/11 기본 내장)만 있으면 즉시 실행됩니다.

```powershell
# 방법 1: 네이티브 데스크톱 실행 파일 (권장)
.\FreeProxyBrowser.exe

# 방법 2: 배치 파일 실행
.\start_free_proxy_browser.bat

# 방법 3: Python 직접 실행
python free_proxy_browser.py
```
> 💡 **첫 실행 안내**: GitHub 용량 제한(100MB) 준수를 위해 분할 압축된 커널 바이너리(`chrome.dll.zpart*`, `xul.dll.zpart*`)가 첫 실행 시 자동으로 병합·압축 해제됩니다(약 2~3초 소요).

---

## 🛠️ CLI 및 자동화 사용법 (CLI & Automation)

### CLI 명령어
```powershell
# 커널(TaeBrowser 153 & YangBrowser 153) 및 프로파일 상태 확인
python free_proxy_browser.py status

# 프로파일 목록 조회
python free_proxy_browser.py list

# 새 프록시 브라우저 프로파일 생성
python free_proxy_browser.py create --name "US Store #1" --kernel taebrowser --os Windows --proxy-type socks5 --proxy-host proxy.example.com --proxy-port 1080

# 특정 프로파일 브라우저 실행 / 종료
python free_proxy_browser.py start fa1001win
python free_proxy_browser.py stop fa1001win

# 실행 중인 브라우저의 WebRTC IP & 타임존 실시간 무중단 변경 (Hot-Reload)
python free_proxy_browser.py dynamic-update fa1001win --ip 198.51.100.77 --tz America/New_York

# 전체 엔드투엔드 자동 검증 스위트 실행
python free_proxy_browser.py test --launch-browsers
```

### Python Selenium 연동 예제
```python
import urllib.request
import json
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

# 1. Local API를 통해 프로파일 실행
with urllib.request.urlopen("http://127.0.0.1:50325/api/v1/browser/start?user_id=fa1001win") as res:
    data = json.loads(res.read().decode("utf-8"))["data"]

# 2. 반환된 ChromeDriver 및 디버그 포트로 즉시 연결
opts = Options()
opts.add_experimental_option("debuggerAddress", data["ws"]["selenium"])
driver = webdriver.Chrome(service=Service(data["webdriver"]), options=opts)
print("Connected Browser Title:", driver.title)
```

---

## 📁 프로젝트 구조 (Project Structure)

```text
free-proxy-browser/
├── FreeProxyBrowser.exe           # 네이티브 Windows 데스크톱 실행 파일 (x64 & ARM64 AnyCPU, 커스텀 아이콘 적용)
├── free_proxy_browser.py          # 메인 CLI & 데스크톱 런처 엔트리포인트
├── start_free_proxy_browser.bat   # 원클릭 실행 배치 스크립트
├── assets/
│   ├── hero-banner.svg            # GitHub 리드미 전면 모션그래픽 배너 (Animated SVG)
│   ├── icon.ico                   # 멀티 해상도(16px~256px) 실행 & 윈도우 타이틀바/작업표시줄 아이콘
│   ├── icon.png                   # 고해상도(512x512) 앱 아이콘
│   └── icon.svg                   # 벡터 원본 아이콘
├── core/
│   ├── FreeAntiDesktopLauncher.cs # C# WinForms + WebView2 데스크톱 클라이언트 소스 (x64/ARM64 호환)
│   ├── database.py                # SQLite 프로파일 · 그룹 · 프록시 데이터베이스 엔진
│   ├── fingerprint.py             # GPU/OpenGL 카탈로그, 프록시 GeoIP 리졸버 & MD5 사이드카 컴파일러
│   ├── kernel_rebrander.py        # TaeBrowser 153 & YangBrowser 153 커널 빌더 및 자동 언패커
│   ├── kernels.py                 # 커널 및 확장프로그램 자동 탐색 모듈
│   ├── launcher.py                # 브라우저 프로세스 스포너, 핸드셰이크 & 실시간 Hot-Reload 매니저
│   ├── extension_builder.py       # Google Chrome x-browser-validation SHA-1 헤더 위조 확장 빌더
│   └── server.py                  # 내장 HTTP 제어 서버 & Local API (v1/v2) 호환 레이어
├── ui/
│   ├── index.html                 # 데스크톱 프로파일 스튜디오 & 프록시 매니저 UI
│   └── verify.html                # 실시간 C++ 지문 훅 검증 페이지 (/verify)
├── runtimes/                      # 아키텍처별 네이티브 WebView2Loader.dll (win-x64, win-arm64, win-x86)
└── kernels/                       # 독립 리브랜딩된 TaeBrowser 153 & YangBrowser 153 커널 바이너리
```

---

## 📄 라이선스 (License)

이 프로젝트는 오픈소스 **MIT License** 하에 배포됩니다.
