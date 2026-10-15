const conversation = document.querySelector("#conversation");
const welcome = document.querySelector("#welcome");
const form = document.querySelector("#chat-form");
const input = document.querySelector("#message-input");
const sendButton = document.querySelector("#send-button");
const micButton = document.querySelector("#mic-button");
const imageInput = document.querySelector("#image-input");
const fileInput = document.querySelector("#file-input");
const imagePreview = document.querySelector("#image-preview");
const previewImage = document.querySelector("#preview-image");
const previewName = document.querySelector("#preview-name");
const filePreview = document.querySelector("#file-preview");
const fileNameLabel = document.querySelector("#file-name");
const toast = document.querySelector("#toast");
const historyList = document.querySelector("#history-list");
const historySearchToggle = document.querySelector("#history-search-toggle");
const historySearch = document.querySelector("#history-search");
const sidebar = document.querySelector(".sidebar");
const sidebarBackdrop = document.querySelector("#sidebar-backdrop");
const mobileMenuToggle = document.querySelector("#mobile-history-toggle");
const helpCenterButton = document.querySelector("#help-center-button");
const helpCenterOverlay = document.querySelector("#help-center-overlay");
const helpCenterCard = document.querySelector(".help-center-card");
const helpCenterForm = document.querySelector("#help-center-form");
const helpCenterDescription = document.querySelector("#help-center-description");
const helpGuestFields = document.querySelector("#help-guest-fields");
const helpGuestName = document.querySelector("#help-guest-name");
const helpGuestEmail = document.querySelector("#help-guest-email");
const helpCenterTitle = document.querySelector("#help-center-title");
const helpCategoryField = document.querySelector("#help-category-field");
const helpCategory = document.querySelector("#help-category");
const helpContent = document.querySelector("#help-content");
const helpContentLabel = document.querySelector("#help-content-label");
const helpSubmit = document.querySelector("#help-submit");
const helpError = document.querySelector("#help-error");
const profileName = document.querySelector("#profile-name");
const profileSettings = document.querySelector("#profile-settings");
const profileSettingsToggle = document.querySelector("#profile-settings-toggle");
const settingsOverlay = document.querySelector("#settings-overlay");
const closeSettingsButton = document.querySelector("#close-settings");
const usernameSettings = document.querySelector("#username-settings");
const usernameForm = document.querySelector("#username-form");
const usernameInput = document.querySelector("#username-input");
const usernameSubmit = document.querySelector("#username-submit");
const usernameMessage = document.querySelector("#username-message");
const phoneSettings = document.querySelector("#phone-settings");
const phoneForm = document.querySelector("#phone-form");
const phoneInput = document.querySelector("#phone-input");
const phoneSubmit = document.querySelector("#phone-submit");
const phoneMessage = document.querySelector("#phone-message");
const userAvatar = document.querySelector("#user-avatar");
const userAvatarFallback = document.querySelector("#user-avatar-fallback");
const logoutButton = document.querySelector("#logout-button");
const adminButton = document.querySelector("#admin-button");
const adminOverlay = document.querySelector("#admin-overlay");
const adminPageViews = document.querySelector("#admin-page-views");
const adminUniqueVisitors = document.querySelector("#admin-unique-visitors");
const adminUserCount = document.querySelector("#admin-user-count");
const adminAdminCount = document.querySelector("#admin-admin-count");
const adminUsers = document.querySelector("#admin-users");
const adminEmpty = document.querySelector("#admin-empty");
const adminUserSearch = document.querySelector("#admin-user-search");
const adminUserSearchPanel = document.querySelector("#admin-user-search-panel");
const adminNoSearchResults = document.querySelector("#admin-no-search-results");
const adminError = document.querySelector("#admin-error");
const adminTabs = [...document.querySelectorAll("[data-admin-tab]")];
const adminUsersView = document.querySelector("#admin-users-view");
const adminSupportView = document.querySelector("#admin-support-view");
const adminSupportMessages = document.querySelector("#admin-support-messages");
const adminSupportEmpty = document.querySelector("#admin-support-empty");
const adminSupportDeleteAll = document.querySelector("#admin-support-delete-all");
const adminPasswordDialog = document.querySelector("#admin-password-dialog");
const adminPasswordDescription = document.querySelector("#admin-password-description");
const adminPasswordForm = document.querySelector("#admin-password-form");
const adminNewPassword = document.querySelector("#admin-new-password");
const adminConfirmPassword = document.querySelector("#admin-confirm-password");
const adminPasswordSubmit = document.querySelector("#admin-password-submit");
const adminPasswordError = document.querySelector("#admin-password-error");
const changePasswordForm = document.querySelector("#change-password-form");
const currentPasswordInput = document.querySelector("#current-password");
const newPasswordInput = document.querySelector("#new-password");
const confirmPasswordInput = document.querySelector("#confirm-password");
const changePasswordSubmit = document.querySelector("#change-password-submit");
const passwordError = document.querySelector("#password-error");

/* ============================================================
 * دعم الرياضيات (LaTeX) عبر KaTeX
 * - يُحقن KaTeX (CSS + JS) من CDN تلقائيًا عند الحاجة.
 * - المعادلات السطرية: \( ... \)  أو $...$
 * - المعادلات المنفصلة: \[ ... \]  أو $$...$$ (سطر واحد أو عدة أسطر)
 * - تُحمى المعادلات من معالجة المارك داون حتى لا تتشوّه.
 * ============================================================ */
const KATEX_VERSION = "0.16.11";

(function injectMathStyles() {
  const style = document.createElement("style");
  style.textContent = [
    ".math-inline { white-space: normal; direction: ltr; unicode-bidi: isolate; }",
    ".math-block { display: block; text-align: center; direction: ltr; unicode-bidi: isolate;",
    "  margin: 0.75em 0; padding: 2px 4px; overflow-x: auto; overflow-y: hidden;",
    "  max-width: 100%; }",
    ".math-block > .katex-display { margin: 0; }",
    ".math-pending { font-family: var(--font-mono, ui-monospace, monospace);",
    "  white-space: pre-wrap; direction: ltr; unicode-bidi: isolate; }",
  ].join(" ");
  document.head.append(style);
})();

function loadKaTeX() {
  if (window.katex) return Promise.resolve();
  return new Promise((resolve) => {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = `https://cdn.jsdelivr.net/npm/katex@${KATEX_VERSION}/dist/katex.min.css`;
    document.head.append(link);

    const script = document.createElement("script");
    script.src = `https://cdn.jsdelivr.net/npm/katex@${KATEX_VERSION}/dist/katex.min.js`;
    script.onload = () => {
      document.querySelectorAll(".math-pending").forEach(renderPendingMath);
      resolve();
    };
    script.onerror = () => resolve();
    document.head.append(script);
  });
}
loadKaTeX();

const katexHtmlCache = new Map();

function katexHtml(latex, displayMode) {
  const key = `${displayMode ? "D" : "I"}:${latex}`;
  let html = katexHtmlCache.get(key);
  if (html === undefined) {
    html = window.katex.renderToString(latex, {
      displayMode,
      throwOnError: false,
      output: "html",
      strict: false,
    });
    if (katexHtmlCache.size > 400) katexHtmlCache.clear();
    katexHtmlCache.set(key, html);
  }
  return html;
}

function renderMath(parent, latex, displayMode) {
  const container = document.createElement(displayMode ? "div" : "span");
  container.className = displayMode ? "math-block" : "math-inline";
  if (window.katex) {
    try {
      container.innerHTML = katexHtml(latex, displayMode);
    } catch {
      container.textContent = latex;
    }
  } else {
    container.classList.add("math-pending");
    container.dataset.latex = latex;
    container.dataset.display = String(displayMode);
    container.textContent = latex;
  }
  parent.append(container);
}

function renderPendingMath(element) {
  const latex = element.dataset.latex;
  const displayMode = element.dataset.display === "true";
  if (!window.katex || typeof latex !== "string") return;
  try {
    element.innerHTML = katexHtml(latex, displayMode);
    element.classList.remove("math-pending");
    delete element.dataset.latex;
    delete element.dataset.display;
  } catch {
    element.textContent = latex;
  }
}

const mobileMenuQuery = window.matchMedia("(max-width: 760px)");
const SIDEBAR_COLLAPSED_KEY = "faheem_sidebar_collapsed";

function isSidebarVisible() {
  return mobileMenuQuery.matches
    ? sidebar.classList.contains("mobile-open")
    : !document.documentElement.classList.contains("sidebar-collapsed");
}

function syncSidebarToggle() {
  const visible = isSidebarVisible();
  mobileMenuToggle.setAttribute("aria-expanded", String(visible));
  mobileMenuToggle.setAttribute(
    "aria-label",
    visible ? "إغلاق القائمة الجانبية" : "فتح القائمة الجانبية",
  );
  sidebar.inert = !visible;
}

// الهاتف: القائمة تنزلق فوق المحتوى مع خلفية معتمة
function setMobileMenuOpen(isOpen) {
  const open = isOpen && mobileMenuQuery.matches;
  sidebar.classList.toggle("mobile-open", open);
  sidebarBackdrop.classList.toggle("visible", open);
  syncSidebarToggle();
}

// الزر الواحد: على الهاتف يفتح/يغلق الدرج، وعلى الشاشات الكبيرة يطوي/يوسّع القائمة
function toggleSidebar() {
  if (mobileMenuQuery.matches) {
    setMobileMenuOpen(!sidebar.classList.contains("mobile-open"));
    return;
  }
  const collapsed = document.documentElement.classList.toggle("sidebar-collapsed");
  try {
    localStorage.setItem(SIDEBAR_COLLAPSED_KEY, collapsed ? "1" : "0");
  } catch {
  }
  syncSidebarToggle();
}

syncSidebarToggle();
mobileMenuQuery.addEventListener("change", () => setMobileMenuOpen(false));

async function loadAdminSupportMessages() {
  adminError.textContent = "";
  adminSupportMessages.replaceChildren();
  adminSupportEmpty.classList.add("hidden");
  try {
    const result = await apiRequest("/api/admin/support-messages");
    for (const record of result.messages) {
      const item = document.createElement("article");
      item.className = "admin-support-item";
      const heading = document.createElement("div");
      heading.className = "admin-support-heading";
      const name = document.createElement("strong");
      name.textContent = record.user_name;
      const email = document.createElement("span");
      email.textContent = record.user_email;
      const category = document.createElement("span");
      category.className = `admin-support-category ${record.category}`;
      category.textContent = record.category === "complaint" ? "شكوى" : "رسالة";
      const date = document.createElement("time");
      date.dateTime = new Date(record.created_at * 1000).toISOString();
      date.textContent = new Date(record.created_at * 1000).toLocaleString("ar");
      const status = document.createElement("span");
      status.className = `admin-support-status ${record.status}`;
      status.textContent = record.status === "resolved" ? "تمت المعالجة" : "جديدة";
      heading.append(name, email, category, date, status);
      const content = document.createElement("p");
      content.className = "admin-support-content";
      content.textContent = record.content;
      item.append(heading, content);
      if (record.status === "new") {
        const resolve = document.createElement("button");
        resolve.type = "button";
        resolve.className = "admin-support-resolve";
        resolve.textContent = "وضع علامة تمت المعالجة";
        resolve.addEventListener("click", async () => {
          resolve.disabled = true;
          adminError.textContent = "";
          try {
            await apiRequest(
              `/api/admin/support-messages/${encodeURIComponent(record.id)}`,
              {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ status: "resolved" }),
              },
            );
            await loadAdminSupportMessages();
          } catch (error) {
            adminError.textContent = error.message;
            resolve.disabled = false;
          }
        });
        item.append(resolve);
      }
      adminSupportMessages.append(item);
    }
    const newCount = result.messages.filter((record) => record.status === "new").length;
    document.querySelector("#admin-support-tab").textContent =
      newCount ? `رسائل المساعدة (${newCount.toLocaleString("ar")})` : "رسائل المساعدة";
    adminSupportEmpty.classList.toggle("hidden", result.messages.length > 0);
    adminSupportDeleteAll.classList.toggle("hidden", result.messages.length === 0);
    adminSupportDeleteAll.dataset.count = String(result.messages.length);
  } catch (error) {
    adminError.textContent = error.message;
  }
}

adminSupportDeleteAll.addEventListener("click", async () => {
  const count = Number(adminSupportDeleteAll.dataset.count || 0);
  if (!window.confirm(`سيتم حذف جميع رسائل مركز المساعدة (${count.toLocaleString("ar")}) نهائيًا. هل أنت متأكد؟`)) {
    return;
  }
  adminSupportDeleteAll.disabled = true;
  adminError.textContent = "";
  try {
    await apiRequest("/api/admin/support-messages", { method: "DELETE" });
    await loadAdminSupportMessages();
  } catch (error) {
    adminError.textContent = error.message;
  } finally {
    adminSupportDeleteAll.disabled = false;
  }
});

function filterAdminList(list, search, emptyMessage, noResultsMessage) {
  const activeTab = adminTabs.find((tab) => tab.getAttribute("aria-selected") === "true")
    ?.dataset.adminTab || "users";
  const isAdminTab = activeTab === "admins";
  const query = isAdminTab ? "" : search.value.trim().toLocaleLowerCase();
  adminUserSearchPanel.classList.toggle("hidden", isAdminTab);
  let visibleCount = 0;
  for (const row of list.rows) {
    const email = row.cells[1].textContent.toLocaleLowerCase();
    const isInCategory = isAdminTab
      ? row.dataset.isAdmin === "true"
      : row.dataset.isAdmin !== "true";
    row.hidden = !isInCategory || !email.includes(query);
    if (!row.hidden) visibleCount += 1;
  }
  const categoryCount = [...list.rows].filter((row) =>
    isAdminTab ? row.dataset.isAdmin === "true" : row.dataset.isAdmin !== "true",
  ).length;
  emptyMessage.classList.toggle("hidden", categoryCount !== 0);
  noResultsMessage.classList.toggle(
    "hidden",
    isAdminTab || categoryCount === 0 || visibleCount !== 0,
  );
}

function filterAdminUsers() {
  filterAdminList(adminUsers, adminUserSearch, adminEmpty, adminNoSearchResults);
}

let selectedImage = null;
let selectedFile = null;
let recognition = null;
let toastTimer = null;
let currentConversationId = null;
let currentUser = null;

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("visible");
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => toast.classList.remove("visible"), 5000);
}

function serverStatusMessage(status) {
  if (status === 429) {
    return "الخادم مشغول حاليًا. انتظر قليلًا ثم اضغط «إعادة الإرسال»؛ رسالتك محفوظة.";
  }
  if (status === 502 || status === 503 || status === 504 || status >= 500) {
    return "واجه الخادم مشكلة مؤقتة. انتظر قليلًا ثم أعد المحاولة. إذا استمرت، حدّث الصفحة.";
  }
  return null;
}

function studentErrorMessage(error, fallback = "حدث خطأ غير متوقع.") {
  const message = error instanceof Error ? error.message : "";
  if (/failed to fetch|networkerror|load failed|network request failed/i.test(message)) {
    return "تعذّر الاتصال بالخادم. تحقق من اتصال الإنترنت ثم حاول مرة أخرى.";
  }
  return message || fallback;
}

function scrollToLatest() {
  conversation.scrollTop = conversation.scrollHeight;
}

const COPY_ICON =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h9"/></svg>';
const CHECK_ICON =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>';

async function copyToClipboard(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // ننتقل إلى الطريقة البديلة
  }
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.cssText = "position:fixed;top:0;left:-9999px;opacity:0";
  document.body.append(area);
  area.select();
  let copied = false;
  try {
    copied = document.execCommand("copy");
  } catch {
    copied = false;
  }
  area.remove();
  return copied;
}

function createCopyButton(className, label, getText) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.title = label;

  const icon = document.createElement("span");
  icon.className = "copy-icon";
  icon.setAttribute("aria-hidden", "true");
  icon.innerHTML = COPY_ICON;

  const text = document.createElement("span");
  text.className = "copy-label";
  text.setAttribute("aria-live", "polite");
  text.textContent = label;

  button.append(icon, text);

  let timer = 0;
  button.addEventListener("click", async () => {
    const copied = await copyToClipboard(getText());
    window.clearTimeout(timer);
    icon.innerHTML = copied ? CHECK_ICON : COPY_ICON;
    text.textContent = copied ? "تم النسخ" : "تعذّر النسخ";
    button.classList.toggle("copied", copied);
    if (!copied) showToast("تعذّر النسخ، انسخ النص يدويًا.");
    timer = window.setTimeout(() => {
      icon.innerHTML = COPY_ICON;
      text.textContent = label;
      button.classList.remove("copied");
    }, 1800);
  });
  return button;
}

// زر "نسخ الرد" تحت كل رد من فهيم (يُنسخ نص الرد الأصلي بما فيه الأكواد والمعادلات)
const RESEND_ICON =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/></svg>';

// زر "إعادة الإرسال" تحت رسالة الطالب: يعيد إرسال النص مع الصورة أو الملف المرفقين
function addResendAction(body, payload, messageElement) {
  if (!payload || body.querySelector(".message-actions")) return;
  const actions = document.createElement("div");
  actions.className = "message-actions";
  const button = document.createElement("button");
  button.type = "button";
  button.className = "resend-button";
  button.title = "إعادة إرسال الرسالة";
  button.disabled = isSending;
  const icon = document.createElement("span");
  icon.className = "copy-icon";
  icon.setAttribute("aria-hidden", "true");
  icon.innerHTML = RESEND_ICON;
  const label = document.createElement("span");
  label.textContent = "إعادة الإرسال";
  button.append(icon, label);
  button.addEventListener("click", () => {
    if (isSending) return;
    if (payload._completed) {
      payload.requestId = null;
      payload.retryRequest = false;
      payload._completed = false;
    } else {
      payload.retryRequest = true;
    }
    // إن لم يصل رد لهذه الرسالة (فشل أو إيقاف) نستبدلها بدل تكرارها
    const previousAssistant = messageElement?.nextElementSibling;
    if (
      payload.retryRequest &&
      previousAssistant?.classList.contains("assistant") &&
      previousAssistant.querySelector(".message-unsaved")
    ) {
      previousAssistant.remove();
    }
    const unanswered = messageElement && conversation.lastElementChild === messageElement;
    if (unanswered) messageElement.remove();
    deliverMessage(payload).catch((error) => {
      showToast(error instanceof Error ? error.message : "تعذّرت إعادة الإرسال.");
    });
  });
  actions.append(button);
  body.append(actions);
}

function addReplyActions(body, text) {
  if (!text || body.querySelector(".message-actions")) return;
  const actions = document.createElement("div");
  actions.className = "message-actions";
  actions.append(createCopyButton("copy-button", "نسخ الرد", () => text));
  body.append(actions);
}

function appendMessage(role, text, imageUrl = null) {
  welcome.classList.add("hidden");
  const message = document.createElement("article");
  message.className = `message ${role}`;

  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  avatar.textContent = role === "user" ? "أ" : "ف";

  const body = document.createElement("div");
  body.className = "message-body";
  const name = document.createElement("div");
  name.className = "message-name";
  name.textContent = role === "user" ? "أنت" : "فهيم";
  body.append(name);

  if (imageUrl) {
    const image = document.createElement("img");
    image.className = "message-image";
    image.src = imageUrl;
    image.alt = "الصورة المرفقة";
    body.append(image);
  }
  if (text) {
    const content = document.createElement("div");
    content.className = "message-text";
    renderMarkdown(content, text);
    body.append(content);
    if (role === "assistant") addReplyActions(body, text);
  }
  message.append(avatar, body);
  conversation.append(message);
  scrollToLatest();
  body.messageElement = message;
  return body;
}

// أثناء الإرسال يتحول زر الإرسال إلى زر إيقاف (لا يُعطَّل)
let isSending = false;
let activeRequest = null;

function setBusy(busy) {
  isSending = busy;
  input.disabled = busy;
  sendButton.classList.toggle("is-stop", busy);
  sendButton.setAttribute("aria-label", busy ? "إيقاف الرد" : "إرسال الرسالة");
  sendButton.title = busy ? "إيقاف الرد" : "إرسال";
  sendButton.setAttribute("aria-busy", String(busy));
  document.querySelectorAll(".resend-button").forEach((button) => {
    button.disabled = busy;
  });
}

function stopGeneration() {
  if (!activeRequest || activeRequest.stopped) return;
  activeRequest.stopped = true;
  activeRequest.controller.abort();
}

// تركيز مربع الكتابة تلقائيًا على الحاسوب فقط، حتى لا تظهر لوحة المفاتيح فجأة على الهاتف
const touchDevice = window.matchMedia("(pointer: coarse)");
function focusInputAuto() {
  if (touchDevice.matches || input.disabled) return;
  const blocked = document.querySelector(
    ".auth-overlay:not(.hidden):not(#auth-overlay), .settings-overlay:not(.hidden)",
  );
  if (blocked) return;
  input.focus({ preventScroll: true });
}

function parseMarkdownTableRow(line) {
  if (typeof line !== "string" || !line.includes("|")) return null;
  return line.trim().replace(/^\|/, "").replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function isMarkdownTableDivider(line, columnCount) {
  const cells = parseMarkdownTableRow(line);
  return cells?.length === columnCount
    && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

function createSafeTable(markup) {
  const parsed = new DOMParser().parseFromString(markup, "text/html");
  const sourceTable = parsed.body.querySelector("table");
  const sourceRows = sourceTable ? [...sourceTable.rows] : [];
  if (!sourceRows.length) return null;

  const wrapper = document.createElement("div");
  wrapper.className = "faheem-table-wrap";
  const table = document.createElement("table");
  table.className = "faheem-table";
  table.dir = "rtl";
  const head = document.createElement("thead");
  const headerRow = document.createElement("tr");
  for (const sourceCell of sourceRows[0].cells) {
    const cell = document.createElement("th");
    cell.scope = "col";
    appendInlineMarkdown(cell, sourceCell.textContent.trim());
    headerRow.append(cell);
  }
  head.append(headerRow);
  table.append(head);

  const body = document.createElement("tbody");
  for (const sourceRow of sourceRows.slice(1)) {
    const row = document.createElement("tr");
    for (const sourceCell of sourceRow.cells) {
      const cell = document.createElement("td");
      appendInlineMarkdown(cell, sourceCell.textContent.trim());
      row.append(cell);
    }
    body.append(row);
  }
  table.append(body);
  wrapper.append(table);
  return wrapper;
}

function renderMarkdown(element, text) {
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  element.replaceChildren();
  let paragraph = [];
  let list = null;
  let codeLines = null;
  let codeLanguage = "";
  let fenceCharacter = "";
  let fenceLength = 0;
  let mathLines = null;
  let mathClose = "";

  function flushParagraph() {
    if (!paragraph.length) return;
    const block = document.createElement("p");
    appendInlineMarkdown(block, paragraph.join(" "));
    element.append(block);
    paragraph = [];
  }

  function flushList() {
    if (!list) return;
    element.append(list);
    list = null;
  }

  function flushCode() {
    if (codeLines === null) return;
    const block = document.createElement("div");
    block.className = "code-block";
    block.dir = "ltr";

    const header = document.createElement("div");
    header.className = "code-header";
    const language = document.createElement("span");
    language.className = "code-language";
    language.textContent = codeLanguage || "code";
    const source = codeLines.join("\n");
    header.append(language, createCopyButton("code-copy", "نسخ", () => source));

    const pre = document.createElement("pre");
    pre.dir = "ltr";
    const code = document.createElement("code");
    codeLines.forEach((line) => {
      const lineElement = document.createElement("span");
      lineElement.className = "code-line";
      highlightCodeLine(lineElement, line);
      code.append(lineElement);
    });
    pre.append(code);
    block.append(header, pre);
    element.append(block);
    codeLines = null;
    codeLanguage = "";
    fenceCharacter = "";
    fenceLength = 0;
  }

  function flushMath() {
    if (mathLines === null) return;
    renderMath(element, mathLines.join("\n"), true);
    mathLines = null;
    mathClose = "";
  }

  for (let lineIndex = 0; lineIndex < lines.length; lineIndex += 1) {
    const line = lines[lineIndex];
    const trimmed = line.trim();

    // داخل كتلة رياضيات متعددة الأسطر: نجمع حتى نصل للإغلاق ($$ أو \])
    if (mathLines !== null) {
      const closeIndex = line.indexOf(mathClose);
      if (closeIndex === -1) {
        mathLines.push(line);
      } else {
        const before = line.slice(0, closeIndex);
        if (before.trim()) mathLines.push(before);
        const after = line.slice(closeIndex + mathClose.length).trim();
        flushMath();
        if (after) paragraph.push(after);
      }
      continue;
    }

    if (codeLines !== null) {
      const closingFence = new RegExp(
        `^ {0,3}${fenceCharacter}{${fenceLength},}\\s*$`,
      );
      if (closingFence.test(line)) flushCode();
      else codeLines.push(line);
      continue;
    }

    const fence = line.match(/^ {0,3}(`{3,}|~{3,})(.*)$/);
    if (fence) {
      flushParagraph();
      flushList();
      codeLines = [];
      fenceCharacter = fence[1][0];
      fenceLength = fence[1].length;
      codeLanguage = fence[2].trim().split(/\s+/)[0] || "";
      continue;
    }

    // كتلة رياضيات: تبدأ بـ $$ أو \[ في بداية السطر
    const mathFence = line.match(/^ {0,3}(\$\$|\\\[)(.*)$/);
    if (mathFence) {
      const closer = mathFence[1] === "$$" ? "$$" : "\\]";
      const rest = mathFence[2];
      const closeIndex = rest.indexOf(closer);
      flushParagraph();
      flushList();
      if (closeIndex !== -1) {
        // معادلة كاملة على سطر واحد
        renderMath(element, rest.slice(0, closeIndex).trim(), true);
        const tail = rest.slice(closeIndex + closer.length).trim();
        if (tail) paragraph.push(tail);
        continue;
      }
      // كتلة متعددة الأسطر
      mathLines = [];
      mathClose = closer;
      if (rest.trim()) mathLines.push(rest.trim());
      continue;
    }

    if (!trimmed) {
      flushParagraph();
      flushList();
      continue;
    }

    if (/^<table\b/i.test(trimmed)) {
      let tableEnd = lineIndex;
      while (tableEnd < lines.length && !/<\/table\s*>/i.test(lines[tableEnd])) {
        tableEnd += 1;
      }
      if (tableEnd < lines.length) {
        flushParagraph();
        flushList();
        const safeTable = createSafeTable(
          lines.slice(lineIndex, tableEnd + 1).join("\n"),
        );
        if (safeTable) element.append(safeTable);
        lineIndex = tableEnd;
        continue;
      }
    }

    const tableHeaders = parseMarkdownTableRow(trimmed);
    if (
      tableHeaders?.length > 1
      && isMarkdownTableDivider(lines[lineIndex + 1], tableHeaders.length)
    ) {
      flushParagraph();
      flushList();

      const wrapper = document.createElement("div");
      wrapper.className = "faheem-table-wrap";
      const table = document.createElement("table");
      table.className = "faheem-table";
      table.dir = "rtl";
      const head = document.createElement("thead");
      const headerRow = document.createElement("tr");
      for (const title of tableHeaders) {
        const cell = document.createElement("th");
        cell.scope = "col";
        appendInlineMarkdown(cell, title);
        headerRow.append(cell);
      }
      head.append(headerRow);
      table.append(head);

      const body = document.createElement("tbody");
      let rowIndex = lineIndex + 2;
      while (rowIndex < lines.length) {
        const cells = parseMarkdownTableRow(lines[rowIndex]);
        if (!cells || cells.length !== tableHeaders.length) break;
        const row = document.createElement("tr");
        for (const value of cells) {
          const cell = document.createElement("td");
          appendInlineMarkdown(cell, value);
          row.append(cell);
        }
        body.append(row);
        rowIndex += 1;
      }
      table.append(body);
      wrapper.append(table);
      element.append(wrapper);
      lineIndex = rowIndex - 1;
      continue;
    }

    const heading = trimmed.match(/^(#{1,4})\s+(.+?)\s*#*$/);
    if (heading) {
      flushParagraph();
      flushList();
      const block = document.createElement(`h${heading[1].length}`);
      appendInlineMarkdown(block, heading[2]);
      element.append(block);
      continue;
    }

    const orderedItem = trimmed.match(/^(?:[0-9٠-٩]+)[.)،-]\s+(.+)$/u);
    const unorderedItem = trimmed.match(/^[-*+•]\s+(.+)$/u);
    const item = orderedItem || unorderedItem;
    if (!item) {
      flushList();
      paragraph.push(trimmed);
      continue;
    }

    flushParagraph();
    const listType = orderedItem ? "ol" : "ul";
    if (list && list.tagName.toLowerCase() !== listType) flushList();
    if (!list) {
      list = document.createElement(listType);
      list.dir = "rtl";
    }
    const listItem = document.createElement("li");
    appendInlineMarkdown(listItem, item[1]);
    list.append(listItem);
  }

  flushParagraph();
  flushList();
  flushCode();
  flushMath();
}

function appendInlineMarkdown(parent, text) {
  // الرياضيات أولاً حتى لا تُعالَج كمارك داون (تتجنّب تشوّه * و_ و~ داخل LaTeX)
  const pattern = /(\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)|\$\$[\s\S]+?\$\$|\$(?!\s)(?:\\.|[^$\\\n])+?(?<!\s)\$(?!\d)|\[[^\]]+\]\(https?:\/\/[^)\s]+\)|https?:\/\/[^\s<>]+|\*\*[^*]+\*\*|__[^_]+__|==.+?==|~~.+?~~|\*[^*\n]+\*|_[^_\n]+_|`[^`\n]+`)/g;
  let position = 0;

  for (const match of text.matchAll(pattern)) {
    const index = match.index;
    if (index > position) {
      parent.append(document.createTextNode(text.slice(position, index)));
    }

    const token = match[0];

    // معادلة منفصلة داخل النص: \[...\] أو $$...$$
    if (token.startsWith("\\[") || token.startsWith("$$")) {
      renderMath(parent, token.slice(2, -2).trim(), true);
      position = index + token.length;
      continue;
    }
    // معادلة سطرية: \(...\)
    if (token.startsWith("\\(")) {
      renderMath(parent, token.slice(2, -2).trim(), false);
      position = index + token.length;
      continue;
    }
    // معادلة سطرية: $...$
    if (token.startsWith("$")) {
      renderMath(parent, token.slice(1, -1).trim(), false);
      position = index + token.length;
      continue;
    }

    const markdownLink = token.match(/^\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)$/);
    if (markdownLink) {
      appendSafeLink(parent, markdownLink[1], markdownLink[2]);
      position = index + token.length;
      continue;
    }
    if (/^https?:\/\//i.test(token)) {
      const url = token.replace(/[.,!?؟،;:]+$/u, "");
      appendSafeLink(parent, url, url);
      parent.append(document.createTextNode(token.slice(url.length)));
      position = index + token.length;
      continue;
    }

    const marker = ["**", "__", "==", "~~"].find((item) =>
      token.startsWith(item),
    ) || token[0];
    const content = token.slice(marker.length, token.length - marker.length);
    const tagName = marker === "**" || marker === "__"
      ? "strong"
      : marker === "=="
        ? "mark"
        : marker === "~~"
          ? "del"
          : marker === "`"
            ? "code"
            : "em";
    const formatted = document.createElement(tagName);
    if (tagName !== "code" && /\\[(\[]|\$/.test(content)) {
      appendInlineMarkdown(formatted, content);
    } else {
      formatted.textContent = content;
    }
    parent.append(formatted);
    position = index + token.length;
  }

  if (position < text.length) {
    parent.append(document.createTextNode(text.slice(position)));
  }
}

function appendSafeLink(parent, label, href) {
  let linkUrl;
  try {
    linkUrl = new URL(href);
  } catch {
    parent.append(document.createTextNode(label));
    return;
  }
  if (
    !["http:", "https:"].includes(linkUrl.protocol) ||
    linkUrl.username ||
    linkUrl.password
  ) {
    parent.append(document.createTextNode(label));
    return;
  }

  const link = document.createElement("a");
  link.href = linkUrl.href;
  link.textContent = label;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  parent.append(link);
}

function highlightCodeLine(lineElement, text) {
  const tokenPattern = /(?:\/\*.*?\*\/|\/\/.*|(?:^|\s)#.*|<!--.*?-->)|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`|\b(?:const|let|var|function|return|if|else|for|while|class|new|import|from|export|default|async|await|def|print|in|is|not|and|or|True|False|None|true|false|null|undefined|public|private|static|void|int|float|string|bool|try|catch|throw|extends|implements|package|SELECT|FROM|WHERE|INSERT|UPDATE|DELETE|CREATE|TABLE)\b|\b\d+(?:\.\d+)?\b|<\/?[A-Za-z][^>]*>/g;
  let position = 0;

  for (const match of text.matchAll(tokenPattern)) {
    const index = match.index;
    if (index > position) {
      lineElement.append(document.createTextNode(text.slice(position, index)));
    }

    const token = match[0];
    const className = /^(?:\/\*|\/\/|#|<!--)/.test(token)
      ? "code-comment"
      : /^(?:"|'|`)/.test(token)
        ? "code-string"
        : /^\d/.test(token)
          ? "code-number"
          : /^</.test(token)
            ? "code-tag"
            : "code-keyword";
    const span = document.createElement("span");
    span.className = className;
    span.textContent = token;
    lineElement.append(span);
    position = index + token.length;
  }

  if (position < text.length) {
    lineElement.append(document.createTextNode(text.slice(position)));
  }
}

async function readGeminiStream(response, assistantBody, name, answer, state = {}) {
  if (!response.body) throw new Error("المتصفح لا يدعم استقبال البث.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let eventName = "";
  let dataLines = [];
  let answerText = "";
  let responseId = null;
  let conversationId = null;
  let conversationTitle = null;
  let answerVisible = false;
  let streamComplete = false;
  let shownLength = 0;
  let frameId = 0;

  // نرسم إطارًا واحدًا كحد أقصى لكل رسم شاشة، ونكشف جزءًا من النص المستلَم
  // (كلما زاد المتراكم زادت السرعة) فيبدو البث متصلًا حتى لو وصل على دفعات كبيرة.
  function paintAnswer() {
    frameId = 0;
    const backlog = answerText.length - shownLength;
    if (backlog <= 0) return;
    let step = Math.max(2, Math.ceil(backlog / (streamComplete ? 3 : 6)));
    shownLength = Math.min(answerText.length, shownLength + step);
    const lastCode = answerText.charCodeAt(shownLength - 1);
    if (lastCode >= 0xd800 && lastCode <= 0xdbff && shownLength < answerText.length) {
      shownLength += 1;
    }
    const nearBottom =
      conversation.scrollHeight - conversation.scrollTop - conversation.clientHeight < 160;
    renderMarkdown(answer, answerText.slice(0, shownLength));
    if (nearBottom) scrollToLatest();
    if (shownLength < answerText.length) frameId = requestAnimationFrame(paintAnswer);
  }

  function schedulePaint() {
    if (!frameId) frameId = requestAnimationFrame(paintAnswer);
  }

  function flushPaint() {
    if (frameId) {
      cancelAnimationFrame(frameId);
      frameId = 0;
    }
    if (!answerVisible) return;
    const nearBottom =
      conversation.scrollHeight - conversation.scrollTop - conversation.clientHeight < 160;
    shownLength = answerText.length;
    renderMarkdown(answer, answerText);
    if (nearBottom) scrollToLatest();
  }

  function finishPainting() {
    return new Promise((resolve) => {
      const deadline = performance.now() + 700;
      const check = () => {
        if (shownLength >= answerText.length || performance.now() > deadline) {
          flushPaint();
          resolve();
          return;
        }
        setTimeout(check, 30);
      };
      check();
    });
  }

  function dispatchEvent() {
    if (!dataLines.length) return;
    let eventData;
    try {
      eventData = JSON.parse(dataLines.join("\n"));
    } catch {
      throw new Error("وصلت بيانات بث غير مفهومة من الخادم.");
    }
    dataLines = [];

    if (eventName === "delta") {
      if (typeof eventData.text !== "string") {
        throw new Error("وصل جزء غير صالح من إجابة فهيم.");
      }
      if (!answerVisible) {
        assistantBody.replaceChildren(name, answer);
        answerVisible = true;
      }
      answerText += eventData.text;
      state.answerText = answerText;
      schedulePaint();
    } else if (eventName === "conversation") {
      if (
        typeof eventData.conversationId !== "string" ||
        typeof eventData.title !== "string"
      ) {
        throw new Error("لم تصل بيانات المحادثة المحفوظة.");
      }
      conversationId = eventData.conversationId;
      conversationTitle = eventData.title;
      currentConversationId = conversationId;
    } else if (eventName === "title") {
      if (typeof eventData.title !== "string") {
        throw new Error("وصل عنوان غير صالح للمحادثة.");
      }
      conversationTitle = eventData.title;
    } else if (eventName === "title_warning") {
      if (typeof eventData.message !== "string") {
        throw new Error("وصل تنبيه غير صالح عن عنوان المحادثة.");
      }
      showToast(eventData.message);
    } else if (eventName === "done") {
      if (typeof eventData.responseId !== "string") {
        throw new Error("لم يصل معرّف المحادثة من Gemini.");
      }
      responseId = eventData.responseId;
      conversationId = eventData.conversationId || conversationId;
      conversationTitle = eventData.title || conversationTitle;
      streamComplete = true;
    } else if (eventName === "error") {
      const error = new Error(
        typeof eventData.error === "string"
          ? eventData.error
          : "تعذّر إكمال الإجابة.",
      );
      error.code = eventData.code;
      throw error;
    }
    eventName = "";
  }

  function processLine(line) {
    if (line === "") {
      dispatchEvent();
    } else if (line.startsWith("event:")) {
      eventName = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }

  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });
      buffer = buffer.replace(/\r\n/g, "\n");
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      lines.forEach(processLine);
      if (streamComplete) {
        try {
          await reader.cancel();
        } catch {
        }
        break;
      }
      if (done) break;
    }
    if (buffer) processLine(buffer);
    processLine("");
  } finally {
    if (!streamComplete) {
      flushPaint();
      try {
        await reader.cancel();
      } catch {
      }
    }
    reader.releaseLock();
  }

  if (!streamComplete || !answerText) {
    throw new Error("انتهى البث قبل اكتمال إجابة فهيم.");
  }
  await finishPainting();
  return {
    answer: answerText,
    responseId,
    conversationId,
    title: conversationTitle,
  };
}

function setSelectedImage(file) {
  removeSelectedFile();
  selectedImage = file;
  previewImage.src = URL.createObjectURL(file);
  previewName.textContent = file.name;
  imagePreview.classList.remove("hidden");
}

function removeSelectedImage() {
  if (previewImage.src.startsWith("blob:")) URL.revokeObjectURL(previewImage.src);
  previewImage.removeAttribute("src");
  previewName.textContent = "";
  imageInput.value = "";
  selectedImage = null;
  imagePreview.classList.add("hidden");
}

function documentMimeType(fileName) {
  const extension = fileName.split(".").pop()?.toLowerCase();
  return {
    pdf: "application/pdf",
    txt: "text/plain",
    md: "text/markdown",
    csv: "text/csv",
    json: "application/json",
    html: "text/html",
    xml: "application/xml",
  }[extension] || "";
}

function setSelectedFile(file) {
  removeSelectedImage();
  selectedFile = file;
  fileNameLabel.textContent = file.name;
  filePreview.classList.remove("hidden");
}

function removeSelectedFile() {
  fileNameLabel.textContent = "";
  fileInput.value = "";
  selectedFile = null;
  filePreview.classList.add("hidden");
}

function readImageAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => {
      if (typeof reader.result !== "string") {
        reject(new Error("تعذّرت قراءة الصورة."));
        return;
      }
      resolve(reader.result);
    });
    reader.addEventListener("error", () => reject(new Error("تعذّرت قراءة الصورة.")));
    reader.readAsDataURL(file);
  });
}

async function apiRequest(url, options = {}) {
  const { suppressAuthOverlay = false, ...requestOptions } = options;

  let response;
  try {
    response = await fetch(url, {
      cache: "no-store",
      credentials: "same-origin",
      ...requestOptions,
    });
  } catch (error) {
    throw new Error(studentErrorMessage(error, "تعذّر الاتصال بالخادم. حاول مرة أخرى."));
  }

  if (!response.ok) {
    const serverMessage = serverStatusMessage(response.status);
    if (serverMessage) {
      if (response.status === 401 && !suppressAuthOverlay) {
        redirectToLogin("expired");
      }
      throw new Error(serverMessage);
    }

    let detail = "تعذّر إكمال الطلب.";

    try {
      const rawText = await response.text();

      if (rawText.trim()) {
        try {
          const result = JSON.parse(rawText);
          detail = result?.error || result?.message || detail;
        } catch {
          // الرد ليس JSON، نستخدم النص نفسه إذا كان مفيدًا
          detail = rawText.trim().slice(0, 500) || detail;
        }
      } else {
        detail = `تعذّر إكمال الطلب (HTTP ${response.status}).`;
      }
    } catch {
      detail = `تعذّر إكمال الطلب (HTTP ${response.status}).`;
    }

    if (response.status === 401 && !suppressAuthOverlay) {
      redirectToLogin("expired");
    }

    throw new Error(detail);
  }

  if (response.status === 204) {
    return null;
  }

  const rawText = await response.text();

  if (!rawText.trim()) {
    throw new Error(`الخادم أعاد استجابة فارغة (HTTP ${response.status}).`);
  }

  try {
    return JSON.parse(rawText);
  } catch {
    throw new Error("الخادم أعاد استجابة غير صالحة بصيغة JSON.");
  }
}


// صفحة الدخول وإنشاء الحساب أصبحت مستقلة (login.html)
function redirectToLogin(reason = "") {
  try {
    sessionStorage.setItem("faheem_bounce", String(Date.now()));
  } catch {
    // التخزين غير متاح
  }
  window.location.replace(reason ? `/login.html?reason=${encodeURIComponent(reason)}` : "/login.html");
}

function setAuthenticated(user, isAdmin = false, isPrimaryAdmin = false) {
  currentUser = { ...user, isAdmin, isPrimaryAdmin };
  profileName.textContent = user.name;
  usernameSettings.classList.toggle("hidden", !user.isStudentAccount);
  phoneSettings.classList.toggle("hidden", !user.isStudentAccount);
  usernameInput.value = user.name || "";
  helpCenterButton.classList.remove("hidden");
  profileSettings.classList.remove("hidden");
  logoutButton.classList.remove("hidden");
  adminButton.classList.toggle("hidden", !isAdmin);
  userAvatarFallback.classList.add("hidden");
  if (user.picture) {
    userAvatar.src = user.picture;
    userAvatar.classList.remove("hidden");
  } else {
    userAvatar.classList.add("hidden");
    userAvatarFallback.textContent = (user.name || user.email).slice(0, 1);
    userAvatarFallback.classList.remove("hidden");
  }
  try {
    localStorage.setItem(LOGGED_IN_BEFORE_KEY, "1");
  } catch {
    // التخزين غير متاح
  }
  afterAuthenticated();
}

async function loadAdminDashboard() {
  adminError.textContent = "";
  adminUsers.replaceChildren();
  try {
    const result = await apiRequest("/api/admin/dashboard");
    adminPageViews.textContent = Number(result.pageViews).toLocaleString("ar");
    adminUniqueVisitors.textContent = Number(result.uniqueVisitors).toLocaleString("ar");
    const users = result.users.filter((user) => !user.is_admin).length;
    const admins = result.users.length - users;
    adminUserCount.textContent = users.toLocaleString("ar");
    adminAdminCount.textContent = admins.toLocaleString("ar");
    for (const user of result.users) {
      const isAdmin = Boolean(user.is_admin);
      const isPrimaryAdmin = Boolean(user.is_primary_admin);
      const row = document.createElement("tr");
      const name = document.createElement("td");
      name.textContent = user.name;
      const email = document.createElement("td");
      email.textContent = user.email;
      const created = document.createElement("td");
      created.textContent = new Date(user.created_at * 1000).toLocaleDateString("ar");
      const action = document.createElement("td");
      row.dataset.isAdmin = String(isAdmin);
      const isOtherUser = user.id !== currentUser.id;
      const canManageSensitiveActions = isOtherUser
        && (!isAdmin || currentUser.isPrimaryAdmin);
      const role = document.createElement("span");
      role.className = isAdmin ? "admin-role-badge active" : "admin-role-badge";
      role.textContent = isPrimaryAdmin
        ? "الأدمن الأساسي"
        : isAdmin ? "أدمن" : "مستخدم";
      action.append(role);
      if (isOtherUser && !isPrimaryAdmin) {
        const toggleAdmin = document.createElement("button");
        toggleAdmin.type = "button";
        toggleAdmin.className = "admin-role-action";
        toggleAdmin.textContent = isAdmin ? "إزالة الأدمن" : "جعله أدمن";
        toggleAdmin.setAttribute(
          "aria-label",
          isAdmin
            ? `إزالة صلاحية الأدمن من ${user.email}`
            : `جعل ${user.email} أدمن`,
        );
        toggleAdmin.addEventListener("click", async () => {
          toggleAdmin.disabled = true;
          adminError.textContent = "";
          try {
            await apiRequest(
              `/api/admin/users/${encodeURIComponent(user.id)}/admin`,
              {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ isAdmin: !isAdmin }),
              },
            );
            await loadAdminDashboard();
          } catch (error) {
            adminError.textContent = error.message;
            toggleAdmin.disabled = false;
          }
        });
        action.append(toggleAdmin);
      } else if (user.id === currentUser.id) {
        const selfLabel = document.createElement("span");
        selfLabel.className = "admin-self-label";
        selfLabel.textContent = "حسابك";
        action.append(selfLabel);
      }
      if (canManageSensitiveActions) {
        const changePassword = document.createElement("button");
        changePassword.type = "button";
        changePassword.className = "admin-password-action";
        changePassword.textContent = "تغيير كلمة المرور";
        changePassword.setAttribute("aria-label", `تغيير كلمة مرور ${user.email}`);
        changePassword.addEventListener("click", () => {
          adminPasswordForm.dataset.userId = user.id;
          adminPasswordForm.reset();
          adminPasswordError.textContent = "";
          adminPasswordDescription.textContent =
            `عيّن كلمة مرور جديدة للحساب ${user.email}. سيتم تسجيل خروجه من أجهزته.`;
          adminPasswordDialog.classList.remove("hidden");
          adminNewPassword.focus();
        });
        action.append(changePassword);
      }
      if (canManageSensitiveActions && !isPrimaryAdmin) {
        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "admin-delete";
        remove.textContent = "حذف";
        remove.setAttribute("aria-label", `حذف حساب ${user.email}`);
        remove.addEventListener("click", async () => {
          if (!window.confirm(`هل تريد حذف حساب ${user.email} وكل محادثاته نهائيًا؟`)) {
            return;
          }
          remove.disabled = true;
          try {
            await apiRequest(`/api/admin/users/${encodeURIComponent(user.id)}`, {
              method: "DELETE",
            });
            await loadAdminDashboard();
          } catch (error) {
            adminError.textContent = error.message;
            remove.disabled = false;
          }
        });
        action.append(remove);
      }
      row.append(name, email, created, action);
      adminUsers.append(row);
    }
    filterAdminUsers();
  } catch (error) {
    adminError.textContent = error.message;
  }
}

async function refreshAdminStatistics() {
  const result = await apiRequest("/api/admin/statistics");
  adminPageViews.textContent = Number(result.pageViews).toLocaleString("ar");
  adminUniqueVisitors.textContent = Number(result.uniqueVisitors).toLocaleString("ar");
}

function closeAdminPasswordDialog() {
  adminPasswordDialog.classList.add("hidden");
  adminPasswordForm.reset();
  delete adminPasswordForm.dataset.userId;
  adminPasswordError.textContent = "";
}

adminPasswordForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!adminPasswordForm.reportValidity()) return;
  adminPasswordError.textContent = "";
  if (adminNewPassword.value !== adminConfirmPassword.value) {
    adminPasswordError.textContent = "كلمتا المرور الجديدتان غير متطابقتين.";
    adminConfirmPassword.focus();
    return;
  }
  const userId = adminPasswordForm.dataset.userId;
  if (!userId) {
    adminPasswordError.textContent = "اختر حسابًا لتغيير كلمة مروره.";
    return;
  }

  adminPasswordSubmit.disabled = true;
  try {
    await apiRequest(`/api/admin/users/${encodeURIComponent(userId)}/password`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ newPassword: adminNewPassword.value }),
    });
    closeAdminPasswordDialog();
    showToast("تم تغيير كلمة المرور وإنهاء جلسات المستخدم.");
  } catch (error) {
    adminPasswordError.textContent = error.message;
  } finally {
    adminPasswordSubmit.disabled = false;
  }
});

document.querySelector("#cancel-admin-password").addEventListener("click", closeAdminPasswordDialog);

function renderHistory(conversations) {
  const scrollTop = historyList.scrollTop;
  historyList.replaceChildren();
  if (!conversations.length) {
    const empty = document.createElement("div");
    empty.className = "history-empty";
    empty.textContent = historySearch.value.trim()
      ? "لا توجد محادثات تطابق البحث."
      : "ستظهر محادثاتك هنا بعد بدء محادثة جديدة.";
    historyList.append(empty);
    return;
  }

  for (const record of conversations) {
    const entry = document.createElement("div");
    entry.className = "history-entry";
    entry.dataset.id = record.id;
    if (record.id === currentConversationId) entry.classList.add("active");

    const title = document.createElement("button");
    title.type = "button";
    title.className = "history-title";
    title.textContent = record.title;
    title.title = record.title;
    entry.dataset.title = record.title.toLocaleLowerCase();
    title.addEventListener("click", () => {
      loadConversation(record.id).catch((error) => showToast(error.message));
    });

    const rename = document.createElement("button");
    rename.type = "button";
    rename.className = "history-action";
    rename.textContent = "✎";
    rename.title = "تعديل العنوان";
    rename.setAttribute("aria-label", `تعديل عنوان ${record.title}`);
    rename.addEventListener("click", () => renameConversation(record));

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "history-action delete";
    remove.textContent = "×";
    remove.title = "حذف المحادثة";
    remove.setAttribute("aria-label", `حذف ${record.title}`);
    remove.addEventListener("click", () => deleteConversation(record));

    entry.append(title, rename, remove);
    historyList.append(entry);
  }
  filterHistory();
  historyList.scrollTop = scrollTop;
}

function filterHistory() {
  const query = historySearch.value.trim().toLocaleLowerCase();
  let matches = 0;
  for (const entry of historyList.querySelectorAll(".history-entry")) {
    entry.classList.toggle("hidden", !entry.dataset.title.includes(query));
    if (!entry.classList.contains("hidden")) matches += 1;
  }
  const empty = historyList.querySelector(".history-empty");
  if (!empty && matches === 0) {
    const noResults = document.createElement("div");
    noResults.className = "history-empty";
    noResults.textContent = "لا توجد محادثات تطابق البحث.";
    historyList.append(noResults);
  } else if (empty && matches > 0) {
    empty.remove();
  } else if (empty && matches === 0) {
    empty.textContent = query
      ? "لا توجد محادثات تطابق البحث."
      : "ستظهر محادثاتك هنا بعد بدء محادثة جديدة.";
  } else if (matches > 0) {
    empty?.remove();
  }
}

async function loadHistory() {
  const result = await apiRequest("/api/conversations");
  renderHistory(result.conversations.filter((item) => !pendingDeletes.has(item.id)));
}

const CONVERSATION_LOADER_DELAY_MS = 120;
let conversationLoadToken = 0;
let loadingConversationId = null;

function markActiveHistoryEntry(id) {
  for (const entry of historyList.querySelectorAll(".history-entry")) {
    entry.classList.toggle("active", entry.dataset.id === id);
  }
}

function createConversationLoader() {
  const loader = document.createElement("div");
  loader.className = "convo-loader";
  loader.setAttribute("role", "status");
  loader.setAttribute("aria-live", "polite");

  const stage = document.createElement("div");
  stage.className = "convo-loader__stage";
  const glow = document.createElement("div");
  glow.className = "convo-loader__glow";

  const picture = document.createElement("picture");
  const source = document.createElement("source");
  source.srcset = "/loader-robot.webp";
  source.type = "image/webp";
  const robot = document.createElement("img");
  robot.className = "convo-loader__robot";
  robot.src = "/loader-robot.png";
  robot.alt = "";
  robot.width = 420;
  robot.height = 510;
  robot.decoding = "async";
  robot.draggable = false;
  picture.append(source, robot);

  const shadow = document.createElement("div");
  shadow.className = "convo-loader__shadow";
  stage.append(glow, picture, shadow);

  const text = document.createElement("p");
  text.className = "convo-loader__text";
  text.textContent = "جارٍ فتح المحادثة";
  const dots = document.createElement("span");
  dots.className = "loader-dots";
  dots.setAttribute("aria-hidden", "true");
  for (let index = 0; index < 3; index += 1) {
    dots.append(document.createElement("i"));
  }
  text.append(dots);

  loader.append(stage, text);
  return loader;
}

async function loadConversation(id) {
  if (isSending) {
    showToast("انتظر حتى ينتهي فهيم من الرد ثم افتح المحادثة.");
    return;
  }
  // ضغط متكرر على نفس المحادثة أثناء فتحها: نتجاهله بدل إرسال طلبات مكررة
  if (loadingConversationId === id) return;

  const token = ++conversationLoadToken;
  loadingConversationId = id;
  markActiveHistoryEntry(id);
  setMobileMenuOpen(false);

  // إن تأخر الفتح نعرض الروبوت فورًا ليعرف الطالب أن المحادثة تُحمَّل
  let loaderShown = false;
  const loaderTimer = window.setTimeout(() => {
    if (token !== conversationLoadToken) return;
    loaderShown = true;
    welcome.classList.add("hidden");
    conversation.replaceChildren(createConversationLoader());
    conversation.setAttribute("aria-busy", "true");
  }, CONVERSATION_LOADER_DELAY_MS);

  let result;
  try {
    result = await apiRequest(`/api/conversations/${encodeURIComponent(id)}`);
  } catch (error) {
    if (token === conversationLoadToken) {
      if (loaderShown) {
        conversation.replaceChildren(welcome);
        welcome.classList.remove("hidden");
        currentConversationId = null;
      }
      markActiveHistoryEntry(currentConversationId);
    }
    throw error;
  } finally {
    window.clearTimeout(loaderTimer);
    if (token === conversationLoadToken) {
      loadingConversationId = null;
      conversation.removeAttribute("aria-busy");
    }
  }

  // اختار الطالب محادثة أخرى (أو بدأ محادثة جديدة) أثناء التحميل
  if (token !== conversationLoadToken) return;

  currentConversationId = result.conversation.id;
  conversation.replaceChildren();
  welcome.classList.add("hidden");

  for (const message of result.messages) {
    const imageUrl = message.image
      ? `data:${message.image.mimeType};base64,${message.image.data}`
      : null;
    const body = appendMessage(message.role, message.content, imageUrl);
    if (message.role === "user" && !/مرفق ملف:/.test(message.content || "")) {
      addResendAction(
        body,
        {
          conversationId: result.conversation.id,
          text: message.content || "",
          image: message.image
            ? { mimeType: message.image.mimeType, data: message.image.data }
            : null,
          file: null,
          displayedImage: imageUrl,
          displayedFileName: null,
        },
        body.messageElement,
      );
    }
  }
  if (!result.messages.length) {
    welcome.classList.remove("hidden");
    conversation.append(welcome);
  }
  focusInputAuto();
  await loadHistory();
}

async function renameConversation(record) {
  const title = window.prompt("اكتب عنوان المحادثة:", record.title);
  if (title === null || !title.trim()) return;
  try {
    await apiRequest(`/api/conversations/${encodeURIComponent(record.id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
    await loadHistory();
  } catch (error) {
    showToast(error.message);
  }
}

// محادثات تُحذف في الخلفية: نخفيها من القائمة فورًا حتى لو أعاد الخادم نسخة قديمة منها
const pendingDeletes = new Set();

function sendConversationDelete(id, attempt = 0) {
  fetch(`/api/conversations/${encodeURIComponent(id)}`, {
    method: "DELETE",
    credentials: "same-origin",
    cache: "no-store",
    keepalive: true, // يكتمل الطلب حتى لو أُغلقت الصفحة
  })
    .then((response) => {
      if (response.ok || response.status === 404) {
        pendingDeletes.delete(id);
        return;
      }
      throw new Error(`HTTP ${response.status}`);
    })
    .catch(() => {
      if (attempt < 2) {
        window.setTimeout(() => sendConversationDelete(id, attempt + 1), 1500 * (attempt + 1));
        return;
      }
      pendingDeletes.delete(id);
      showToast("تعذّر إكمال حذف المحادثة، ستعود إلى القائمة.");
      loadHistory().catch(() => {});
    });
}

function deleteConversation(record) {
  if (!window.confirm(`هل تريد حذف محادثة «${record.title}» نهائيًا؟`)) return;
  const isActive = currentConversationId === record.id || loadingConversationId === record.id;
  if (isActive && isSending) {
    showToast("انتظر حتى ينتهي فهيم من الرد ثم احذف المحادثة.");
    return;
  }

  pendingDeletes.add(record.id);

  // 1) إزالة فورية من قائمة المحادثات
  for (const entry of historyList.querySelectorAll(".history-entry")) {
    if (entry.dataset.id === record.id) entry.remove();
  }
  if (!historyList.querySelector(".history-entry")) renderHistory([]);

  // 2) العودة فورًا إلى الواجهة الرئيسية (شعار المدرسة والاختصارات)
  if (isActive) resetChat();

  // 3) الحذف الفعلي من قاعدة البيانات في الخلفية دون انتظار
  sendConversationDelete(record.id);
}

// ===== شاشة التحميل: تظهر أثناء التحقق من الجلسة بدل وميض نافذة تسجيل الدخول =====
const appLoader = document.querySelector("#app-loader");
const LOADER_MIN_MS = 700;
const LOADER_MAX_MS = 12000;
const LOGGED_IN_BEFORE_KEY = "faheem_logged_in_before";
const loaderStartedAt = performance.now();

function hideAppLoader() {
  if (!appLoader || appLoader.dataset.done) return;
  appLoader.dataset.done = "1";
  const wait = Math.max(0, LOADER_MIN_MS - (performance.now() - loaderStartedAt));
  window.setTimeout(() => {
    appLoader.classList.add("is-hidden");
    const remove = () => appLoader.remove();
    appLoader.addEventListener("transitionend", remove, { once: true });
    window.setTimeout(remove, 900);
  }, wait);
}

// إن تعذّر الخادم طويلًا لا نترك الشاشة عالقة: ننتقل إلى صفحة الدخول
window.setTimeout(() => {
  if (appLoader && !appLoader.dataset.done) redirectToLogin();
}, LOADER_MAX_MS);

async function initializeApp() {
  try {
    const result = await apiRequest("/api/me", { suppressAuthOverlay: true });
    setAuthenticated(result.user, result.isAdmin, result.isPrimaryAdmin);
  } catch (error) {
    // لا جلسة صالحة: ننتقل إلى صفحة الدخول (شاشة التحميل تبقى ظاهرة حتى يكتمل الانتقال)
    redirectToLogin();
    return;
  }
  try {
    await loadHistory();
  } catch (error) {
    showToast(error.message);
  }
  hideAppLoader();
}

const ACTIVITY_CREATE_PATTERN =
  /(اكتب|اكتبي|أنشئ|انشئ|ألّف|ألف|صمّم|صمم|ولّد|ولد|لخّص|لخص|تلخيص|مقال|موضوع تعبير|قصيدة|قصة|رسالة|برنامج|كود|خطة|جدول|اختبار|أسئلة)/;

// يحدد حالة فهيم من طلب الطالب: تحليل مرفق، إنشاء محتوى، أو تفكير عادي
function detectActivity(text, hasImage, hasFile) {
  if (hasImage) {
    return {
      state: "analyzing",
      labels: ["فهيم يحلّل الصورة", "يقرأ التفاصيل", "يربطها بسؤالك"],
    };
  }
  if (hasFile) {
    return {
      state: "analyzing",
      labels: ["فهيم يقرأ الملف", "يحلّل محتواه", "يستخرج المهم"],
    };
  }
  if (ACTIVITY_CREATE_PATTERN.test(text)) {
    return {
      state: "creating",
      labels: ["فهيم ينشئ المحتوى", "يصيغ النص", "يراجع الصياغة"],
    };
  }
  return {
    state: "thinking",
    labels: ["فهيم يفكّر", "يرتّب أفكاره", "يجهّز الإجابة"],
  };
}

function createActivityIndicator({ state, labels }) {
  const indicator = document.createElement("div");
  indicator.className = "typing";
  indicator.dataset.state = state;
  indicator.setAttribute("aria-label", labels[0]);

  const icon = document.createElement("span");
  icon.className = "typing-icon";
  icon.setAttribute("aria-hidden", "true");
  for (let index = 0; index < 3; index += 1) {
    icon.append(document.createElement("b"));
  }

  const label = document.createElement("span");
  label.className = "typing-label";
  label.textContent = labels[0];

  indicator.append(icon, label);
  for (let index = 0; index < 3; index += 1) {
    indicator.append(document.createElement("i"));
  }

  let step = 0;
  const timer = window.setInterval(() => {
    if (!indicator.isConnected) {
      window.clearInterval(timer);
      return;
    }
    step = (step + 1) % labels.length;
    label.textContent = labels[step];
    indicator.setAttribute("aria-label", labels[step]);
  }, 2600);

  return indicator;
}

// ===== حصة المرفقات اليومية =====
const quotaRow = document.querySelector("#quota-row");
const quotaText = document.querySelector("#quota-text");
let uploadQuota = null;

function renderUploadQuota() {
  if (!quotaRow) return;
  if (!uploadQuota || uploadQuota.unlimited) {
    quotaRow.classList.add("hidden");
    return;
  }
  const left = uploadQuota.remaining;
  quotaRow.classList.remove("hidden");
  quotaRow.classList.toggle("empty", left <= 0);
  quotaRow.classList.toggle("low", left === 1);
  const number = (value) => Number(value).toLocaleString("ar");
  quotaText.textContent =
    left > 0
      ? `متبقي لك ${number(left)} من ${number(uploadQuota.limit)} مرفقات اليوم`
      : "انتهت مرفقاتك لهذا اليوم، عُد غدًا";
}

async function refreshUploadQuota() {
  try {
    const result = await apiRequest("/api/uploads/quota", { suppressAuthOverlay: true });
    uploadQuota = result.quota;
    renderUploadQuota();
  } catch {
    // العدّاد غير ضروري لعمل الدردشة
  }
}

function ensureUploadAllowed() {
  if (!uploadQuota || uploadQuota.unlimited || uploadQuota.remaining > 0) return true;
  showToast("انتهت مرفقاتك لهذا اليوم، عُد غدًا.");
  return false;
}

// ===== المظهر (فاتح / داكن) =====
const THEME_KEY = "faheem_theme";
const systemTheme = window.matchMedia("(prefers-color-scheme: dark)");
let savedTheme = null;
let themeSaveSequence = 0;
try {
  const storedTheme = localStorage.getItem(THEME_KEY);
  if (storedTheme === "light" || storedTheme === "dark") savedTheme = storedTheme;
} catch {
  // التخزين غير متاح
}
const DEFAULT_THEME = savedTheme || (systemTheme.matches ? "dark" : "light");
let hasSavedThemePreference = Boolean(savedTheme);
const themeButtons = document.querySelectorAll("[data-theme-option]");

function applyTheme(theme, { save = false } = {}) {
  const previousTheme = document.documentElement.dataset.theme || "light";
  const value = theme === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = value;
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute("content", value === "dark" ? "#101114" : "#ffffff");
  themeButtons.forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.themeOption === value));
  });
  if (save) {
    hasSavedThemePreference = true;
    try {
      localStorage.setItem(THEME_KEY, value);
    } catch {
      // التخزين غير متاح
    }
    persistThemePreference(value, previousTheme, ++themeSaveSequence);
  }
}

async function persistThemePreference(theme, previousTheme, requestSequence) {
  try {
    await apiRequest("/api/preferences", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ theme }),
    });
  } catch (error) {
    if (requestSequence === themeSaveSequence) {
      applyTheme(previousTheme);
      try {
        localStorage.setItem(THEME_KEY, previousTheme);
      } catch {
        // التخزين غير متاح
      }
    }
    showToast(`تعذّر حفظ المظهر: ${error.message}`);
  }
}

async function loadThemePreference() {
  try {
    const result = await apiRequest("/api/preferences", { suppressAuthOverlay: true });
    const preference = result?.preferences?.theme;
    if (preference === "light" || preference === "dark") {
      hasSavedThemePreference = true;
      applyTheme(preference);
    } else {
      applyTheme(DEFAULT_THEME);
    }
  } catch {
    // نبقى على المظهر الحالي
  }
}

systemTheme.addEventListener("change", (event) => {
  if (!hasSavedThemePreference) applyTheme(event.matches ? "dark" : "light");
});

themeButtons.forEach((button) => {
  button.addEventListener("click", () => applyTheme(button.dataset.themeOption, { save: true }));
});
applyTheme(document.documentElement.dataset.theme);

// الصورة الخلفية (images.jpg) تحتفظ بمظهرها الأصلي وتظليلها الأسود في المظهرين:
// نعلّم العنصر الذي يحملها (أو ::before / ::after) ليستثنيه theme.css من قلب الألوان.
function markPhotoBackgrounds() {
  for (const element of document.querySelectorAll("body *")) {
    if (element.parentElement?.closest("[data-photo-bg]")) continue;
    for (const pseudo of [null, "::before", "::after"]) {
      const image = window.getComputedStyle(element, pseudo).backgroundImage;
      if (image && image.includes("images.jpg")) {
        element.dataset.photoBg = "true";
        break;
      }
    }
  }
}

markPhotoBackgrounds();
window.addEventListener("load", markPhotoBackgrounds);

// اكتب في أي مكان فيذهب النص إلى مربع الدردشة (على الحاسوب)
document.addEventListener("keydown", (event) => {
  if (event.ctrlKey || event.metaKey || event.altKey || event.key.length !== 1) return;
  const target = event.target;
  if (
    target instanceof HTMLElement &&
    (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT|BUTTON)$/.test(target.tagName))
  ) {
    return;
  }
  if (touchDevice.matches || input.disabled) return;
  if (document.querySelector(".auth-overlay:not(.hidden), .settings-overlay:not(.hidden)")) return;
  input.focus({ preventScroll: true });
});

function afterAuthenticated() {
  window.setTimeout(focusInputAuto, 400);
  new Image().src = "/loader-robot.webp"; // تُخزَّن مسبقًا لتظهر شاشة فتح المحادثة فورًا
  refreshUploadQuota();
  loadThemePreference();
}

async function sendMessage(message) {
  const text = message.trim();

  if ((selectedImage || selectedFile) && !ensureUploadAllowed()) {
    return;
  }

  if ((!text && !selectedImage && !selectedFile) || isSending) {
    return;
  }

  let image = null;
  let file = null;
  let displayedImage = null;
  let displayedFileName = null;

  if (selectedImage) {
    if (selectedImage.size > 8 * 1024 * 1024) {
      showToast("حجم الصورة يجب ألا يتجاوز 8 ميغابايت.");
      return;
    }

    const dataUrl = await readImageAsDataUrl(selectedImage);

    image = {
      mimeType: selectedImage.type,
      data: dataUrl.split(",", 2)[1],
    };

    displayedImage = dataUrl;
  }

  if (selectedFile) {
    if (selectedFile.size > 8 * 1024 * 1024) {
      showToast("حجم الملف يجب ألا يتجاوز 8 ميغابايت.");
      return;
    }

    const dataUrl = await readImageAsDataUrl(selectedFile);

    file = {
      name: selectedFile.name,
      mimeType: documentMimeType(selectedFile.name) || selectedFile.type,
      data: dataUrl.split(",", 2)[1],
    };

    displayedFileName = selectedFile.name;
  }

  removeSelectedImage();
  removeSelectedFile();

  input.value = "";
  input.style.height = "auto";

  await deliverMessage({ text, image, file, displayedImage, displayedFileName });
}

// يرسل رسالة جاهزة (نص + صورة/ملف مشفّرين)؛ تُستعمل للإرسال الجديد ولإعادة الإرسال
async function deliverMessage(payload) {
  const { text, image, file, displayedImage, displayedFileName } = payload;

  if (isSending) return;
  if ((image || file) && !ensureUploadAllowed()) return;
  if (!payload.requestId) {
    const requestId = new Uint8Array(16);
    crypto.getRandomValues(requestId);
    payload.requestId = Array.from(requestId, (byte) =>
      byte.toString(16).padStart(2, "0"),
    ).join("");
  }
  if (!Object.prototype.hasOwnProperty.call(payload, "conversationId")) {
    payload.conversationId = currentConversationId;
  }
  const previousConversationId = currentConversationId;

  const visibleText = displayedFileName
    ? `${text}${text ? "\n" : ""}مرفق ملف: ${displayedFileName}`
    : text;

  const userBody = appendMessage("user", visibleText, displayedImage);
  addResendAction(userBody, payload, userBody.messageElement);

  const assistantBody = appendMessage("assistant", "");

  const typing = createActivityIndicator(
    detectActivity(text, Boolean(image), Boolean(file)),
  );

  assistantBody.append(typing);

  const name = document.createElement("div");
  name.className = "message-name";
  name.textContent = "فهيم";

  const answer = document.createElement("div");
  answer.className = "message-text";

  setBusy(true);

  const request = { controller: new AbortController(), stopped: false };
  activeRequest = request;
  const streamState = {};
  let refreshHistory = false;

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
      },
      credentials: "same-origin",
      cache: "no-store",
      signal: request.controller.signal,
      body: JSON.stringify({
        message: text,
        image,
        file,
        conversationId: payload.conversationId,
        requestId: payload.requestId,
        retryRequest: payload.retryRequest === true,
      }),
    });

    /*
     * /api/chat يستخدم SSE streaming وليس JSON عادي.
     * لذلك لا نستخدم response.json() هنا.
     */
    if (!response.ok) {
      let errorMessage = "لم ينجح إرسال الرسالة.";

      try {
        const rawText = await response.text();

        if (rawText.trim()) {
          try {
            const result = JSON.parse(rawText);
            errorMessage =
              result?.error ||
              result?.message ||
              errorMessage;
            if (result?.code === "upload_limit" && result.quota) {
              uploadQuota = result.quota;
              renderUploadQuota();
            }
          } catch {
            // إذا كان الرد نصًا وليس JSON
            errorMessage = rawText.trim().slice(0, 500);
          }
        } else {
          errorMessage = `فشل إرسال الرسالة (HTTP ${response.status}).`;
        }
      } catch {
        errorMessage = `فشل إرسال الرسالة (HTTP ${response.status}).`;
      }

      if (response.status === 401) {
        redirectToLogin("expired");
      }

      throw new Error(errorMessage);
    }

    /*
     * نجاح /api/chat يعني أن السيرفر بدأ SSE stream.
     * يجب أن يكون response.body موجودًا حتى نتمكن من القراءة.
     */
    if (!response.body) {
      throw new Error("الخادم بدأ الاستجابة لكن لم يرسل اتصال البث.");
    }

    const result = await readGeminiStream(
      response,
      assistantBody,
      name,
      answer,
      streamState,
    );

    currentConversationId = result.conversationId;
    payload.conversationId = result.conversationId;
    payload._completed = true;
    payload.retryRequest = false;
    refreshHistory = true;

    const nearBottom =
      conversation.scrollHeight - conversation.scrollTop - conversation.clientHeight < 200;
    addReplyActions(assistantBody, result.answer);
    if (nearBottom) scrollToLatest();

  } catch (error) {
    currentConversationId = previousConversationId;
    if (request.stopped) {
      refreshHistory = true;
      // أوقف الطالب الرد: نُبقي ما وصل منه، أو نحذف الفقاعة الفارغة
      if (streamState.answerText && assistantBody.contains(answer)) {
        const note = document.createElement("div");
        note.className = "message-stopped";
        note.textContent = "تم إيقاف الرد";
        assistantBody.append(note);
        addReplyActions(assistantBody, streamState.answerText);
      } else {
        (assistantBody.messageElement || assistantBody).remove();
      }
    } else {
      showToast(
        studentErrorMessage(error),
      );
      if (error?.code === "save_failed" && streamState.answerText) {
        const note = document.createElement("div");
        note.className = "message-unsaved";
        note.textContent =
          "وصلت الإجابة لكن لم تُحفظ في سجل المحادثة. انسخها قبل مغادرة الصفحة.";
        assistantBody.append(note);
        addReplyActions(assistantBody, streamState.answerText);
        payload._completed = false;
      } else {
        (assistantBody.messageElement || assistantBody).remove();
        payload._completed = false;
      }
    }

  } finally {
    if (activeRequest === request) activeRequest = null;
    setBusy(false);
    input.focus();
  }

  if (image || file) refreshUploadQuota();

  if (refreshHistory) {
    try {
      await loadHistory();
    } catch (error) {
      showToast(
        error instanceof Error
          ? error.message
          : "تعذّر تحديث المحادثات.",
      );
    }
  }
}

function setupSpeechRecognition() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    micButton.classList.add("unsupported");
    micButton.title = "الإملاء الصوتي غير مدعوم في هذا المتصفح";
    return;
  }

  recognition = new SpeechRecognition();
  recognition.lang = "ar-SA";
  recognition.interimResults = true;
  recognition.continuous = false;
  recognition.addEventListener("start", () => micButton.classList.add("recording"));
  recognition.addEventListener("end", () => micButton.classList.remove("recording"));
  recognition.addEventListener("error", (event) => {
    micButton.classList.remove("recording");
    const messages = {
      "not-allowed": "اسمح للمتصفح باستخدام الميكروفون أولًا.",
      "no-speech": "لم أسمع صوتًا. حاول مرة أخرى.",
      "network": "تعذّر الاتصال بخدمة التعرّف على الصوت.",
    };
    showToast(messages[event.error] || "تعذّر بدء الإملاء الصوتي.");
  });
  recognition.addEventListener("result", (event) => {
    let transcript = "";
    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      transcript += event.results[index][0].transcript;
    }
    input.value = transcript;
    input.dispatchEvent(new Event("input"));
  });

  micButton.addEventListener("click", () => {
    if (micButton.classList.contains("recording")) {
      recognition.stop();
      return;
    }
    try {
      recognition.start();
    } catch {
      showToast("الإملاء الصوتي يعمل بالفعل. انتظر قليلًا ثم جرّب.");
    }
  });
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  if (isSending) {
    stopGeneration();
    return;
  }
  sendMessage(input.value).catch((error) => {
    showToast(error instanceof Error ? error.message : "تعذّرت قراءة الرسالة.");
  });
});

input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 140)}px`;
});

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

document.querySelector("#upload-button").addEventListener("click", () => {
  if (ensureUploadAllowed()) imageInput.click();
});
document.querySelector("#file-upload-button").addEventListener("click", () => {
  if (ensureUploadAllowed()) fileInput.click();
});
imageInput.addEventListener("change", () => {
  const file = imageInput.files?.[0];
  if (!file) return;
  if (!["image/png", "image/jpeg", "image/webp", "image/gif"].includes(file.type)) {
    showToast("اختر صورة بصيغة PNG أو JPEG أو WEBP أو GIF.");
    imageInput.value = "";
    return;
  }
  if (file.size > 8 * 1024 * 1024) {
    showToast("حجم الصورة يجب ألا يتجاوز 8 ميغابايت.");
    imageInput.value = "";
    return;
  }
  setSelectedImage(file);
});
fileInput.addEventListener("change", () => {
  const file = fileInput.files?.[0];
  if (!file) return;
  const mimeType = documentMimeType(file.name) || file.type;
  if (!mimeType || file.size > 8 * 1024 * 1024) {
    showToast(file.size > 8 * 1024 * 1024
      ? "حجم الملف يجب ألا يتجاوز 8 ميغابايت."
      : "اختر PDF أو ملفًا نصيًا أو CSV أو JSON أو HTML أو XML.");
    fileInput.value = "";
    return;
  }
  setSelectedFile(file);
});
document.querySelector("#remove-image").addEventListener("click", removeSelectedImage);
document.querySelector("#remove-file").addEventListener("click", removeSelectedFile);
document.querySelector("#new-chat").addEventListener("click", resetChat);
document.querySelector("#clear-chat").addEventListener("click", resetChat);
document.querySelectorAll(".suggestion").forEach((button) => {
  button.addEventListener("click", () => sendMessage(button.dataset.prompt || "").catch((error) => {
    showToast(error instanceof Error ? error.message : "تعذّر إرسال الرسالة.");
  }));
});

function resetChat() {
  if (isSending) return;
  conversationLoadToken += 1;
  loadingConversationId = null;
  conversation.removeAttribute("aria-busy");
  conversation.replaceChildren(welcome);
  welcome.classList.remove("hidden");
  removeSelectedImage();
  removeSelectedFile();
  input.value = "";
  focusInputAuto();
  currentConversationId = null;
  setMobileMenuOpen(false);
}

setupSpeechRecognition();
initializeApp();

function closeSettings() {
  settingsOverlay.classList.add("hidden");
  resetPasswordForm();
  passwordError.textContent = "";
  usernameMessage.textContent = "";
  phoneMessage.textContent = "";
}

function resetPasswordForm() {
  changePasswordForm.reset();
  for (const button of changePasswordForm.querySelectorAll(".password-toggle")) {
    const passwordInput = button.closest(".password-field")?.querySelector("input");
    if (passwordInput) passwordInput.type = "password";
    button.textContent = "إظهار";
    button.setAttribute("aria-label", "إظهار كلمة المرور");
    button.setAttribute("aria-pressed", "false");
  }
}

document.querySelectorAll(".password-toggle").forEach((button) => {
  button.addEventListener("click", () => {
    const field = button.closest(".password-field");
    const passwordInput = field?.querySelector("input");
    if (!passwordInput) return;
    const isVisible = passwordInput.type === "password";
    passwordInput.type = isVisible ? "text" : "password";
    button.textContent = isVisible ? "إخفاء" : "إظهار";
    button.setAttribute("aria-label", `${isVisible ? "إخفاء" : "إظهار"} كلمة المرور`);
    button.setAttribute("aria-pressed", String(isVisible));
  });
});
function closeHelpCenter() {
  helpCenterOverlay.classList.add("hidden");
  helpError.textContent = "";
  helpCenterForm.reset();
}

function openHelpCenter({ guest = !currentUser } = {}) {
  setMobileMenuOpen(false);
  helpError.textContent = "";
  helpCenterCard.classList.toggle("guest-help-card", guest);
  helpGuestFields.classList.toggle("hidden", !guest);
  helpGuestName.disabled = !guest;
  helpGuestName.required = guest;
  helpGuestEmail.disabled = !guest;
  helpGuestEmail.required = guest;
  helpCenterTitle.textContent = guest ? "استعادة الوصول إلى الحساب" : "مركز المساعدة";
  helpCategoryField.classList.toggle("hidden", guest);
  helpCategory.value = "message";
  helpContentLabel.textContent = guest ? "تفاصيل المشكلة" : "رسالتك";
  helpContent.placeholder = guest
    ? "اذكر ما يحدث عند محاولة الدخول إلى حسابك..."
    : "اكتب رسالتك أو شكواك هنا...";
  helpSubmit.textContent = guest ? "إرسال طلب المساعدة" : "إرسال إلى الأدمن";
  helpCenterDescription.textContent = guest
    ? "أرسل تفاصيل المشكلة وسيتواصل معك فريق المساعدة عبر بريدك الإلكتروني."
    : "أرسل رسالة أو شكوى، وستصل إلى فريق الأدمن.";
  helpCenterOverlay.classList.remove("hidden");
  (guest ? helpGuestName : helpContent).focus();
}

helpCenterButton.addEventListener("click", () => openHelpCenter({ guest: false }));
document.querySelector("#close-help-center").addEventListener("click", closeHelpCenter);
helpCenterOverlay.addEventListener("click", (event) => {
  if (event.target === helpCenterOverlay) closeHelpCenter();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !helpCenterOverlay.classList.contains("hidden")) {
    closeHelpCenter();
  }
});
helpCenterForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!helpCenterForm.reportValidity()) return;
  helpError.textContent = "";
  helpSubmit.disabled = true;
  const guestRequest = !helpGuestFields.classList.contains("hidden");
  try {
    await apiRequest("/api/support-messages", {
      suppressAuthOverlay: guestRequest,
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        category: helpCategory.value,
        content: helpContent.value,
        ...(helpGuestFields.classList.contains("hidden")
          ? {}
          : { name: helpGuestName.value, email: helpGuestEmail.value }),
      }),
    });
    closeHelpCenter();
    showToast(
      guestRequest
        ? "وصل طلبك لفريق المساعدة، وسنتواصل معك عبر البريد."
        : "وصلت رسالتك إلى فريق الأدمن. شكرًا لملاحظتك.",
    );
  } catch (error) {
    helpError.textContent = error.message;
  } finally {
    helpSubmit.disabled = false;
  }
});

profileSettingsToggle.addEventListener("click", () => {
  usernameMessage.textContent = "";
  settingsOverlay.classList.remove("hidden");
  if (!usernameSettings.classList.contains("hidden")) usernameInput.focus();
  else currentPasswordInput.focus();
});
closeSettingsButton.addEventListener("click", closeSettings);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !settingsOverlay.classList.contains("hidden")) {
    closeSettings();
  }
});

usernameForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!usernameForm.reportValidity()) return;
  usernameMessage.classList.remove("error");
  usernameMessage.textContent = "";
  usernameSubmit.disabled = true;
  try {
    const result = await apiRequest("/api/account/name", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fullName: usernameInput.value }),
    });
    currentUser.name = result.fullName;
    profileName.textContent = result.fullName;
    userAvatarFallback.textContent = result.fullName.slice(0, 1);
    usernameInput.value = result.fullName;
    usernameMessage.textContent = "تم تحديث اسم المستخدم بنجاح.";
  } catch (error) {
    usernameMessage.classList.add("error");
    usernameMessage.textContent = error.message;
  } finally {
    usernameSubmit.disabled = false;
  }
});

phoneForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!phoneForm.reportValidity()) return;
  phoneMessage.classList.remove("error");
  phoneMessage.textContent = "";
  phoneSubmit.disabled = true;
  try {
    const result = await apiRequest("/api/account/phone", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ phone: phoneInput.value }),
    });
    phoneInput.value = result.phone;
    phoneMessage.textContent = "تم تحديث رقم الهاتف بنجاح.";
  } catch (error) {
    phoneMessage.classList.add("error");
    phoneMessage.textContent = error.message;
  } finally {
    phoneSubmit.disabled = false;
  }
});

changePasswordForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!changePasswordForm.reportValidity()) return;
  passwordError.textContent = "";
  if (newPasswordInput.value !== confirmPasswordInput.value) {
    passwordError.textContent = "كلمتا المرور الجديدتان غير متطابقتين.";
    confirmPasswordInput.focus();
    return;
  }

  changePasswordSubmit.disabled = true;
  try {
    await apiRequest("/api/auth/change-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        currentPassword: currentPasswordInput.value,
        newPassword: newPasswordInput.value,
        confirmPassword: confirmPasswordInput.value,
      }),
    });
    resetPasswordForm();
    passwordError.textContent = "تم تغيير كلمة المرور بنجاح. أُنهيت جلساتك على الأجهزة الأخرى.";
    showToast("تم تغيير كلمة المرور وتسجيل الخروج من الأجهزة الأخرى.");
  } catch (error) {
    passwordError.textContent = error.message;
    if (error.message.includes("الحالية غير صحيحة")) {
      currentPasswordInput.value = "";
      currentPasswordInput.focus();
    }
  } finally {
    changePasswordSubmit.disabled = false;
  }
});

logoutButton.addEventListener("click", async () => {
  try {
    await apiRequest("/api/logout", { method: "POST" });
    currentUser = null;
    currentConversationId = null;
    conversation.replaceChildren(welcome);
    welcome.classList.remove("hidden");
    historyList.replaceChildren();
    profileName.textContent = "مساحتك الخاصة";
    helpCenterButton.classList.add("hidden");
    logoutButton.classList.add("hidden");
    profileSettings.classList.add("hidden");
    settingsOverlay.classList.add("hidden");
    adminButton.classList.add("hidden");
    closeSettings();
    userAvatar.classList.add("hidden");
    userAvatarFallback.textContent = "ف";
    userAvatarFallback.classList.remove("hidden");
    try {
      localStorage.removeItem(LOGGED_IN_BEFORE_KEY);
    } catch {
      // التخزين غير متاح
    }
    try {
      sessionStorage.clear();
    } catch {
      // التخزين غير متاح
    }
    window.location.replace("/login.html");
  } catch (error) {
    showToast(error.message);
  }
});

adminButton.addEventListener("click", () => {
  setMobileMenuOpen(false);
  // تفتح لوحة التحكم في تبويب جديد (الجلسة نفسها، فلا تحتاج لتسجيل دخول ثانٍ)
  const link = document.createElement("a");
  link.href = "/admin.html";
  link.target = "_blank";
  link.rel = "noopener";
  document.body.append(link);
  link.click();
  link.remove();
});
window.setInterval(() => {
  if (!adminOverlay.classList.contains("hidden")) {
    refreshAdminStatistics().catch((error) => {
      adminError.textContent = error.message;
    });
  }
}, 15000);
adminUserSearch.addEventListener("input", filterAdminUsers);
for (const tab of adminTabs) {
  tab.addEventListener("click", () => {
    for (const item of adminTabs) {
      const isSelected = item === tab;
      item.classList.toggle("active", isSelected);
      item.setAttribute("aria-selected", String(isSelected));
    }
    const showSupport = tab.dataset.adminTab === "support";
    adminUsersView.classList.toggle("hidden", showSupport);
    adminSupportView.classList.toggle("hidden", !showSupport);
    adminError.textContent = "";
    if (showSupport) loadAdminSupportMessages();
    else filterAdminUsers();
  });
}
document.querySelector("#close-admin").addEventListener("click", () => {
  closeAdminPasswordDialog();
  adminOverlay.classList.add("hidden");
  adminError.textContent = "";
});
adminOverlay.addEventListener("click", (event) => {
  if (event.target === adminOverlay) {
    closeAdminPasswordDialog();
    adminOverlay.classList.add("hidden");
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") setMobileMenuOpen(false);
  if (event.key === "Escape" && !adminOverlay.classList.contains("hidden")) {
    if (!adminPasswordDialog.classList.contains("hidden")) {
      closeAdminPasswordDialog();
    } else {
      adminOverlay.classList.add("hidden");
    }
  }
});

mobileMenuToggle.addEventListener("click", toggleSidebar);
historySearchToggle.addEventListener("click", () => {
  const isOpen = historySearchToggle.getAttribute("aria-expanded") !== "true";
  historySearchToggle.setAttribute("aria-expanded", String(isOpen));
  historySearch.classList.toggle("hidden", !isOpen);
  if (isOpen) historySearch.focus();
  else {
    historySearch.value = "";
    filterHistory();
  }
});
historySearch.addEventListener("input", filterHistory);
sidebarBackdrop.addEventListener("click", () => setMobileMenuOpen(false));
