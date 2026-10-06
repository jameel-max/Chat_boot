import subprocess
from pathlib import Path


# ============================================================
# SETTINGS
# ============================================================

PROJECT_ROOT = Path(
    r"C:\python projects\ai"
)

ROOT = PROJECT_ROOT / "books" / "الصف_الثامن"

PYTHON = PROJECT_ROOT / ".venv-1" / "Scripts" / "python.exe"

SOURCE = "المركز الوطني لتطوير المناهج"

SOURCE_URL = (
    "https://nccd.gov.jo/Ar/Pages/textbooks"
)


# ============================================================
# ONLY FAILED BOOKS
# ============================================================

FAILED_BOOKS = [
    {
        "filename": "كتاب الطالب لمادة العلوم الصف الثامن الفصل الأول.pdf",
        "subject": "العلوم",
        "semester": "الفصل الأول",
    },
    {
        "filename": "كتاب الطالب لمادة التربية المهنية الصف الثامن الفصل الثاني.pdf",
        "subject": "التربية المهنية",
        "semester": "الفصل الثاني",
    },
    {
        "filename": "كتاب الطالب لمادة الدراسات الاجتماعية للصف الثامن الفصل الثاني.pdf",
        "subject": "الدراسات الاجتماعية",
        "semester": "الفصل الثاني",
    },
    {
        "filename": "كتاب الطالب لمادة العلوم الصف الثامن الفصل الثاني.pdf",
        "subject": "العلوم",
        "semester": "الفصل الثاني",
    },
]


# ============================================================
# FIND PDF RECURSIVELY
# ============================================================

def find_pdf(filename):
    """
    يبحث عن الكتاب داخل الصف الثامن
    وجميع المجلدات الفرعية.
    """

    matches = list(
        ROOT.rglob(filename)
    )

    if matches:
        return matches[0]

    # محاولة بحث أكثر مرونة
    target = filename.strip().lower()

    for pdf in ROOT.rglob("*.pdf"):

        if pdf.name.strip().lower() == target:
            return pdf

    return None


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("استكمال فهرسة الكتب الفاشلة فقط")
    print("=" * 70)

    print(
        f"عدد الكتب المطلوب تشغيلها: {len(FAILED_BOOKS)}"
    )

    print(
        f"مجلد البحث: {ROOT}"
    )

    print("=" * 70)

    # --------------------------------------------------------
    # CHECK ROOT
    # --------------------------------------------------------

    if not ROOT.exists():

        raise RuntimeError(
            f"مجلد الصف الثامن غير موجود:\n{ROOT}"
        )

    # --------------------------------------------------------
    # CHECK PYTHON
    # --------------------------------------------------------

    if not PYTHON.exists():

        raise RuntimeError(
            f"Python غير موجود:\n{PYTHON}"
        )

    # --------------------------------------------------------
    # CHECK INDEX SCRIPT
    # --------------------------------------------------------

    index_script = (
        PROJECT_ROOT / "index_curriculum.py"
    )

    if not index_script.exists():

        raise RuntimeError(
            f"index_curriculum.py غير موجود:\n{index_script}"
        )

    # --------------------------------------------------------
    # LIST ALL PDFs
    # --------------------------------------------------------

    all_pdfs = list(
        ROOT.rglob("*.pdf")
    )

    print(
        f"تم العثور على {len(all_pdfs)} ملف PDF داخل المجلد."
    )

    # --------------------------------------------------------
    # COUNTERS
    # --------------------------------------------------------

    successful = 0
    failed = []

    # ========================================================
    # PROCESS ONLY FAILED BOOKS
    # ========================================================

    for number, book in enumerate(
        FAILED_BOOKS,
        1
    ):

        filename = book["filename"]
        subject = book["subject"]
        semester = book["semester"]

        print()
        print("=" * 70)

        print(
            f"[{number}/4] {filename}"
        )

        print(
            f"المادة: {subject}"
        )

        print(
            f"الفصل: {semester}"
        )

        print("=" * 70)

        # ----------------------------------------------------
        # FIND PDF
        # ----------------------------------------------------

        pdf = find_pdf(filename)

        if pdf is None:

            print()
            print(
                "❌ لم يتم العثور على ملف PDF."
            )

            print(
                "اسم الملف المطلوب:"
            )

            print(
                filename
            )

            failed.append(
                (
                    filename,
                    "ملف PDF غير موجود"
                )
            )

            continue

        # ----------------------------------------------------
        # FOUND
        # ----------------------------------------------------

        print()
        print(
            "✅ تم العثور على الكتاب:"
        )

        print(
            pdf
        )

        # ----------------------------------------------------
        # BUILD COMMAND
        # ----------------------------------------------------

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
            filename,

            "--source",
            SOURCE,

            "--source-url",
            SOURCE_URL,

            "--official",
        ]

        # ----------------------------------------------------
        # RUN INDEXING
        # ----------------------------------------------------

        print()
        print(
            "جاري تشغيل الفهرسة..."
        )

        try:

            result = subprocess.run(
                command,
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

        except Exception as error:

            print()
            print(
                "❌ تعذر تشغيل الفهرسة:"
            )

            print(
                error
            )

            failed.append(
                (
                    filename,
                    str(error)
                )
            )

            continue

        # ----------------------------------------------------
        # OUTPUT
        # ----------------------------------------------------

        if result.stdout:

            print()
            print(
                "----- OUTPUT -----"
            )

            print(
                result.stdout
            )

        # ----------------------------------------------------
        # ERRORS
        # ----------------------------------------------------

        if result.stderr:

            print()
            print(
                "----- ERROR / STDERR -----"
            )

            print(
                result.stderr
            )

        # ----------------------------------------------------
        # SUCCESS
        # ----------------------------------------------------

        if result.returncode == 0:

            successful += 1

            print()
            print(
                "✅ تمت معالجة الكتاب بنجاح:"
            )

            print(
                filename
            )

        # ----------------------------------------------------
        # FAILURE
        # ----------------------------------------------------

        else:

            error_message = (
                result.stderr.strip()
                if result.stderr
                else f"exit code {result.returncode}"
            )

            failed.append(
                (
                    filename,
                    error_message
                )
            )

            print()
            print(
                "❌ فشلت فهرسة الكتاب:"
            )

            print(
                filename
            )

            print()
            print(
                f"Exit code: {result.returncode}"
            )

    # ========================================================
    # FINAL REPORT
    # ========================================================

    print()
    print("=" * 70)
    print(
        "انتهت محاولة استكمال الكتب الأربعة"
    )
    print("=" * 70)

    print(
        f"نجح: {successful}/4"
    )

    print(
        f"فشل: {len(failed)}/4"
    )

    # --------------------------------------------------------
    # FAILED
    # --------------------------------------------------------

    if failed:

        print()
        print(
            "الكتب التي ما زالت تحتاج مراجعة:"
        )

        print("-" * 70)

        for filename, reason in failed:

            print()
            print(
                filename
            )

            print(
                "السبب:"
            )

            print(
                reason
            )

            print("-" * 70)

    # --------------------------------------------------------
    # ALL SUCCESS
    # --------------------------------------------------------

    else:

        print()
        print(
            "🎉 ممتاز!"
        )

        print(
            "الكتب الأربعة تمت فهرستها بنجاح."
        )

        print(
            "وبالتالي أصبحت الكتب الـ20 مكتملة."
        )

    print("=" * 70)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()