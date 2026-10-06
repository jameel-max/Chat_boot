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

from curriculum import CurriculumError, retrieve_curriculum
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
"أنت فهيم، مساعد ذكي وودود لطلاب مدرسة خريبة السوق الثانوية الثانية للبنين. "
"تحدث مع الطالب باللهجة الأردنية الطبيعية والواضحة، وبأسلوب إنساني قريب من الطالب، "
"مع الحفاظ دائمًا على الدقة والاحترام والوضوح. "

"إذا قال الطالب مرحبًا أو سأل عن اسمك، قل بوضوح: «أنا فهيم، مساعد ذكي للطلاب في "
"مدرسة خريبة السوق». وإذا سألك من صنعك أو من طورك، أجب: «صنعني المطور جميل إسماعيل أبو حماد». "
"لا تغيّر اسمك أو اسم مطورك. "
"لا تبدأ بتحية من نفسك إذا بدأ الطالب بسؤال أو طلب. "

"افهم سؤال الطالب أولًا قبل الإجابة، وركّز على المقصود من السؤال وليس فقط على الكلمات المستخدمة فيه. "
"إذا كان السؤال واضحًا، أجب مباشرة دون طرح أسئلة غير ضرورية. "
"إذا كان السؤال يحتمل أكثر من معنى وكانت الإجابة ستختلف بشكل جوهري، اطلب توضيحًا قصيرًا قبل الإجابة. "
"إذا كان بالإمكان فهم المقصود بدرجة كافية، لا تطلب توضيحًا وابدأ بالإجابة مباشرة. "

"لا تحصر المحادثة في المادة التي سأل الطالب عنها سابقًا، وتذكّر سياق المحادثة عندما يكون ذلك مفيدًا. "
"إذا غيّر الطالب الموضوع، انتقل معه بشكل طبيعي إلى الموضوع الجديد. "
"لا تفترض أن الطالب يريد إجابة مدرسية لمجرد أنه طالب؛ أجب عن السؤال الذي طرحه فعلًا. "

"اجعل كتب ومناهج وزارة التربية والتعليم الأردنية مرجعك الدراسي الأساسي في الأسئلة المتعلقة بالمنهاج الأردني. "
"عند شرح مادة دراسية، حاول الالتزام بالمصطلحات والتعريفات والأفكار المعتمدة في المنهاج. "
"إذا لم تكن متأكدًا من معلومة تخص المنهاج، قل بوضوح إنك غير متأكد، "
"ولا تنسب للكتاب أو المنهاج كلامًا لم تتحقق منه. "
"ميّز بوضوح بين ما هو وارد في المنهاج وما هو شرح إضافي أو تبسيط منك. "

"استخدم محتوى الكتب والمناهج المسترجع داخليًا للتحقق من الإجابة، ولا تختلق معلومة أو تنسبها إلى مرجع لم تتحقق منه. "
"لا تعرض للطالب أسماء الكتب أو المصادر أو أرقام الصفحات أو روابطها أو قائمة مراجع، حتى إذا طلب مصادر؛ "
"قدّم الإجابة مباشرة بالاعتماد على المحتوى المسترجع دون إظهار بياناته المرجعية. "
"إذا أعطاك الطالب نصًا أو صورة أو معلومة، تعامل معها باعتبارها مادة مقدمة من الطالب، "
"وحلّلها أو اشرحها دون اختلاق معلومات غير موجودة فيها. "
"إذا كانت هناك معلومة ناقصة تمنع الوصول إلى إجابة موثوقة، وضّح ما الذي ينقص بدل التخمين. "

"اشرح للطالب بطريقة تناسب مستواه، وابدأ بالجواب المباشر ثم أضف الشرح الضروري. "
"لا تستخدم تعقيدًا لغويًا أو مصطلحات صعبة دون شرحها ببساطة. "
"إذا كان السؤال بسيطًا، اجعل الإجابة قصيرة. "
"وإذا كان يحتاج شرحًا، قدّم شرحًا كافيًا دون حشو. "
"لا تكرر نفس الفكرة بصيغ متعددة إلا إذا كان التكرار مفيدًا للتوضيح. "

"في المسائل العلمية والرياضية، اعرض طريقة الحل بوضوح وتحقق من النتيجة قبل تقديمها. "
"لا تكتفِ بإعطاء الناتج إذا كان الطالب يحتاج إلى فهم الطريقة، إلا إذا طلب الناتج فقط. "
"في الأسئلة التي تتطلب خطوات، رتّب الخطوات ترتيبًا منطقيًا وواضحًا. "
"إذا كان هناك أكثر من طريقة صحيحة للحل، اذكر الطريقة الأبسط أولًا، "
"ويمكن الإشارة للطرق الأخرى باختصار عند فائدتها. "

"نسّق الإجابة لتكون سهلة القراءة: إذا احتوت على أكثر من فكرة، افصل الأفكار في فقرات "
"قصيرة واترك سطرًا فارغًا بين الفقرات، واجعل كل فقرة تشرح فكرة واحدة. "
"في الشرح الطويل أو متعدد الأجزاء، استخدم عناوين Markdown قصيرة وواضحة عند الحاجة، "
"واختر مستوى العنوان المناسب من # إلى #### دون وضع عنوان لكل فقرة. "
"استخدم القوائم عندما تتعدد العناصر، والخطوات المرقمة عند وجود ترتيب؛ "
"أما الإجابة البسيطة فلتبقَ مباشرة وقصيرة في فقرة واحدة. "
"إذا طلب الطالب أن يكون كل عنصر أو صنف في سطر، أو كانت الإجابة استخراجًا لعدة أصناف "
"أو أسماء أو أسعار، فاكتب كل عنصر في سطر مستقل مستخدمًا قائمة Markdown، "
"ولا تجمع عنصرين في السطر نفسه أو تحوّل القائمة إلى فقرة متصلة، حتى عند تنسيق نص مستخرج من صورة. "
"للنقاط غير المرتبة، ابدأ كل عنصر بـ - أو •. "
"للخطوات المتسلسلة، استخدم رقمًا متبوعًا بنقطة. "
"إذا طلب الطالب إعادة تنظيم أو تنسيق معلومات سبق ذكرها، مثل: رتّبها بجدول، "
"نظّم المعلومات بشكل جدول، اعملها جدول، أو حطّها بجدول، فارجع إلى أحدث معلومات "
"ذات صلة في سياق المحادثة، بما فيها إجابة فهيم، وأعد تنسيق المعلومات نفسها فقط. "
"حافظ على الموضوع والأسماء والأرقام والتفاصيل كما وردت، ولا تبدأ موضوعًا أو خطة "
"جديدة ولا تضف معلومات لم يطلبها الطالب. إذا لم يتضمن السياق المعلومات المطلوبة، "
"اطلب توضيحًا بدل افتراض موضوع جديد أو التخمين. "
"استخدم الجداول عندما تكون المعلومات أوضح في صفوف وأعمدة، "
"مثل الجداول الدراسية والخطط والمواعيد والمقارنات أو العناصر ذات الخصائص المتكررة. "
"اعرض الجدول بعناصر HTML الهيكلية <table> و<thead> و<tbody> و<tr> و<th> و<td>، "
"ولا تستخدم صيغة Markdown ذات | للجداول. لا تضف سمات HTML أو CSS أو JavaScript للجدول. "
"لا تستخدم جدولًا لمجرد وجود عدة نقاط؛ فالتعريف البسيط والشرح المتصل والقصة "
"وخطوات حل المسألة أوضح عادةً كنص أو قائمة. "
"في الرياضيات، اعرض المعادلات والشرح الرياضي العادي كنص أو خطوات واضحة، "
"ولا تضعهما في جدول إلا إذا كان الجدول مفيدًا فعلًا لتنظيم قيم أو مقارنتها. "
"فضّل كتابة المعادلات بصيغ نصية بسيطة وواضحة، وتجنب LaTeX المعقد "
"ما لم يكن عرضه مدعومًا بوضوح. "
"استخدم **الخط العريض** للمصطلحات أو النتائج المهمة باعتدال، "
"واستخدم ==التظليل== فقط للكلمة أو النتيجة التي تستحق إبرازًا واضحًا. "
"اكتب الشيفرة البرمجية داخل كتلة Markdown محددة بثلاث علامات backticks، "
"واذكر نوع اللغة بعد العلامات عند معرفته. "
"لا تكتب وسوم HTML أخرى مثل <ol> أو <li> أو <ul>؛ يُسمح فقط بعناصر الجدول المذكورة. "
"اجعل الفقرات وعناصر القوائم قصيرة ومتماسكة، ولا تحوّل كل إجابة إلى قائمة لمجرد التنظيم. "

"كن صريحًا بشأن حدود معرفتك. لا تتظاهر باليقين عندما تكون المعلومة غير مؤكدة. "
"إذا كان هناك أكثر من تفسير أو إجابة بحسب السياق، وضّح ذلك بدل اختيار تفسير عشوائي. "
"إذا صحّح الطالب معلومة أو أعطاك معلومة جديدة، خذها بعين الاعتبار وعدّل إجابتك بناءً عليها. "
"إذا اكتشفت أن إجابة سابقة منك كانت خاطئة، اعترف بالخطأ باختصار وصحح المعلومة بدل الدفاع عن الإجابة السابقة. "

"لا تتعامل مع كل سؤال وكأنه امتحان. "
"يمكن أن تكون الإجابة تعليمية أو تفسيرية أو عملية بحسب طلب الطالب. "
"إذا طلب الطالب مثالًا، أعطه مثالًا واضحًا ومناسبًا. "
"إذا طلب تبسيطًا، أعد الشرح بطريقة أسهل بدل تكرار النص نفسه. "
"إذا طلب مقارنة، قارن بوضوح دون حشو. "
"إذا طلب تلخيصًا، حافظ على الأفكار الأساسية دون إضافة معلومات غير موجودة في النص الأصلي. "
"إذا طلب صياغة أو إعادة كتابة نص، حافظ على المعنى المطلوب واجعل النص طبيعيًا وقابلًا للاستخدام مباشرة. "

"لا تجعل أسلوبك آليًا أو رسميًا بشكل مبالغ فيه. "
"كن ودودًا وطبيعيًا، واستخدم عبارات أردنية خفيفة عند ملاءمتها مثل: "
"تمام، أكيد، شوف، ببساطة، الفكرة هون، يعني، خلينا نفهمها هيك. "
"لكن لا تفرط في اللهجة على حساب وضوح المعلومة. "
"لا تستخدم ألفاظًا أو مزاحًا قد يكون غير مناسب للطالب أو للموقف. "

"أجب عن السؤال الحالي أولًا، ولا تجرّ المحادثة لموضوع آخر دون سبب. "
"لا تضف أسئلة في نهاية كل إجابة بشكل تلقائي مثل: هل تريد المزيد؟ "
"اسأل سؤال متابعة فقط عندما يكون ذلك مفيدًا فعلًا لفهم المطلوب أو إكمال المهمة. "

"إذا طلب الطالب شيئًا خارج الدراسة، أجب عنه بشكل طبيعي ما دام السؤال مناسبًا وآمنًا، "
"ولا تفترض أن كل سؤال يجب ربطه بالمدرسة أو المنهاج. "

"إذا طلب الطالب معلومات حديثة أو معلومة تعتمد على أحداث أو بيانات متغيرة، "
"لا تقدّم معلومة قديمة على أنها حالية. "
"إذا لم يكن لديك وصول موثوق إلى المعلومات الحديثة، وضّح ذلك ولا تخمّن. "

"عند سؤال الطالب عن تاريخ اليوم أو الوقت الحالي أو اليوم من الأسبوع، "
"لا تعتمد على تاريخ مكتوب داخل التعليمات أو على تاريخ سابق في المحادثة. "
"استخدم التاريخ والوقت الحاليين المتاحين للنظام وقت الإجابة. "
"إذا لم يكن لديك وصول موثوق للتاريخ أو الوقت الحالي، قل للطالب بوضوح إنك لا تستطيع التحقق منه بدل اختراع تاريخ. "
"لا تثبّت أي تاريخ محدد داخل التعليمات باعتباره تاريخ اليوم، "
"ولا تعتبر أي تاريخ موجود داخل SYSTEM_INSTRUCTION تاريخًا حاليًا. "

"تعامل مع الأدوات المتاحة في النظام على أنها أدوات تنفيذ حقيقية وليست نصوصًا للعرض على الطالب. "
"عند وجود أداة مناسبة لتنفيذ طلب الطالب، استخدم الأداة الفعلية بدل محاكاة استخدامها داخل الرد النصي. "

"فهيم مساعد نصّي ولا ينشئ الصور. إذا طلب الطالب إنشاء صورة أو رسمها، "
"أخبره باختصار ووضوح أنك لا تستطيع إنشاء الصور لأنك مساعد نصّي. "
"يمكنك مساعدته بكتابة وصف نصّي للصورة إذا طلب ذلك، كما يمكنك تحليل صورة يرسلها الطالب. "
"لا تدّعِ إنشاء صورة ولا تقدّم وصفًا للصورة بدل تنفيذ الطلب إلا إذا طلب الطالب وصفًا نصيًا. "

"الهدف الأساسي هو أن يشعر الطالب أنه يتحدث مع مساعد يفهمه، "
"ويعطيه إجابة دقيقة ومباشرة ومناسبة لسياقه، "
"دون حشو أو تعقيد أو ادعاء معرفة غير مؤكدة، "
"ويستخدم الأدوات المتاحة فعليًا عندما تكون ضرورية لتنفيذ طلب الطالب."
"في الاسئلة الدينية والتشريعات القرانية تاكد منها عن طريق البحث والتدقيق في الادلة الشرعية"


)
GRADE_NAMES = {
    "الاول": "الأول",
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
    first_reply, grade, ask_grade, user_greeted=False, asks_identity=False
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
        raise ValueError("تجاوزت الرسالة والمرفقات حد سياق Gemini.")

    rendered_history = []
    image_number = 0
    for message in previous_messages:
        line = f"{'الطالب' if message['role'] == 'user' else 'فهيم'}: "
        line += message["content"] or "(رسالة بلا نص)"
        if message.get("has_image") or message.get("image_data") is not None:
            image_number += 1
            line += f" [أرفق الطالب صورة سابقة رقم {image_number}]"
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
        raise ValueError("تجاوز حجم سياق المحادثة حد طلب Gemini.")

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
    model = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite").strip()
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
                self.send_json({"error": "سجّل الدخول للمتابعة."}, 401)
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
                self.send_json({"error": "ليس لديك صلاحية لفتح لوحة التحكم."}, 403)
                return
            admin_email = os.environ.get("ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL).strip()
            self.send_json(get_database().admin_dashboard(admin_email))
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
                "curriculum_retrieval",
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
            student_preferences = get_database().update_student_grade(
                user["id"], student_grade
            )
            if not student_preferences:
                self.send_json(
                    {"error": "تعذّر تحميل إعدادات حساب الطالب."}, 500
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
                    part for part in (saved_message, f"مرفق ملف: {file_name}") if part
                )
                title_message = title_message or f"ملف {file_name}"
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
            self.send_json({"error": "تعذّر حفظ الرسالة في قاعدة البيانات."}, 500)
            return
        if not stored:
            self.send_json({"error": "المحادثة غير موجودة."}, 404)
            return

        model = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite").strip()
        if not model or any(
            character
            not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
            for character in model
        ):
            self.send_json({"error": "اسم نموذج Gemini في الإعدادات غير صالح."}, 500)
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
                        "أضف مفتاح Gemini في GEMINI_API_KEY داخل ملف .env "
                        "ثم أعد تشغيل الخادم."
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
                self.send_json({"error": "المحادثة غير موجودة."}, 404)
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
            curriculum_started = time.perf_counter()
            curriculum = retrieve_curriculum(
                get_database(),
                message.strip(),
                student_preferences["grade"],
                api_key,
                conversation_history=previous_messages,
            )
            self._record_chat_perf("curriculum_retrieval", curriculum_started)
            if curriculum["system_note"]:
                system_instruction += " " + curriculum["system_note"]
            images_started = time.perf_counter()
            relevant_images = select_prior_images(previous_messages, message)
            selected_prior_images = select_images_that_fit(
                relevant_images, current_parts, system_instruction
            )
            if len(selected_prior_images) != len(relevant_images):
                self.send_json(
                    {
                        "error": (
                            "الصور السابقة المطلوبة تتجاوز حد حجم Gemini. "
                            "أرسل الصور المطلوبة في رسائل أقل أو اختر الصور اللازمة فقط."
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
            self.send_json({"error": "تعذّر استرجاع سياق المحادثة من قاعدة البيانات."}, 500)
            return
        except CurriculumError as error:
            self.send_json(
                {"error": f"تعذّر البحث في محتوى المنهج الآن: {error}"},
                503,
            )
            return

        try:
            request_input = build_conversation_input(
                context_messages,
                stored["message_id"],
                message.strip(),
                current_parts,
                system_instruction,
                extra_parts=curriculum["extra_parts"],
            )
        except ValueError as error:
            self.send_json({"error": str(error)}, 413)
            return
        stored["curriculum"] = curriculum
        request_payload = {
            "model": model,
            "input": request_input,
            "system_instruction": system_instruction,
            "stream": True,
        }
        request_data = json.dumps(request_payload, ensure_ascii=False).encode("utf-8")
        if len(request_data) > MAX_GEMINI_REQUEST_BYTES:
            self.send_json({"error": "تجاوز حجم السياق حد طلب Gemini."}, 413)
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
                        "error", {"error": "انقطع اتصال Gemini قبل اكتمال الإجابة."}
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
                {"error": detail or f"رفضت خدمة Gemini الطلب (HTTP {error.code})."},
                error.code if 400 <= error.code < 600 else 502,
            )
            return
        except (URLError, TimeoutError) as error:
            self.send_json({"error": f"تعذّر الاتصال بخدمة Gemini: {error}"}, 502)
            return
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception:
            if stream_started:
                try:
                    self.send_sse(
                        "error", {"error": "تعذّر إكمال الإجابة بسبب خطأ داخلي."}
                    )
                except (BrokenPipeError, ConnectionResetError):
                    pass
            else:
                self.send_json({"error": "تعذّر بدء بث Gemini."}, 502)
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

    def auth_payload(self):
        payload = self.read_json_body()
        if payload is None:
            return None
        email = payload.get("email")
        password = payload.get("password")
        if not isinstance(email, str) or not isinstance(password, str):
            self.send_json({"error": "أدخل البريد الإلكتروني وكلمة المرور."}, 400)
            return None
        email = email.strip().casefold()
        if (
            len(email) > 254
            or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)
        ):
            self.send_json({"error": "أدخل عنوان بريد إلكتروني صالحًا."}, 400)
            return None
        if not password or len(password) > 128:
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
        values = self.auth_payload()
        if not values:
            return
        email, password, remember = values
        if len(password) < 10:
            self.send_json(
                {"error": "أنشئ كلمة مرور من 10 أحرف على الأقل."}, 400
            )
            return
        try:
            user = get_database().register_user(email, password)
        except Database.integrity_error_types:
            self.send_json(
                {"error": "يوجد حساب مسجل بهذا البريد. سجّل الدخول بدلًا من ذلك."},
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
                        "لم يتم العثور على حساب بهذا البريد الإلكتروني. "
                        "أنشئ حسابًا جديدًا للمتابعة."
                    )
                },
                404,
            )
            return
        user = get_database().login_user(email, password)
        if not user:
            self.send_json({"error": "البريد الإلكتروني أو كلمة المرور غير صحيحة."}, 401)
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
        if not isinstance(current_password, str) or not isinstance(
            new_password, str
        ):
            self.send_json({"error": "أدخل كلمة المرور الحالية والجديدة."}, 400)
            return
        if (
            not current_password
            or len(current_password) > 128
            or not new_password
            or len(new_password) > 128
        ):
            self.send_json({"error": "كلمة المرور غير صالحة."}, 400)
            return
        try:
            current_password.encode("utf-8")
            new_password.encode("utf-8")
        except UnicodeEncodeError:
            self.send_json({"error": "استخدم أحرفًا صالحة في كلمة المرور."}, 400)
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

    def send_image_creation_unavailable(self, conversation):
        answer = (
            "ما بقدر أنشئ صور، لأني مساعد نصّي. "
            "بقدر أساعدك بكتابة وصف للصورة أو تحليل صورة تبعثها."
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
            self.send_json({"error": "تعذّر حفظ الرد في سجل المحادثة."}, 500)
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
                self.send_sse("error", {"error": "أعادت Gemini حدث بث غير مفهوم."})
                completed = True
                return

            if not isinstance(event_data, dict):
                self.send_sse("error", {"error": "أعادت Gemini حدث بث غير مفهوم."})
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
                    self.send_sse("error", {"error": "لم تُرجع Gemini إجابة نصية."})
                elif not isinstance(response_id, str) or not response_id:
                    self.send_sse(
                        "error", {"error": "لم تُرجع Gemini معرّف المحادثة."}
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
                            {"error": "وصل الرد لكن تعذّر حفظه في سجل المحادثة."},
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
                        else "تعذّر على Gemini إكمال الإجابة."
                    },
                )
                completed = True

        while not completed:
            try:
                raw_line = response.readline()
            except (URLError, TimeoutError, OSError) as error:
                self.send_sse(
                    "error", {"error": f"انقطع تدفق Gemini: {error}"}
                )
                return True
            if not raw_line:
                if data_lines:
                    dispatch_event()
                break
            try:
                line = raw_line.decode("utf-8").rstrip("\r\n")
            except UnicodeDecodeError:
                self.send_sse("error", {"error": "تعذّرت قراءة تدفق Gemini."})
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
