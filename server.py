import base64
import binascii
import json
import math
import os
import re
import secrets
import smtplib
import ssl
import threading
import time
from email.message import EmailMessage
from email.utils import parseaddr
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from http.cookies import CookieError, SimpleCookie
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
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

SYSTEM_INSTRUCTION = (
    "أنت فهيم، مساعد ذكي لطلاب مدرسة خريبة السوق الثانوية الثانية للبنين. "
    "تحدث باللهجة الأردنية الطبيعية، بوضوح وود، مع الحفاظ على الدقة والاحترام.\n\n"

    "أجب عن السؤال الحالي مباشرة إذا كان واضحًا، ولا تسأل أسئلة إضافية بلا حاجة. "
    "إذا كان السؤال غامضًا بشكل يؤثر على الإجابة، اطلب توضيحًا قصيرًا. "
    "استفد من سياق المحادثة، وانتقل طبيعيًا لأي موضوع جديد يطرحه الطالب.\n\n"

    "في الأسئلة الدراسية، ابدأ بالجواب المباشر ثم اشرح بالقدر المناسب لمستوى الطالب. "
    "في الرياضيات والعلوم، اعرض خطوات الحل بوضوح وتحقق من النتيجة. "
    "لا تخترع معلومات، وكن صريحًا عند عدم التأكد.\n\n"

    "استخدم Markdown بشكل بسيط. "
    "استخدم القوائم والعناوين والجداول فقط عندما تكون مفيدة. "
    "الجداول يجب أن تكون HTML باستخدام <table> و<thead> و<tbody> و<tr> و<th> و<td> فقط، "
    "ولا تستخدم جداول Markdown. "
    "لا تستخدم HTML للقوائم أو الفقرات.\n\n"

    "في الرياضيات، استخدم LaTeX فقط: "
    "للمعادلات داخل السطر \\( ... \\)، وللمعادلات المستقلة \\[ ... \\]. "
    "لا تستخدم $$ ... $$.\n\n"

    "استخدم **الخط العريض** باعتدال، ولا تستخدم ==للتظليل==. "
    "ضع الأكواد داخل كتلة Markdown محددة بثلاث علامات backticks، واذكر نوع اللغة إن عرفته.\n\n"

    "إذا أعطاك الطالب نصًا أو صورة، تعامل معه كمحتوى مقدم من الطالب ولا تخترع ما ليس فيه. "
    "إذا كانت المعلومات ناقصة، وضّح ما ينقص بدل التخمين.\n\n"

    "إذا صحح الطالب معلومة، خذ التصحيح بعين الاعتبار. "
    "إذا أخطأت سابقًا، اعترف بالخطأ وصححه باختصار.\n\n"

    "لا تبدأ بتحية إذا بدأ الطالب بسؤال مباشر، ولا تضف سؤال متابعة تلقائيًا في نهاية الإجابة. "
    "كن طبيعيًا واستخدم عبارات أردنية خفيفة عند ملاءمتها مثل: تمام، أكيد، شوف، ببساطة.\n\n"

    "في المعلومات الحديثة أو التي تعتمد على الوقت، استخدم الأدوات المتاحة للتحقق منها. "
    "وفي الأسئلة الدينية والتشريعات القرآنية، تحقّق من الأدلة الموثوقة قبل الجزم.\n\n"

    "إذا سُئلت عن اسمك، قل: «أنا فهيم، مساعد ذكي للطلاب في مدرسة خريبة السوق الثانوية الثانية للبنين». "
    "إذا سُئلت عن مطورك، قل: «صنعني المطور جميل إسماعيل أبو حماد». "
    "لا تغيّر اسمك أو اسم مطورك.\n\n"

    "فهيم مساعد نصي ولا ينشئ الصور. إذا طلب الطالب إنشاء صورة، وضّح ذلك باختصار، "
    "ويمكنك مساعدته في كتابة وصف للصورة أو تحليل صورة يرسلها.\n\n"

    "هدفك: إجابة دقيقة، مباشرة، طبيعية، ومناسبة لسؤال الطالب دون حشو."
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
    normalized = message.translate(str.maketrans("ظ ظ،ظ¢ظ£ظ¤ظ¥ظ¦ظ§ظ¨ظ©", "0123456789"))
    normalized = re.sub(r"[\u064b-\u065f\u0670ظ€]", "", normalized).casefold()
    grade_pattern = "|".join(
        sorted(
            (re.escape(name) for name in GRADE_NAMES),
            key=len,
            reverse=True,
        )
    )
    match = re.search(
        rf"(?:طµظپ(?:ظٹ)?|ط§ظ„طµظپ|ط¨ط§ظ„طµظپ|ط¨ط§ظ„طµظپ ط§ظ„ط¯ط±ط§ط³ظٹ)\s*"
        rf"(?:ط±ظ‚ظ…\s*)?(?:(?:ط§ظ„)?({grade_pattern})|([1-9]|1[0-2]))"
        rf"(?!\d)",
        normalized,
    )
    if not match and allow_short_answer:
        match = re.fullmatch(
            rf"(?:(?:ط§ظ†ط§|ط§ظ†ظٹ)\s+)?(?:ط§ظ„طµظپ\s+)?"
            rf"(?:(?:ط§ظ„)?({grade_pattern})|([1-9]|1[0-2]))"
            rf"[.!طںطŒ\s]*",
            normalized,
        )
    if not match:
        return None
    if match.group(1):
        return GRADE_NAMES[match.group(1)]
    return f"ط§ظ„طµظپ {match.group(2)}"


def user_starts_with_greeting(message):
    normalized = re.sub(r"[\u064b-\u065f\u0670ظ€]", "", message.strip()).casefold()
    return re.match(
        r"^(?:ط§ظ„ط³ظ„ط§ظ… ط¹ظ„ظٹظƒظ…|ط³ظ„ط§ظ…|ظ…ط±ط­ط¨ط§|ظ…ط±ط­ط¨ط§ظ‹|ط£ظ‡ظ„ط§|ط§ظ‡ظ„ط§|ط£ظ‡ظ„ظ‹ط§|ظ‡ظ„ط§|"
        r"طµط¨ط§ط­ ط§ظ„ط®ظٹط±|ظ…ط³ط§ط، ط§ظ„ط®ظٹط±|ظ‡ط§ظٹ|hello|hi)(?=$|[\sطŒ,:.!طں!?-])",
        normalized,
    ) is not None


def user_asks_assistant_identity(message):
    normalized = re.sub(r"[\u064b-\u065f\u0670ظ€]", "", message.casefold())
    return re.search(
        r"(?:ط´ظˆ|ظ…ط§|ط§ظٹط´|ط¥ظٹط´|ظˆط´)\s+(?:ظ‡ظˆ\s+)?ط§ط³ظ…ظƒ|"
        r"(?:ظ…ظٹظ†|ظ…ظ†)\s+(?:ط£ظ†طھ|ط§ظ†طھ)|"
        r"(?:ظ…ظٹظ†|ظ…ظ†)\s+(?:طµظ†ط¹ظƒ|ط·ظˆط±ظƒ|ط·ظˆظ‘ط±ظƒ)|"
        r"ط¹ط±ظپظ†ظٹ\s+ط¹ظ†\s+ظ†ظپط³ظƒ|ط§ط­ظƒظٹظ„ظٹ\s+ط¹ظ†\s+ظ†ظپط³ظƒ",
        normalized,
    ) is not None


def conversation_system_instruction(
    first_reply, grade, ask_grade, user_greeted=False, asks_identity=False
):
    instructions = [SYSTEM_INSTRUCTION]
    if user_greeted or asks_identity:
        instructions.append(
            "ظپظٹ ظ‡ط°ظ‡ ط§ظ„ط±ط³ط§ظ„ط©طŒ ط¹ط±ظ‘ظپ ط¹ظ† ظ†ظپط³ظƒ ط¨ظˆط¶ظˆط­ ط¨ط§ظ„ظ†طµ: "
            "آ«ط£ظ†ط§ ظپظ‡ظٹظ…طŒ ظ…ط³ط§ط¹ط¯ ط°ظƒظٹ ظ„ظ„ط·ظ„ط§ط¨ ظپظٹ ظ…ط¯ط±ط³ط© ط®ط±ظٹط¨ط© ط§ظ„ط³ظˆظ‚آ». "
            "ط¥ط°ط§ ط³ط£ظ„ ط§ظ„ط·ط§ظ„ط¨ ط¹ظ† ظ…ط·ظˆط±ظƒطŒ ظ‚ظ„: آ«طµظ†ط¹ظ†ظٹ ط§ظ„ظ…ط·ظˆط± ط¬ظ…ظٹظ„ ط¥ط³ظ…ط§ط¹ظٹظ„ ط£ط¨ظˆ ط­ظ…ط§ط¯آ»."
        )
        if user_greeted:
            instructions.append("ط¨ط¯ط£ ط§ظ„ط·ط§ظ„ط¨ ط¨طھط­ظٹط©ط› ط§ط¨ط¯ط£ ط¨ظ‡ط°ط§ ط§ظ„طھط¹ط±ظٹظپ ط«ظ… ط£ط¬ط¨ ط¹ظ† ط³ط¤ط§ظ„ظ‡.")
    elif first_reply:
        instructions.append(
            "ظ‡ط°ظ‡ ط£ظˆظ„ ط±ط³ط§ظ„ط© ظپظٹ ط§ظ„ظ…ط­ط§ط¯ط«ط© ظˆظ„ظ… ظٹط¨ط¯ط£ ط§ظ„ط·ط§ظ„ط¨ ط¨طھط­ظٹط©ط› ظ„ط§ طھط±ط­ظ‘ط¨ ط¨ظ‡ "
            "ظˆظ„ط§ طھط¹ط±ظ‘ظپ ط¨ظ†ظپط³ظƒطŒ ظˆط§ط¨ط¯ط£ ط¨ط§ظ„ظ…ط¹ظ„ظˆظ…ط© ط£ظˆ ط§ظ„ط­ظ„ ظ…ط¨ط§ط´ط±ط© ط¯ظˆظ† ظ…ظ‚ط¯ظ…ط©."
        )
    else:
        instructions.append(
            "ظ‡ط°ظ‡ ظ…طھط§ط¨ط¹ط© ظ„ظ…ط­ط§ط¯ط«ط© ط¨ط¯ط£طھ ط³ط§ط¨ظ‚ظ‹ط§ط› ط£ط¬ط¨ ط¹ظ† ط§ظ„ط±ط³ط§ظ„ط© ظ…ط¨ط§ط´ط±ط© ظˆظ„ط§ طھط¨ط¯ط£ ط¨طھط­ظٹط©."
        )

    if grade:
        instructions.append(
            f"طµظپ ط§ظ„ط·ط§ظ„ط¨ ط§ظ„ظ…ط­ظپظˆط¸ ظپظٹ ظ…ظ„ظپظ‡ ظ‡ظˆ {grade}. ط§ط³طھط®ط¯ظ… ظƒطھط¨ ظ‡ط°ط§ ط§ظ„طµظپ "
            "ظˆظ…ظ†ظ‡ط¬ظ‡ ط§ظ„ط£ط±ط¯ظ†ظٹ ط¹ظ†ط¯ طµظ„ط© ط§ظ„ط³ط¤ط§ظ„ ط¨ط§ظ„ط¯ط±ط§ط³ط©."
        )
    elif ask_grade:
        instructions.append(
            "ظ„ظ… ظٹظڈط¹ط±ظپ طµظپ ط§ظ„ط·ط§ظ„ط¨ ط¨ط¹ط¯. ط§ط³ط£ظ„ظ‡ ظ…ط±ط© ظˆط§ط­ط¯ط© ظپظ‚ط· ظˆط¨ط£ط³ظ„ظˆط¨ ط£ط±ط¯ظ†ظٹ ط·ط¨ظٹط¹ظٹ: "
            "آ«ظˆط¨ط§ظ„ظ…ظ†ط§ط³ط¨ط©طŒ ط¥ظ†طھ ط¨ط£ظٹ طµظپطںآ» ظˆظ„ط§ طھط¤ط®ط± ط§ظ„ط¥ط¬ط§ط¨ط© ط¹ظ† ط³ط¤ط§ظ„ظ‡ ط¨ط§ظ†طھط¸ط§ط± ط§ظ„طµظپ."
        )
    else:
        instructions.append(
            "ط³ط¨ظ‚ ط£ظ† ط³ظڈط¦ظ„ ط§ظ„ط·ط§ظ„ط¨ ط¹ظ† طµظپظ‡ ظˆظ„ظ… ظٹظ‚ط¯ظ‘ظ… طµظپظ‹ط§ ظ…ط­ظپظˆط¸ظ‹ط§ط› ظ„ط§ طھط¹ط§ظˆط¯ ط§ظ„ط³ط¤ط§ظ„ ط¹ظ†ظ‡ "
            "ظپظٹ ظ‡ط°ظ‡ ط§ظ„ظ…ط­ط§ط¯ط«ط© ط£ظˆ ظپظٹ ظ…ط­ط§ط¯ط«ط© ط¬ط¯ظٹط¯ط©."
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
                database = Database(database_url)
    return database


def wants_image_generation(message):
    normalized = message.casefold()
    normalized = normalized.translate(str.maketrans("ط£ط¥ط¢", "ط§ط§ط§"))
    normalized = re.sub(r"[\u064b-\u065f\u0670ظ€]", "", normalized)
    return re.search(
        r"(?:ط§ط±ط³ظ…(?:ظٹ|ظ„ظٹ)?|ط§ظ†ط´ط¦(?:ظٹ|ظ„ظٹ)?|ط§ط¹ظ…ظ„(?:ظٹ|ظ„ظٹ)?|ط§ط¹ظ…ظ„ظ„ظٹ|ط³ظˆظٹ|طµظ…ظ…(?:ظٹ|ظ„ظٹ)?|"
        r"ظˆظ„ط¯|طھظˆظ„ط¯|ط¨ط¯ظٹ|ط§ط±ظٹط¯|ظ…ظ…ظƒظ†|please)\s*(?:ظ„ظٹ\s*)?(?:ط§ظ†\s*)?"
        r"(?:(?:طھط¹ظ…ظ„|ط§ط¹ظ…ظ„|طھط±ط³ظ…|ط§ط±ط³ظ…|طھظ†ط´ط¦|ط§ظ†ط´ط¦|طھطµظ…ظ…|طµظ…ظ…)\s*)?"
        r"(?:طµظˆط±ط©|طµظˆط±ظ‡|طµظˆط±|ط±ط³ظ…ط©|ظ„ظˆط­ط©|طھطµظ…ظٹظ…|ط®ظ„ظپظٹط©|ظ…ظ„طµظ‚|ط´ط¹ط§ط±|"
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
        str.maketrans("ط£ط¥ط¢", "ط§ط§ط§")
    )
    normalized = normalized.translate(str.maketrans("ظ ظ،ظ¢ظ£ظ¤ظ¥ظ¦ظ§ظ¨ظ©", "0123456789"))
    image_ordinals = {
        "1": 1,
        "first": 1,
        "ط§ظ„ط§ظˆظ„ظ‰": 1,
        "ط§ظˆظ„ظ‰": 1,
        "ط§ظ„ط£ظˆظ„ظ‰": 1,
        "2": 2,
        "second": 2,
        "ط§ظ„ط«ط§ظ†ظٹط©": 2,
        "ط«ط§ظ†ظٹظ‡": 2,
        "3": 3,
        "third": 3,
        "ط§ظ„ط«ط§ظ„ط«ط©": 3,
        "ط«ط§ظ„ط«ظ‡": 3,
    }
    ordinal_matches = re.findall(
        r"(?:ط§ظ„طµظˆط±ط©|ط§ظ„طµظˆط±ظ‡|طµظˆط±ط©|image|picture)\s*(?:ط±ظ‚ظ…\s*)?"
        r"(\d+|first|second|third|ط§ظ„ط£ظˆظ„ظ‰|ط§ظ„ط§ظˆظ„ظ‰|ط§ظˆظ„ظ‰|ط§ظ„ط«ط§ظ†ظٹط©|ط«ط§ظ†ظٹظ‡|"
        r"ط§ظ„ط«ط§ظ„ط«ط©|ط«ط§ظ„ط«ظ‡)",
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

    if re.search(r"ظ‚ط§ط±ظ†|ظ…ظ‚ط§ط±ظ†|ط§ظ„طµظˆط±طھظٹظ†|ط§ظ„طµظˆط±|compare|both images", normalized):
        return images

    if re.search(
        r"طµظˆط±ط©|ط§ظ„طµظˆط±ط©|ط§ظ„طµظˆط±ظ‡|ط§ظ„ظ…ط±ظپظ‚|ط§ظ„ظ…ط±ظپظ‚ط©|image|picture|"
        r"ظ‡ط§ظٹ|ظ‡ط°ظٹ|ظ‡ط°ظ‡|ظ‡ط°ط§|ظ‡ظٹ|ظ‡ظˆ|ظ†ظپط³ظ‡ط§|ظ†ظپط³ظ‡|ط²ظٹظ‡ط§|ظ…ط«ظ„ظ‡ط§|ط¹ظ„ظٹظ‡ط§|ظپظٹظ‡ط§|"
        r"ط§ظ„ط³ط§ط¨ظ‚|ط§ظ„ط³ط§ط¨ظ‚ط©|ظ‚ط¨ظ„|ظƒظ…ط§ظ†|it\b|this\b|that\b|same\b",
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
        raise ValueError("طھط¬ط§ظˆط²طھ ط§ظ„ط±ط³ط§ظ„ط© ظˆط§ظ„ظ…ط±ظپظ‚ط§طھ ط­ط¯ ط³ظٹط§ظ‚ Gemini.")

    rendered_history = []
    image_number = 0
    for message in previous_messages:
        line = f"{'ط§ظ„ط·ط§ظ„ط¨' if message['role'] == 'user' else 'ظپظ‡ظٹظ…'}: "
        line += message["content"] or "(ط±ط³ط§ظ„ط© ط¨ظ„ط§ ظ†طµ)"
        if message.get("has_image") or message.get("image_data") is not None:
            image_number += 1
            line += f" [ط£ط±ظپظ‚ ط§ظ„ط·ط§ظ„ط¨ طµظˆط±ط© ط³ط§ط¨ظ‚ط© ط±ظ‚ظ… {image_number}]"
        rendered_history.append((line, math.ceil(len(line.encode("utf-8")) / 2)))

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
            "ط³ط¬ظ„ ط§ظ„ظ…ط­ط§ط¯ط«ط© ط§ظ„ط³ط§ط¨ظ‚طŒ ظ…ط±طھط¨ظ‹ط§ ظ…ظ† ط§ظ„ط£ظ‚ط¯ظ… ط¥ظ„ظ‰ ط§ظ„ط£ط­ط¯ط«. "
            "ط§ط³طھط®ط¯ظ…ظ‡ ظ„ظپظ‡ظ… ط§ظ„ط¥ط´ط§ط±ط§طھ ظˆط§ظ„ط¶ظ…ط§ط¦ط± ظˆط§ظ„ط³ظٹط§ظ‚:\n"
            + "\n".join(history_lines)
        )
    context_parts = (
        [{"type": "text", "text": history_text}] if history_text else []
    )
    for image in selected_images:
        context_parts.extend(
            [
                {"type": "text", "text": "طµظˆط±ط© ط³ط§ط¨ظ‚ط© ط£ط´ط§ط± ط¥ظ„ظٹظ‡ط§ ط§ظ„ط·ط§ظ„ط¨:"},
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
        raise ValueError("طھط¬ط§ظˆط² ط­ط¬ظ… ط³ظٹط§ظ‚ ط§ظ„ظ…ط­ط§ط¯ط«ط© ط­ط¯ ط·ظ„ط¨ Gemini.")

    return parts


def make_conversation_title(message, has_image):
    title = message.strip()
    title = re.sub(r"\s+", " ", title)
    if has_image and not title:
        return "ظ…ط­ط§ط¯ط«ط© ط­ظˆظ„ طµظˆط±ط©"

    title = re.sub(
        r"^(?:(?:ط§ظ„ط³ظ„ط§ظ… ط¹ظ„ظٹظƒظ…|ظ…ط±ط­ط¨ط§|ظ…ط±ط­ط¨ط§ظ‹|ط£ظ‡ظ„ط§ظ‹|ط§ظ‡ظ„ط§|ط£ظ‡ظ„ظ‹ط§|ظ‡ظ„ط§|ظ‡ط§ظٹ|hello|hi)"
        r"[\sطŒ,:.!طں-]*)+",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()
    title = re.sub(r"^(?:ظٹط§\s+)?(?:ط¬ظ…ظٹظ„|ظپظ‡ظٹظ…)[\sطŒ,:.!طں-]*", "", title).strip()
    title = re.sub(
        r"^(?:ظƒظٹظپظƒ|ظƒظٹظپ ط­ط§ظ„ظƒ|ط´ظˆ ط£ط®ط¨ط§ط±ظƒ|ط´ظˆ ط§ط®ط¨ط§ط±ظƒ|ظƒظٹظپ ط§ظ„ط£ظ…ظˆط±|ظƒظٹظپ ط§ظ„ط§ظ…ظˆط±)"
        r"[\sطŒ,:.!طں-]*",
        "",
        title,
    ).strip()
    if not title or re.fullmatch(
        r"(?:ظƒظٹظپظƒ|ظƒظٹظپ ط­ط§ظ„ظƒ|ط´ظˆ ط£ط®ط¨ط§ط±ظƒ|ط´ظˆ ط§ط®ط¨ط§ط±ظƒ|ظƒظٹظپ ط§ظ„ط£ظ…ظˆط±|ظƒظٹظپ ط§ظ„ط§ظ…ظˆط±)"
        r"[طں?!.\s]*",
        title,
    ):
        return "ظ…ط­ط§ط¯ط«ط© ط¬ط¯ظٹط¯ط©"
    return title[:MAX_TITLE_LENGTH].rstrip()

def generate_conversation_title(message, answer):
    model = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash").strip()
    title_input = (
        "ط§ظƒطھط¨ ط¹ظ†ظˆط§ظ†ظ‹ط§ ظ„ظ‡ط°ظ‡ ط§ظ„ظ…ط­ط§ط¯ط«ط© ظٹطµظپ ظ…ظˆط¶ظˆط¹ظ‡ط§ ط§ظ„ط¹ط§ظ… ط¨ط¯ظ‚ط©طŒ ط§ط¹طھظ…ط§ط¯ظ‹ط§ ط¹ظ„ظ‰ ط£ظˆظ„ ط±ط³ط§ظ„ط© "
        "ظˆط±ط¯ ظپظ‡ظٹظ…. ظ„ط§ طھظƒطھط¨ ط¥ط¬ط§ط¨ط© ط§ظ„ط·ط§ظ„ط¨ ظˆظ„ط§ طھظ„ط®طµ ط§ظ„ظ…ط­ط§ط¯ط«ط© ظƒط§ظ…ظ„ط©. ط£ط¹ط¯ ط§ظ„ط¹ظ†ظˆط§ظ† ظپظ‚ط· "
        "ط¨ط§ظ„ط¹ط±ط¨ظٹط©طŒ ظ…ظ† 3 ط¥ظ„ظ‰ 8 ظƒظ„ظ…ط§طھطŒ ط¯ظˆظ† ط¹ظ„ط§ظ…ط§طھ ط§ظ‚طھط¨ط§ط³ ط£ظˆ طھط±ظ‚ظٹظ….\n\n"
        f"ط£ظˆظ„ ط±ط³ط§ظ„ط© ظ…ظ† ط§ظ„ط·ط§ظ„ط¨:\n{message[:2000]}\n\n"
        f"ط±ط¯ ظپظ‡ظٹظ…:\n{answer[:2000]}"
    )
    request = Request(
        API_URL,
        data=json.dumps(
            {
                "model": model,
                "input": title_input,
                "system_instruction": (
                    "ط£ظ†طھ طھظ†ط´ط¦ ط¹ظ†ط§ظˆظٹظ† ظ‚طµظٹط±ط© ظˆط¯ظ‚ظٹظ‚ط© ظ„ظ…ط­ط§ط¯ط«ط§طھ ظ…ط³ط§ط¹ط¯ ط¯ط±ط§ط³ظٹ. "
                    "ط§ط³طھط®ط±ط¬ ط§ظ„ظ…ظˆط¶ظˆط¹ ط§ظ„ط£ط³ط§ط³ظٹ ظˆظ„ط§ طھط¶ظپ ظ…ظˆط¶ظˆط¹ظ‹ط§ ط؛ظٹط± ظ…ظˆط¬ظˆط¯."
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
        raise RuntimeError(f"ط±ظپط¶طھ ط®ط¯ظ…ط© Gemini ط¥ظ†ط´ط§ط، ط¹ظ†ظˆط§ظ† (HTTP {error.code}).") from error
    except (URLError, TimeoutError) as error:
        raise RuntimeError(f"طھط¹ط°ظ‘ط± ط§ظ„ط§طھطµط§ظ„ ط¨ط®ط¯ظ…ط© Gemini ظ„ط¥ظ†ط´ط§ط، ط¹ظ†ظˆط§ظ†: {error}") from error
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise RuntimeError("ط£ط¹ط§ط¯طھ Gemini ط¨ظٹط§ظ†ط§طھ ط؛ظٹط± ظ…ظپظ‡ظˆظ…ط© ظ„ظ„ط¹ظ†ظˆط§ظ†.") from error

    if not isinstance(interaction, dict):
        raise RuntimeError("ط£ط¹ط§ط¯طھ Gemini ط¨ظ†ظٹط© ط؛ظٹط± طµط§ظ„ط­ط© ظ„ظ„ط¹ظ†ظˆط§ظ†.")
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
        raise RuntimeError("ظ„ظ… طھظڈط±ط¬ط¹ Gemini ط¹ظ†ظˆط§ظ†ظ‹ط§ طµط§ظ„ط­ظ‹ط§ ظ„ظ„ظ…ط­ط§ط¯ط«ط©.")
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


class ChatHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_ROOT), **kwargs)

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
        if self.path == "/api/me":
            if not user:
                self.send_json({"error": "ط³ط¬ظ‘ظ„ ط§ظ„ط¯ط®ظˆظ„ ظ„ظ„ظ…طھط§ط¨ط¹ط©."}, 401)
            else:
                self.send_json(
                    {
                        "user": user,
                        "isAdmin": self.is_admin(user),
                        "isPrimaryAdmin": self.is_primary_admin(user),
                    }
                )
            return

        if self.path == "/api/admin/dashboard":
            if not user:
                self.send_unauthorized()
                return
            if not self.is_admin(user):
                self.send_json({"error": "ظ„ظٹط³ ظ„ط¯ظٹظƒ طµظ„ط§ط­ظٹط© ظ„ظپطھط­ ظ„ظˆط­ط© ط§ظ„طھط­ظƒظ…."}, 403)
                return
            admin_email = os.environ.get("ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL).strip()
            self.send_json(get_database().admin_dashboard(admin_email))
            return

        if self.path == "/api/admin/statistics":
            if not user:
                self.send_unauthorized()
                return
            if not self.is_admin(user):
                self.send_json({"error": "ظ„ظٹط³ ظ„ط¯ظٹظƒ طµظ„ط§ط­ظٹط© ظ„ظپطھط­ ظ„ظˆط­ط© ط§ظ„طھط­ظƒظ…."}, 403)
                return
            self.send_json(get_database().admin_statistics())
            return

        if self.path == "/api/admin/support-messages":
            if not user:
                self.send_unauthorized()
                return
            if not self.is_admin(user):
                self.send_json(
                    {"error": "ظ„ظٹط³ ظ„ط¯ظٹظƒ طµظ„ط§ط­ظٹط© ظ„ط¹ط±ط¶ ط±ط³ط§ط¦ظ„ ظ…ط±ظƒط² ط§ظ„ظ…ط³ط§ط¹ط¯ط©."}, 403
                )
                return
            self.send_json(
                {"messages": get_database().list_support_messages()}
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
                self.send_json({"error": "ط§ظ„ظ…ط­ط§ط¯ط«ط© ط؛ظٹط± ظ…ظˆط¬ظˆط¯ط©."}, 404)
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

        super().do_GET()

    def do_POST(self):
        if self.path != "/api/chat":
            return self._do_POST()

        self._chat_perf_started = time.perf_counter()
        self._chat_perf = {}
        try:
            self._do_POST()
        finally:
            total = time.perf_counter() - self._chat_perf_started
            stages = (
                "student_preferences",
                "title_generation",
                "prepare_user_message",
                "conversation_context",
                "conversation_images",
                "gemini_first_byte",
                "gemini_total",
                "save_assistant",
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
        if self.path == "/api/logout":
            token = self.session_token()
            get_database().delete_session(token)
            self.send_response(204)
            self.send_header(
                "Set-Cookie",
                self.session_cookie("", max_age=0),
            )
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if self.path != "/api/chat":
            self.send_json({"error": "ط§ظ„ظ…ط³ط§ط± ط؛ظٹط± ظ…ظˆط¬ظˆط¯."}, 404)
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
            self.send_json({"error": "طµظٹط؛ط© ط§ظ„ط±ط³ط§ظ„ط© ط؛ظٹط± طµط§ظ„ط­ط©."}, 400)
            return

        conversation_id = payload.get("conversationId")
        if conversation_id is not None and (
            not isinstance(conversation_id, str)
            or not re.fullmatch(r"[a-f0-9]{32}", conversation_id)
        ):
            self.send_json({"error": "ظ…ط±ط¬ط¹ ط§ظ„ظ…ط­ط§ط¯ط«ط© ط؛ظٹط± طµط§ظ„ط­."}, 400)
            return

        current_parts = []
        if message.strip():
            current_parts.append({"type": "text", "text": message.strip()})

        image = payload.get("image")
        attachment = payload.get("file")
        if image is not None:
            if not isinstance(image, dict):
                self.send_json({"error": "ط¨ظٹط§ظ†ط§طھ ط§ظ„طµظˆط±ط© ط؛ظٹط± طµط§ظ„ط­ط©."}, 400)
                return
            mime_type = image.get("mimeType")
            data = image.get("data")
            if mime_type not in ALLOWED_IMAGE_TYPES or not isinstance(data, str):
                self.send_json({"error": "طµظٹط؛ط© ط§ظ„طµظˆط±ط© ط؛ظٹط± ظ…ط¯ط¹ظˆظ…ط©."}, 400)
                return
            try:
                image_bytes = base64.b64decode(data, validate=True)
            except (binascii.Error, ValueError):
                self.send_json({"error": "طھط¹ط°ظ‘ط± ظ‚ط±ط§ط،ط© ط§ظ„طµظˆط±ط©."}, 400)
                return
            if not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
                self.send_json(
                    {"error": "ظٹط¬ط¨ ط£ظ„ط§ ظٹطھط¬ط§ظˆط² ط­ط¬ظ… ط§ظ„طµظˆط±ط© 8 ظ…ظٹط؛ط§ط¨ط§ظٹطھ."}, 413
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
                self.send_json({"error": "ط£ط±ظپظ‚ طµظˆط±ط© ط£ظˆ ظ…ظ„ظپظ‹ط§ ظˆط§ط­ط¯ظ‹ط§ ظپظٹ ظƒظ„ ظ…ط±ط©."}, 400)
                return
            if not isinstance(attachment, dict):
                self.send_json({"error": "ط¨ظٹط§ظ†ط§طھ ط§ظ„ظ…ظ„ظپ ط؛ظٹط± طµط§ظ„ط­ط©."}, 400)
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
                self.send_json({"error": "ظ†ظˆط¹ ط§ظ„ظ…ظ„ظپ ط؛ظٹط± ظ…ط¯ط¹ظˆظ…."}, 400)
                return
            try:
                document_bytes = base64.b64decode(file_data, validate=True)
            except (binascii.Error, ValueError):
                self.send_json({"error": "طھط¹ط°ظ‘ط±طھ ظ‚ط±ط§ط،ط© ط§ظ„ظ…ظ„ظپ."}, 400)
                return
            if not document_bytes or len(document_bytes) > MAX_DOCUMENT_BYTES:
                self.send_json({"error": "ظٹط¬ط¨ ط£ظ„ط§ ظٹطھط¬ط§ظˆط² ط­ط¬ظ… ط§ظ„ظ…ظ„ظپ 8 ظ…ظٹط؛ط§ط¨ط§ظٹطھ."}, 413)
                return
            current_parts.append(
                {
                    "type": "document",
                    "mime_type": file_mime,
                    "data": base64.b64encode(document_bytes).decode("ascii"),
                }
            )

        if not current_parts:
            self.send_json({"error": "ط§ظƒطھط¨ ط±ط³ط§ظ„ط© ط£ظˆ ط£ط±ظپظ‚ طµظˆط±ط© ط£ظˆ ظ…ظ„ظپظ‹ط§ ظ‚ط¨ظ„ ط§ظ„ط¥ط±ط³ط§ظ„."}, 400)
            return
        generate_image = (
            payload.get("generateImage") is True or wants_image_generation(message)
        )
        student_started = time.perf_counter()
        student_preferences = get_database().get_student_preferences(user["id"])
        if not student_preferences:
            self.send_json({"error": "طھط¹ط°ظ‘ط± طھط­ظ…ظٹظ„ ط¥ط¹ط¯ط§ط¯ط§طھ ط­ط³ط§ط¨ ط§ظ„ط·ط§ظ„ط¨."}, 500)
            return
        student_grade = extract_student_grade(message)
        if (
            student_grade is None
            and student_preferences["grade_question_asked"]
            and student_preferences["grade"] is None
        ):
            student_grade = extract_student_grade(message, allow_short_answer=True)
        if student_grade:
            student_preferences = get_database().update_student_grade(
                user["id"], student_grade
            )
            if not student_preferences:
                self.send_json(
                    {"error": "طھط¹ط°ظ‘ط± طھط­ظ…ظٹظ„ ط¥ط¹ط¯ط§ط¯ط§طھ ط­ط³ط§ط¨ ط§ظ„ط·ط§ظ„ط¨."}, 500
                )
                return
        self._record_chat_perf("student_preferences", student_started)
        ask_grade = (
            not student_preferences["grade_question_asked"]
            and student_preferences["grade"] is None
        )

        try:
            saved_message = message.strip()
            title_message = saved_message
            if file_name:
                saved_message = "\n".join(
                    part for part in (saved_message, f"ظ…ط±ظپظ‚ ظ…ظ„ظپ: {file_name}") if part
                )
                title_message = title_message or f"ظ…ظ„ظپ {file_name}"
            title_started = time.perf_counter()
            local_title = make_conversation_title(
                title_message, image is not None
            )
            self._record_chat_perf("title_generation", title_started)
            prepare_started = time.perf_counter()
            stored = get_database().prepare_user_message(
                user["id"],
                conversation_id,
                local_title,
                saved_message,
                mime_type if image is not None else None,
                image_bytes if image is not None else None,
            )
            self._record_chat_perf("prepare_user_message", prepare_started)
        except Database.error_types:
            self.send_json({"error": "طھط¹ط°ظ‘ط± ط­ظپط¸ ط§ظ„ط±ط³ط§ظ„ط© ظپظٹ ظ‚ط§ط¹ط¯ط© ط§ظ„ط¨ظٹط§ظ†ط§طھ."}, 500)
            return
        if not stored:
            self.send_json({"error": "ط§ظ„ظ…ط­ط§ط¯ط«ط© ط؛ظٹط± ظ…ظˆط¬ظˆط¯ط©."}, 404)
            return

        model = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite").strip()
        if not model or any(
            character
            not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
            for character in model
        ):
            self.send_json({"error": "ط§ط³ظ… ظ†ظ…ظˆط°ط¬ Gemini ظپظٹ ط§ظ„ط¥ط¹ط¯ط§ط¯ط§طھ ط؛ظٹط± طµط§ظ„ط­."}, 500)
            return

        stored["user_id"] = user["id"]
        stored["mark_grade_question_asked"] = ask_grade
        if stored["title_needs_ai"]:
            stored["title_source"] = title_message
        if generate_image:
            self.send_image_creation_unavailable(stored)
            return

        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            self.send_json(
                {
                    "error": (
                        "ط£ط¶ظپ ظ…ظپطھط§ط­ Gemini ظپظٹ GEMINI_API_KEY ط¯ط§ط®ظ„ ظ…ظ„ظپ .env "
                        "ط«ظ… ط£ط¹ط¯ طھط´ط؛ظٹظ„ ط§ظ„ط®ط§ط¯ظ…."
                    )
                },
                503,
            )
            return

        try:
            context_started = time.perf_counter()
            context_rows = get_database().get_conversation_context(
                user["id"], stored["id"]
            )
            self._record_chat_perf("conversation_context", context_started)
            if not context_rows:
                self.send_json({"error": "ط§ظ„ظ…ط­ط§ط¯ط«ط© ط؛ظٹط± ظ…ظˆط¬ظˆط¯ط©."}, 404)
                return
            context_messages = [dict(row) for row in context_rows]
            previous_messages = [
                row
                for row in context_messages
                if row["id"] < stored["message_id"]
            ]
            system_instruction = conversation_system_instruction(
                first_reply=not any(
                    row["role"] == "assistant" for row in previous_messages
                ),
                grade=student_preferences["grade"],
                ask_grade=ask_grade,
                user_greeted=user_starts_with_greeting(message),
                asks_identity=user_asks_assistant_identity(message),
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
                            "ط§ظ„طµظˆط± ط§ظ„ط³ط§ط¨ظ‚ط© ط§ظ„ظ…ط·ظ„ظˆط¨ط© طھطھط¬ط§ظˆط² ط­ط¯ ط­ط¬ظ… Gemini. "
                            "ط£ط±ط³ظ„ ط§ظ„طµظˆط± ط§ظ„ظ…ط·ظ„ظˆط¨ط© ظپظٹ ط±ط³ط§ط¦ظ„ ط£ظ‚ظ„ ط£ظˆ ط§ط®طھط± ط§ظ„طµظˆط± ط§ظ„ظ„ط§ط²ظ…ط© ظپظ‚ط·."
                        )
                    },
                    413,
                )
                return
            selected_images = get_database().get_conversation_images(
                user["id"],
                stored["id"],
                [image["id"] for image in selected_prior_images],
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
            self.send_json({"error": "طھط¹ط°ظ‘ط± ط§ط³طھط±ط¬ط§ط¹ ط³ظٹط§ظ‚ ط§ظ„ظ…ط­ط§ط¯ط«ط© ظ…ظ† ظ‚ط§ط¹ط¯ط© ط§ظ„ط¨ظٹط§ظ†ط§طھ."}, 500)
            returntry:
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
        request_data = json.dumps(request_payload, ensure_ascii=False).encode("utf-8")
        if len(request_data) > MAX_GEMINI_REQUEST_BYTES:
            self.send_json({"error": "طھط¬ط§ظˆط² ط­ط¬ظ… ط§ظ„ط³ظٹط§ظ‚ ط­ط¯ ط·ظ„ط¨ Gemini."}, 413)
            return
        request = Request(
            API_URL,
            data=request_data,
            headers={
                "x-goog-api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            method="POST",
        )
        gemini_started = time.perf_counter()
        stored["gemini_started_at"] = gemini_started
        stream_started = False
        try:
            with urlopen(request, timeout=90) as response:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, no-transform")
                self.send_header("Connection", "close")
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()
                self.close_connection = True
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
                        "error", {"error": "ط§ظ†ظ‚ط·ط¹ ط§طھطµط§ظ„ Gemini ظ‚ط¨ظ„ ط§ظƒطھظ…ط§ظ„ ط§ظ„ط¥ط¬ط§ط¨ط©."}
                    )
                return
        except HTTPError as error:
            try:
                error_body = json.loads(error.read())
                detail = error_body.get("error", {}).get("message")
            except (
                json.JSONDecodeError,
                UnicodeDecodeError,
                AttributeError,
                TypeError,
            ):
                detail = None
            self.send_json(
                {"error": detail or f"ط±ظپط¶طھ ط®ط¯ظ…ط© Gemini ط§ظ„ط·ظ„ط¨ (HTTP {error.code})."},
                error.code if 400 <= error.code < 600 else 502,
            )
            return
        except (URLError, TimeoutError) as error:
            self.send_json({"error": f"طھط¹ط°ظ‘ط± ط§ظ„ط§طھطµط§ظ„ ط¨ط®ط¯ظ…ط© Gemini: {error}"}, 502)
            return
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception:
            if stream_started:
                try:
                    self.send_sse(
                        "error", {"error": "طھط¹ط°ظ‘ط± ط¥ظƒظ…ط§ظ„ ط§ظ„ط¥ط¬ط§ط¨ط© ط¨ط³ط¨ط¨ ط®ط·ط£ ط¯ط§ط®ظ„ظٹ."}
                    )
                except (BrokenPipeError, ConnectionResetError):
                    pass
            else:
                self.send_json({"error": "طھط¹ط°ظ‘ط± ط¨ط¯ط، ط¨ط« Gemini."}, 502)
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
                    {"error": "ظ„ظٹط³ ظ„ط¯ظٹظƒ طµظ„ط§ط­ظٹط© ظ„ط¥ط¯ط§ط±ط© ط±ط³ط§ط¦ظ„ ظ…ط±ظƒط² ط§ظ„ظ…ط³ط§ط¹ط¯ط©."}, 403
                )
                return
            payload = self.read_json_body()
            if payload is None:
                return
            status = payload.get("status")
            if status not in {"new", "resolved"}:
                self.send_json({"error": "ط­ط§ظ„ط© ط§ظ„ط±ط³ط§ظ„ط© ط؛ظٹط± طµط§ظ„ط­ط©."}, 400)
                return
            if not get_database().set_support_message_status(
                int(support_match.group(1)), status
            ):
                self.send_json({"error": "ط±ط³ط§ظ„ط© ظ…ط±ظƒط² ط§ظ„ظ…ط³ط§ط¹ط¯ط© ط؛ظٹط± ظ…ظˆط¬ظˆط¯ط©."}, 404)
                return
            self.send_json({"ok": True, "status": status})
            return

        match = re.fullmatch(r"/api/conversations/([a-f0-9]{32})", self.path)
        if not match:
            self.send_json({"error": "ط§ظ„ظ…ط³ط§ط± ط؛ظٹط± ظ…ظˆط¬ظˆط¯."}, 404)
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
            self.send_json({"error": "ط§ظƒطھط¨ ط¹ظ†ظˆط§ظ†ظ‹ط§ ظ„ظ„ظ…ط­ط§ط¯ط«ط©."}, 400)
            return
        title = re.sub(r"\s+", " ", title.strip())
        if len(title) > MAX_TITLE_LENGTH:
            self.send_json(
                {"error": f"ظٹط¬ط¨ ط£ظ„ط§ ظٹطھط¬ط§ظˆط² ط§ظ„ط¹ظ†ظˆط§ظ† {MAX_TITLE_LENGTH} ط­ط±ظپظ‹ط§."}, 400
            )
            return
        updated_title = get_database().rename_conversation(
            user["id"], match.group(1), title
        )
        if not updated_title:
            self.send_json({"error": "ط§ظ„ظ…ط­ط§ط¯ط«ط© ط؛ظٹط± ظ…ظˆط¬ظˆط¯ط©."}, 404)
            return
        self.send_json({"ok": True, "title": updated_title})

    def do_DELETE(self):
        admin_match = re.fullmatch(r"/api/admin/users/([a-f0-9]{32})", self.path)
        if admin_match:
            user = self.current_user()
            if not user:
                self.send_unauthorized()
                return
            if not self.is_admin(user):
                self.send_json({"error": "ظ„ظٹط³ ظ„ط¯ظٹظƒ طµظ„ط§ط­ظٹط© ظ„ط­ط°ظپ ط§ظ„ظ…ط³طھط®ط¯ظ…ظٹظ†."}, 403)
                return
            target_user_id = admin_match.group(1)
            if target_user_id == user["id"]:
                self.send_json({"error": "ظ„ط§ ظٹظ…ظƒظ†ظƒ ط­ط°ظپ ط­ط³ط§ط¨ ط§ظ„ط£ط¯ظ…ظ† ظ…ظ† ظ„ظˆط­ط© ط§ظ„طھط­ظƒظ…."}, 400)
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
                    {"error": "ظ„ط§ ظٹظ…ظƒظ† ط­ط°ظپ ط­ط³ط§ط¨ ط§ظ„ط£ط¯ظ…ظ† ط§ظ„ط£ط³ط§ط³ظٹ."}, 400
                )
                return
            if result == "target_admin":
                self.send_json(
                    {"error": "ط§ظ„ط£ط¯ظ…ظ† ط؛ظٹط± ط§ظ„ط£ط³ط§ط³ظٹ ظ„ط§ ظٹظ…ظƒظ†ظ‡ ط­ط°ظپ ط­ط³ط§ط¨ ط£ط¯ظ…ظ† ط¢ط®ط±."},
                    403,
                )
                return
            if result == "not_found":
                self.send_json({"error": "ط§ظ„ظ…ط³طھط®ط¯ظ… ط؛ظٹط± ظ…ظˆط¬ظˆط¯."}, 404)
                return
            self.send_response(204)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return

        match = re.fullmatch(r"/api/conversations/([a-f0-9]{32})", self.path)
        if not match:
            self.send_json({"error": "ط§ظ„ظ…ط³ط§ط± ط؛ظٹط± ظ…ظˆط¬ظˆط¯."}, 404)
            return
        user = self.current_user()
        if not user:
            self.send_unauthorized()
            return
        if not get_database().delete_conversation(user["id"], match.group(1)):
            self.send_json({"error": "ط§ظ„ظ…ط­ط§ط¯ط«ط© ط؛ظٹط± ظ…ظˆط¬ظˆط¯ط©."}, 404)
            return
        self.send_response(204)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def auth_payload(self):
        payload = self.read_json_body()
        if payload is None:
            return None
        email = payload.get("email")
        password = payload.get("password")
        if not isinstance(email, str) or not isinstance(password, str):
            self.send_json({"error": "ط£ط¯ط®ظ„ ط§ظ„ط¨ط±ظٹط¯ ط§ظ„ط¥ظ„ظƒطھط±ظˆظ†ظٹ ظˆظƒظ„ظ…ط© ط§ظ„ظ…ط±ظˆط±."}, 400)
            return None
        email = email.strip().casefold()
        if (
            len(email) > 254
            or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)
        ):
            self.send_json({"error": "ط£ط¯ط®ظ„ ط¹ظ†ظˆط§ظ† ط¨ط±ظٹط¯ ط¥ظ„ظƒطھط±ظˆظ†ظٹ طµط§ظ„ط­ظ‹ط§."}, 400)
            return None
        if not password or len(password) > 128:
            self.send_json({"error": "ظƒظ„ظ…ط© ط§ظ„ظ…ط±ظˆط± ط؛ظٹط± طµط§ظ„ط­ط©."}, 400)
            return None
        try:
            password.encode("utf-8")
        except UnicodeEncodeError:
            self.send_json({"error": "ط§ط³طھط®ط¯ظ… ط£ط­ط±ظپظ‹ط§ طµط§ظ„ط­ط© ظپظٹ ظƒظ„ظ…ط© ط§ظ„ظ…ط±ظˆط±."}, 400)
            return None
        remember = payload.get("remember", True)
        if not isinstance(remember, bool):
            self.send_json({"error": "ط¥ط¹ط¯ط§ط¯ طھط°ظƒظ‘ط± ط§ظ„ط¬ظ‡ط§ط² ط؛ظٹط± طµط§ظ„ط­."}, 400)
            return None
        return email, password, remember

    def send_authenticated_user(self, user, remember):
        lifetime = 365 * 24 * 60 * 60 if remember else 24 * 60 * 60
        token = get_database().create_session(user["id"], lifetime)
        self.send_json(
            {
                "user": user,
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
                {"error": "ظ„ظٹط³ ظ„ط¯ظٹظƒ طµظ„ط§ط­ظٹط© ظ„ط¥ط¯ط§ط±ط© طµظ„ط§ط­ظٹط§طھ ط§ظ„ظ…ط³طھط®ط¯ظ…ظٹظ†."}, 403
            )
            return
        payload = self.read_json_body()
        if payload is None:
            return
        is_admin = payload.get("isAdmin")
        if not isinstance(is_admin, bool):
            self.send_json({"error": "ظ‚ظٹظ…ط© طµظ„ط§ط­ظٹط© ط§ظ„ط£ط¯ظ…ظ† ط؛ظٹط± طµط§ظ„ط­ط©."}, 400)
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
            self.send_json({"error": "ط§ظ„ظ…ط³طھط®ط¯ظ… ط؛ظٹط± ظ…ظˆط¬ظˆط¯."}, 404)
            return
        if result == "self":
            self.send_json(
                {"error": "ظ„ط§ ظٹظ…ظƒظ†ظƒ طھط؛ظٹظٹط± طµظ„ط§ط­ظٹط§طھ ط­ط³ط§ط¨ظƒ ط¨ظ†ظپط³ظƒ."}, 400
            )
            return
        if result == "primary_admin":
            self.send_json(
                {"error": "ظ„ط§ ظٹظ…ظƒظ† طھط؛ظٹظٹط± طµظ„ط§ط­ظٹط© ط§ظ„ط£ط¯ظ…ظ† ط§ظ„ط£ط³ط§ط³ظٹ."}, 400
            )
            return
        self.send_json({"ok": True, "isAdmin": is_admin})

    def register_account(self):
        values = self.auth_payload()
        if not values:
            return
        email, password, remember = values
        if len(password) < 10:
            self.send_json(
                {"error": "ط£ظ†ط´ط¦ ظƒظ„ظ…ط© ظ…ط±ظˆط± ظ…ظ† 10 ط£ط­ط±ظپ ط¹ظ„ظ‰ ط§ظ„ط£ظ‚ظ„."}, 400
            )
            return
        try:
            user = get_database().register_user(email, password)
        except Database.integrity_error_types:
            self.send_json(
                {"error": "ظٹظˆط¬ط¯ ط­ط³ط§ط¨ ظ…ط³ط¬ظ„ ط¨ظ‡ط°ط§ ط§ظ„ط¨ط±ظٹط¯. ط³ط¬ظ‘ظ„ ط§ظ„ط¯ط®ظˆظ„ ط¨ط¯ظ„ظ‹ط§ ظ…ظ† ط°ظ„ظƒ."},
                409,
            )
            return
        self.send_authenticated_user(user, remember)

    def login_account(self):
        values = self.auth_payload()
        if not values:
            return
        email, password, remember = values
        if not get_database().user_exists(email):
            self.send_json(
                {
                    "error": (
                        "ظ„ظ… ظٹطھظ… ط§ظ„ط¹ط«ظˆط± ط¹ظ„ظ‰ ط­ط³ط§ط¨ ط¨ظ‡ط°ط§ ط§ظ„ط¨ط±ظٹط¯ ط§ظ„ط¥ظ„ظƒطھط±ظˆظ†ظٹ. "
                        "ط£ظ†ط´ط¦ ط­ط³ط§ط¨ظ‹ط§ ط¬ط¯ظٹط¯ظ‹ط§ ظ„ظ„ظ…طھط§ط¨ط¹ط©."
                    )
                },
                404,
            )
            return
        user = get_database().login_user(email, password)
        if not user:
            self.send_json({"error": "ط§ظ„ط¨ط±ظٹط¯ ط§ظ„ط¥ظ„ظƒطھط±ظˆظ†ظٹ ط£ظˆ ظƒظ„ظ…ط© ط§ظ„ظ…ط±ظˆط± ط؛ظٹط± طµط­ظٹط­ط©."}, 401)
            return
        self.send_authenticated_user(user, remember)

    def forgot_password(self):
        payload = self.read_json_body()
        if payload is None:
            return
        email = payload.get("email")
        if not isinstance(email, str):
            self.send_json({"error": "ط£ط¯ط®ظ„ ط¨ط±ظٹط¯ظ‹ط§ ط¥ظ„ظƒطھط±ظˆظ†ظٹظ‹ط§ طµط§ظ„ط­ظ‹ط§."}, 400)
            return
        email = email.strip().casefold()
        if (
            len(email) > 254
            or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)
        ):
            self.send_json({"error": "ط£ط¯ط®ظ„ ط¨ط±ظٹط¯ظ‹ط§ ط¥ظ„ظƒطھط±ظˆظ†ظٹظ‹ط§ طµط§ظ„ط­ظ‹ط§."}, 400)
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
                    {"error": "طھط¹ط°ظ‘ط± ط¥ط±ط³ط§ظ„ ط±ظ…ط² ط§ظ„طھط­ظ‚ظ‚ ط­ط§ظ„ظٹظ‹ط§. ط­ط§ظˆظ„ ظ…ط±ط© ط£ط®ط±ظ‰ ظ„ط§ط­ظ‚ظ‹ط§."},
                    503,
                )
                return

        self.send_json(
            {
                "ok": True,
                "message": (
                    "ط¥ط°ط§ ظƒط§ظ† ط§ظ„ط¨ط±ظٹط¯ ظ…ط±طھط¨ط·ظ‹ط§ ط¨ط­ط³ط§ط¨طŒ ظپط³ظٹطµظ„ظƒ ط±ظ…ط² طھط­ظ‚ظ‚ طµط§ظ„ط­ ظ„ظ…ط¯ط© "
                    "10 ط¯ظ‚ط§ط¦ظ‚. ط§ظپط­طµ ط¨ط±ظٹط¯ظƒ ط§ظ„ظˆط§ط±ط¯ ظˆظ…ط¬ظ„ط¯ ط§ظ„ط±ط³ط§ط¦ظ„ ط؛ظٹط± ط§ظ„ظ…ط±ط؛ظˆط¨ ظپظٹظ‡ط§."
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
                {"error": "ط£ط¯ط®ظ„ ط§ظ„ط¨ط±ظٹط¯ ط§ظ„ط¥ظ„ظƒطھط±ظˆظ†ظٹ ظˆط±ظ…ط² ط§ظ„طھط­ظ‚ظ‚ ظˆظƒظ„ظ…ط© ط§ظ„ظ…ط±ظˆط± ط§ظ„ط¬ط¯ظٹط¯ط©."},
                400,
            )
            return

        email = email.strip().casefold()
        if (
            len(email) > 254
            or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)
        ):
            self.send_json({"error": "ط£ط¯ط®ظ„ ط¨ط±ظٹط¯ظ‹ط§ ط¥ظ„ظƒطھط±ظˆظ†ظٹظ‹ط§ طµط§ظ„ط­ظ‹ط§."}, 400)
            return
        if not re.fullmatch(r"[0-9]{6}", code):
            self.send_json({"error": "ط±ظ…ط² ط§ظ„طھط­ظ‚ظ‚ ظٹط¬ط¨ ط£ظ† ظٹطھظƒظˆظ† ظ…ظ† 6 ط£ط±ظ‚ط§ظ…."}, 400)
            return
        if not new_password or len(new_password) > 128:
            self.send_json({"error": "ظƒظ„ظ…ط© ط§ظ„ظ…ط±ظˆط± ط§ظ„ط¬ط¯ظٹط¯ط© ط؛ظٹط± طµط§ظ„ط­ط©."}, 400)
            return
        try:
            new_password.encode("utf-8")
        except UnicodeEncodeError:
            self.send_json({"error": "ط§ط³طھط®ط¯ظ… ط£ط­ط±ظپظ‹ط§ طµط§ظ„ط­ط© ظپظٹ ظƒظ„ظ…ط© ط§ظ„ظ…ط±ظˆط±."}, 400)
            return
        if len(new_password) < 10:
            self.send_json(
                {"error": "ط£ظ†ط´ط¦ ظƒظ„ظ…ط© ظ…ط±ظˆط± ط¬ط¯ظٹط¯ط© ظ…ظ† 10 ط£ط­ط±ظپ ط¹ظ„ظ‰ ط§ظ„ط£ظ‚ظ„."}, 400
            )
            return

        result = get_database().reset_password(
            email, code, new_password, int(time.time())
        )
        if result == "success":
            self.send_json({"ok": True})
            return
        errors = {
            "expired": "ط§ظ†طھظ‡طھ طµظ„ط§ط­ظٹط© ط§ظ„ط±ظ…ط². ط§ط·ظ„ط¨ ط±ظ…ط²ظ‹ط§ ط¬ط¯ظٹط¯ظ‹ط§.",
            "locked": "طھظ… ط¥ظٹظ‚ط§ظپ ط§ظ„ط±ظ…ط² ط¨ط¹ط¯ ظ…ط­ط§ظˆظ„ط§طھ ظƒط«ظٹط±ط©. ط§ط·ظ„ط¨ ط±ظ…ط²ظ‹ط§ ط¬ط¯ظٹط¯ظ‹ط§.",
            "invalid": "ط±ظ…ط² ط§ظ„طھط­ظ‚ظ‚ ط؛ظٹط± طµط­ظٹط­ ط£ظˆ ط§ظ†طھظ‡طھ طµظ„ط§ط­ظٹطھظ‡.",
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
        if not isinstance(current_password, str) or not isinstance(
            new_password, str
        ):
            self.send_json({"error": "ط£ط¯ط®ظ„ ظƒظ„ظ…ط© ط§ظ„ظ…ط±ظˆط± ط§ظ„ط­ط§ظ„ظٹط© ظˆط§ظ„ط¬ط¯ظٹط¯ط©."}, 400)
            return
        if (
            not current_password
            or len(current_password) > 128
            or not new_password
            or len(new_password) > 128
        ):
            self.send_json({"error": "ظƒظ„ظ…ط© ط§ظ„ظ…ط±ظˆط± ط؛ظٹط± طµط§ظ„ط­ط©."}, 400)
            return
        try:
            current_password.encode("utf-8")
            new_password.encode("utf-8")
        except UnicodeEncodeError:
            self.send_json({"error": "ط§ط³طھط®ط¯ظ… ط£ط­ط±ظپظ‹ط§ طµط§ظ„ط­ط© ظپظٹ ظƒظ„ظ…ط© ط§ظ„ظ…ط±ظˆط±."}, 400)
            return
        if len(new_password) < 10:
            self.send_json(
                {"error": "ط£ظ†ط´ط¦ ظƒظ„ظ…ط© ظ…ط±ظˆط± ط¬ط¯ظٹط¯ط© ظ…ظ† 10 ط£ط­ط±ظپ ط¹ظ„ظ‰ ط§ظ„ط£ظ‚ظ„."}, 400
            )
            return
        if new_password == current_password:
            self.send_json(
                {"error": "ط§ط®طھط± ظƒظ„ظ…ط© ظ…ط±ظˆط± ط¬ط¯ظٹط¯ط© ظ…ط®طھظ„ظپط© ط¹ظ† ط§ظ„ط­ط§ظ„ظٹط©."}, 400
            )
            return
        if not get_database().change_password(
            user["id"],
            current_password,
            new_password,
            self.session_token(),
        ):
            self.send_json({"error": "ظƒظ„ظ…ط© ط§ظ„ظ…ط±ظˆط± ط§ظ„ط­ط§ظ„ظٹط© ط؛ظٹط± طµط­ظٹط­ط©."}, 400)
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
            self.send_json({"error": "ط§ط®طھط± ظ†ظˆط¹ظ‹ط§ طµط§ظ„ط­ظ‹ط§ ظ„ظ„ط±ط³ط§ظ„ط©."}, 400)
            return
        if not isinstance(content, str) or not content.strip():
            self.send_json({"error": "ط§ظƒطھط¨ ط±ط³ط§ظ„طھظƒ ظ‚ط¨ظ„ ط§ظ„ط¥ط±ط³ط§ظ„."}, 400)
            return
        content = content.strip()
        if len(content) > 3000:
            self.send_json(
                {"error": "ظٹط¬ط¨ ط£ظ„ط§ طھطھط¬ط§ظˆط² ط§ظ„ط±ط³ط§ظ„ط© 3000 ط­ط±ظپ."}, 400
            )
            return
        if not user:
            name = payload.get("name")
            email = payload.get("email")
            if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
                self.send_json({"error": "ط§ظƒطھط¨ ط§ط³ظ…ظ‹ط§ طµط§ظ„ط­ظ‹ط§ ظ„ظ„طھظˆط§طµظ„."}, 400)
                return
            if (
                not isinstance(email, str)
                or len(email.strip()) > 254
                or not re.fullmatch(
                    r"[^@\s]+@[^@\s]+\.[^@\s]+", email.strip()
                )
            ):
                self.send_json({"error": "ط£ط¯ط®ظ„ ط¨ط±ظٹط¯ظ‹ط§ ط¥ظ„ظƒطھط±ظˆظ†ظٹظ‹ط§ طµط§ظ„ط­ظ‹ط§."}, 400)
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
                {"error": "طھط¹ط°ظ‘ط± ط­ظپط¸ ط±ط³ط§ظ„طھظƒ. ط­ط§ظˆظ„ ظ…ط±ط© ط£ط®ط±ظ‰."}, 500
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
                {"error": "ظ„ظٹط³ ظ„ط¯ظٹظƒ طµظ„ط§ط­ظٹط© ظ„طھط؛ظٹظٹط± ظƒظ„ظ…ط§طھ ظ…ط±ظˆط± ط§ظ„ظ…ط³طھط®ط¯ظ…ظٹظ†."}, 403
            )
            return
        if target_user_id == user["id"]:
            self.send_json(
                {"error": "ط§ط³طھط®ط¯ظ… ط¥ط¹ط¯ط§ط¯ط§طھ ط­ط³ط§ط¨ظƒ ظ„طھط؛ظٹظٹط± ظƒظ„ظ…ط© ظ…ط±ظˆط±ظƒ."}, 400
            )
            return

        payload = self.read_json_body()
        if payload is None:
            return
        new_password = payload.get("newPassword")
        if not isinstance(new_password, str):
            self.send_json({"error": "ط£ط¯ط®ظ„ ظƒظ„ظ…ط© ظ…ط±ظˆط± ط¬ط¯ظٹط¯ط©."}, 400)
            return
        if not new_password or len(new_password) > 128:
            self.send_json({"error": "ظƒظ„ظ…ط© ط§ظ„ظ…ط±ظˆط± ط§ظ„ط¬ط¯ظٹط¯ط© ط؛ظٹط± طµط§ظ„ط­ط©."}, 400)
            return
        try:
            new_password.encode("utf-8")
        except UnicodeEncodeError:
            self.send_json({"error": "ط§ط³طھط®ط¯ظ… ط£ط­ط±ظپظ‹ط§ طµط§ظ„ط­ط© ظپظٹ ظƒظ„ظ…ط© ط§ظ„ظ…ط±ظˆط±."}, 400)
            return
        if len(new_password) < 10:
            self.send_json(
                {"error": "ط£ظ†ط´ط¦ ظƒظ„ظ…ط© ظ…ط±ظˆط± ظ…ظ† 10 ط£ط­ط±ظپ ط¹ظ„ظ‰ ط§ظ„ط£ظ‚ظ„."}, 400
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
                    "error": "ط§ظ„ط£ط¯ظ…ظ† ط؛ظٹط± ط§ظ„ط£ط³ط§ط³ظٹ ظ„ط§ ظٹظ…ظƒظ†ظ‡ طھط؛ظٹظٹط± ظƒظ„ظ…ط© ظ…ط±ظˆط± ط£ط¯ظ…ظ† ط¢ط®ط±."
                },
                403,
            )
            return
        if result == "not_found":
            self.send_json({"error": "ط§ظ„ظ…ط³طھط®ط¯ظ… ط؛ظٹط± ظ…ظˆط¬ظˆط¯."}, 404)
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

    def current_user(self):
        return get_database().get_session_user(self.session_token())

    def send_unauthorized(self):
        self.send_json({"error": "ط§ظ†طھظ‡طھ ط¬ظ„ط³ط© ط§ظ„ط¯ط®ظˆظ„. ط³ط¬ظ‘ظ„ ط§ظ„ط¯ط®ظˆظ„ ظ…ط±ط© ط£ط®ط±ظ‰."}, 401)

    def read_json_body(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_json({"error": "ط­ط¬ظ… ط§ظ„ط·ظ„ط¨ ط؛ظٹط± طµط§ظ„ط­."}, 400)
            return None
        if length <= 0 or length > MAX_REQUEST_BYTES:
            self.send_json(
                {"error": "ط­ط¬ظ… ط§ظ„ط·ظ„ط¨ ط؛ظٹط± طµط§ظ„ط­ ط£ظˆ ظٹطھط¬ط§ظˆط² ط§ظ„ط­ط¯ ط§ظ„ظ…ط³ظ…ظˆط­."}, 413
            )
            return None
        try:
            payload = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.send_json({"error": "طھط¹ط°ظ‘ط±طھ ظ‚ط±ط§ط،ط© ط¨ظٹط§ظ†ط§طھ ط§ظ„ط±ط³ط§ظ„ط©."}, 400)
            return None
        if not isinstance(payload, dict):
            self.send_json({"error": "طµظٹط؛ط© ط§ظ„ط±ط³ط§ظ„ط© ط؛ظٹط± طµط§ظ„ط­ط©."}, 400)
            return None
        return payload

    def send_sse(self, event, payload):
        body = json.dumps(payload, ensure_ascii=False)
        self.wfile.write(f"event: {event}\ndata: {body}\n\n".encode("utf-8"))
        self.wfile.flush()

    def send_image_creation_unavailable(self, conversation):
        answer = (
            "ظ…ط§ ط¨ظ‚ط¯ط± ط£ظ†ط´ط¦ طµظˆط±طŒ ظ„ط£ظ†ظٹ ظ…ط³ط§ط¹ط¯ ظ†طµظ‘ظٹ. "
            "ط¨ظ‚ط¯ط± ط£ط³ط§ط¹ط¯ظƒ ط¨ظƒطھط§ط¨ط© ظˆطµظپ ظ„ظ„طµظˆط±ط© ط£ظˆ طھط­ظ„ظٹظ„ طµظˆط±ط© طھط¨ط¹ط«ظ‡ط§."
        )
        try:
            get_database().complete_assistant_message(
                conversation["id"],
                answer,
                conversation["response_id"],
                user_id=conversation["user_id"],
                grade_question_asked=conversation["mark_grade_question_asked"],
            )
        except Database.error_types:
            self.send_json({"error": "طھط¹ط°ظ‘ط± ط­ظپط¸ ط§ظ„ط±ط¯ ظپظٹ ط³ط¬ظ„ ط§ظ„ظ…ط­ط§ط¯ط«ط©."}, 500)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        self.close_connection = True
        self.send_sse(
            "conversation",
            {
                "conversationId": conversation["id"],
                "title": conversation["title"],
            },
        )
        self.send_sse("delta", {"text": answer})
        self.send_sse(
            "done",
            {
                "responseId": conversation["response_id"] or "",
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
            print(f"طھط¹ط°ظ‘ط± ط¥ظ†ط´ط§ط، ط¹ظ†ظˆط§ظ† ط§ظ„ظ…ط­ط§ط¯ط«ط© ط¨ط§ظ„ط°ظƒط§ط، ط§ظ„ط§طµط·ظ†ط§ط¹ظٹ: {error}")
            conversation["title_warning"] = (
                "طھط¹ط°ظ‘ط± ط¥ظ†ط´ط§ط، ط¹ظ†ظˆط§ظ† ظ„ظ„ظ…ط­ط§ط¯ط«ط© طھظ„ظ‚ط§ط¦ظٹظ‹ط§ط› ظٹظ…ظƒظ†ظƒ طھط؛ظٹظٹط±ظ‡ ظ…ظ† ط³ط¬ظ„ ط§ظ„ظ…ط­ط§ط¯ط«ط§طھ."
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
                self.send_sse("error", {"error": "ط£ط¹ط§ط¯طھ Gemini ط­ط¯ط« ط¨ط« ط؛ظٹط± ظ…ظپظ‡ظˆظ…."})
                completed = True
                return

            if not isinstance(event_data, dict):
                self.send_sse("error", {"error": "ط£ط¹ط§ط¯طھ Gemini ط­ط¯ط« ط¨ط« ط؛ظٹط± ظ…ظپظ‡ظˆظ…."})
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
                    self.send_sse("error", {"error": "ظ„ظ… طھظڈط±ط¬ط¹ Gemini ط¥ط¬ط§ط¨ط© ظ†طµظٹط©."})
                elif not isinstance(response_id, str) or not response_id:
                    self.send_sse(
                        "error", {"error": "ظ„ظ… طھظڈط±ط¬ط¹ Gemini ظ…ط¹ط±ظ‘ظپ ط§ظ„ظ…ط­ط§ط¯ط«ط©."}
                    )
                else:
                    try:
                        conversation_title = conversation["title"]
                        save_started = time.perf_counter()
                        get_database().complete_assistant_message(
                            conversation["id"],
                            "".join(answer_parts),
                            response_id,
                            user_id=conversation["user_id"],
                            grade_question_asked=conversation[
                                "mark_grade_question_asked"
                            ],
                        )
                        self._record_chat_perf("save_assistant", save_started)
                    except Database.error_types:
                        if "save_started" in locals():
                            self._record_chat_perf("save_assistant", save_started)
                        self.send_sse(
                            "error",
                            {"error": "ظˆطµظ„ ط§ظ„ط±ط¯ ظ„ظƒظ† طھط¹ط°ظ‘ط± ط­ظپط¸ظ‡ ظپظٹ ط³ط¬ظ„ ط§ظ„ظ…ط­ط§ط¯ط«ط©."},
                        )
                    else:
                        done_payload = {
                            "responseId": response_id,
                            "conversationId": conversation["id"],
                            "title": conversation_title,
                        }
                        self.send_sse("done", done_payload)
                completed = True
            elif event_type in {"interaction.failed", "error"}:
                error = event_data.get("error")
                message = (
                    error.get("message") if isinstance(error, dict) else None
                )
                self.send_sse(
                    "error",
                    {
                        "error": message
                        if isinstance(message, str)
                        else "طھط¹ط°ظ‘ط± ط¹ظ„ظ‰ Gemini ط¥ظƒظ…ط§ظ„ ط§ظ„ط¥ط¬ط§ط¨ط©."
                    },
                )
                completed = True

        while not completed:
            try:
                raw_line = response.readline()
            except (URLError, TimeoutError, OSError) as error:
                self.send_sse(
                    "error", {"error": f"ط§ظ†ظ‚ط·ط¹ طھط¯ظپظ‚ Gemini: {error}"}
                )
                return True
            if not raw_line:
                if data_lines:
                    dispatch_event()
                break
            try:
                line = raw_line.decode("utf-8").rstrip("\r\n")
            except UnicodeDecodeError:
                self.send_sse("error", {"error": "طھط¹ط°ظ‘ط±طھ ظ‚ط±ط§ط،ط© طھط¯ظپظ‚ Gemini."})
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
    message["Subject"] = "ط±ظ…ط² ط§ط³طھط¹ط§ط¯ط© ظƒظ„ظ…ط© ط§ظ„ظ…ط±ظˆط± - ظپظ‡ظٹظ…"
    message["From"] = sender
    message["To"] = recipient
    message.set_content(
        "ظˆطµظ„ظ†ط§ ط·ظ„ط¨ ظ„ط¥ط¹ط§ط¯ط© طھط¹ظٹظٹظ† ظƒظ„ظ…ط© ظ…ط±ظˆط± ط­ط³ط§ط¨ظƒ ظپظٹ ظپظ‡ظٹظ….\n\n"
        f"ط±ظ…ط² ط§ظ„طھط­ظ‚ظ‚: {code}\n\n"
        "ط§ظ„ط±ظ…ط² طµط§ظ„ط­ ظ„ظ…ط¯ط© 10 ط¯ظ‚ط§ط¦ظ‚طŒ ظˆظٹظ…ظƒظ† ط§ط³طھط®ط¯ط§ظ…ظ‡ ظ…ط±ط© ظˆط§ط­ط¯ط©. "
        "ط¥ط°ط§ ظ„ظ… طھط·ظ„ط¨ ط¥ط¹ط§ط¯ط© ط§ظ„طھط¹ظٹظٹظ†طŒ ظپطھط¬ط§ظ‡ظ„ ظ‡ط°ظ‡ ط§ظ„ط±ط³ط§ظ„ط©."
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
    print(f"AI Chat ظٹط¹ظ…ظ„ ط¹ظ„ظ‰ http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nطھظ… ط¥ظٹظ‚ط§ظپ ط§ظ„ط®ط§ط¯ظ….")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

