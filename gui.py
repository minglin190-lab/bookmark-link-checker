# -*- coding: utf-8 -*-
# GUI for the bookmark link checker / archiver (tkinter, no extra deps).
import os, sys, json, queue, threading, datetime, webbrowser, subprocess
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import core
import bm_lang as lang
from bm_lang import tr

DEFAULT_REPORT_DIR = os.path.join(os.path.expanduser('~'), 'Desktop')
DEFAULT_BACKUP_DIR = core.BACKUP_DIR


def open_folder(path):
    """Open a folder in the platform's file manager (works on Win/Mac/Linux)."""
    try:
        if sys.platform == 'win32':
            os.startfile(path)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', path])
        else:
            subprocess.Popen(['xdg-open', path])
    except Exception:
        pass


def _exe_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def config_path():
    return os.path.join(_exe_dir(), 'settings.json')


def load_settings():
    try:
        with open(config_path(), encoding='utf-8') as f:
            d = json.load(f)
        if isinstance(d, dict):
            return d
    except Exception:
        pass
    return {}


def save_settings(d):
    try:
        with open(config_path(), 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

# verdict -> (display text, tag)  tag: dead / weak / alive / archived
DISPLAY = dict(core.VERDICT_INFO)
DISPLAY['OK'] = ('能打开', 'alive')  # translated via _dtext
DISPLAY['BLOCKED'] = ('能打开（网站拦截自动访问，链接正常）', 'alive')
DISPLAY['ARCHIVED'] = ('已归档', 'archived')
DISPLAY['WAIT'] = ('检测中…', 'alive')
DISPLAY['SKIP'] = ('未检测', 'archived')


def res_path(name):
    # works both as script and frozen onefile exe
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def row_tag(verdict):
    if verdict in ('ARCHIVED', 'SKIP'):
        return 'archived'
    return core.severity(verdict)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(tr('收藏夹链接检测'))
        self.geometry('1050x680')
        self.minsize(920, 580)
        try:
            self.iconbitmap(res_path('icon.ico'))
        except Exception:
            pass

        self.q = queue.Queue()
        self.rows = []  # dicts: id/folder/name/url/verdict/code/err
        self.rows_from_html = None  # None=empty, True=from HTML, False=from browser
        self.busy = False
        self.stop_event = threading.Event()
        self.epoch = 0  # guards against stale worker events after a stop
        self.settings = load_settings()
        self.report_dir = self.settings.get('report_dir') or DEFAULT_REPORT_DIR
        self.backup_dir = self.settings.get('backup_dir') or DEFAULT_BACKUP_DIR

        self._build_style()
        self._build_ui()
        self.after(80, self._poll)
        self.protocol('WM_DELETE_WINDOW', self._close)

    # ---------------- ui ----------------
    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use('vista')
        except Exception:
            pass
        self.option_add('*Font', '{Microsoft YaHei UI} 10')
        style.configure('.', font=('Microsoft YaHei UI', 10))
        style.configure('Treeview', rowheight=30)
        style.configure('Treeview.Heading', font=('Microsoft YaHei UI', 10, 'bold'))
        style.configure('TButton', padding=(12, 5))
        style.configure('TCombobox', padding=4)

    def _build_ui(self):
        top = ttk.Frame(self, padding=(12, 12, 12, 4))
        top.pack(fill='x')
        ttk.Label(top, text=tr('浏览器：')).pack(side='left')
        self.browser_var = tk.StringVar(value='Edge')
        self.browser_box = ttk.Combobox(top, textvariable=self.browser_var,
                                        values=['Edge', 'Chrome'],
                                        state='readonly', width=8)
        self.browser_box.pack(side='left', padx=(0, 14))
        ttk.Label(top, text=tr('范围：')).pack(side='left')
        self.scope_box = ttk.Combobox(top, values=[tr('其他收藏夹'), tr('全部收藏夹')],
                                      state='readonly', width=10)
        self.scope_box.current(1)
        self.scope_box.pack(side='left', padx=(0, 14))
        self.browser_box.bind('<<ComboboxSelected>>', self._on_source_change)
        self.scope_box.bind('<<ComboboxSelected>>', self._on_source_change)
        self.btn_start = ttk.Button(top, text=tr('开始检测'), command=self.start_check)
        self.btn_start.pack(side='left')
        self.btn_stop = ttk.Button(top, text=tr('停止'), command=self.stop_check)
        self.btn_stop.pack(side='left', padx=(8, 0))
        self.btn_stop.state(['disabled'])

        prog = ttk.Frame(self, padding=(12, 4, 12, 8))
        prog.pack(fill='x')
        self.pb = ttk.Progressbar(prog, mode='determinate')
        self.pb.pack(side='left', fill='x', expand=True, padx=(0, 12))
        self.only_dead_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(prog, text=tr('只看失效'), variable=self.only_dead_var,
                        command=self._populate).pack(side='left', padx=(0, 12))
        self.btn_import = ttk.Button(prog, text=tr('导入 HTML 收藏夹…'),
                                     command=self.import_html)
        self.btn_import.pack(side='left')
        self.prog_lbl = ttk.Label(prog, text=tr('待检测'), width=12, anchor='e')
        self.prog_lbl.pack(side='left', padx=(10, 0))

        mid = ttk.Frame(self, padding=(12, 0, 12, 6))
        mid.pack(fill='both', expand=True)
        cols = ('status', 'name', 'folder', 'url')
        heads = {'status': tr('状态'), 'name': tr('名称'), 'folder': tr('所在文件夹'), 'url': tr('网址')}
        widths = {'status': 200, 'name': 300, 'folder': 200, 'url': 330}
        self.tree = ttk.Treeview(mid, columns=cols, show='headings',
                                 selectmode='extended')
        for c in cols:
            self.tree.heading(c, text=heads[c])
            self.tree.column(c, width=widths[c], anchor='w',
                             stretch=(c in ('name', 'url')))
        vs = ttk.Scrollbar(mid, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side='left', fill='both', expand=True)
        vs.pack(side='right', fill='y')
        self.tree.tag_configure('dead', foreground='#c62828')
        self.tree.tag_configure('weak', foreground='#e65100')
        self.tree.tag_configure('alive', foreground='#37474f')
        self.tree.tag_configure('archived', foreground='#9e9e9e')
        self.tree.bind('<Double-1>', self._open_url)
        self.tree.bind('<Button-3>', self._context_menu)

        bottom = ttk.Frame(self, padding=(12, 2, 12, 8))
        bottom.pack(fill='x')
        self.btn_recheck = ttk.Button(bottom, text=tr('复检选中'), command=self.recheck_selected)
        self.btn_recheck.pack(side='left')
        self.btn_report = ttk.Button(bottom, text=tr('导出失效报告'), command=self.export_report)
        self.btn_report.pack(side='left', padx=10)
        self.btn_archive = ttk.Button(bottom, text=tr('归档失效链接…'), command=self.archive_dead)
        self.btn_archive.pack(side='left')
        self.btn_settings = ttk.Button(bottom, text=tr('设置…'), command=self.open_settings)
        self.btn_settings.pack(side='left', padx=10)

        status_row = ttk.Frame(self, padding=(12, 0, 12, 8))
        status_row.pack(fill='x')
        self.status = tk.StringVar(value=tr('就绪。点“开始检测”先跑一遍。'))
        ttk.Label(status_row, textvariable=self.status, foreground='#455a64').pack(side='left')
        ttk.Label(status_row, text=tr('双击一行打开网址｜右键更多操作'),
                  foreground='#78909c').pack(side='right')
        self.action_buttons = [self.btn_start, self.btn_recheck,
                               self.btn_report, self.btn_archive,
                               self.btn_import]

    # ---------------- helpers ----------------
    def _scope(self):
        return 'all' if self.scope_box.current() == 1 else 'other'

    def _set_busy(self, b):
        self.busy = b
        for w in self.action_buttons:
            w.state(['disabled'] if b else ['!disabled'])
        self.btn_stop.state(['!disabled'] if b else ['disabled'])
        self.stop_event.clear()

    def stop_check(self):
        if not self.busy:
            return
        self.stop_event.set()
        self.btn_stop.state(['disabled'])
        self.status.set(tr('正在停止…已发出的网络请求要等几秒超时才断开，稍等一下。'))

    def _poll(self):
        try:
            while True:
                ev = self.q.get_nowait()
                kind = ev[0]
                if kind == 'prog':
                    if ev[3] == self.epoch:
                        self.pb.configure(value=ev[1])
                        self.prog_lbl.configure(text='%d / %d' % (ev[1], ev[2]))
                elif kind == 'row_result':
                    idx, res, ep = ev[1], ev[2], ev[3]
                    if ep != self.epoch:
                        continue
                    if 0 <= idx < len(self.rows):
                        v, c, e = res
                        r = self.rows[idx]
                        r['verdict'], r['code'], r['err'] = v, c, e
                        self._update_row(idx)
                elif kind == 'checked':
                    res, stopped, ep = ev[1], ev[2], ev[3]
                    if ep != self.epoch:
                        continue
                    for r in self.rows:
                        if r['url'] in res:
                            v, c, e = res[r['url']]
                            r['verdict'], r['code'], r['err'] = v, c, e
                        else:
                            r['verdict'] = 'SKIP'
                    self._populate()
                    self._set_busy(False)
                    dead = sum(1 for r in self.rows if core.severity(r['verdict']) == 'dead')
                    weak = sum(1 for r in self.rows if core.severity(r['verdict']) == 'weak')
                    skip = sum(1 for r in self.rows if r['verdict'] == 'SKIP')
                    n = len(self.rows) - skip
                    self.prog_lbl.configure(text=tr('已停止') if stopped else tr('完成'))
                    if stopped:
                        self.status.set(tr('已停止：检测了 %d 条，跳过 %d 条。'
                                            '可再点“开始检测”重查，或选中几条用“复检选中”。')
                                            % (n, skip))
                    else:
                        self.status.set(tr('检测完成：确定失效 %d 条，疑似问题 %d 条，正常 %d 条')
                                        % (dead, weak, n - dead - weak))
                elif kind == 'rechecked':
                    idxs, res, stopped, ep = ev[1], ev[2], ev[3], ev[4]
                    if ep != self.epoch:
                        continue
                    got = 0
                    for i in idxs:
                        r = self.rows[i]
                        if r['url'] in res:
                            v, c, e = res[r['url']]
                            r['verdict'], r['code'], r['err'] = v, c, e
                            got += 1
                    self._populate()
                    self._set_busy(False)
                    self.prog_lbl.configure(text=tr('已停止') if stopped else tr('完成'))
                    self.status.set(tr('复检%s：更新了 %d 条。')
                                    % (tr('已停止') if stopped else tr('完成'), got))
                elif kind == 'archived':
                    bak, n, found = ev[1], ev[2], ev[3]
                    for r in self.rows:
                        if core.severity(r['verdict']) == 'dead':
                            r['verdict'] = 'ARCHIVED'
                    self._populate()
                    self._set_busy(False)
                    self.status.set(tr('已归档 %d 条，备份：%s') % (found, bak))
                    if messagebox.askyesno(
                            tr('归档完成'),
                            tr('已把 %d 条失效链接移入收藏夹的“失效链接归档”文件夹。\n'
                               '改动前自动备份在：\n%s\n\n现在打开备份文件夹吗？') % (found, bak)):
                        open_folder(os.path.dirname(bak))
                elif kind == 'error':
                    self._set_busy(False)
                    self.status.set(tr('出错'))
                    messagebox.showerror(tr('出错'), ev[1])
        except queue.Empty:
            pass
        self.after(80, self._poll)

    def _populate(self):
        self.tree.delete(*self.tree.get_children())
        for i, r in enumerate(self.rows):
            if self.only_dead_var.get() and core.severity(r['verdict']) != 'dead':
                continue
            txt = DISPLAY.get(r['verdict'], (core.status_text(r['verdict'], None),
                                             'alive'))[0]
            self.tree.insert('', 'end', iid=str(i), tags=(row_tag(r['verdict']),),
                             values=(txt, r['name'], r['folder'], r['url']))

    def _update_row(self, idx):
        """Live-update a single row in the tree without rebuilding the whole
        list, so results appear as they finish during detection."""
        r = self.rows[idx]
        if self.only_dead_var.get() and core.severity(r['verdict']) != 'dead':
            if self.tree.exists(str(idx)):
                self.tree.delete(str(idx))
            return
        txt = DISPLAY.get(r['verdict'], (core.status_text(r['verdict'], None),
                                         'alive'))[0]
        if self.tree.exists(str(idx)):
            self.tree.item(str(idx), values=(txt, r['name'], r['folder'], r['url']),
                           tags=(row_tag(r['verdict']),))
        else:
            self.tree.insert('', 'end', iid=str(idx), tags=(row_tag(r['verdict']),),
                             values=(txt, r['name'], r['folder'], r['url']))

    # ---------------- actions ----------------
    def _on_source_change(self, _ev=None):
        if not self.busy:
            self.rows = []
            self.rows_from_html = None
            self._populate()
            self.status.set(tr('已切换来源。点“开始检测”载入新的收藏夹。'))

    def start_check(self):
        if self.busy:
            return
        # Only load browser bookmarks if there is no list yet. Imported-HTML
        # lists are kept as-is (rows already filled with src=html), so choosing
        # a file then starting won't be overwritten by the browser bookmarks.
        if not self.rows:
            try:
                bm = core.bookmark_path(self.browser_var.get())
                _, items = core.load_items(bm, self._scope())
            except Exception as e:
                messagebox.showerror(tr('读取收藏夹失败'),
                                     tr('找不到收藏夹文件或读取失败：\n%s') % e)
                return
            if not items:
                messagebox.showinfo(tr('没有链接'), tr('这个范围内没有要检测的网址链接。'))
                return
            self.rows = [dict(it, verdict='WAIT', code=None, err='') for it in items]
            self.rows_from_html = False
        self._populate()
        self._set_busy(True)
        self.pb.configure(maximum=len(self.rows), value=0)
        self.prog_lbl.configure(text='0 / %d' % len(self.rows))
        self.status.set(tr('正在检测 %d 条链接…') % len(self.rows))
        self.epoch += 1
        threading.Thread(target=self._work_check, args=(self.epoch,),
                         daemon=True).start()

    def import_html(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(
            title=tr('选择导出的收藏夹 HTML 文件'),
            filetypes=[(tr('HTML 文件'), '*.html *.htm'), (tr('所有文件'), '*.*')])
        if not path:
            return
        try:
            items = core.load_html(path)
        except Exception as e:
            messagebox.showerror(tr('导入失败'), tr('解析文件出错：\n%s') % e)
            return
        if not items:
            messagebox.showinfo(tr('没有链接'), tr('这个 HTML 文件里没有找到网址链接。'))
            return
        self.rows = [dict(it, verdict='WAIT', code=None, err='') for it in items]
        self.rows_from_html = True
        self.html_path = path
        self._populate()
        self.status.set(tr('已从 HTML 导入 %d 条链接（%s）。点“开始检测”即可检测。')
                        % (len(items), os.path.basename(path)))
        self.prog_lbl.configure(text=tr('%d 条') % len(items))

    def _work_check(self, ep):
        urls = [r['url'] for r in self.rows]
        self.row_index = {u: i for i, u in enumerate(urls)}
        try:
            res = core.check_all(
                urls, 32,
                progress_cb=lambda d, t: self.q.put(('prog', d, t, ep)),
                stop_cb=self.stop_event.is_set,
                result_cb=lambda u, r: self.q.put(
                    ('row_result', self.row_index[u], r, ep)))
            self.q.put(('checked', res, self.stop_event.is_set(), ep))
        except Exception as e:
            self.q.put(('error', tr('检测出错：%s') % e, ep))

    def recheck_selected(self):
        if self.busy:
            return
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo(tr('提示'), tr('先在列表里选中要复检的行（按住 Ctrl 可多选）。'))
            return
        idxs = sorted(int(s) for s in sel)
        self._set_busy(True)
        self.pb.configure(maximum=len(idxs), value=0)
        self.prog_lbl.configure(text='0 / %d' % len(idxs))
        self.status.set(tr('复检选中的 %d 条…') % len(idxs))
        self.epoch += 1
        threading.Thread(target=self._work_recheck, args=(idxs, self.epoch),
                         daemon=True).start()

    def _work_recheck(self, idxs, ep):
        urls = [self.rows[i]['url'] for i in idxs]
        try:
            res = core.check_all(
                urls, min(16, max(1, len(urls))),
                progress_cb=lambda d, t: self.q.put(('prog', d, t, ep)),
                stop_cb=self.stop_event.is_set)
            self.q.put(('rechecked', idxs, res, self.stop_event.is_set(), ep))
        except Exception as e:
            self.q.put(('error', tr('复检出错：%s') % e, ep))

    def export_report(self):
        dead = [r for r in self.rows if core.severity(r['verdict']) == 'dead']
        weak = [r for r in self.rows if core.severity(r['verdict']) == 'weak']
        if not dead and not weak:
            messagebox.showinfo(tr('没有失效链接'), tr('当前结果里没有失效或疑似问题的链接。'))
            return
        text = core.build_report(dead + weak)
        os.makedirs(self.report_dir, exist_ok=True)
        path = os.path.join(self.report_dir, '失效链接报告_%s.txt' %
                            datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
        with open(path, 'w', encoding='utf-8-sig') as f:
            f.write(text)
        self.status.set(tr('报告已保存：%s') % path)
        if messagebox.askyesno(tr('报告已导出'), tr('已保存到：\n%s\n\n现在打开所在文件夹吗？') % path):
            open_folder(self.report_dir)

    def archive_dead(self):
        if self.busy:
            return
        browser = self.browser_var.get()
        dead = [r for r in self.rows if core.severity(r['verdict']) == 'dead'
                and r.get('src') != 'html']
        html_dead = sum(1 for r in self.rows if core.severity(r['verdict']) == 'dead'
                        and r.get('src') == 'html')
        if not dead:
            if html_dead:
                messagebox.showinfo(tr('无法归档'),
                                    tr('失效链接都来自 HTML 导入（不在浏览器收藏夹里），'
                                       '不能归档。\n可导出失效报告自己核对。'))
            else:
                messagebox.showinfo(tr('没有可归档的链接'), tr('列表里没有“确定失效”的链接。'))
            return
        extra = tr('\n（另有 %d 条来自 HTML 导入的失效项不能归档，已跳过）') % html_dead if html_dead else ''
        if not messagebox.askyesno(
                tr('确认归档'),
                tr('将把 %d 条“确定失效”的链接移动到收藏夹的“失效链接归档”文件夹。\n'
                   '（超时、服务器报错等疑似问题不动；网址不删除，只是换位置）%s\n\n继续吗？')
                % (len(dead), extra)):
            return
        if core.browser_running(browser):
            if not messagebox.askyesno(
                    tr('%s 正在运行') % browser,
                    tr('%s 正在运行，退出前它可能把改动覆盖回去。\n'
                       '建议先完全退出 %s 再归档。\n\n仍要现在继续吗？') % (browser, browser)):
                return
        try:
            bm = core.bookmark_path(browser)
        except Exception as e:
            messagebox.showerror(tr('出错'), str(e))
            return
        self._set_busy(True)
        self.status.set(tr('正在归档并写入收藏夹…'))
        threading.Thread(target=self._work_archive,
                         args=(bm, [r['id'] for r in dead]), daemon=True).start()

    def _work_archive(self, bm, ids):
        try:
            bak, n, found = core.archive_links(bm, ids, backup_dir=self.backup_dir)
            self.q.put(('archived', bak, n, found))
        except Exception as e:
            self.q.put(('error', tr('归档失败（收藏夹已先自动备份，可手动还原）：\n%s') % e))

    def _open_url(self, _ev):
        sel = self.tree.selection()
        if sel:
            webbrowser.open(self.rows[int(sel[0])]['url'])

    # ---------------- context menu (right-click) ----------------
    def _context_menu(self, ev):
        iid = self.tree.identify_row(ev.y)
        if not iid:
            return
        if iid not in self.tree.selection():
            self.tree.selection_set(iid)
        idx = int(iid)
        r = self.rows[idx]
        menu = tk.Menu(self, tearoff=0)
        if r.get('src') == 'html':
            menu.add_command(label=tr('打开网址'), command=lambda: self._open_url(None))
            menu.add_separator()
            menu.add_command(label=tr('删除该网址（同时从 HTML 文件删除）'),
                             command=lambda: self._del_html_row(idx))
            menu.add_command(label=tr('标记为正常（移除出失效名单）'),
                             command=lambda: self._mark_alive(idx))
        else:
            menu.add_command(label=tr('打开网址'), command=lambda: self._open_url(None))
            menu.add_separator()
            menu.add_command(label=tr('删除该网址（从浏览器收藏夹删除，自动备份）'),
                             command=lambda: self._del_browser_row(idx))
            menu.add_command(label=tr('标记为正常（移除出失效名单）'),
                             command=lambda: self._mark_alive(idx))
        try:
            menu.tk_popup(ev.x_root, ev.y_root)
        finally:
            menu.grab_release()

    def _del_browser_row(self, idx):
        r = self.rows[idx]
        browser = self.browser_var.get()
        if not messagebox.askyesno(
                tr('确认删除'),
                tr('确定要从浏览器收藏夹删除这条链接吗？\n\n%s\n%s')
                % (r['name'], r['url'])):
            return
        if core.browser_running(browser):
            if not messagebox.askyesno(
                    tr('%s 正在运行') % browser,
                    tr('%s 正在运行，退出前它可能把改动覆盖回去。\n'
                       '建议先完全退出 %s 再删除。\n\n仍要现在继续吗？') % (browser, browser)):
                return
        try:
            bm = core.bookmark_path(browser)
        except Exception as e:
            messagebox.showerror(tr('出错'), str(e))
            return
        try:
            bak, n, _found = core.archive_links(bm, [r['id']], mode='delete',
                                                backup_dir=self.backup_dir)
        except Exception as e:
            messagebox.showerror(tr('删除失败'), tr('删除失败（收藏夹已自动备份）：\n%s') % e)
            return
        del self.rows[idx]
        self._populate()
        self.status.set(tr('已删除 %d 条，备份：%s') % (n, bak))

    def _del_html_row(self, idx):
        r = self.rows[idx]
        path = getattr(self, 'html_path', None)
        if not path:
            messagebox.showerror(tr('出错'), tr('找不到导入的 HTML 文件路径。'))
            return
        if not messagebox.askyesno(
                tr('确认删除'),
                tr('确定要从导入的 HTML 文件删除这条链接吗？\n\n%s\n%s')
                % (r['name'], r['url'])):
            return
        try:
            n = core.remove_from_html(path, [r['url']])
        except Exception as e:
            messagebox.showerror(tr('删除失败'), tr('从 HTML 删除失败：\n%s') % e)
            return
        del self.rows[idx]
        self._populate()
        self.status.set(tr('已从 HTML 删除 %d 条链接。') % n)

    def _mark_alive(self, idx):
        r = self.rows[idx]
        r['verdict'] = 'OK'
        r['code'] = None
        r['err'] = ''
        self._populate()
        self.status.set(tr('已把「%s」标记为正常（仅本次显示，不改收藏夹）。') % r['name'])

    # ---------------- settings ----------------
    def open_settings(self):
        if getattr(self, '_settings_open', False):
            return
        self._settings_open = True
        win = tk.Toplevel(self)
        win.title(tr('设置 - 文件保存位置'))
        win.transient(self)
        win.grab_set()
        win.resizable(False, False)
        frm = ttk.Frame(win, padding=16)
        frm.pack(fill='both', expand=True)
        report_var = tk.StringVar(value=self.report_dir)
        backup_var = tk.StringVar(value=self.backup_dir)

        def browse(var):
            d = filedialog.askdirectory(parent=win, title=tr('选择文件夹'),
                                        initialdir=var.get() or os.path.expanduser('~'))
            if d:
                var.set(d)

        ttk.Label(frm, text=tr('失效报告保存位置：')).grid(row=0, column=0, sticky='w')
        ttk.Entry(frm, textvariable=report_var, width=46).grid(row=0, column=1, padx=8)
        ttk.Button(frm, text=tr('浏览…'),
                   command=lambda: browse(report_var)).grid(row=0, column=2)

        ttk.Label(frm, text=tr('归档/删除的备份位置：')).grid(row=1, column=0, sticky='w', pady=(10, 0))
        ttk.Entry(frm, textvariable=backup_var, width=46).grid(row=1, column=1, padx=8, pady=(10, 0))
        ttk.Button(frm, text=tr('浏览…'),
                   command=lambda: browse(backup_var)).grid(row=1, column=2, pady=(10, 0))

        ttk.Label(frm, text=tr('报告：导出报告时保存到的文件夹。\n备份：归档/删除收藏夹时自动备份收藏夹文件的位置。'),
                  foreground='#78909c').grid(row=2, column=0, columnspan=3, sticky='w', pady=(10, 0))

        lang_row = ttk.Frame(frm)
        lang_row.grid(row=3, column=0, columnspan=3, sticky='w', pady=(10, 0))
        ttk.Label(lang_row, text=tr('语言：')).pack(side='left')
        lang_var = tk.StringVar(value='English' if lang.current_lang() == 'en' else '中文')
        lang_box = ttk.Combobox(lang_row, textvariable=lang_var, values=['中文', 'English'],
                                state='readonly', width=10)
        lang_box.pack(side='left', padx=(4, 0))
        ttk.Label(lang_row, text=tr('保存后应用将自动重启以生效。'),
                  foreground='#78909c').pack(side='left', padx=(10, 0))

        def save():
            rd = report_var.get().strip()
            bd = backup_var.get().strip()
            lg = 'zh' if lang_var.get() != 'English' else 'en'
            changed = lg != lang.current_lang()
            if rd:
                self.report_dir = rd
            if bd:
                self.backup_dir = bd
            settings = {'report_dir': self.report_dir, 'backup_dir': self.backup_dir,
                        'lang': lg}
            save_settings(settings)
            lang.set_lang(lg)
            self._settings_open = False
            win.destroy()
            if changed:
                # restart the app so all UI text re-renders in the new language.
                # Use after() so the restart happens outside the callback stack.
                def _restart():
                    try:
                        self.destroy()
                    except Exception:
                        pass
                    try:
                        import sys as _sys
                        if getattr(_sys, 'frozen', False):
                            os.startfile(_sys.executable)
                        else:
                            subprocess.Popen([_sys.executable, os.path.abspath(__file__)])
                    except Exception:
                        pass
                self.after(150, _restart)
            else:
                self.status.set(tr('设置已保存：报告→%s；备份→%s') % (self.report_dir, self.backup_dir))

        def cancel():
            self._settings_open = False
            win.destroy()

        btns = ttk.Frame(frm)
        btns.grid(row=4, column=0, columnspan=3, sticky='e', pady=(14, 0))
        ttk.Button(btns, text=tr('保存'), command=save).pack(side='left')
        ttk.Button(btns, text=tr('取消'), command=cancel).pack(side='left', padx=8)
        win.protocol('WM_DELETE_WINDOW', cancel)

    def _close(self):
        if self.busy and not messagebox.askokcancel(tr('正在运行'),
                                                    tr('任务还在进行中，确定要退出吗？')):
            return
        self.destroy()


def main():
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    App().mainloop()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        import traceback
        log = os.path.join(os.path.dirname(sys.executable), 'gui_crash.log')
        with open(log, 'w', encoding='utf-8') as f:
            traceback.print_exc(file=f)
        raise
