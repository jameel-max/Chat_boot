import json
import os
import re
import secrets
import sys
import threading
import time
from http.cookies import CookieError, SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_ROOT = Path(__file__).resolve().parent
STATIC_ROOT = DASHBOARD_ROOT / "static"
sys.path.insert(0, str(WORKSPACE_ROOT))

from database import Database  # noqa: E402
from store import DashboardStore  # noqa: E402

DEFAULT_ADMIN_EMAIL = "mstfyaysht384@gmail.com"
ADMIN_COOKIE = "faheem_admin_session"
ADMIN_SESSION_SECONDS = 12 * 60 * 60
REMEMBERED_ADMIN_SESSION_SECONDS = 7 * 24 * 60 * 60
MAX_BODY_BYTES = 64 * 1024
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_MAX_ATTEMPTS = 5

store = None
_started_at = time.monotonic()
_login_attempts = {}
_login_attempts_lock = threading.Lock()
_summary_cache = {"expires_at": 0.0, "value": None}
_summary_cache_lock = threading.Lock()


def load_local_env():
    env_path = WORKSPACE_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip("\"'")
        if name and name not in os.environ:
            os.environ[name] = value


def _login_is_limited(address):
    now = time.monotonic()
    with _login_attempts_lock:
        attempts = _login_attempts.get(address)
        if attempts is None or now - attempts[0] >= LOGIN_WINDOW_SECONDS:
            _login_attempts[address] = [now, 1]
            return False
        attempts[1] += 1
        if len(_login_attempts) > 2048:
            for key, value in list(_login_attempts.items()):
                if now - value[0] >= LOGIN_WINDOW_SECONDS:
                    _login_attempts.pop(key, None)
        return attempts[1] > LOGIN_MAX_ATTEMPTS


def _clear_login_attempts(address):
    with _login_attempts_lock:
        _login_attempts.pop(address, None)


def _cached_summary(dashboard_store):
    now = time.monotonic()
    with _summary_cache_lock:
        if _summary_cache["value"] is None or now >= _summary_cache["expires_at"]:
            _summary_cache["value"] = dashboard_store.dashboard_summary()
            _summary_cache["expires_at"] = now + 45
        return dict(_summary_cache["value"])


def _invalidate_summary():
    with _summary_cache_lock:
        _summary_cache["expires_at"] = 0.0
        _summary_cache["value"] = None


class DashboardHandler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_ROOT), **kwargs)

    @property
    def database(self):
        return store.database

    @property
    def dashboard_store(self):
        return store

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("X-Frame-Options", "DENY")
        super().end_headers()

    def log_message(self, format, *args):
        path = urlsplit(self.path).path
        print(f"{self.client_address[0]} - {args[0]} {path}")

    def send_json(self, payload, status=200, headers=()):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_json({"error": "حجم الطلب غير صالح."}, 400)
            return None
        if length < 1 or length > MAX_BODY_BYTES:
            self.send_json({"error": "حجم الطلب غير صالح."}, 413)
            return None
        try:
            payload = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.send_json({"error": "تعذّرت قراءة بيانات الطلب."}, 400)
            return None
        if not isinstance(payload, dict):
            self.send_json({"error": "صيغة الطلب غير صالحة."}, 400)
            return None
        return payload

    def session_token(self):
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get("Cookie", ""))
        except CookieError:
            return ""
        token = cookies.get(ADMIN_COOKIE)
        return token.value if token else ""

    def current_user(self):
        return self.database.get_session_user(self.session_token())

    def is_primary_admin(self, user):
        primary_email = os.environ.get("ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL).strip().casefold()
        return bool(primary_email) and user["email"].casefold() == primary_email

    def require_admin(self):
        user = self.current_user()
        if not user:
            self.send_json({"error": "سجّل الدخول للمتابعة."}, 401)
            return None
        if not self.dashboard_store.is_admin(user):
            self.send_json({"error": "ليست لديك صلاحية لوحة التحكم."}, 403)
            return None
        return user

    def same_origin(self):
        origin = self.headers.get("Origin")
        if not origin:
            return True
        parsed = urlsplit(origin)
        host = self.headers.get("Host", "").casefold()
        return parsed.scheme in {"http", "https"} and parsed.netloc.casefold() == host

    def _cookie(self, token, max_age):
        value = f"{ADMIN_COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={max_age}"
        forwarded_proto = self.headers.get("X-Forwarded-Proto", "").split(",", 1)[0].strip().casefold()
        secure = os.environ.get("COOKIE_SECURE", "false").strip().casefold() == "true"
        if secure or forwarded_proto == "https":
            value += "; Secure"
        return value

    def do_GET(self):
        parsed = urlsplit(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path == "/api/me":
            user = self.require_admin()
            if user:
                self.send_json({
                    "user": user,
                    "isAdmin": True,
                    "isPrimaryAdmin": self.is_primary_admin(user),
                })
            return
        if not path.startswith("/api/"):
            self.path = "/index.html" if path == "/" else self.path
            return super().do_GET()

        user = self.require_admin()
        if not user:
            return
        params = parse_qs(parsed.query)
        if path == "/api/admin/dashboard":
            page = self.dashboard_store.list_users(
                page=self._param(params, "page", "1"),
                page_size=self._param(params, "pageSize", "25"),
                query=self._param(params, "q", ""),
                role=self._param(params, "role", "all"),
                sort=self._param(params, "sort", "created_desc"),
            )
            summary = _cached_summary(self.dashboard_store)
            self.send_json({
                "pageViews": summary["page_views"],
                "uniqueVisitors": summary["unique_visitors"],
                "users": page["users"],
                "total": page["total"],
                "page": page["page"],
                "pageSize": page["pageSize"],
                "pages": page["pages"],
                "counts": {
                    "users": summary["users"] - summary["admins"],
                    "admins": summary["admins"],
                },
            })
            return
        if path == "/api/admin/statistics":
            summary = _cached_summary(self.dashboard_store)
            self.send_json({
                "pageViews": summary["page_views"],
                "uniqueVisitors": summary["unique_visitors"],
                "newSupport": summary["new_support"],
            })
            return
        if path == "/api/admin/analytics":
            self.send_json(_cached_summary(self.dashboard_store))
            return
        if path == "/api/admin/support-messages":
            self.send_json(self.dashboard_store.support_messages(
                page=self._param(params, "page", "1"),
                page_size=self._param(params, "pageSize", "25"),
                query=self._param(params, "q", ""),
                status=self._param(params, "status", "all"),
                category=self._param(params, "category", "all"),
            ))
            return
        if path == "/api/admin/audit-logs":
            self.send_json(self.dashboard_store.audit_logs(
                page=self._param(params, "page", "1"),
                page_size=self._param(params, "pageSize", "25"),
            ))
            return
        if path == "/api/admin/announcements":
            self.send_json({"announcements": self.dashboard_store.announcements()})
            return
        if path == "/api/admin/system-health":
            self.send_json(self.dashboard_store.system_health(_started_at))
            return
        if path == "/api/admin/users":
            self.send_json(self.dashboard_store.list_users(
                page=self._param(params, "page", "1"),
                page_size=self._param(params, "pageSize", "25"),
                query=self._param(params, "q", ""),
                role=self._param(params, "role", "all"),
                sort=self._param(params, "sort", "created_desc"),
            ))
            return
        match = re.fullmatch(r"/api/admin/users/([a-f0-9]{32})", path)
        if match:
            detail = self.dashboard_store.user_detail(match.group(1))
            if not detail:
                self.send_json({"error": "المستخدم غير موجود."}, 404)
            else:
                self.send_json({"user": detail})
            return
        self.send_json({"error": "المسار غير موجود."}, 404)

    @staticmethod
    def _param(params, name, default):
        return params.get(name, [default])[0]

    def do_POST(self):
        path = urlsplit(self.path).path.rstrip("/") or "/"
        if path in {"/api/auth/login", "/api/admin/login"}:
            self.login()
            return
        if path in {"/api/logout", "/api/admin/logout"}:
            user = self.current_user()
            if user:
                self.dashboard_store.log_action(user, "admin_logout")
            self.database.delete_session(self.session_token())
            self.send_response(204)
            self.send_header("Set-Cookie", self._cookie("", 0))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        user = self.require_admin()
        if not user:
            return
        if not self.same_origin():
            self.send_json({"error": "رفض الطلب لعدم تطابق المصدر."}, 403)
            return
        payload = self.read_json()
        if payload is None:
            return
        role_match = re.fullmatch(r"/api/admin/users/([a-f0-9]{32})/admin", path)
        if role_match:
            enabled = payload.get("isAdmin")
            if not isinstance(enabled, bool):
                self.send_json({"error": "قيمة الصلاحية غير صالحة."}, 400)
                return
            result = self.dashboard_store.set_admin_role(user, role_match.group(1), enabled)
            if result != "updated":
                self._send_admin_action_error(result)
                return
            _invalidate_summary()
            self.send_json({"ok": True, "isAdmin": enabled})
            return
        password_match = re.fullmatch(r"/api/admin/users/([a-f0-9]{32})/password", path)
        if password_match:
            password = payload.get("newPassword")
            if not isinstance(password, str) or len(password) < 10 or len(password) > 128:
                self.send_json({"error": "كلمة المرور يجب أن تكون بين 10 و128 حرفًا."}, 400)
                return
            result = self.dashboard_store.set_user_password(user, password_match.group(1), password)
            if result != "updated":
                self._send_admin_action_error(result)
                return
            self.send_json({"ok": True})
            return
        if path == "/api/admin/announcements":
            title, body = payload.get("title"), payload.get("body")
            published = payload.get("isPublished", False)
            if not isinstance(title, str) or not isinstance(body, str) or not isinstance(published, bool):
                self.send_json({"error": "بيانات الإعلان غير صالحة."}, 400)
                return
            result = self.dashboard_store.save_announcement(user, title, body, published)
            if result == "invalid":
                self.send_json({"error": "العنوان أو نص الإعلان غير صالح."}, 400)
                return
            self.send_json({"ok": True, "id": result}, 201)
            return
        self.send_json({"error": "المسار غير موجود."}, 404)

    def do_PATCH(self):
        user = self.require_admin()
        if not user:
            return
        if not self.same_origin():
            self.send_json({"error": "رفض الطلب لعدم تطابق المصدر."}, 403)
            return
        payload = self.read_json()
        if payload is None:
            return
        path = urlsplit(self.path).path.rstrip("/")
        support_match = re.fullmatch(r"/api/admin/support-messages/(\d+)", path)
        if support_match:
            result = self.dashboard_store.set_support_status(
                user, int(support_match.group(1)), payload.get("status")
            )
            if result == "updated":
                _invalidate_summary()
                self.send_json({"ok": True, "status": payload["status"]})
            elif result == "not_found":
                self.send_json({"error": "رسالة الدعم غير موجودة."}, 404)
            else:
                self.send_json({"error": "حالة الرسالة غير صالحة."}, 400)
            return
        announcement_match = re.fullmatch(r"/api/admin/announcements/(\d+)", path)
        if announcement_match:
            title, body = payload.get("title"), payload.get("body")
            published = payload.get("isPublished")
            if not isinstance(title, str) or not isinstance(body, str) or not isinstance(published, bool):
                self.send_json({"error": "بيانات الإعلان غير صالحة."}, 400)
                return
            result = self.dashboard_store.save_announcement(
                user, title, body, published, int(announcement_match.group(1))
            )
            if result == "not_found":
                self.send_json({"error": "الإعلان غير موجود."}, 404)
            elif result == "invalid":
                self.send_json({"error": "العنوان أو نص الإعلان غير صالح."}, 400)
            else:
                self.send_json({"ok": True, "id": result})
            return
        self.send_json({"error": "المسار غير موجود."}, 404)

    def do_DELETE(self):
        user = self.require_admin()
        if not user:
            return
        if not self.same_origin():
            self.send_json({"error": "رفض الطلب لعدم تطابق المصدر."}, 403)
            return
        path = urlsplit(self.path).path.rstrip("/")
        user_match = re.fullmatch(r"/api/admin/users/([a-f0-9]{32})", path)
        if user_match:
            result = self.dashboard_store.delete_user(user, user_match.group(1))
            if result != "deleted":
                self._send_admin_action_error(result)
                return
            _invalidate_summary()
            self.send_response(204)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        announcement_match = re.fullmatch(r"/api/admin/announcements/(\d+)", path)
        if announcement_match:
            if not self.dashboard_store.delete_announcement(user, int(announcement_match.group(1))):
                self.send_json({"error": "الإعلان غير موجود."}, 404)
            else:
                self.send_response(204)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
            return
        self.send_json({"error": "المسار غير موجود."}, 404)

    def _send_admin_action_error(self, result):
        messages = {
            "not_found": (404, "المستخدم غير موجود."),
            "self": (400, "لا يمكنك تنفيذ هذا الإجراء على حسابك."),
            "primary_admin": (400, "حساب الأدمن الأساسي محمي."),
            "target_admin": (403, "لا يمكن لهذا الأدمن إدارة حساب أدمن آخر."),
        }
        status, message = messages.get(result, (400, "تعذّر تنفيذ الإجراء."))
        self.send_json({"error": message}, status)

    def login(self):
        address = self.client_address[0]
        if _login_is_limited(address):
            self.send_json({"error": "محاولات كثيرة. حاول بعد قليل."}, 429)
            return
        payload = self.read_json()
        if payload is None:
            return
        email, password = payload.get("email"), payload.get("password")
        remember = payload.get("remember", True)
        if (
            not isinstance(email, str)
            or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email.strip())
            or not isinstance(password, str)
            or len(password) > 128
            or not isinstance(remember, bool)
        ):
            self.send_json({"error": "البريد الإلكتروني أو كلمة المرور غير صحيحة."}, 401)
            return
        email = email.strip().casefold()
        account = self.database.login_user(email, password)
        if not account:
            self.send_json({"error": "البريد الإلكتروني أو كلمة المرور غير صحيحة."}, 401)
            return
        if not self.dashboard_store.is_admin(account):
            self.send_json({"error": "هذا الحساب لا يملك صلاحية الأدمن."}, 403)
            return
        _clear_login_attempts(address)
        lifetime = REMEMBERED_ADMIN_SESSION_SECONDS if remember else ADMIN_SESSION_SECONDS
        token = self.database.create_session(account["id"], lifetime)
        self.dashboard_store.log_action(account, "admin_login")
        self.send_json(
            {"user": account, "isAdmin": True, "isPrimaryAdmin": self.is_primary_admin(account)},
            headers=[("Set-Cookie", self._cookie(token, lifetime))],
        )

    def _cookie(self, token, max_age):
        value = f"{ADMIN_COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={max_age}"
        forwarded = self.headers.get("X-Forwarded-Proto", "").split(",", 1)[0].strip().casefold()
        if os.environ.get("COOKIE_SECURE", "false").strip().casefold() == "true" or forwarded == "https":
            value += "; Secure"
        return value

    def session_token(self):
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get("Cookie", ""))
        except CookieError:
            return ""
        cookie = cookies.get(ADMIN_COOKIE)
        return cookie.value if cookie else ""

    def current_user(self):
        return self.database.get_session_user(self.session_token())

    def is_primary_admin(self, user):
        return user["email"].casefold() == os.environ.get("ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL).strip().casefold()


def main():
    global store
    load_local_env()
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url.startswith(("postgres://", "postgresql://")):
        raise SystemExit("Set DATABASE_URL to the shared Faheem PostgreSQL database.")
    database = Database(database_url, initialize_schema=False)
    store = DashboardStore(database, os.environ.get("ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL))
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    httpd = ThreadingHTTPServer((host, port), DashboardHandler)
    print(f"Faheem Admin Dashboard listening on {host}:{port}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
