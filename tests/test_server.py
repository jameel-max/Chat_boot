import base64
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import server


class ChatApiTests(unittest.TestCase):
    def setUp(self):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.ChatHandler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.httpd.server_port}"
        self.temp_directory = tempfile.TemporaryDirectory()
        self.previous_database = server.database
        server.database = server.Database(
            Path(self.temp_directory.name) / "test.sqlite3"
        )
        self.user = server.database.register_user(
            "student@example.com", "correct-horse-battery"
        )
        self.session_token = server.database.create_session(self.user["id"])
        self.env = patch.dict(
            server.os.environ,
            {"GEMINI_API_KEY": "test-key"},
        )
        self.env.start()
        self.api = patch("server.urlopen")
        self.mock_urlopen = self.api.start()
        self.gemini_prewarm = patch.object(
            server.ChatHandler, "start_gemini_prewarm"
        )
        self.gemini_prewarm.start()
        self.gemini_stream = patch.object(
            server.ChatHandler,
            "open_gemini_stream",
            autospec=True,
            side_effect=self.open_gemini_stream,
        )
        self.gemini_stream.start()
        self.title_generation = patch(
            "server.generate_conversation_title",
            side_effect=lambda message, answer: (
                server.make_conversation_title(message, False)
                if message
                else "محادثة حول صورة"
            ),
        )
        self.title_generation.start()

    def tearDown(self):
        self.gemini_stream.stop()
        self.gemini_prewarm.stop()
        self.api.stop()
        self.title_generation.stop()
        self.env.stop()
        server.database = self.previous_database
        self.temp_directory.cleanup()
        self.httpd.shutdown()
        self.thread.join()
        self.httpd.server_close()

    def open_gemini_stream(
        self, handler, request_data, request_headers, request_payload=None
    ):
        request = Request(
            server.API_URL,
            data=request_data,
            headers=request_headers,
            method="POST",
        )
        return server.urlopen(request)

    def request(self, method, path, payload=None, authorized=True):
        headers = {}
        data = None
        if payload is not None:
            data = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        if authorized:
            headers["Cookie"] = f"school_assistant_session={self.session_token}"
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request) as response:
                status, body = response.status, response.read()
                response_headers = response.headers
        except HTTPError as error:
            status, body = error.code, error.read()
            response_headers = error.headers
        if status == 204:
            return status, None, response_headers
        if response_headers.get_content_type() != "text/event-stream":
            return status, json.loads(body), response_headers
        events = []
        for frame in body.decode("utf-8").split("\n\n"):
            event = ""
            data_lines = []
            for line in frame.splitlines():
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    data_lines.append(line[5:].lstrip())
            if data_lines:
                events.append((event, json.loads("\n".join(data_lines))))
        answer = "".join(
            item["text"] for name, item in events if name == "delta"
        )
        done = next((item for name, item in events if name == "done"), {})
        meta = next((item for name, item in events if name == "conversation"), {})
        error = next((item for name, item in events if name == "error"), None)
        title = next((item for name, item in events if name == "title"), {})
        if error:
            result = {"error": error["error"], "events": events}
        else:
            result = {
                "answer": answer,
                "responseId": done.get("responseId"),
                "conversationId": meta.get("conversationId"),
                "title": title.get(
                    "title",
                    done.get("title", meta.get("title")),
                ),
                "events": events,
            }
        return status, result, response_headers

    def post(self, payload, path="/api/chat", authorized=True):
        status, result, _ = self.request(
            "POST", path, payload, authorized=authorized
        )
        return status, result

    def test_database_singleton_initializes_once_for_parallel_requests(self):
        with patch("server.database", None):
            with patch("server.Database") as database_factory:
                with patch.dict(server.os.environ, {"DATABASE_URL": "postgresql://test"}):
                    with ThreadPoolExecutor(max_workers=4) as executor:
                        instances = list(executor.map(
                            lambda _: server.get_database(),
                            range(8),
                        ))

        self.assertEqual(database_factory.call_count, 1)
        self.assertTrue(
            all(instance is database_factory.return_value for instance in instances)
        )

    def test_student_can_update_own_name_phone_and_grade(self):
        old_name = "محمد أحمد علي الحسن"
        new_name = "سعيد سالم ناصر العبد"
        old_email = server.student_email(server.name_tokens(old_name))
        new_email = server.student_email(server.name_tokens(new_name))
        student = server.database.register_user(
            old_email, "long-enough-password", phone="+962791234567"
        )
        server.database.update_student_grade(student["id"], "العاشر")
        self.session_token = server.database.create_session(student["id"])

        with patch.object(
            server.USER_PROFILES,
            "get",
            return_value={"fullName": old_name, "grade": "10"},
        ):
            status, result, _ = self.request("GET", "/api/account/profile")
        self.assertEqual(status, 200)
        self.assertEqual(
            result["profile"],
            {"fullName": old_name, "phone": "+962791234567", "grade": "10"},
        )

        with patch.object(server.USER_PROFILES, "set"), patch.object(
            server.GRADE_DIRECTORY, "forget"
        ):
            status, result, _ = self.request(
                "POST",
                "/api/account/profile",
                {
                    "fullName": new_name,
                    "phone": "078 123 4567",
                    "grade": "9",
                },
            )

        self.assertEqual(status, 200)
        self.assertEqual(result["email"], new_email)
        self.assertEqual(
            result["profile"],
            {"fullName": new_name, "phone": "+962781234567", "grade": "9"},
        )
        self.assertIsNone(server.database.login_user(old_email, "long-enough-password"))
        self.assertEqual(
            server.database.login_user(new_email, "long-enough-password")["id"],
            student["id"],
        )
        self.assertEqual(server.database.get_session_user(self.session_token)["id"], student["id"])

    def test_student_profile_update_rejects_duplicate_name(self):
        own_name = "سعيد سالم ناصر العبد"
        taken_name = "محمد أحمد علي الحسن"
        own_email = server.student_email(server.name_tokens(own_name))
        taken_email = server.student_email(server.name_tokens(taken_name))
        own = server.database.register_user(own_email, "long-enough-password")
        server.database.register_user(taken_email, "another-long-password")
        self.session_token = server.database.create_session(own["id"])

        status, result, _ = self.request(
            "POST",
            "/api/account/profile",
            {
                "fullName": taken_name,
                "phone": "079 123 4567",
                "grade": "10",
            },
        )

        self.assertEqual(status, 409)
        self.assertIn("اسم مستخدم", result["error"])
        self.assertTrue(server.database.user_exists(own_email))

    def test_account_name_requires_four_arabic_words_and_unique_name(self):
        old_name = "محمد أحمد علي الحسن"
        own_email = server.student_email(server.name_tokens(old_name))
        own = server.database.register_user(own_email, "long-enough-password")
        self.session_token = server.database.create_session(own["id"])
        other_email = server.student_email(
            server.name_tokens("سعيد سالم ناصر العبد")
        )
        server.database.register_user(other_email, "another-long-password")

        invalid_names = (
            "John Doe Name Here",
            "محمد أحمد علي 123",
            "محمد أحمد علي",
            "محمد أحمد علي الحسن خامس",
            "محمد أحمد علي @الحسن",
        )
        for name in invalid_names:
            with self.subTest(name=name):
                status, result, _ = self.request(
                    "POST",
                    "/api/account/name",
                    {"fullName": name},
                )
                self.assertEqual(status, 400)
                self.assertTrue(result["error"])

        with patch.object(
            server.USER_PROFILES, "get", return_value={"grade": "10"}
        ), patch.object(server.USER_PROFILES, "set"):
            status, result, _ = self.request(
                "POST",
                "/api/account/name",
                {"fullName": "سعيد سالم ناصر العبد"},
            )
            self.assertEqual(status, 409)
            self.assertIn("مستخدم", result["error"])

            status, result, _ = self.request(
                "POST",
                "/api/account/name",
                {"fullName": old_name},
            )
            self.assertEqual(status, 200)
            self.assertEqual(result["fullName"], old_name)

            new_name = "عمر خالد فهد الزعبي"
            new_email = server.student_email(server.name_tokens(new_name))
            status, result, _ = self.request(
                "POST",
                "/api/account/name",
                {"fullName": new_name},
            )

        self.assertEqual(status, 200)
        self.assertEqual(result["fullName"], new_name)
        self.assertIsNone(
            server.database.login_user(own_email, "long-enough-password")
        )
        self.assertEqual(
            server.database.login_user(new_email, "long-enough-password")["id"],
            own["id"],
        )
        self.assertEqual(
            server.database.get_session_user(self.session_token)["id"],
            own["id"],
        )

    def test_student_can_update_phone_and_nonstudents_cannot(self):
        email = server.student_email(
            server.name_tokens("محمد أحمد علي الحسن")
        )
        student = server.database.register_user(email, "long-enough-password")
        self.session_token = server.database.create_session(student["id"])

        status, result, _ = self.request(
            "POST",
            "/api/account/phone",
            {"phone": "079 123 4567"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["phone"], "+962791234567")
        self.assertEqual(
            server.database.get_student_account_profile(student["id"])["phone"],
            "+962791234567",
        )
        status, result, _ = self.request(
            "POST",
            "/api/account/phone",
            {"phone": "12345"},
        )
        self.assertEqual(status, 400)
        self.assertEqual(
            server.database.get_student_account_profile(student["id"])["phone"],
            "+962791234567",
        )

        self.session_token = server.database.create_session(self.user["id"])
        status, _, _ = self.request(
            "POST",
            "/api/account/phone",
            {"phone": "078 123 4567"},
        )
        self.assertEqual(status, 403)

    def test_student_can_update_own_grade_and_invalid_changes_are_rejected(self):
        email = server.student_email(server.name_tokens("محمد أحمد علي الحسن"))
        student = server.database.register_user(email, "long-enough-password")
        self.session_token = server.database.create_session(student["id"])

        with patch.object(
            server.USER_PROFILES, "set", side_effect=OSError("profile file unavailable")
        ), patch.object(server.GRADE_DIRECTORY, "forget"):
            status, result, _ = self.request(
                "POST", "/api/account/grade", {"grade": "11"}
            )
        self.assertEqual(status, 200)
        self.assertEqual(result["grade"], "11")
        self.assertEqual(result["gradeLabel"], "الأول الثانوي")
        self.assertEqual(
            server.database.get_student_preferences(student["id"])["grade"],
            "الحادي عشر",
        )

        status, result, _ = self.request(
            "POST", "/api/account/grade", {"grade": "13"}
        )
        self.assertEqual(status, 400)
        self.assertEqual(
            server.database.get_student_preferences(student["id"])["grade"],
            "الحادي عشر",
        )

        regular_user = server.database.register_user(
            "regular@example.com", "long-enough-password"
        )
        self.session_token = server.database.create_session(regular_user["id"])
        status, result, _ = self.request(
            "POST", "/api/account/grade", {"grade": "10"}
        )
        self.assertEqual(status, 403)

    def test_theme_preference_persists_and_logout_blocks_protected_pages(self):
        previous_preferences = server.USER_PREFERENCES
        server.USER_PREFERENCES = server.UserPreferences(
            Path(self.temp_directory.name) / "preferences.json"
        )
        try:
            status, result, _ = self.request(
                "POST", "/api/preferences", {"theme": "dark"}
            )
            self.assertEqual(status, 200)
            self.assertEqual(result["preferences"]["theme"], "dark")
            status, result, _ = self.request("GET", "/api/preferences")
            self.assertEqual(status, 200)
            self.assertEqual(result["preferences"]["theme"], "dark")
        finally:
            server.USER_PREFERENCES = previous_preferences

        status, _, headers = self.request("POST", "/api/logout")
        self.assertEqual(status, 204)
        self.assertIn("Max-Age=0", headers.get("Set-Cookie", ""))
        status, _, _ = self.request("GET", "/api/me")
        self.assertEqual(status, 401)
        status, _, _ = self.request("GET", "/api/conversations")
        self.assertEqual(status, 401)

        for path in ("/", "/index.html", "/admin.html"):
            with self.subTest(path=path):
                request = Request(
                    f"{self.base_url}{path}",
                    headers={"Accept": "text/html"},
                )
                with urlopen(request) as response:
                    self.assertEqual(response.status, 200)
                    self.assertTrue(response.url.endswith("/login.html"))

    def test_non_student_cannot_read_or_update_student_profile(self):
        status, result, _ = self.request("GET", "/api/account/profile")
        self.assertEqual(status, 403)
        self.assertIn("حسابات الطلاب فقط", result["error"])

        status, result, _ = self.request(
            "POST",
            "/api/account/profile",
            {
                "fullName": "محمد أحمد علي الحسن",
                "phone": "079 123 4567",
                "grade": "10",
            },
        )
        self.assertEqual(status, 403)

    def test_student_profile_update_changes_login_and_preserves_session(self):
        old_email = server.student_email(
            server.name_tokens("محمد أحمد علي الحسن")
        )
        new_email = server.student_email(
            server.name_tokens("سعيد سالم ناصر العبد")
        )
        user = server.database.register_user(
            old_email, "long-enough-password", phone="+962791234567"
        )
        session = server.database.create_session(user["id"])

        result = server.database.update_student_account_profile(
            user["id"], new_email, "سعيد سالم ناصر العبد", "+962781234567", "التاسع"
        )

        self.assertEqual(result, "updated")
        self.assertIsNone(server.database.login_user(old_email, "long-enough-password"))
        self.assertEqual(
            server.database.login_user(new_email, "long-enough-password")["id"],
            user["id"],
        )
        self.assertEqual(server.database.get_session_user(session)["id"], user["id"])
        self.assertEqual(
            server.database.get_student_account_profile(user["id"]),
            {"email": new_email, "phone": "+962781234567", "grade": "التاسع"},
        )

    def test_student_profile_update_rejects_duplicate_login_name(self):
        target_email = server.student_email(
            server.name_tokens("محمد أحمد علي الحسن")
        )
        original_email = server.student_email(
            server.name_tokens("سعيد سالم ناصر العبد")
        )
        existing = server.database.register_user(
            target_email, "long-enough-password"
        )
        changing = server.database.register_user(
            original_email, "long-enough-password"
        )

        result = server.database.update_student_account_profile(
            changing["id"], target_email, "محمد أحمد علي الحسن", "+962791234567", "العاشر"
        )

        self.assertEqual(result, "duplicate")
        self.assertTrue(server.database.user_exists(original_email))
        self.assertTrue(server.database.user_exists(target_email))
        self.assertEqual(
            server.database.get_student_account_profile(changing["id"])["email"],
            original_email,
        )

    def test_requires_gemini_api_key(self):
        with patch.dict(server.os.environ, {"GEMINI_API_KEY": ""}), patch(
            "builtins.print"
        ) as print_mock:
            status, result = self.post({"message": "مرحبا"})
        self.assertEqual(status, 503)
        self.assertIn("المساعد غير متاح الآن", result["error"])
        self.assertNotIn("GEMINI_API_KEY", result["error"])
        self.mock_urlopen.assert_not_called()
        diagnostic = next(
            call.args[0]
            for call in print_mock.call_args_list
            if call.args[0].startswith("[CHAT_DIAG]")
        )
        self.assertIn('"phase":"gemini_configuration"', diagnostic)
        self.assertIn('"error_type":"ConfigurationError"', diagnostic)
        self.assertIn('"upstream_http_status":null', diagnostic)
        self.assertIn('"message":"Gemini API key is not configured."', diagnostic)

    def test_sanitizes_chat_diagnostic_secrets_and_personal_data(self):
        secret = "AIzaSyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6"
        email = "student@example.com"
        phone = "+962790000001"

        diagnostic = server.safe_chat_diagnostic_message(
            f"api_key={secret} {email} {phone}"
        )

        for sensitive_value in (secret, email, phone):
            self.assertNotIn(sensitive_value, diagnostic)
        self.assertIn("[REDACTED]", diagnostic)
        self.assertIn("[REDACTED_EMAIL]", diagnostic)
        self.assertIn("[REDACTED_PHONE]", diagnostic)

    def test_rejects_invalid_gemini_model_with_diagnostic(self):
        with patch.dict(server.os.environ, {"GEMINI_MODEL": "invalid model"}), patch(
            "builtins.print"
        ) as print_mock:
            status, result = self.post({"message": "مرحبا"})

        self.assertEqual(status, 500)
        self.assertIn("المساعد غير جاهز الآن", result["error"])
        self.mock_urlopen.assert_not_called()
        diagnostic = next(
            call.args[0]
            for call in print_mock.call_args_list
            if call.args[0].startswith("[CHAT_DIAG]")
        )
        self.assertIn('"phase":"model_validation"', diagnostic)
        self.assertIn('"error_type":"ConfigurationError"', diagnostic)

    def test_uses_gemini_3_1_pro_by_default(self):
        self.mock_urlopen.return_value = BytesIO(
            (
                'event: step.delta\n'
                'data: {"event_type":"step.delta","delta":{"type":"text","text":"إجابة"}}\n\n'
                'event: interaction.completed\n'
                'data: {"event_type":"interaction.completed","interaction":{"id":"v1_model"}}\n\n'
            ).encode()
        )
        with patch.dict(server.os.environ):
            server.os.environ.pop("GEMINI_MODEL", None)
            status, _ = self.post({"message": "سؤال"})

        self.assertEqual(status, 200)
        sent = json.loads(self.mock_urlopen.call_args.args[0].data)
        self.assertEqual(sent["model"], "gemini-3.1-pro")

    def test_protects_chat_api_without_a_session(self):
        status, result = self.post(
            {"message": "مرحبا"}, authorized=False
        )
        self.assertEqual(status, 401)
        self.assertIn("سجّل الدخول", result["error"])
        self.mock_urlopen.assert_not_called()

    def test_streams_current_image_and_database_conversation_history(self):
        self.mock_urlopen.return_value = BytesIO(
            (
                'event: interaction.created\n'
                'data: {"event_type":"interaction.created","interaction":{"id":"v1_previous-next"}}\n\n'
                'event: step.delta\n'
                'data: {"event_type":"step.delta","delta":{"type":"text","text":"هذه "}}\n\n'
                'event: step.delta\n'
                'data: {"event_type":"step.delta","delta":{"type":"text","text":"صورة قطة."}}\n\n'
                'event: interaction.completed\n'
                'data: {"event_type":"interaction.completed","interaction":{"id":"v1_previous-next"}}\n\n'
            ).encode()
        )
        image = base64.b64encode(b"fake-png").decode()
        previous = server.database.prepare_user_message(
            self.user["id"], None, "سؤال سابق", "سؤال سابق", None, None
        )
        server.database.complete_assistant_message(
            previous["id"], "إجابة سابقة", "v1_previous"
        )
        status, result = self.post(
            {
                "message": "ما هذه الصورة؟",
                "image": {"mimeType": "image/png", "data": image},
                "conversationId": previous["id"],
            }
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            result,
            {
                "answer": "هذه صورة قطة.",
                "responseId": "v1_previous-next",
                "conversationId": previous["id"],
                "title": "سؤال سابق",
                "events": [
                    (
                        "conversation",
                        {"conversationId": previous["id"], "title": "سؤال سابق"},
                    ),
                    ("delta", {"text": "هذه "}),
                    ("delta", {"text": "صورة قطة."}),
                    (
                        "done",
                        {
                            "responseId": "v1_previous-next",
                            "conversationId": previous["id"],
                            "title": "سؤال سابق",
                        },
                    ),
                ],
            },
        )
        request = self.mock_urlopen.call_args.args[0]
        self.assertEqual(request.get_header("X-goog-api-key"), "test-key")
        self.assertEqual(
            request.full_url,
            "https://generativelanguage.googleapis.com/v1beta/interactions",
        )
        sent = json.loads(request.data)
        self.assertEqual(sent["model"], "gemini-3.1-pro")
        self.assertIn(server.SYSTEM_INSTRUCTION, sent["system_instruction"])
        self.assertIn("لا تبدأ بتحية", sent["system_instruction"])
        self.assertIn("اسأله مرة واحدة فقط", sent["system_instruction"])
        self.assertIn("باللهجة الأردنية", sent["system_instruction"])
        self.assertIn("اترك سطرًا فارغًا بين الفقرات", sent["system_instruction"])
        self.assertIn("اكتب كل عنصر في سطر مستقل", sent["system_instruction"])
        self.assertIn("ولا تجمع عنصرين في السطر نفسه", sent["system_instruction"])
        self.assertIn("عناوين Markdown قصيرة وواضحة", sent["system_instruction"])
        self.assertIn("كتلة Markdown", sent["system_instruction"])
        self.assertIn("عناصر HTML الهيكلية <table>", sent["system_instruction"])
        self.assertIn("لا تستخدم صيغة Markdown ذات | للجداول", sent["system_instruction"])
        self.assertIn("ولا تضعهما في جدول إلا إذا كان الجدول مفيدًا فعلًا", sent["system_instruction"])
        self.assertIn("تجنب LaTeX المعقد", sent["system_instruction"])
        self.assertIn("لا تكتب وسوم HTML", sent["system_instruction"])
        self.assertIs(sent["stream"], True)
        self.assertNotIn("previous_interaction_id", sent)
        transcript = "\n".join(
            part.get("text", "") for part in sent["input"]
        )
        self.assertIn("الطالب: سؤال سابق", transcript)
        self.assertIn("فهيم: إجابة سابقة", transcript)
        images = [part for part in sent["input"] if part["type"] == "image"]
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0]["mime_type"], "image/png")

    def test_starts_gemini_before_writing_new_conversation(self):
        self.mock_urlopen.return_value = BytesIO(
            (
                'event: step.delta\n'
                'data: {"event_type":"step.delta","delta":{"type":"text","text":"إجابة"}}\n\n'
                'event: interaction.completed\n'
                'data: {"event_type":"interaction.completed","interaction":{"id":"v1_fast"}}\n\n'
            ).encode()
        )

        def check_empty_database(request):
            self.assertEqual(
                server.database.list_conversations(self.user["id"]),
                [],
            )
            return self.mock_urlopen.return_value

        self.mock_urlopen.side_effect = check_empty_database
        status, response = self.post({"message": "سؤال جديد"})

        self.assertEqual(status, 200)
        self.assertEqual(response["answer"], "إجابة")
        conversation = server.database.get_conversation(
            self.user["id"], response["conversationId"]
        )
        self.assertEqual(
            [message["role"] for message in conversation[1]],
            ["user", "assistant"],
        )

    def test_streams_first_chunk_before_delayed_database_save(self):
        started = server.time.perf_counter()
        first_delta_at = {}
        save_started_at = {}

        class TimedStream(BytesIO):
            def readline(self, *args):
                line = super().readline(*args)
                if b'"event_type":"step.delta"' in line:
                    first_delta_at["time"] = server.time.perf_counter()
                return line

        self.mock_urlopen.return_value = TimedStream(
            (
                'event: step.delta\n'
                'data: {"event_type":"step.delta","delta":{"type":"text","text":"سريع"}}\n\n'
                'event: interaction.completed\n'
                'data: {"event_type":"interaction.completed","interaction":{"id":"v1_delayed_save"}}\n\n'
            ).encode()
        )
        original_save = server.Database.complete_chat_exchange

        def delayed_save(database, *args, **kwargs):
            save_started_at["time"] = server.time.perf_counter()
            server.time.sleep(0.08)
            return original_save(database, *args, **kwargs)

        with patch.object(
            server.Database,
            "complete_chat_exchange",
            delayed_save,
        ):
            status, response = self.post({"message": "اختبار تأخير التخزين"})

        self.assertEqual(status, 200)
        self.assertEqual(response["answer"], "سريع")
        self.assertLess(first_delta_at["time"], save_started_at["time"])
        self.assertGreaterEqual(
            server.time.perf_counter() - save_started_at["time"],
            0.08,
        )
        self.assertLess(first_delta_at["time"] - started, 0.08)

    def test_retry_replays_completed_exchange_without_regenerating(self):
        request_id = "a" * 32
        self.mock_urlopen.return_value = BytesIO(
            (
                'event: step.delta\n'
                'data: {"event_type":"step.delta","delta":{"type":"text","text":"الإجابة الأصلية"}}\n\n'
                'event: interaction.completed\n'
                'data: {"event_type":"interaction.completed","interaction":{"id":"v1_retry"}}\n\n'
            ).encode()
        )
        payload = {
            "message": "سؤال يعاد بأمان",
            "requestId": request_id,
        }
        status, first = self.post(payload)
        self.assertEqual(status, 200)
        self.assertEqual(first["answer"], "الإجابة الأصلية")

        self.mock_urlopen.reset_mock()
        status, replay = self.post({**payload, "retryRequest": True})

        self.assertEqual(status, 200)
        self.assertEqual(replay["answer"], "الإجابة الأصلية")
        self.assertEqual(replay["conversationId"], first["conversationId"])
        self.mock_urlopen.assert_not_called()
        status, conflict = self.post(
            {
                **payload,
                "message": "رسالة مختلفة بنفس المعرّف",
                "retryRequest": True,
            }
        )
        self.assertEqual(status, 409)
        self.assertIn("مرجع الطلب مستخدم", conflict["error"])
        self.mock_urlopen.assert_not_called()
        conversation = server.database.get_conversation(
            self.user["id"], first["conversationId"]
        )
        self.assertEqual(
            [message["role"] for message in conversation[1]],
            ["user", "assistant"],
        )

    def test_retry_replays_image_using_fingerprint_without_saving_image(self):
        request_id = "b" * 32
        self.mock_urlopen.return_value = BytesIO(
            (
                'event: step.delta\n'
                'data: {"event_type":"step.delta","delta":{"type":"text","text":"إجابة الصورة"}}\n\n'
                'event: interaction.completed\n'
                'data: {"event_type":"interaction.completed","interaction":{"id":"v1_image_retry"}}\n\n'
            ).encode()
        )
        image = base64.b64encode(b"one-image").decode()
        payload = {
            "message": "ما في الصورة؟",
            "image": {"mimeType": "image/png", "data": image},
            "requestId": request_id,
        }
        status, first = self.post(payload)
        self.assertEqual(status, 200)
        message = server.database.get_conversation(
            self.user["id"], first["conversationId"]
        )[1][0]
        self.assertIsNone(message["image_data"])

        self.mock_urlopen.reset_mock()
        status, replay = self.post({**payload, "retryRequest": True})
        self.assertEqual(status, 200)
        self.assertEqual(replay["answer"], first["answer"])
        self.mock_urlopen.assert_not_called()

        different_image = base64.b64encode(b"different-image").decode()
        status, conflict = self.post(
            {
                **payload,
                "image": {"mimeType": "image/png", "data": different_image},
                "retryRequest": True,
            }
        )
        self.assertEqual(status, 409)
        self.assertIn("مرجع الطلب مستخدم", conflict["error"])

    def test_save_failure_keeps_streamed_answer_and_does_not_persist_partial_pair(self):
        self.mock_urlopen.return_value = BytesIO(
            (
                'event: step.delta\n'
                'data: {"event_type":"step.delta","delta":{"type":"text","text":"الإجابة التي ظهرت"}}\n\n'
                'event: interaction.completed\n'
                'data: {"event_type":"interaction.completed","interaction":{"id":"v1_save_error"}}\n\n'
            ).encode()
        )
        with patch.object(
            server.Database,
            "complete_chat_exchange",
            side_effect=sqlite3.OperationalError("database unavailable"),
        ):
            status, response = self.post({"message": "احتفظوا بالإجابة"})

        self.assertEqual(status, 200)
        self.assertEqual(
            "".join(
                event["text"]
                for name, event in response["events"]
                if name == "delta"
            ),
            "الإجابة التي ظهرت",
        )
        error = next(event for name, event in response["events"] if name == "error")
        self.assertEqual(error["code"], "save_failed")
        self.assertEqual(server.database.list_conversations(self.user["id"]), [])

    def test_table_formatting_followup_reuses_previous_schedule_context(self):
        previous = server.database.prepare_user_message(
            self.user["id"],
            None,
            "تنظيم الأيام",
            "أريد تنظيم أيامي",
            None,
            None,
        )
        schedule = (
            "الأحد: رياضيات وعلوم\n"
            "الاثنين: عربي وإنجليزي\n"
            "الثلاثاء: اجتماعيات"
        )
        server.database.complete_assistant_message(
            previous["id"], schedule, "previous-schedule"
        )
        self.mock_urlopen.return_value = BytesIO(
            (
                'event: step.delta\n'
                'data: {"event_type":"step.delta","delta":{"type":"text","text":"| اليوم | المواد |\\n| --- | --- |\\n| الأحد | رياضيات وعلوم |"}}\n\n'
                'event: interaction.completed\n'
                'data: {"event_type":"interaction.completed","interaction":{"id":"v1_table_followup"}}\n\n'
            ).encode()
        )

        status, _ = self.post(
            {
                "message": "نظم المعلومات بشكل جدول",
                "conversationId": previous["id"],
            }
        )

        self.assertEqual(status, 200)
        sent = json.loads(self.mock_urlopen.call_args.args[0].data)
        self.assertIn("أعد تنسيق المعلومات نفسها فقط", sent["system_instruction"])
        self.assertIn("لا تبدأ موضوعًا أو خطة جديدة", sent["system_instruction"])
        transcript = "\n".join(
            part.get("text", "") for part in sent["input"]
        )
        self.assertIn("فهيم: " + schedule, transcript)
        self.assertIn("نظم المعلومات بشكل جدول", transcript)

    def test_previous_images_are_not_reloaded_from_conversation_history(self):
        previous_image = b"previous-png-image"
        previous = server.database.prepare_user_message(
            self.user["id"],
            None,
            "مسألة مصورة",
            "أوجد الناتج في الصورة",
            "image/png",
            previous_image,
        )
        server.database.complete_assistant_message(
            previous["id"], "تظهر الصورة مسألة جمع.", "old-interaction"
        )
        stream = (
            'event: step.delta\n'
            'data: {"event_type":"step.delta","delta":{"type":"text","text":"الناتج ٤."}}\n\n'
            'event: interaction.completed\n'
            'data: {"event_type":"interaction.completed","interaction":{"id":"new-interaction"}}\n\n'
        ).encode()
        self.mock_urlopen.return_value = BytesIO(stream)

        status, result = self.post(
            {
                "message": "ما حل المسألة الظاهرة في الصورة السابقة؟",
                "conversationId": previous["id"],
            }
        )
        self.assertEqual(status, 200)
        request = self.mock_urlopen.call_args.args[0]
        sent = json.loads(request.data)
        prior_images = [
            part for part in sent["input"] if part.get("type") == "image"
        ]
        self.assertEqual(prior_images, [])

        self.mock_urlopen.return_value = BytesIO(stream)
        status, _ = self.post(
            {
                "message": "ما عاصمة الأردن؟",
                "conversationId": previous["id"],
            }
        )
        self.assertEqual(status, 200)
        unrelated_request = self.mock_urlopen.call_args.args[0]
        unrelated = json.loads(unrelated_request.data)
        self.assertFalse(
            any(part.get("type") == "image" for part in unrelated["input"])
        )

    def test_first_response_skips_greeting_unless_student_greets(self):
        self.mock_urlopen.return_value = BytesIO(
            (
                'event: step.delta\n'
                'data: {"event_type":"step.delta","delta":{"type":"text","text":"أهلًا"}}\n\n'
                'event: interaction.completed\n'
                'data: {"event_type":"interaction.completed","interaction":{"id":"v1_first"}}\n\n'
            ).encode()
        )
        status, first = self.post({"message": "كيفك؟"})
        self.assertEqual(status, 200)
        first_payload = json.loads(self.mock_urlopen.call_args.args[0].data)
        self.assertIn("لم يبدأ الطالب بتحية", first_payload["system_instruction"])
        self.assertIn("لا ترحّب به", first_payload["system_instruction"])
        self.assertIn("اسأله مرة واحدة فقط", first_payload["system_instruction"])

        self.mock_urlopen.return_value = BytesIO(
            (
                'event: step.delta\n'
                'data: {"event_type":"step.delta","delta":{"type":"text","text":"تمام"}}\n\n'
                'event: interaction.completed\n'
                'data: {"event_type":"interaction.completed","interaction":{"id":"v1_second"}}\n\n'
            ).encode()
        )
        status, second = self.post(
            {"message": "احكيلي نكتة", "conversationId": first["conversationId"]}
        )
        self.assertEqual(status, 200)
        second_payload = json.loads(self.mock_urlopen.call_args.args[0].data)
        self.assertIn("لا تبدأ بتحية", second_payload["system_instruction"])
        self.assertIn("لا تعاود السؤال عنه", second_payload["system_instruction"])

        self.mock_urlopen.return_value = BytesIO(
            (
                'event: step.delta\n'
                'data: {"event_type":"step.delta","delta":{"type":"text","text":"شرح"}}\n\n'
                'event: interaction.completed\n'
                'data: {"event_type":"interaction.completed","interaction":{"id":"v1_third"}}\n\n'
            ).encode()
        )
        status, _ = self.post({"message": "اشرح لي الكسور"})
        self.assertEqual(status, 200)
        new_chat_payload = json.loads(self.mock_urlopen.call_args.args[0].data)
        self.assertIn("لم يبدأ الطالب بتحية", new_chat_payload["system_instruction"])
        self.assertIn("لا تعاود السؤال عنه", new_chat_payload["system_instruction"])

        self.mock_urlopen.return_value = BytesIO(
            (
                'event: step.delta\n'
                'data: {"event_type":"step.delta","delta":{"type":"text","text":"تمام"}}\n\n'
                'event: interaction.completed\n'
                'data: {"event_type":"interaction.completed","interaction":{"id":"v1_grade_answer"}}\n\n'
            ).encode()
        )
        status, _ = self.post({"message": "العاشر"})
        self.assertEqual(status, 200)
        grade_answer_payload = json.loads(self.mock_urlopen.call_args.args[0].data)
        self.assertIn(
            "صف الطالب المحفوظ في ملفه هو العاشر",
            grade_answer_payload["system_instruction"],
        )
        self.assertNotIn("اسأله مرة واحدة فقط", grade_answer_payload["system_instruction"])

    def test_first_response_may_greet_when_student_starts_with_greeting(self):
        self.mock_urlopen.return_value = BytesIO(
            (
                'event: step.delta\n'
                'data: {"event_type":"step.delta","delta":{"type":"text","text":"أهلًا"}}\n\n'
                'event: interaction.completed\n'
                'data: {"event_type":"interaction.completed","interaction":{"id":"v1_greeting"}}\n\n'
            ).encode()
        )
        status, _ = self.post({"message": "مرحبا، اشرحلي قانون نيوتن"})
        self.assertEqual(status, 200)
        payload = json.loads(self.mock_urlopen.call_args.args[0].data)
        self.assertIn("أنا فهيم، مساعد ذكي للطلاب", payload["system_instruction"])
        self.assertIn("بدأ الطالب بتحية", payload["system_instruction"])
        self.assertNotIn("لم يبدأ الطالب بتحية", payload["system_instruction"])

    def test_assistant_identity_and_developer_questions_are_explicit(self):
        self.assertTrue(server.user_asks_assistant_identity("شو اسمك؟"))
        self.assertTrue(server.user_asks_assistant_identity("مين طورك؟"))
        self.assertFalse(server.user_asks_assistant_identity("اشرح قانون نيوتن"))
        instruction = server.conversation_system_instruction(
            first_reply=False,
            grade=None,
            ask_grade=False,
            asks_identity=True,
        )
        self.assertIn("أنا فهيم، مساعد ذكي للطلاب في مدرسة خريبة السوق", instruction)
        self.assertIn("صنعني المطور جميل إسماعيل أبو حماد", instruction)

    def test_detects_greetings_only_at_the_start_of_the_message(self):
        self.assertTrue(server.user_starts_with_greeting("مرحبا، عندي سؤال"))
        self.assertTrue(server.user_starts_with_greeting("السلام عليكم"))
        self.assertFalse(server.user_starts_with_greeting("كيفك؟"))
        self.assertFalse(server.user_starts_with_greeting("ما معنى كلمة مرحبا؟"))

    def test_saves_grade_from_student_message_and_uses_it_in_prompt(self):
        self.mock_urlopen.return_value = BytesIO(
            (
                'event: step.delta\n'
                'data: {"event_type":"step.delta","delta":{"type":"text","text":"أكيد"}}\n\n'
                'event: interaction.completed\n'
                'data: {"event_type":"interaction.completed","interaction":{"id":"v1_grade"}}\n\n'
            ).encode()
        )
        status, _ = self.post({"message": "أنا بالصف العاشر، اشرحلي المعادلات"})
        self.assertEqual(status, 200)
        payload = json.loads(self.mock_urlopen.call_args.args[0].data)
        self.assertIn("صف الطالب المحفوظ في ملفه هو العاشر", payload["system_instruction"])
        self.assertNotIn("اسأله مرة واحدة فقط", payload["system_instruction"])
        preferences = server.database.get_student_preferences(self.user["id"])
        self.assertEqual(preferences["grade"], "العاشر")
        self.assertTrue(preferences["grade_question_asked"])

    def test_extracts_written_and_numeric_grade_forms(self):
        self.assertEqual(
            server.extract_student_grade("أنا بالصف العاشر"),
            "العاشر",
        )
        self.assertEqual(
            server.extract_student_grade("صفّي ١٠"),
            "الصف 10",
        )
        self.assertEqual(
            server.extract_student_grade("أنا بالصف الثاني عشر"),
            "الثاني عشر",
        )
        self.assertEqual(
            server.extract_student_grade("العاشر", allow_short_answer=True),
            "العاشر",
        )
        self.assertIsNone(server.extract_student_grade("اشرح صفحة 10 من الكتاب"))

    def test_conversation_title_tracks_first_topic_after_a_greeting(self):
        self.assertEqual(server.make_conversation_title("مرحبا جميل", False), "محادثة جديدة")
        self.assertEqual(
            server.make_conversation_title(
                "مرحبا، بدي أسألك عن قانون نيوتن", False
            ),
            "بدي أسألك عن قانون نيوتن",
        )

        self.mock_urlopen.return_value = BytesIO(
            (
                'event: step.delta\n'
                'data: {"event_type":"step.delta","delta":{"type":"text","text":"أهلًا"}}\n\n'
                'event: interaction.completed\n'
                'data: {"event_type":"interaction.completed","interaction":{"id":"v1_greeting"}}\n\n'
            ).encode()
        )
        status, greeting = self.post({"message": "مرحبا جميل"})
        self.assertEqual(status, 200)
        self.assertEqual(greeting["title"], "محادثة جديدة")

        self.mock_urlopen.return_value = BytesIO(
            (
                'event: step.delta\n'
                'data: {"event_type":"step.delta","delta":{"type":"text","text":"قانون نيوتن يشرح"}}\n\n'
                'event: interaction.completed\n'
                'data: {"event_type":"interaction.completed","interaction":{"id":"v1_topic"}}\n\n'
            ).encode()
        )
        status, topic = self.post(
            {
                "message": "مرحبا، بدي أسألك عن قانون نيوتن",
                "conversationId": greeting["conversationId"],
            }
        )
        self.assertEqual(status, 200)
        self.assertEqual(topic["title"], "بدي أسألك عن قانون نيوتن")

        self.mock_urlopen.return_value = BytesIO(
            (
                'event: step.delta\n'
                'data: {"event_type":"step.delta","delta":{"type":"text","text":"التسارع"}}\n\n'
                'event: interaction.completed\n'
                'data: {"event_type":"interaction.completed","interaction":{"id":"v1_followup"}}\n\n'
            ).encode()
        )
        status, follow_up = self.post(
            {
                "message": "طيب شو يعني التسارع؟",
                "conversationId": greeting["conversationId"],
            }
        )
        self.assertEqual(status, 200)
        self.assertEqual(follow_up["title"], "بدي أسألك عن قانون نيوتن")

    def test_generates_ai_conversation_title_from_the_initial_message(self):
        self.title_generation.stop()
        self.mock_urlopen.return_value = BytesIO(
            json.dumps(
                {"output_text": "تنسيق النصوص البرمجية والعناوين"},
                ensure_ascii=False,
            ).encode("utf-8")
        )
        title = server.generate_conversation_title(
            "رتب النصوص والعناوين وأضف ألوانًا وأرقام أسطر للأكواد",
            "سأرتب الردود والعناوين والكتل البرمجية.",
        )
        self.assertEqual(title, "تنسيق النصوص البرمجية والعناوين")
        request = self.mock_urlopen.call_args.args[0]
        request_payload = json.loads(request.data)
        self.assertIn("أول رسالة من الطالب", request_payload["input"])
        self.assertIn("ألوانًا وأرقام أسطر", request_payload["input"])

    def test_stream_response_keeps_local_title_without_second_gemini_request(self):
        self.title_generation.stop()
        self.mock_urlopen.return_value = BytesIO(
            (
                'event: step.delta\n'
                'data: {"event_type":"step.delta","delta":{"type":"text","text":"سأشرح تنسيق الكود والعناوين."}}\n\n'
                'event: interaction.completed\n'
                'data: {"event_type":"interaction.completed","interaction":{"id":"v1_title"}}\n\n'
            ).encode()
        )
        message = "رتب النصوص والعناوين وأضف ألوانًا وأرقام أسطر للكود"
        with patch(
            "server.generate_conversation_title",
            side_effect=AssertionError("title generation must not block chat"),
        ) as title_generator:
            status, result = self.post(
                {"message": message}
            )
        title_generator.assert_not_called()
        self.assertEqual(status, 200)
        self.assertEqual(result["title"], server.make_conversation_title(message, False))
        self.assertEqual(self.mock_urlopen.call_count, 1)
        self.assertEqual(
            server.database.list_conversations(self.user["id"])[0]["title"],
            server.make_conversation_title(message, False),
        )

    def test_conversation_titles_are_unique_after_creation_and_rename(self):
        first = server.database.prepare_user_message(
            self.user["id"], None, "تنسيق النصوص البرمجية", "الأولى", None, None
        )
        second = server.database.prepare_user_message(
            self.user["id"], None, "تنسيق النصوص البرمجية", "الثانية", None, None
        )
        self.assertEqual(first["title"], "تنسيق النصوص البرمجية")
        self.assertEqual(second["title"], "تنسيق النصوص البرمجية (2)")
        renamed = server.database.rename_conversation(
            self.user["id"], second["id"], "تنسيق النصوص البرمجية"
        )
        self.assertEqual(renamed, "تنسيق النصوص البرمجية (2)")

    def test_migrates_duplicate_conversation_titles(self):
        first = server.database.prepare_user_message(
            self.user["id"], None, "محادثة مكررة", "الأولى", None, None
        )
        second = server.database.prepare_user_message(
            self.user["id"], None, "محادثة ثانية", "الثانية", None, None
        )
        with server.database.connect() as connection:
            connection.execute(
                "UPDATE conversations SET title = ? WHERE id IN (?, ?)",
                ("محادثة مكررة", first["id"], second["id"]),
            )
        server.database = server.Database(server.database.path)
        titles = [
            item["title"]
            for item in server.database.list_conversations(self.user["id"])
        ]
        self.assertEqual(set(titles), {"محادثة مكررة", "محادثة مكررة (2)"})

    def test_migrates_existing_user_table_for_student_preferences(self):
        legacy_path = Path(self.temp_directory.name) / "legacy.sqlite3"
        connection = sqlite3.connect(legacy_path)
        try:
            connection.execute(
                """
                CREATE TABLE users (
                    id TEXT PRIMARY KEY,
                    google_sub TEXT NOT NULL UNIQUE,
                    email TEXT NOT NULL,
                    name TEXT NOT NULL,
                    picture TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO users (id, google_sub, email, name, created_at)
                VALUES ('legacy-user', 'legacy-sub', 'old@example.com', 'Old', 1)
                """
            )
            connection.commit()
        finally:
            connection.close()
        migrated_database = server.Database(legacy_path)
        self.assertEqual(
            migrated_database.get_student_preferences("legacy-user"),
            {"grade": None, "grade_question_asked": False},
        )

    def test_accepts_image_without_caption(self):
        self.mock_urlopen.return_value = BytesIO(
            (
                'event: step.delta\n'
                'data: {"event_type":"step.delta","delta":{"type":"text","text":"تظهر في الصورة شجرة."}}\n\n'
                'event: interaction.completed\n'
                'data: {"event_type":"interaction.completed","interaction":{"id":"v1_image"}}\n\n'
            ).encode()
        )
        image = base64.b64encode(b"fake-png").decode()
        status, result = self.post(
            {
                "message": "",
                "image": {"mimeType": "image/png", "data": image},
            }
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["answer"], "تظهر في الصورة شجرة.")
        self.assertEqual(result["responseId"], "v1_image")
        self.assertEqual(result["title"], "محادثة حول صورة")
        sent = json.loads(self.mock_urlopen.call_args.args[0].data)
        self.assertEqual(sent["input"][0]["type"], "image")
        self.assertEqual(sent["input"][0]["mime_type"], "image/png")

    def test_attaches_pdf_document_to_gemini_request(self):
        self.mock_urlopen.return_value = BytesIO(
            (
                'event: step.delta\n'
                'data: {"event_type":"step.delta","delta":{"type":"text","text":"ملخص الدرس."}}\n\n'
                'event: interaction.completed\n'
                'data: {"event_type":"interaction.completed","interaction":{"id":"v1_pdf"}}\n\n'
            ).encode()
        )
        document_data = base64.b64encode(b"%PDF-test").decode()

        status, result = self.post(
            {
                "message": "لخص هذا الملف",
                "file": {
                    "name": "lesson.pdf",
                    "mimeType": "application/pdf",
                    "data": document_data,
                },
            }
        )

        self.assertEqual(status, 200)
        self.assertEqual(result["answer"], "ملخص الدرس.")
        sent = json.loads(self.mock_urlopen.call_args.args[0].data)
        document_part = next(part for part in sent["input"] if part["type"] == "document")
        self.assertEqual(document_part["mime_type"], "application/pdf")
        self.assertEqual(document_part["data"], document_data)
        detail = server.database.get_conversation(
            self.user["id"], result["conversationId"]
        )
        self.assertIn("lesson.pdf", detail[1][0]["content"])
        self.assertNotIn(document_data, detail[1][0]["content"])
        self.assertIsNone(detail[1][0]["image_data"])

    def test_rejects_unsupported_document_type(self):
        status, result = self.post(
            {
                "message": "اقرأ الملف",
                "file": {
                    "name": "program.exe",
                    "mimeType": "application/octet-stream",
                    "data": base64.b64encode(b"data").decode(),
                },
            }
        )
        self.assertEqual(status, 400)
        self.assertIn("نوع الملف", result["error"])
        self.mock_urlopen.assert_not_called()

    def test_image_generation_request_gets_text_chat_refusal_without_gemini(self):
        with patch.dict(server.os.environ, {"GEMINI_API_KEY": ""}):
            status, result = self.post(
                {"message": "ارسم لي صورة قلعة على تلة وقت الغروب"}
            )

        self.assertEqual(status, 200)
        self.assertIn("ما بقدر أنشئ صور", result["answer"])
        self.assertIn("مساعد نصّي", result["answer"])
        self.assertTrue(result["responseId"].startswith("local-"))
        self.mock_urlopen.assert_not_called()
        detail = server.database.get_conversation(
            self.user["id"], result["conversationId"]
        )
        self.assertEqual(detail[1][-1]["role"], "assistant")
        self.assertEqual(detail[1][-1]["content"], result["answer"])
        self.assertIsNone(detail[1][-1]["image_data"])

    def test_detects_explicit_image_requests_only(self):
        self.assertTrue(server.wants_image_generation("ارسم لي صورة لقطة فضائية"))
        self.assertTrue(server.wants_image_generation("بدي تعمل صورة لقلعة"))
        self.assertFalse(server.wants_image_generation("اشرح كيف تتكون الصور الرقمية"))

    def test_rejects_invalid_image_type(self):
        status, result = self.post(
            {
                "message": "ما هذه؟",
                "image": {"mimeType": "text/plain", "data": "eA=="},
            }
        )
        self.assertEqual(status, 400)
        self.assertIn("صيغة الصورة", result["error"])
        self.mock_urlopen.assert_not_called()

    def test_support_message_reaches_admin_inbox_and_can_be_resolved(self):
        status, submitted, _ = self.request(
            "POST",
            "/api/support-messages",
            {"category": "complaint", "content": "هناك مشكلة في سجل المحادثات."},
        )
        self.assertEqual(status, 201)
        self.assertGreater(submitted["id"], 0)

        status, denied, _ = self.request("GET", "/api/admin/support-messages")
        self.assertEqual(status, 403)
        self.assertIn("صلاحية", denied["error"])

        with patch.dict(server.os.environ, {"ADMIN_EMAIL": self.user["email"]}):
            status, inbox, _ = self.request("GET", "/api/admin/support-messages")
            self.assertEqual(status, 200)
            self.assertEqual(len(inbox["messages"]), 1)
            self.assertEqual(inbox["messages"][0]["user_email"], self.user["email"])
            self.assertEqual(inbox["messages"][0]["category"], "complaint")
            self.assertEqual(inbox["messages"][0]["status"], "new")
            status, updated, _ = self.request(
                "PATCH",
                f"/api/admin/support-messages/{submitted['id']}",
                {"status": "resolved"},
            )
            self.assertEqual(status, 200)
            self.assertEqual(updated["status"], "resolved")
            status, inbox, _ = self.request("GET", "/api/admin/support-messages")
            self.assertEqual(inbox["messages"][0]["status"], "resolved")

    def test_authenticated_support_message_uses_account_profile_name(self):
        full_name = "محمد أحمد علي الحسن"
        email = server.student_email(server.name_tokens(full_name))
        student = server.database.register_user(email, "long-enough-password")
        self.session_token = server.database.create_session(student["id"])

        with patch.object(
            server.USER_PROFILES,
            "get",
            return_value={"fullName": full_name, "grade": "10"},
        ):
            status, submitted, _ = self.request(
                "POST",
                "/api/support-messages",
                {
                    "category": "message",
                    "content": "أحتاج مساعدة في واجهة الحساب.",
                },
            )

        self.assertEqual(status, 201)
        self.assertGreater(submitted["id"], 0)
        message = server.database.list_support_messages()[0]
        self.assertEqual(message["user_name"], full_name)
        self.assertEqual(message["user_email"], email)
        with server.database.connect() as connection:
            owner = connection.execute(
                "SELECT user_id FROM support_messages WHERE id = ?",
                (submitted["id"],),
            ).fetchone()
        self.assertEqual(owner["user_id"], student["id"])

    def test_support_message_rejects_invalid_categories_and_empty_content(self):
        status, result, _ = self.request(
            "POST",
            "/api/support-messages",
            {"category": "other", "content": "رسالة"},
        )
        self.assertEqual(status, 400)

    def test_logged_out_user_can_send_help_request_with_contact_details(self):
        status, result, _ = self.request(
            "POST",
            "/api/support-messages",
            {
                "category": "message",
                "content": "أحتاج مساعدة في الدخول إلى حسابي.",
                "name": "طالب فهيم",
                "email": "student@example.com",
            },
            authorized=False,
        )

        self.assertEqual(status, 201)
        self.assertGreater(result["id"], 0)
        messages = server.database.list_support_messages()
        self.assertEqual(messages[0]["user_name"], "طالب فهيم")
        self.assertEqual(messages[0]["user_email"], "student@example.com")
        with server.database.connect() as connection:
            owner = connection.execute(
                "SELECT user_id FROM support_messages WHERE id = ?",
                (result["id"],),
            ).fetchone()
        self.assertIsNone(owner["user_id"])

    def test_logged_out_help_request_without_contact_details_requires_login(self):
        status, result, _ = self.request(
            "POST",
            "/api/support-messages",
            {"category": "message", "content": "أحتاج مساعدة."},
            authorized=False,
        )

        self.assertEqual(status, 401)
        self.assertIn("سجّل الدخول", result["error"])
        self.assertEqual(server.database.list_support_messages(), [])

    def test_logged_out_help_request_requires_valid_email(self):
        status, result, _ = self.request(
            "POST",
            "/api/support-messages",
            {
                "category": "message",
                "content": "أحتاج مساعدة.",
                "name": "طالب فهيم",
                "email": "invalid-email",
            },
            authorized=False,
        )

        self.assertEqual(status, 400)
        self.assertIn("بريدًا إلكترونيًا صالحًا", result["error"])
        status, result, _ = self.request(
            "POST",
            "/api/support-messages",
            {"category": "message", "content": "   "},
        )
        self.assertEqual(status, 400)

    def test_rejects_invalid_conversation_id(self):
        status, result = self.post(
            {
                "message": "مرحبا",
                "conversationId": "id with spaces",
            }
        )
        self.assertEqual(status, 400)
        self.assertIn("مرجع المحادثة", result["error"])
        self.mock_urlopen.assert_not_called()

    def test_reports_gemini_connection_error(self):
        self.mock_urlopen.side_effect = URLError("offline")
        with patch("builtins.print") as print_mock:
            status, result = self.post({"message": "مرحبا"})
        self.assertEqual(status, 502)
        self.assertEqual(
            result["error"],
            "تعذّر الاتصال بالمساعد. تحقق من اتصال الإنترنت ثم حاول مرة أخرى.",
        )
        self.assertNotIn("offline", result["error"])
        diagnostic = next(
            call.args[0]
            for call in print_mock.call_args_list
            if call.args[0].startswith("[CHAT_DIAG]")
        )
        self.assertIn('"phase":"gemini_connection"', diagnostic)
        self.assertIn('"error_type":"URLError"', diagnostic)
        self.assertIn('"message":"Could not connect to the Gemini service."', diagnostic)

    def test_reports_gemini_http_503_without_logging_error_body(self):
        secret = "AIzaSyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6"
        email = "student@example.com"
        phone = "+962790000001"
        sensitive_body = (
            f'{{"error":"{secret} {email} {phone} طالب فهيم"}}'
        ).encode()
        upstream_error = HTTPError(
            server.API_URL,
            503,
            "Service Unavailable",
            {},
            BytesIO(sensitive_body),
        )
        self.mock_urlopen.side_effect = upstream_error

        with patch("builtins.print") as print_mock:
            status, result = self.post({"message": "مرحبا"})
        upstream_error.close()

        self.assertEqual(status, 503)
        self.assertIn("واجه المساعد مشكلة مؤقتة", result["error"])
        self.assertNotIn(secret, result["error"])
        diagnostic = next(
            call.args[0]
            for call in print_mock.call_args_list
            if call.args[0].startswith("[CHAT_DIAG]")
        )
        self.assertIn('"phase":"gemini_upstream_response"', diagnostic)
        self.assertIn('"error_type":"HTTPError"', diagnostic)
        self.assertIn('"upstream_http_status":503', diagnostic)
        self.assertIn('"message":"Service Unavailable"', diagnostic)
        for sensitive_value in (secret, email, phone, "طالب فهيم"):
            self.assertNotIn(sensitive_value, diagnostic)

    def test_reports_gemini_request_timeout_with_diagnostic(self):
        self.mock_urlopen.side_effect = TimeoutError("timed out")

        with patch("builtins.print") as print_mock:
            status, result = self.post({"message": "مرحبا"})

        self.assertEqual(status, 504)
        self.assertIn("تأخر رد المساعد", result["error"])
        diagnostic = next(
            call.args[0]
            for call in print_mock.call_args_list
            if call.args[0].startswith("[CHAT_DIAG]")
        )
        self.assertIn('"phase":"gemini_request"', diagnostic)
        self.assertIn('"error_type":"TimeoutError"', diagnostic)
        self.assertIn('"upstream_http_status":null', diagnostic)

    def test_reports_malformed_gemini_stream_event(self):
        self.mock_urlopen.return_value = BytesIO(
            b"event: step.delta\ndata: not-json\n\n"
        )
        status, result = self.post({"message": "مرحبا"})
        self.assertEqual(status, 200)
        self.assertIn("وصل رد غير واضح من المساعد", result["error"])
        self.assertNotIn("not-json", result["error"])

    def test_reports_stream_ended_before_completion(self):
        self.mock_urlopen.return_value = BytesIO(
            (
                'event: step.delta\n'
                'data: {"event_type":"step.delta","delta":{"type":"text","text":"جزء من الإجابة"}}\n\n'
            ).encode()
        )
        status, result = self.post({"message": "مرحبا"})
        self.assertEqual(status, 200)
        self.assertIn("انقطع الرد قبل اكتماله", result["error"])

    def test_saves_streamed_messages_and_exposes_history(self):
        self.mock_urlopen.return_value = BytesIO(
            (
                'event: step.delta\n'
                'data: {"event_type":"step.delta","delta":{"type":"text","text":"إجابة محفوظة"}}\n\n'
                'event: interaction.completed\n'
                'data: {"event_type":"interaction.completed","interaction":{"id":"v1_saved"}}\n\n'
            ).encode()
        )
        status, response = self.post({"message": "ساعدني في العلوم"})
        self.assertEqual(status, 200)
        done = next(event for name, event in response["events"] if name == "done")
        self.assertNotIn("sources", done)

        status, history, _ = self.request("GET", "/api/conversations")
        self.assertEqual(status, 200)
        record = history["conversations"][0]
        self.assertEqual(record["title"], "ساعدني في العلوم")

        status, detail, _ = self.request(
            "GET", f"/api/conversations/{record['id']}"
        )
        self.assertEqual(status, 200)
        self.assertEqual(detail["messages"][0]["role"], "user")
        self.assertEqual(detail["messages"][0]["content"], "ساعدني في العلوم")
        self.assertEqual(detail["messages"][1]["role"], "assistant")
        self.assertEqual(detail["messages"][1]["content"], "إجابة محفوظة")
        self.assertEqual(response["conversationId"], record["id"])

    def test_does_not_persist_attached_image_for_history(self):
        self.mock_urlopen.return_value = BytesIO(
            (
                'event: step.delta\n'
                'data: {"event_type":"step.delta","delta":{"type":"text","text":"أرى كتابًا."}}\n\n'
                'event: interaction.completed\n'
                'data: {"event_type":"interaction.completed","interaction":{"id":"v1_book"}}\n\n'
            ).encode()
        )
        image = base64.b64encode(b"image-data").decode()
        status, response = self.post(
            {
                "message": "",
                "image": {"mimeType": "image/png", "data": image},
            }
        )
        self.assertEqual(status, 200)
        status, detail, _ = self.request(
            "GET", f"/api/conversations/{response['conversationId']}"
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            detail["messages"][0]["image"],
            None,
        )
        self.assertIn("مرفق صورة (غير محفوظة)", detail["messages"][0]["content"])
        self.assertIsNone(
            server.database.get_conversation(
                self.user["id"], response["conversationId"]
            )[1][0]["image_data"]
        )

    def test_can_rename_and_delete_only_owned_conversations(self):
        record = server.database.prepare_user_message(
            self.user["id"], None, "عنوان أول", "رسالة", None, None
        )
        status, result, _ = self.request(
            "PATCH",
            f"/api/conversations/{record['id']}",
            {"title": "عنوان معدل"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["title"], "عنوان معدل")

        other_user = server.database.register_user(
            "other@example.com", "correct-horse-battery"
        )
        other_token = server.database.create_session(other_user["id"])
        request = Request(
            f"{self.base_url}/api/conversations/{record['id']}",
            headers={"Cookie": f"school_assistant_session={other_token}"},
        )
        with self.assertRaises(HTTPError) as missing:
            urlopen(request)
        self.assertEqual(missing.exception.code, 404)

        status, _, _ = self.request("DELETE", f"/api/conversations/{record['id']}")
        self.assertEqual(status, 204)
        self.assertEqual(server.database.list_conversations(self.user["id"]), [])

    def test_admin_can_delete_only_target_users_conversations(self):
        first = server.database.prepare_user_message(
            self.user["id"], None, "first-key", "المحادثة الأولى", None, None
        )
        second = server.database.prepare_user_message(
            self.user["id"], None, "second-key", "المحادثة الثانية", None, None
        )
        other_user = server.database.register_user(
            "admin@example.com", "admin-long-password"
        )
        admin_token = server.database.create_session(other_user["id"])

        status, denied, _ = self.request(
            "GET",
            f"/api/admin/users/{self.user['id']}/conversations",
            authorized=False,
        )
        self.assertEqual(status, 401)
        status, denied, _ = self.request(
            "DELETE",
            f"/api/admin/users/{self.user['id']}/conversations/{first['id']}",
        )
        self.assertEqual(status, 403)

        with patch.dict(server.os.environ, {"ADMIN_EMAIL": "admin@example.com"}):
            self.session_token = admin_token
            status, conversations, _ = self.request(
                "GET", f"/api/admin/users/{self.user['id']}/conversations"
            )
            self.assertEqual(status, 200)
            self.assertEqual(
                {item["id"] for item in conversations["conversations"]},
                {first["id"], second["id"]},
            )
            status, dashboard, _ = self.request("GET", "/api/admin/dashboard")
            self.assertEqual(status, 200)
            target_user = next(
                user for user in dashboard["users"] if user["id"] == self.user["id"]
            )
            self.assertEqual(target_user["conversation_count"], 2)

            status, _, _ = self.request(
                "DELETE",
                f"/api/admin/users/{other_user['id']}/conversations/{first['id']}",
            )
            self.assertEqual(status, 404)
            self.assertEqual(
                len(server.database.list_conversations(self.user["id"])), 2
            )

            status, _, _ = self.request(
                "DELETE",
                f"/api/admin/users/{self.user['id']}/conversations/{first['id']}",
            )
            self.assertEqual(status, 204)
            self.assertEqual(
                [item["id"] for item in server.database.list_conversations(self.user["id"])],
                [second["id"]],
            )
            self.assertIsNotNone(
                server.database.get_session_user(self.session_token)
            )
            status, dashboard, _ = self.request("GET", "/api/admin/dashboard")
            self.assertEqual(status, 200)
            target_user = next(
                user for user in dashboard["users"] if user["id"] == self.user["id"]
            )
            self.assertEqual(target_user["conversation_count"], 1)
            with server.database.connect() as connection:
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM messages WHERE conversation_id = ?",
                        (first["id"],),
                    ).fetchone()[0],
                    0,
                )

    def test_conversation_delete_database_failure_is_reported(self):
        record = server.database.prepare_user_message(
            self.user["id"], None, "delete-failure", "سؤال", None, None
        )
        with patch.object(
            server.database,
            "delete_conversation",
            side_effect=sqlite3.OperationalError("database unavailable"),
        ):
            status, result, _ = self.request(
                "DELETE", f"/api/conversations/{record['id']}"
            )
        self.assertEqual(status, 500)
        self.assertIn("تعذّر حذف المحادثة", result["error"])
        self.assertEqual(len(server.database.list_conversations(self.user["id"])), 1)

    def test_admin_user_delete_database_failure_is_reported(self):
        admin = server.database.register_user(
            "admin@example.com", "admin-long-password"
        )
        self.session_token = server.database.create_session(admin["id"])
        with patch.dict(server.os.environ, {"ADMIN_EMAIL": "admin@example.com"}):
            with patch.object(
                server.database,
                "delete_user",
                side_effect=sqlite3.OperationalError("database unavailable"),
            ):
                status, result, _ = self.request(
                    "DELETE", f"/api/admin/users/{self.user['id']}"
                )
        self.assertEqual(status, 500)
        self.assertIn("تعذّر حذف المستخدم", result["error"])
        self.assertIsNotNone(server.database.get_session_user(self.session_token))

    def test_registers_and_logs_in_with_persistent_session(self):
        full_name = "محمد أحمد علي الحسن"
        email = server.student_email(server.name_tokens(full_name))
        registration = {
            "fullName": full_name,
            "phone": "0791234567",
            "grade": "10",
            "password": "long-enough-pass",
            "remember": True,
        }
        with patch.object(server.USER_PROFILES, "set"):
            status, result, headers = self.request(
                "POST",
                "/api/auth/register",
                registration,
                authorized=False,
            )
        self.assertEqual(status, 200)
        self.assertEqual(result["user"]["email"], email)
        logged_in_user_id = result["user"]["id"]
        cookie = headers["Set-Cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)
        self.assertIn("Max-Age=31536000", cookie)
        with server.database.connect() as connection:
            password_hash = connection.execute(
                "SELECT password_hash FROM users WHERE id = ?",
                (logged_in_user_id,),
            ).fetchone()["password_hash"]
        self.assertNotEqual(password_hash, "long-enough-pass")
        self.assertTrue(password_hash.startswith("pbkdf2_sha256$"))
        restarted_database = server.Database(server.database.path)
        self.assertEqual(
            restarted_database.get_session_user(
                cookie.split(";", 1)[0].split("=", 1)[1]
            )["id"],
            logged_in_user_id,
        )

        with patch.object(server.USER_PROFILES, "set"):
            status, duplicate, _ = self.request(
                "POST",
                "/api/auth/register",
                {**registration, "password": "another-long-pass"},
                authorized=False,
            )
        self.assertEqual(status, 409)
        self.assertIn("مسجّل مسبقًا", duplicate["error"])

        status, login, login_headers = self.request(
            "POST",
            "/api/auth/login",
            {"identifier": full_name, "password": "long-enough-pass"},
            authorized=False,
        )
        self.assertEqual(status, 200)
        self.assertEqual(login["user"]["id"], logged_in_user_id)
        self.assertIn("Max-Age=31536000", login_headers["Set-Cookie"])
        self.session_token = login_headers["Set-Cookie"].split(";", 1)[0].split("=", 1)[1]
        status, result, _ = self.request("GET", "/api/me")
        self.assertEqual(status, 200)
        self.assertEqual(result["user"]["id"], logged_in_user_id)

    def test_rejects_short_password_and_invalid_credentials(self):
        status, result = self.post(
            {
                "fullName": "محمد أحمد علي الحسن",
                "phone": "0791234567",
                "grade": "10",
                "password": "short",
            },
            path="/api/auth/register",
            authorized=False,
        )
        self.assertEqual(status, 400)
        self.assertIn("10 أحرف", result["error"])

        status, result = self.post(
            {
                "email": "student@example.com",
                "password": "incorrect-password",
            },
            path="/api/auth/login",
            authorized=False,
        )
        self.assertEqual(status, 401)
        self.assertIn("غير صحيحة", result["error"])

    def test_login_requests_account_creation_for_unregistered_student_name(self):
        status, result, _ = self.request(
            "POST",
            "/api/auth/login",
            {
                "identifier": "محمد أحمد علي الحسن",
                "password": "incorrect-password",
            },
            authorized=False,
        )

        self.assertEqual(status, 404)
        self.assertIn("لم يتم العثور على حساب", result["error"])
        self.assertIn("أنشئ حسابًا جديدًا", result["error"])

    def test_changes_password_and_invalidates_other_sessions(self):
        other_token = server.database.create_session(self.user["id"])
        status, result = self.post(
            {
                "currentPassword": "correct-horse-battery",
                "newPassword": "brand-new-password",
                "confirmPassword": "different-new-password",
            },
            path="/api/auth/change-password",
        )
        self.assertEqual(status, 400)
        self.assertIn("غير متطابقتين", result["error"])

        status, result = self.post(
            {
                "currentPassword": "wrong-current-password",
                "newPassword": "brand-new-password",
                "confirmPassword": "brand-new-password",
            },
            path="/api/auth/change-password",
        )
        self.assertEqual(status, 400)
        self.assertIn("الحالية غير صحيحة", result["error"])
        self.assertIsNotNone(
            server.database.login_user("student@example.com", "correct-horse-battery")
        )
        self.assertIsNone(
            server.database.login_user("student@example.com", "brand-new-password")
        )

        status, result = self.post(
            {
                "currentPassword": "correct-horse-battery",
                "newPassword": "short",
                "confirmPassword": "short",
            },
            path="/api/auth/change-password",
        )
        self.assertEqual(status, 400)
        self.assertIn("10 أحرف", result["error"])

        status, result = self.post(
            {
                "currentPassword": "correct-horse-battery",
                "newPassword": "brand-new-password",
                "confirmPassword": "brand-new-password",
            },
            path="/api/auth/change-password",
        )
        self.assertEqual(status, 200)
        self.assertTrue(result["ok"])
        self.assertIsNotNone(server.database.get_session_user(self.session_token))
        self.assertIsNone(server.database.get_session_user(other_token))
        self.assertIsNone(
            server.database.login_user("student@example.com", "correct-horse-battery")
        )
        self.assertEqual(
            server.database.login_user("student@example.com", "brand-new-password")[
                "id"
            ],
            self.user["id"],
        )

    def test_recovers_password_with_email_verification_code(self):
        other_token = server.database.create_session(self.user["id"])
        with patch("server.send_password_reset_email") as send_email:
            status, request_result = self.post(
                {"email": "STUDENT@example.com"},
                path="/api/auth/forgot-password",
                authorized=False,
            )
            self.assertEqual(status, 200)
            self.assertIn("10 دقائق", request_result["message"])
            send_email.assert_called_once()
            recipient, code = send_email.call_args.args
            self.assertEqual(recipient, "student@example.com")
            self.assertRegex(code, r"^[0-9]{6}$")
            status, throttled = self.post(
                {"email": "student@example.com"},
                path="/api/auth/forgot-password",
                authorized=False,
            )
            self.assertEqual(status, 200)
            self.assertEqual(request_result, throttled)
            send_email.assert_called_once()
            wrong_code = "000000" if code != "000000" else "000001"

            status, invalid = self.post(
                {
                    "email": "student@example.com",
                    "code": wrong_code,
                    "newPassword": "a-new-long-password",
                },
                path="/api/auth/reset-password",
                authorized=False,
            )
            self.assertEqual(status, 400)
            self.assertIn("رمز التحقق", invalid["error"])

            status, result = self.post(
                {
                    "email": "student@example.com",
                    "code": code,
                    "newPassword": "a-new-long-password",
                },
                path="/api/auth/reset-password",
                authorized=False,
            )
            self.assertEqual(status, 200)
            self.assertTrue(result["ok"])

            status, unknown_email = self.post(
                {"email": "unknown@example.com"},
                path="/api/auth/forgot-password",
                authorized=False,
            )
            self.assertEqual(status, 200)
            self.assertEqual(request_result, unknown_email)
            self.assertEqual(send_email.call_count, 1)

        self.assertIsNone(server.database.get_session_user(self.session_token))
        self.assertIsNone(server.database.get_session_user(other_token))
        self.assertIsNone(
            server.database.login_user("student@example.com", "correct-horse-battery")
        )
        self.assertEqual(
            server.database.login_user("student@example.com", "a-new-long-password")[
                "id"
            ],
            self.user["id"],
        )

    def test_remember_device_can_be_disabled(self):
        status, _, headers = self.request(
            "POST",
            "/api/auth/login",
            {
                "email": "student@example.com",
                "password": "correct-horse-battery",
                "remember": False,
            },
            authorized=False,
        )
        self.assertEqual(status, 200)
        self.assertIn("Max-Age=86400", headers["Set-Cookie"])

    def test_admin_dashboard_counts_page_views_and_deletes_users(self):
        student_token = self.session_token
        admin_user = server.database.register_user(
            "admin@example.com", "admin-long-password"
        )
        admin_token = server.database.create_session(admin_user["id"])
        with patch.dict(server.os.environ, {"ADMIN_EMAIL": "admin@example.com"}):
            status, denied_password_change, _ = self.request(
                "POST",
                f"/api/admin/users/{admin_user['id']}/password",
                {"newPassword": "another-new-password"},
            )
            self.assertEqual(status, 403)
            self.assertIn("صلاحية", denied_password_change["error"])

            status, denied, _ = self.request("GET", "/api/admin/dashboard")
            self.assertEqual(status, 403)
            self.assertIn("صلاحية", denied["error"])

            self.session_token = admin_token
            status, me, _ = self.request("GET", "/api/me")
            self.assertEqual(status, 200)
            self.assertTrue(me["isAdmin"])

            with urlopen(
                Request(
                    f"{self.base_url}/",
                    headers={"Accept": "text/html"},
                )
            ) as response:
                self.assertEqual(response.status, 200)
                response.read()

            status, dashboard, _ = self.request("GET", "/api/admin/dashboard")
            self.assertEqual(status, 200)
            self.assertEqual(dashboard["pageViews"], 1)
            self.assertEqual(dashboard["uniqueVisitors"], 1)
            self.assertEqual(len(dashboard["users"]), 2)
            self.assertTrue(
                all(
                    "password" not in user and "password_hash" not in user
                    for user in dashboard["users"]
                )
            )

            status, denied_self_delete, _ = self.request(
                "DELETE", f"/api/admin/users/{admin_user['id']}"
            )
            self.assertEqual(status, 400)
            self.assertIn("لا يمكنك حذف", denied_self_delete["error"])

            status, denied_self_password, _ = self.request(
                "POST",
                f"/api/admin/users/{admin_user['id']}/password",
                {"newPassword": "another-new-password"},
            )
            self.assertEqual(status, 400)
            self.assertIn("إعدادات حسابك", denied_self_password["error"])

            student_session = server.database.create_session(self.user["id"])
            status, short_password, _ = self.request(
                "POST",
                f"/api/admin/users/{self.user['id']}/password",
                {"newPassword": "short"},
            )
            self.assertEqual(status, 400)
            self.assertIn("10 أحرف", short_password["error"])
            self.assertIsNotNone(
                server.database.login_user(
                    "student@example.com", "correct-horse-battery"
                )
            )

            status, result, _ = self.request(
                "POST",
                f"/api/admin/users/{self.user['id']}/password",
                {"newPassword": "admin-set-password"},
            )
            self.assertEqual(status, 200)
            self.assertTrue(result["ok"])
            self.assertIsNone(server.database.get_session_user(student_session))
            self.assertIsNone(
                server.database.login_user(
                    "student@example.com", "correct-horse-battery"
                )
            )
            self.assertIsNotNone(
                server.database.login_user(
                    "student@example.com", "admin-set-password"
                )
            )

            status, _, _ = self.request(
                "DELETE", f"/api/admin/users/{self.user['id']}"
            )
            self.assertEqual(status, 204)
            self.assertIsNone(server.database.get_session_user(student_token))
            self.assertIsNotNone(server.database.get_session_user(admin_token))

    def test_page_views_dedupe_refreshes_and_count_new_browsers(self):
        def open_page(path, visitor_cookie=None):
            headers = {
                "Accept": "text/html",
                "Cookie": f"school_assistant_session={self.session_token}",
            }
            if visitor_cookie:
                headers["Cookie"] += f"; {visitor_cookie}"
            with urlopen(Request(f"{self.base_url}{path}", headers=headers)) as response:
                self.assertEqual(response.status, 200)
                set_cookie = response.headers.get("Set-Cookie")
                return set_cookie.split(";", 1)[0] if set_cookie else visitor_cookie

        first_browser = open_page("/")
        self.assertIsNotNone(first_browser)
        self.assertEqual(open_page("/?reload=1", first_browser), first_browser)

        with urlopen(f"{self.base_url}/") as response:
            self.assertEqual(response.status, 200)
        second_browser = open_page("/?source=another-browser")
        self.assertIsNotNone(second_browser)
        self.assertNotEqual(first_browser, second_browser)
        open_page("/index.html?reload=2", second_browser)

        with patch.dict(server.os.environ, {"ADMIN_EMAIL": self.user["email"]}):
            status, dashboard, _ = self.request("GET", "/api/admin/dashboard")
            stats_status, live_statistics, _ = self.request(
                "GET", "/api/admin/statistics"
            )
        self.assertEqual(status, 200)
        self.assertEqual(dashboard["pageViews"], 2)
        self.assertEqual(dashboard["uniqueVisitors"], 2)
        self.assertEqual(stats_status, 200)
        self.assertEqual(live_statistics, {
            "pageViews": 2,
            "uniqueVisitors": 2,
        })

    def test_admin_can_grant_and_revoke_unlimited_admin_roles(self):
        primary_admin = server.database.register_user(
            "admin@example.com", "admin-long-password"
        )
        primary_token = server.database.create_session(primary_admin["id"])
        promoted_users = [
            server.database.register_user(
                f"admin{index}@example.com", "admin-long-password"
            )
            for index in range(3)
        ]
        with patch.dict(server.os.environ, {"ADMIN_EMAIL": "admin@example.com"}):
            self.session_token = primary_token
            for promoted in promoted_users:
                status, result, _ = self.request(
                    "POST",
                    f"/api/admin/users/{promoted['id']}/admin",
                    {"isAdmin": True},
                )
                self.assertEqual(status, 200)
                self.assertTrue(result["isAdmin"])

            status, dashboard, _ = self.request("GET", "/api/admin/dashboard")
            self.assertEqual(status, 200)
            granted_admins = {
                user["id"] for user in dashboard["users"] if user["is_admin"]
            }
            self.assertTrue(
                {user["id"] for user in promoted_users}.issubset(granted_admins)
            )
            self.assertTrue(
                next(
                    user for user in dashboard["users"]
                    if user["id"] == primary_admin["id"]
                )["is_primary_admin"]
            )

            status, self_change, _ = self.request(
                "POST",
                f"/api/admin/users/{primary_admin['id']}/admin",
                {"isAdmin": False},
            )
            self.assertEqual(status, 400)
            self.assertIn("حسابك", self_change["error"])

            self.session_token = server.database.create_session(
                promoted_users[0]["id"]
            )
            status, promoted_me, _ = self.request("GET", "/api/me")
            self.assertEqual(status, 200)
            self.assertTrue(promoted_me["isAdmin"])
            status, _, _ = self.request("GET", "/api/admin/dashboard")
            self.assertEqual(status, 200)

            status, protected_primary, _ = self.request(
                "POST",
                f"/api/admin/users/{primary_admin['id']}/admin",
                {"isAdmin": False},
            )
            self.assertEqual(status, 400)
            self.assertIn("الأدمن الأساسي", protected_primary["error"])

            status, protected_delete, _ = self.request(
                "DELETE", f"/api/admin/users/{primary_admin['id']}"
            )
            self.assertEqual(status, 400)
            self.assertIn("الأدمن الأساسي", protected_delete["error"])

            status, result, _ = self.request(
                "POST",
                f"/api/admin/users/{promoted_users[1]['id']}/admin",
                {"isAdmin": False},
            )
            self.assertEqual(status, 200)
            self.assertFalse(result["isAdmin"])
            self.session_token = server.database.create_session(
                promoted_users[1]["id"]
            )
            status, revoked_me, _ = self.request("GET", "/api/me")
            self.assertEqual(status, 200)
            self.assertFalse(revoked_me["isAdmin"])
            status, denied, _ = self.request("GET", "/api/admin/dashboard")
            self.assertEqual(status, 403)
            self.assertIn("صلاحية", denied["error"])

    def test_secondary_admin_cannot_change_or_delete_other_admins(self):
        primary = server.database.register_user(
            "owner@example.com", "primary-admin-password"
        )
        secondary = server.database.register_user(
            "secondary@example.com", "secondary-admin-password"
        )
        other_admin = server.database.register_user(
            "other-admin@example.com", "other-admin-password"
        )
        regular_user = server.database.register_user(
            "regular@example.com", "regular-user-password"
        )
        server.database.set_user_admin(
            secondary["id"], True, primary["id"], "owner@example.com"
        )
        server.database.set_user_admin(
            other_admin["id"], True, primary["id"], "owner@example.com"
        )
        self.session_token = server.database.create_session(secondary["id"])
        secondary_session = self.session_token

        with patch.dict(server.os.environ, {"ADMIN_EMAIL": "owner@example.com"}):
            status, identity, _ = self.request("GET", "/api/me")
            self.assertEqual(status, 200)
            self.assertTrue(identity["isAdmin"])
            self.assertFalse(identity["isPrimaryAdmin"])

            status, denied_password, _ = self.request(
                "POST",
                f"/api/admin/users/{other_admin['id']}/password",
                {"newPassword": "changed-admin-password"},
            )
            self.assertEqual(status, 403)
            self.assertIn("أدمن آخر", denied_password["error"])
            self.assertIsNotNone(
                server.database.login_user(
                    "other-admin@example.com", "other-admin-password"
                )
            )

            status, denied_delete, _ = self.request(
                "DELETE", f"/api/admin/users/{other_admin['id']}"
            )
            self.assertEqual(status, 403)
            self.assertIn("أدمن آخر", denied_delete["error"])
            self.assertIsNotNone(
                server.database.get_session_user(
                    server.database.create_session(other_admin["id"])
                )
            )

            status, changed_user, _ = self.request(
                "POST",
                f"/api/admin/users/{regular_user['id']}/password",
                {"newPassword": "changed-regular-password"},
            )
            self.assertEqual(status, 200)
            self.assertTrue(changed_user["ok"])

            status, _, _ = self.request(
                "DELETE", f"/api/admin/users/{regular_user['id']}"
            )
            self.assertEqual(status, 204)

            self.session_token = server.database.create_session(primary["id"])
            status, primary_identity, _ = self.request("GET", "/api/me")
            self.assertEqual(status, 200)
            self.assertTrue(primary_identity["isPrimaryAdmin"])

            status, primary_password_change, _ = self.request(
                "POST",
                f"/api/admin/users/{other_admin['id']}/password",
                {"newPassword": "primary-changed-password"},
            )
            self.assertEqual(status, 200)
            self.assertTrue(primary_password_change["ok"])

            status, _, _ = self.request(
                "DELETE", f"/api/admin/users/{other_admin['id']}"
            )
            self.assertEqual(status, 204)
            self.assertIsNotNone(server.database.get_session_user(secondary_session))

    def test_online_users_are_distinct_and_expire_after_sixty_seconds(self):
        database = server.database
        second_user = database.register_user(
            "second-student@example.com", "correct-horse-battery"
        )
        second_tab_session = database.create_session(self.user["id"])
        second_user_session = database.create_session(second_user["id"])
        expired_session = database.create_session(second_user["id"], lifetime=-1)

        self.assertEqual(database.get_online_user_count(), 2)

        stale_at = int(server.time.time()) - 61
        with database.connect() as connection:
            connection.execute(
                "UPDATE sessions SET last_activity_at = ? WHERE user_id = ?",
                (stale_at, self.user["id"]),
            )
        self.assertEqual(database.get_online_user_count(), 1)

        status, identity, _ = self.request("GET", "/api/me")
        self.assertEqual(status, 200)
        self.assertEqual(identity["user"]["id"], self.user["id"])
        self.assertEqual(database.get_online_user_count(), 2)

        database.delete_session(second_tab_session)
        self.assertEqual(database.get_online_user_count(), 2)
        database.delete_session(self.session_token)
        self.assertEqual(database.get_online_user_count(), 1)
        database.delete_session(second_user_session)
        self.assertEqual(database.get_online_user_count(), 0)
        self.assertIsNone(database.get_session_user(expired_session))

    def test_online_users_endpoint_requires_admin_and_reports_database_errors(self):
        status, _, _ = self.request(
            "GET", "/api/admin/online-users", authorized=False
        )
        self.assertEqual(status, 401)

        status, _, _ = self.request("GET", "/api/admin/online-users")
        self.assertEqual(status, 403)

        with server.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO admin_users (user_id, granted_at)
                VALUES (?, ?)
                """,
                (self.user["id"], int(server.time.time())),
            )

        status, result, _ = self.request("GET", "/api/admin/online-users")
        self.assertEqual(status, 200)
        self.assertEqual(result["onlineUsers"], 1)
        self.assertIsInstance(result["updatedAt"], int)

        with patch.object(
            server.database,
            "get_online_user_count",
            side_effect=sqlite3.OperationalError("database unavailable"),
        ):
            status, result, _ = self.request("GET", "/api/admin/online-users")
        self.assertEqual(status, 503)
        self.assertIn("تعذّر تحديث", result["error"])

        status, _, _ = self.request("POST", "/api/logout")
        self.assertEqual(status, 204)
        self.assertEqual(server.database.get_online_user_count(), 0)


class DatabaseContextTests(unittest.TestCase):
    def test_migrates_existing_sessions_for_live_activity(self):
        with tempfile.TemporaryDirectory() as folder:
            database_path = Path(folder) / "legacy-sessions.sqlite3"
            connection = sqlite3.connect(database_path)
            try:
                connection.execute(
                    """
                    CREATE TABLE sessions (
                        token_hash TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        expires_at INTEGER NOT NULL
                    )
                    """
                )
                connection.commit()
            finally:
                connection.close()

            migrated_database = server.Database(database_path)
            with migrated_database.connect() as migrated_connection:
                columns = {
                    row["name"]
                    for row in migrated_connection.execute(
                        "PRAGMA table_info(sessions)"
                    ).fetchall()
                }
                indexes = {
                    row["name"]
                    for row in migrated_connection.execute(
                        "PRAGMA index_list(sessions)"
                    ).fetchall()
                }
            self.assertIn("last_activity_at", columns)
            self.assertIn("sessions_last_activity_idx", indexes)

    def test_visit_counts_are_deduplicated_and_persist_after_database_reopen(self):
        with tempfile.TemporaryDirectory() as folder:
            database_path = Path(folder) / "visits.sqlite3"
            database = server.Database(database_path)
            database.record_page_view("browser-one", now=1_000)
            database.record_page_view("browser-one", now=1_001)
            database.record_page_view("browser-two", now=1_002)
            database.record_page_view("browser-one", now=1_031)

            reopened = server.Database(database_path)
            statistics = reopened.admin_dashboard()
            self.assertEqual(statistics["pageViews"], 3)
            self.assertEqual(statistics["uniqueVisitors"], 2)

    def test_existing_page_total_survives_unique_visitor_migration(self):
        with tempfile.TemporaryDirectory() as folder:
            database_path = Path(folder) / "legacy-statistics.sqlite3"
            connection = sqlite3.connect(database_path)
            try:
                with connection:
                    connection.execute(
                        "CREATE TABLE site_statistics ("
                        "id INTEGER PRIMARY KEY CHECK(id = 1), "
                        "page_views INTEGER NOT NULL DEFAULT 0)"
                    )
                    connection.execute(
                        "INSERT INTO site_statistics (id, page_views) VALUES (1, 7)"
                    )
            finally:
                connection.close()

            database = server.Database(database_path)
            statistics = database.admin_dashboard()
            self.assertEqual(statistics["pageViews"], 7)
            self.assertEqual(statistics["uniqueVisitors"], 1)

    def test_context_budget_keeps_newest_messages_and_request_budget_limits_images(self):
        messages = [
            {
                "id": 1,
                "role": "user",
                "content": "ancient " * 80,
                "image_data": None,
            },
            {
                "id": 2,
                "role": "assistant",
                "content": "recent answer",
                "image_data": None,
            },
            {
                "id": 3,
                "role": "user",
                "content": "current",
                "image_data": None,
            },
        ]
        with patch.object(server, "MAX_GEMINI_CONTEXT_TOKENS", 100):
            parts = server.build_conversation_input(
                messages,
                3,
                "current",
                [{"type": "text", "text": "current"}],
                "system",
            )
        history = "\n".join(part.get("text", "") for part in parts)
        self.assertIn("recent answer", history)
        self.assertNotIn("ancient", history)

        with patch.object(server, "MAX_GEMINI_REQUEST_BYTES", 1024):
            selected = server.select_images_that_fit(
                [{"id": 1, "image_size": 100, "has_image": True}],
                [{"type": "text", "text": "current"}],
                "system",
            )
        self.assertEqual(selected, [])

    def test_conversation_history_does_not_persist_images(self):
        with tempfile.TemporaryDirectory() as folder:
            database_path = Path(folder) / "conversation.sqlite3"
            database = server.Database(database_path)
            user = database.register_user(
                "history@example.com", "correct-horse-battery"
            )
            first = database.prepare_user_message(
                user["id"],
                None,
                "مسألة بالصورة",
                "حل السؤال في الصورة",
                "image/png",
                b"persisted-image-bytes",
            )
            database.complete_assistant_message(
                first["id"], "أحتاج قراءة الأرقام أولًا.", "response-1"
            )
            second = database.prepare_user_message(
                user["id"],
                first["id"],
                "مسألة بالصورة",
                "الرقم هو ٥",
                None,
                None,
            )
            database.complete_assistant_message(
                second["id"], "إذن الحل هو ١٠.", "response-2"
            )

            reopened = server.Database(database_path)
            messages = reopened.get_conversation_context(user["id"], first["id"])
            self.assertEqual(
                [message["role"] for message in messages],
                ["user", "assistant", "user", "assistant"],
            )
            self.assertEqual(
                [message["content"] for message in messages],
                [
                    "حل السؤال في الصورة\nمرفق صورة (غير محفوظة)",
                    "أحتاج قراءة الأرقام أولًا.",
                    "الرقم هو ٥",
                    "إذن الحل هو ١٠.",
                ],
            )
            self.assertEqual(
                [message["id"] for message in messages],
                sorted(message["id"] for message in messages),
            )
            images = reopened.get_conversation_images(
                user["id"], first["id"], [first["message_id"]]
            )
            self.assertEqual(images, {})

            other_user = reopened.register_user(
                "other@example.com", "correct-horse-battery"
            )
            self.assertIsNone(
                reopened.get_conversation_context(other_user["id"], first["id"])
            )
            self.assertEqual(
                reopened.get_conversation_images(
                    other_user["id"], first["id"], [first["message_id"]]
                ),
                {},
            )

    def test_database_startup_removes_legacy_image_data(self):
        with tempfile.TemporaryDirectory() as folder:
            database_path = Path(folder) / "legacy-images.sqlite3"
            database = server.Database(database_path)
            user = database.register_user(
                "legacy-image@example.com", "correct-horse-battery"
            )
            message = database.prepare_user_message(
                user["id"],
                None,
                "سؤال مصور",
                "حل السؤال",
                "image/png",
                b"legacy-image-bytes",
            )
            with database.connect() as connection:
                connection.execute(
                    "UPDATE messages SET image_data = ? WHERE id = ?",
                    (b"legacy-image-bytes", message["message_id"]),
                )

            reopened = server.Database(database_path)
            conversation = reopened.get_conversation(user["id"], message["id"])
            self.assertIsNone(conversation[1][0]["image_data"])
            self.assertIn("مرفق صورة (غير محفوظة)", conversation[1][0]["content"])


if __name__ == "__main__":
    unittest.main()
