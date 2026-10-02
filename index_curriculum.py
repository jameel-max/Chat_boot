import argparse
import os
import sys
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


def main(argv=None):
    arguments = build_parser().parse_args(argv)

    if (
        not arguments.pdf.is_file()
        or arguments.pdf.suffix.lower() != ".pdf"
    ):
        print(
            "The input must be an existing PDF file.",
            file=sys.stderr,
        )
        return 2

    load_local_env()

    api_key = os.environ.get(
        "GEMINI_API_KEY",
        "",
    ).strip()

    if not api_key:
        print(
            "Set GEMINI_API_KEY in .env before indexing curriculum PDFs.",
            file=sys.stderr,
        )
        return 2

    try:
        database = get_database()

        if not database.curriculum_vector_enabled:
            print(
                "PostgreSQL pgvector is unavailable; "
                "enable the vector extension first.",
                file=sys.stderr,
            )
            return 2

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

        # مهم:
        # لا ننشئ embeddings هنا.
        # نستخرج الكتاب فقط ثم نعالج embeddings
        # على batches محفوظة في PostgreSQL.
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

        if not pages:
            raise CurriculumError(
                "لم يُستخرج نص أو صفحات مصورة قابلة للفهرسة؛ "
                "جرّب --include-page-images لملف PDF ممسوح ضوئيًا."
            )

        expected_chunks = sum(
            len(page["chunks"])
            for page in pages
        )

        database.start_curriculum_progress(
            book,
            expected_chunks,
        )

        existing_ids = (
            database.get_existing_curriculum_chunk_ids(
                book["book_id"]
            )
        )

        print(
            "=" * 60,
            flush=True,
        )

        print(
            f"Book ID: {book['book_id']}",
            flush=True,
        )

        print(
            f"إجمالي chunks: {expected_chunks}",
            flush=True,
        )

        print(
            f"الموجود مسبقًا: {len(existing_ids)}",
            flush=True,
        )

        if len(existing_ids) >= expected_chunks:
            database.complete_curriculum_indexing(
                book_id=book["book_id"],
                expected_chunks=expected_chunks,
                completed_chunks=expected_chunks,
            )

            print(
                "الكتاب موجود بالكامل في قاعدة البيانات. تخطي.",
                flush=True,
            )

            return 0

        completed = len(existing_ids)

        # ---------------------------------------------------------
        # النصوص
        # ---------------------------------------------------------

        text_batches = curriculum_embedding_batches(
            book,
            pages,
            existing_chunk_ids=existing_ids,
        )

        for batch_number, batch in enumerate(
            text_batches,
            start=1,
        ):
            print(
                f"\nText Batch #{batch_number}",
                flush=True,
            )

            print(
                f"عدد المقاطع: {len(batch)}",
                flush=True,
            )

            vectors = embed_texts(
                [item[2] for item in batch],
                api_key,
                task_type="RETRIEVAL_DOCUMENT",
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
                f"تم حفظ الـbatch ✅ "
                f"{completed}/{expected_chunks}",
                flush=True,
            )

        # ---------------------------------------------------------
        # الصور
        # ---------------------------------------------------------

        visual_batches = (
            curriculum_visual_embedding_batches(
                book,
                pages,
                existing_chunk_ids=existing_ids,
            )
        )

        for batch_number, batch in enumerate(
            visual_batches,
            start=1,
        ):
            print(
                f"\nVisual Batch #{batch_number}",
                flush=True,
            )

            print(
                f"عدد الصفحات المصورة: {len(batch)}",
                flush=True,
            )

            vectors = embed_page_images(
                batch,
                api_key,
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
                f"تم حفظ الـvisual batch ✅ "
                f"{completed}/{expected_chunks}",
                flush=True,
            )

        # ---------------------------------------------------------
        # التحقق النهائي
        # ---------------------------------------------------------

        final_ids = (
            database.get_existing_curriculum_chunk_ids(
                book["book_id"]
            )
        )

        completed = len(final_ids)

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

        database.complete_curriculum_indexing(
            book_id=book["book_id"],
            expected_chunks=expected_chunks,
            completed_chunks=completed,
        )

        print()
        print("=" * 60)
        print(
            f"تمت فهرسة الكتاب بالكامل ✅"
        )
        print(
            f"{book['book_title']}"
        )
        print(
            f"{completed}/{expected_chunks} chunks"
        )
        print("=" * 60)

        return 0

    except Database.error_types as error:
        print(
            "Curriculum database operation failed: "
            f"{type(error).__name__}.",
            file=sys.stderr,
        )
        return 1

    except (
        CurriculumError,
        OSError,
        RuntimeError,
        ValueError,
    ) as error:
        print(
            f"Curriculum indexing failed: {error}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )