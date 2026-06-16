# Browser Tool UX & Stability Todo List

This document outlines planned improvements, quick UX wins, and complex refactors to elevate the browser experience in Meedia Studio.

## 🔒 Security

- [ ] **Certificate Error Interception — Hardened Warning Page**
  - Currently, TLS certificate errors may be silently bypassed or dismissed without user awareness. Implement a full-page interstitial (replacing the web view content) that renders the error code, the affected domain, and the certificate's CN/SAN fields. Require an explicit user action to proceed. Log all bypasses with timestamp + domain to a local audit log file.
  - *Target File:* [`CustomWebEnginePage`](file:///C:/Users/User/Documents/GitHub/meedia-studio/src/browser_tab.py) via `certificateError` signal.

- [ ] **HTTP to HTTPS Upgrade with Fallback Banner**
  - When a user navigates to a plain `http://` URL, automatically attempt the `https://` equivalent first. If the HTTPS upgrade fails (connection error / timeout), fall through to the HTTP version but inject a non-dismissible warning banner into the rendered page: *"⚠ This page is not encrypted. Your connection to [domain] is not secure."* Never silently serve HTTP.
  - *Target File:* [`browser_tab.py`](file:///C:/Users/User/Documents/GitHub/meedia-studio/src/browser_tab.py) in `navigate_to` before committing the URL load.

- [ ] **Permission Request Audit Log with Per-Origin Persistence**
  - When a site requests camera, microphone, geolocation, or desktop notifications, show a persistent in-app permission bar (not a native OS dialog) with the site's origin, the permission type icon, and Allow / Block / Block Always buttons. Persist per-origin decisions in `settings.json` under a `browser_permissions` key. Expose a "Site Permissions" view in settings to review and revoke stored grants.
  - *Target File:* [`browser_tab.py`](file:///C:/Users/User/Documents/GitHub/meedia-studio/src/browser_tab.py) via `featurePermissionRequested` signal on `QWebEnginePage`.

- [X] **Download Safety Screening — Extension Blocklist + Hash Warning**
  - Before writing any downloaded file to disk, check its extension against a blocklist of dangerous types (`.exe`, `.bat`, `.cmd`, `.scr`, `.ps1`, `.vbs`, `.msi`, `.jar`, `.hta`). Show a modal warning dialog naming the file and its type, with a prominent "Cancel Download" primary action and a de-emphasized "Download Anyway" secondary action. Log all warnings.
  - *Target File:* [`browser_tab.py`](file:///C:/Users/User/Documents/GitHub/meedia-studio/src/browser_tab.py) in the `QWebEngineDownloadRequest` handler.

- [ ] **Mixed Content Indicator in Address Bar**
  - Display a security badge in the URL bar that reflects the current page's TLS state: 🔒 full HTTPS, ⚠️ mixed content (HTTPS page loading HTTP sub-resources), 🔴 plain HTTP. Use `QWebEnginePage.certificateError`, URL scheme inspection on `loadFinished`, and JS injection (`window.performance.getEntriesByType('resource')`) to detect mixed content. Tooltip on the badge must show the exact issue.
  - *Target File:* [`browser_tab.py`](file:///C:/Users/User/Documents/GitHub/meedia-studio/src/browser_tab.py) in URL bar rendering and `loadFinished`.

- [ ] **Response Header Security Inspector**
  - On each page load, capture HTTP response headers via `QWebEngineUrlRequestInterceptor`. Parse and score the page's security posture: missing `Content-Security-Policy`, absent `X-Frame-Options`, `Set-Cookie` without `HttpOnly` / `Secure` flags, missing `Strict-Transport-Security`. Surface a colour-coded shield icon in the toolbar (green / amber / red). Clicking it opens a compact panel listing each header's status.
  - *Target File:* [`browser_tab.py`](file:///C:/Users/User/Documents/GitHub/meedia-studio/src/browser_tab.py) + new `request_interceptor.py`.

- [ ] **Per-Site Cookie & Storage Isolation (Containerised Profiles)**
  - Allow the user to right-click the address bar security badge and choose "Isolate this site" — allocating a separate `QWebEngineProfile` for that origin so its cookies, `localStorage`, `IndexedDB`, and service workers are fully siloed from the default profile. Show a coloured container badge on tabs running in isolation. Useful for multi-account logins without private mode.
  - *Target File:* [`browser_tab.py`](file:///C:/Users/User/Documents/GitHub/meedia-studio/src/browser_tab.py) in `add_new_tab`, backed by a `{origin: QWebEngineProfile}` registry dict.

- [ ] **Auto-Fill Suppression for User-Defined Sensitive Domains**
  - Let the user define a blocklist of domain patterns (e.g. `*.bankofamerica.com`) in settings. On `loadFinished`, if the current URL matches any pattern, inject a script that sets `autocomplete="off"` on all `<input>` fields, removes `autofill` hints, and disables credential autofill for that origin via `QWebEngineProfile` settings. Display a subtle lock badge to confirm suppression is active.
  - *Target File:* [`browser_tab.py`](file:///C:/Users/User/Documents/GitHub/meedia-studio/src/browser_tab.py) in `loadFinished` via `runJavaScript`.

## 🎨 UI & UX Issues

- [ ] **Immersive Reader Mode**
  - Add a "Reader" toggle icon in the address bar (visible only on article-like pages, detected by checking for `<article>` / `itemprop="articleBody"` / high text-to-element ratio via injected JS). On activation, strip navigation chrome, ads, and sidebars using a bundled `Readability.js` extractor and render the cleaned content as a styled full-page overlay with selectable font size and line-height controls.
  - *Target File:* [`browser_tab.py`](file:///C:/Users/User/Documents/GitHub/meedia-studio/src/browser_tab.py) via `runJavaScript` with bundled `Readability.js`.

- [ ] **Picture-in-Picture (PiP) Video Detach**
  - Add a "Pop Out Video" option to the right-click context menu on `<video>` elements. Detach the video's `src` into a frameless, always-on-top `QDialog` with a dark background, play/pause and volume controls, and a resize handle. The original tab's video element should be paused cleanly. Closing the PiP window resumes the tab's video at the same timestamp.
  - *Target File:* [`browser_tab.py`](file:///C:/Users/User/Documents/GitHub/meedia-studio/src/browser_tab.py) in `createStandardContextMenu` override + new `pip_window.py`.

- [ ] **Custom DNS-over-HTTPS (DoH) — Full Interception Pipeline**
  - The current DoH setting is stored in settings but has no actual interception implementation. Implement a `QWebEngineUrlRequestInterceptor` subclass that resolves hostnames via the user-selected DoH provider (Cloudflare, Google, AdGuard, or custom) using async `QNetworkAccessManager` requests before forwarding to the engine. Without this, the setting is cosmetic only and does not protect against ISP-level DNS snooping.
  - *Target File:* [`browser_tab.py`](file:///C:/Users/User/Documents/GitHub/meedia-studio/src/browser_tab.py) + new `dns_resolver.py` utility.

- [ ] **Per-Site Custom Script Injector (Userscripts)**
  - Add a "Scripts" section in browser settings where users can define JavaScript snippets scoped to URL glob patterns (e.g. `*://github.com/*`). On `loadFinished`, iterate matching scripts by URL and inject them via `runJavaScript`. Include an enable/disable toggle per script, a last-run timestamp, and a console output capture pane. Lightweight Tampermonkey equivalent, natively integrated.
  - *Target File:* Browser settings HTML + [`browser_tab.py`](file:///C:/Users/User/Documents/GitHub/meedia-studio/src/browser_tab.py) in `loadFinished`.

- [ ] **Viewport Emulation Presets (Responsive Testing)**
  - Extend the User-Agent selector in settings to also resize the `QWebEngineView` to common device resolutions (375×812 iPhone SE, 390×844 iPhone 14, 768×1024 iPad, 1280×800 Desktop). Inject the matching `<meta name="viewport">` override via JS. When a non-desktop preset is active, overlay a thin device-frame border around the viewport and show a persistent "Device Emulation Active" badge in the toolbar.
  - *Target File:* [`browser_tab.py`](file:///C:/Users/User/Documents/GitHub/meedia-studio/src/browser_tab.py) in UA change handler.

- [ ] **Offline Page Cache — Graceful Degradation**
  - On every successful `loadFinished`, asynchronously snapshot the page's outer HTML and store it on disk keyed by URL hash (LRU cache, max 50 pages, configurable). If the next load of the same URL fails due to network error, serve the cached snapshot with a top banner: *"You're offline — showing a saved version from [date]."* Avoids blank error screens on connectivity loss.
  - *Target File:* [`browser_tab.py`](file:///C:/Users/User/Documents/GitHub/meedia-studio/src/browser_tab.py) in `loadFinished` + new `offline_cache.py` module.

- [ ] **Element Clip / Screenshot Tool**
  - Add a "Clip Region" toolbar button. On activation, overlay a semi-transparent rubber-band selection widget on top of the `QWebEngineView`. On mouse release, call `QWebEngineView.grab()` cropped to the selection rect, copy the result to the clipboard, and show a Save As dialog. Include a 1-second ghost flash animation on the selected region to confirm capture. Ideal for saving UI references or collecting web assets.
  - *Target File:* [`browser_tab.py`](file:///C:/Users/User/Documents/GitHub/meedia-studio/src/browser_tab.py) — new `BrowserClipOverlay(QWidget)` layered over the web view.

- [ ] **Network Request Throttling (Developer Mode)**
  - Add a hidden "Dev Mode" toggle accessible from the `⋯` overflow menu that exposes a throttle selector: None / Slow 3G (400 Kbps, 400 ms latency) / Fast 3G (1.5 Mbps, 40 ms latency) / Offline. Implement via a `QWebEngineUrlRequestInterceptor` that introduces artificial delays on outgoing requests and drops all requests for Offline mode. Show a persistent amber "Throttled: Slow 3G" badge in the address bar when active.
  - *Target File:* [`browser_tab.py`](file:///C:/Users/User/Documents/GitHub/meedia-studio/src/browser_tab.py) + `request_interceptor.py`.

- [ ] **Page Resource Audit Badge**
  - After each `loadFinished`, tally the total number of intercepted network requests and their approximate transfer sizes, broken down by type (images, JS, CSS, fonts, XHR). Display a compact *"48 req · 2.8 MB"* badge in the toolbar. Clicking the badge opens a side panel with a sortable list of all requests, their type, size, and status code. Flag notably large resources (> 1 MB) in amber.
  - *Target File:* [`browser_tab.py`](file:///C:/Users/User/Documents/GitHub/meedia-studio/src/browser_tab.py) + `request_interceptor.py` — accumulate stats in the interceptor, emit a signal on `loadFinished`.

## 🔬 Reliability & Correctness

- [ ] **Smart URL Bar Fuzzy Auto-Complete from Full History**
  - The current autocomplete sources only URLs. Query the full `browser_history` list (which now stores titles + URLs) and match against both fields using fuzzy substring scoring. Show the top 8 results in a styled `QListView` popup below the URL bar with favicon, title (bold matched chars), and URL. `↑/↓` to navigate, `Enter` to load, `Escape` to dismiss without navigating.
  - *Target File:* [`browser_tab.py`](file:///C:/Users/User/Documents/GitHub/meedia-studio/src/browser_tab.py) — subclass `QLineEdit` + `QCompleter` with a custom `QAbstractItemModel`.

- [ ] **Tab Session Crash Recovery — Granular State Preservation**
  - On unclean exit (process kill, crash) the current session restore only saves URLs. Extend it to also persist each tab's forward/back history stack (via `QWebEngineHistory` serialization), scroll position, and form field contents where possible. On next launch, show a "Restore Session" banner listing the tabs with their titles and favicons, not just a silent auto-reload.
  - *Target File:* [`browser_tab.py`](file:///C:/Users/User/Documents/GitHub/meedia-studio/src/browser_tab.py) in session persistence logic + `main.py` on startup.

- [ ] **Memory Pressure Relief — Background Tab Suspension**
  - After a user-configurable timeout (default 15 min), automatically suspend background tabs that haven't been interacted with by calling `QWebEngineView.page().setLifecycleState(LifecycleState.Discarded)`. Show a "Suspended" overlay on discarded tabs. On re-activation (tab click), reload the page and restore scroll position. Expose the timeout setting in the browser settings panel.
  - *Target File:* [`browser_tab.py`](file:///C:/Users/User/Documents/GitHub/meedia-studio/src/browser_tab.py) — `QTimer` per tab, lifecycle state management.
