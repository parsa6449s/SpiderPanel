#!/usr/bin/env python3
"""Safely add the OpenVPN API router import and a sidebar link to SpiderPanel.
Creates timestamped backups, refuses unexpected main.py layout, and is idempotent.
"""
from __future__ import annotations
import argparse
import datetime as dt
import re
import shutil
import sys
from pathlib import Path

ROUTE_MARKER = "# SPIDERPANEL_OPENVPN_ADDON_START"
ROUTE_SNIPPET = '''\n\n# SPIDERPANEL_OPENVPN_ADDON_START\nfrom openvpn_addon import build_router as _build_openvpn_router\napp.include_router(_build_openvpn_router(require_auth))\n# SPIDERPANEL_OPENVPN_ADDON_END\n'''
NAV_MARKER = 'id="nav-openvpn-addon"'
NAV_SNIPPET = '''      <div class="nav-item" id="nav-openvpn-addon" onclick="window.location.href='/openvpn'" role="link" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();window.location.href='/openvpn'}">\n        <span class="nav-ic"><span class="material-symbols-outlined" style="font-size:18px">vpn_key</span></span>\n        <span>OpenVPN</span>\n      </div>\n'''
NAV_ANCHOR = '<div class="nav-item" onclick="switchTab(\'users\',this)">'


def backup(path: Path) -> Path:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    target = path.with_name(path.name + ".openvpn-backup-" + stamp)
    shutil.copy2(path, target)
    return target


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--app-dir", default="/opt/SpiderPanel", help="SpiderPanel app directory")
    args = p.parse_args()
    app = Path(args.app_dir).resolve()
    main_py = app / "main.py"
    addon = app / "openvpn_addon.py"
    html = app / "openvpn.html"
    index = app / "static" / "index.html"

    for required in (main_py, addon, html):
        if not required.is_file():
            print(f"ERROR: فایل لازم پیدا نشد: {required}", file=sys.stderr)
            return 2

    source = main_py.read_text(encoding="utf-8")
    if ROUTE_MARKER not in source:
        if not re.search(r"^async def require_auth\(request: Request\):", source, re.M):
            print("ERROR: ساختار احراز هویت نسخهٔ فعلی تشخیص داده نشد؛ main.py تغییر نکرد.", file=sys.stderr)
            return 3
        if not re.search(r"^app\s*=\s*FastAPI\(", source, re.M):
            print("ERROR: نمونهٔ FastAPI تشخیص داده نشد؛ main.py تغییر نکرد.", file=sys.stderr)
            return 3
        b = backup(main_py)
        with main_py.open("a", encoding="utf-8") as f:
            f.write(ROUTE_SNIPPET)
        print(f"Router added to main.py. Backup: {b}")
    else:
        print("Router already present; main.py unchanged.")

    if not index.is_file():
        print(f"WARNING: {index} پیدا نشد؛ صفحه در مسیر /openvpn در دسترس خواهد بود اما لینک منو اضافه نشد.")
        return 0
    ui = index.read_text(encoding="utf-8")
    if NAV_MARKER in ui:
        print("Sidebar link already present; index.html unchanged.")
        return 0
    if NAV_ANCHOR not in ui:
        print("WARNING: محل منوی کاربران با نسخهٔ فعلی مطابقت نداشت؛ لینک منو اضافه نشد.")
        return 0
    b = backup(index)
    ui = ui.replace(NAV_ANCHOR, NAV_SNIPPET + NAV_ANCHOR, 1)
    index.write_text(ui, encoding="utf-8")
    print(f"Sidebar link added. Backup: {b}")
    print("نکته: پس از به‌روزرسانی SpiderPanel ممکن است لازم باشد patch منو را دوباره اجرا کنی.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
