import subprocess
from pathlib import Path


ROOT = Path(
    r"C:\python projects\ai\books\الصف_الثامن"
)

PYTHON = Path(
    r"C:\python projects\ai\.venv-1\Scripts\python.exe"
)

SOURCE = "المركز الوطني لتطوير المناهج"

SOURCE_URL = (
    "https://nccd.gov.jo/Ar/Pages/textbooks"
)


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


def get_subject(filename):
    for subject, keywords in SUBJECTS:
        for keyword in keywords:
            if keyword in filename:
                return subject

    raise RuntimeError(
        f"تعذر تحديد المادة للملف: {filename}"
    )


def get_semester(path):
    path_text = str(path)

    if "الفصل_الأول" in path_text:
        return "الفصل الأول"

    if "الفصل_الثاني" in path_text:
        return "الفصل الثاني"

    raise RuntimeError(
        f"تعذر تحديد الفصل للملف: {path.name}"
    )


def main():
    if not ROOT.exists():
        raise RuntimeError(
            f"مجلد الكتب غير موجود: {ROOT}"
        )

    if not PYTHON.exists():
        raise RuntimeError(
            f"Python غير موجود في المسار: {PYTHON}"
        )

    files = sorted(
        ROOT.rglob("*.pdf")
    )

    print("=" * 60)
    print("فهرسة مناهج الصف الثامن")
    print(
        f"عدد ملفات PDF: {len(files)}"
    )
    print("=" * 60)

    if len(files) != 20:
        raise RuntimeError(
            "المتوقع 20 ملف PDF، "
            f"لكن تم العثور على {len(files)}"
        )

    successful = 0
    skipped_or_resumed = 0
    failed = []

    for number, pdf in enumerate(
        files,
        1,
    ):
        try:
            subject = get_subject(
                pdf.name
            )

            semester = get_semester(
                pdf
            )

        except Exception as error:
            print()
            print("=" * 60)
            print(
                f"[{number}/20] خطأ في معلومات الكتاب"
            )
            print(pdf.name)
            print(error)
            print(
                "سيتم الانتقال للكتاب التالي."
            )
            print("=" * 60)

            failed.append(
                (
                    pdf.name,
                    str(error),
                )
            )

            continue

        print()
        print("=" * 60)
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
        print("=" * 60)

        command = [
            str(PYTHON),
            "index_curriculum.py",
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

        try:
            result = subprocess.run(
                command,
                cwd=Path(
                    r"C:\python projects\ai"
                ),
            )

        except Exception as error:
            print()
            print(
                f"تعذر تشغيل الفهرسة: {error}"
            )

            failed.append(
                (
                    pdf.name,
                    str(error),
                )
            )

            continue

        if result.returncode == 0:
            successful += 1

            print()
            print(
                f"تمت معالجة الكتاب بنجاح ✅: "
                f"{pdf.name}"
            )

        else:
            failed.append(
                (
                    pdf.name,
                    f"exit code {result.returncode}",
                )
            )

            print()
            print(
                f"فشلت فهرسة هذا الكتاب ❌: "
                f"{pdf.name}"
            )

            print(
                "سيتم الانتقال للكتاب التالي "
                "بدون إعادة الكتب السابقة."
            )

    print()
    print("=" * 60)
    print("انتهت جولة فهرسة الصف الثامن.")
    print(
        f"إجمالي ملفات PDF: {len(files)}"
    )
    print(
        f"كتب انتهت/تمت معالجتها: {successful}"
    )
    print(
        f"كتب فشلت في هذه الجولة: {len(failed)}"
    )

    if failed:
        print()
        print("الكتب التي تحتاج إعادة تشغيل:")
        for filename, reason in failed:
            print(
                f"- {filename} ({reason})"
            )

        print()
        print(
            "شغّل index_grade8.py مرة أخرى؛ "
            "الكتب والـchunks المحفوظة لن تُعاد."
        )
    else:
        print()
        print(
            "جميع الكتب عولجت بنجاح ✅"
        )

    print("=" * 60)


if __name__ == "__main__":
    main()