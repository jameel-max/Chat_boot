
"use strict";

const authOverlay = document.querySelector("#auth-overlay");
const authError = document.querySelector("#auth-error");
const authForm = document.querySelector("#auth-form");
const authEmail = document.querySelector("#auth-email");
const authPassword = document.querySelector("#auth-password");
const authPasswordConfirm = document.querySelector("#auth-password-confirm");
const authTitle = document.querySelector("#auth-title");
const authDescription = document.querySelector("#auth-description");
const authSubmit = document.querySelector("#auth-submit");
const authModeToggle = document.querySelector("#auth-mode-toggle");
const authNameLabel = document.querySelector("#auth-name-label");
const authNameHint = document.querySelector("#auth-name-hint");
const authGradeField = document.querySelector("#auth-grade-field");
const authConfirmGroup = document.querySelector("#auth-confirm-group");
const authPasswordHint = document.querySelector("#auth-password-hint");
const forgotPasswordLink = document.querySelector("#forgot-password-link");
const rememberDevice = document.querySelector("#remember-device");

let authMode = "login";
const PASSWORD_MIN_LENGTH = 10;
const NAME_PREFIXES = new Set(["عبد", "ابو", "ابن", "بن", "ام", "ال", "بنت"]);

async function apiRequest(url, options = {}) {
    const response = await fetch(url, {
        credentials: "same-origin",
        cache: "no-store",
        ...options,
    });

    const rawText = await response.text();
    let result = {};

    if (rawText.trim()) {
        try {
            result = JSON.parse(rawText);
        } catch {
            throw new Error("استجابة غير صالحة من الخادم.");
        }
    }

    if (!response.ok) {
        throw new Error(
            result.error || result.message || `حدث خطأ (HTTP ${response.status}).`
        );
    }

    return result;
}

function normalizeArabic(text) {
    return text
        .replace(/[\u064b-\u065f\u0670\u0640]/g, "")
        .replace(/[أإآٱ]/g, "ا")
        .replace(/ى/g, "ي")
        .replace(/ة/g, "ه")
        .replace(/\s+/g, " ")
        .trim();
}

function countNameTokens(text) {
    const words = normalizeArabic(text).split(" ").filter(Boolean);
    let count = 0;

    for (let i = 0; i < words.length; i++) {
        if (NAME_PREFIXES.has(words[i]) && i + 1 < words.length) i++;
        count++;
    }

    return count;
}

function validateFullName(text) {
    const normalized = normalizeArabic(text);

    if (!normalized) return "اكتب اسمك الرباعي.";

    if (!/^[\u0621-\u064a ]+$/.test(normalized)) {
        return "اكتب الاسم بالأحرف العربية فقط، دون أرقام أو رموز.";
    }

    const count = countNameTokens(text);

    if (count !== 4) {
        return `اكتب اسمك الرباعي كاملًا. عدد الأسماء التي كتبتها: ${count.toLocaleString("ar")}.`;
    }

    return "";
}

function updateNameHint() {
    if (authMode !== "register" || !authNameHint) return;

    const error = validateFullName(authEmail.value);
    const valid = !error && Boolean(authEmail.value.trim());

    authNameHint.textContent = valid
        ? "✓ اسم رباعي صحيح"
        : "اكتب اسمك، واسم أبيك، واسم جدك، واسم العائلة.";

    authNameHint.classList.toggle("ok", valid);
    authNameHint.classList.toggle("warn", Boolean(error) && Boolean(authEmail.value.trim()));
}

function setAuthMode(mode) {
    authMode = mode;
    const registering = mode === "register";

    authTitle.textContent = registering
        ? "أنشئ حسابك في فهيم"
        : "أهلًا بك في فهيم";

    authDescription.textContent = registering
        ? "اكتب اسمك الرباعي، واختر صفك، وأنشئ كلمة مرور لتبدأ."
        : "سجّل الدخول باسمك الرباعي وكلمة المرور للوصول إلى محادثاتك.";

    authSubmit.textContent = registering ? "إنشاء حساب" : "تسجيل الدخول";

    authModeToggle.textContent = registering
        ? "لديك حساب؟ سجّل الدخول"
        : "ليس لديك حساب؟ أنشئ حسابًا";

    forgotPasswordLink?.classList.toggle("hidden", registering);
    authGradeField?.classList.toggle("hidden", !registering);
    authConfirmGroup?.classList.toggle("hidden", !registering);
    authPasswordHint?.classList.toggle("hidden", !registering);
    authNameHint?.classList.toggle("hidden", !registering);

    authNameLabel.textContent = registering
        ? "الاسم الرباعي"
        : "الاسم الرباعي (أو البريد الإلكتروني للأدمن)";

    authEmail.autocomplete = registering ? "name" : "username";
    authEmail.placeholder = registering ? "مثال: محمد أحمد علي الحسن" : "اسمك الرباعي";
    authPassword.autocomplete = registering ? "new-password" : "current-password";
    authPassword.placeholder = registering ? "أنشئ كلمة مرور" : "أدخل كلمة المرور";
    authPassword.minLength = registering ? PASSWORD_MIN_LENGTH : 1;
    authPasswordConfirm.required = registering;

    authForm.querySelectorAll('input[name="grade"]').forEach((radio) => {
        radio.required = registering;
    });

    authError.textContent = "";
    updateNameHint();
}

authModeToggle.addEventListener("click", () => {
    setAuthMode(authMode === "login" ? "register" : "login");
});

authEmail.addEventListener("input", updateNameHint);

document.querySelectorAll(".password-toggle").forEach((button) => {
    button.addEventListener("click", () => {
        const field = button.closest(".password-field");
        const passwordInput = field?.querySelector("input");
        if (!passwordInput) return;

        const visible = passwordInput.type === "password";
        passwordInput.type = visible ? "text" : "password";
        button.textContent = visible ? "إخفاء" : "إظهار";
        button.setAttribute("aria-pressed", String(visible));
        button.setAttribute(
            "aria-label",
            `${visible ? "إخفاء" : "إظهار"} كلمة المرور`
        );
    });
});

authForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    authError.textContent = "";

    const registering = authMode === "register";
    let body;
    let endpoint;

    if (registering) {
        const nameError = validateFullName(authEmail.value);

        if (nameError) {
            authError.textContent = nameError;
            authEmail.focus();
            return;
        }

        const grade = authForm.querySelector('input[name="grade"]:checked')?.value;

        if (!grade) {
            authError.textContent = "اختر صفك الدراسي.";
            return;
        }

        if (authPassword.value.length < PASSWORD_MIN_LENGTH) {
            authError.textContent = `أنشئ كلمة مرور من ${PASSWORD_MIN_LENGTH} أحرف على الأقل.`;
            authPassword.focus();
            return;
        }

        if (authPassword.value !== authPasswordConfirm.value) {
            authError.textContent = "كلمتا المرور غير متطابقتين.";
            authPasswordConfirm.focus();
            return;
        }

        endpoint = "/api/auth/register";
        body = {
            fullName: authEmail.value.trim(),
            grade,
            password: authPassword.value,
            remember: rememberDevice.checked,
        };
    } else {
        if (!authForm.reportValidity()) return;

        endpoint = "/api/auth/login";
        body = {
            identifier: authEmail.value.trim(),
            password: authPassword.value,
            remember: rememberDevice.checked,
        };
    }

    authSubmit.disabled = true;

    try {
        await apiRequest(endpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });

        // الجلسة تُحفظ في ملف الارتباط؛ انتقل إلى التطبيق بعد نجاح الدخول.
        window.location.replace("/");
    } catch (error) {
        authError.textContent = error.message;
    } finally {
        authSubmit.disabled = false;
    }
});

// إذا كانت الجلسة فعالة، افتح التطبيق مباشرة.
(async () => {
    try {
        await apiRequest("/api/me");
        window.location.replace("/");
        return;
    } catch {
        // لا توجد جلسة فعالة؛ أبقِ صفحة الدخول ظاهرة.
    }

    let previouslyLoggedIn = false;

    try {
        previouslyLoggedIn =
            localStorage.getItem("faheem_logged_in_before") === "1";
    } catch {
        // قد يكون التخزين غير متاح.
    }

    setAuthMode(previouslyLoggedIn ? "login" : "register");
})();