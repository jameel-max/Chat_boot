import base64
import hashlib
import io
import json
import math
import re
import requests
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


EMBEDDING_MODEL = "gemini-embedding-2"
EMBEDDING_DIMENSIONS = 768

EMBEDDING_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{EMBEDDING_MODEL}:batchEmbedContents"
)

EMBEDDING_BATCH_SIZE = 32
EMBEDDING_IMAGE_BATCH_SIZE = 4

EMBEDDING_MAX_RETRIES = 6
EMBEDDING_TIMEOUT = 60
EMBEDDING_INITIAL_RETRY_DELAY = 5
EMBEDDING_MAX_RETRY_DELAY = 120

MAX_CURRICULUM_PDF_BYTES = 50 * 1024 * 1024
MAX_CHUNK_CHARACTERS = 1_800
CHUNK_OVERLAP_CHARACTERS = 180
MAX_RETRIEVED_CHUNKS = 5
MAX_RETRIEVED_CONTEXT_CHARACTERS = 12_000
MAX_RETRIEVED_PAGE_IMAGES = 2
MAX_RETRIEVED_IMAGE_BYTES = 1 * 1024 * 1024
MIN_COSINE_SIMILARITY = 0.30
MAX_RETRIEVAL_QUERY_CHARACTERS = 3_000

UNIT_PATTERN = re.compile(
    r"(الوحدة\s+(?:الأولى|الاولى|الثانية|الثاني|الثالثة|الثالث|الرابعة|الرابع|"
    r"الخامسة|الخامس|السادسة|السادس|السابعة|السابع|الثامنة|الثامن|"
    r"التاسعة|التاسع|العاشرة|العاشر|[0-9٠-٩]+))"
)

LESSON_PATTERN = re.compile(
    r"(الدرس\s+(?:الأول|الاول|الثاني|الثالث|الرابع|الخامس|السادس|"
    r"السابع|الثامن|التاسع|العاشر|[0-9٠-٩]+))"
)


class CurriculumError(RuntimeError):
    pass


SUBJECT_ALIASES = {
    "الرياضيات": ("الرياضيات", "رياضيات", "الجبر", "الهندسة", "التفاضل"),
    "الفيزياء": ("الفيزياء", "فيزياء", "نيوتن", "التسارع", "السرعة"),
    "الكيمياء": ("الكيمياء", "كيمياء", "التفاعل الكيميائي", "الذرة", "المول"),
    "الأحياء": ("الأحياء", "احياء", "الخلية", "الوراثة", "التنفس الخلوي"),
    "علوم الأرض": ("علوم الأرض", "علوم الارض", "الجيولوجيا", "الصخور"),
    "اللغة العربية": ("اللغة العربية", "العربي", "النحو", "البلاغة", "الصرف"),
    "اللغة الإنجليزية": (
        "اللغة الإنجليزية",
        "اللغة الانجليزية",
        "الإنجليزي",
        "الانجليزي",
    ),
    "التاريخ": ("التاريخ", "تاريخ الأردن", "تاريخ الاردن"),
    "الجغرافيا": ("الجغرافيا", "جغرافيا", "المناخ", "التضاريس"),
    "التربية الإسلامية": (
        "التربية الإسلامية",
        "التربية الاسلامية",
        "فقه",
        "حديث",
        "تفسير",
    ),
    "الحاسوب": ("الحاسوب", "الحاسوب", "البرمجة", "الخوارزمية"),
    "العلوم": ("العلوم", "علوم", "علوم الحياة"),
}


EDUCATION_MARKERS = (
    "اشرح",
    "فسر",
    "علل",
    "احسب",
    "اوجد",
    "حل السؤال",
    "حل المسألة",
    "عرف",
    "ما المقصود",
    "ما هو",
    "ما هي",
    "شو هو",
    "شو هي",
    "قانون",
    "معادلة",
    "تمرين",
    "واجب",
    "سؤال",
    "صفحة",
    "درس",
    "وحدة",
    "منهج",
    "كتاب الوزارة",
    "الوزارة",
    "الامتحان",
    "العلامة",
    "المادة",
    "الفصل",
    "المثلث",
    "الكسر",
    "المعادلات",
    "الخلية",
    "الطاقة",
)


def normalize_arabic(text):
    text = text.casefold().translate(str.maketrans("أإآ", "ااا"))
    return re.sub(r"[\u064b-\u065f\u0670ـ]", "", text)


def normalize_grade(grade):
    if not grade:
        return None
    value = " ".join(normalize_arabic(grade).split())
    value = re.sub(r"^(?:ال)?صف\s+", "", value)
    return value or None


def normalize_semester(semester):
    if not semester:
        return None

    value = " ".join(normalize_arabic(semester).split())

    if value in {"الفصل الاول", "الاول"}:
        return "الفصل الأول"

    if value in {"الفصل الثاني", "الثاني"}:
        return "الفصل الثاني"

    return semester.strip()


def infer_subjects(question):
    normalized = normalize_arabic(question)
    matches = []

    for subject, aliases in SUBJECT_ALIASES.items():
        if any(normalize_arabic(alias) in normalized for alias in aliases):
            matches.append(subject)

    return matches


def infer_semester(question):
    normalized = normalize_arabic(question)

    if re.search(r"الفصل\s+(?:ال)?اول", normalized):
        return "الفصل الأول"

    if re.search(r"الفصل\s+(?:ال)?ثاني", normalized):
        return "الفصل الثاني"

    return None


def infer_unit(question):
    match = UNIT_PATTERN.search(question)
    return match.group(1) if match else None


def infer_lesson(question):
    match = LESSON_PATTERN.search(question)
    return match.group(1) if match else None


def is_educational_question(question):
    normalized = normalize_arabic(question)

    return bool(infer_subjects(question)) or any(
        marker in normalized for marker in EDUCATION_MARKERS
    )


def chunk_text(
    text,
    maximum=MAX_CHUNK_CHARACTERS,
    overlap=CHUNK_OVERLAP_CHARACTERS,
):
    normalized = " ".join(text.split())

    if not normalized:
        return []

    chunks = []
    start = 0

    while start < len(normalized):
        end = min(start + maximum, len(normalized))

        if end < len(normalized):
            boundary = normalized.rfind(
                " ",
                start + maximum // 2,
                end,
            )

            if boundary > start:
                end = boundary

        chunk = normalized[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= len(normalized):
            break

        start = max(start + 1, end - overlap)

    return chunks


# ============================================================
# Local Embeddings - Sentence Transformers

from sentence_transformers import SentenceTransformer

LOCAL_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
EMBEDDING_DIMENSIONS = 768
LOCAL_EMBEDDING_BATCH_SIZE = 8

_local_embedding_model = None


def _get_local_embedding_model():
    global _local_embedding_model

    if _local_embedding_model is None:
        print(
            f"Loading local embedding model: {LOCAL_EMBEDDING_MODEL}",
            flush=True,
        )

        _local_embedding_model = SentenceTransformer(
            LOCAL_EMBEDDING_MODEL,
            device="cpu",
        )

        dimension = (
            _local_embedding_model.get_sentence_embedding_dimension()
        )

        if dimension != EMBEDDING_DIMENSIONS:
            raise CurriculumError(
                "Local embedding model returned an unexpected "
                f"dimension: {dimension}. "
                f"Expected: {EMBEDDING_DIMENSIONS}."
            )

        print(
            f"Local embedding model ready "
            f"(dimension={dimension}).",
            flush=True,
        )

    return _local_embedding_model


def embed_texts(
    texts,
    api_key=None,
    task_type="RETRIEVAL_DOCUMENT",
):
    if not texts:
        return []

    if not isinstance(texts, (list, tuple)):
        raise CurriculumError(
            "texts must be a list or tuple."
        )

    cleaned_texts = []

    for text in texts:
        if text is None:
            cleaned_texts.append("")
        else:
            cleaned_texts.append(str(text))

    model = _get_local_embedding_model()

    print(
        f"Generating local embeddings: "
        f"{len(cleaned_texts)} texts",
        flush=True,
    )

    try:
        vectors = model.encode(
            cleaned_texts,
            batch_size=LOCAL_EMBEDDING_BATCH_SIZE,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
    except Exception as error:
        raise CurriculumError(
            f"Local embedding generation failed: {error}"
        ) from error

    if len(vectors) != len(cleaned_texts):
        raise CurriculumError(
            "Local embedding count does not match "
            "the number of input texts."
        )

    embeddings = []

    for vector in vectors:
        values = vector.tolist()

        if len(values) != EMBEDDING_DIMENSIONS:
            raise CurriculumError(
                "Local embedding has an unexpected dimension: "
                f"{len(values)}."
            )

        if not all(
            math.isfinite(float(value))
            for value in values
        ):
            raise CurriculumError(
                "Local embedding contains invalid values."
            )

        embeddings.append(
            [float(value) for value in values]
        )

    return embeddings


def embed_page_images(
    pages,
    api_key=None,
):
    if not pages:
        return []

    texts = []

    for page in pages:
        text = page.get("embedding_text", "")

        if text is None:
            text = ""

        texts.append(str(text))

    return embed_texts(
        texts,
        api_key,
        task_type="RETRIEVAL_DOCUMENT",
    )
