import tempfile
import unittest
import json
from base64 import b64decode
from io import BytesIO
from pathlib import Path
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from pypdf import PdfWriter

import curriculum


class FakeCurriculumDatabase:
    curriculum_vector_enabled = True

    def __init__(self, official_results=None, supplemental_results=None):
        self.official_results = official_results or []
        self.supplemental_results = supplemental_results or []
        self.search_calls = []

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
        self.search_calls.append(
            {
                "grade": grade,
                "subject": subject,
                "semester": semester,
                "unit": unit,
                "lesson": lesson,
                "official_only": official_only,
                "limit": limit,
            }
        )
        return self.official_results if official_only else self.supplemental_results


def curriculum_result(**overrides):
    result = {
        "chunk_id": "chunk-1",
        "content": "ينص قانون نيوتن الثاني على أن القوة تساوي الكتلة مضروبة بالتسارع.",
        "similarity": 0.82,
        "book_id": "book-physics-12",
        "grade": "الثاني عشر",
        "subject": "الفيزياء",
        "semester": "الفصل الأول",
        "book_title": "كتاب الفيزياء",
        "edition": "2025",
        "source": "وزارة التربية والتعليم الأردنية",
        "source_url": "https://moe.gov.jo/example.pdf",
        "is_official": True,
        "page_id": "page-47",
        "page_number": 47,
        "unit": "الوحدة الثانية",
        "lesson": "الدرس الثالث",
        "page_image_data": b"page-image",
        "page_image_mime": "image/jpeg",
    }
    result.update(overrides)
    return result


class CurriculumRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.embedding_patch = patch(
            "curriculum.embed_texts", return_value=[[0.1] * 768]
        )
        self.mock_embeddings = self.embedding_patch.start()
        self.addCleanup(self.embedding_patch.stop)

    def test_retrieves_official_content_with_exact_metadata_and_page_image(self):
        database = FakeCurriculumDatabase([curriculum_result()])
        result = curriculum.retrieve_curriculum(
            database,
            "اشرح قانون نيوتن الثاني في الفيزياء الفصل الأول، الوحدة الثانية، الدرس الثالث",
            "الثاني عشر",
            "test-key",
        )

        self.assertTrue(result["official"])
        self.assertIn("صفحة 47", result["answer_suffix"])
        self.assertIn("الوحدة الثانية", result["answer_suffix"])
        self.assertIn("كتاب الفيزياء", result["answer_suffix"])
        self.assertIn("وزارة التربية والتعليم الأردنية", result["answer_suffix"])
        self.assertEqual(database.search_calls[0]["grade"], "الثاني عشر")
        self.assertEqual(database.search_calls[0]["subject"], "الفيزياء")
        self.assertEqual(database.search_calls[0]["semester"], "الفصل الأول")
        self.assertEqual(database.search_calls[0]["unit"], "الوحدة الثانية")
        self.assertEqual(database.search_calls[0]["lesson"], "الدرس الثالث")
        self.assertTrue(database.search_calls[0]["official_only"])
        self.assertEqual(len(database.search_calls), 1)
        images = [part for part in result["extra_parts"] if part["type"] == "image"]
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0]["mime_type"], "image/jpeg")

    def test_uses_explicit_recent_conversation_subject_and_semester(self):
        database = FakeCurriculumDatabase([curriculum_result()])
        result = curriculum.retrieve_curriculum(
            database,
            "احسبها",
            "الثاني عشر",
            "test-key",
            conversation_history=[
                {
                    "role": "user",
                    "content": "أنا أدرس الفيزياء في الفصل الثاني، الوحدة الثانية، الدرس الثالث",
                },
                {"role": "assistant", "content": "تمام"},
            ],
        )
        self.assertTrue(result["official"])
        self.assertEqual(database.search_calls[0]["subject"], "الفيزياء")
        self.assertEqual(database.search_calls[0]["semester"], "الفصل الثاني")
        self.assertEqual(database.search_calls[0]["unit"], "الوحدة الثانية")
        self.assertEqual(database.search_calls[0]["lesson"], "الدرس الثالث")
        query_text = self.mock_embeddings.call_args.args[0][0]
        self.assertIn("أنا أدرس الفيزياء في الفصل الثاني", query_text)
        self.assertIn("سؤال الطالب الحالي", query_text)

    def test_fails_closed_on_ambiguous_subject_or_grade(self):
        database = FakeCurriculumDatabase(
            [
                curriculum_result(grade="العاشر", similarity=0.83),
                curriculum_result(
                    chunk_id="chunk-2", grade="الحادي عشر", similarity=0.81
                ),
            ]
        )
        result = curriculum.retrieve_curriculum(
            database, "اشرح قانون نيوتن الثاني", None, "test-key"
        )
        self.assertTrue(result.get("ambiguous"))
        self.assertFalse(result["sources"])
        self.assertIn("اسأل الطالب عن صفه", result["system_note"])

        ambiguous_subject = curriculum.retrieve_curriculum(
            FakeCurriculumDatabase(),
            "اشرح قانون نيوتن والرياضيات في السؤال نفسه",
            "الثاني عشر",
            "test-key",
        )
        self.assertTrue(ambiguous_subject.get("ambiguous"))
        self.assertIn("تحديد المادة", ambiguous_subject["system_note"])

    def test_does_not_assume_retrieved_grade_is_the_students_grade(self):
        result = curriculum.retrieve_curriculum(
            FakeCurriculumDatabase([curriculum_result()]),
            "اشرح قانون نيوتن الثاني",
            None,
            "test-key",
        )
        self.assertTrue(result["official"])
        self.assertIn("لم يُؤكد صف الطالب", result["system_note"])
        self.assertIn("الثاني عشر", result["system_note"])

    def test_missing_content_uses_unattributed_general_fallback(self):
        database = FakeCurriculumDatabase()
        result = curriculum.retrieve_curriculum(
            database, "اشرح قانون نيوتن الثاني", "الثاني عشر", "test-key"
        )
        self.assertTrue(result["searched"])
        self.assertFalse(result.get("official", False))
        self.assertFalse(result["sources"])
        self.assertIn("ليست منسوبة إلى كتاب الوزارة", result["answer_suffix"])
        self.assertEqual(
            [call["official_only"] for call in database.search_calls],
            [True, False],
        )

    def test_postgres_vector_query_filters_grade_subject_semester_and_source(self):
        class Cursor:
            def fetchall(self):
                return []

        class Connection:
            statement = ""
            parameters = ()

            def execute(self, statement, parameters=()):
                self.statement = statement
                self.parameters = parameters
                return Cursor()

        raw_connection = Connection()
        from database import Database, PostgresConnection

        @contextmanager
        def connect():
            yield PostgresConnection(raw_connection)

        database = SimpleNamespace(curriculum_vector_enabled=True, connect=connect)
        results = Database.search_curriculum(
            database,
            [0.0] * 768,
            grade="الثاني عشر",
            subject="الفيزياء",
            semester="الفصل الأول",
            official_only=True,
        )
        self.assertEqual(results, [])
        self.assertIn("books.grade = %s", raw_connection.statement)
        self.assertIn("books.subject = %s", raw_connection.statement)
        self.assertIn("books.semester = %s", raw_connection.statement)
        self.assertEqual(
            raw_connection.parameters[1:5],
            [True, "الثاني عشر", "الفيزياء", "الفصل الأول"],
        )

    def test_never_fabricates_source_for_a_non_educational_question(self):
        database = FakeCurriculumDatabase()
        result = curriculum.retrieve_curriculum(
            database, "كيف الطقس اليوم؟", None, "test-key"
        )
        self.assertFalse(result["searched"])
        self.assertFalse(result["sources"])
        self.assertFalse(database.search_calls)
        self.mock_embeddings.assert_not_called()

    def test_image_embeddings_are_multimodal_and_batched_in_small_requests(self):
        response = lambda count: BytesIO(
            json.dumps(
                {"embeddings": [{"values": [0.25] * 768} for _ in range(count)]}
            ).encode()
        )
        with patch(
            "curriculum.urlopen",
            side_effect=[response(4), response(1)],
        ) as urlopen_mock:
            vectors = curriculum.embed_page_images(
                [
                    {
                        "embedding_text": f"عنوان صفحة منهج {index}",
                        "image_data": b"page-image",
                        "image_mime": "image/jpeg",
                    }
                    for index in range(5)
                ],
                "test-key",
            )
        self.assertEqual(len(vectors), 5)
        self.assertEqual(urlopen_mock.call_count, 2)
        first_request = json.loads(urlopen_mock.call_args_list[0].args[0].data)
        image_part = first_request["requests"][0]["content"]["parts"][1]
        self.assertEqual(image_part["inlineData"]["mimeType"], "image/jpeg")
        self.assertEqual(b64decode(image_part["inlineData"]["data"]), b"page-image")
        self.assertNotIn("taskType", first_request["requests"][0])

    def test_embedding_query_uses_gemini_embedding_two_retrieval_format(self):
        response = BytesIO(
            json.dumps({"embeddings": [{"values": [0.25] * 768}]}).encode()
        )
        embedding_request = curriculum._embedding_request(
            "اشرح قانون نيوتن الثاني", "RETRIEVAL_QUERY"
        )
        with patch("curriculum.urlopen", return_value=response) as urlopen_mock:
            vectors = curriculum._embed_requests([embedding_request], "test-key")
        self.assertEqual(len(vectors), 1)
        self.assertEqual(len(vectors[0]), 768)
        request = json.loads(urlopen_mock.call_args.args[0].data)["requests"][0]
        self.assertEqual(request["model"], "models/gemini-embedding-2")
        self.assertIn(
            "task: search result | query:",
            request["content"]["parts"][0]["text"],
        )
        self.assertEqual(
            request["embedContentConfig"]["outputDimensionality"], 768
        )
        self.assertNotIn("taskType", request)

    def test_pdf_import_records_grade_book_page_and_optional_page_image(self):
        with tempfile.TemporaryDirectory() as folder:
            pdf_path = Path(folder) / "curriculum.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=612, height=792)
            with pdf_path.open("wb") as stream:
                writer.write(stream)

            with patch("curriculum.embed_page_images", return_value=[[0.2] * 768]) as visual_embed:
                book, pages = curriculum.index_pdf(
                    pdf_path,
                    {
                        "grade": "الصف الثاني عشر",
                        "subject": "الفيزياء",
                        "semester": "الفصل الأول",
                        "book_title": "كتاب الفيزياء",
                        "edition": "2025",
                        "source": "وزارة التربية والتعليم الأردنية",
                        "is_official": True,
                    },
                    "test-key",
                    page_metadata={1: {"unit": "الوحدة الثانية", "lesson": "الدرس الثالث"}},
                    include_page_images=True,
                    page_offset=46,
                )

        self.assertEqual(book["grade"], "الثاني عشر")
        self.assertEqual(pages[0]["page_number"], 47)
        self.assertEqual(pages[0]["unit"], "الوحدة الثانية")
        self.assertEqual(pages[0]["lesson"], "الدرس الثالث")
        self.assertTrue(pages[0]["page_image_data"].startswith(b"\xff\xd8"))
        self.assertEqual(len(pages[0]["chunks"]), 1)
        self.assertIn("صورة صفحة", pages[0]["chunks"][0]["content"])
        self.assertEqual(len(pages[0]["chunks"][0]["embedding"]), 768)
        visual_embed.assert_called_once()


if __name__ == "__main__":
    unittest.main()
