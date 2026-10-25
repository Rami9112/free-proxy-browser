// freeanti Stealth Assistant — Autonomous x-browser-validation Header Spoofer
const TARGET_DOMAINS = [
  { id: 1, name: "google", regex: "^https?://([a-z0-9-]+\\.)?google\\.[a-z]{2,}(\\.[a-z]{2,})?(?:/|$)" },
  { id: 2, name: "youtube", regex: "^https?://([a-z0-9-]+\\.)?youtube\\.[a-z]{2,}(\\.[a-z]{2,})?(?:/|$)" },
  { id: 3, name: "chromeWebstore", regex: "^https?://chromewebstore\\.google\\.com(?:/|$)" }
];

const CHROME_VALIDATION_SEEDS = {
  WINDOWS: "AIzaSyA2KlwBX3mkFo30om9LUFYQhpqLoa_BNhE",
  LINUX:   "AIzaSyBqJZh-7pA44blAaAkH6490hUFOwX0KCYM",
  MACOS:   "AIzaSyDr2UxVnv_U85AbhhY8XSHSIavUW0DC-sY"
};

function getChromeMajorVersion(ua) {
  const m = ua.match(/Chrome\/(\d+)\./);
  return m ? Number.parseInt(m[1], 10) : 153;
}

async function computeValidationHeader() {
  const ua = navigator.userAgent;
  const uaLower = ua.toLowerCase();
  const osKey = uaLower.includes("windows")
    ? "WINDOWS"
    : (uaLower.includes("linux") && !uaLower.includes("android"))
      ? "LINUX"
      : "MACOS";
  const payload = `${CHROME_VALIDATION_SEEDS[osKey]}${ua}`;
  const year = getChromeMajorVersion(ua) > 131 ? "2025" : "2024";
  const encoded = new TextEncoder().encode(payload);
  const digest = await crypto.subtle.digest("SHA-1", encoded);
  const rawBytes = Array.from(new Uint8Array(digest)).map(b => String.fromCharCode(b)).join("");
  return { hash: btoa(rawBytes), year };
}

async function installValidationRules() {
  try {
    const { hash, year } = await computeValidationHeader();
    const requestHeaders = [
      { header: "x-browser-channel", operation: chrome.declarativeNetRequest.HeaderOperation.SET, value: "stable" },
      { header: "x-browser-copyright", operation: chrome.declarativeNetRequest.HeaderOperation.SET, value: `Copyright ${year} Google LLC. All rights reserved.` },
      { header: "x-browser-validation", operation: chrome.declarativeNetRequest.HeaderOperation.SET, value: hash },
      { header: "x-browser-year", operation: chrome.declarativeNetRequest.HeaderOperation.SET, value: year }
    ];
    const resourceTypes = [
      chrome.declarativeNetRequest.ResourceType.MAIN_FRAME,
      chrome.declarativeNetRequest.ResourceType.SUB_FRAME,
      chrome.declarativeNetRequest.ResourceType.STYLESHEET,
      chrome.declarativeNetRequest.ResourceType.SCRIPT,
      chrome.declarativeNetRequest.ResourceType.IMAGE,
      chrome.declarativeNetRequest.ResourceType.FONT,
      chrome.declarativeNetRequest.ResourceType.OBJECT,
      chrome.declarativeNetRequest.ResourceType.XMLHTTPREQUEST,
      chrome.declarativeNetRequest.ResourceType.PING,
      chrome.declarativeNetRequest.ResourceType.CSP_REPORT,
      chrome.declarativeNetRequest.ResourceType.MEDIA,
      chrome.declarativeNetRequest.ResourceType.WEBSOCKET,
      chrome.declarativeNetRequest.ResourceType.WEBTRANSPORT,
      chrome.declarativeNetRequest.ResourceType.WEBBUNDLE,
      chrome.declarativeNetRequest.ResourceType.OTHER
    ];
    const addRules = TARGET_DOMAINS.map(d => ({
      id: d.id,
      priority: 1,
      action: {
        type: chrome.declarativeNetRequest.RuleActionType.MODIFY_HEADERS,
        requestHeaders
      },
      condition: {
        regexFilter: d.regex,
        resourceTypes
      }
    }));
    await chrome.declarativeNetRequest.updateSessionRules({
      removeRuleIds: TARGET_DOMAINS.map(d => d.id),
      addRules
    });
  } catch (err) {
    console.error("[freeanti_assistant] Failed to install x-browser-validation rules:", err);
  }
}

chrome.runtime.onInstalled.addListener(() => { installValidationRules(); });
chrome.runtime.onStartup.addListener(() => { installValidationRules(); });
installValidationRules();
