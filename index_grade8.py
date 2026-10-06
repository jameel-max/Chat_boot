import subprocess
from pathlib import Path


# ============================================================
# SETTINGS
# ============================================================

ROOT = Path(
    r"C:\python projects\ai\books\الصف_الثامن"
)

PYTHON = Path(
    r"C:\python projects\ai\.venv-1\Scripts\python.exe"
)

PROJECT_ROOT = Path(
    r"C:\python projects\ai"
)

SOURCE = "المركز الوطني لتطوير المناهج"

SOURCE_URL = (
    "https://nccd.gov.jo/Ar/Pages/textbooks"
)


# ============================================================
# SUBJECTS
# ============================================================

SUBJECTS = [
    (
        "اللغة العربية",
        ["اللغة العربية", "كتاب عربي"],
    ),
    (
        "اللغة الإنجليزية",
        ["اللغة الإنجليزية"],
    ),
    (
        "الرياضيات",
        ["الرياضيات"],
    ),
    (
        "العلوم",
        ["العلوم"],
    ),
    (
        "التربية الإسلامية",
        ["التربية الإسلامية"],
    ),
    (
        "التربية المهنية",
        ["التربية المهنية"],
    ),
    (
        "الدراسات الاجتماعية",
        ["الدراسات الاجتماعية"],
    ),
    (
        "المهارات الرقمية",
        ["المهارات الرقمية"],
    ),
]


# ============================================================
# HELPERS
# ============================================================

def get_subject(filename):
    """
    تحديد المادة اعتمادًا على اسم ملف PDF.
    """

    for subject, keywords in SUBJECTS:
        for keyword in keywords:
            if keyword in filename:
                return subject

    raise RuntimeError(
        f"تعذر تحديد المادة للملف: {filename}"
    )


def get_semester(path):
    """
    تحديد الفصل الدراسي من مسار/اسم الملف.
    """

    path_text = str(path)

    if "الفصل_الأول" in path_text:
        return "الفصل الأول"

    if "الفصل_الثاني" in path_text:
        return "الفصل الثاني"

    raise RuntimeError(
        f"تعذر تحديد الفصل للملف: {path.name}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    # --------------------------------------------------------
    # CHECK PATHS
    # --------------------------------------------------------

    if not ROOT.exists():
        raise RuntimeError(
            f"مجلد الكتب غير موجود:\n{ROOT}"
        )

    if not PYTHON.exists():
        raise RuntimeError(
            f"Python غير موجود في المسار:\n{PYTHON}"
        )

    index_script = PROJECT_ROOT / "index_curriculum.py"

    if not index_script.exists():
        raise RuntimeError(
            f"ملف index_curriculum.py غير موجود:\n{index_script}"
        )

    # --------------------------------------------------------
    # FIND PDF FILES
    # --------------------------------------------------------

    files = sorted(
        ROOT.rglob("*.pdf")
    )

    print("=" * 70)
    print("فهرسة مناهج الصف الثامن")
    print("=" * 70)

    print(
        f"عدد ملفات PDF: {len(files)}"
    )

    print(
        f"مجلد الكتب: {ROOT}"
    )

    print(
        f"Python: {PYTHON}"
    )

    print("=" * 70)

    # --------------------------------------------------------
    # EXPECTED NUMBER OF BOOKS
    # --------------------------------------------------------

    if len(files) != 20:
        raise RuntimeError(
            "المتوقع 20 ملف PDF، "
            f"لكن تم العثور على {len(files)}"
        )

    # --------------------------------------------------------
    # COUNTERS
    # --------------------------------------------------------

    successful = 0
    failed = []

    # --------------------------------------------------------
    # PROCESS BOOKS
    # --------------------------------------------------------

    for number, pdf in enumerate(files, 1):

        # ====================================================
        # DETERMINE SUBJECT + SEMESTER
        # ====================================================

        try:

            subject = get_subject(
                pdf.name
            )

            semester = get_semester(
                pdf
            )

        except Exception as error:

            print()
            print("=" * 70)
            print(
                f"[{number}/20] خطأ في معلومات الكتاب"
            )
            print("=" * 70)

            print(
                f"الملف: {pdf.name}"
            )

            print(
                f"الخطأ: {error}"
            )

            print(
                "سيتم الانتقال للكتاب التالي."
            )

            print("=" * 70)

            failed.append(
                (
                    pdf.name,
                    str(error),
                )
            )

            continue

        # ====================================================
        # BOOK HEADER
        # ====================================================

        print()
        print("=" * 70)

        print(
            f"[{number}/20] {pdf.name}"
        )

        print(
            f"المادة: {subject}"
        )

        print(
            f"الفصل: {semester}"
        )

        print(
            "الحالة: فحص/استكمال الفهرسة..."
        )

        print("=" * 70)

        # ====================================================
        # BUILD COMMAND
        # ====================================================

        command = [
            str(PYTHON),

            str(index_script),

            "--pdf",
            str(pdf),

            "--grade",
            "الثامن",

            "--subject",
            subject,

            "--semester",
            semester,

            "--book-title",
            pdf.name,

            "--source",
            SOURCE,

            "--source-url",
            SOURCE_URL,

            "--official",
        ]

        # ====================================================
        # RUN INDEXING
        # ====================================================

        try:

            result = subprocess.run(
                command,
                cwd=PROJECT_ROOT,

                # التقاط مخرجات البرنامج
                capture_output=True,

                # تحويل المخرجات إلى نص
                text=True,

                # دعم العربية
                encoding="utf-8",

                # منع توقف السكربت بسبب مشكلة encoding
                errors="replace",
            )

        except Exception as error:

            print()
            print("=" * 70)
            print(
                "تعذر تشغيل الفهرسة"
            )
            print("=" * 70)

            print(
                f"الكتاب: {pdf.name}"
            )

            print(
                f"الخطأ: {error}"
            )

            print("=" * 70)

            failed.append(
                (
                    pdf.name,
                    str(error),
                )
            )

            continue

        # ====================================================
        # SHOW NORMAL OUTPUT
        # ====================================================

        if result.stdout:

            print()
            print("----- مخرجات index_curriculum.py -----")
            print(
                result.stdout
            )

        # ====================================================
        # SHOW ERROR OUTPUT
        # ====================================================

        if result.stderr:

            print()
            print("----- ERROR / STDERR -----")
            print(
                result.stderr
            )

        # ====================================================
        # RESULT
        # ====================================================

        if result.returncode == 0:

            successful += 1

            print()
            print(
                f"تمت معالجة الكتاب بنجاح ✅: "
                f"{pdf.name}"
            )

        else:

            # ------------------------------------------------
            # SAVE ERROR DETAILS
            # ------------------------------------------------

            error_details = (
                f"exit code {result.returncode}"
            )

            if result.stderr:
                error_details += (
                    "\n"
                    + result.stderr.strip()
                )

            failed.append(
                (
                    pdf.name,
                    error_details,
                )
            )

            # ------------------------------------------------
            # DISPLAY FAILURE
            # ------------------------------------------------

            print()
            print("=" * 70)

            print(
                f"فشلت فهرسة هذا الكتاب ❌"
            )

            print(
                f"الكتاب: {pdf.name}"
            )

            print(
                f"Exit code: {result.returncode}"
            )

            print()

            if result.stderr:

                print(
                    "الخطأ الحقيقي:"
                )

                print(
                    result.stderr
                )

            else:

                print(
                    "لم يتم إرسال رسالة خطأ إلى STDERR."
                )

            print(
                "سيتم الانتقال للكتاب التالي "
                "بدون إعادة الكتب السابقة."
            )

            print("=" * 70)

    # ========================================================
    # FINAL REPORT
    # ========================================================

    print()
    print("=" * 70)
    print("انتهت جولة فهرسة الصف الثامن.")
    print("=" * 70)

    print(
        f"إجمالي ملفات PDF: {len(files)}"
    )

    print(
        f"كتب انتهت/تمت معالجتها: {successful}"
    )

    print(
        f"كتب فشلت في هذه الجولة: {len(failed)}"
    )

    # ========================================================
    # FAILED BOOKS
    # ========================================================

    if failed:

        print()
        print(
            "الكتب التي تحتاج مراجعة:"
        )

        print("-" * 70)

        for filename, reason in failed:

            print()
            print(
                f"📕 {filename}"
            )

            print(
                f"السبب:"
            )

            print(
                reason
            )

            print("-" * 70)

        print()
        print(
            "ملاحظة:"
        )

        print(
            "الكتب والـchunks التي تم حفظها مسبقًا "
            "لن تتم إعادة فهرستها إذا كان "
            "index_curriculum.py يدعم الاستكمال."
        )

    # ========================================================
    # ALL SUCCESS
    # ========================================================

    else:

        print()
        print(
            "جميع الكتب عولجت بنجاح ✅"
        )

    print()
    print("=" * 70)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()