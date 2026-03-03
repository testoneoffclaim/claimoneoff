import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).parent
STATIC_DIR = ROOT / "static"
TEMPLATE_FILE = ROOT / "templates" / "index.html"
PORT = int(os.getenv("PORT", "8000"))
SESSION_TTL_HOURS = int(os.getenv("SESSION_TTL_HOURS", "12"))
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
PBKDF2_ITERATIONS = int(os.getenv("PBKDF2_ITERATIONS", "260000"))

_lock = threading.Lock()


def utcnow():
    return datetime.now(timezone.utc)


def db_path() -> str:
    return os.getenv("DB_PATH", str(ROOT / "data.db"))


def db_conn():
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _pbkdf2(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = _pbkdf2(password, salt)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, iterations, b64salt, b64hash = encoded.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(b64salt)
        expected = base64.b64decode(b64hash)
        got = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(got, expected)
    except Exception:
        return False


def init_db():
    conn = db_conn()
    cur = conn.cursor()
    cur.executescript(
        """
        PRAGMA journal_mode = WAL;
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin', 'client')),
            client_name TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            client_name TEXT NOT NULL,
            type TEXT NOT NULL,
            priority TEXT NOT NULL,
            order_ref TEXT NOT NULL,
            status TEXT NOT NULL,
            description TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_scope TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_hash TEXT UNIQUE NOT NULL,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_sessions_token_hash ON sessions(token_hash);
        CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at);
        """
    )

    # Migration from legacy schema (plain-text `password`) to `password_hash`.
    user_columns = {row["name"] for row in cur.execute("PRAGMA table_info(users)").fetchall()}
    if "password_hash" not in user_columns:
        cur.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
    if "created_at" not in user_columns:
        cur.execute("ALTER TABLE users ADD COLUMN created_at TEXT")

    now = utcnow().isoformat()
    has_legacy_password = "password" in user_columns
    if has_legacy_password:
        legacy_rows = cur.execute("SELECT id, password, password_hash, created_at FROM users").fetchall()
        for row in legacy_rows:
            if not row["password_hash"]:
                cur.execute(
                    "UPDATE users SET password_hash = ?, created_at = COALESCE(created_at, ?) WHERE id = ?",
                    (hash_password(row["password"] or "ChangeMe123!"), now, row["id"]),
                )
            elif not row["created_at"]:
                cur.execute("UPDATE users SET created_at = ? WHERE id = ?", (now, row["id"]))
    else:
        cur.execute("UPDATE users SET created_at = COALESCE(created_at, ?) WHERE created_at IS NULL OR created_at = ''", (now,))

    count = cur.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    if count == 0:
        now = utcnow().isoformat()
        demo_users = [
            ("admin", "Admin2026!", "admin", "Direction logistique"),
            ("client_mode_paris", "Paris#123", "client", "Mode Paris"),
            ("client_beaute_lyon", "Lyon#123", "client", "Beauté Lyon"),
            ("client_tech_lille", "Lille#123", "client", "Tech Lille"),
        ]
        cur.executemany(
            "INSERT INTO users (username, password_hash, role, client_name, created_at) VALUES (?, ?, ?, ?, ?)",
            [(u, hash_password(p), r, c, now) for (u, p, r, c) in demo_users],
        )

    if cur.execute("SELECT COUNT(*) AS c FROM tickets").fetchone()["c"] == 0:
        now = utcnow().isoformat()
        cur.executemany(
            "INSERT INTO tickets (code,client_name,type,priority,order_ref,status,description,updated_at) VALUES (?,?,?,?,?,?,?,?)",
            [
                ("TK-1001", "Mode Paris", "Retard transport", "Haute", "CMD-2026-00081", "En-cours", "Hub transport bloqué depuis 12h.", now),
                ("TK-1002", "Beauté Lyon", "Erreur préparation", "Critique", "CMD-2026-00079", "Nouveau", "Inversion SKU sur commande influenceur.", now),
                ("TK-1003", "Tech Lille", "Adresse invalide", "Normale", "CMD-2026-00073", "Résolu", "Adresse corrigée puis livraison relancée.", now),
            ],
        )

    if cur.execute("SELECT COUNT(*) AS c FROM notifications").fetchone()["c"] == 0:
        now = utcnow().isoformat()
        cur.executemany(
            "INSERT INTO notifications (user_scope,message,created_at) VALUES (?,?,?)",
            [
                ("admin", "3 tickets ouverts dont 1 critique à traiter avant 12h.", now),
                ("admin", "SLA global: 94% (objectif: 97%).", now),
                ("Mode Paris", "Ticket TK-1001 pris en charge par le pôle transport.", now),
                ("Beauté Lyon", "Ticket critique détecté: proposition d'avoir client préparée.", now),
                ("Tech Lille", "Ticket TK-1003 résolu. Livraison replanifiée confirmée.", now),
            ],
        )

    conn.commit()
    conn.close()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = utcnow()
    expires = now + timedelta(hours=SESSION_TTL_HOURS)
    with _lock:
        conn = db_conn()
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, created_at, expires_at, last_seen_at) VALUES (?, ?, ?, ?, ?)",
            (sha256_text(token), user_id, now.isoformat(), expires.isoformat(), now.isoformat()),
        )
        conn.commit()
        conn.close()
    return token


def delete_session(token: str):
    with _lock:
        conn = db_conn()
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (sha256_text(token),))
        conn.commit()
        conn.close()


def get_session_user(token: str):
    now = utcnow()
    with _lock:
        conn = db_conn()
        row = conn.execute(
            """
            SELECT s.id as session_id, s.expires_at, u.id, u.username, u.role, u.client_name
            FROM sessions s JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = ?
            """,
            (sha256_text(token),),
        ).fetchone()
        if not row:
            conn.close()
            return None
        if datetime.fromisoformat(row["expires_at"]) <= now:
            conn.execute("DELETE FROM sessions WHERE id = ?", (row["session_id"],))
            conn.commit()
            conn.close()
            return None
        conn.execute("UPDATE sessions SET last_seen_at = ? WHERE id = ?", (now.isoformat(), row["session_id"]))
        conn.commit()
        conn.close()
    return row


def cleanup_sessions():
    with _lock:
        conn = db_conn()
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (utcnow().isoformat(),))
        conn.commit()
        conn.close()


class AppHandler(BaseHTTPRequestHandler):
    server_version = "LogiTicketPro/1.0"

    def _json_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw)

    def _send_json(self, status, payload, set_cookie=None):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        if set_cookie:
            self.send_header("Set-Cookie", set_cookie)
        self.end_headers()
        self.wfile.write(data)

    def _get_cookie(self, name: str):
        cookie = SimpleCookie(self.headers.get("Cookie"))
        morsel = cookie.get(name)
        return morsel.value if morsel else None

    def _current_user(self):
        token = self._get_cookie("session_id")
        if not token:
            return None
        return get_session_user(token)

    def _require_auth(self):
        user = self._current_user()
        if not user:
            self._send_json(401, {"error": "Authentification requise"})
            return None
        return user

    def _serve_file(self, path: Path, content_type: str):
        if not path.exists() or not path.is_file():
            self.send_error(404)
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            return self._serve_file(TEMPLATE_FILE, "text/html; charset=utf-8")
        static_map = {
            "/static/styles.css": (STATIC_DIR / "styles.css", "text/css; charset=utf-8"),
            "/static/app.js": (STATIC_DIR / "app.js", "application/javascript; charset=utf-8"),
        }
        if parsed.path in static_map:
            file_path, content_type = static_map[parsed.path]
            return self._serve_file(file_path, content_type)
        if parsed.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        if parsed.path == "/health":
            cleanup_sessions()
            return self._send_json(200, {"status": "ok"})

        if parsed.path == "/api/me":
            user = self._require_auth()
            if not user:
                return
            return self._send_json(200, {"id": user["id"], "username": user["username"], "role": user["role"], "clientName": user["client_name"]})

        if parsed.path == "/api/tickets":
            user = self._require_auth()
            if not user:
                return
            conn = db_conn()
            if user["role"] == "admin":
                rows = conn.execute("SELECT * FROM tickets ORDER BY datetime(updated_at) DESC").fetchall()
            else:
                rows = conn.execute("SELECT * FROM tickets WHERE client_name=? ORDER BY datetime(updated_at) DESC", (user["client_name"],)).fetchall()
            conn.close()
            return self._send_json(200, [dict(row) for row in rows])

        if parsed.path == "/api/notifications":
            user = self._require_auth()
            if not user:
                return
            scope = "admin" if user["role"] == "admin" else user["client_name"]
            conn = db_conn()
            rows = conn.execute("SELECT id, message, created_at FROM notifications WHERE user_scope=? ORDER BY datetime(created_at) DESC", (scope,)).fetchall()
            conn.close()
            return self._send_json(200, [dict(row) for row in rows])

        if parsed.path.startswith("/api/"):
            return self._send_json(404, {"error": "Route API introuvable"})

        # SPA fallback to avoid preview 404 for non-root paths.
        return self._serve_file(TEMPLATE_FILE, "text/html; charset=utf-8")

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/login":
            try:
                data = self._json_body()
            except Exception:
                return self._send_json(400, {"error": "JSON invalide"})

            username = (data.get("username") or "").strip()
            password = data.get("password") or ""
            if not username or not password:
                return self._send_json(400, {"error": "Identifiants requis"})

            conn = db_conn()
            user = conn.execute("SELECT id, password_hash FROM users WHERE username = ?", (username,)).fetchone()
            conn.close()
            if not user or not verify_password(password, user["password_hash"]):
                return self._send_json(401, {"error": "Identifiants invalides"})

            token = create_session(int(user["id"]))
            attributes = [f"session_id={token}", "HttpOnly", "Path=/", "SameSite=Strict", f"Max-Age={SESSION_TTL_HOURS * 3600}"]
            if COOKIE_SECURE:
                attributes.append("Secure")
            return self._send_json(200, {"ok": True}, "; ".join(attributes))

        if parsed.path == "/api/logout":
            token = self._get_cookie("session_id")
            if token:
                delete_session(token)
            return self._send_json(200, {"ok": True}, "session_id=deleted; Path=/; Max-Age=0; HttpOnly; SameSite=Strict")

        if parsed.path == "/api/tickets":
            user = self._require_auth()
            if not user:
                return
            if user["role"] != "client":
                return self._send_json(403, {"error": "Seuls les clients peuvent créer un ticket"})

            try:
                data = self._json_body()
            except Exception:
                return self._send_json(400, {"error": "JSON invalide"})

            required = ["type", "priority", "orderRef", "description"]
            if any(not (data.get(key) or "").strip() for key in required):
                return self._send_json(400, {"error": "Champs obligatoires manquants"})

            conn = db_conn()
            total = conn.execute("SELECT COUNT(*) AS c FROM tickets").fetchone()["c"]
            code = f"TK-{1001 + total}"
            now = utcnow().isoformat()
            conn.execute(
                "INSERT INTO tickets (code,client_name,type,priority,order_ref,status,description,updated_at) VALUES (?,?,?,?,?,'Nouveau',?,?)",
                (code, user["client_name"], data["type"].strip(), data["priority"].strip(), data["orderRef"].strip(), data["description"].strip(), now),
            )
            conn.execute(
                "INSERT INTO notifications (user_scope, message, created_at) VALUES (?, ?, ?)",
                (user["client_name"], f"Ticket {code} créé avec succès.", now),
            )
            conn.commit()
            conn.close()
            return self._send_json(201, {"ok": True, "code": code})

        self.send_error(404)

    def do_PATCH(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/tickets/") and parsed.path.endswith("/status"):
            user = self._require_auth()
            if not user:
                return
            if user["role"] != "admin":
                return self._send_json(403, {"error": "Réservé admin"})

            segments = parsed.path.split("/")
            if len(segments) < 5 or not segments[3].isdigit():
                return self._send_json(400, {"error": "ID ticket invalide"})
            ticket_id = int(segments[3])

            try:
                data = self._json_body()
            except Exception:
                return self._send_json(400, {"error": "JSON invalide"})

            status = data.get("status")
            if status not in {"Nouveau", "En-cours", "Résolu"}:
                return self._send_json(400, {"error": "Statut invalide"})

            conn = db_conn()
            cur = conn.execute("UPDATE tickets SET status=?, updated_at=? WHERE id=?", (status, utcnow().isoformat(), ticket_id))
            conn.commit()
            conn.close()
            if cur.rowcount == 0:
                return self._send_json(404, {"error": "Ticket introuvable"})
            return self._send_json(200, {"ok": True})

        self.send_error(404)


if __name__ == "__main__":
    init_db()
    print(f"LogiTicket Pro running on http://0.0.0.0:{PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), AppHandler).serve_forever()
