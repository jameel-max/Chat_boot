import hashlib
import hmac
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4


SESSION_LIFETIME_SECONDS = 365 * 24 * 60 * 60
PASSWORD_HASH_ITERATIONS = 600_000


class Database:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    google_sub TEXT NOT NULL UNIQUE,
                    email TEXT NOT NULL,
                    name TEXT NOT NULL,
                    picture TEXT NOT NULL DEFAULT '',
                    password_hash TEXT,
                    grade TEXT,
                    grade_question_asked INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS admin_users (
                    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    granted_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS sessions_expiry_idx
                    ON sessions(expires_at);
                CREATE TABLE IF NOT EXISTS password_reset_codes (
                    email TEXT PRIMARY KEY COLLATE NOCASE,
                    user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
                    code_hash TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS site_statistics (
                    id INTEGER PRIMARY KEY CHECK(id = 1),
                    page_views INTEGER NOT NULL DEFAULT 0
                );
                INSERT OR IGNORE INTO site_statistics (id, page_views) VALUES (1, 0);
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    response_id TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS conversations_user_updated_idx
                    ON conversations(user_id, updated_at DESC);
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL
                        REFERENCES conversations(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    image_mime TEXT,
                    image_data BLOB,
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS messages_conversation_idx
                    ON messages(conversation_id, id);
                CREATE TABLE IF NOT EXISTS support_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
                    user_name TEXT NOT NULL,
                    user_email TEXT NOT NULL,
                    category TEXT NOT NULL CHECK(category IN ('message', 'complaint')),
                    content TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'new'
                        CHECK(status IN ('new', 'resolved')),
                    created_at INTEGER NOT NULL,
                    resolved_at INTEGER
                );
                CREATE INDEX IF NOT EXISTS support_messages_status_idx
                    ON support_messages(status, created_at DESC);
                """
            )
            user_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(users)").fetchall()
            }
            if "password_hash" not in user_columns:
                connection.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
            if "grade" not in user_columns:
                connection.execute("ALTER TABLE users ADD COLUMN grade TEXT")
            if "grade_question_asked" not in user_columns:
                connection.execute(
                    "ALTER TABLE users ADD COLUMN grade_question_asked "
                    "INTEGER NOT NULL DEFAULT 0"
                )
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS users_email_unique_idx "
                "ON users(email COLLATE NOCASE)"
            )
            conversations = connection.execute(
                """
                SELECT id, user_id, title
                FROM conversations
                ORDER BY user_id, created_at, id
                """
            ).fetchall()
            seen_titles = {}
            for conversation in conversations:
                seen = seen_titles.setdefault(conversation["user_id"], set())
                title = conversation["title"]
                candidate = title
                suffix_number = 2
                while candidate.casefold() in seen:
                    suffix = f" ({suffix_number})"
                    candidate = f"{title[:80 - len(suffix)].rstrip()}{suffix}"
                    suffix_number += 1
                if candidate != title:
                    connection.execute(
                        "UPDATE conversations SET title = ? WHERE id = ?",
                        (candidate, conversation["id"]),
                    )
                seen.add(candidate.casefold())

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def public_user(row):
        return {
            "id": row["id"],
            "email": row["email"],
            "name": row["name"],
            "picture": row["picture"],
        }

    @staticmethod
    def hash_password(password):
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, PASSWORD_HASH_ITERATIONS
        )
        return (
            f"pbkdf2_sha256${PASSWORD_HASH_ITERATIONS}"
            f"${salt.hex()}${digest.hex()}"
        )

    @staticmethod
    def verify_password(password, encoded_hash):
        if encoded_hash:
            try:
                algorithm, iterations, salt_hex, digest_hex = encoded_hash.split("$")
                if algorithm != "pbkdf2_sha256":
                    return False
                expected = bytes.fromhex(digest_hex)
                salt = bytes.fromhex(salt_hex)
                iteration_count = int(iterations)
            except (ValueError, TypeError):
                return False
        else:
            salt = bytes.fromhex("68d3c0e98e11522275f91a4e27af10a6")
            expected = bytes(32)
            iteration_count = PASSWORD_HASH_ITERATIONS
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, iteration_count
        )
        return bool(encoded_hash) and hmac.compare_digest(actual, expected)

    def register_user(self, email, password):
        now = int(time.time())
        user_id = uuid4().hex
        email = email.strip().casefold()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO users
                    (id, google_sub, email, name, picture, password_hash, created_at)
                VALUES (?, ?, ?, ?, '', ?, ?)
                """,
                (
                    user_id,
                    f"password:{email}",
                    email,
                    email.partition("@")[0],
                    self.hash_password(password),
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        return self.public_user(row)

    def login_user(self, email, password):
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE email = ? COLLATE NOCASE", (email.strip(),)
            ).fetchone()
        if not row or not self.verify_password(password, row["password_hash"]):
            return None
        return self.public_user(row)

    def change_password(self, user_id, current_password, new_password, session_token):
        current_token_hash = self.hash_session(session_token)
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT password_hash FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if not row or not self.verify_password(
                current_password, row["password_hash"]
            ):
                connection.rollback()
                return False

            connection.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (self.hash_password(new_password), user_id),
            )
            if connection.execute("SELECT changes()").fetchone()[0] != 1:
                connection.rollback()
                return False
            connection.execute(
                "DELETE FROM sessions WHERE user_id = ? AND token_hash != ?",
                (user_id, current_token_hash),
            )
        return True

    def issue_password_reset(self, email, code_hash, now, cooldown_seconds=60):
        email = email.strip().casefold()
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT created_at FROM password_reset_codes WHERE email = ?",
                (email,),
            ).fetchone()
            if existing and now - existing["created_at"] < cooldown_seconds:
                return "throttled", None

            user = connection.execute(
                "SELECT id, email FROM users WHERE email = ? COLLATE NOCASE",
                (email,),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO password_reset_codes
                    (email, user_id, code_hash, created_at, expires_at, attempts)
                VALUES (?, ?, ?, ?, ?, 0)
                ON CONFLICT(email) DO UPDATE SET
                    user_id = excluded.user_id,
                    code_hash = excluded.code_hash,
                    created_at = excluded.created_at,
                    expires_at = excluded.expires_at,
                    attempts = 0
                """,
                (
                    email,
                    user["id"] if user else None,
                    code_hash,
                    now,
                    now + 10 * 60,
                ),
            )
        return "issued", user["email"] if user else None

    def cancel_password_reset(self, email, code_hash):
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM password_reset_codes WHERE email = ? AND code_hash = ?",
                (email.strip().casefold(), code_hash),
            )

    def reset_password(self, email, code, new_password, now):
        email = email.strip().casefold()
        with self.connect() as connection:
            record = connection.execute(
                "SELECT * FROM password_reset_codes WHERE email = ?", (email,)
            ).fetchone()
            if not record:
                return "invalid"
            if record["expires_at"] <= now:
                connection.execute(
                    "DELETE FROM password_reset_codes WHERE email = ?", (email,)
                )
                return "expired"
            if record["attempts"] >= 5:
                connection.execute(
                    "DELETE FROM password_reset_codes WHERE email = ?", (email,)
                )
                return "locked"
            if not record["user_id"] or not self.verify_password(
                code, record["code_hash"]
            ):
                attempts = record["attempts"] + 1
                if attempts >= 5:
                    connection.execute(
                        "DELETE FROM password_reset_codes WHERE email = ?",
                        (email,),
                    )
                    return "locked"
                connection.execute(
                    """
                    UPDATE password_reset_codes
                    SET attempts = ? WHERE email = ?
                    """,
                    (attempts, email),
                )
                return "invalid"

            connection.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (self.hash_password(new_password), record["user_id"]),
            )
            connection.execute(
                "DELETE FROM password_reset_codes WHERE user_id = ?",
                (record["user_id"],),
            )
            connection.execute(
                "DELETE FROM sessions WHERE user_id = ?", (record["user_id"],)
            )
        return "success"

    def record_page_view(self):
        with self.connect() as connection:
            connection.execute(
                "UPDATE site_statistics SET page_views = page_views + 1 WHERE id = 1"
            )

    def admin_dashboard(self, primary_admin_email=""):
        with self.connect() as connection:
            users = connection.execute(
                """
                SELECT users.id, users.email, users.name, users.created_at,
                       CASE WHEN admin_users.user_id IS NOT NULL
                                  OR lower(users.email) = lower(?)
                            THEN 1 ELSE 0 END AS is_admin,
                       CASE WHEN lower(users.email) = lower(?)
                            THEN 1 ELSE 0 END AS is_primary_admin
                FROM users
                LEFT JOIN admin_users ON admin_users.user_id = users.id
                ORDER BY created_at DESC, email COLLATE NOCASE
                """,
                (primary_admin_email, primary_admin_email),
            ).fetchall()
            stats = connection.execute(
                "SELECT page_views FROM site_statistics WHERE id = 1"
            ).fetchone()
        return {
            "pageViews": stats["page_views"],
            "users": [dict(user) for user in users],
        }

    def create_support_message(self, user, category, content):
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO support_messages
                    (user_id, user_name, user_email, category, content, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    user["id"],
                    user["name"],
                    user["email"],
                    category,
                    content,
                    int(time.time()),
                ),
            )
            return cursor.lastrowid

    def list_support_messages(self):
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, user_name, user_email, category, content, status,
                       created_at, resolved_at
                FROM support_messages
                ORDER BY CASE status WHEN 'new' THEN 0 ELSE 1 END,
                         created_at DESC, id DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def set_support_message_status(self, message_id, status):
        resolved_at = int(time.time()) if status == "resolved" else None
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE support_messages
                SET status = ?, resolved_at = ?
                WHERE id = ?
                """,
                (status, resolved_at, message_id),
            )
        return cursor.rowcount > 0

    def is_admin(self, user_id):
        with self.connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM admin_users WHERE user_id = ?", (user_id,)
            ).fetchone()
        return row is not None

    def set_user_admin(self, user_id, enabled, actor_id, primary_admin_email):
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            user = connection.execute(
                "SELECT email FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if not user:
                connection.rollback()
                return "not_found"
            if user_id == actor_id:
                connection.rollback()
                return "self"
            if (
                primary_admin_email
                and user["email"].casefold() == primary_admin_email.casefold()
            ):
                connection.rollback()
                return "primary_admin"
            if enabled:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO admin_users (user_id, granted_at)
                    VALUES (?, ?)
                    """,
                    (user_id, int(time.time())),
                )
            else:
                connection.execute(
                    "DELETE FROM admin_users WHERE user_id = ?", (user_id,)
                )
        return "updated"

    def delete_user(self, user_id, primary_admin_email="", actor_is_primary_admin=False):
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            user = connection.execute(
                "SELECT email FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if not user:
                connection.rollback()
                return "not_found"
            if (
                primary_admin_email
                and user["email"].casefold() == primary_admin_email.casefold()
            ):
                connection.rollback()
                return "primary_admin"
            target_is_admin = connection.execute(
                "SELECT 1 FROM admin_users WHERE user_id = ?", (user_id,)
            ).fetchone() or (
                primary_admin_email
                and user["email"].casefold() == primary_admin_email.casefold()
            )
            if target_is_admin and not actor_is_primary_admin:
                connection.rollback()
                return "target_admin"
            connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
        return "deleted"

    def admin_set_password(
        self, user_id, new_password, primary_admin_email="", actor_is_primary_admin=False
    ):
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            user = connection.execute(
                "SELECT email FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if not user:
                connection.rollback()
                return "not_found"
            target_is_admin = connection.execute(
                "SELECT 1 FROM admin_users WHERE user_id = ?", (user_id,)
            ).fetchone() or (
                primary_admin_email
                and user["email"].casefold() == primary_admin_email.casefold()
            )
            if target_is_admin and not actor_is_primary_admin:
                connection.rollback()
                return "target_admin"
            cursor = connection.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (self.hash_password(new_password), user_id),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                return "not_found"
            connection.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        return "updated"

    def get_student_preferences(self, user_id):
        with self.connect() as connection:
            row = connection.execute(
                "SELECT grade, grade_question_asked FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "grade": row["grade"],
            "grade_question_asked": bool(row["grade_question_asked"]),
        }

    def update_student_grade(self, user_id, grade):
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE users
                SET grade = ?, grade_question_asked = 1
                WHERE id = ?
                """,
                (grade, user_id),
            )

    @staticmethod
    def hash_session(token):
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def create_session(self, user_id, lifetime=SESSION_LIFETIME_SECONDS):
        token = secrets.token_urlsafe(32)
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                (
                    self.hash_session(token),
                    user_id,
                    int(time.time()) + lifetime,
                ),
            )
            connection.execute(
                "DELETE FROM sessions WHERE expires_at <= ?", (int(time.time()),)
            )
        return token

    def get_session_user(self, token):
        if not token:
            return None
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT users.*
                FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.token_hash = ? AND sessions.expires_at > ?
                """,
                (self.hash_session(token), int(time.time())),
            ).fetchone()
        return self.public_user(row) if row else None

    def delete_session(self, token):
        if token:
            with self.connect() as connection:
                connection.execute(
                    "DELETE FROM sessions WHERE token_hash = ?",
                    (self.hash_session(token),),
                )

    def list_conversations(self, user_id):
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, title, created_at, updated_at
                FROM conversations
                WHERE user_id = ?
                ORDER BY updated_at DESC, id DESC
                """,
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def is_placeholder_title(title):
        return title == "محادثة جديدة" or (
            title.startswith("محادثة جديدة (") and title.endswith(")")
        )

    @staticmethod
    def unique_conversation_title(connection, user_id, title, exclude_id=None):
        base_title = " ".join(title.split())[:80].rstrip() or "محادثة جديدة"
        candidate = base_title
        suffix_number = 2
        while True:
            query = """
                SELECT 1 FROM conversations
                WHERE user_id = ? AND title = ? COLLATE NOCASE
            """
            parameters = [user_id, candidate]
            if exclude_id:
                query += " AND id != ?"
                parameters.append(exclude_id)
            if not connection.execute(query, parameters).fetchone():
                return candidate
            suffix = f" ({suffix_number})"
            candidate = f"{base_title[:80 - len(suffix)].rstrip()}{suffix}"
            suffix_number += 1

    def prepare_user_message(
        self, user_id, conversation_id, title, content, image_mime, image_data
    ):
        now = int(time.time())
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            title_source = ""
            title_needs_ai = False
            if conversation_id:
                conversation = connection.execute(
                    "SELECT id, title, response_id FROM conversations WHERE id = ? AND user_id = ?",
                    (conversation_id, user_id),
                ).fetchone()
                if not conversation:
                    return None
                if self.is_placeholder_title(conversation["title"]) and not self.is_placeholder_title(title):
                    title_source = content
                    title_needs_ai = True
                    title = self.unique_conversation_title(
                        connection, user_id, title, conversation_id
                    )
                    connection.execute(
                        "UPDATE conversations SET title = ? WHERE id = ?",
                        (title, conversation_id),
                    )
                    conversation = {
                        "id": conversation["id"],
                        "title": title,
                        "response_id": conversation["response_id"],
                    }
            else:
                conversation_id = uuid4().hex
                title_needs_ai = not self.is_placeholder_title(title)
                title_source = content if title_needs_ai else ""
                title = self.unique_conversation_title(connection, user_id, title)
                connection.execute(
                    """
                    INSERT INTO conversations
                        (id, user_id, title, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (conversation_id, user_id, title, now, now),
                )
                conversation = {
                    "id": conversation_id,
                    "title": title,
                    "response_id": None,
                }
            connection.execute(
                """
                INSERT INTO messages
                    (conversation_id, role, content, image_mime, image_data, created_at)
                VALUES (?, 'user', ?, ?, ?, ?)
                """,
                (conversation_id, content, image_mime, image_data, now),
            )
            connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now, conversation_id),
            )
        return {
            "id": conversation_id,
            "title": conversation["title"],
            "response_id": conversation["response_id"],
            "title_source": title_source,
            "title_needs_ai": title_needs_ai,
        }

    def set_conversation_title(self, user_id, conversation_id, title):
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            conversation = connection.execute(
                "SELECT 1 FROM conversations WHERE id = ? AND user_id = ?",
                (conversation_id, user_id),
            ).fetchone()
            if not conversation:
                connection.rollback()
                return None
            unique_title = self.unique_conversation_title(
                connection, user_id, title, conversation_id
            )
            connection.execute(
                """
                UPDATE conversations
                SET title = ?, updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (unique_title, int(time.time()), conversation_id, user_id),
            )
        return unique_title

    def complete_assistant_message(
        self,
        conversation_id,
        content,
        response_id,
        user_id=None,
        grade_question_asked=False,
    ):
        now = int(time.time())
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO messages (conversation_id, role, content, created_at)
                VALUES (?, 'assistant', ?, ?)
                """,
                (conversation_id, content, now),
            )
            connection.execute(
                """
                UPDATE conversations
                SET response_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (response_id, now, conversation_id),
            )
            if user_id and grade_question_asked:
                connection.execute(
                    "UPDATE users SET grade_question_asked = 1 WHERE id = ?",
                    (user_id,),
                )

    def get_conversation(self, user_id, conversation_id):
        with self.connect() as connection:
            conversation = connection.execute(
                """
                SELECT id, title, created_at, updated_at
                FROM conversations WHERE id = ? AND user_id = ?
                """,
                (conversation_id, user_id),
            ).fetchone()
            if not conversation:
                return None
            messages = connection.execute(
                """
                SELECT role, content, image_mime, image_data, created_at
                FROM messages WHERE conversation_id = ? ORDER BY id
                """,
                (conversation_id,),
            ).fetchall()
        return dict(conversation), messages

    def rename_conversation(self, user_id, conversation_id, title):
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            unique_title = self.unique_conversation_title(
                connection, user_id, title, conversation_id
            )
            result = connection.execute(
                """
                UPDATE conversations SET title = ?, updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (unique_title, int(time.time()), conversation_id, user_id),
            )
        return unique_title if result.rowcount == 1 else None

    def delete_conversation(self, user_id, conversation_id):
        with self.connect() as connection:
            result = connection.execute(
                "DELETE FROM conversations WHERE id = ? AND user_id = ?",
                (conversation_id, user_id),
            )
        return result.rowcount == 1
