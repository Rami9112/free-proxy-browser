using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net.Sockets;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

[assembly: AssemblyTitle("Free Proxy Browser — Anti-Detect & Proxy Browser Manager")]
[assembly: AssemblyDescription("Free Proxy Browser Native Microsoft Edge WebView2 Desktop Application (Windows x64 & ARM64)")]
[assembly: AssemblyCompany("Free Proxy Browser Open Source")]
[assembly: AssemblyProduct("Free Proxy Browser Desktop Client (TaeBrowser & YangBrowser)")]
[assembly: AssemblyVersion("2.1.0.0")]
[assembly: AssemblyFileVersion("2.1.0.0")]

namespace FreeAnti
{
    public class FreeAntiMainForm : Form
    {
        [DllImport("user32.dll", CharSet = CharSet.Auto)]
        private static extern IntPtr SendMessage(IntPtr hWnd, int Msg, IntPtr wParam, IntPtr lParam);

        private const int WM_SETICON = 0x0080;
        private static readonly IntPtr ICON_SMALL = new IntPtr(0);
        private static readonly IntPtr ICON_BIG = new IntPtr(1);

        private readonly WebView2 _webView;
        private readonly string _targetUrl;
        private readonly string _userDataFolder;
        private readonly Process _backendProc;
        private readonly Icon _appIcon;

        public FreeAntiMainForm(string targetUrl, string userDataFolder, Process backendProc)
        {
            _targetUrl = targetUrl;
            _userDataFolder = userDataFolder;
            _backendProc = backendProc;

            Text = "Free Proxy Browser — Anti-Detect & Proxy Browser Manager (TaeBrowser & YangBrowser)";
            Width = 1440;
            Height = 900;
            MinimumSize = new Size(1040, 680);
            StartPosition = FormStartPosition.CenterScreen;
            BackColor = Color.FromArgb(11, 15, 25);
            ShowIcon = true;

            _appIcon = LoadAppIcon();
            if (_appIcon != null)
            {
                Icon = _appIcon;
            }

            _webView = new WebView2
            {
                Dock = DockStyle.Fill,
                DefaultBackgroundColor = Color.FromArgb(11, 15, 25)
            };
            Controls.Add(_webView);

            HandleCreated += OnFormHandleCreated;
            Load += OnMainFormLoad;
            FormClosed += OnMainFormClosed;
        }

        private static Icon LoadAppIcon()
        {
            try
            {
                string baseDir = AppDomain.CurrentDomain.BaseDirectory;
                string[] candidates = new string[]
                {
                    Path.Combine(baseDir, "assets", "icon.ico"),
                    Path.Combine(baseDir, "icon.ico")
                };
                foreach (string path in candidates)
                {
                    if (File.Exists(path))
                    {
                        return new Icon(path);
                    }
                }
                return Icon.ExtractAssociatedIcon(Application.ExecutablePath);
            }
            catch
            {
                return null;
            }
        }

        private void OnFormHandleCreated(object sender, EventArgs e)
        {
            try
            {
                if (_appIcon != null && IsHandleCreated)
                {
                    SendMessage(Handle, WM_SETICON, ICON_BIG, _appIcon.Handle);
                    SendMessage(Handle, WM_SETICON, ICON_SMALL, _appIcon.Handle);
                }
            }
            catch { }
        }

        private void Log(string msg)
        {
            try
            {
                string logDir = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "data");
                Directory.CreateDirectory(logDir);
                File.AppendAllText(
                    Path.Combine(logDir, "webview2.log"),
                    DateTime.Now.ToString("HH:mm:ss.fff") + " " + msg + Environment.NewLine
                );
            }
            catch { }
        }

        private async void OnMainFormLoad(object sender, EventArgs e)
        {
            try
            {
                Log("OnMainFormLoad started. Creating WebView2 environment at: " + _userDataFolder);
                Directory.CreateDirectory(_userDataFolder);
                var env = await CoreWebView2Environment.CreateAsync(null, _userDataFolder, null);
                Log("CoreWebView2Environment created: " + env.BrowserVersionString);
                await _webView.EnsureCoreWebView2Async(env);
                Log("EnsureCoreWebView2Async completed.");

                if (_webView.CoreWebView2 != null)
                {
                    _webView.CoreWebView2.Settings.IsStatusBarEnabled = false;
                    _webView.CoreWebView2.Settings.AreDefaultContextMenusEnabled = true;
                    _webView.CoreWebView2.Settings.AreDevToolsEnabled = true;
                    _webView.CoreWebView2.NewWindowRequested += (s, args) =>
                    {
                        args.Handled = true;
                        var popup = new FreeAntiMainForm(args.Uri, _userDataFolder, null)
                        {
                            Text = "Free Proxy Browser — Live Browser Fingerprint Verification (TaeBrowser & YangBrowser)",
                            Width = 1280,
                            Height = 820
                        };
                        popup.Show();
                    };
                    _webView.CoreWebView2.Navigate(_targetUrl);
                    Log("Navigated to: " + _targetUrl);
                }
            }
            catch (Exception ex)
            {
                Log("WebView2 exception: " + ex.ToString());
                MessageBox.Show(
                    "WebView2 초기화 오류: " + ex.Message,
                    "Free Proxy Browser WebView2 Error",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error
                );
            }
        }

        private void OnMainFormClosed(object sender, FormClosedEventArgs e)
        {
            if (_backendProc != null)
            {
                try
                {
                    if (!_backendProc.HasExited)
                    {
                        _backendProc.Kill();
                    }
                }
                catch
                {
                }
            }
        }
    }

    static class Program
    {
        [DllImport("user32.dll")]
        private static extern bool SetProcessDPIAware();

        [DllImport("shell32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern int SetCurrentProcessExplicitAppUserModelID(string AppID);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern IntPtr LoadLibraryW(string lpFileName);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern bool SetDllDirectoryW(string lpPathName);

        /// <summary>
        /// Pre-loads the native WebView2Loader.dll matching the current CLR process architecture
        /// (win-x64, win-arm64, or win-x86) so the AnyCPU executable runs natively on both
        /// Windows x64 and Windows ARM64 without BadImageFormatException.
        /// </summary>
        private static void PreloadNativeWebView2Loader(string baseDir)
        {
            try
            {
                string[] archOrder;
                if (IntPtr.Size == 4)
                {
                    archOrder = new string[] { "win-x86" };
                }
                else
                {
                    string procArch = (Environment.GetEnvironmentVariable("PROCESSOR_ARCHITECTURE") ?? "").ToUpperInvariant();
                    if (procArch.Contains("ARM"))
                    {
                        archOrder = new string[] { "win-arm64", "win-x64" };
                    }
                    else
                    {
                        archOrder = new string[] { "win-x64", "win-arm64" };
                    }
                }

                foreach (string arch in archOrder)
                {
                    string nativeDir = Path.Combine(baseDir, "runtimes", arch, "native");
                    string dllPath = Path.Combine(nativeDir, "WebView2Loader.dll");
                    if (File.Exists(dllPath))
                    {
                        IntPtr handle = LoadLibraryW(dllPath);
                        if (handle != IntPtr.Zero)
                        {
                            SetDllDirectoryW(nativeDir);
                            return;
                        }
                    }
                }

                string rootDll = Path.Combine(baseDir, "WebView2Loader.dll");
                if (File.Exists(rootDll))
                {
                    LoadLibraryW(rootDll);
                }
            }
            catch { }
        }

        private static bool IsPortListening(string host, int port)
        {
            try
            {
                using (var client = new TcpClient())
                {
                    var result = client.BeginConnect(host, port, null, null);
                    bool success = result.AsyncWaitHandle.WaitOne(TimeSpan.FromMilliseconds(250));
                    if (!success) return false;
                    client.EndConnect(result);
                    return true;
                }
            }
            catch
            {
                return false;
            }
        }

        private static bool IsValidPythonExe(string exePath)
        {
            try
            {
                if (string.IsNullOrEmpty(exePath) || !File.Exists(exePath))
                    return false;
                // Skip 0-byte Microsoft Store app execution alias stub inside WindowsApps
                if (exePath.IndexOf("WindowsApps", StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    var fi = new FileInfo(exePath);
                    if (fi.Length < 1024)
                        return false;
                }
                return true;
            }
            catch
            {
                return false;
            }
        }

        /// <summary>
        /// Resolves python.exe across both Windows x64 and Windows ARM64 installations:
        /// 1. Local portable python / .venv inside the application folder
        /// 2. %LocalAppData%\Programs\Python\Python* (both x64 Python3xx and Python3xx-arm64)
        /// 3. %ProgramFiles%\Python*, %ProgramFiles(x86)%\Python*, C:\Python*
        /// 4. Anaconda / Miniconda in user profile
        /// 5. PATH environment variable (excluding 0-byte WindowsApps Store stub)
        /// 6. Windows Python Launcher (C:\Windows\py.exe)
        /// </summary>
        private static string FindPythonExe(string baseDir)
        {
            var directCandidates = new List<string>
            {
                Path.Combine(baseDir, "python", "python.exe"),
                Path.Combine(baseDir, ".venv", "Scripts", "python.exe"),
                Path.Combine(baseDir, "venv", "Scripts", "python.exe")
            };
            foreach (string c in directCandidates)
            {
                if (IsValidPythonExe(c)) return c;
            }

            string localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            string progFiles = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles);
            string progFilesX86 = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86);
            string userProfile = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);

            var searchRoots = new List<string>
            {
                Path.Combine(localAppData, "Programs", "Python"),
                progFiles,
                progFilesX86,
                @"C:\"
            };

            foreach (string root in searchRoots)
            {
                try
                {
                    if (!string.IsNullOrEmpty(root) && Directory.Exists(root))
                    {
                        string[] dirs = Directory.GetDirectories(root, "Python*");
                        Array.Sort(dirs);
                        Array.Reverse(dirs); // Prefer newest Python version (e.g. Python314, Python313, Python312)
                        foreach (string dir in dirs)
                        {
                            string candidate = Path.Combine(dir, "python.exe");
                            if (IsValidPythonExe(candidate))
                            {
                                return candidate;
                            }
                        }
                    }
                }
                catch { }
            }

            var condaCandidates = new List<string>
            {
                Path.Combine(userProfile, "miniconda3", "python.exe"),
                Path.Combine(userProfile, "anaconda3", "python.exe"),
                Path.Combine(localAppData, "miniconda3", "python.exe"),
                Path.Combine(localAppData, "anaconda3", "python.exe")
            };
            foreach (string c in condaCandidates)
            {
                if (IsValidPythonExe(c)) return c;
            }

            string pathEnv = Environment.GetEnvironmentVariable("PATH") ?? "";
            foreach (string p in pathEnv.Split(Path.PathSeparator))
            {
                try
                {
                    string dir = p.Trim().Trim('"');
                    if (string.IsNullOrEmpty(dir)) continue;
                    string candidate = Path.Combine(dir, "python.exe");
                    if (IsValidPythonExe(candidate))
                    {
                        return candidate;
                    }
                }
                catch { }
            }

            string pyLauncher = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows), "py.exe");
            if (File.Exists(pyLauncher))
            {
                return pyLauncher;
            }

            return "python.exe";
        }

        [STAThread]
        static int Main(string[] args)
        {
            try { SetProcessDPIAware(); } catch { }
            try { SetCurrentProcessExplicitAppUserModelID("FreeProxyBrowser.Desktop.Client"); } catch { }

            string baseDir = AppDomain.CurrentDomain.BaseDirectory;
            PreloadNativeWebView2Loader(baseDir);

            string scriptPath = Path.Combine(baseDir, "free_proxy_browser.py");
            if (!File.Exists(scriptPath))
            {
                scriptPath = Path.Combine(baseDir, "freeanti.py");
            }
            int port = 50325;
            string host = "127.0.0.1";

            Process backendProc = null;
            if (!IsPortListening(host, port) && File.Exists(scriptPath))
            {
                string pythonExe = FindPythonExe(baseDir);
                string pyArgs = "\"" + scriptPath + "\" --port " + port + " serve --no-open";
                if (pythonExe.EndsWith("py.exe", StringComparison.OrdinalIgnoreCase))
                {
                    pyArgs = "-3 " + pyArgs;
                }
                var psi = new ProcessStartInfo
                {
                    FileName = pythonExe,
                    Arguments = pyArgs,
                    WorkingDirectory = baseDir,
                    UseShellExecute = false,
                    CreateNoWindow = true
                };
                try
                {
                    backendProc = Process.Start(psi);
                }
                catch
                {
                }

                // Wait up to 8 seconds for backend HTTP server (and first-run kernel unpack if needed) to bind
                var sw = Stopwatch.StartNew();
                while (sw.ElapsedMilliseconds < 8000)
                {
                    if (IsPortListening(host, port))
                    {
                        break;
                    }
                    Thread.Sleep(150);
                }
            }

            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            string url = "http://" + host + ":" + port + "/";
            string cacheDir = Path.Combine(baseDir, "data", "webview2_cache");
            Application.Run(new FreeAntiMainForm(url, cacheDir, backendProc));
            return 0;
        }
    }
}
