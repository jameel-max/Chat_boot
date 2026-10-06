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
        self.api.stop()
        self.title_generation.stop()
        self.env.stop()
        server.database = self.previous_database
        self.temp_directory.cleanup()
        self.httpd.shutdown()
        self.thread.join()
        self.httpd.server_close()

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
                "title": title.get("title", meta.get("title")),
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

    def test_requires_gemini_api_key(self):
        with patch.dict(server.os.environ, {"GEMINI_API_KEY": ""}):
            status, result = self.post({"message": "مرحبا"})
        self.assertEqual(status, 503)
        self.assertIn("GEMINI_API_KEY", result["error"])
        self.mock_urlopen.assert_not_called()

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
        self.assertEqual(sent["model"], "gemini-3.1-flash-lite")
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

    def test_curriculum_context_and_verified_source_flow_through_existing_chat(self):
        curriculum_result = {
            "searched": True,
            "extra_parts": [
                {"type": "text", "text": "[مقطع رسمي | صفحة 47]\nالقوة تساوي الكتلة مضروبة بالتسارع."}
            ],
            "system_note": "التزم بالمقطع الرسمي ولا تخترع صفحة.",
            "answer_suffix": "\n\n**المصادر:**\n[1] كتاب الفيزياء — ص. 47",
            "sources": [{"book": "كتاب الفيزياء", "page": 47}],
            "official": True,
        }
        self.mock_urlopen.return_value = BytesIO(
            (
                'event: step.delta\n'
                'data: {"event_type":"step.delta","delta":{"type":"text","text":"القوة تساوي الكتلة مضروبة بالتسارع."}}\n\n'
                'event: interaction.completed\n'
                'data: {"event_type":"interaction.completed","interaction":{"id":"v1_curriculum"}}\n\n'
            ).encode()
        )

        with patch("server.retrieve_curriculum", return_value=curriculum_result) as retrieve:
            status, result = self.post({"message": "اشرح قانون نيوتن الثاني"})

        self.assertEqual(status, 200)
        retrieve.assert_called_once()
        sent = json.loads(self.mock_urlopen.call_args.args[0].data)
        self.assertIn("التزم بالمقطع الرسمي", sent["system_instruction"])
        sent_text = "\n".join(
            part.get("text", "") for part in sent["input"] if part["type"] == "text"
        )
        self.assertIn("القوة تساوي الكتلة مضروبة بالتسارع", sent_text)
        self.assertIn("اشرح قانون نيوتن الثاني", sent_text)
        self.assertEqual(result["answer"], "القوة تساوي الكتلة مضروبة بالتسارع.")
        done = next(
            event for name, event in result["events"] if name == "done"
        )
        self.assertNotIn("sources", done)

        stored = server.database.get_conversation(
            self.user["id"], result["conversationId"]
        )
        self.assertEqual(stored[1][-1]["content"], result["answer"])

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

    def test_curriculum_embedding_failure_does_not_use_unverified_fallback(self):
        with patch(
            "server.retrieve_curriculum",
            side_effect=server.CurriculumError("embedding unavailable"),
        ):
            status, result = self.post({"message": "اشرح قانون نيوتن الثاني"})
        self.assertEqual(status, 503)
        self.assertIn("تعذّر البحث في محتوى المنهج", result["error"])
        self.mock_urlopen.assert_not_called()

    def test_curriculum_filters_using_explicit_subject_in_postgres_chat_history(self):
        previous = server.database.prepare_user_message(
            self.user["id"],
            None,
            "سؤال في الفيزياء",
            "أنا أدرس الفيزياء في الفصل الثاني",
            None,
            None,
        )
        server.database.complete_assistant_message(
            previous["id"], "تمام، سأشرح على هذا الأساس.", "old-interaction"
        )
        self.mock_urlopen.return_value = BytesIO(
            (
                'event: step.delta\n'
                'data: {"event_type":"step.delta","delta":{"type":"text","text":"الشرح."}}\n\n'
                'event: interaction.completed\n'
                'data: {"event_type":"interaction.completed","interaction":{"id":"v1_followup"}}\n\n'
            ).encode()
        )
        empty_retrieval = {
            "searched": True,
            "extra_parts": [],
            "system_note": "",
            "answer_suffix": "",
            "sources": [],
        }

        with patch(
            "server.retrieve_curriculum", return_value=empty_retrieval
        ) as retrieve:
            status, _ = self.post(
                {"message": "اشرحها", "conversationId": previous["id"]}
            )

        self.assertEqual(status, 200)
        self.assertIsNone(retrieve.call_args.args[2])
        kwargs = retrieve.call_args.kwargs
        self.assertEqual(
            kwargs["conversation_history"][0]["content"],
            "أنا أدرس الفيزياء في الفصل الثاني",
        )

    def test_reloads_referenced_previous_image_but_skips_unrelated_images(self):
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
        self.assertEqual(len(prior_images), 1)
        self.assertEqual(
            base64.b64decode(prior_images[0]["data"]), previous_image
        )

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
        self.assertEqual(result["responseId"], "")
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
        status, result = self.post({"message": "مرحبا"})
        self.assertEqual(status, 502)
        self.assertIn("خدمة Gemini", result["error"])

    def test_reports_malformed_gemini_stream_event(self):
        self.mock_urlopen.return_value = BytesIO(
            b"event: step.delta\ndata: not-json\n\n"
        )
        status, result = self.post({"message": "مرحبا"})
        self.assertEqual(status, 200)
        self.assertIn("حدث بث غير مفهوم", result["error"])

    def test_reports_stream_ended_before_completion(self):
        self.mock_urlopen.return_value = BytesIO(
            (
                'event: step.delta\n'
                'data: {"event_type":"step.delta","delta":{"type":"text","text":"جزء من الإجابة"}}\n\n'
            ).encode()
        )
        status, result = self.post({"message": "مرحبا"})
        self.assertEqual(status, 200)
        self.assertIn("انقطع اتصال Gemini", result["error"])

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

    def test_persists_attached_image_for_history(self):
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
            {"mimeType": "image/png", "data": image},
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

    def test_registers_and_logs_in_with_persistent_session(self):
        status, result, headers = self.request(
            "POST",
            "/api/auth/register",
            {"email": "new@example.com", "password": "long-enough-pass", "remember": True},
            authorized=False,
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["user"]["email"], "new@example.com")
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

        status, duplicate, _ = self.request(
            "POST",
            "/api/auth/register",
            {"email": "NEW@example.com", "password": "another-long-pass"},
            authorized=False,
        )
        self.assertEqual(status, 409)
        self.assertIn("مسجل", duplicate["error"])

        status, login, login_headers = self.request(
            "POST",
            "/api/auth/login",
            {"email": "NEW@example.com", "password": "long-enough-pass"},
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
                "email": "new@example.com",
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

    def test_login_requests_account_creation_when_email_is_not_registered(self):
        status, result, _ = self.request(
            "POST",
            "/api/auth/login",
            {"email": "missing@example.com", "password": "incorrect-password"},
            authorized=False,
        )

        self.assertEqual(status, 404)
        self.assertIn("لم يتم العثور على حساب", result["error"])
        self.assertIn("أنشئ حسابًا جديدًا", result["error"])

    def test_changes_password_and_invalidates_other_sessions(self):
        other_token = server.database.create_session(self.user["id"])
        status, result = self.post(
            {
                "currentPassword": "wrong-current-password",
                "newPassword": "brand-new-password",
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
            },
            path="/api/auth/change-password",
        )
        self.assertEqual(status, 400)
        self.assertIn("10 أحرف", result["error"])

        status, result = self.post(
            {
                "currentPassword": "correct-horse-battery",
                "newPassword": "brand-new-password",
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
            headers = {"Accept": "text/html"}
            if visitor_cookie:
                headers["Cookie"] = visitor_cookie
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


class DatabaseContextTests(unittest.TestCase):
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

    def test_ordered_history_images_and_ownership_survive_database_reopen(self):
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
                    "حل السؤال في الصورة",
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
            self.assertEqual(
                images[first["message_id"]]["image_data"],
                b"persisted-image-bytes",
            )

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


if __name__ == "__main__":
    unittest.main()
