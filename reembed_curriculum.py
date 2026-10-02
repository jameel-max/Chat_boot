import os
from dotenv import load_dotenv

load_dotenv()

from database import Database
from curriculum import embed_texts


BATCH_SIZE = 32


def main():
    database_url = os.getenv("DATABASE_URL", "").strip()

    if not database_url:
        raise RuntimeError("DATABASE_URL غير موجود.")

    db = Database(database_url)

    # قراءة كل الـ chunks الموجودة فقط
    with db.connect() as connection:
        rows = connection.execute(
            """
            SELECT chunk_id, content
            FROM curriculum_chunks
            ORDER BY chunk_id
            """
        ).fetchall()

    total = len(rows)

    print(f"إجمالي chunks لإعادة الفهرسة: {total}", flush=True)

    if total == 0:
        print("لا توجد chunks.", flush=True)
        return

    processed = 0

    for start in range(0, total, BATCH_SIZE):
        batch = rows[start:start + BATCH_SIZE]

        chunk_ids = [row['chunk_id'] for row in batch]
        texts = [row['content'] for row in batch]

        print(
            f"\nEmbedding: {start + 1}-{start + len(batch)} / {total}",
            flush=True,
        )

        vectors = embed_texts(texts)

        if len(vectors) != len(batch):
            raise RuntimeError(
                "عدد الـ embeddings لا يطابق عدد الـ chunks."
            )

        with db.connect() as connection:
            for chunk_id, vector in zip(chunk_ids, vectors):
                vector_text = "[" + ",".join(
                    str(float(value)) for value in vector
                ) + "]"

                connection.execute(
                    """
                    UPDATE curriculum_chunks
                    SET embedding = ?
                    WHERE chunk_id = ?
                    """,
                    (vector_text, chunk_id),
                )

        processed += len(batch)

        print(
            f"تم تحديث: {processed}/{total}",
            flush=True,
        )

    print("\nاكتملت إعادة الـ embeddings بنجاح.", flush=True)


if __name__ == "__main__":
    main()
