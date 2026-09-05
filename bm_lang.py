# -*- coding: utf-8 -*-
# Minimal i18n for the bookmark checker GUI (zh-CN <-> en).
# tr() looks up a Chinese source string in the EN table; if not found,
# returns the original text (so the UI never breaks).
import os
import sys

_LANG = None  # 'zh' or 'en', resolved lazily

EN = {
    # ---- main window ----
    '收藏夹链接检测': 'Bookmark Link Checker',
    '浏览器：': 'Browser:',
    '范围：': 'Scope:',
    '其他收藏夹': 'Other bookmarks',
    '全部收藏夹': 'All bookmarks',
    '开始检测': 'Start Check',
    '停止': 'Stop',
    '只看失效': 'Dead only',
    '导入 HTML 收藏夹…': 'Import HTML Bookmarks...',
    '待检测': 'Ready',
    '状态': 'Status',
    '名称': 'Name',
    '所在文件夹': 'Folder',
    '网址': 'URL',
    '复检选中': 'Re-check Selected',
    '导出失效报告': 'Export Report',
    '归档失效链接…': 'Archive Dead Links...',
    '设置…': 'Settings...',
    '双击一行打开网址｜右键更多操作': 'Double-click to open | Right-click for more',

    # ---- status bar / dynamic text ----
    '就绪。点“开始检测”先跑一遍。': 'Ready. Click "Start Check" to begin.',
    '已停止': 'Stopped',
    '完成': 'Done',
    '正在停止…已发出的网络请求要等几秒超时才断开，稍等一下。':
        'Stopping... already-sent requests take a few seconds to time out.',
    '已停止：检测了 %d 条，跳过 %d 条。可再点“开始检测”重查，或选中几条用“复检选中”。':
        'Stopped: checked %d, skipped %d. Click "Start Check" to rerun, or re-check selected rows.',
    '检测完成：确定失效 %d 条，疑似问题 %d 条，正常 %d 条':
        'Done: %d dead, %d suspicious, %d OK',
    '复检%s：更新了 %d 条。': 'Re-check %s: updated %d.',
    '已归档 %d 条，备份：%s': 'Archived %d, backup: %s',
    '出错': 'Error',
    '已切换来源。点“开始检测”载入新的收藏夹。':
        'Source changed. Click "Start Check" to load bookmarks.',
    '正在检测 %d 条链接…': 'Checking %d links...',
    '已从 HTML 导入 %d 条链接（%s）。点“开始检测”即可检测。':
        'Imported %d links from HTML (%s). Click "Start Check".',
    '%d 条': '%d links',
    '复检选中的 %d 条…': 'Re-checking %d selected...',
    '报告已保存：%s': 'Report saved: %s',
    '正在归档并写入收藏夹…': 'Archiving into bookmarks...',
    '已删除 %d 条，备份：%s': 'Deleted %d, backup: %s',
    '已从 HTML 删除 %d 条链接。': 'Deleted %d links from HTML.',
    '已把「%s」标记为正常（仅本次显示，不改收藏夹）。':
        'Marked "%s" as OK (display only; bookmarks unchanged).',
    '设置已保存：报告→%s；备份→%s': 'Settings saved: report->%s; backup->%s',

    # ---- verdict display ----
    '能打开': 'OK',
    '能打开（网站拦截自动访问，链接正常）': 'OK (site blocks scripts, link is fine)',
    '已归档': 'Archived',
    '检测中…': 'Checking...',
    '未检测': 'Not checked',
    '确定失效（页面404）': 'Dead (404)',
    '确定失效（域名不存在）': 'Dead (domain not found)',
    '确定失效（连接不上）': 'Dead (connection failed)',
    '确定失效（证书打不开）': 'Dead (certificate)',
    '超时，可能反爬或网络快，网页可能能开': 'Timeout - may open in browser',
    '服务器报错，可能临时故障': 'Server error - may be temporary',
    '证书异常（网站能开）': 'Cert issue (site loads)',
    '连接不上，可能是反爬或网络，建议网页重开确认':
        'Cannot connect - may be anti-bot/network, verify in browser',
    '证书问题打不开（可能仅网页能开）': 'Cert problem (may open in browser)',
    '超时，可能反爬或网络快徒，网页可能能开': 'Timeout - may open in browser',
    '超时，可能反爬或网络快，网页可能能开': 'Timeout - may open in browser',

    # ---- messageboxes ----
    '读取收藏夹失败': 'Failed to read bookmarks',
    '找不到收藏夹文件或读取失败：\n%s': 'Bookmark file not found or unreadable:\n%s',
    '没有链接': 'No links',
    '这个范围内没有要检测的网址链接。': 'No links to check in this scope.',
    '提示': 'Info',
    '先在列表里选中要复检的行（按住 Ctrl 可多选）。':
        'Select rows in the list first (hold Ctrl for multiple).',
    '没有失效链接': 'No dead links',
    '当前结果里没有失效或疑似问题的链接。': 'No dead or suspicious links in the results.',
    '报告已导出': 'Report exported',
    '已保存到：\n%s\n\n现在打开所在文件夹吗？': 'Saved to:\n%s\n\nOpen the folder now?',
    '无法归档': 'Cannot archive',
    '失效链接都来自 HTML 导入（不在浏览器收藏夹里），不能归档。\n可导出失效报告自己核对。':
        'Dead links all come from the imported HTML file (not in the browser bookmarks), '
        'so they cannot be archived. Export a report to review instead.',
    '没有可归档的链接': 'Nothing to archive',
    '列表里没有“确定失效”的链接。': 'No confirmed-dead links in the list.',
    '（另有 %d 条来自 HTML 导入的失效项不能归档，已跳过）':
        ' (%d dead links from HTML import skipped - cannot archive)',
    '确认归档': 'Confirm archive',
    '将把 %d 条“确定失效”的链接移动到收藏夹的“失效链接归档”文件夹。\n'
    '（超时、服务器报错等疑似问题不动；网址不删除，只是换位置）%s\n\n继续吗？':
        'Move %d confirmed-dead links to the "dead links archive" folder in your bookmarks?\n'
        ' (suspicious links stay; nothing is deleted, just moved)%s\n\nContinue?',
    '%s 正在运行': '%s is running',
    '%s 正在运行，退出前它可能把改动覆盖回去。\n建议先完全退出 %s 再归档。\n\n仍要现在继续吗？':
        '%s is running and may overwrite changes on exit.\n'
        'Please fully quit %s first. Continue anyway?',
    '正在归档并写入收藏夹…': 'Archiving into bookmarks...',
    '归档失败（收藏夹已先自动备份，可手动还原）：\n%s':
        'Archive failed (bookmarks were backed up first, can restore manually):\n%s',
    '归档完成': 'Archive complete',
    '已把 %d 条失效链接移入收藏夹的“失效链接归档”文件夹。\n改动前自动备份在：\n%s\n\n现在打开备份文件夹吗？':
        'Moved %d dead links into the "dead links archive" folder.\nBackup saved at:\n%s\n\nOpen the backup folder now?',
    '导入失败': 'Import failed',
    '解析文件出错：\n%s': 'Failed to parse file:\n%s',
    '这个 HTML 文件里没有找到网址链接。': 'No links found in this HTML file.',
    '复检出错：%s': 'Re-check error: %s',
    '检测出错：%s': 'Check error: %s',
    '确认删除': 'Confirm delete',
    '确定要从浏览器收藏夹删除这条链接吗？\n\n%s\n%s':
        'Delete this link from the browser bookmarks?\n\n%s\n%s',
    '%s 正在运行，退出前它可能把改动覆盖回去。\n建议先完全退出 %s 再删除。\n\n仍要现在继续吗？':
        '%s is running and may overwrite changes on exit.\n'
        'Please fully quit %s first. Delete anyway?',
    '删除失败': 'Delete failed',
    '删除失败（收藏夹已自动备份）：\n%s': 'Delete failed (bookmarks were backed up):\n%s',
    '找不到导入的 HTML 文件路径。': 'Imported HTML file path not found.',
    '确定要从导入的 HTML 文件删除这条链接吗？\n\n%s\n%s':
        'Delete this link from the imported HTML file?\n\n%s\n%s',
    '从 HTML 删除失败：\n%s': 'Failed to delete from HTML:\n%s',
    '正在运行': 'Running',
    '任务还在进行中，确定要退出吗？': 'A task is still running. Quit anyway?',
    '选择导出的收藏夹 HTML 文件': 'Select exported bookmarks HTML file',
    'HTML 文件': 'HTML files',
    '所有文件': 'All files',

    # ---- settings dialog ----
    '设置 - 文件保存位置': 'Settings - Save Locations',
    '失效报告保存位置：': 'Report folder:',
    '归档/删除的备份位置：': 'Backup folder:',
    '浏览…': 'Browse...',
    '报告：导出报告时保存到的文件夹。\n备份：归档/删除收藏夹时自动备份收藏夹文件的位置。':
        'Report: where exported reports are saved.\nBackup: where bookmark backups go '
        'when archiving/deleting.',
    '保存': 'Save',
    '取消': 'Cancel',
    '语言：': 'Language:',
    '中文': '中文',
    'English': 'English',
    '语言修改后需重启应用生效。': 'Language change takes effect after restarting the app.',
}


def current_lang():
    global _LANG
    if _LANG is not None:
        return _LANG
    try:
        if getattr(sys, 'frozen', False):
            base = os.path.dirname(sys.executable)
        else:
            base = os.path.dirname(os.path.abspath(__file__))
        s = os.path.join(base, 'settings.json')
        import json
        with open(s, encoding='utf-8') as f:
            d = json.load(f)
        _LANG = d.get('lang', 'zh')
    except Exception:
        _LANG = 'zh'
    return _LANG


def set_lang(lang):
    global _LANG
    _LANG = lang


def tr(text):
    if current_lang() == 'en':
        return EN.get(text, text)
    return text
