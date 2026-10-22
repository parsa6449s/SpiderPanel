"""OpenVPN addon for SpiderPanel (FastAPI).

This module deliberately does not import or copy code from vpn-ui. SpiderPanel
is a Python/FastAPI application, while vpn-ui is a separate Go-based fork.

Install beside SpiderPanel's main.py and register build_router(require_auth)
near the end of main.py. See README_FA.md before enabling this in production.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response

LOG = logging.getLogger("SpiderPanel.OpenVPN")
_USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,31}$")
_HOST_RE = re.compile(r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?$")
_MUTATION_LOCK = asyncio.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _username(value: object) -> str:
    name = str(value or "").strip()
    if not _USERNAME_RE.fullmatch(name) or name.lower() in {"server", "ca", "client", "root"}:
        raise HTTPException(status_code=400, detail="نام کاربری نامعتبر است؛ فقط حروف انگلیسی، عدد، _ و - (۲ تا ۳۲ کاراکتر).")
    return name


def _public_host() -> str:
    host = str(os.environ.get("SPIDER_OPENVPN_PUBLIC_HOST", "")).strip()
    if (not host or not _HOST_RE.fullmatch(host) or ".." in host
            or host.startswith(".") or host.lower() in {"localhost", "localhost.localdomain"}):
        return ""
    # Refuse URLs, paths, ports and whitespace; IPv6 literals are intentionally
    # not supported in this first version.
    return host


def _port() -> int:
    raw = str(os.environ.get("SPIDER_OPENVPN_PORT", "1194")).strip()
    try:
        value = int(raw)
    except ValueError:
        return 1194
    return value if 1 <= value <= 65535 else 1194


def _db_path() -> Path:
    return Path(os.environ.get("SPIDER_OPENVPN_DB", "/opt/SpiderPanel/data/openvpn.sqlite3"))


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    conn = sqlite3.connect(str(path), timeout=10)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS openvpn_clients (
            username TEXT PRIMARY KEY COLLATE NOCASE,
            status TEXT NOT NULL CHECK(status IN ('creating','active','error','revoked')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            error_code TEXT
        )
    """)
    conn.commit()
    return conn


def _control_command(*args: str) -> list[str]:
    helper = os.environ.get("SPIDER_OPENVPN_CTL", "/usr/local/sbin/spider-openvpnctl")
    if not helper.startswith("/"):
        raise RuntimeError("OpenVPN helper path must be absolute")
    use_sudo_raw = os.environ.get("SPIDER_OPENVPN_USE_SUDO", "auto").lower()
    use_sudo = use_sudo_raw in {"1", "true", "yes"} or (use_sudo_raw == "auto" and os.geteuid() != 0)
    if use_sudo:
        return ["/usr/bin/sudo", "-n", helper, *args]
    return [helper, *args]


def _run_control(*args: str, timeout: int = 120) -> str:
    """Call only the fixed, validating root helper; never invoke a shell."""
    try:
        result = subprocess.run(
            _control_command(*args),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"},
        )
    except subprocess.TimeoutExpired as exc:
        LOG.error("OpenVPN helper timed out for action=%s", args[0] if args else "unknown")
        raise HTTPException(status_code=504, detail="عملیات OpenVPN بیش از حد طول کشید؛ وضعیت سرویس را بررسی کن.") from exc
    except OSError as exc:
        LOG.error("OpenVPN helper unavailable: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="کنترل‌گر OpenVPN در دسترس نیست؛ نصب و مجوزهای آن را بررسی کن.") from exc

    if result.returncode != 0:
        # Do not return helper stderr: it can contain paths or operational data.
        LOG.warning("OpenVPN helper failed: action=%s rc=%s", args[0] if args else "unknown", result.returncode)
        raise HTTPException(status_code=502, detail="عملیات OpenVPN ناموفق بود؛ گزارش سرویس روی سرور را بررسی کن.")
    return result.stdout.strip()


def _same_origin(request: Request) -> None:
    """Basic same-origin gate for browser mutation requests (cookie sessions)."""
    host = str(request.headers.get("host") or "").lower()
    origin = str(request.headers.get("origin") or "").strip()
    referer = str(request.headers.get("referer") or "").strip()
    candidate = origin or referer
    if not host or not candidate:
        raise HTTPException(status_code=403, detail="درخواست باید از صفحهٔ خود پنل ارسال شود.")
    try:
        parsed = urlsplit(candidate)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="مبدأ درخواست نامعتبر است.") from exc
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != host:
        raise HTTPException(status_code=403, detail="مبدأ درخواست با پنل مطابقت ندارد.")


def build_router(require_auth) -> APIRouter:
    """Return a router using SpiderPanel's existing cookie-session dependency."""
    router = APIRouter()
    page_file = Path(__file__).with_name("openvpn.html")

    @router.get("/openvpn")
    async def openvpn_page(_=Depends(require_auth)):
        if not page_file.is_file():
            raise HTTPException(status_code=503, detail="فایل رابط OpenVPN نصب نشده است.")
        return FileResponse(
            page_file,
            media_type="text/html; charset=utf-8",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    @router.get("/api/openvpn/status")
    async def openvpn_status(_=Depends(require_auth)):
        try:
            state = await asyncio.to_thread(_run_control, "status", timeout=10)
        except HTTPException as exc:
            return {
                "ok": False,
                "service": "unavailable",
                "public_host_configured": bool(_public_host()),
                "port": _port(),
                "protocol": "udp",
                "message": str(exc.detail),
            }
        return {
            "ok": True,
            "service": state if state in {"active", "inactive", "not-installed"} else "unknown",
            "public_host_configured": bool(_public_host()),
            "port": _port(),
            "protocol": "udp",
        }

    @router.get("/api/openvpn/clients")
    async def list_clients(_=Depends(require_auth)):
        with _connect() as conn:
            rows = conn.execute(
                "SELECT username,status,created_at,updated_at FROM openvpn_clients ORDER BY created_at DESC"
            ).fetchall()
        return {"clients": [dict(row) for row in rows]}

    @router.post("/api/openvpn/clients")
    async def create_client(request: Request, _=Depends(require_auth)):
        _same_origin(request)
        if not _public_host():
            raise HTTPException(status_code=503, detail="ابتدا SPIDER_OPENVPN_PUBLIC_HOST را در تنظیمات محیطی پنل تنظیم کن.")
        try:
            body = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=400, detail="بدنهٔ درخواست JSON معتبر نیست.") from exc
        name = _username((body or {}).get("username"))

        async with _MUTATION_LOCK:
            with _connect() as conn:
                existing = conn.execute("SELECT status FROM openvpn_clients WHERE username=?", (name,)).fetchone()
                if existing:
                    raise HTTPException(status_code=409, detail="این نام قبلاً ثبت شده است؛ برای جلوگیری از استفادهٔ مجدد از گواهی، نام دیگری انتخاب کن.")
                now = _now()
                conn.execute(
                    "INSERT INTO openvpn_clients(username,status,created_at,updated_at,error_code) VALUES(?,?,?,?,NULL)",
                    (name, "creating", now, now),
                )
                conn.commit()
            try:
                await asyncio.to_thread(_run_control, "create", name, timeout=180)
            except HTTPException:
                with _connect() as conn:
                    conn.execute("UPDATE openvpn_clients SET status='error',updated_at=?,error_code='create_failed' WHERE username=?", (_now(), name))
                    conn.commit()
                raise
            with _connect() as conn:
                conn.execute("UPDATE openvpn_clients SET status='active',updated_at=?,error_code=NULL WHERE username=?", (_now(), name))
                conn.commit()
        LOG.info("OpenVPN client created: username=%s", name)
        return {"ok": True, "username": name, "status": "active"}

    @router.get("/api/openvpn/clients/{username}/download")
    async def download_client(username: str, request: Request, _=Depends(require_auth)):
        require_https = os.environ.get("SPIDER_OPENVPN_REQUIRE_HTTPS", "1").lower() not in {"0", "false", "no"}
        if require_https and request.url.scheme.lower() != "https":
            raise HTTPException(status_code=403, detail="برای دانلود فایل حاوی کلید خصوصی، ابتدا HTTPS معتبر روی پنل فعال کن.")
        name = _username(username)
        with _connect() as conn:
            row = conn.execute("SELECT status FROM openvpn_clients WHERE username=?", (name,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="کاربر پیدا نشد.")
        if row["status"] != "active":
            raise HTTPException(status_code=410, detail="این گواهی فعال نیست و فایل آن قابل دریافت نیست.")
        host = _public_host()
        if not host:
            raise HTTPException(status_code=503, detail="آدرس عمومی OpenVPN تنظیم نشده است.")
        profile = await asyncio.to_thread(_run_control, "profile", name, host, str(_port()), "udp", timeout=20)
        if not profile.startswith("client\n"):
            LOG.error("OpenVPN helper returned a malformed profile for %s", name)
            raise HTTPException(status_code=502, detail="فایل کانفیگ تولید نشد.")
        return Response(
            content=profile + "\n",
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{name}.ovpn"',
                "Cache-Control": "no-store, no-cache, must-revalidate, private",
                "Pragma": "no-cache",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @router.delete("/api/openvpn/clients/{username}")
    async def revoke_client(username: str, request: Request, _=Depends(require_auth)):
        _same_origin(request)
        name = _username(username)
        async with _MUTATION_LOCK:
            with _connect() as conn:
                row = conn.execute("SELECT status FROM openvpn_clients WHERE username=?", (name,)).fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="کاربر پیدا نشد.")
                if row["status"] == "revoked":
                    return {"ok": True, "username": name, "status": "revoked"}
                if row["status"] != "active":
                    raise HTTPException(status_code=409, detail="وضعیت کاربر برای لغو گواهی مناسب نیست.")
            try:
                await asyncio.to_thread(_run_control, "revoke", name, timeout=180)
            except HTTPException:
                # Do not leave the profile downloadable after a revoke attempt
                # that may already have changed PKI/CRL state.
                with _connect() as conn:
                    conn.execute("UPDATE openvpn_clients SET status='error',updated_at=?,error_code='revoke_failed' WHERE username=?", (_now(), name))
                    conn.commit()
                raise
            with _connect() as conn:
                conn.execute("UPDATE openvpn_clients SET status='revoked',updated_at=?,error_code=NULL WHERE username=?", (_now(), name))
                conn.commit()
        LOG.warning("OpenVPN client revoked: username=%s", name)
        return {"ok": True, "username": name, "status": "revoked"}

    return router
