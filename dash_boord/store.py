import json
import sys
import time
from datetime import datetime, timedelta, timezone


SUPPORT_STATES = {"new", "in_progress", "resolved"}
PAGE_SIZE_DEFAULT = 25
PAGE_SIZE_MAX = 100


class DashboardStore:
    def __init__(self, database, primary_admin_email):
        self.database = database
        self.primary_admin_email = primary_admin_email.strip().casefold()
        self.initialize()

    def initialize(self):
        serial_type = "BIGSERIAL" if self.database.is_postgres else "INTEGER"
        support_id_type = "BIGINT" if self.database.is_postgres else "INTEGER"
        statements = (
            f"""CREATE TABLE IF NOT EXISTS admin_audit_logs (
                id {serial_type} PRIMARY KEY,
                actor_user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
                actor_email TEXT NOT NULL,
                action TEXT NOT NULL,
                target_user_id TEXT,
                target_email TEXT,
                target_support_message_id {support_id_type},
                details_json TEXT NOT NULL DEFAULT '{{}}',
                created_at INTEGER NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS admin_audit_created_idx ON admin_audit_logs(created_at DESC, id DESC)",
            "CREATE INDEX IF NOT EXISTS admin_audit_actor_idx ON admin_audit_logs(actor_user_id, created_at DESC)",
            f"""CREATE TABLE IF NOT EXISTS admin_support_workflow (
                message_id {support_id_type} PRIMARY KEY
                    REFERENCES support_messages(id) ON DELETE CASCADE,
                status TEXT NOT NULL CHECK(status IN ('new', 'in_progress', 'resolved')),
                updated_by TEXT REFERENCES users(id) ON DELETE SET NULL,
                updated_at INTEGER NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS admin_support_workflow_status_idx ON admin_support_workflow(status, updated_at DESC)",
            f"""CREATE TABLE IF NOT EXISTS admin_announcements (
                id {serial_type} PRIMARY KEY,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                is_published INTEGER NOT NULL DEFAULT 0,
                created_by TEXT REFERENCES users(id) ON DELETE SET NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS admin_announcements_published_idx ON admin_announcements(is_published, updated_at DESC)",
            "CREATE INDEX IF NOT EXISTS users_created_at_idx ON users(created_at DESC)",
            "CREATE INDEX IF NOT EXISTS conversations_created_at_idx ON conversations(created_at DESC)",
            "CREATE INDEX IF NOT EXISTS messages_created_at_idx ON messages(created_at DESC)",
            "CREATE TABLE IF NOT EXISTS site_visit_events (id BIGSERIAL PRIMARY KEY, visitor_hash TEXT NOT NULL REFERENCES site_visitors(visitor_hash) ON DELETE CASCADE, visited_at INTEGER NOT NULL)",
            "CREATE INDEX IF NOT EXISTS site_visit_events_time_idx ON site_visit_events(visited_at)",
        )
        if not self.database.is_postgres:
            statements = tuple(
                statement.replace("BIGSERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
                .replace("id INTEGER PRIMARY KEY,", "id INTEGER PRIMARY KEY AUTOINCREMENT,")
                for statement in statements
            )
        with self.database.connect() as connection:
            for statement in statements:
                connection.execute(statement)

    def is_admin(self, user):
        return bool(
            user
            and (
                user["email"].casefold() == self.primary_admin_email
                or self.database.is_admin(user["id"])
            )
        )

    @staticmethod
    def _page(page, page_size):
        try:
            page = max(1, int(page))
        except (TypeError, ValueError):
            page = 1
        try:
            page_size = max(1, min(int(page_size), PAGE_SIZE_MAX))
        except (TypeError, ValueError):
            page_size = PAGE_SIZE_DEFAULT
        return page, page_size, (page - 1) * page_size

    def _audit(self, connection, actor, action, target_user_id=None,
               target_email=None, support_message_id=None, details=None):
        connection.execute(
            """INSERT INTO admin_audit_logs
                (actor_user_id, actor_email, action, target_user_id,
                 target_email, target_support_message_id, details_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                actor["id"],
                actor["email"],
                action,
                target_user_id,
                target_email,
                support_message_id,
                json.dumps(details or {}, ensure_ascii=False, separators=(",", ":")),
                int(time.time()),
            ),
        )

    def log_action(self, actor, action, details=None):
        with self.database.connect() as connection:
            self._audit(connection, actor, action, details=details)

    def set_admin_role(self, actor, user_id, enabled):
        with self.database.connect() as connection:
            target = connection.execute(
                "SELECT id, email FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if not target:
                return "not_found"
            if user_id == actor["id"]:
                return "self"
            is_primary = target["email"].casefold() == self.primary_admin_email
            if is_primary:
                return "primary_admin"
            target_is_admin = connection.execute(
                "SELECT 1 FROM admin_users WHERE user_id = ?", (user_id,)
            ).fetchone()
            actor_is_primary = actor["email"].casefold() == self.primary_admin_email
            if target_is_admin and not actor_is_primary:
                return "target_admin"
            if enabled:
                connection.execute(
                    "INSERT INTO admin_users(user_id, granted_at) VALUES (?, ?) ON CONFLICT DO NOTHING",
                    (user_id, int(time.time())),
                )
                action = "admin_granted"
            else:
                connection.execute("DELETE FROM admin_users WHERE user_id = ?", (user_id,))
                action = "admin_revoked"
            self._audit(
                connection, actor, action, target_user_id=user_id,
                target_email=target["email"], details={"is_admin": bool(enabled)},
            )
        return "updated"

    def delete_user(self, actor, user_id):
        with self.database.connect() as connection:
            target = connection.execute(
                "SELECT id, email FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if not target:
                return "not_found"
            is_primary = target["email"].casefold() == self.primary_admin_email
            if is_primary:
                return "primary_admin"
            target_is_admin = connection.execute(
                "SELECT 1 FROM admin_users WHERE user_id = ?", (user_id,)
            ).fetchone()
            if target_is_admin and actor["email"].casefold() != self.primary_admin_email:
                return "target_admin"
            self._audit(
                connection, actor, "user_deleted", target_user_id=user_id,
                target_email=target["email"],
            )
            connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
        return "deleted"

    def set_user_password(self, actor, user_id, new_password):
        with self.database.connect() as connection:
            target = connection.execute(
                "SELECT id, email FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if not target:
                return "not_found"
            if user_id == actor["id"]:
                return "self"
            is_primary = target["email"].casefold() == self.primary_admin_email
            target_is_admin = connection.execute(
                "SELECT 1 FROM admin_users WHERE user_id = ?", (user_id,)
            ).fetchone()
            if (is_primary or target_is_admin) and actor["email"].casefold() != self.primary_admin_email:
                return "target_admin"
            password_hash = self.database.hash_password(new_password)
            connection.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (password_hash, user_id),
            )
            connection.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            self._audit(
                connection, actor, "user_password_changed", target_user_id=user_id,
                target_email=target["email"],
            )
        return "updated"

    def list_users(self, page=1, page_size=PAGE_SIZE_DEFAULT, query="",
                   role="all", sort="created_desc"):
        page, page_size, offset = self._page(page, page_size)
        query = (query or "").strip().casefold()[:200]
        role = role if role in {"all", "admins", "users"} else "all"
        sort_columns = {
            "created_desc": "users.created_at DESC, users.id",
            "created_asc": "users.created_at ASC, users.id",
            "activity_desc": "COALESCE(activity.last_activity, users.created_at) DESC, users.id",
        }
        order_by = sort_columns.get(sort, sort_columns["created_desc"])
        where = []
        parameters = []
        if query:
            where.append("(LOWER(users.name) LIKE ? OR LOWER(users.email) LIKE ?)")
            pattern = f"%{query}%"
            parameters.extend((pattern, pattern))
        admin_expression = "(admin_users.user_id IS NOT NULL OR LOWER(users.email) = LOWER(?))"
        if role == "admins":
            where.append(admin_expression)
            parameters.append(self.primary_admin_email)
        elif role == "users":
            where.append(f"NOT {admin_expression}")
            parameters.append(self.primary_admin_email)
        where_sql = " WHERE " + " AND ".join(where) if where else ""
        with self.database.connect() as connection:
            total = connection.execute(
                "SELECT COUNT(*) AS total FROM users LEFT JOIN admin_users ON admin_users.user_id = users.id" + where_sql,
                parameters,
            ).fetchone()["total"]
            rows = connection.execute(
                f"""WITH activity AS (
                    SELECT conversations.user_id,
                           MAX(messages.created_at) AS last_activity,
                           COUNT(DISTINCT conversations.id) AS conversation_count,
                           COUNT(messages.id) AS message_count
                    FROM conversations
                    LEFT JOIN messages ON messages.conversation_id = conversations.id
                    GROUP BY conversations.user_id
                )
                SELECT users.id, users.name, users.email, users.created_at,
                       CASE WHEN {admin_expression} THEN 1 ELSE 0 END AS is_admin,
                       CASE WHEN LOWER(users.email) = LOWER(?) THEN 1 ELSE 0 END AS is_primary_admin,
                       activity.last_activity,
                       COALESCE(activity.conversation_count, 0) AS conversation_count,
                       COALESCE(activity.message_count, 0) AS message_count
                FROM users
                LEFT JOIN admin_users ON admin_users.user_id = users.id
                LEFT JOIN activity ON activity.user_id = users.id
                {where_sql}
                ORDER BY {order_by}
                LIMIT ? OFFSET ?""",
                [self.primary_admin_email, self.primary_admin_email, *parameters, page_size, offset],
            ).fetchall()
        return {
            "users": [dict(row) for row in rows],
            "total": total,
            "page": page,
            "pageSize": page_size,
            "pages": max(1, (total + page_size - 1) // page_size),
        }

    def user_detail(self, user_id):
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT users.id, users.name, users.email, users.picture,
                          users.created_at,
                          CASE WHEN admin_users.user_id IS NOT NULL OR LOWER(users.email) = LOWER(?) THEN 1 ELSE 0 END AS is_admin,
                          CASE WHEN LOWER(users.email) = LOWER(?) THEN 1 ELSE 0 END AS is_primary_admin,
                          COUNT(DISTINCT conversations.id) AS conversation_count,
                          COUNT(messages.id) AS message_count,
                          MAX(messages.created_at) AS last_activity
                   FROM users
                   LEFT JOIN admin_users ON admin_users.user_id = users.id
                   LEFT JOIN conversations ON conversations.user_id = users.id
                   LEFT JOIN messages ON messages.conversation_id = conversations.id
                   WHERE users.id = ?
                   GROUP BY users.id, admin_users.user_id""",
                (self.primary_admin_email, self.primary_admin_email, user_id),
            ).fetchone()
        return dict(row) if row else None

    def dashboard_summary(self):
        now = datetime.now(timezone.utc)
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week = today - timedelta(days=today.weekday())
        month = today.replace(day=1)
        since_30d = int((now - timedelta(days=30)).timestamp())
        today_ts, week_ts, month_ts = int(today.timestamp()), int(week.timestamp()), int(month.timestamp())
        series_start = int((today - timedelta(days=13)).timestamp())
        with self.database.connect() as connection:
            stats = connection.execute(
                "SELECT page_views, unique_visitors FROM site_statistics WHERE id = 1"
            ).fetchone()
            counts = connection.execute(
                """SELECT
                    (SELECT COUNT(*) FROM users) AS users,
                    (SELECT COUNT(*) FROM admin_users) AS assigned_admins,
                    (SELECT COUNT(*) FROM conversations) AS conversations,
                    (SELECT COUNT(*) FROM messages) AS messages,
                    (SELECT COUNT(DISTINCT conversations.user_id) FROM conversations) AS users_used,
                    (SELECT COUNT(DISTINCT conversations.user_id) FROM conversations JOIN messages ON messages.conversation_id = conversations.id WHERE messages.role = 'user' AND messages.created_at >= ?) AS active_users_30d,
                    (SELECT COUNT(*) FROM users WHERE created_at >= ?) AS users_today,
                    (SELECT COUNT(*) FROM users WHERE created_at >= ?) AS users_week,
                    (SELECT COUNT(*) FROM users WHERE created_at >= ?) AS users_month,
                    (SELECT COUNT(*) FROM conversations WHERE created_at >= ?) AS conversations_today,
                    (SELECT COUNT(*) FROM conversations WHERE created_at >= ?) AS conversations_week,
                    (SELECT COUNT(*) FROM conversations WHERE created_at >= ?) AS conversations_month,
                    (SELECT COUNT(*) FROM messages WHERE created_at >= ?) AS messages_today,
                    (SELECT COUNT(*) FROM messages WHERE created_at >= ?) AS messages_week,
                    (SELECT COUNT(*) FROM messages WHERE created_at >= ?) AS messages_month,
                    (SELECT AVG(message_count) FROM (SELECT COUNT(*) AS message_count FROM messages GROUP BY conversation_id) AS per_conversation) AS avg_messages_per_conversation,
                          (SELECT COUNT(*) FROM support_messages
                              LEFT JOIN admin_support_workflow AS workflow ON workflow.message_id = support_messages.id
                              WHERE COALESCE(workflow.status, support_messages.status) = 'new') AS new_support,
                          (SELECT COUNT(*) FROM users
                              LEFT JOIN admin_users ON admin_users.user_id = users.id
                              WHERE admin_users.user_id IS NOT NULL OR LOWER(users.email) = LOWER(?)) AS admins""",
                (since_30d, today_ts, week_ts, month_ts,
                 today_ts, week_ts, month_ts,
                      today_ts, week_ts, month_ts, self.primary_admin_email),
            ).fetchone()
            visit_counts = connection.execute(
                """SELECT
                    COUNT(*) FILTER (WHERE visited_at >= ?) AS today,
                    COUNT(*) FILTER (WHERE visited_at >= ?) AS week,
                    COUNT(*) FILTER (WHERE visited_at >= ?) AS month,
                    COUNT(DISTINCT visitor_hash) FILTER (WHERE visited_at >= ?) AS unique_today,
                    COUNT(DISTINCT visitor_hash) FILTER (WHERE visited_at >= ?) AS unique_week,
                    COUNT(DISTINCT visitor_hash) FILTER (WHERE visited_at >= ?) AS unique_month
                   FROM site_visit_events WHERE visited_at >= ?""",
                (today_ts, week_ts, month_ts, today_ts, week_ts, month_ts, month_ts),
            ).fetchone()
            if self.database.is_postgres:
                hours = connection.execute(
                    """SELECT EXTRACT(HOUR FROM to_timestamp(created_at))::INTEGER AS hour,
                              COUNT(*) AS messages
                       FROM messages WHERE created_at >= ?
                       GROUP BY hour ORDER BY hour""",
                    (since_30d,),
                ).fetchall()
                days = connection.execute(
                    """SELECT to_timestamp(created_at)::date AS day, COUNT(*) AS messages
                       FROM messages WHERE created_at >= ?
                       GROUP BY day ORDER BY messages DESC, day DESC LIMIT 1""",
                    (since_30d,),
                ).fetchall()
            else:
                hours = connection.execute(
                    """SELECT CAST(strftime('%H', created_at, 'unixepoch') AS INTEGER) AS hour,
                              COUNT(*) AS messages
                       FROM messages WHERE created_at >= ?
                       GROUP BY hour ORDER BY hour""",
                    (since_30d,),
                ).fetchall()
                days = connection.execute(
                    """SELECT date(created_at, 'unixepoch') AS day, COUNT(*) AS messages
                       FROM messages WHERE created_at >= ?
                       GROUP BY day ORDER BY messages DESC, day DESC LIMIT 1""",
                    (since_30d,),
                ).fetchall()
            if self.database.is_postgres:
                signup_rows = connection.execute(
                    """SELECT to_timestamp(created_at)::date AS day, COUNT(*) AS count
                       FROM users WHERE created_at >= ? GROUP BY day""",
                    (series_start,),
                ).fetchall()
                visit_rows = connection.execute(
                    """SELECT to_timestamp(visited_at)::date AS day, COUNT(*) AS count
                       FROM site_visit_events WHERE visited_at >= ? GROUP BY day""",
                    (series_start,),
                ).fetchall()
            else:
                signup_rows = connection.execute(
                    """SELECT date(created_at, 'unixepoch') AS day, COUNT(*) AS count
                       FROM users WHERE created_at >= ? GROUP BY day""",
                    (series_start,),
                ).fetchall()
                visit_rows = connection.execute(
                    """SELECT date(visited_at, 'unixepoch') AS day, COUNT(*) AS count
                       FROM site_visit_events WHERE visited_at >= ? GROUP BY day""",
                    (series_start,),
                ).fetchall()
        signup_by_day = {str(row["day"]): row["count"] for row in signup_rows}
        visits_by_day = {str(row["day"]): row["count"] for row in visit_rows}
        daily_series = []
        for index in range(14):
            day = (today - timedelta(days=13 - index)).date().isoformat()
            daily_series.append({
                "day": day,
                "users": signup_by_day.get(day, 0),
                "visits": visits_by_day.get(day, 0),
            })
        summary = dict(counts)
        summary.update({
            "page_views": stats["page_views"] if stats else 0,
            "unique_visitors": stats["unique_visitors"] if stats else 0,
            "visits_today": visit_counts["today"],
            "visits_week": visit_counts["week"],
            "visits_month": visit_counts["month"],
            "unique_today": visit_counts["unique_today"],
            "unique_week": visit_counts["unique_week"],
            "unique_month": visit_counts["unique_month"],
            "messages_per_user": round(summary_value / max(1, counts["users_used"]), 2)
                if (summary_value := counts["messages"]) else 0,
            "busy_hours": [dict(row) for row in hours],
            "most_active_day": dict(days[0]) if days else None,
            "daily_series": daily_series,
        })
        return summary

    def support_messages(self, page=1, page_size=PAGE_SIZE_DEFAULT, query="",
                         status="all", category="all"):
        page, page_size, offset = self._page(page, page_size)
        query = (query or "").strip().casefold()[:200]
        status = status if status in SUPPORT_STATES | {"all"} else "all"
        category = category if category in {"all", "message", "complaint"} else "all"
        state_expr = "COALESCE(workflow.status, support_messages.status)"
        where, parameters = [], []
        if status != "all":
            where.append(f"{state_expr} = ?")
            parameters.append(status)
        if category != "all":
            where.append("support_messages.category = ?")
            parameters.append(category)
        if query:
            where.append("(LOWER(support_messages.user_name) LIKE ? OR LOWER(support_messages.user_email) LIKE ? OR LOWER(support_messages.content) LIKE ?)")
            pattern = f"%{query}%"
            parameters.extend((pattern, pattern, pattern))
        where_sql = " WHERE " + " AND ".join(where) if where else ""
        with self.database.connect() as connection:
            total = connection.execute(
                "SELECT COUNT(*) AS total FROM support_messages LEFT JOIN admin_support_workflow AS workflow ON workflow.message_id = support_messages.id" + where_sql,
                parameters,
            ).fetchone()["total"]
            rows = connection.execute(
                f"""SELECT support_messages.id, support_messages.user_id,
                           support_messages.user_name, support_messages.user_email,
                           support_messages.category, support_messages.content,
                           {state_expr} AS status,
                           support_messages.created_at,
                           COALESCE(workflow.updated_at, support_messages.resolved_at) AS updated_at
                    FROM support_messages
                    LEFT JOIN admin_support_workflow AS workflow ON workflow.message_id = support_messages.id
                    {where_sql}
                    ORDER BY CASE {state_expr} WHEN 'new' THEN 0 WHEN 'in_progress' THEN 1 ELSE 2 END,
                             support_messages.created_at DESC, support_messages.id DESC
                    LIMIT ? OFFSET ?""",
                [*parameters, page_size, offset],
            ).fetchall()
        return {
            "messages": [dict(row) for row in rows],
            "total": total,
            "page": page,
            "pageSize": page_size,
            "pages": max(1, (total + page_size - 1) // page_size),
        }

    def set_support_status(self, actor, message_id, status):
        if status not in SUPPORT_STATES:
            return "invalid_status"
        now = int(time.time())
        with self.database.connect() as connection:
            message = connection.execute(
                "SELECT id FROM support_messages WHERE id = ?", (message_id,)
            ).fetchone()
            if not message:
                return "not_found"
            connection.execute(
                """INSERT INTO admin_support_workflow(message_id, status, updated_by, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(message_id) DO UPDATE SET status = excluded.status,
                       updated_by = excluded.updated_by, updated_at = excluded.updated_at""",
                (message_id, status, actor["id"], now),
            )
            if status in {"new", "resolved"}:
                connection.execute(
                    "UPDATE support_messages SET status = ?, resolved_at = ? WHERE id = ?",
                    (status, now if status == "resolved" else None, message_id),
                )
            self._audit(
                connection, actor, "support_status_changed",
                support_message_id=message_id, details={"status": status},
            )
        return "updated"

    def audit_logs(self, page=1, page_size=PAGE_SIZE_DEFAULT):
        page, page_size, offset = self._page(page, page_size)
        with self.database.connect() as connection:
            total = connection.execute("SELECT COUNT(*) AS total FROM admin_audit_logs").fetchone()["total"]
            rows = connection.execute(
                """SELECT id, actor_email, action, target_user_id, target_email,
                          target_support_message_id, details_json, created_at
                   FROM admin_audit_logs ORDER BY id DESC LIMIT ? OFFSET ?""",
                (page_size, offset),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["details"] = json.loads(item.pop("details_json"))
            except (TypeError, json.JSONDecodeError):
                item["details"] = {}
            result.append(item)
        return {"logs": result, "total": total, "page": page, "pageSize": page_size,
                "pages": max(1, (total + page_size - 1) // page_size)}

    def announcements(self):
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT id, title, body, is_published, created_by, created_at, updated_at
                   FROM admin_announcements ORDER BY updated_at DESC, id DESC"""
            ).fetchall()
        return [dict(row) for row in rows]

    def save_announcement(self, actor, title, body, published, announcement_id=None):
        title = title.strip()
        body = body.strip()
        if not title or len(title) > 160 or not body or len(body) > 5000:
            return "invalid"
        now = int(time.time())
        with self.database.connect() as connection:
            if announcement_id:
                cursor = connection.execute(
                    """UPDATE admin_announcements SET title = ?, body = ?, is_published = ?, updated_at = ? WHERE id = ?""",
                    (title, body, int(published), now, announcement_id),
                )
                if cursor.rowcount == 0:
                    return "not_found"
                action = "announcement_updated"
                target_id = announcement_id
            else:
                cursor = connection.execute(
                    """INSERT INTO admin_announcements(title, body, is_published, created_by, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?) RETURNING id""",
                    (title, body, int(published), actor["id"], now, now),
                )
                target_id = cursor.fetchone()["id"]
                action = "announcement_created"
            self._audit(connection, actor, action, details={"announcement_id": target_id})
        return target_id

    def delete_announcement(self, actor, announcement_id):
        with self.database.connect() as connection:
            cursor = connection.execute("DELETE FROM admin_announcements WHERE id = ?", (announcement_id,))
            if cursor.rowcount == 0:
                return False
            self._audit(connection, actor, "announcement_deleted", details={"announcement_id": announcement_id})
        return True

    def system_health(self, started_at):
        started = time.perf_counter()
        with self.database.connect() as connection:
            connection.execute("SELECT 1").fetchone()
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            if self.database.is_postgres:
                connections = connection.execute(
                    "SELECT COUNT(*) AS count FROM pg_stat_activity WHERE datname = current_database()"
                ).fetchone()["count"]
                size_bytes = connection.execute(
                    "SELECT pg_database_size(current_database()) AS bytes"
                ).fetchone()["bytes"]
            else:
                connections = None
                size_bytes = None
        return {
            "database": "connected",
            "databaseLatencyMs": latency_ms,
            "databaseConnections": connections,
            "databaseSizeBytes": size_bytes,
            "uptimeSeconds": max(0, int(time.monotonic() - started_at)),
            "pythonVersion": sys.version.split()[0],
        }