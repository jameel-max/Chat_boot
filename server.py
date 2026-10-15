import base64
import binascii
import gzip
import http.client
import io
import json
import math
import os
import re
import secrets
import smtplib
import ssl
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import parseaddr
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from http.cookies import CookieError, SimpleCookie
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen

from database import Database


ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "public"
DEFAULT_ADMIN_EMAIL = "mstfyaysht384@gmail.com"
API_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
MAX_REQUEST_BYTES = 12 * 1024 * 1024
VISITOR_COOKIE_NAME = "faheem_visitor"
VISITOR_COOKIE_MAX_AGE = 365 * 24 * 60 * 60
VISIT_DEDUP_SECONDS = 30
MAX_GEMINI_REQUEST_BYTES = 19 * 1024 * 1024
MAX_GEMINI_CONTEXT_TOKENS = 900_000
MAX_HISTORY_MESSAGES = 16  # عدد آخر الرسائل (سؤال وجواب) المرسلة كسياق إلى Gemini

# ===== حصة المرفقات اليومية (صور وملفات) =====
DAILY_UPLOAD_LIMIT = 4        # عدد الصور/الملفات المسموح بها لكل طالب يوميًا
UPLOAD_QUOTA_PATH = Path(__file__).resolve().parent / "data" / "upload_quota.json"
JORDAN_TZ = timezone(timedelta(hours=3))  # توقيت الأردن (UTC+3) لتصفير العداد عند منتصف الليل
USER_PREFERENCES_PATH = Path(__file__).resolve().parent / "data" / "user_preferences.json"
ALLOWED_THEMES = {"light", "dark"}

# ===== حسابات الطلاب: الاسم الرباعي + الصف + كلمة المرور =====
USER_PROFILES_PATH = Path(__file__).resolve().parent / "data" / "user_profiles.json"
# الحساب يُخزَّن في قاعدة البيانات ببريد داخلي مشتق من الاسم الرباعي (لا يُعرض للطالب)
STUDENT_EMAIL_DOMAIN = "students.faheem.local"
# مفتاح الصف كما يختاره الطالب -> الاسم المعروض + القيمة التي يفهمها فهيم (GRADE_NAMES)
GRADE_CHOICES = {
    "8": {"label": "الثامن", "stored": "الثامن"},
    "9": {"label": "التاسع", "stored": "التاسع"},
    "10": {"label": "العاشر", "stored": "العاشر"},
    "11": {"label": "الأول الثانوي", "stored": "الحادي عشر"},
    "12": {"label": "الثاني الثانوي", "stored": "الثاني عشر"},
}
GRADE_ORDER = ["8", "9", "10", "11", "12"]
STORED_TO_GRADE_KEY = {value["stored"]: key for key, value in GRADE_CHOICES.items()}
# كلمات تُدمج مع التي بعدها لتُحسب اسمًا واحدًا: عبد الله، أبو حماد، بن علي ...
NAME_PREFIXES = {"عبد", "ابو", "ابن", "بن", "ام", "ال", "بنت"}
PASSWORD_MIN_LENGTH = 10
MAX_CONTEXT_IMAGES = 32
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_DOCUMENT_BYTES = 8 * 1024 * 1024
MAX_TITLE_LENGTH = 80
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
ALLOWED_DOCUMENT_TYPES = {
    "application/pdf",
    "application/json",
    "text/plain",
    "text/markdown",
    "text/csv",
    "text/html",
    "text/xml",
    "application/xml",
}
ALLOWED_DOCUMENT_EXTENSIONS = {
    ".pdf", ".txt", ".md", ".csv", ".json", ".html", ".xml"
}
database = None
_database_lock = threading.Lock()


SYSTEM_INSTRUCTION = " ".join(
    (
        "أنت فهيم، مساعد ذكي لطلاب مدرسة خريبة السوق الثانوية الثانية للبنين.",
        "اترك سطرًا فارغًا بين الفقرات، واستخدم عناوين Markdown قصيرة عند الحاجة.",
        "استخدم الجداول فقط عندما تكون مفيدة فعلًا.",
        "تجنب التكرار والمقدمات الطويلة، ونفّذ طلب الطالب مباشرة دون أسئلة غير ضرورية.",
    )
)

GRADE_NAMES = {
    "الأول": "الأول",
    "اول": "الأول",
    "الثاني": "الثاني",
    "ثاني": "الثاني",
    "الثالث": "الثالث",
    "ثالث": "الثالث",
    "الرابع": "الرابع",
    "رابع": "الرابع",
    "الخامس": "الخامس",
    "خامس": "الخامس",
    "السادس": "السادس",
    "سادس": "السادس",
    "السابع": "السابع",
    "سابع": "السابع",
    "الثامن": "الثامن",
    "ثامن": "الثامن",
    "التاسع": "التاسع",
    "تاسع": "التاسع",
    "العاشر": "العاشر",
    "عاشر": "العاشر",
    "الحادي عشر": "الحادي عشر",
    "حادي عشر": "الحادي عشر",
    "الثاني عشر": "الثاني عشر",
    "ثاني عشر": "الثاني عشر",
}


def extract_student_grade(message, allow_short_answer=False):
    normalized = message.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    normalized = re.sub(r"[\u064b-\u065f\u0670ـ]", "", normalized).casefold()
    grade_pattern = "|".join(
        sorted(
            (re.escape(name) for name in GRADE_NAMES),
            key=len,
            reverse=True,
        )
    )
    match = re.search(
        rf"(?:صف(?:ي)?|الصف|بالصف|بالصف الدراسي)\s*"
        rf"(?:رقم\s*)?(?:(?:ال)?({grade_pattern})|([1-9]|1[0-2]))"
        rf"(?!\d)",
        normalized,
    )
    if not match and allow_short_answer:
        match = re.fullmatch(
            rf"(?:(?:انا|اني)\s+)?(?:الصف\s+)?"
            rf"(?:(?:ال)?({grade_pattern})|([1-9]|1[0-2]))"
            rf"[.!؟،\s]*",
            normalized,
        )
    if not match:
        return None
    if match.group(1):
        return GRADE_NAMES[match.group(1)]
    return f"الصف {match.group(2)}"


def user_starts_with_greeting(message):
    normalized = re.sub(r"[\u064b-\u065f\u0670ـ]", "", message.strip()).casefold()
    return re.match(
        r"^(?:السلام عليكم|سلام|مرحبا|مرحباً|أهلا|اهلا|أهلًا|هلا|"
        r"صباح الخير|مساء الخير|هاي|hello|hi)(?=$|[\s،,:.!؟!?-])",
        normalized,
    ) is not None


def user_asks_own_grade(message):
    normalized = message.casefold().translate(str.maketrans("أإآ", "ااا"))
    normalized = re.sub(r"[\u064b-\u065f\u0670ـ]", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return re.search(
        r"(?:كم|شو|ايش|وش|ما)\s+(?:هو\s+)?صفي\b|"
        r"(?:انا|اني)\s+(?:(?:في|ب)\s*)?(?:اي|كم)\s+(?:ال)?صف\b|"
        r"(?:باي|في\s+اي)\s+(?:ال)?صف\s+(?:انا|اني)\b|"
        r"(?:اي|ما)\s+(?:هو\s+)?(?:ال)?صف\s+(?:انا|اني)\b|"
        r"(?:شو|ايش|ما)\s+(?:هو\s+)?الصف\s+المسجل\s+(?:عندي|لي)\b",
        normalized,
    ) is not None


def user_asks_assistant_identity(message):
    normalized = re.sub(r"[\u064b-\u065f\u0670ـ]", "", message.casefold())
    return re.search(
        r"(?:شو|ما|ايش|إيش|وش)\s+(?:هو\s+)?اسمك|"
        r"(?:مين|من)\s+(?:أنت|انت)|"
        r"(?:مين|من)\s+(?:صنعك|طورك|طوّرك)|"
        r"عرفني\s+عن\s+نفسك|احكيلي\s+عن\s+نفسك",
        normalized,
    ) is not None


def conversation_system_instruction(
    first_reply,
    grade,
    ask_grade,
    user_greeted=False,
    asks_identity=False,
    user_message="",
    has_previous_answer=False,
):
    instructions = [SYSTEM_INSTRUCTION]
    if user_greeted or asks_identity:
        instructions.append(
            "في هذه الرسالة، عرّف عن نفسك بوضوح بالنص: "
            "«أنا فهيم، مساعد ذكي للطلاب في مدرسة خريبة السوق». "
            "إذا سأل الطالب عن مطورك، قل: «صنعني المطور جميل إسماعيل أبو حماد»."
        )
        if user_greeted:
            instructions.append("بدأ الطالب بتحية؛ ابدأ بهذا التعريف ثم أجب عن سؤاله.")
    elif first_reply:
        instructions.append(
            "هذه أول رسالة في المحادثة ولم يبدأ الطالب بتحية؛ لا ترحّب به "
            "ولا تعرّف بنفسك، وابدأ بالمعلومة أو الحل مباشرة دون مقدمة."
        )
    else:
        instructions.append(
            "هذه متابعة لمحادثة بدأت سابقًا؛ أجب عن الرسالة مباشرة ولا تبدأ بتحية."
        )

    if grade:
        instructions.append(
            f"صف الطالب المحفوظ في ملفه هو {grade}. استخدم كتب هذا الصف "
            "ومنهجه الأردني عند صلة السؤال بالدراسة."
        )
    elif ask_grade:
        instructions.append(
            "لم يُعرف صف الطالب بعد. اسأله مرة واحدة فقط وبأسلوب أردني طبيعي: "
            "«وبالمناسبة، إنت بأي صف؟» ولا تؤخر الإجابة عن سؤاله بانتظار الصف."
        )
    else:
        instructions.append(
            "سبق أن سُئل الطالب عن صفه ولم يقدّم صفًا محفوظًا؛ لا تعاود السؤال عنه "
            "في هذه المحادثة أو في محادثة جديدة."
        )
    if (
        has_previous_answer
        and re.search(r"جدول|جداول|جدولي", user_message)
    ):
        instructions.append(
            "أعد تنسيق المعلومات نفسها فقط في جدول مناسب، ولا تبدأ موضوعًا أو خطة جديدة."
        )
    return " ".join(instructions)


def get_database():
    global database
    if database is None:
        with _database_lock:
            if database is None:
                database_url = os.environ.get("DATABASE_URL", "").strip()
                if not database_url:
                    raise RuntimeError(
                        "Set DATABASE_URL to a PostgreSQL connection URL."
                    )
                initialized_database = Database(database_url)
                admin_password = os.environ.get("ADMIN_PASSWORD", "")
                if admin_password:
                    if len(admin_password) < PASSWORD_MIN_LENGTH:
                        raise RuntimeError(
                            f"ADMIN_PASSWORD must be at least {PASSWORD_MIN_LENGTH} characters."
                        )
                    admin_email = os.environ.get(
                        "ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL
                    ).strip()
                    if not re.fullmatch(
                        r"[^@\s]+@[^@\s]+\.[^@\s]+", admin_email
                    ):
                        raise RuntimeError("ADMIN_EMAIL must be a valid email address.")
                    initialized_database.ensure_primary_admin(
                        admin_email, admin_password
                    )
                database = initialized_database
    return database


def wants_image_generation(message):
    normalized = message.casefold()
    normalized = normalized.translate(str.maketrans("أإآ", "ااا"))
    normalized = re.sub(r"[\u064b-\u065f\u0670ـ]", "", normalized)
    return re.search(
        r"(?:ارسم(?:ي|لي)?|انشئ(?:ي|لي)?|اعمل(?:ي|لي)?|اعمللي|سوي|صمم(?:ي|لي)?|"
        r"ولد|تولد|بدي|اريد|ممكن|please)\s*(?:لي\s*)?(?:ان\s*)?"
        r"(?:(?:تعمل|اعمل|ترسم|ارسم|تنشئ|انشئ|تصمم|صمم)\s*)?"
        r"(?:صورة|صوره|صور|رسمة|لوحة|تصميم|خلفية|ملصق|شعار|"
        r"an?\s+(?:image|picture|illustration)|image|picture)",
        normalized,
    ) is not None


def estimate_part_tokens(part):
    if part.get("type") == "text":
        return math.ceil(len(part.get("text", "").encode("utf-8")) / 2)
    encoded_data = part.get("data", "")
    byte_count = len(encoded_data) * 3 // 4
    if part.get("type") == "document":
        return math.ceil(byte_count / 2)
    return max(258, math.ceil(byte_count / 32_768) * 258)


def select_prior_images(messages, current_message):
    images = [
        message
        for message in messages
        if message["role"] == "user"
        and (message.get("has_image") or message.get("image_data") is not None)
    ]
    if not images:
        return []

    normalized = current_message.casefold().translate(
        str.maketrans("أإآ", "ااا")
    )
    normalized = normalized.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    image_ordinals = {
        "1": 1,
        "first": 1,
        "الاولى": 1,
        "اولى": 1,
        "الأولى": 1,
        "2": 2,
        "second": 2,
        "الثانية": 2,
        "ثانيه": 2,
        "3": 3,
        "third": 3,
        "الثالثة": 3,
        "ثالثه": 3,
    }
    ordinal_matches = re.findall(
        r"(?:الصورة|الصوره|صورة|image|picture)\s*(?:رقم\s*)?"
        r"(\d+|first|second|third|الأولى|الاولى|اولى|الثانية|ثانيه|"
        r"الثالثة|ثالثه)",
        normalized,
    )
    requested_ordinals = {
        image_ordinals.get(value, int(value) if value.isdigit() else 0)
        for value in ordinal_matches
    }
    if requested_ordinals:
        return [
            images[index - 1]
            for index in sorted(requested_ordinals)
            if 1 <= index <= len(images)
        ]

    if re.search(r"قارن|مقارن|الصورتين|الصور|compare|both images", normalized):
        return images

    if re.search(
        r"صورة|الصورة|الصوره|المرفق|المرفقة|image|picture|"
        r"هاي|هذي|هذه|هذا|هي|هو|نفسها|نفسه|زيها|مثلها|عليها|فيها|"
        r"السابق|السابقة|قبل|كمان|it\b|this\b|that\b|same\b",
        normalized,
    ):
        return [images[-1]]
    return []


def select_images_that_fit(images, current_parts, system_instruction):
    base_size = len(
        json.dumps(
            {"input": current_parts, "system_instruction": system_instruction},
            ensure_ascii=False,
        ).encode("utf-8")
    )
    available_bytes = MAX_GEMINI_REQUEST_BYTES - base_size - 2 * 1024 * 1024
    selected = []
    for image in reversed(images):
        encoded_size = math.ceil(image["image_size"] / 3) * 4 + 128
        if len(selected) >= MAX_CONTEXT_IMAGES or encoded_size > available_bytes:
            continue
        selected.append(image)
        available_bytes -= encoded_size
    return list(reversed(selected))


def build_conversation_input(
    messages,
    current_message_id,
    current_message,
    current_parts,
    system_instruction,
    extra_parts=(),
):
    previous_messages = [
        message for message in messages if message["id"] < current_message_id
    ]
    selected_images = [
        image
        for image in select_prior_images(previous_messages, current_message)
        if image.get("image_data") is not None
    ]
    current_tokens = sum(estimate_part_tokens(part) for part in current_parts)
    extra_tokens = sum(estimate_part_tokens(part) for part in extra_parts)
    image_tokens = sum(
        estimate_part_tokens(
            {"type": "image", "data": base64.b64encode(image["image_data"]).decode("ascii")}
        )
        for image in selected_images
    )
    available_tokens = (
        MAX_GEMINI_CONTEXT_TOKENS
        - math.ceil(len(system_instruction.encode("utf-8")) / 2)
        - current_tokens
        - extra_tokens
        - image_tokens
    )
    if available_tokens < 0:
        raise ValueError(
            "رسالتك ومرفقاتك أكبر من الحد المسموح. احذف بعض المرفقات "
            "أو أرسلها في رسائل منفصلة."
        )

    rendered_history = []
    image_number = 0
    for message in previous_messages:
        line = f"{'الطالب' if message['role'] == 'user' else 'فهيم'}: "
        line += message["content"] or "(رسالة بلا نص)"
        if message.get("has_image") or message.get("image_data") is not None:
            image_number += 1
            line += f" [أرفق الطالب صورة سابقة رقم {image_number}]"
        rendered_history.append((line, math.ceil(len(line.encode("utf-8")) / 2)))

    rendered_history = rendered_history[-MAX_HISTORY_MESSAGES:]
    history_lines = []
    used_tokens = 0
    for line, line_tokens in reversed(rendered_history):
        if used_tokens + line_tokens > available_tokens:
            break
        history_lines.append(line)
        used_tokens += line_tokens
    history_lines.reverse()

    history_text = ""
    if history_lines:
        history_text = (
            "سجل المحادثة السابق، مرتبًا من الأقدم إلى الأحدث. "
            "استخدمه لفهم الإشارات والضمائر والسياق:\n"
            + "\n".join(history_lines)
        )
    context_parts = (
        [{"type": "text", "text": history_text}] if history_text else []
    )
    for image in selected_images:
        context_parts.extend(
            [
                {"type": "text", "text": "صورة سابقة أشار إليها الطالب:"},
                {
                    "type": "image",
                    "mime_type": image["image_mime"],
                    "data": base64.b64encode(image["image_data"]).decode("ascii"),
                },
            ]
        )

    parts = context_parts + list(extra_parts) + current_parts
    request_size = len(
        json.dumps(
            {"input": parts, "system_instruction": system_instruction},
            ensure_ascii=False,
        ).encode("utf-8")
    )
    if request_size > MAX_GEMINI_REQUEST_BYTES:
        raise ValueError(
            "المحادثة طويلة جدًا لإكمال الطلب. ابدأ محادثة جديدة "
            "أو أرسل صورًا أقل."
        )

    return parts


def make_conversation_title(message, has_image):
    title = message.strip()
    title = re.sub(r"\s+", " ", title)
    if has_image and not title:
        return "محادثة حول صورة"

    title = re.sub(
        r"^(?:(?:السلام عليكم|مرحبا|مرحباً|أهلاً|اهلا|أهلًا|هلا|هاي|hello|hi)"
        r"[\s،,:.!؟-]*)+",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()
    title = re.sub(r"^(?:يا\s+)?(?:جميل|فهيم)[\s،,:.!؟-]*", "", title).strip()
    title = re.sub(
        r"^(?:كيفك|كيف حالك|شو أخبارك|شو اخبارك|كيف الأمور|كيف الامور)"
        r"[\s،,:.!؟-]*",
        "",
        title,
    ).strip()
    if not title or re.fullmatch(
        r"(?:كيفك|كيف حالك|شو أخبارك|شو اخبارك|كيف الأمور|كيف الامور)"
        r"[؟?!.\s]*",
        title,
    ):
        return "محادثة جديدة"
    return title[:MAX_TITLE_LENGTH].rstrip()

def generate_conversation_title(message, answer):
    model = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash").strip()
    title_input = (
        "اكتب عنوانًا لهذه المحادثة يصف موضوعها العام بدقة، اعتمادًا على أول رسالة "
        "ورد فهيم. لا تكتب إجابة الطالب ولا تلخص المحادثة كاملة. أعد العنوان فقط "
        "بالعربية، من 3 إلى 8 كلمات، دون علامات اقتباس أو ترقيم.\n\n"
        f"أول رسالة من الطالب:\n{message[:2000]}\n\n"
        f"رد فهيم:\n{answer[:2000]}"
    )
    request = Request(
        API_URL,
        data=json.dumps(
            {
                "model": model,
                "input": title_input,
                "system_instruction": (
                    "أنت تنشئ عناوين قصيرة ودقيقة لمحادثات مساعد دراسي. "
                    "استخرج الموضوع الأساسي ولا تضف موضوعًا غير موجود."
                ),
            }
        ).encode("utf-8"),
        headers={
            "x-goog-api-key": os.environ["GEMINI_API_KEY"],
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=45) as response:
            interaction = json.loads(response.read())
    except HTTPError as error:
        raise RuntimeError(f"رفضت خدمة Gemini إنشاء عنوان (HTTP {error.code}).") from error
    except (URLError, TimeoutError) as error:
        raise RuntimeError(f"تعذّر الاتصال بخدمة Gemini لإنشاء عنوان: {error}") from error
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise RuntimeError("أعادت Gemini بيانات غير مفهومة للعنوان.") from error

    if not isinstance(interaction, dict):
        raise RuntimeError("أعادت Gemini بنية غير صالحة للعنوان.")
    title_parts = []
    output_text = interaction.get("output_text")
    if isinstance(output_text, str):
        title_parts.append(output_text)
    for step in interaction.get("steps", []):
        if not isinstance(step, dict) or step.get("type") != "model_output":
            continue
        for block in step.get("content", []):
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    title_parts.append(text)
    title = " ".join(" ".join(title_parts).split())
    title = re.sub(r"^[\s\"'`#*]+|[\s\"'`#*]+$", "", title)
    title = re.sub(r"\s+", " ", title).strip()
    if not title:
        raise RuntimeError("لم تُرجع Gemini عنوانًا صالحًا للمحادثة.")
    return title[:MAX_TITLE_LENGTH].rstrip()


def load_local_env():
    env_path = ROOT / ".env"
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip("\"'")
        if name and name not in os.environ:
            os.environ[name] = value


STATIC_GZIP_TYPES = {".html", ".js", ".css", ".svg", ".json", ".txt"}
STATIC_GZIP_CACHE = {}
STATIC_GZIP_LOCK = threading.Lock()
GEMINI_THINKING_LEVELS = {"minimal", "low", "medium", "high"}


class UploadQuota:
    """يحفظ عدد مرفقات كل طالب لليوم الحالي في ملف JSON."""

    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()
        self.data = {}
        self._load()

    @staticmethod
    def _today():
        return datetime.now(JORDAN_TZ).strftime("%Y-%m-%d")

    def _load(self):
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
        day = self._today()
        self.data = {
            key: value
            for key, value in (raw.items() if isinstance(raw, dict) else [])
            if isinstance(value, dict) and value.get("day") == day
        }

    def _save(self):
        day = self._today()
        self.data = {k: v for k, v in self.data.items() if v.get("day") == day}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.data), encoding="utf-8")
            temporary.replace(self.path)
        except OSError as error:
            print(f"[QUOTA] تعذّر حفظ الحصة: {error}", flush=True)

    def _entry(self, user_id):
        key = str(user_id)
        day = self._today()
        entry = self.data.get(key)
        if not entry or entry.get("day") != day:
            entry = {"day": day, "used": 0}
            self.data[key] = entry
        return entry

    @staticmethod
    def _status(entry):
        return {
            "limit": DAILY_UPLOAD_LIMIT,
            "used": entry["used"],
            "remaining": max(0, DAILY_UPLOAD_LIMIT - entry["used"]),
        }

    def status(self, user_id):
        with self.lock:
            return self._status(self._entry(user_id))

    def consume(self, user_id):
        with self.lock:
            entry = self._entry(user_id)
            if entry["used"] >= DAILY_UPLOAD_LIMIT:
                return False, self._status(entry)
            entry["used"] += 1
            self._save()
            return True, self._status(entry)

    def refund(self, user_id):
        """يعيد مرفقًا واحدًا (فشل الطلب قبل أن يبدأ الرد أو أُوقف قبل أي نص)."""
        with self.lock:
            entry = self._entry(user_id)
            if entry["used"] > 0:
                entry["used"] -= 1
                self._save()


class UserPreferences:
    """تفضيلات كل مستخدم (المظهر) تُحفظ في ملف JSON."""

    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
        self.data = raw if isinstance(raw, dict) else {}

    def get(self, user_id):
        with self.lock:
            entry = self.data.get(str(user_id))
            theme = entry.get("theme") if isinstance(entry, dict) else None
            return {"theme": theme if theme in ALLOWED_THEMES else None}

    def set_theme(self, user_id, theme):
        with self.lock:
            entry = self.data.get(str(user_id))
            if not isinstance(entry, dict):
                entry = {}
            updated_entry = {**entry, "theme": theme}
            updated_data = {**self.data, str(user_id): updated_entry}
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.path.with_suffix(".tmp")
                temporary.write_text(json.dumps(updated_data), encoding="utf-8")
                temporary.replace(self.path)
            except OSError as error:
                print(f"[PREFS] تعذّر حفظ التفضيلات: {error}", flush=True)
                raise
            self.data = updated_data
            return {"theme": theme}


UPLOAD_QUOTA = UploadQuota(UPLOAD_QUOTA_PATH)
USER_PREFERENCES = UserPreferences(USER_PREFERENCES_PATH)


_ARABIC_MARKS = re.compile(r"[\u064b-\u065f\u0670\u0640]")


def normalize_arabic(text):
    """يوحّد الهمزات والتاء المربوطة والياء ويحذف التشكيل والمدّ ليتطابق الاسم مهما اختلف إملاؤه."""
    text = _ARABIC_MARKS.sub("", text)
    text = text.translate(
        str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه"})
    )
    return re.sub(r"\s+", " ", text).strip().casefold()


def name_tokens(text):
    """يقسّم الاسم إلى أسمائه بعد دمج (عبد الله / أبو حماد / بن علي) كاسم واحد."""
    words = [word for word in normalize_arabic(text).split(" ") if word]
    tokens = []
    index = 0
    while index < len(words):
        word = words[index]
        if word in NAME_PREFIXES and index + 1 < len(words):
            tokens.append(word + words[index + 1])
            index += 2
        else:
            tokens.append(word)
            index += 1
    return tokens


def validate_full_name(raw):
    """يعيد (الاسم المنظّف، رسالة الخطأ). الاسم المقبول: أربعة أسماء عربية بالضبط."""
    if not isinstance(raw, str):
        return None, "اكتب اسمك الرباعي."
    display = _ARABIC_MARKS.sub("", re.sub(r"\s+", " ", raw).strip())
    if not display:
        return None, "اكتب اسمك الرباعي."
    if len(display) > 80:
        return None, "الاسم طويل جدًا. اكتب اسمك الرباعي فقط."
    if not re.fullmatch(r"[\u0621-\u064a ]+", normalize_arabic(display)):
        return None, "اكتب الاسم بالأحرف العربية فقط، دون أرقام أو رموز."
    tokens = name_tokens(display)
    if len(tokens) != 4:
        return None, (
            "اكتب اسمك الرباعي كاملًا: اسمك، اسم أبيك، اسم جدك، اسم العائلة. "
            f"عدد الأسماء التي كتبتها: {len(tokens)}."
        )
    if any(len(token) < 2 or len(token) > 30 for token in tokens):
        return None, "تأكد من كتابة كل اسم بشكل صحيح."
    if len(set(tokens)) < 2:
        return None, "اكتب اسمك الحقيقي الرباعي."
    return display, None


def validate_account_name(raw):
    """يتحقق من اسم حساب عربي يتكون من أربع كلمات مفصولة بمسافات."""
    if not isinstance(raw, str):
        return None, "اكتب اسمك الرباعي."
    display = _ARABIC_MARKS.sub("", re.sub(r"\s+", " ", raw).strip())
    normalized = normalize_arabic(display)
    if not display:
        return None, "اكتب اسمك الرباعي."
    if len(display) > 80:
        return None, "الاسم طويل جدًا. اكتب اسمك الرباعي فقط."
    if not re.fullmatch(r"[\u0621-\u064a]+(?: [\u0621-\u064a]+){3}", normalized):
        return None, "اكتب أربعة أسماء باللغة العربية فقط، دون أرقام أو رموز."
    if any(len(word) < 2 or len(word) > 30 for word in normalized.split()):
        return None, "تأكد من كتابة كل اسم بشكل صحيح."
    return display, None


def normalize_phone_number(raw):
    required_error = "أدخل رقم هاتفك لإكمال إنشاء الحساب."
    error = (
        "رقم الهاتف غير صالح. أدخل رقمًا أردنيًا يبدأ بـ 077 أو 078 أو 079، "
        "أو بصيغة +962."
    )
    if raw is None:
        return None, required_error
    if not isinstance(raw, str):
        return None, error

    phone = raw.translate(
        str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
    ).strip()
    if not phone:
        return None, required_error
    if len(phone) > 32 or not re.fullmatch(r"[0-9+\s().-]+", phone):
        return None, error

    compact = re.sub(r"[\s().-]", "", phone)
    if compact.startswith("00"):
        compact = "+" + compact[2:]
    elif re.fullmatch(r"07[789][0-9]{7}", compact):
        compact = "+962" + compact[1:]

    if re.fullmatch(r"\+9627[789][0-9]{7}", compact):
        return compact, None
    return None, error


def student_email(tokens):
    return ".".join(tokens) + "@" + STUDENT_EMAIL_DOMAIN


def student_name_from_email(email):
    local, _, domain = str(email).rpartition("@")
    if domain != STUDENT_EMAIL_DOMAIN:
        return None
    return local.replace(".", " ")


class UserProfiles:
    """الاسم الرباعي والصف المختار عند التسجيل (ملف JSON)."""

    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
        self.data = raw if isinstance(raw, dict) else {}

    def get(self, user_id):
        with self.lock:
            entry = self.data.get(str(user_id))
            return dict(entry) if isinstance(entry, dict) else None

    def set(self, user_id, full_name, grade_key):
        with self.lock:
            self.data[str(user_id)] = {"fullName": full_name, "grade": grade_key}
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.path.with_suffix(".tmp")
                temporary.write_text(
                    json.dumps(self.data, ensure_ascii=False), encoding="utf-8"
                )
                temporary.replace(self.path)
            except OSError as error:
                print(f"[PROFILES] تعذّر حفظ الملف الشخصي: {error}", flush=True)


USER_PROFILES = UserProfiles(USER_PROFILES_PATH)


def decorate_user(user):
    """يضيف الاسم الرباعي والصف إلى بيانات المستخدم المرسلة للواجهة."""
    result = dict(user)
    profile = USER_PROFILES.get(user["id"]) or {}
    full_name = profile.get("fullName") or student_name_from_email(user.get("email", ""))
    if student_name_from_email(user.get("email", "")):
        result["isStudentAccount"] = True
    if full_name:
        result["name"] = full_name
    grade_key = profile.get("grade")
    if grade_key in GRADE_CHOICES:
        result["gradeLabel"] = GRADE_CHOICES[grade_key]["label"]
    return result


def grade_percentages(counts, total):
    """نسب مئوية صحيحة مجموعها 100 (طريقة أكبر باقٍ)."""
    if not total:
        return {key: 0 for key in counts}
    raw = {key: counts[key] * 100 / total for key in counts}
    floors = {key: int(value) for key, value in raw.items()}
    leftover = 100 - sum(floors.values())
    for key in sorted(counts, key=lambda k: raw[k] - floors[k], reverse=True)[:leftover]:
        floors[key] += 1
    return floors


class GradeDirectory:
    """صف كل مستخدم من قاعدة البيانات مع تخزين مؤقت قصير وجلب متوازٍ."""

    TTL_SECONDS = 60

    def __init__(self):
        self.lock = threading.Lock()
        self.cache = {}

    def grades_for(self, user_ids):
        now = time.monotonic()
        result = {}
        missing = []
        with self.lock:
            for user_id in user_ids:
                hit = self.cache.get(user_id)
                if hit and now - hit[0] < self.TTL_SECONDS:
                    result[user_id] = hit[1]
                else:
                    missing.append(user_id)
        if missing:

            def fetch(user_id):
                profile = USER_PROFILES.get(user_id) or {}
                try:
                    preferences = get_database().get_student_preferences(user_id)
                except Exception as error:
                    print(f"[GRADES] تعذّر جلب صف {user_id}: {error}", flush=True)
                    return user_id, profile.get("grade"), False
                key = STORED_TO_GRADE_KEY.get(preferences.get("grade")) or profile.get("grade")
                return user_id, key if key in GRADE_CHOICES else None, True

            with ThreadPoolExecutor(max_workers=8) as pool:
                for user_id, key, ok in pool.map(fetch, missing):
                    result[user_id] = key
                    if ok:
                        with self.lock:
                            self.cache[user_id] = (now, key)
        return result

    def forget(self, user_id):
        with self.lock:
            self.cache.pop(user_id, None)


GRADE_DIRECTORY = GradeDirectory()


def decorate_support_messages(messages):
    """يعرض اسم الطالب الرباعي وصفه بدل البريد الداخلي في رسائل مركز المساعدة."""
    if not isinstance(messages, list):
        return messages
    for message in messages:
        if not isinstance(message, dict):
            continue
        derived = student_name_from_email(message.get("user_email", ""))
        if not derived:
            continue
        profile = USER_PROFILES.get(message.get("user_id")) or {}
        message["user_name"] = profile.get("fullName") or derived
        grade_key = profile.get("grade")
        message["user_email"] = (
            f"الصف {GRADE_CHOICES[grade_key]['label']}"
            if grade_key in GRADE_CHOICES
            else "حساب طالب"
        )
    return messages


def decorate_dashboard(data):
    """يضيف أسماء الطلاب وصفوفهم ونسب الصفوف إلى بيانات لوحة التحكم."""
    users = data.get("users") if isinstance(data, dict) else None
    if not isinstance(users, list):
        return data
    users = [user for user in users if isinstance(user, dict) and "id" in user]
    grades = GRADE_DIRECTORY.grades_for([user["id"] for user in users])
    counts = {key: 0 for key in GRADE_ORDER}
    unspecified = 0
    for user in users:
        email = str(user.get("email", ""))
        derived = student_name_from_email(email)
        if derived:
            profile = USER_PROFILES.get(user["id"]) or {}
            user["is_student"] = True
            user["name"] = profile.get("fullName") or derived
        key = grades.get(user["id"])
        if key:
            user["grade_label"] = GRADE_CHOICES[key]["label"]
        if not user.get("is_admin"):
            if key:
                counts[key] += 1
            else:
                unspecified += 1
    total = sum(counts.values())
    percents = grade_percentages(counts, total)
    data["gradeStats"] = {
        "total": total,
        "unspecified": unspecified,
        "grades": [
            {
                "key": key,
                "label": GRADE_CHOICES[key]["label"],
                "count": counts[key],
                "percent": percents[key],
                "exact": round(counts[key] * 100 / total, 1) if total else 0,
            }
            for key in GRADE_ORDER
        ],
    }
    return data


class GeminiStream:
    """غلاف خفيف حول استجابة Gemini يوفّر readline() ويغلق الاتصال عند الانتهاء."""

    def __init__(self, connection, response):
        self._connection = connection
        self._response = response

    def readline(self):
        return self._response.readline()

    def close(self):
        try:
            self._response.close()
        finally:
            self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
        return False


def safe_chat_diagnostic_message(message):
    message = str(message)
    message = re.sub(
        r"(?i)\b(?:api[_ -]?key|authorization|password|secret|token)\b"
        r"\s*[:=]\s*[^\s,;]+",
        "[REDACTED]",
        message,
    )
    message = re.sub(r"(?i)\bbearer\s+\S+", "Bearer [REDACTED]", message)
    message = re.sub(r"\bAIza[0-9A-Za-z_-]{20,}\b", "[REDACTED]", message)
    message = re.sub(r"\bsk-[0-9A-Za-z_-]{16,}\b", "[REDACTED]", message)
    message = re.sub(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        "[REDACTED_EMAIL]",
        message,
    )
    message = re.sub(
        r"(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)",
        "[REDACTED_PHONE]",
        message,
    )
    message = re.sub(r"[\r\n\t]+", " ", message)
    return message[:240]


def log_chat_diagnostic(phase, error_type, message, upstream_http_status=None):
    diagnostic = {
        "phase": phase,
        "error_type": error_type,
        "upstream_http_status": upstream_http_status,
        "message": safe_chat_diagnostic_message(message),
    }
    print(
        "[CHAT_DIAG] "
        + json.dumps(diagnostic, ensure_ascii=True, separators=(",", ":")),
        flush=True,
    )


class ChatHandler(SimpleHTTPRequestHandler):
    # تعطيل خوارزمية Nagle: كل جزء من البث يُرسل فورًا بدل أن ينتظر ACK (يزيل تقطّع الكتابة).
    disable_nagle_algorithm = True
    thinking_rejected = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_ROOT), **kwargs)

    def send_response(self, code, message=None):
        self._last_status = code
        super().send_response(code, message)

    def send_error(self, code, message=None, explain=None):
        if code == 404:
            title = "الصفحة غير موجودة"
            guidance = "تحقق من الرابط، أو ارجع إلى الصفحة الرئيسية."
        elif code >= 500:
            title = "الخادم يواجه مشكلة مؤقتة"
            guidance = "انتظر قليلًا ثم حدّث الصفحة."
        else:
            title = "تعذّر فتح الصفحة"
            guidance = "تحقق من الرابط وحاول مرة أخرى."

        body = (
            "<!doctype html><html lang=\"ar\"><meta charset=\"utf-8\">"
            f"<title>{title}</title><main><h1>{title}</h1><p>{guidance}</p></main></html>"
        ).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def end_headers(self):
        visitor_token = getattr(self, "new_visitor_token", None)
        if visitor_token:
            cookie = (
                f"{VISITOR_COOKIE_NAME}={visitor_token}; Path=/; "
                f"Max-Age={VISITOR_COOKIE_MAX_AGE}; HttpOnly; SameSite=Lax"
            )
            forwarded_proto = (
                self.headers.get("X-Forwarded-Proto", "")
                .split(",", 1)[0]
                .strip()
                .lower()
            )
            if (
                os.environ.get("COOKIE_SECURE", "false").strip().lower() == "true"
                or forwarded_proto == "https"
            ):
                cookie += "; Secure"
            self.send_header("Set-Cookie", cookie)
            self.new_visitor_token = None
        cache_control = getattr(self, "_static_cache_control", None)
        if cache_control and getattr(self, "_last_status", None) in (200, 304):
            self.send_header("Cache-Control", cache_control)
            self._static_cache_control = None
        super().end_headers()

    def page_visitor_token(self):
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get("Cookie", ""))
        except CookieError:
            cookies = SimpleCookie()
        visitor = cookies.get(VISITOR_COOKIE_NAME)
        if visitor and re.fullmatch(r"[A-Za-z0-9_-]{40,50}", visitor.value):
            return visitor.value
        self.new_visitor_token = secrets.token_urlsafe(32)
        return self.new_visitor_token

    def do_GET(self):
        page_path = urlsplit(self.path).path.rstrip("/") or "/"
        accepts_html = "text/html" in self.headers.get("Accept", "").lower()
        is_document = (
            accepts_html
            or self.headers.get("Sec-Fetch-Dest", "").lower() == "document"
            or self.headers.get("Sec-Fetch-Mode", "").lower() == "navigate"
        )
        if page_path in {"/", "/index.html"} and is_document:
            get_database().record_page_view(
                self.page_visitor_token(), dedup_seconds=VISIT_DEDUP_SECONDS
            )
        user = self.current_user()
        if page_path in {"/", "/index.html", "/admin.html"}:
            if not user:
                self.send_response(303)
                self.send_header("Location", "/login.html")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            if page_path == "/admin.html" and not self.is_admin(user):
                self.send_response(303)
                self.send_header("Location", "/")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
        if self.path == "/api/me":
            if not user:
                self.send_json({"error": "سجّل الدخول للمتابعة."}, 401)
            else:
                self.send_json(
                    {
                        "user": decorate_user(user),
                        "isAdmin": self.is_admin(user),
                        "isPrimaryAdmin": self.is_primary_admin(user),
                    }
                )
            return

        if self.path == "/api/account/profile":
            self.account_profile(user)
            return

        if self.path == "/api/preferences":
            if not user:
                self.send_unauthorized()
            else:
                self.send_json({"preferences": USER_PREFERENCES.get(user["id"])})
            return

        if self.path == "/api/uploads/quota":
            if not user:
                self.send_unauthorized()
            else:
                self.send_json({"quota": self.quota_for(user)})
            return

        if self.path == "/api/admin/dashboard":
            if not user:
                self.send_unauthorized()
                return
            if not self.is_admin(user):
                self.send_json({"error": "ليس لديك صلاحية لفتح لوحة التحكم."}, 403)
                return
            admin_email = os.environ.get("ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL).strip()
            self.send_json(decorate_dashboard(get_database().admin_dashboard(admin_email)))
            return

        if self.path == "/api/admin/statistics":
            if not user:
                self.send_unauthorized()
                return
            if not self.is_admin(user):
                self.send_json({"error": "ليس لديك صلاحية لفتح لوحة التحكم."}, 403)
                return
            self.send_json(get_database().admin_statistics())
            return

        if self.path == "/api/admin/support-messages":
            if not user:
                self.send_unauthorized()
                return
            if not self.is_admin(user):
                self.send_json(
                    {"error": "ليس لديك صلاحية لعرض رسائل مركز المساعدة."}, 403
                )
                return
            self.send_json(
                {"messages": decorate_support_messages(get_database().list_support_messages())}
            )
            return

        if self.path == "/api/conversations":
            if not user:
                self.send_unauthorized()
                return
            self.send_json(
                {"conversations": get_database().list_conversations(user["id"])}
            )
            return

        match = re.fullmatch(r"/api/conversations/([a-f0-9]{32})", self.path)
        if match:
            if not user:
                self.send_unauthorized()
                return
            record = get_database().get_conversation(user["id"], match.group(1))
            if not record:
                self.send_json({"error": "المحادثة غير موجودة."}, 404)
                return
            conversation, messages = record
            self.send_json(
                {
                    "conversation": conversation,
                    "messages": [
                        {
                            "role": message["role"],
                            "content": message["content"],
                            "image": (
                                {
                                    "mimeType": message["image_mime"],
                                    "data": base64.b64encode(
                                        message["image_data"]
                                    ).decode("ascii"),
                                }
                                if message["image_data"] is not None
                                else None
                            ),
                        }
                        for message in messages
                    ],
                }
            )
            return

        self._static_cache_control = self.static_cache_control()
        if self.serve_static_file():
            return
        super().do_GET()

    def static_cache_control(self):
        parts = urlsplit(self.path)
        if parts.path.startswith("/api/"):
            return None
        # الروابط المرقّمة (?v=..) تُخزَّن يومًا كاملًا، وغيرها (index.html) تُراجَع بخفّة عبر ETag.
        if "v" in parse_qs(parts.query):
            return "public, max-age=86400"
        return "no-cache"

    def serve_static_file(self):
        if "gzip" not in self.headers.get("Accept-Encoding", "").lower():
            return False
        url_path = urlsplit(self.path).path
        if url_path.startswith("/api/"):
            return False
        try:
            file_path = Path(self.translate_path(self.path))
            if file_path.is_dir():
                if not url_path.endswith("/"):
                    return False
                file_path = file_path / "index.html"
            if file_path.suffix.lower() not in STATIC_GZIP_TYPES:
                return False
            stat = file_path.stat()
        except OSError:
            return False
        signature = (stat.st_mtime_ns, stat.st_size)
        key = str(file_path)
        with STATIC_GZIP_LOCK:
            cached = STATIC_GZIP_CACHE.get(key)
        if cached is None or cached[0] != signature:
            try:
                data = file_path.read_bytes()
            except OSError:
                return False
            etag = f'W/"{stat.st_mtime_ns:x}-{stat.st_size:x}"'
            cached = (signature, gzip.compress(data, compresslevel=6, mtime=0), etag)
            with STATIC_GZIP_LOCK:
                STATIC_GZIP_CACHE[key] = cached
        _, compressed, etag = cached
        try:
            if self.headers.get("If-None-Match", "").strip() == etag:
                self.send_response(304)
                self.send_header("ETag", etag)
                self.send_header("Vary", "Accept-Encoding")
                self.end_headers()
                return True
            content_type = self.guess_type(str(file_path))
            if content_type.startswith("text/"):
                content_type += "; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
            self.send_header("ETag", etag)
            self.send_header("Content-Length", str(len(compressed)))
            self.send_header("Last-Modified", self.date_time_string(stat.st_mtime))
            self.end_headers()
            self.wfile.write(compressed)
        except (BrokenPipeError, ConnectionResetError):
            pass
        return True

    def do_POST(self):
        if self.path != "/api/chat":
            return self._do_POST()

        self._chat_perf_started = time.perf_counter()
        self._chat_perf = {}
        self._quota_charged = None
        self._quota_kept = False
        try:
            self._do_POST()
        finally:
            self.close_gemini_prewarm()
            # المرفق لا يُحتسب إن لم يبدأ رد فهيم (خطأ، أو أوقف الطالب قبل أي نص)
            charged = getattr(self, "_quota_charged", None)
            if charged is not None and not getattr(self, "_quota_kept", False):
                UPLOAD_QUOTA.refund(charged)
            self._quota_charged = None
            total = time.perf_counter() - self._chat_perf_started
            stages = (
                "student_preferences",
                "title_generation",
                "conversation_context",
                "conversation_images",
                "pre_gemini",
                "gemini_first_byte",
                "gemini_total",
                "save_exchange",
            )
            details = " ".join(
                f"{stage}={self._chat_perf[stage]:.3f}s"
                if stage in self._chat_perf
                else f"{stage}=n/a"
                for stage in stages
            )
            print(f"[PERF] {details} total_request={total:.3f}s", flush=True)

    def _record_chat_perf(self, stage, started):
        if hasattr(self, "_chat_perf"):
            self._chat_perf[stage] = time.perf_counter() - started

    def _do_POST(self):
        if self.path == "/api/auth/register":
            self.register_account()
            return
        if self.path == "/api/auth/login":
            self.login_account()
            return
        if self.path == "/api/auth/forgot-password":
            self.forgot_password()
            return
        if self.path == "/api/auth/reset-password":
            self.reset_password()
            return
        if self.path == "/api/auth/change-password":
            self.change_password()
            return
        if self.path == "/api/account/profile":
            self.account_profile()
            return
        if self.path == "/api/account/name":
            self.change_account_name()
            return
        if self.path == "/api/account/phone":
            self.change_account_phone()
            return
        if self.path == "/api/support-messages":
            self.submit_support_message()
            return
        admin_password_match = re.fullmatch(
            r"/api/admin/users/([a-f0-9]{32})/password", self.path
        )
        if admin_password_match:
            self.admin_set_user_password(admin_password_match.group(1))
            return
        admin_role_match = re.fullmatch(
            r"/api/admin/users/([a-f0-9]{32})/admin", self.path
        )
        if admin_role_match:
            self.admin_set_user_role(admin_role_match.group(1))
            return
        if self.path == "/api/preferences":
            self.save_preferences()
            return
        if self.path == "/api/logout":
            token = self.session_token()
            try:
                get_database().delete_session(token)
            except Database.error_types:
                self.send_json({"error": "تعذّر إنهاء الجلسة. حاول مرة أخرى."}, 500)
                return
            self.send_response(204)
            self.send_header(
                "Set-Cookie",
                self.session_cookie("", max_age=0),
            )
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if self.path != "/api/chat":
            self.send_json({"error": "المسار غير موجود."}, 404)
            return

        user = self.current_user()
        if not user:
            self.send_unauthorized()
            return

        payload = self.read_json_body()
        if payload is None:
            return

        message = payload.get("message")
        if not isinstance(message, str):
            self.send_json({"error": "صيغة الرسالة غير صالحة."}, 400)
            return

        conversation_id = payload.get("conversationId")
        if conversation_id is not None and (
            not isinstance(conversation_id, str)
            or not re.fullmatch(r"[a-f0-9]{32}", conversation_id)
        ):
            self.send_json({"error": "مرجع المحادثة غير صالح."}, 400)
            return
        idempotency_key = payload.get("requestId")
        if idempotency_key is not None and (
            not isinstance(idempotency_key, str)
            or not re.fullmatch(r"[a-f0-9]{32}", idempotency_key)
        ):
            self.send_json({"error": "مرجع الطلب غير صالح."}, 400)
            return
        idempotency_key = idempotency_key or secrets.token_hex(16)
        retry_request = payload.get("retryRequest") is True

        current_parts = []
        if message.strip():
            current_parts.append({"type": "text", "text": message.strip()})

        image = payload.get("image")
        attachment = payload.get("file")
        if image is not None:
            if not isinstance(image, dict):
                self.send_json({"error": "بيانات الصورة غير صالحة."}, 400)
                return
            mime_type = image.get("mimeType")
            data = image.get("data")
            if mime_type not in ALLOWED_IMAGE_TYPES or not isinstance(data, str):
                self.send_json({"error": "صيغة الصورة غير مدعومة."}, 400)
                return
            try:
                image_bytes = base64.b64decode(data, validate=True)
            except (binascii.Error, ValueError):
                self.send_json({"error": "تعذّر قراءة الصورة."}, 400)
                return
            if not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
                self.send_json(
                    {"error": "يجب ألا يتجاوز حجم الصورة 8 ميغابايت."}, 413
                )
                return
            current_parts.append(
                {
                    "type": "image",
                    "mime_type": mime_type,
                    "data": base64.b64encode(image_bytes).decode("ascii"),
                }
            )

        file_name = None
        if attachment is not None:
            if image is not None:
                self.send_json({"error": "أرفق صورة أو ملفًا واحدًا في كل مرة."}, 400)
                return
            if not isinstance(attachment, dict):
                self.send_json({"error": "بيانات الملف غير صالحة."}, 400)
                return
            file_name = attachment.get("name")
            file_mime = attachment.get("mimeType")
            file_data = attachment.get("data")
            extension = Path(file_name).suffix.lower() if isinstance(file_name, str) else ""
            if (
                not isinstance(file_name, str)
                or not file_name.strip()
                or len(file_name) > 255
                or extension not in ALLOWED_DOCUMENT_EXTENSIONS
                or file_mime not in ALLOWED_DOCUMENT_TYPES
                or not isinstance(file_data, str)
            ):
                self.send_json({"error": "نوع الملف غير مدعوم."}, 400)
                return
            try:
                document_bytes = base64.b64decode(file_data, validate=True)
            except (binascii.Error, ValueError):
                self.send_json({"error": "تعذّرت قراءة الملف."}, 400)
                return
            if not document_bytes or len(document_bytes) > MAX_DOCUMENT_BYTES:
                self.send_json({"error": "يجب ألا يتجاوز حجم الملف 8 ميغابايت."}, 413)
                return
            current_parts.append(
                {
                    "type": "document",
                    "mime_type": file_mime,
                    "data": base64.b64encode(document_bytes).decode("ascii"),
                }
            )

        if not current_parts:
            self.send_json({"error": "اكتب رسالة أو أرفق صورة أو ملفًا قبل الإرسال."}, 400)
            return

        saved_message = message.strip()
        title_message = saved_message
        if file_name:
            saved_message = "\n".join(
                part for part in (saved_message, f"مرفق ملف: {file_name}") if part
            )
            title_message = title_message or f"ملف {file_name}"

        if retry_request:
            try:
                completed_exchange = get_database().get_completed_chat_exchange(
                    user["id"], idempotency_key
                )
            except Database.error_types:
                self.send_json(
                    {"error": "تعذّر التحقق من حالة الطلب. حاول مرة أخرى."}, 500
                )
                return
            if completed_exchange:
                if (
                    completed_exchange["user_content"] != saved_message
                    or completed_exchange["image_mime"]
                    != (mime_type if image is not None else None)
                    or completed_exchange["image_data"]
                    != (image_bytes if image is not None else None)
                ):
                    self.send_json(
                        {"error": "مرجع الطلب مستخدم لرسالة مختلفة."}, 409
                    )
                    return
                self.start_sse_response()
                self.send_sse(
                    "conversation",
                    {
                        "conversationId": completed_exchange["conversation_id"],
                        "title": completed_exchange["title"],
                    },
                )
                self.send_sse(
                    "delta", {"text": completed_exchange["assistant_content"]}
                )
                self.send_sse(
                    "done",
                    {
                        "responseId": "replayed",
                        "conversationId": completed_exchange["conversation_id"],
                        "title": completed_exchange["title"],
                    },
                )
                return

        if (image is not None or attachment is not None) and not self.is_admin(user):
            allowed, quota_status = UPLOAD_QUOTA.consume(user["id"])
            if allowed:
                self._quota_charged = user["id"]
            if not allowed:
                self.send_json(
                    {
                        "error": "انتهت مرفقاتك لهذا اليوم. شاهد إعلانًا قصيرًا لتحصل على المزيد.",
                        "code": "upload_limit",
                        "quota": quota_status,
                    },
                    429,
                )
                return
        generate_image = (
            payload.get("generateImage") is True or wants_image_generation(message)
        )
        student_started = time.perf_counter()
        student_preferences = get_database().get_student_preferences(user["id"])
        if not student_preferences:
            self.send_json({"error": "تعذّر تحميل إعدادات حساب الطالب."}, 500)
            return
        student_grade = extract_student_grade(message)
        if (
            student_grade is None
            and student_preferences["grade_question_asked"]
            and student_preferences["grade"] is None
        ):
            student_grade = extract_student_grade(message, allow_short_answer=True)
        if student_grade:
            student_preferences = {
                **student_preferences,
                "grade": student_grade,
                "grade_question_asked": True,
            }
        self._record_chat_perf("student_preferences", student_started)
        ask_grade = (
            not student_preferences["grade_question_asked"]
            and student_preferences["grade"] is None
        )

        try:
            title_started = time.perf_counter()
            local_title = make_conversation_title(
                title_message, image is not None
            )
            self._record_chat_perf("title_generation", title_started)
        except (TypeError, ValueError):
            self.send_json({"error": "تعذّر تجهيز الرسالة."}, 400)
            return

        stored = {
            "id": conversation_id or secrets.token_hex(16),
            "title": local_title,
            "pending_title": local_title,
            "message_id": 1,
            "user_id": user["id"],
            "user_content": saved_message,
            "image_mime": mime_type if image is not None else None,
            "image_data": image_bytes if image is not None else None,
            "idempotency_key": idempotency_key,
            "create_conversation": conversation_id is None,
            "grade": student_grade,
            "mark_grade_question_asked": ask_grade or bool(student_grade),
        }

        model = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite").strip()
        if not model or any(
            character
            not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
            for character in model
        ):
            log_chat_diagnostic(
                "model_validation",
                "ConfigurationError",
                "GEMINI_MODEL is invalid.",
            )
            self.send_json(
                {
                    "error": (
                        "المساعد غير جاهز الآن. حاول لاحقًا، وإذا استمرت المشكلة "
                        "أخبر المعلم."
                    )
                },
                500,
            )
            return

        if (
            not generate_image
            and image is None
            and attachment is None
            and user_asks_own_grade(message)
        ):
            if student_preferences["grade"]:
                local_answer = (
                    f"صفك المسجّل عندي هو {student_preferences['grade']}."
                )
            else:
                local_answer = (
                    "ما عندي صفك محفوظ لسه. احكيلي بأي صف إنت، وبحفظه في ملفك."
                )
            local_response_id = f"local-{secrets.token_hex(16)}"
            self.start_sse_response()
            self.send_sse(
                "conversation", {"conversationId": stored["id"], "title": stored["title"]}
            )
            self.send_sse("delta", {"text": local_answer})
            self._quota_kept = True
            try:
                self.persist_chat_exchange(
                    stored,
                    local_answer,
                    local_response_id,
                )
            except Database.error_types + (RuntimeError,):
                self.send_sse(
                    "error",
                    {
                        "error": "وصل الرد لكن تعذّر حفظه في سجل المحادثة.",
                        "code": "save_failed",
                    },
                )
                return
            self.send_sse(
                "done",
                {
                    "responseId": local_response_id,
                    "conversationId": stored["id"],
                    "title": stored["title"],
                },
            )
            return

        if not generate_image and os.environ.get("GEMINI_API_KEY", "").strip():
            # افتح الاتصال فقط بعد استبعاد الردود التي لا تحتاج Gemini.
            self.start_gemini_prewarm()
        if generate_image:
            self.send_image_creation_unavailable(stored)
            return

        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            log_chat_diagnostic(
                "gemini_configuration",
                "ConfigurationError",
                "Gemini API key is not configured.",
            )
            self.send_json(
                {
                    "error": (
                        "المساعد غير متاح الآن. حاول مرة أخرى بعد قليل، "
                        "أو أخبر المعلم."
                    )
                },
                503,
            )
            return

        try:
            if conversation_id:
                context_started = time.perf_counter()
                context_rows = get_database().get_conversation_context(
                    user["id"], conversation_id
                )
                self._record_chat_perf("conversation_context", context_started)
                if not context_rows:
                    self.send_json({"error": "المحادثة غير موجودة."}, 404)
                    return
                context_messages = [dict(row) for row in context_rows]
                stored["message_id"] = max(row["id"] for row in context_messages) + 1
                stored["title"] = context_messages[-1]["conversation_title"]
                stored["pending_title"] = local_title
            else:
                context_messages = []
            previous_messages = context_messages
            system_instruction = conversation_system_instruction(
                first_reply=not any(
                    row["role"] == "assistant" for row in previous_messages
                ),
                grade=student_preferences["grade"],
                ask_grade=ask_grade,
                user_greeted=user_starts_with_greeting(message),
                asks_identity=user_asks_assistant_identity(message),
                user_message=message,
                has_previous_answer=any(
                    row["role"] == "assistant" for row in previous_messages
                ),
            )
            images_started = time.perf_counter()
            relevant_images = select_prior_images(previous_messages, message)
            selected_prior_images = select_images_that_fit(
                relevant_images, current_parts, system_instruction
            )
            if len(selected_prior_images) != len(relevant_images):
                self.send_json(
                    {
                        "error": (
                            "الصور التي اخترتها كثيرة. أرسل الصور المهمة فقط "
                            "أو قسّمها على أكثر من رسالة."
                        )
                    },
                    413,
                )
                return
            selected_images = (
                get_database().get_conversation_images(
                    user["id"],
                    stored["id"],
                    [image["id"] for image in selected_prior_images],
                )
                if selected_prior_images
                else {}
            )
            for context_message in context_messages:
                selected_image = selected_images.get(context_message["id"])
                if selected_image:
                    context_message["image_mime"] = selected_image["image_mime"]
                    context_message["image_data"] = selected_image["image_data"]
                else:
                    context_message["image_data"] = None
            self._record_chat_perf("conversation_images", images_started)
        except Database.error_types:
            self.send_json({"error": "تعذّر استرجاع سياق المحادثة من قاعدة البيانات."}, 500)
            return

        try:
            request_input = build_conversation_input(
                context_messages,
                stored["message_id"],
                message.strip(),
                current_parts,
                system_instruction,
            )
        except ValueError as error:
            self.send_json({"error": str(error)}, 413)
            return
        request_payload = {
            "model": model,
            "input": request_input,
            "system_instruction": system_instruction,
            "stream": True,
        }
        # التفكير الديناميتي الافتراضي يؤخّر أول كلمة عدة ثوانٍ؛ "low" أسرع بكثير للأسئلة المدرسية.
        # للتعديل: GEMINI_THINKING_LEVEL=minimal|low|medium|high (أو فارغة لتعطيله).
        thinking_level = os.environ.get("GEMINI_THINKING_LEVEL", "low").strip().lower()
        if thinking_level in GEMINI_THINKING_LEVELS and not ChatHandler.thinking_rejected:
            request_payload["generation_config"] = {"thinking_level": thinking_level}
        request_data = json.dumps(request_payload, ensure_ascii=False).encode("utf-8")
        if len(request_data) > MAX_GEMINI_REQUEST_BYTES:
            self.send_json(
                {
                    "error": (
                        "المحادثة طويلة جدًا لإكمال الطلب. ابدأ محادثة جديدة "
                        "أو أرسل صورًا أقل."
                    )
                },
                413,
            )
            return
        request_headers = {
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        self._record_chat_perf("pre_gemini", self._chat_perf_started)
        gemini_started = time.perf_counter()
        stored["gemini_started_at"] = gemini_started
        stream_started = False
        failure_phase = "gemini_request"
        try:
            with self.open_gemini_stream(
                request_data, request_headers, request_payload
            ) as response:
                failure_phase = "gemini_stream"
                self.start_sse_response()
                stream_started = True
                self.send_sse(
                    "conversation",
                    {
                        "conversationId": stored["id"],
                        "title": stored["title"],
                    },
                )
                completed = self.stream_gemini_response(response, stored)
                if not completed:
                    self.send_sse(
                        "error",
                        {
                            "error": (
                                "انقطع الرد قبل اكتماله. اضغط «إعادة الإرسال» "
                                "للمحاولة مرة أخرى."
                            )
                        },
                    )
                return
        except HTTPError as error:
            log_chat_diagnostic(
                "gemini_upstream_response",
                type(error).__name__,
                http.client.responses.get(
                    error.code, "Gemini returned an HTTP error."
                ),
                upstream_http_status=error.code,
            )
            if error.code == 429:
                detail = (
                    "الخادم مشغول حاليًا بسبب كثرة الطلبات. "
                    "انتظر قليلًا ثم اضغط «إعادة الإرسال»."
                )
            elif error.code in {408, 425} or error.code >= 500:
                detail = (
                    "واجه المساعد مشكلة مؤقتة. انتظر قليلًا ثم أعد الإرسال."
                )
            else:
                detail = (
                    "تعذّر على المساعد معالجة الرسالة. جرّب اختصار سؤالك "
                    "أو إعادة صياغته."
                )
            self.send_json(
                {"error": detail},
                error.code if 400 <= error.code < 600 else 502,
            )
            return
        except TimeoutError:
            log_chat_diagnostic(
                failure_phase,
                "TimeoutError",
                "Timed out while waiting for the Gemini response.",
            )
            self.send_json(
                {
                    "error": (
                        "تأخر رد المساعد. انتظر قليلًا ثم اضغط «إعادة الإرسال»."
                    )
                },
                504,
            )
            return
        except URLError:
            log_chat_diagnostic(
                "gemini_connection",
                "URLError",
                "Could not connect to the Gemini service.",
            )
            self.send_json(
                {
                    "error": (
                        "تعذّر الاتصال بالمساعد. تحقق من اتصال الإنترنت "
                        "ثم حاول مرة أخرى."
                    )
                },
                502,
            )
            return
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as error:
            log_chat_diagnostic(
                failure_phase,
                type(error).__name__,
                "Unexpected error while starting the Gemini response.",
            )
            if stream_started:
                try:
                    self.send_sse(
                        "error", {"error": "تعذّر إكمال الإجابة بسبب خطأ داخلي."}
                    )
                except (BrokenPipeError, ConnectionResetError):
                    pass
            else:
                self.send_json(
                    {
                        "error": (
                            "لم يتمكن المساعد من بدء الرد. انتظر قليلًا "
                            "ثم أعد الإرسال."
                        )
                    },
                    502,
                )
            return

    def do_PATCH(self):
        support_match = re.fullmatch(
            r"/api/admin/support-messages/([0-9]+)", self.path
        )
        if support_match:
            user = self.current_user()
            if not user:
                self.send_unauthorized()
                return
            if not self.is_admin(user):
                self.send_json(
                    {"error": "ليس لديك صلاحية لإدارة رسائل مركز المساعدة."}, 403
                )
                return
            payload = self.read_json_body()
            if payload is None:
                return
            status = payload.get("status")
            if status not in {"new", "resolved"}:
                self.send_json({"error": "حالة الرسالة غير صالحة."}, 400)
                return
            if not get_database().set_support_message_status(
                int(support_match.group(1)), status
            ):
                self.send_json({"error": "رسالة مركز المساعدة غير موجودة."}, 404)
                return
            self.send_json({"ok": True, "status": status})
            return

        match = re.fullmatch(r"/api/conversations/([a-f0-9]{32})", self.path)
        if not match:
            self.send_json({"error": "المسار غير موجود."}, 404)
            return
        user = self.current_user()
        if not user:
            self.send_unauthorized()
            return
        payload = self.read_json_body()
        if payload is None:
            return
        title = payload.get("title")
        if not isinstance(title, str) or not title.strip():
            self.send_json({"error": "اكتب عنوانًا للمحادثة."}, 400)
            return
        title = re.sub(r"\s+", " ", title.strip())
        if len(title) > MAX_TITLE_LENGTH:
            self.send_json(
                {"error": f"يجب ألا يتجاوز العنوان {MAX_TITLE_LENGTH} حرفًا."}, 400
            )
            return
        updated_title = get_database().rename_conversation(
            user["id"], match.group(1), title
        )
        if not updated_title:
            self.send_json({"error": "المحادثة غير موجودة."}, 404)
            return
        self.send_json({"ok": True, "title": updated_title})

    def do_DELETE(self):
        if self.path == "/api/admin/support-messages":
            user = self.current_user()
            if not user:
                self.send_unauthorized()
                return
            if not self.is_admin(user):
                self.send_json(
                    {"error": "ليس لديك صلاحية لحذف رسائل مركز المساعدة."}, 403
                )
                return
            delete_all = getattr(get_database(), "delete_all_support_messages", None)
            if delete_all is None:
                self.send_json(
                    {"error": "أضف الدالة delete_all_support_messages إلى database.py أولًا."},
                    501,
                )
                return
            try:
                deleted = delete_all()
            except Database.error_types:
                self.send_json({"error": "تعذّر حذف رسائل مركز المساعدة."}, 500)
                return
            self.send_json({"ok": True, "deleted": deleted if isinstance(deleted, int) else None})
            return

        admin_match = re.fullmatch(r"/api/admin/users/([a-f0-9]{32})", self.path)
        if admin_match:
            user = self.current_user()
            if not user:
                self.send_unauthorized()
                return
            if not self.is_admin(user):
                self.send_json({"error": "ليس لديك صلاحية لحذف المستخدمين."}, 403)
                return
            target_user_id = admin_match.group(1)
            if target_user_id == user["id"]:
                self.send_json({"error": "لا يمكنك حذف حساب الأدمن من لوحة التحكم."}, 400)
                return
            primary_admin_email = os.environ.get(
                "ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL
            ).strip()
            result = get_database().delete_user(
                target_user_id,
                primary_admin_email,
                self.is_primary_admin(user),
            )
            if result == "primary_admin":
                self.send_json(
                    {"error": "لا يمكن حذف حساب الأدمن الأساسي."}, 400
                )
                return
            if result == "target_admin":
                self.send_json(
                    {"error": "الأدمن غير الأساسي لا يمكنه حذف حساب أدمن آخر."},
                    403,
                )
                return
            if result == "not_found":
                self.send_json({"error": "المستخدم غير موجود."}, 404)
                return
            self.send_response(204)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return

        match = re.fullmatch(r"/api/conversations/([a-f0-9]{32})", self.path)
        if not match:
            self.send_json({"error": "المسار غير موجود."}, 404)
            return
        user = self.current_user()
        if not user:
            self.send_unauthorized()
            return
        if not get_database().delete_conversation(user["id"], match.group(1)):
            self.send_json({"error": "المحادثة غير موجودة."}, 404)
            return
        self.send_response(204)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def password_and_remember(self, payload):
        password = payload.get("password")
        if not isinstance(password, str) or not password or len(password) > 128:
            self.send_json({"error": "كلمة المرور غير صالحة."}, 400)
            return None
        try:
            password.encode("utf-8")
        except UnicodeEncodeError:
            self.send_json({"error": "استخدم أحرفًا صالحة في كلمة المرور."}, 400)
            return None
        remember = payload.get("remember", True)
        if not isinstance(remember, bool):
            self.send_json({"error": "إعداد تذكّر الجهاز غير صالح."}, 400)
            return None
        return password, remember

    def login_credentials(self):
        """يقبل الاسم الرباعي (للطلاب) أو البريد الإلكتروني (للأدمن)."""
        payload = self.read_json_body()
        if payload is None:
            return None
        identifier = payload.get("identifier", payload.get("email"))
        if not isinstance(identifier, str) or not identifier.strip():
            self.send_json({"error": "اكتب اسمك الرباعي وكلمة المرور."}, 400)
            return None
        identifier = identifier.strip()
        if "@" in identifier:
            email = identifier.casefold()
            if len(email) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
                self.send_json({"error": "أدخل عنوان بريد إلكتروني صالحًا."}, 400)
                return None
            is_student = False
        else:
            if len(identifier) > 120 or not re.fullmatch(
                r"[\u0621-\u064a ]+", normalize_arabic(identifier)
            ):
                self.send_json({"error": "اكتب اسمك الرباعي بالأحرف العربية كما سجّلته."}, 400)
                return None
            tokens = name_tokens(identifier)
            if len(tokens) < 2:
                self.send_json({"error": "اكتب اسمك الرباعي كاملًا كما سجّلته."}, 400)
                return None
            email = student_email(tokens)
            is_student = True
        extra = self.password_and_remember(payload)
        if extra is None:
            return None
        password, remember = extra
        return email, password, remember, is_student

    def send_authenticated_user(self, user, remember):
        lifetime = 365 * 24 * 60 * 60 if remember else 24 * 60 * 60
        token = get_database().create_session(user["id"], lifetime)
        self.send_json(
            {
                "user": decorate_user(user),
                "isAdmin": self.is_admin(user),
                "isPrimaryAdmin": self.is_primary_admin(user),
            },
            headers=[
                (
                    "Set-Cookie",
                    self.session_cookie(token, max_age=lifetime),
                )
            ],
        )

    def is_admin(self, user):
        admin_email = os.environ.get("ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL).strip()
        return (
            self.is_primary_admin(user)
        ) or get_database().is_admin(user["id"])

    def is_primary_admin(self, user):
        admin_email = os.environ.get("ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL).strip()
        return bool(admin_email) and user["email"].casefold() == admin_email.casefold()

    def admin_set_user_role(self, target_user_id):
        user = self.current_user()
        if not user:
            self.send_unauthorized()
            return
        if not self.is_admin(user):
            self.send_json(
                {"error": "ليس لديك صلاحية لإدارة صلاحيات المستخدمين."}, 403
            )
            return
        payload = self.read_json_body()
        if payload is None:
            return
        is_admin = payload.get("isAdmin")
        if not isinstance(is_admin, bool):
            self.send_json({"error": "قيمة صلاحية الأدمن غير صالحة."}, 400)
            return
        primary_admin_email = os.environ.get(
            "ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL
        ).strip()
        result = get_database().set_user_admin(
            target_user_id,
            is_admin,
            user["id"],
            primary_admin_email,
        )
        if result == "not_found":
            self.send_json({"error": "المستخدم غير موجود."}, 404)
            return
        if result == "self":
            self.send_json(
                {"error": "لا يمكنك تغيير صلاحيات حسابك بنفسك."}, 400
            )
            return
        if result == "primary_admin":
            self.send_json(
                {"error": "لا يمكن تغيير صلاحية الأدمن الأساسي."}, 400
            )
            return
        self.send_json({"ok": True, "isAdmin": is_admin})

    def register_account(self):
        payload = self.read_json_body()
        if payload is None:
            return
        full_name, error = validate_full_name(payload.get("fullName"))
        if error:
            self.send_json({"error": error}, 400)
            return
        grade_key = str(payload.get("grade", ""))
        if grade_key not in GRADE_CHOICES:
            self.send_json({"error": "اختر صفك الدراسي."}, 400)
            return
        phone, error = normalize_phone_number(payload.get("phone"))
        if error:
            self.send_json({"error": error}, 400)
            return
        extra = self.password_and_remember(payload)
        if extra is None:
            return
        password, remember = extra
        if len(password) < PASSWORD_MIN_LENGTH:
            self.send_json(
                {"error": f"أنشئ كلمة مرور من {PASSWORD_MIN_LENGTH} أحرف على الأقل."}, 400
            )
            return
        email = student_email(name_tokens(full_name))
        try:
            user = get_database().register_user(email, password, phone)
        except Database.integrity_error_types:
            self.send_json(
                {"error": "هذا الاسم مسجّل مسبقًا. سجّل الدخول بدلًا من إنشاء حساب جديد."},
                409,
            )
            return
        USER_PROFILES.set(user["id"], full_name, grade_key)
        try:
            get_database().update_student_grade(
                user["id"], GRADE_CHOICES[grade_key]["stored"]
            )
        except Exception as error:
            print(f"[REGISTER] تعذّر حفظ الصف في قاعدة البيانات: {error}", flush=True)
        GRADE_DIRECTORY.forget(user["id"])
        self.send_authenticated_user(user, remember)

    def login_account(self):
        values = self.login_credentials()
        if not values:
            return
        email, password, remember, is_student = values
        if not get_database().user_exists(email):
            self.send_json(
                {
                    "error": (
                        "لم يتم العثور على حساب بهذا الاسم. تأكد من كتابة اسمك الرباعي "
                        "كما سجّلته، أو أنشئ حسابًا جديدًا للمتابعة."
                        if is_student
                        else "لم يتم العثور على حساب بهذا البريد الإلكتروني."
                    )
                },
                404,
            )
            return
        user = get_database().login_user(email, password)
        if not user:
            self.send_json(
                {
                    "error": (
                        "الاسم الرباعي أو كلمة المرور غير صحيحة."
                        if is_student
                        else "البريد الإلكتروني أو كلمة المرور غير صحيحة."
                    )
                },
                401,
            )
            return
        self.send_authenticated_user(user, remember)

    def forgot_password(self):
        payload = self.read_json_body()
        if payload is None:
            return
        email = payload.get("email")
        if not isinstance(email, str):
            self.send_json({"error": "أدخل بريدًا إلكترونيًا صالحًا."}, 400)
            return
        email = email.strip().casefold()
        if (
            len(email) > 254
            or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)
        ):
            self.send_json({"error": "أدخل بريدًا إلكترونيًا صالحًا."}, 400)
            return

        code = f"{secrets.randbelow(1_000_000):06d}"
        code_hash = Database.hash_password(code)
        status, account_email = get_database().issue_password_reset(
            email, code_hash, int(time.time())
        )
        if status == "issued" and account_email:
            try:
                send_password_reset_email(account_email, code)
            except (OSError, RuntimeError, smtplib.SMTPException) as error:
                get_database().cancel_password_reset(email, code_hash)
                print(
                    "Password reset email could not be sent: "
                    f"{type(error).__name__}"
                )
                self.send_json(
                    {"error": "تعذّر إرسال رمز التحقق حاليًا. حاول مرة أخرى لاحقًا."},
                    503,
                )
                return

        self.send_json(
            {
                "ok": True,
                "message": (
                    "إذا كان البريد مرتبطًا بحساب، فسيصلك رمز تحقق صالح لمدة "
                    "10 دقائق. افحص بريدك الوارد ومجلد الرسائل غير المرغوب فيها."
                ),
            }
        )

    def reset_password(self):
        payload = self.read_json_body()
        if payload is None:
            return
        email = payload.get("email")
        code = payload.get("code")
        new_password = payload.get("newPassword")
        if not all(isinstance(value, str) for value in (email, code, new_password)):
            self.send_json(
                {"error": "أدخل البريد الإلكتروني ورمز التحقق وكلمة المرور الجديدة."},
                400,
            )
            return

        email = email.strip().casefold()
        if (
            len(email) > 254
            or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)
        ):
            self.send_json({"error": "أدخل بريدًا إلكترونيًا صالحًا."}, 400)
            return
        if not re.fullmatch(r"[0-9]{6}", code):
            self.send_json({"error": "رمز التحقق يجب أن يتكون من 6 أرقام."}, 400)
            return
        if not new_password or len(new_password) > 128:
            self.send_json({"error": "كلمة المرور الجديدة غير صالحة."}, 400)
            return
        try:
            new_password.encode("utf-8")
        except UnicodeEncodeError:
            self.send_json({"error": "استخدم أحرفًا صالحة في كلمة المرور."}, 400)
            return
        if len(new_password) < 10:
            self.send_json(
                {"error": "أنشئ كلمة مرور جديدة من 10 أحرف على الأقل."}, 400
            )
            return

        result = get_database().reset_password(
            email, code, new_password, int(time.time())
        )
        if result == "success":
            self.send_json({"ok": True})
            return
        errors = {
            "expired": "انتهت صلاحية الرمز. اطلب رمزًا جديدًا.",
            "locked": "تم إيقاف الرمز بعد محاولات كثيرة. اطلب رمزًا جديدًا.",
            "invalid": "رمز التحقق غير صحيح أو انتهت صلاحيته.",
        }
        self.send_json({"error": errors[result]}, 400)

    def change_password(self):
        user = self.current_user()
        if not user:
            self.send_unauthorized()
            return

        payload = self.read_json_body()
        if payload is None:
            return
        current_password = payload.get("currentPassword")
        new_password = payload.get("newPassword")
        confirm_password = payload.get("confirmPassword")
        if (
            not isinstance(current_password, str)
            or not isinstance(new_password, str)
            or not isinstance(confirm_password, str)
        ):
            self.send_json(
                {"error": "أدخل كلمة المرور الحالية والجديدة وأعد تأكيدها."}, 400
            )
            return
        if (
            not current_password
            or len(current_password) > 128
            or not new_password
            or len(new_password) > 128
            or not confirm_password
            or len(confirm_password) > 128
        ):
            self.send_json({"error": "كلمة المرور غير صالحة."}, 400)
            return
        try:
            current_password.encode("utf-8")
            new_password.encode("utf-8")
        except UnicodeEncodeError:
            self.send_json({"error": "استخدم أحرفًا صالحة في كلمة المرور."}, 400)
            return
        if new_password != confirm_password:
            self.send_json(
                {"error": "كلمتا المرور الجديدتان غير متطابقتين."}, 400
            )
            return
        if len(new_password) < 10:
            self.send_json(
                {"error": "أنشئ كلمة مرور جديدة من 10 أحرف على الأقل."}, 400
            )
            return
        if new_password == current_password:
            self.send_json(
                {"error": "اختر كلمة مرور جديدة مختلفة عن الحالية."}, 400
            )
            return
        if not get_database().change_password(
            user["id"],
            current_password,
            new_password,
            self.session_token(),
        ):
            self.send_json({"error": "كلمة المرور الحالية غير صحيحة."}, 400)
            return
        self.send_json({"ok": True})

    def submit_support_message(self):
        user = self.current_user()
        payload = self.read_json_body()
        if payload is None:
            return
        category = payload.get("category")
        content = payload.get("content")
        if category not in {"message", "complaint"}:
            self.send_json({"error": "اختر نوعًا صالحًا للرسالة."}, 400)
            return
        if not isinstance(content, str) or not content.strip():
            self.send_json({"error": "اكتب رسالتك قبل الإرسال."}, 400)
            return
        content = content.strip()
        if len(content) > 3000:
            self.send_json(
                {"error": "يجب ألا تتجاوز الرسالة 3000 حرف."}, 400
            )
            return
        if not user:
            name = payload.get("name")
            email = payload.get("email")
            if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
                self.send_json({"error": "اكتب اسمًا صالحًا للتواصل."}, 400)
                return
            if (
                not isinstance(email, str)
                or len(email.strip()) > 254
                or not re.fullmatch(
                    r"[^@\s]+@[^@\s]+\.[^@\s]+", email.strip()
                )
            ):
                self.send_json({"error": "أدخل بريدًا إلكترونيًا صالحًا."}, 400)
                return
            user = {
                "id": None,
                "name": name.strip(),
                "email": email.strip().casefold(),
            }
        try:
            message_id = get_database().create_support_message(
                user, category, content
            )
        except Database.error_types:
            self.send_json(
                {"error": "تعذّر حفظ رسالتك. حاول مرة أخرى."}, 500
            )
            return
        self.send_json({"ok": True, "id": message_id}, 201)

    def admin_set_user_password(self, target_user_id):
        user = self.current_user()
        if not user:
            self.send_unauthorized()
            return
        if not self.is_admin(user):
            self.send_json(
                {"error": "ليس لديك صلاحية لتغيير كلمات مرور المستخدمين."}, 403
            )
            return
        if target_user_id == user["id"]:
            self.send_json(
                {"error": "استخدم إعدادات حسابك لتغيير كلمة مرورك."}, 400
            )
            return

        payload = self.read_json_body()
        if payload is None:
            return
        new_password = payload.get("newPassword")
        if not isinstance(new_password, str):
            self.send_json({"error": "أدخل كلمة مرور جديدة."}, 400)
            return
        if not new_password or len(new_password) > 128:
            self.send_json({"error": "كلمة المرور الجديدة غير صالحة."}, 400)
            return
        try:
            new_password.encode("utf-8")
        except UnicodeEncodeError:
            self.send_json({"error": "استخدم أحرفًا صالحة في كلمة المرور."}, 400)
            return
        if len(new_password) < 10:
            self.send_json(
                {"error": "أنشئ كلمة مرور من 10 أحرف على الأقل."}, 400
            )
            return
        primary_admin_email = os.environ.get(
            "ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL
        ).strip()
        result = get_database().admin_set_password(
            target_user_id,
            new_password,
            primary_admin_email,
            self.is_primary_admin(user),
        )
        if result == "target_admin":
            self.send_json(
                {
                    "error": "الأدمن غير الأساسي لا يمكنه تغيير كلمة مرور أدمن آخر."
                },
                403,
            )
            return
        if result == "not_found":
            self.send_json({"error": "المستخدم غير موجود."}, 404)
            return
        self.send_json({"ok": True})

    def session_token(self):
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get("Cookie", ""))
        except CookieError:
            return ""
        morsel = cookies.get("school_assistant_session")
        return morsel.value if morsel else ""

    def session_cookie(self, token, max_age):
        cookie = (
            f"school_assistant_session={token}; Path=/; HttpOnly; "
            f"SameSite=Lax; Max-Age={max_age}"
        )
        if os.environ.get("COOKIE_SECURE", "").strip().lower() in {"1", "true", "yes"}:
            cookie += "; Secure"
        return cookie

    def quota_for(self, user):
        if self.is_admin(user):
            return {"unlimited": True}
        return UPLOAD_QUOTA.status(user["id"])

    def save_preferences(self):
        user = self.current_user()
        if not user:
            self.send_unauthorized()
            return
        payload = self.read_json_body()
        if payload is None:
            return
        theme = payload.get("theme")
        if theme not in ALLOWED_THEMES:
            self.send_json({"error": "المظهر غير صالح."}, 400)
            return
        try:
            preferences = USER_PREFERENCES.set_theme(user["id"], theme)
        except OSError:
            self.send_json({"error": "تعذّر حفظ المظهر. حاول مرة أخرى."}, 500)
            return
        self.send_json({"preferences": preferences})

    def change_account_name(self):
        user = self.current_user()
        if not user:
            self.send_unauthorized()
            return
        if not student_name_from_email(user.get("email", "")):
            self.send_json(
                {"error": "تغيير الاسم متاح لحسابات الطلاب فقط."}, 403
            )
            return
        payload = self.read_json_body()
        if payload is None:
            return
        full_name, error = validate_account_name(payload.get("fullName"))
        if error:
            self.send_json({"error": error}, 400)
            return

        email = student_email(name_tokens(full_name))
        try:
            result = get_database().update_student_account_name(
                user["id"], email, full_name
            )
        except Database.integrity_error_types:
            result = "duplicate"
        except Database.error_types:
            self.send_json({"error": "تعذّر حفظ الاسم الجديد."}, 500)
            return

        if result == "duplicate":
            self.send_json(
                {"error": "هذا الاسم مستخدم لحساب آخر. اختر اسمًا مختلفًا."}, 409
            )
            return
        if result == "not_found":
            self.send_json({"error": "الحساب غير موجود."}, 404)
            return

        saved_profile = USER_PROFILES.get(user["id"]) or {}
        USER_PROFILES.set(user["id"], full_name, saved_profile.get("grade", ""))
        self.send_json({"ok": True, "fullName": full_name})

    def change_account_phone(self):
        user = self.current_user()
        if not user:
            self.send_unauthorized()
            return
        if not student_name_from_email(user.get("email", "")):
            self.send_json(
                {"error": "تغيير رقم الهاتف متاح لحسابات الطلاب فقط."}, 403
            )
            return
        payload = self.read_json_body()
        if payload is None:
            return
        phone, error = normalize_phone_number(payload.get("phone"))
        if error:
            self.send_json({"error": error}, 400)
            return

        try:
            result = get_database().update_student_account_phone(
                user["id"], phone
            )
        except Database.error_types:
            self.send_json({"error": "تعذّر حفظ رقم الهاتف."}, 500)
            return
        if result == "not_found":
            self.send_json({"error": "الحساب غير موجود."}, 404)
            return
        self.send_json({"ok": True, "phone": phone})

    def account_profile(self, user=None):
        if user is None:
            user = self.current_user()
        if not user:
            self.send_unauthorized()
            return
        if not student_name_from_email(user.get("email", "")):
            self.send_json(
                {"error": "إعدادات الاسم والصف والهاتف متاحة لحسابات الطلاب فقط."},
                403,
            )
            return

        if self.command == "GET":
            profile = get_database().get_student_account_profile(user["id"])
            if not profile:
                self.send_json({"error": "الحساب غير موجود."}, 404)
                return
            saved_profile = USER_PROFILES.get(user["id"]) or {}
            grade_key = saved_profile.get("grade")
            if grade_key not in GRADE_CHOICES:
                grade_key = STORED_TO_GRADE_KEY.get(profile["grade"])
            self.send_json(
                {
                    "profile": {
                        "fullName": saved_profile.get("fullName")
                        or student_name_from_email(profile["email"]),
                        "phone": profile["phone"] or "",
                        "grade": grade_key or "",
                    }
                }
            )
            return

        payload = self.read_json_body()
        if payload is None:
            return
        full_name, error = validate_full_name(payload.get("fullName"))
        if error:
            self.send_json({"error": error}, 400)
            return
        grade_key = str(payload.get("grade", ""))
        if grade_key not in GRADE_CHOICES:
            self.send_json({"error": "اختر صفك الدراسي."}, 400)
            return
        phone, error = normalize_phone_number(payload.get("phone"))
        if error:
            self.send_json({"error": error}, 400)
            return

        email = student_email(name_tokens(full_name))
        try:
            result = get_database().update_student_account_profile(
                user["id"],
                email,
                full_name,
                phone,
                GRADE_CHOICES[grade_key]["stored"],
            )
        except Database.integrity_error_types:
            result = "duplicate"
        except Database.error_types:
            self.send_json({"error": "تعذّر حفظ بيانات الحساب."}, 500)
            return

        if result == "duplicate":
            self.send_json(
                {"error": "هذا الاسم مستخدم لحساب آخر. اختر اسمًا مختلفًا."}, 409
            )
            return
        if result == "not_found":
            self.send_json({"error": "الحساب غير موجود."}, 404)
            return

        USER_PROFILES.set(user["id"], full_name, grade_key)
        GRADE_DIRECTORY.forget(user["id"])
        self.send_json(
            {
                "ok": True,
                "profile": {"fullName": full_name, "phone": phone, "grade": grade_key},
                "email": email,
            }
        )

    def current_user(self):
        return get_database().get_session_user(self.session_token())

    def send_unauthorized(self):
        self.send_json({"error": "انتهت جلسة الدخول. سجّل الدخول مرة أخرى."}, 401)

    def read_json_body(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_json({"error": "حجم الطلب غير صالح."}, 400)
            return None
        if length <= 0 or length > MAX_REQUEST_BYTES:
            self.send_json(
                {"error": "حجم الطلب غير صالح أو يتجاوز الحد المسموح."}, 413
            )
            return None
        try:
            payload = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.send_json({"error": "تعذّرت قراءة بيانات الرسالة."}, 400)
            return None
        if not isinstance(payload, dict):
            self.send_json({"error": "صيغة الرسالة غير صالحة."}, 400)
            return None
        return payload

    def send_sse(self, event, payload):
        body = json.dumps(payload, ensure_ascii=False)
        self.wfile.write(f"event: {event}\ndata: {body}\n\n".encode("utf-8"))
        self.wfile.flush()

    def start_sse_response(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        self.close_connection = True

    def persist_chat_exchange(
        self,
        conversation,
        answer,
        response_id,
    ):
        save_started = time.perf_counter()
        try:
            for attempt in range(2):
                try:
                    result = get_database().complete_chat_exchange(
                        conversation["user_id"],
                        conversation["id"],
                        conversation.get("pending_title", conversation["title"]),
                        conversation["user_content"],
                        conversation["image_mime"],
                        conversation["image_data"],
                        answer,
                        response_id,
                        conversation["idempotency_key"],
                        grade=conversation["grade"],
                        grade_question_asked=conversation[
                            "mark_grade_question_asked"
                        ],
                        create_conversation=conversation[
                            "create_conversation"
                        ],
                    )
                    if not result:
                        raise RuntimeError("Conversation disappeared before save.")
                    if (
                        result.get("duplicate")
                        and result["assistant_content"] != answer
                    ):
                        raise RuntimeError(
                            "An idempotent exchange already contains another answer."
                        )
                    conversation["title"] = result["title"]
                    return result
                except Database.error_types as error:
                    if attempt == 0:
                        time.sleep(0.05)
                        continue
                    print(
                        "[CHAT_SAVE] attempts=2 "
                        f"error={type(error).__name__}",
                        flush=True,
                    )
                    raise
        except Database.error_types:
            raise
        except Exception as error:
            print(
                "[CHAT_SAVE] attempts=1 "
                f"error={type(error).__name__}",
                flush=True,
            )
            raise RuntimeError("Could not persist completed chat exchange.") from error
        finally:
            self._record_chat_perf("save_exchange", save_started)

    def send_image_creation_unavailable(self, conversation):
        answer = (
            "ما بقدر أنشئ صور، لأني مساعد نصّي. "
            "بقدر أساعدك بكتابة وصف للصورة أو تحليل صورة تبعثها."
        )
        response_id = f"local-{secrets.token_hex(16)}"
        self.start_sse_response()
        self.send_sse(
            "conversation",
            {
                "conversationId": conversation["id"],
                "title": conversation["title"],
            },
        )
        self.send_sse("delta", {"text": answer})
        self._quota_kept = True
        try:
            self.persist_chat_exchange(
                conversation,
                answer,
                response_id,
            )
        except Database.error_types + (RuntimeError,):
            self.send_sse(
                "error",
                {
                    "error": "وصل الرد لكن تعذّر حفظه في سجل المحادثة.",
                    "code": "save_failed",
                },
            )
            return
        self.send_sse(
            "done",
            {
                "responseId": response_id,
                "conversationId": conversation["id"],
                "title": conversation["title"],
            },
        )

    def update_ai_title(self, conversation, answer):
        if not conversation.get("title_needs_ai"):
            return conversation["title"]
        try:
            proposed_title = generate_conversation_title(
                conversation["title_source"], answer
            )
        except RuntimeError as error:
            print(f"تعذّر إنشاء عنوان المحادثة بالذكاء الاصطناعي: {error}")
            conversation["title_warning"] = (
                "تعذّر إنشاء عنوان للمحادثة تلقائيًا؛ يمكنك تغييره من سجل المحادثات."
            )
            return conversation["title"]
        title = get_database().set_conversation_title(
            conversation["user_id"], conversation["id"], proposed_title
        )
        if not title:
            raise Database.integrity_error_types[0](
                "conversation disappeared before title update"
            )
        conversation["title"] = title
        conversation["title_needs_ai"] = False
        return title

    def gemini_connection_class(self):
        scheme = urlsplit(API_URL).scheme
        return (
            http.client.HTTPSConnection
            if scheme == "https"
            else http.client.HTTPConnection
        )

    def start_gemini_prewarm(self):
        netloc = urlsplit(API_URL).netloc
        connection = self.gemini_connection_class()(netloc, timeout=90)

        def connect():
            try:
                connection.connect()
            except Exception:
                # عند الفشل يعيد http.client الاتصال تلقائيًا عند إرسال الطلب.
                pass

        thread = threading.Thread(target=connect, daemon=True)
        thread.start()
        self._gemini_prewarm = (connection, thread)

    def close_gemini_prewarm(self):
        prewarm = getattr(self, "_gemini_prewarm", None)
        self._gemini_prewarm = None
        if prewarm:
            connection, thread = prewarm
            thread.join(timeout=1)
            connection.close()

    def take_gemini_connection(self):
        prewarm = getattr(self, "_gemini_prewarm", None)
        self._gemini_prewarm = None
        if prewarm:
            connection, thread = prewarm
            thread.join(timeout=10)
            if not thread.is_alive():
                return connection
            connection.close()
        return self.gemini_connection_class()(urlsplit(API_URL).netloc, timeout=90)

    def open_gemini_stream(self, request_data, request_headers, request_payload=None):
        parts = urlsplit(API_URL)
        path = parts.path + (f"?{parts.query}" if parts.query else "")
        for attempt in (0, 1):
            connection = self.take_gemini_connection()
            try:
                connection.request(
                    "POST", path, body=request_data, headers=request_headers
                )
                response = connection.getresponse()
            except TimeoutError:
                connection.close()
                raise
            except (http.client.HTTPException, OSError) as error:
                connection.close()
                raise URLError(error) from error
            if response.status < 400:
                if attempt == 1:
                    ChatHandler.thinking_rejected = True
                return GeminiStream(connection, response)
            error_body = response.read()
            connection.close()
            if (
                attempt == 0
                and response.status == 400
                and request_payload
                and "generation_config" in request_payload
            ):
                # النموذج رفض إعداد التفكير: نعيد المحاولة مرة واحدة بدونه.
                print("[PERF] رفض Gemini thinking_level؛ إعادة المحاولة بدونه", flush=True)
                request_payload = {
                    key: value
                    for key, value in request_payload.items()
                    if key != "generation_config"
                }
                request_data = json.dumps(
                    request_payload, ensure_ascii=False
                ).encode("utf-8")
                continue
            raise HTTPError(
                API_URL,
                response.status,
                response.reason,
                response.msg,
                io.BytesIO(error_body),
            )

    def stream_gemini_response(self, response, conversation):
        event_name = ""
        data_lines = []
        answer_started = False
        completed = False
        answer_parts = []

        def dispatch_event():
            nonlocal answer_started, completed
            if not data_lines:
                return
            try:
                event_data = json.loads("\n".join(data_lines))
            except (json.JSONDecodeError, UnicodeDecodeError):
                self.send_sse(
                    "error",
                    {"error": "وصل رد غير واضح من المساعد. أعد إرسال سؤالك."},
                )
                completed = True
                return

            if not isinstance(event_data, dict):
                self.send_sse(
                    "error",
                    {"error": "وصل رد غير واضح من المساعد. أعد إرسال سؤالك."},
                )
                completed = True
                return

            event_type = event_data.get("event_type", event_name)
            if event_type == "step.delta":
                delta = event_data.get("delta")
                text = delta.get("text") if isinstance(delta, dict) else None
                if isinstance(text, str) and text:
                    if not answer_started:
                        self._record_chat_perf(
                            "gemini_first_byte",
                            conversation.get("gemini_started_at", time.perf_counter()),
                        )
                    self.send_sse("delta", {"text": text})
                    answer_parts.append(text)
                    answer_started = True
                    self._quota_kept = True
            elif event_type == "interaction.completed":
                self._record_chat_perf(
                    "gemini_total",
                    conversation.get("gemini_started_at", time.perf_counter()),
                )
                interaction = event_data.get("interaction")
                response_id = (
                    interaction.get("id") if isinstance(interaction, dict) else None
                )
                if not answer_started:
                    self.send_sse(
                        "error", {"error": "لم يصل رد واضح. أعد إرسال سؤالك."}
                    )
                elif not isinstance(response_id, str) or not response_id:
                    self.send_sse(
                        "error",
                        {
                            "error": (
                                "واجه المساعد مشكلة مؤقتة. انتظر قليلًا "
                                "ثم أعد الإرسال."
                            )
                        },
                    )
                else:
                    try:
                        self.persist_chat_exchange(
                            conversation,
                            "".join(answer_parts),
                            response_id,
                        )
                    except Database.error_types + (RuntimeError,):
                        self.send_sse(
                            "error",
                            {
                                "error": "وصل الرد لكن تعذّر حفظه في سجل المحادثة.",
                                "code": "save_failed",
                            },
                        )
                    else:
                        done_payload = {
                            "responseId": response_id,
                            "conversationId": conversation["id"],
                            "title": conversation["title"],
                        }
                        self.send_sse("done", done_payload)
                completed = True
            elif event_type in {"interaction.failed", "error"}:
                self.send_sse(
                    "error",
                    {
                        "error": (
                            "تعذّر إكمال الإجابة الآن. انتظر قليلًا ثم "
                            "اضغط «إعادة الإرسال»."
                        )
                    },
                )
                completed = True

        while not completed:
            try:
                raw_line = response.readline()
            except TimeoutError:
                self.send_sse(
                    "error",
                    {
                        "error": (
                            "تأخر رد المساعد. انتظر قليلًا ثم اضغط "
                            "«إعادة الإرسال»."
                        )
                    },
                )
                return True
            except (URLError, OSError):
                self.send_sse(
                    "error",
                    {
                        "error": (
                            "انقطع الاتصال بالمساعد. تحقق من اتصال الإنترنت "
                            "ثم اضغط «إعادة الإرسال»."
                        )
                    },
                )
                return True
            if not raw_line:
                if data_lines:
                    dispatch_event()
                break
            try:
                line = raw_line.decode("utf-8").rstrip("\r\n")
            except UnicodeDecodeError:
                self.send_sse(
                    "error",
                    {"error": "انقطع الرد قبل اكتماله. اضغط «إعادة الإرسال»."},
                )
                return True

            if not line:
                dispatch_event()
                event_name = ""
                data_lines = []
            elif line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
            elif line.startswith(":"):
                continue

        return completed

    def send_json(self, payload, status=200, headers=()):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        print(f"{self.client_address[0]} - {format % args}")


def send_password_reset_email(recipient, code):
    host = os.environ.get("SMTP_HOST", "").strip()
    sender = os.environ.get("SMTP_FROM", "").strip()
    username = os.environ.get("SMTP_USERNAME", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "")
    try:
        port = int(os.environ.get("SMTP_PORT", "587"))
    except ValueError as error:
        raise RuntimeError("SMTP_PORT must be a valid port number.") from error
    if not host or not sender or not 1 <= port <= 65535:
        raise RuntimeError("SMTP_HOST, SMTP_FROM, and a valid SMTP_PORT are required.")
    if bool(username) != bool(password):
        raise RuntimeError("SMTP_USERNAME and SMTP_PASSWORD must be set together.")
    if "\r" in sender or "\n" in sender or parseaddr(sender)[1] != sender:
        raise RuntimeError("SMTP_FROM must be a valid email address.")

    message = EmailMessage()
    message["Subject"] = "رمز استعادة كلمة المرور - فهيم"
    message["From"] = sender
    message["To"] = recipient
    message.set_content(
        "وصلنا طلب لإعادة تعيين كلمة مرور حسابك في فهيم.\n\n"
        f"رمز التحقق: {code}\n\n"
        "الرمز صالح لمدة 10 دقائق، ويمكن استخدامه مرة واحدة. "
        "إذا لم تطلب إعادة التعيين، فتجاهل هذه الرسالة."
    )

    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=15, context=context) as smtp:
            if username:
                smtp.login(username, password)
            smtp.send_message(message)
        return

    with smtplib.SMTP(host, port, timeout=15) as smtp:
        smtp.ehlo()
        smtp.starttls(context=context)
        smtp.ehlo()
        if username:
            smtp.login(username, password)
        smtp.send_message(message)


def main():
    load_local_env()
    if not os.environ.get("DATABASE_URL", "").strip():
        raise SystemExit("Set DATABASE_URL to a PostgreSQL connection URL in .env.")
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), ChatHandler)
    print(f"AI Chat يعمل على http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nتم إيقاف الخادم.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()