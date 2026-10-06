import argparse
import os
import sys
import traceback
from pathlib import Path

from curriculum import (
    CurriculumError,
    curriculum_embedding_batches,
    curriculum_visual_embedding_batches,
    embed_page_images,
    embed_texts,
    index_pdf,
    page_metadata_from_csv,
)

from database import Database
from server import get_database, load_local_env


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Extract and index a curriculum PDF into "
            "the PostgreSQL knowledge base."
        )
    )

    parser.add_argument(
        "--pdf",
        required=True,
        type=Path,
        help="PDF file to index",
    )

    parser.add_argument(
        "--grade",
        required=True,
        help="Canonical grade, e.g. الثاني عشر",
    )

    parser.add_argument(
        "--subject",
        required=True,
        help="Canonical subject, e.g. الفيزياء",
    )

    parser.add_argument(
        "--semester",
        default="",
        help="Semester metadata",
    )

    parser.add_argument(
        "--book-title",
        required=True,
        help="Official book title",
    )

    parser.add_argument(
        "--edition",
        default="",
        help="Book year or edition",
    )

    parser.add_argument(
        "--source",
        required=True,
        help="Publisher/source label",
    )

    parser.add_argument(
        "--source-url",
        default="",
        help="Official source URL, when available",
    )

    parser.add_argument(
        "--metadata-csv",
        type=Path,
        help="Optional page_number,unit,lesson CSV",
    )

    parser.add_argument(
        "--page-offset",
        type=int,
        default=0,
        help=(
            "Offset from PDF page index "
            "to printed book page number"
        ),
    )

    parser.add_argument(
        "--include-page-images",
        action="store_true",
        help=(
            "Render PDF pages as optional visual context "
            "for diagrams and tables"
        ),
    )

    source_kind = parser.add_mutually_exclusive_group(
        required=True
    )

    source_kind.add_argument(
        "--official",
        action="store_true",
        help="Use only for a verified Ministry of Education source",
    )

    source_kind.add_argument(
        "--supplemental",
        action="store_true",
        help="Mark this as a non-official supporting source",
    )

    return parser


def _make_batch_pages(batch):
    pages_by_id = {}

    for page, chunk, _ in batch:
        page_id = page["page_id"]

        if page_id not in pages_by_id:
            pages_by_id[page_id] = {
                "page_id": page["page_id"],
                "page_number": page["page_number"],
                "unit": page.get("unit", ""),
                "lesson": page.get("lesson", ""),
                "page_image_data": page.get(
                    "page_image_data"
                ),
                "page_image_mime": page.get(
                    "page_image_mime"
                ),
                "chunks": [],
            }

        pages_by_id[page_id]["chunks"].append(
            chunk
        )

    return list(pages_by_id.values())


def _make_visual_batch_pages(batch):
    pages_by_id = {}

    for item in batch:
        page = item["page"]
        chunk = item["chunk"]

        page_id = page["page_id"]

        if page_id not in pages_by_id:
            pages_by_id[page_id] = {
                "page_id": page["page_id"],
                "page_number": page["page_number"],
                "unit": page.get("unit", ""),
                "lesson": page.get("lesson", ""),
                "page_image_data": page.get(
                    "page_image_data"
                ),
                "page_image_mime": page.get(
                    "page_image_mime"
                ),
                "chunks": [],
            }

        pages_by_id[page_id]["chunks"].append(
            chunk
        )

    return list(pages_by_id.values())


def _print_progress(database, book_id, expected):
    progress = database.get_curriculum_progress(
        book_id
    )

    if not progress:
        return

    print(
        "التقدم: "
        f"{progress['completed_chunks']}/"
        f"{expected} chunks "
        f"({progress['status']})",
        flush=True,
    )


def _print_pdf_info(pdf_path):
    try:
        size_bytes = pdf_path.stat().st_size
    except OSError:
        return

    size_mb = size_bytes / (1024 * 1024)

    print(
        "=" * 60,
        flush=True,
    )

    print(
        f"PDF: {pdf_path.name}",
        flush=True,
    )

    print(
        f"حجم الملف: {size_mb:.2f} MB",
        flush=True,
    )

    print(
        "الحد الحالي المسموح به في curriculum.py: 200 MB",
        flush=True,
    )

    if size_bytes > 200 * 1024 * 1024:
        print(
            "تحذير: حجم هذا الملف أكبر من 200 MB.",
            flush=True,
        )

    print(
        "=" * 60,
        flush=True,
    )


def main(argv=None):
    arguments = build_parser().parse_args(argv)

    # ---------------------------------------------------------
    # التحقق من ملف PDF
    # ---------------------------------------------------------

    if (
        not arguments.pdf.is_file()
        or arguments.pdf.suffix.lower() != ".pdf"
    ):
        print(
            "The input must be an existing PDF file.",
            file=sys.stderr,
        )
        return 2

    # ---------------------------------------------------------
    # تحسين ترميز Windows
    # ---------------------------------------------------------

    try:
        sys.stdout.reconfigure(
            encoding="utf-8",
            errors="replace",
        )
        sys.stderr.reconfigure(
            encoding="utf-8",
            errors="replace",
        )
    except AttributeError:
        pass

    _print_pdf_info(arguments.pdf)

    load_local_env()

    api_key = os.environ.get(
        "GEMINI_API_KEY",
        "",
    ).strip()

    # ---------------------------------------------------------
    # ملاحظة:
    # المشروع الحالي يستخدم Local SentenceTransformer
    # للـ embeddings، لذلك وجود GEMINI_API_KEY قد يكون
    # مطلوبًا من بيئة المشروع، لكن لا ننشئ embeddings
    # داخل index_pdf.
    # ---------------------------------------------------------

    if not api_key:
        print(
            "تحذير: GEMINI_API_KEY غير موجود في .env.",
            file=sys.stderr,
        )

        print(
            "سيستمر البرنامج إذا كان نظام الـ embeddings المحلي "
            "لا يحتاج المفتاح.",
            file=sys.stderr,
        )

    try:
        database = get_database()

        # -----------------------------------------------------
        # التحقق من pgvector
        # -----------------------------------------------------

        if not database.curriculum_vector_enabled:
            print(
                "PostgreSQL pgvector is unavailable; "
                "enable the vector extension first.",
                file=sys.stderr,
            )
            return 2

        # -----------------------------------------------------
        # Metadata CSV
        # -----------------------------------------------------

        page_metadata = (
            page_metadata_from_csv(
                arguments.metadata_csv
            )
            if arguments.metadata_csv
            else {}
        )

        print(
            f"استخراج محتوى الكتاب: "
            f"{arguments.pdf.name}",
            flush=True,
        )

        # -----------------------------------------------------
        # استخراج PDF فقط
        #
        # مهم جدًا:
        # embed=False
        #
        # حتى لا يتم إنشاء كل embeddings دفعة واحدة.
        # -----------------------------------------------------

        book, pages = index_pdf(
            arguments.pdf,
            {
                "grade": arguments.grade,
                "subject": arguments.subject,
                "semester": arguments.semester,
                "book_title": arguments.book_title,
                "edition": arguments.edition,
                "source": arguments.source,
                "source_url": arguments.source_url,
                "is_official": arguments.official,
            },
            api_key,
            page_metadata=page_metadata,
            include_page_images=arguments.include_page_images,
            page_offset=arguments.page_offset,
            embed=False,
        )

        # -----------------------------------------------------
        # التأكد من وجود صفحات/chunks
        # -----------------------------------------------------

        if not pages:
            raise CurriculumError(
                "لم يُستخرج نص أو صفحات مصورة قابلة للفهرسة؛ "
                "جرّب --include-page-images لملف PDF ممسوح ضوئيًا."
            )

        expected_chunks = sum(
            len(page["chunks"])
            for page in pages
        )

        # -----------------------------------------------------
        # Book ID
        # -----------------------------------------------------

        print(
            "=" * 60,
            flush=True,
        )

        print(
            f"Book ID: {book['book_id']}",
            flush=True,
        )

        print(
            f"إجمالي الصفحات القابلة للفهرسة: "
            f"{len(pages)}",
            flush=True,
        )

        print(
            f"إجمالي chunks المتوقع: "
            f"{expected_chunks}",
            flush=True,
        )

        # -----------------------------------------------------
        # استرجاع الموجود من قاعدة البيانات
        #
        # هذا أهم جزء في الاستكمال.
        #
        # أي chunk موجود مسبقًا لن تتم معالجته مرة أخرى.
        # -----------------------------------------------------

        existing_ids = (
            database.get_existing_curriculum_chunk_ids(
                book["book_id"]
            )
        )

        print(
            f"الموجود مسبقًا في قاعدة البيانات: "
            f"{len(existing_ids)}",
            flush=True,
        )

        remaining_chunks = (
            expected_chunks - len(existing_ids)
        )

        if remaining_chunks < 0:
            remaining_chunks = 0

        print(
            f"المتبقي للفهرسة: "
            f"{remaining_chunks}",
            flush=True,
        )

        # -----------------------------------------------------
        # إنشاء/تحديث progress
        #
        # يتم بعد قراءة الموجود مسبقًا حتى لا نعرض progress
        # غير صحيح.
        # -----------------------------------------------------

        database.start_curriculum_progress(
            book,
            expected_chunks,
        )
        database.update_curriculum_progress(
            book_id=book["book_id"],
            expected_chunks=expected_chunks,
            completed_chunks=len(existing_ids),
            status=(
                "complete"
                if len(existing_ids) >= expected_chunks
                else "indexing"
            ),
        )

        _print_progress(
            database,
            book["book_id"],
            expected_chunks,
        )
        # -----------------------------------------------------
        # إذا كان الكتاب موجودًا بالكامل
        # -----------------------------------------------------

        if len(existing_ids) >= expected_chunks:
            database.complete_curriculum_indexing(
                book_id=book["book_id"],
                expected_chunks=expected_chunks,
                completed_chunks=expected_chunks,
            )

            print(
                "الكتاب موجود بالكامل في قاعدة البيانات. "
                "تخطي بدون إعادة معالجة.",
                flush=True,
            )

            return 0

        completed = len(existing_ids)

        # =====================================================
        # TEXT EMBEDDINGS
        # =====================================================

        text_batches = curriculum_embedding_batches(
            book,
            pages,
            existing_chunk_ids=existing_ids,
        )

        text_batch_count = 0

        for batch_number, batch in enumerate(
            text_batches,
            start=1,
        ):
            text_batch_count += 1

            print(
                f"\nText Batch #{batch_number}",
                flush=True,
            )

            print(
                f"عدد المقاطع في الـbatch: "
                f"{len(batch)}",
                flush=True,
            )

            print(
                "إنشاء embeddings محلية...",
                flush=True,
            )

            vectors = embed_texts(
                [item[2] for item in batch],
                api_key,
                task_type="RETRIEVAL_DOCUMENT",
            )

            if len(vectors) != len(batch):
                raise CurriculumError(
                    "عدد embeddings الناتجة لا يساوي "
                    "عدد المقاطع في الـbatch."
                )

            for item, vector in zip(
                batch,
                vectors,
            ):
                item[1]["embedding"] = vector

            batch_pages = _make_batch_pages(
                batch
            )

            inserted_ids = (
                database.index_curriculum_batch(
                    book,
                    batch_pages,
                )
            )

            completed += len(inserted_ids)

            existing_ids.update(
                inserted_ids
            )

            database.update_curriculum_progress(
                book_id=book["book_id"],
                expected_chunks=expected_chunks,
                completed_chunks=completed,
                status="indexing",
            )

            print(
                f"تم حفظ الـText batch ✅ "
                f"{completed}/{expected_chunks}",
                flush=True,
            )

        print(
            f"\nإجمالي Text Batches المعالجة: "
            f"{text_batch_count}",
            flush=True,
        )

        # =====================================================
        # VISUAL EMBEDDINGS
        # =====================================================

        visual_batches = (
            curriculum_visual_embedding_batches(
                book,
                pages,
                existing_chunk_ids=existing_ids,
            )
        )

        visual_batch_count = 0

        for batch_number, batch in enumerate(
            visual_batches,
            start=1,
        ):
            visual_batch_count += 1

            print(
                f"\nVisual Batch #{batch_number}",
                flush=True,
            )

            print(
                f"عدد الصفحات المصورة: "
                f"{len(batch)}",
                flush=True,
            )

            print(
                "إنشاء visual embeddings محلية...",
                flush=True,
            )

            vectors = embed_page_images(
                batch,
                api_key,
            )

            if len(vectors) != len(batch):
                raise CurriculumError(
                    "عدد visual embeddings الناتجة "
                    "لا يساوي عدد الصفحات في الـbatch."
                )

            for item, vector in zip(
                batch,
                vectors,
            ):
                item["chunk"]["embedding"] = vector

            batch_pages = (
                _make_visual_batch_pages(
                    batch
                )
            )

            inserted_ids = (
                database.index_curriculum_batch(
                    book,
                    batch_pages,
                )
            )

            completed += len(inserted_ids)

            existing_ids.update(
                inserted_ids
            )

            database.update_curriculum_progress(
                book_id=book["book_id"],
                expected_chunks=expected_chunks,
                completed_chunks=completed,
                status="indexing",
            )

            print(
                f"تم حفظ الـVisual batch ✅ "
                f"{completed}/{expected_chunks}",
                flush=True,
            )

        print(
            f"\nإجمالي Visual Batches المعالجة: "
            f"{visual_batch_count}",
            flush=True,
        )

        # =====================================================
        # FINAL VERIFICATION
        # =====================================================

        print(
            "\nالتحقق النهائي من قاعدة البيانات...",
            flush=True,
        )

        final_ids = (
            database.get_existing_curriculum_chunk_ids(
                book["book_id"]
            )
        )

        completed = len(final_ids)

        print(
            f"النتيجة النهائية: "
            f"{completed}/{expected_chunks} chunks",
            flush=True,
        )

        # -----------------------------------------------------
        # الكتاب غير مكتمل
        # -----------------------------------------------------

        if completed < expected_chunks:
            database.update_curriculum_progress(
                book_id=book["book_id"],
                expected_chunks=expected_chunks,
                completed_chunks=completed,
                status="indexing",
            )

            raise CurriculumError(
                "لم تكتمل فهرسة الكتاب. "
                f"تم حفظ {completed} من "
                f"{expected_chunks} chunks. "
                "شغّل الأمر مرة أخرى ليكمل من مكان التوقف."
            )

        # -----------------------------------------------------
        # الكتاب مكتمل
        # -----------------------------------------------------

        database.complete_curriculum_indexing(
            book_id=book["book_id"],
            expected_chunks=expected_chunks,
            completed_chunks=completed,
        )

        print()
        print(
            "=" * 60,
            flush=True,
        )

        print(
            "تمت فهرسة الكتاب بالكامل ✅",
            flush=True,
        )

        print(
            f"العنوان: {book['book_title']}",
            flush=True,
        )

        print(
            f"Book ID: {book['book_id']}",
            flush=True,
        )

        print(
            f"تم حفظ: "
            f"{completed}/{expected_chunks} chunks",
            flush=True,
        )

        print(
            "=" * 60,
            flush=True,
        )

        return 0

    # =========================================================
    # Database errors
    # =========================================================

    except Database.error_types as error:
        print(
            "=" * 60,
            file=sys.stderr,
        )

        print(
            "Curriculum database operation failed:",
            file=sys.stderr,
        )

        print(
            f"{type(error).__name__}: {error}",
            file=sys.stderr,
        )

        print(
            "=" * 60,
            file=sys.stderr,
        )

        traceback.print_exc()

        return 1

    # =========================================================
    # Curriculum / file / runtime errors
    # =========================================================

    except (
        CurriculumError,
        OSError,
        RuntimeError,
        ValueError,
    ) as error:
        print(
            "=" * 60,
            file=sys.stderr,
        )

        print(
            "Curriculum indexing failed:",
            file=sys.stderr,
        )

        print(
            f"{type(error).__name__}: {error}",
            file=sys.stderr,
        )

        print(
            "=" * 60,
            file=sys.stderr,
        )

        traceback.print_exc()

        return 1

    # =========================================================
    # أي خطأ غير متوقع
    # =========================================================

    except Exception as error:
        print(
            "=" * 60,
            file=sys.stderr,
        )

        print(
            "Unexpected curriculum indexing error:",
            file=sys.stderr,
        )

        print(
            f"{type(error).__name__}: {error}",
            file=sys.stderr,
        )

        print(
            "=" * 60,
            file=sys.stderr,
        )

        traceback.print_exc()

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )

