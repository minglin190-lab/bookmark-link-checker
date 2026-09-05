# Bookmark Link Checker

[**中文说明 / Chinese**](README.zh-CN.md)

A green, portable browser bookmark dead-link checker for **Edge / Chrome**. Runs fully locally — your bookmarks never leave your machine.

Works on **Windows / macOS / Linux**.

## Features

- **One-click check**: reads Edge / Chrome bookmarks (or an imported HTML bookmarks file), checks with 32 threads in parallel, and shows results **live as they finish** — no need to wait for everything to complete
- **Three-tier verdict**:
  - 🔴 **Dead**: HTTP 404, domain does not exist, connection refused, certificate failure
  - 🟡 **Suspicious**: timeout, server error (may be anti-bot blocking or network fluctuation — the page may still open in a browser)
  - ⚪ **Alive**: normal response, or blocked by the site (403/401 etc. — the link itself is fine)
- **Import HTML bookmarks**: supports browser-exported `bookmarks.html` (nested folders, UTF-8 / GBK encodings)
- **Right-click actions** (on any result row):
  - Double-click / right-click "Open URL" → open in browser to verify
  - "Delete URL" → removes it from browser bookmarks (auto-backup first); for HTML-imported items, removes it from the HTML file too
  - "Mark as OK" → remove a false positive from the dead list
- **One-click archive**: move dead links into a "失效链接归档" (dead links archive) folder in your bookmarks (auto-backup before any change)
- **Export report**: save a dead-link report to your Desktop
- **Re-check selected**: re-test specific links individually
- **Settings**: customize where reports and backups are saved

## Usage

**Windows**: download `BookmarkChecker.exe` from [Releases](https://github.com/minglin190-lab/bookmark-link-checker/releases), double-click and run. No installation needed.

**macOS / Linux**: run from source (Python 3 + `requests` required):

```bash
git clone https://github.com/minglin190-lab/bookmark-link-checker.git
cd bookmark-link-checker
pip install requests
python gui.py
```

**Build a standalone executable** (Windows, requires PyInstaller):

```bash
pyinstaller --noconfirm --onefile --windowed --icon icon.ico --name BookmarkChecker gui.py
```

## How verdicts work

The tool probes each URL over HTTP, with hardening against false positives:

- Domain existence is **independently re-verified with DNS** (`socket.getaddrinfo`) to avoid blaming a live site for a transient DNS wobble
- On connection failure it retries with HEAD first, then a longer-timeout GET — **anti-bot sites that cut off scripted requests are not declared dead**
- Timeouts, server errors and other unreliable signals are always downgraded to "suspicious" (yellow), never "dead"
- Only reliable signals (HTTP 404, confirmed missing domain) are marked "dead" (red)

**Limitations**: the tool can only tell whether a URL is reachable — it cannot detect "content rot" (e.g. the site is still up but the article is gone, or an expired domain now shows ads). Those need manual verification. Detection depends on your network environment; occasional false positives are possible — always confirm the suspicious ones manually.

## Privacy

- 100% local: bookmarks never leave your machine
- Backups are saved to `Documents/收藏夹链接检测备份` (configurable in Settings)
- Reports default to your Desktop (configurable in Settings)

## License

[MIT License](LICENSE)
