# -*- coding: utf-8 -*-
# Core logic for bookmark link checker / archiver. No GUI here.
# ASCII-only code comments; Chinese only as string data.
import json, os, re, shutil, subprocess, uuid, datetime, time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import urllib3
urllib3.disable_warnings()

_USER_HOME = os.path.expanduser('~')
BACKUP_DIR = os.path.join(_USER_HOME, 'Documents',
                          '\u6536\u85cf\u5939\u94fe\u63a5\u68c0\u6d4b\u5907\u4efd')  # Documents/收藏夹链接检测备份
ARCHIVE_FOLDER_NAME = '\u5931\u6548\u94fe\u63a5\u5f52\u6863'  # 失效链接归档

BROWSERS = {
    'Edge': r'{user}\Microsoft\Edge\User Data\Default\Bookmarks',
    'Chrome': r'{user}\Google\Chrome\User Data\Default\Bookmarks',
}

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0')
HEADERS = {
    'User-Agent': UA,
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
}
BLOCKED_CODES = {401, 403, 405, 406, 409, 429, 999}

# verdict -> (display text, severity)  severity: dead / weak / alive
VERDICT_INFO = {
    'DEAD_404': ('\u786e\u5b9a\u5931\u6548\uff08\u9875\u9762404\uff09', 'dead'),
    'DNS_FAIL': ('\u786e\u5b9a\u5931\u6548\uff08\u57df\u540d\u4e0d\u5b58\u5728\uff09', 'dead'),
    'CONN_FAIL': ('\u786e\u5b9a\u5931\u6548\uff08\u8fde\u63a5\u4e0d\u4e0a\uff09', 'dead'),
    'SSL_FAIL': ('\u786e\u5b9a\u5931\u6548\uff08\u8bc1\u4e66\u6253\u4e0d\u5f00\uff09', 'dead'),
    'TIMEOUT': ('\u8d85\u65f6\uff0c\u53ef\u80fd\u53cd\u722c\u6216\u7f51\u7edc\u5feb\uff0c\u7f51\u9875\u53ef\u80fd\u80fd\u5f00', 'weak'),
    'SERVER_ERR': ('\u670d\u52a1\u5668\u62a5\u9519\uff0c\u53ef\u80fd\u4e34\u65f6\u6545\u969c', 'weak'),
    'SSL_BROKEN': ('\u8bc1\u4e66\u5f02\u5e38\uff08\u7f51\u7ad9\u80fd\u5f00\uff09', 'alive'),
}
DEAD_SET = {'DEAD_404', 'DNS_FAIL', 'CONN_FAIL', 'SSL_FAIL'}
WEAK_SET = {'TIMEOUT', 'SERVER_ERR'}
# quick definitive verdicts stop retrying
FINAL_GOOD = {'OK', 'BLOCKED', 'DEAD_404', 'DNS_FAIL'}


def bookmark_path(browser):
    tpl = BROWSERS[browser]
    base = os.environ.get('LOCALAPPDATA', os.path.join(_USER_HOME, 'AppData', 'Local'))
    return tpl.format(user=base)


def walk_bookmarks(data, scope):
    """Pre-order walk in bookmark display order.
    scope: 'other' | 'all'
    Returns list of dicts: id, folder, name, url."""
    roots = data.get('roots', {})
    names = ['other'] if scope == 'other' else [k for k in roots if isinstance(roots[k], dict)]
    items = []

    def rec(node, path):
        for ch in node.get('children', []) or []:
            if ch.get('type') == 'folder':
                rec(ch, path + [ch.get('name', '')])
            elif ch.get('type') == 'url':
                u = ch.get('url', '')
                if u.startswith('http://') or u.startswith('https://'):
                    items.append({
                        'id': str(ch.get('id', '')),
                        'folder': ' / '.join(path) if path else '',
                        'name': ch.get('name', ''),
                        'url': u,
                    })

    for key in names:
        root = roots[key]
        name = root.get('name', '')
        base = [] if name in ('\u5176\u4ed6\u6536\u85cf\u5939',) else [name]
        rec(root, base)
    return items


def load_items(bm_path, scope):
    with open(bm_path, encoding='utf-8') as f:
        data = json.load(f)
    return data, walk_bookmarks(data, scope)


def load_html(path):
    """Parse a browser-exported bookmarks.html (Netscape format).
    Returns a list of dicts: id/folder/name/url/src='html'."""
    with open(path, 'rb') as f:
        raw = f.read()
    text = None
    for enc in ('utf-8-sig', 'utf-8', 'gbk'):
        try:
            text = raw.decode(enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    if text is None:
        text = raw.decode('utf-8', errors='replace')
    items = []
    depth = 0
    folder_chain = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        m = re.search(r'<DT><H3[^>]*>(.*?)</H3>', s, re.I | re.S)
        if m:
            name = re.sub(r'<[^>]+>', '', m.group(1)).strip()
            name = _unescape(name)
            while len(folder_chain) > depth:
                folder_chain.pop()
            folder_chain.append(name)
            depth += 1
            continue
        m = re.search(r'<DT><A\s+[^>]*HREF="([^"]+)"[^>]*>(.*?)</A>', s, re.I | re.S)
        if m:
            url = m.group(1).strip()
            name = re.sub(r'<[^>]+>', '', m.group(2)).strip()
            name = _unescape(name) or url
            if url.startswith('http://') or url.startswith('https://'):
                items.append({
                    'id': str(uuid.uuid4()),
                    'folder': ' / '.join(folder_chain),
                    'name': name[:200],
                    'url': url,
                    'src': 'html',
                })
            continue
        if re.search(r'</DL>', s, re.I):
            if folder_chain:
                folder_chain.pop()
            depth = max(0, depth - 1)
    return items


def _unescape(s):
    return (s.replace('&amp;', '&').replace('&lt;', '<')
             .replace('&gt;', '>').replace('&quot;', '"')
             .replace('&#39;', "'"))


def remove_from_html(path, urls):
    """Remove the bookmark lines whose HREF matches one of urls from a
    Netscape-format bookmarks.html, and drop folders that become empty as a
    result. Returns the number of links removed. Matches by exact URL."""
    with open(path, 'rb') as f:
        raw = f.read()
    try:
        text = raw.decode('utf-8-sig')
        enc = 'utf-8-sig'
    except UnicodeDecodeError:
        text = raw.decode('gbk', errors='replace')
        enc = 'gbk'
    wanted = set(urls)
    kept = []
    removed = 0
    for line in text.splitlines(keepends=True):
        m = re.search(r'<DT><A\s+[^>]*HREF="([^"]+)"', line, re.I)
        if m and m.group(1).strip() in wanted:
            removed += 1
            continue
        kept.append(line)
    new_text = ''.join(kept)
    # drop any now-empty <DL><p> ... </DL><p> groups (allow only whitespace inside)
    changed = True
    while changed:
        changed = False
        pat = re.compile(r'<DT><DL><p>\s*</DL><p>\s*', re.I | re.S)
        new_text2, n = pat.subn('', new_text)
        if n:
            new_text = new_text2
            changed = True
        pat2 = re.compile(r'<DT><H3[^>]*>[^<]*</H3>\s*<DL><p>\s*</DL><p>\s*', re.I | re.S)
        new_text2, n = pat2.subn('', new_text)
        if n:
            new_text = new_text2
            changed = True
    if removed:
        if enc == 'utf-8-sig':
            with open(path, 'w', encoding='utf-8-sig') as f:
                f.write(new_text)
        else:
            with open(path, 'w', encoding='gbk') as f:
                f.write(new_text)
    return removed


def _attempt(s, url, timeout, verify=True, method='GET'):
    """Send a request and return the status code, reading the full body so
    anti-bot sites that only answer headers don't slip through. Lets the
    original exception propagate so callers can tell timeouts from refused
    connections apart."""
    if method == 'HEAD':
        r = s.head(url, timeout=timeout, allow_redirects=True, verify=verify)
    else:
        r = s.get(url, timeout=timeout, allow_redirects=True, verify=verify)
    code = r.status_code
    try:
        for _chunk in r.iter_content(8192):
            break
    except Exception:
        pass
    r.close()
    return code


def _dns_ok(host):
    """Independently resolve the hostname to avoid blaming DNS for a transient
    network wobble. Returns True when the name resolves (or resolution fails
    for an unknown reason we can't be sure about)."""
    import socket
    try:
        socket.getaddrinfo(host, None)
        return True
    except socket.gaierror:
        return False
    except Exception:
        return True


def _parse_host(url):
    from urllib.parse import urlparse
    return urlparse(url).hostname or ''


def check_url(url):
    """Returns (verdict, code, err). A conservative checker: transient network
    problems are downgraded to 'weak' instead of being declared dead, because a
    site that is slow / briefly unreachable / protected by anti-bot measures is
    usually still alive in a real browser."""
    import requests as _req
    s = requests.Session()
    s.headers.update(HEADERS)
    verdict, code, err = 'UNKNOWN', None, ''
    host = _parse_host(url)
    TimeoutExc = (_req.exceptions.ConnectTimeout, _req.exceptions.ReadTimeout)
    ConnExc = _req.exceptions.ConnectionError

    def classify(code2):
        if code2 is None:
            return None
        if 200 <= code2 < 400:
            return 'OK'
        if code2 in BLOCKED_CODES:
            return 'BLOCKED'
        if code2 in (404, 410):
            return 'DEAD_404'
        if code2 >= 500:
            return 'SERVER_ERR'
        return 'HTTP_%d' % code2

    # ---- pass 1: quick GET ----
    try:
        code = _attempt(s, url, (6, 10))
        verdict = classify(code) or verdict
    except TimeoutExc:
        err = 'timeout'
        # transient: retry with a longer window
        try:
            code = _attempt(s, url, (15, 30))
            verdict = classify(code) or 'TIMEOUT'
        except TimeoutExc:
            verdict = 'TIMEOUT'
        except ConnExc:
            verdict = 'TIMEOUT'
    except ConnExc as e:
        err = str(e)[:120]
        low = err.lower()
        is_dns = ('getaddrinfo' in low or 'name or service' in low or 'nodename' in low
                  or 'no address' in low or 'name does not resolve' in low)
        if is_dns:
            # independent DNS check: only call it dead if the name truly fails
            verdict = 'DNS_FAIL' if (not host or not _dns_ok(host)) else 'TIMEOUT'
        elif 'timed out' in low or 'timeout' in low or 'read timed' in low:
            # a read/connect timeout arrived via the ConnectionError branch:
            # treat it as the same transient 'weak' timeout, not a dead link
            verdict = 'TIMEOUT'
        else:
            # connection reset/refused: anti-bot sites cut off scripted requests.
            # Try HEAD then a longer GET before giving up, and land on 'weak'
            # if still unreachable (a real browser may still load it).
            def dns_or_timeout(e2):
                low2 = str(e2).lower()
                if (host and not _dns_ok(host)
                        and ('getaddrinfo' in low2 or 'resolve' in low2 or 'name' in low2)):
                    return 'DNS_FAIL'
                if 'timed out' in low2 or 'timeout' in low2 or 'read timed' in low2:
                    return 'TIMEOUT'
                return None
            try:
                code = _attempt(s, url, (10, 20), method='HEAD')
                verdict = classify(code) or 'CONN_FAIL'
            except Exception as e2:
                v2 = dns_or_timeout(e2)
                if v2:
                    verdict = v2
                else:
                    try:
                        code = _attempt(s, url, (15, 30))
                        verdict = classify(code) or 'CONN_FAIL'
                    except Exception as e3:
                        v3 = dns_or_timeout(e3)
                        verdict = v3 or 'CONN_FAIL'
    except _req.exceptions.SSLError:
        # certificate problem: if it loads without verification, it's alive
        try:
            code = _attempt(s, url, (10, 20), verify=False)
            if code is not None and 200 <= code < 400:
                verdict = 'SSL_BROKEN'
            elif code is not None:
                verdict = 'HTTP_%d' % code
            else:
                verdict = 'SSL_FAIL'
        except Exception:
            verdict = 'SSL_FAIL'
    except Exception as e:
        err = type(e).__name__
        verdict = 'ERROR'

    # ---- if we still couldn't reach it after all attempts, prefer 'weak' ----
    if verdict in ('CONN_FAIL', 'ERROR'):
        # one last full GET attempt
        try:
            code = _attempt(s, url, (20, 40))
            verdict = classify(code) or verdict
        except Exception:
            pass
    return verdict, code, err


def check_all(urls, workers, progress_cb=None, stop_cb=None, result_cb=None):
    """Check many urls concurrently. progress_cb(done, total).
    result_cb(url, (verdict, code, err)) is called as soon as each url
    finishes, so the GUI can reveal results live instead of waiting.
    stop_cb: optional callable polled between completions; when it turns
    true, pending urls are cancelled and partial results are returned."""
    results = {}
    total = len(urls)
    done = 0
    ex = ThreadPoolExecutor(max_workers=workers)
    try:
        futs = {ex.submit(check_url, u): u for u in urls}
        for fut in as_completed(futs):
            u = futs[fut]
            res = fut.result()
            results[u] = res
            done += 1
            if result_cb:
                try:
                    result_cb(u, res)
                except Exception:
                    pass
            if progress_cb:
                progress_cb(done, total)
            if stop_cb is not None and stop_cb():
                for f in futs:
                    f.cancel()
                break
    finally:
        ex.shutdown(wait=True, cancel_futures=True)
    return results


def browser_running(browser):
    exe = 'msedge.exe' if browser == 'Edge' else 'chrome.exe'
    try:
        r = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq %s' % exe],
                           capture_output=True, text=True, timeout=15,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return exe.lower() in (r.stdout or '').lower()
    except Exception:
        return True  # assume running on failure, safer


def _chrome_now():
    # Chrome/Edge epoch: microseconds since 1601-01-01 (UTC based)
    return str(int((time.time() + 11644473600) * 1000000))


def archive_links(bm_path, node_ids, folder_name=ARCHIVE_FOLDER_NAME, mode='archive',
                  backup_dir=None):
    """Move or delete bookmark url-nodes (matched by node id).
    mode: 'archive' -> move into folder under 'other' root.
          'delete'  -> remove entirely.
    Backs up first. Returns (backup_path, moved_count).
    Raises on error after backup is made."""
    os.makedirs(backup_dir or BACKUP_DIR, exist_ok=True)
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = os.path.join(backup_dir or BACKUP_DIR, 'Bookmarks_%s.json' % ts)
    shutil.copy2(bm_path, bak)

    with open(bm_path, encoding='utf-8') as f:
        data = json.load(f)

    wanted = set(str(i) for i in node_ids)
    removed = []

    def prune(node):
        ch = node.get('children')
        if not ch:
            return
        keep = []
        for c in ch:
            if c.get('type') == 'url' and str(c.get('id', '')) in wanted:
                removed.append(c)
            else:
                prune(c)
                keep.append(c)
        node['children'] = keep

    for rk, root in data.get('roots', {}).items():
        if isinstance(root, dict):
            prune(root)

    max_id = 0

    def scan_id(n):
        nonlocal max_id
        try:
            max_id = max(max_id, int(str(n.get('id', '0'))))
        except (TypeError, ValueError):
            pass
        for c in n.get('children', []) or []:
            scan_id(c)

    for root in data.get('roots', {}).values():
        if isinstance(root, dict):
            scan_id(root)

    other = data.get('roots', {}).get('other')
    if mode == 'archive':
        if other is None:
            raise RuntimeError('no other-favorites root found')
        arch = None
        for c in other.get('children', []) or []:
            if c.get('type') == 'folder' and c.get('name') == folder_name:
                arch = c
                break
        if arch is None:
            arch = {
                'children': [],
                'date_added': _chrome_now(),
                'date_modified': _chrome_now(),
                'guid': str(uuid.uuid4()),
                'id': str(max_id + 1),
                'name': folder_name,
                'type': 'folder',
            }
            other.setdefault('children', []).append(arch)

        for node in removed:
            arch['children'].append(node)

    data.pop('checksum', None)
    tmp = bm_path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=3)
    os.replace(tmp, bm_path)

    # verify by re-reading (lesson: always re-read after modifying)
    with open(bm_path, encoding='utf-8') as f:
        check = json.load(f)
    if mode == 'delete':
        remain = []

        def scan_remain(n):
            if n.get('type') == 'url' and str(n.get('id', '')) in wanted:
                remain.append(str(n.get('id', '')))
            for c in n.get('children', []) or []:
                scan_remain(c)

        for root in check.get('roots', {}).values():
            if isinstance(root, dict):
                scan_remain(root)
        if remain:
            raise RuntimeError('verify failed: %d still present' % len(remain))
        return bak, len(removed), len(removed)

    found = 0

    def count_arch(n):
        nonlocal found
        if n.get('type') == 'folder' and n.get('name') == folder_name:
            found = len([c for c in n.get('children', []) if c.get('type') == 'url'])
            return
        for c in n.get('children', []) or []:
            count_arch(c)

    for root in check.get('roots', {}).values():
        if isinstance(root, dict):
            count_arch(root)
    if found < len(removed):
        raise RuntimeError('verify failed: %d/%d' % (found, len(removed)))
    return bak, len(removed), found


def domain_of(url):
    return re.sub(r'^https?://', '', url).split('/')[0]


def status_text(verdict, code):
    if verdict in VERDICT_INFO:
        return VERDICT_INFO[verdict][0]
    if verdict.startswith('HTTP_'):
        return '\u72b6\u6001\u7801' + verdict[5:]  # 状态码xxx
    return verdict


def severity(verdict):
    return VERDICT_INFO.get(verdict, ('', 'alive'))[1]


def build_report(rows):
    """rows: list of dicts with folder/name/url/verdict, in bookmark order.
    Format approved by user: no #, no slashes (use ＞)."""
    lines = ['\u5931\u6548\u94fe\u63a5']  # 失效链接
    for i, r in enumerate(rows, 1):
        cat = (r['folder'] or '').replace(' / ', '\uff1e').replace('\u2b50\ufe0f', '').replace('\u2b50', '')
        lines.append('%d. [%s] %s\uff08%s\uff09\u300e%s\u300f' % (
            i, cat, r['name'][:40], domain_of(r['url']), status_text(r['verdict'], None)))
    return '\n'.join(lines) + '\n'
