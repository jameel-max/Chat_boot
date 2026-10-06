import hashlib
import hmac
import math
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None


DATABASE_ERROR_TYPES = (sqlite3.Error,)
DATABASE_INTEGRITY_ERROR_TYPES = (sqlite3.IntegrityError,)

if psycopg is not None:
    DATABASE_ERROR_TYPES += (psycopg.Error,)
    DATABASE_INTEGRITY_ERROR_TYPES += (psycopg.IntegrityError,)


SESSION_LIFETIME_SECONDS = 365 * 24 * 60 * 60
PASSWORD_HASH_ITERATIONS = 600_000


class PostgresConnection:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, statement, parameters=()):
        statement = statement.replace("?", "%s").replace(
            "BEGIN IMMEDIATE",
            "BEGIN",
        )
        return self.connection.execute(statement, parameters)

    def rollback(self):
        self.connection.rollback()


class Database:
    error_types = DATABASE_ERROR_TYPES
    integrity_error_types = DATABASE_INTEGRITY_ERROR_TYPES

    def __init__(self, path, initialize_schema=True):
        self.curriculum_vector_enabled = False

        self.is_postgres = isinstance(path, str) and path.startswith(
            ("postgres://", "postgresql://")
        )

        if self.is_postgres:
            if psycopg is None:
                raise RuntimeError(
                    "Install the psycopg[binary] package to use PostgreSQL."
                )
            self.path = path
        else:
            self.path = Path(path)
            self.path.parent.mkdir(parents=True, exist_ok=True)

        if not initialize_schema:
            return

        with self.connect() as connection:
            schema = """
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
                    page_views INTEGER NOT NULL DEFAULT 0,
                    unique_visitors INTEGER NOT NULL DEFAULT 0
                );

                INSERT INTO site_statistics (id, page_views)
                VALUES (1, 0)
                ON CONFLICT DO NOTHING;

                CREATE TABLE IF NOT EXISTS site_visitors (
                    visitor_hash TEXT PRIMARY KEY,
                    first_seen_at INTEGER NOT NULL,
                    last_seen_at INTEGER NOT NULL,
                    last_counted_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS site_visit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    visitor_hash TEXT NOT NULL
                        REFERENCES site_visitors(visitor_hash)
                        ON DELETE CASCADE,
                    visited_at INTEGER NOT NULL
                );

                CREATE INDEX IF NOT EXISTS site_visit_events_time_idx
                    ON site_visit_events(visited_at);

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
                    category TEXT NOT NULL
                        CHECK(category IN ('message', 'complaint')),
                    content TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'new'
                        CHECK(status IN ('new', 'resolved')),
                    created_at INTEGER NOT NULL,
                    resolved_at INTEGER
                );

                CREATE INDEX IF NOT EXISTS support_messages_status_idx
                    ON support_messages(status, created_at DESC);
            """

            if self.is_postgres:
                schema = (
                    schema.replace(
                        "id INTEGER PRIMARY KEY AUTOINCREMENT",
                        "id BIGSERIAL PRIMARY KEY",
                    )
                    .replace(
                        "image_data BLOB",
                        "image_data BYTEA",
                    )
                    .replace(
                        "email TEXT PRIMARY KEY COLLATE NOCASE",
                        "email TEXT PRIMARY KEY",
                    )
                )

            for statement in schema.split(";"):
                if statement.strip():
                    connection.execute(statement)

            if self.is_postgres:
                connection.execute(
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT"
                )

                connection.execute(
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS grade TEXT"
                )

                connection.execute(
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
                    "grade_question_asked INTEGER NOT NULL DEFAULT 0"
                )

                connection.execute(
                    "ALTER TABLE site_statistics ADD COLUMN IF NOT EXISTS "
                    "unique_visitors INTEGER NOT NULL DEFAULT 0"
                )

                connection.execute(
                    "UPDATE site_statistics SET unique_visitors = 1 "
                    "WHERE id = 1 AND page_views > 0 "
                    "AND unique_visitors = 0"
                )

            else:
                user_columns = {
                    row["name"]
                    for row in connection.execute(
                        "PRAGMA table_info(users)"
                    ).fetchall()
                }

                if "password_hash" not in user_columns:
                    connection.execute(
                        "ALTER TABLE users ADD COLUMN password_hash TEXT"
                    )

                if "grade" not in user_columns:
                    connection.execute(
                        "ALTER TABLE users ADD COLUMN grade TEXT"
                    )

                if "grade_question_asked" not in user_columns:
                    connection.execute(
                        "ALTER TABLE users ADD COLUMN "
                        "grade_question_asked INTEGER NOT NULL DEFAULT 0"
                    )

                statistics_columns = {
                    row["name"]
                    for row in connection.execute(
                        "PRAGMA table_info(site_statistics)"
                    ).fetchall()
                }

                if "unique_visitors" not in statistics_columns:
                    connection.execute(
                        "ALTER TABLE site_statistics ADD COLUMN "
                        "unique_visitors INTEGER NOT NULL DEFAULT 0"
                    )

                connection.execute(
                    "UPDATE site_statistics SET unique_visitors = 1 "
                    "WHERE id = 1 AND page_views > 0 "
                    "AND unique_visitors = 0"
                )

            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS users_email_unique_idx "
                "ON users(lower(email))"
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
                seen = seen_titles.setdefault(
                    conversation["user_id"],
                    set(),
                )

                title = conversation["title"]
                candidate = title
                suffix_number = 2

                while candidate.casefold() in seen:
                    suffix = f" ({suffix_number})"
                    candidate = (
                        f"{title[:80 - len(suffix)].rstrip()}{suffix}"
                    )
                    suffix_number += 1

                if candidate != title:
                    connection.execute(
                        "UPDATE conversations SET title = ? WHERE id = ?",
                        (candidate, conversation["id"]),
                    )

                seen.add(candidate.casefold())

            if self.is_postgres:
                self._initialize_curriculum_schema(connection)

    def _initialize_curriculum_schema(self, connection):
        extension = connection.execute(
            "SELECT EXISTS ("
            "SELECT 1 FROM pg_available_extensions "
            "WHERE name = 'vector'"
            ") AS available"
        ).fetchone()

        if not extension or not extension["available"]:
            return

        connection.execute(
            "CREATE EXTENSION IF NOT EXISTS vector"
        )

        for statement in (
            """
            CREATE TABLE IF NOT EXISTS curriculum_books (
                book_id TEXT PRIMARY KEY,
                grade TEXT NOT NULL,
                subject TEXT NOT NULL,
                semester TEXT NOT NULL DEFAULT '',
                book_title TEXT NOT NULL,
                edition TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL,
                source_url TEXT NOT NULL DEFAULT '',
                is_official BOOLEAN NOT NULL DEFAULT TRUE,
                created_at INTEGER NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS curriculum_pages (
                page_id TEXT PRIMARY KEY,
                book_id TEXT NOT NULL
                    REFERENCES curriculum_books(book_id)
                    ON DELETE CASCADE,
                page_number INTEGER NOT NULL,
                unit TEXT NOT NULL DEFAULT '',
                lesson TEXT NOT NULL DEFAULT '',
                page_image_data BYTEA,
                page_image_mime TEXT,
                UNIQUE(book_id, page_number)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS curriculum_chunks (
                chunk_id TEXT PRIMARY KEY,
                book_id TEXT NOT NULL
                    REFERENCES curriculum_books(book_id)
                    ON DELETE CASCADE,
                page_id TEXT NOT NULL
                    REFERENCES curriculum_pages(page_id)
                    ON DELETE CASCADE,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                embedding vector(768) NOT NULL,
                UNIQUE(page_id, chunk_index)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS curriculum_book_progress (
                book_id TEXT PRIMARY KEY
                    REFERENCES curriculum_books(book_id)
                    ON DELETE CASCADE,
                expected_chunks INTEGER NOT NULL DEFAULT 0,
                completed_chunks INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'indexing',
                updated_at INTEGER NOT NULL
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS curriculum_books_filter_idx
            ON curriculum_books
                (grade, subject, semester, is_official)
            """,
            """
            CREATE INDEX IF NOT EXISTS curriculum_chunks_book_idx
            ON curriculum_chunks
                (book_id, page_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS curriculum_chunks_embedding_idx
            ON curriculum_chunks
            USING hnsw (embedding vector_cosine_ops)
            """,
        ):
            connection.execute(statement)

        self.curriculum_vector_enabled = True

    @contextmanager
    def connect(self):
        if self.is_postgres:
            connection = psycopg.connect(
                self.path,
                row_factory=dict_row,
            )

            try:
                with connection:
                    yield PostgresConnection(connection)
            finally:
                connection.close()

            return

        connection = sqlite3.connect(
            self.path,
            timeout=10,
        )

        connection.row_factory = sqlite3.Row

        connection.execute(
            "PRAGMA foreign_keys = ON"
        )

        connection.execute(
            "PRAGMA busy_timeout = 10000"
        )

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
            "sha256",
            password.encode("utf-8"),
            salt,
            PASSWORD_HASH_ITERATIONS,
        )

        return (
            f"pbkdf2_sha256${PASSWORD_HASH_ITERATIONS}"
            f"${salt.hex()}${digest.hex()}"
        )

    @staticmethod
    def verify_password(password, encoded_hash):
        if encoded_hash:
            try:
                algorithm, iterations, salt_hex, digest_hex = (
                    encoded_hash.split("$")
                )

                if algorithm != "pbkdf2_sha256":
                    return False

                expected = bytes.fromhex(digest_hex)
                salt = bytes.fromhex(salt_hex)
                iteration_count = int(iterations)

            except (ValueError, TypeError):
                return False

        else:
            salt = bytes.fromhex(
                "68d3c0e98e11522275f91a4e27af10a6"
            )
            expected = bytes(32)
            iteration_count = PASSWORD_HASH_ITERATIONS

        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iteration_count,
        )

        return bool(encoded_hash) and hmac.compare_digest(
            actual,
            expected,
        )

    def register_user(self, email, password):
        now = int(time.time())
        user_id = uuid4().hex
        email = email.strip().casefold()

        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO users
                    (
                        id,
                        google_sub,
                        email,
                        name,
                        picture,
                        password_hash,
                        created_at
                    )
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
                "SELECT * FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()

        return self.public_user(row)

    def login_user(self, email, password):
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM users
                WHERE lower(email) = lower(?)
                """,
                (email.strip(),),
            ).fetchone()

        if not row or not self.verify_password(
            password,
            row["password_hash"],
        ):
            return None

        return self.public_user(row)

    def user_exists(self, email):
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM users
                WHERE lower(email) = lower(?)
                """,
                (email.strip(),),
            ).fetchone()
        return row is not None

    def change_password(
        self,
        user_id,
        current_password,
        new_password,
        session_token,
    ):
        current_token_hash = self.hash_session(session_token)

        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")

            row = connection.execute(
                """
                SELECT password_hash
                FROM users
                WHERE id = ?
                """,
                (user_id,),
            ).fetchone()

            if not row or not self.verify_password(
                current_password,
                row["password_hash"],
            ):
                connection.rollback()
                return False

            cursor = connection.execute(
                """
                UPDATE users
                SET password_hash = ?
                WHERE id = ?
                """,
                (
                    self.hash_password(new_password),
                    user_id,
                ),
            )

            if cursor.rowcount != 1:
                connection.rollback()
                return False

            connection.execute(
                """
                DELETE FROM sessions
                WHERE user_id = ?
                AND token_hash != ?
                """,
                (
                    user_id,
                    current_token_hash,
                ),
            )

        return True

    def issue_password_reset(
        self,
        email,
        code_hash,
        now,
        cooldown_seconds=60,
    ):
        email = email.strip().casefold()

        with self.connect() as connection:
            existing = connection.execute(
                """
                SELECT created_at
                FROM password_reset_codes
                WHERE email = ?
                """,
                (email,),
            ).fetchone()

            if existing and (
                now - existing["created_at"] < cooldown_seconds
            ):
                return "throttled", None

            user = connection.execute(
                """
                SELECT id, email
                FROM users
                WHERE lower(email) = lower(?)
                """,
                (email,),
            ).fetchone()

            connection.execute(
                """
                INSERT INTO password_reset_codes
                    (
                        email,
                        user_id,
                        code_hash,
                        created_at,
                        expires_at,
                        attempts
                    )
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
                """
                DELETE FROM password_reset_codes
                WHERE email = ?
                AND code_hash = ?
                """,
                (
                    email.strip().casefold(),
                    code_hash,
                ),
            )

    def reset_password(
        self,
        email,
        code,
        new_password,
        now,
    ):
        email = email.strip().casefold()

        with self.connect() as connection:
            record = connection.execute(
                """
                SELECT *
                FROM password_reset_codes
                WHERE email = ?
                """,
                (email,),
            ).fetchone()

            if not record:
                return "invalid"

            if record["expires_at"] <= now:
                connection.execute(
                    """
                    DELETE FROM password_reset_codes
                    WHERE email = ?
                    """,
                    (email,),
                )
                return "expired"

            if record["attempts"] >= 5:
                connection.execute(
                    """
                    DELETE FROM password_reset_codes
                    WHERE email = ?
                    """,
                    (email,),
                )
                return "locked"

            if not record["user_id"] or not self.verify_password(
                code,
                record["code_hash"],
            ):
                attempts = record["attempts"] + 1

                if attempts >= 5:
                    connection.execute(
                        """
                        DELETE FROM password_reset_codes
                        WHERE email = ?
                        """,
                        (email,),
                    )
                    return "locked"

                connection.execute(
                    """
                    UPDATE password_reset_codes
                    SET attempts = ?
                    WHERE email = ?
                    """,
                    (
                        attempts,
                        email,
                    ),
                )

                return "invalid"

            connection.execute(
                """
                UPDATE users
                SET password_hash = ?
                WHERE id = ?
                """,
                (
                    self.hash_password(new_password),
                    record["user_id"],
                ),
            )

            connection.execute(
                """
                DELETE FROM password_reset_codes
                WHERE user_id = ?
                """,
                (record["user_id"],),
            )

            connection.execute(
                """
                DELETE FROM sessions
                WHERE user_id = ?
                """,
                (record["user_id"],),
            )

        return "success"

    def record_page_view(
        self,
        visitor_token,
        now=None,
        dedup_seconds=30,
    ):
        if not visitor_token:
            raise ValueError(
                "A visitor token is required to record a page view."
            )

        now = (
            int(time.time())
            if now is None
            else int(now)
        )

        visitor_hash = self.hash_session(visitor_token)

        with self.connect() as connection:
            if not self.is_postgres:
                connection.execute("BEGIN IMMEDIATE")

            inserted = connection.execute(
                """
                INSERT INTO site_visitors
                    (
                        visitor_hash,
                        first_seen_at,
                        last_seen_at,
                        last_counted_at
                    )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(visitor_hash) DO NOTHING
                """,
                (
                    visitor_hash,
                    now,
                    now,
                    now,
                ),
            )

            is_unique_visitor = inserted.rowcount == 1
            count_visit = is_unique_visitor

            if not is_unique_visitor:
                lock_clause = (
                    " FOR UPDATE"
                    if self.is_postgres
                    else ""
                )

                visitor = connection.execute(
                    "SELECT last_counted_at "
                    "FROM site_visitors "
                    f"WHERE visitor_hash = ?{lock_clause}",
                    (visitor_hash,),
                ).fetchone()

                if visitor is None:
                    raise RuntimeError(
                        "Visitor record disappeared during update."
                    )

                count_visit = (
                    now - visitor["last_counted_at"]
                    >= dedup_seconds
                )

                connection.execute(
                    """
                    UPDATE site_visitors
                    SET last_seen_at = ?,
                        last_counted_at = ?
                    WHERE visitor_hash = ?
                    """,
                    (
                        now,
                        now if count_visit
                        else visitor["last_counted_at"],
                        visitor_hash,
                    ),
                )

            connection.execute(
                """
                UPDATE site_statistics
                SET page_views = page_views + ?,
                    unique_visitors = unique_visitors + ?
                WHERE id = 1
                """,
                (
                    int(count_visit),
                    int(is_unique_visitor),
                ),
            )

            if count_visit:
                connection.execute(
                    """
                    INSERT INTO site_visit_events (visitor_hash, visited_at)
                    VALUES (?, ?)
                    """,
                    (visitor_hash, now),
                )

    def admin_dashboard(self, primary_admin_email=""):
        with self.connect() as connection:
            users = connection.execute(
                """
                SELECT
                    users.id,
                    users.email,
                    users.name,
                    users.created_at,
                    CASE
                        WHEN admin_users.user_id IS NOT NULL
                             OR lower(users.email) = lower(?)
                        THEN 1
                        ELSE 0
                    END AS is_admin,
                    CASE
                        WHEN lower(users.email) = lower(?)
                        THEN 1
                        ELSE 0
                    END AS is_primary_admin
                FROM users
                LEFT JOIN admin_users
                    ON admin_users.user_id = users.id
                ORDER BY created_at DESC, lower(email)
                """,
                (
                    primary_admin_email,
                    primary_admin_email,
                ),
            ).fetchall()

            stats = connection.execute(
                """
                SELECT page_views, unique_visitors
                FROM site_statistics
                WHERE id = 1
                """
            ).fetchone()

        return {
            "pageViews": stats["page_views"],
            "uniqueVisitors": stats["unique_visitors"],
            "users": [dict(user) for user in users],
        }

    def admin_statistics(self):
        with self.connect() as connection:
            stats = connection.execute(
                """
                SELECT page_views, unique_visitors
                FROM site_statistics
                WHERE id = 1
                """
            ).fetchone()

        return {
            "pageViews": stats["page_views"],
            "uniqueVisitors": stats["unique_visitors"],
        }

    # ============================================================
    # CURRICULUM
    # ============================================================

    def _upsert_curriculum_book(
        self,
        connection,
        book,
    ):
        """
        Ensures that the parent curriculum_books row exists
        before inserting pages, chunks, or progress records.

        This prevents ForeignKeyViolation errors.
        """

        connection.execute(
            """
            INSERT INTO curriculum_books
                (
                    book_id,
                    grade,
                    subject,
                    semester,
                    book_title,
                    edition,
                    source,
                    source_url,
                    is_official,
                    created_at
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(book_id) DO UPDATE SET
                grade = excluded.grade,
                subject = excluded.subject,
                semester = excluded.semester,
                book_title = excluded.book_title,
                edition = excluded.edition,
                source = excluded.source,
                source_url = excluded.source_url,
                is_official = excluded.is_official
            """,
            (
                book["book_id"],
                book["grade"],
                book["subject"],
                book.get("semester", ""),
                book["book_title"],
                book.get("edition", ""),
                book["source"],
                book.get("source_url", ""),
                book.get("is_official", True),
                int(time.time()),
            ),
        )

    def index_curriculum_book(self, book, pages):
        if not self.curriculum_vector_enabled:
            raise RuntimeError(
                "PostgreSQL pgvector is not available "
                "for curriculum indexing."
            )

        with self.connect() as connection:
            self._upsert_curriculum_book(
                connection,
                book,
            )

            for page in pages:
                connection.execute(
                    """
                    INSERT INTO curriculum_pages
                        (
                            page_id,
                            book_id,
                            page_number,
                            unit,
                            lesson,
                            page_image_data,
                            page_image_mime
                        )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(page_id) DO UPDATE SET
                        book_id = excluded.book_id,
                        page_number = excluded.page_number,
                        unit = excluded.unit,
                        lesson = excluded.lesson,
                        page_image_data =
                            COALESCE(
                                excluded.page_image_data,
                                curriculum_pages.page_image_data
                            ),
                        page_image_mime =
                            COALESCE(
                                excluded.page_image_mime,
                                curriculum_pages.page_image_mime
                            )
                    """,
                    (
                        page["page_id"],
                        book["book_id"],
                        page["page_number"],
                        page.get("unit", ""),
                        page.get("lesson", ""),
                        page.get("page_image_data"),
                        page.get("page_image_mime"),
                    ),
                )

                for chunk in page["chunks"]:
                    embedding = chunk.get("embedding")

                    if embedding is None:
                        raise ValueError(
                            "Cannot save a curriculum chunk "
                            "without an embedding."
                        )

                    if len(embedding) != 768 or not all(
                        math.isfinite(float(value))
                        for value in embedding
                    ):
                        raise ValueError(
                            "Curriculum embeddings must contain "
                            "768 finite values."
                        )

                    vector = "[" + ",".join(
                        format(float(value), ".9g")
                        for value in embedding
                    ) + "]"

                    connection.execute(
                        """
                        INSERT INTO curriculum_chunks
                            (
                                chunk_id,
                                book_id,
                                page_id,
                                chunk_index,
                                content,
                                embedding
                            )
                        VALUES (?, ?, ?, ?, ?, ?::vector)
                        ON CONFLICT(chunk_id) DO UPDATE SET
                            book_id = excluded.book_id,
                            page_id = excluded.page_id,
                            chunk_index = excluded.chunk_index,
                            content = excluded.content,
                            embedding = excluded.embedding
                        """,
                        (
                            chunk["chunk_id"],
                            book["book_id"],
                            page["page_id"],
                            chunk["chunk_index"],
                            chunk["content"],
                            vector,
                        ),
                    )

    def get_curriculum_progress(self, book_id):
        if not self.curriculum_vector_enabled:
            return None

        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    book_id,
                    expected_chunks,
                    completed_chunks,
                    status,
                    updated_at
                FROM curriculum_book_progress
                WHERE book_id = ?
                """,
                (book_id,),
            ).fetchone()

        return dict(row) if row else None

    def get_existing_curriculum_chunk_ids(self, book_id):
        if not self.curriculum_vector_enabled:
            return set()

        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT chunk_id
                FROM curriculum_chunks
                WHERE book_id = ?
                """,
                (book_id,),
            ).fetchall()

        return {
            row["chunk_id"]
            for row in rows
        }

    def start_curriculum_progress(
        self,
        book,
        expected_chunks,
    ):
        if not self.curriculum_vector_enabled:
            raise RuntimeError(
                "PostgreSQL pgvector is not available "
                "for curriculum indexing."
            )

        now = int(time.time())

        with self.connect() as connection:
            # IMPORTANT:
            # The book must exist before progress because
            # curriculum_book_progress.book_id is a foreign key.
            self._upsert_curriculum_book(
                connection,
                book,
            )

            connection.execute(
                """
                INSERT INTO curriculum_book_progress
                    (
                        book_id,
                        expected_chunks,
                        completed_chunks,
                        status,
                        updated_at
                    )
                VALUES (?, ?, 0, 'indexing', ?)
                ON CONFLICT(book_id) DO UPDATE SET
                    expected_chunks = excluded.expected_chunks,
                    status = CASE
                        WHEN curriculum_book_progress.status = 'complete'
                        THEN 'complete'
                        ELSE 'indexing'
                    END,
                    updated_at = excluded.updated_at
                """,
                (
                    book["book_id"],
                    int(expected_chunks),
                    now,
                ),
            )

    def update_curriculum_progress(
        self,
        book_id,
        expected_chunks,
        completed_chunks,
        status="indexing",
    ):
        if not self.curriculum_vector_enabled:
            raise RuntimeError(
                "PostgreSQL pgvector is not available "
                "for curriculum indexing."
            )

        if status not in ("indexing", "complete"):
            raise ValueError(
                "Invalid curriculum indexing status."
            )

        now = int(time.time())

        with self.connect() as connection:
            # Safety check:
            # If the book already exists, this is harmless.
            book_exists = connection.execute(
                """
                SELECT 1
                FROM curriculum_books
                WHERE book_id = ?
                """,
                (book_id,),
            ).fetchone()

            if not book_exists:
                raise ValueError(
                    "Cannot update curriculum progress "
                    "because the curriculum book does not exist."
                )

            connection.execute(
                """
                INSERT INTO curriculum_book_progress
                    (
                        book_id,
                        expected_chunks,
                        completed_chunks,
                        status,
                        updated_at
                    )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(book_id) DO UPDATE SET
                    expected_chunks = excluded.expected_chunks,
                    completed_chunks = excluded.completed_chunks,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (
                    book_id,
                    int(expected_chunks),
                    int(completed_chunks),
                    status,
                    now,
                ),
            )

    def index_curriculum_batch(
        self,
        book,
        pages,
    ):
        """
        Saves one batch of curriculum pages/chunks.

        Order:
            1. curriculum_books
            2. curriculum_pages
            3. curriculum_chunks

        Each batch commits independently, allowing indexing
        to resume after an interruption.
        """

        if not self.curriculum_vector_enabled:
            raise RuntimeError(
                "PostgreSQL pgvector is not available "
                "for curriculum indexing."
            )

        inserted_chunk_ids = []

        with self.connect() as connection:
            # ----------------------------------------------------
            # 1. Parent book
            # ----------------------------------------------------
            self._upsert_curriculum_book(
                connection,
                book,
            )

            # ----------------------------------------------------
            # 2. Pages
            # ----------------------------------------------------
            for page in pages:
                connection.execute(
                    """
                    INSERT INTO curriculum_pages
                        (
                            page_id,
                            book_id,
                            page_number,
                            unit,
                            lesson,
                            page_image_data,
                            page_image_mime
                        )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(page_id) DO UPDATE SET
                        book_id = excluded.book_id,
                        page_number = excluded.page_number,
                        unit = excluded.unit,
                        lesson = excluded.lesson,
                        page_image_data =
                            COALESCE(
                                excluded.page_image_data,
                                curriculum_pages.page_image_data
                            ),
                        page_image_mime =
                            COALESCE(
                                excluded.page_image_mime,
                                curriculum_pages.page_image_mime
                            )
                    """,
                    (
                        page["page_id"],
                        book["book_id"],
                        page["page_number"],
                        page.get("unit", ""),
                        page.get("lesson", ""),
                        page.get("page_image_data"),
                        page.get("page_image_mime"),
                    ),
                )

                # ------------------------------------------------
                # 3. Chunks
                # ------------------------------------------------
                for chunk in page["chunks"]:
                    embedding = chunk.get("embedding")

                    if embedding is None:
                        raise ValueError(
                            "Cannot save a curriculum chunk "
                            "without an embedding."
                        )

                    if len(embedding) != 768 or not all(
                        math.isfinite(float(value))
                        for value in embedding
                    ):
                        raise ValueError(
                            "Curriculum embeddings must contain "
                            "768 finite values."
                        )

                    vector = "[" + ",".join(
                        format(float(value), ".9g")
                        for value in embedding
                    ) + "]"

                    cursor = connection.execute(
                        """
                        INSERT INTO curriculum_chunks
                            (
                                chunk_id,
                                book_id,
                                page_id,
                                chunk_index,
                                content,
                                embedding
                            )
                        VALUES (?, ?, ?, ?, ?, ?::vector)
                        ON CONFLICT(chunk_id) DO NOTHING
                        """,
                        (
                            chunk["chunk_id"],
                            book["book_id"],
                            page["page_id"],
                            chunk["chunk_index"],
                            chunk["content"],
                            vector,
                        ),
                    )

                    # Only count the chunk if it was actually inserted.
                    if cursor.rowcount == 1:
                        inserted_chunk_ids.append(
                            chunk["chunk_id"]
                        )

        return inserted_chunk_ids

    def complete_curriculum_indexing(
        self,
        book_id,
        expected_chunks,
        completed_chunks,
    ):
        if not self.curriculum_vector_enabled:
            raise RuntimeError(
                "PostgreSQL pgvector is not available "
                "for curriculum indexing."
            )

        self.update_curriculum_progress(
            book_id=book_id,
            expected_chunks=expected_chunks,
            completed_chunks=completed_chunks,
            status="complete",
        )

    def search_curriculum(
        self,
        embedding,
        grade=None,
        subject=None,
        semester=None,
        unit=None,
        lesson=None,
        official_only=True,
        limit=5,
    ):
        if not self.curriculum_vector_enabled:
            return []

        if len(embedding) != 768 or not all(
            math.isfinite(float(value))
            for value in embedding
        ):
            raise ValueError(
                "Curriculum query embeddings must contain "
                "768 finite values."
            )

        vector = "[" + ",".join(
            format(float(value), ".9g")
            for value in embedding
        ) + "]"

        limit = max(
            1,
            min(int(limit), 20),
        )

        # ------------------------------------------------------------
        # Build filter sets from strictest to most flexible.
        #
        # This prevents a missing lesson/unit metadata value from
        # causing the entire curriculum search to return zero results.
        # ------------------------------------------------------------

        filter_sets = []

        # 1. Exact metadata: grade + subject + semester + unit + lesson
        filter_sets.append(
            {
                "grade": grade,
                "subject": subject,
                "semester": semester,
                "unit": unit,
                "lesson": lesson,
            }
        )

        # 2. Remove lesson
        if lesson:
            filter_sets.append(
                {
                    "grade": grade,
                    "subject": subject,
                    "semester": semester,
                    "unit": unit,
                    "lesson": None,
                }
            )

        # 3. Remove unit
        if unit:
            filter_sets.append(
                {
                    "grade": grade,
                    "subject": subject,
                    "semester": semester,
                    "unit": None,
                    "lesson": None,
                }
            )

        # 4. Remove semester
        if semester:
            filter_sets.append(
                {
                    "grade": grade,
                    "subject": subject,
                    "semester": None,
                    "unit": None,
                    "lesson": None,
                }
            )

        # 5. Keep grade + subject only
        filter_sets.append(
            {
                "grade": grade,
                "subject": subject,
                "semester": None,
                "unit": None,
                "lesson": None,
            }
        )

        # Remove duplicate filter combinations
        unique_filter_sets = []
        seen = set()

        for filters in filter_sets:
            key = (
                filters["grade"],
                filters["subject"],
                filters["semester"],
                filters["unit"],
                filters["lesson"],
            )

            if key not in seen:
                seen.add(key)
                unique_filter_sets.append(filters)

        with self.connect() as connection:

            for filters in unique_filter_sets:
                conditions = []
                parameters = []

                # ----------------------------------------------------
                # Official source
                # ----------------------------------------------------
                if official_only is not None:
                    conditions.append(
                        "books.is_official = ?"
                    )
                    parameters.append(
                        official_only
                    )

                # ----------------------------------------------------
                # Grade
                # ----------------------------------------------------
                if filters["grade"]:
                    conditions.append(
                        "books.grade = ?"
                    )
                    parameters.append(
                        filters["grade"]
                    )

                # ----------------------------------------------------
                # Subject
                # ----------------------------------------------------
                if filters["subject"]:
                    conditions.append(
                        "books.subject = ?"
                    )
                    parameters.append(
                        filters["subject"]
                    )

                # ----------------------------------------------------
                # Semester
                # ----------------------------------------------------
                if filters["semester"]:
                    conditions.append(
                        "books.semester = ?"
                    )
                    parameters.append(
                        filters["semester"]
                    )

                # ----------------------------------------------------
                # Unit
                # ----------------------------------------------------
                if filters["unit"]:
                    conditions.append(
                        "pages.unit ILIKE ?"
                    )
                    parameters.append(
                        f"%{filters['unit']}%"
                    )

                # ----------------------------------------------------
                # Lesson
                # ----------------------------------------------------
                if filters["lesson"]:
                    conditions.append(
                        "pages.lesson ILIKE ?"
                    )
                    parameters.append(
                        f"%{filters['lesson']}%"
                    )

                where_clause = (
                    " AND ".join(conditions)
                    or "TRUE"
                )

                query_parameters = [
                    vector,
                    *parameters,
                    vector,
                    limit,
                ]

                rows = connection.execute(
                    f"""
                    SELECT
                        chunks.chunk_id,
                        chunks.content,

                        1 - (
                            chunks.embedding <=> ?::vector
                        ) AS similarity,

                        books.book_id,
                        books.grade,
                        books.subject,
                        books.semester,
                        books.book_title,
                        books.edition,
                        books.source,
                        books.source_url,
                        books.is_official,

                        pages.page_id,
                        pages.page_number,
                        pages.unit,
                        pages.lesson,
                        pages.page_image_data,
                        pages.page_image_mime

                    FROM curriculum_chunks AS chunks

                    JOIN curriculum_books AS books
                        ON books.book_id = chunks.book_id

                    JOIN curriculum_pages AS pages
                        ON pages.page_id = chunks.page_id

                    WHERE {where_clause}

                    ORDER BY chunks.embedding <=> ?::vector

                    LIMIT ?
                    """,
                    query_parameters,
                ).fetchall()

                if rows:
                    return [
                        dict(row)
                        for row in rows
                    ]

        return []

    # ============================================================
    # SUPPORT / ADMIN
    # ============================================================

    def create_support_message(
        self,
        user,
        category,
        content,
    ):
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO support_messages
                    (
                        user_id,
                        user_name,
                        user_email,
                        category,
                        content,
                        created_at
                    )
                VALUES (?, ?, ?, ?, ?, ?)
                RETURNING id
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

            return cursor.fetchone()["id"]

    def list_support_messages(self):
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    user_name,
                    user_email,
                    category,
                    content,
                    status,
                    created_at,
                    resolved_at
                FROM support_messages
                ORDER BY
                    CASE status
                        WHEN 'new' THEN 0
                        ELSE 1
                    END,
                    created_at DESC,
                    id DESC
                """
            ).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    def set_support_message_status(
        self,
        message_id,
        status,
    ):
        resolved_at = (
            int(time.time())
            if status == "resolved"
            else None
        )

        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE support_messages
                SET status = ?,
                    resolved_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    resolved_at,
                    message_id,
                ),
            )

        return cursor.rowcount > 0

    def is_admin(self, user_id):
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM admin_users
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()

        return row is not None

    def set_user_admin(
        self,
        user_id,
        enabled,
        actor_id,
        primary_admin_email,
    ):
        with self.connect() as connection:
            connection.execute(
                "BEGIN IMMEDIATE"
            )

            user = connection.execute(
                """
                SELECT email
                FROM users
                WHERE id = ?
                """,
                (user_id,),
            ).fetchone()

            if not user:
                connection.rollback()
                return "not_found"

            if user_id == actor_id:
                connection.rollback()
                return "self"

            if (
                primary_admin_email
                and user["email"].casefold()
                == primary_admin_email.casefold()
            ):
                connection.rollback()
                return "primary_admin"

            if enabled:
                connection.execute(
                    """
                    INSERT INTO admin_users
                        (user_id, granted_at)
                    VALUES (?, ?)
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        user_id,
                        int(time.time()),
                    ),
                )
            else:
                connection.execute(
                    """
                    DELETE FROM admin_users
                    WHERE user_id = ?
                    """,
                    (user_id,),
                )

        return "updated"

    def delete_user(
        self,
        user_id,
        primary_admin_email="",
        actor_is_primary_admin=False,
    ):
        with self.connect() as connection:
            connection.execute(
                "BEGIN IMMEDIATE"
            )

            user = connection.execute(
                """
                SELECT email
                FROM users
                WHERE id = ?
                """,
                (user_id,),
            ).fetchone()

            if not user:
                connection.rollback()
                return "not_found"

            if (
                primary_admin_email
                and user["email"].casefold()
                == primary_admin_email.casefold()
            ):
                connection.rollback()
                return "primary_admin"

            target_is_admin = (
                connection.execute(
                    """
                    SELECT 1
                    FROM admin_users
                    WHERE user_id = ?
                    """,
                    (user_id,),
                ).fetchone()
                or (
                    primary_admin_email
                    and user["email"].casefold()
                    == primary_admin_email.casefold()
                )
            )

            if target_is_admin and not actor_is_primary_admin:
                connection.rollback()
                return "target_admin"

            connection.execute(
                """
                DELETE FROM users
                WHERE id = ?
                """,
                (user_id,),
            )

        return "deleted"

    def admin_set_password(
        self,
        user_id,
        new_password,
        primary_admin_email="",
        actor_is_primary_admin=False,
    ):
        with self.connect() as connection:
            connection.execute(
                "BEGIN IMMEDIATE"
            )

            user = connection.execute(
                """
                SELECT email
                FROM users
                WHERE id = ?
                """,
                (user_id,),
            ).fetchone()

            if not user:
                connection.rollback()
                return "not_found"

            target_is_admin = (
                connection.execute(
                    """
                    SELECT 1
                    FROM admin_users
                    WHERE user_id = ?
                    """,
                    (user_id,),
                ).fetchone()
                or (
                    primary_admin_email
                    and user["email"].casefold()
                    == primary_admin_email.casefold()
                )
            )

            if target_is_admin and not actor_is_primary_admin:
                connection.rollback()
                return "target_admin"

            cursor = connection.execute(
                """
                UPDATE users
                SET password_hash = ?
                WHERE id = ?
                """,
                (
                    self.hash_password(new_password),
                    user_id,
                ),
            )

            if cursor.rowcount != 1:
                connection.rollback()
                return "not_found"

            connection.execute(
                """
                DELETE FROM sessions
                WHERE user_id = ?
                """,
                (user_id,),
            )

        return "updated"

    # ============================================================
    # STUDENT
    # ============================================================

    def get_student_preferences(self, user_id):
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT grade, grade_question_asked
                FROM users
                WHERE id = ?
                """,
                (user_id,),
            ).fetchone()

        if not row:
            return None

        return {
            "grade": row["grade"],
            "grade_question_asked": bool(
                row["grade_question_asked"]
            ),
        }

    def update_student_grade(
        self,
        user_id,
        grade,
    ):
        with self.connect() as connection:
            row = connection.execute(
                """
                UPDATE users
                SET grade = ?,
                    grade_question_asked = 1
                WHERE id = ?
                RETURNING grade, grade_question_asked
                """,
                (
                    grade,
                    user_id,
                ),
            ).fetchone()

        if not row:
            return None

        return {
            "grade": row["grade"],
            "grade_question_asked": bool(row["grade_question_asked"]),
        }

    # ============================================================
    # SESSIONS
    # ============================================================

    @staticmethod
    def hash_session(token):
        return hashlib.sha256(
            token.encode("utf-8")
        ).hexdigest()

    def create_session(
        self,
        user_id,
        lifetime=SESSION_LIFETIME_SECONDS,
    ):
        token = secrets.token_urlsafe(32)

        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO sessions
                    (
                        token_hash,
                        user_id,
                        expires_at
                    )
                VALUES (?, ?, ?)
                """,
                (
                    self.hash_session(token),
                    user_id,
                    int(time.time()) + lifetime,
                ),
            )

            connection.execute(
                """
                DELETE FROM sessions
                WHERE expires_at <= ?
                """,
                (int(time.time()),),
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
                JOIN users
                    ON users.id = sessions.user_id
                WHERE sessions.token_hash = ?
                  AND sessions.expires_at > ?
                """,
                (
                    self.hash_session(token),
                    int(time.time()),
                ),
            ).fetchone()

        return (
            self.public_user(row)
            if row
            else None
        )

    def delete_session(self, token):
        if token:
            with self.connect() as connection:
                connection.execute(
                    """
                    DELETE FROM sessions
                    WHERE token_hash = ?
                    """,
                    (self.hash_session(token),),
                )

    # ============================================================
    # CONVERSATIONS
    # ============================================================

    def list_conversations(self, user_id):
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    title,
                    created_at,
                    updated_at
                FROM conversations
                WHERE user_id = ?
                ORDER BY updated_at DESC, id DESC
                """,
                (user_id,),
            ).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    @staticmethod
    def is_placeholder_title(title):
        return title == "محادثة جديدة" or (
            title.startswith(
                "محادثة جديدة ("
            )
            and title.endswith(")")
        )

    @staticmethod
    def unique_conversation_title(
        connection,
        user_id,
        title,
        exclude_id=None,
    ):
        base_title = (
            " ".join(title.split())[:80].rstrip()
            or "محادثة جديدة"
        )

        candidate = base_title
        suffix_number = 2

        while True:
            query = """
                SELECT 1
                FROM conversations
                WHERE user_id = ?
                  AND lower(title) = lower(?)
            """

            parameters = [
                user_id,
                candidate,
            ]

            if exclude_id:
                query += " AND id != ?"
                parameters.append(exclude_id)

            if not connection.execute(
                query,
                parameters,
            ).fetchone():
                return candidate

            suffix = f" ({suffix_number})"

            candidate = (
                f"{base_title[:80 - len(suffix)].rstrip()}"
                f"{suffix}"
            )

            suffix_number += 1

    def prepare_user_message(
        self,
        user_id,
        conversation_id,
        title,
        content,
        image_mime,
        image_data,
    ):
        now = int(time.time())

        with self.connect() as connection:
            connection.execute(
                "BEGIN IMMEDIATE"
            )

            title_source = ""
            title_needs_ai = False
            is_new_conversation = not conversation_id

            if conversation_id:
                conversation = connection.execute(
                    """
                    SELECT
                        id,
                        title,
                        response_id
                    FROM conversations
                    WHERE id = ?
                      AND user_id = ?
                    """,
                    (
                        conversation_id,
                        user_id,
                    ),
                ).fetchone()

                if not conversation:
                    return None

                if (
                    self.is_placeholder_title(
                        conversation["title"]
                    )
                    and not self.is_placeholder_title(title)
                ):
                    title_source = content
                    title_needs_ai = True

                    title = self.unique_conversation_title(
                        connection,
                        user_id,
                        title,
                        conversation_id,
                    )

                    connection.execute(
                        """
                        UPDATE conversations
                        SET title = ?
                        WHERE id = ?
                        """,
                        (
                            title,
                            conversation_id,
                        ),
                    )

                    conversation = {
                        "id": conversation["id"],
                        "title": title,
                        "response_id": conversation["response_id"],
                    }

            else:
                conversation_id = uuid4().hex

                title_needs_ai = (
                    not self.is_placeholder_title(title)
                )

                title_source = (
                    content
                    if title_needs_ai
                    else ""
                )

                title = self.unique_conversation_title(
                    connection,
                    user_id,
                    title,
                )

                connection.execute(
                    """
                    INSERT INTO conversations
                        (
                            id,
                            user_id,
                            title,
                            created_at,
                            updated_at
                        )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        conversation_id,
                        user_id,
                        title,
                        now,
                        now,
                    ),
                )

                conversation = {
                    "id": conversation_id,
                    "title": title,
                    "response_id": None,
                }

            inserted_message = connection.execute(
                """
                INSERT INTO messages
                    (
                        conversation_id,
                        role,
                        content,
                        image_mime,
                        image_data,
                        created_at
                    )
                VALUES (?, 'user', ?, ?, ?, ?)
                RETURNING id
                """,
                (
                    conversation_id,
                    content,
                    image_mime,
                    image_data,
                    now,
                ),
            )

            message_id = inserted_message.fetchone()["id"]

            if not is_new_conversation:
                connection.execute(
                    """
                    UPDATE conversations
                    SET updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        now,
                        conversation_id,
                    ),
                )

        return {
            "id": conversation_id,
            "message_id": message_id,
            "title": conversation["title"],
            "response_id": conversation["response_id"],
            "title_source": title_source,
            "title_needs_ai": title_needs_ai,
        }

    def set_conversation_title(
        self,
        user_id,
        conversation_id,
        title,
    ):
        with self.connect() as connection:
            connection.execute(
                "BEGIN IMMEDIATE"
            )

            conversation = connection.execute(
                """
                SELECT 1
                FROM conversations
                WHERE id = ?
                  AND user_id = ?
                """,
                (
                    conversation_id,
                    user_id,
                ),
            ).fetchone()

            if not conversation:
                connection.rollback()
                return None

            unique_title = self.unique_conversation_title(
                connection,
                user_id,
                title,
                conversation_id,
            )

            connection.execute(
                """
                UPDATE conversations
                SET title = ?,
                    updated_at = ?
                WHERE id = ?
                  AND user_id = ?
                """,
                (
                    unique_title,
                    int(time.time()),
                    conversation_id,
                    user_id,
                ),
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
                INSERT INTO messages
                    (
                        conversation_id,
                        role,
                        content,
                        created_at
                    )
                VALUES (?, 'assistant', ?, ?)
                """,
                (
                    conversation_id,
                    content,
                    now,
                ),
            )

            connection.execute(
                """
                UPDATE conversations
                SET response_id = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    response_id,
                    now,
                    conversation_id,
                ),
            )

            if user_id and grade_question_asked:
                connection.execute(
                    """
                    UPDATE users
                    SET grade_question_asked = 1
                    WHERE id = ?
                    """,
                    (user_id,),
                )

    def get_conversation(
        self,
        user_id,
        conversation_id,
    ):
        with self.connect() as connection:
            conversation = connection.execute(
                """
                SELECT
                    id,
                    title,
                    created_at,
                    updated_at
                FROM conversations
                WHERE id = ?
                  AND user_id = ?
                """,
                (
                    conversation_id,
                    user_id,
                ),
            ).fetchone()

            if not conversation:
                return None

            messages = connection.execute(
                """
                SELECT
                    id,
                    role,
                    content,
                    image_mime,
                    image_data,
                    created_at
                FROM messages
                WHERE conversation_id = ?
                ORDER BY id
                """,
                (conversation_id,),
            ).fetchall()

        return dict(conversation), messages

    def get_conversation_context(
        self,
        user_id,
        conversation_id,
    ):
        with self.connect() as connection:
            messages = connection.execute(
                """
                SELECT
                    messages.id,
                    messages.role,
                    messages.content,
                    messages.image_mime,
                    messages.image_data IS NOT NULL
                        AS has_image,
                    COALESCE(
                        length(messages.image_data),
                        0
                    ) AS image_size
                FROM messages
                JOIN conversations
                    ON conversations.id =
                       messages.conversation_id
                WHERE conversations.id = ?
                  AND conversations.user_id = ?
                ORDER BY messages.id
                """,
                (
                    conversation_id,
                    user_id,
                ),
            ).fetchall()

        return messages or None

    def get_conversation_images(
        self,
        user_id,
        conversation_id,
        message_ids,
    ):
        if not message_ids:
            return {}

        placeholders = ", ".join(
            "?"
            for _ in message_ids
        )

        with self.connect() as connection:
            images = connection.execute(
                f"""
                SELECT
                    messages.id,
                    messages.image_mime,
                    messages.image_data
                FROM messages
                JOIN conversations
                    ON conversations.id =
                       messages.conversation_id
                WHERE conversations.id = ?
                  AND conversations.user_id = ?
                  AND messages.role = 'user'
                  AND messages.image_data IS NOT NULL
                  AND messages.id IN ({placeholders})
                """,
                (
                    conversation_id,
                    user_id,
                    *message_ids,
                ),
            ).fetchall()

        return {
            image["id"]: image
            for image in images
        }

    def rename_conversation(
        self,
        user_id,
        conversation_id,
        title,
    ):
        with self.connect() as connection:
            connection.execute(
                "BEGIN IMMEDIATE"
            )

            unique_title = self.unique_conversation_title(
                connection,
                user_id,
                title,
                conversation_id,
            )

            result = connection.execute(
                """
                UPDATE conversations
                SET title = ?,
                    updated_at = ?
                WHERE id = ?
                  AND user_id = ?
                """,
                (
                    unique_title,
                    int(time.time()),
                    conversation_id,
                    user_id,
                ),
            )

        return (
            unique_title
            if result.rowcount == 1
            else None
        )

    def delete_conversation(
        self,
        user_id,
        conversation_id,
    ):
        with self.connect() as connection:
            result = connection.execute(
                """
                DELETE FROM conversations
                WHERE id = ?
                  AND user_id = ?
                """,
                (
                    conversation_id,
                    user_id,
                ),
            )

        return result.rowcount == 1