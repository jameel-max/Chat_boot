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
const authOverlay = document.querySelector("#auth-overlay");
const authError = document.querySelector("#auth-error");
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
const profileSettingsMenu = document.querySelector("#profile-settings-menu");
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
const adminPasswordDialog = document.querySelector("#admin-password-dialog");
const adminPasswordDescription = document.querySelector("#admin-password-description");
const adminPasswordForm = document.querySelector("#admin-password-form");
const adminNewPassword = document.querySelector("#admin-new-password");
const adminConfirmPassword = document.querySelector("#admin-confirm-password");
const adminPasswordSubmit = document.querySelector("#admin-password-submit");
const adminPasswordError = document.querySelector("#admin-password-error");
const changePasswordButton = document.querySelector("#change-password-button");
const passwordOverlay = document.querySelector("#password-overlay");
const changePasswordForm = document.querySelector("#change-password-form");
const currentPasswordInput = document.querySelector("#current-password");
const newPasswordInput = document.querySelector("#new-password");
const confirmPasswordInput = document.querySelector("#confirm-password");
const changePasswordSubmit = document.querySelector("#change-password-submit");
const passwordError = document.querySelector("#password-error");
const forgotPasswordLink = document.querySelector("#forgot-password-link");
const authForm = document.querySelector("#auth-form");
const authEmail = document.querySelector("#auth-email");
const authPassword = document.querySelector("#auth-password");
const authDescription = document.querySelector("#auth-description");
const authSubmit = document.querySelector("#auth-submit");
const authModeToggle = document.querySelector("#auth-mode-toggle");
const rememberDevice = document.querySelector("#remember-device");

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
  } catch (error) {
    adminError.textContent = error.message;
  }
}

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
let authMode = "login";

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("visible");
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => toast.classList.remove("visible"), 5000);
}

function scrollToLatest() {
  conversation.scrollTop = conversation.scrollHeight;
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
  }
  message.append(avatar, body);
  conversation.append(message);
  scrollToLatest();
  return body;
}

function setBusy(busy) {
  sendButton.disabled = busy;
  input.disabled = busy;
  sendButton.setAttribute("aria-busy", String(busy));
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
    header.textContent = codeLanguage || "code";

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

async function readGeminiStream(response, assistantBody, name, answer) {
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
      throw new Error(
        typeof eventData.error === "string"
          ? eventData.error
          : "تعذّر إكمال الإجابة.",
      );
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

  const response = await fetch(url, {
    cache: "no-store",
    credentials: "same-origin",
    ...requestOptions,
  });

  if (!response.ok) {
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
      showAuthOverlay(detail);
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


function showAuthOverlay(message = "") {
  if (
    !helpCenterOverlay.classList.contains("hidden") &&
    !helpGuestFields.classList.contains("hidden")
  ) {
    authError.textContent = "";
    return;
  }
  authError.textContent = message;
  authOverlay.classList.remove("hidden");
}

function setAuthenticated(user, isAdmin = false, isPrimaryAdmin = false) {
  currentUser = { ...user, isAdmin, isPrimaryAdmin };
  profileName.textContent = user.name;
  helpCenterButton.classList.remove("hidden");
  profileSettings.classList.remove("hidden");
  logoutButton.classList.remove("hidden");
  changePasswordButton.classList.remove("hidden");
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
  authOverlay.classList.add("hidden");
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
  renderHistory(result.conversations);
}

async function loadConversation(id) {
  if (sendButton.disabled) return;
  const result = await apiRequest(`/api/conversations/${encodeURIComponent(id)}`);
  currentConversationId = result.conversation.id;
  conversation.replaceChildren();
  welcome.classList.add("hidden");
  setMobileMenuOpen(false);

  for (const message of result.messages) {
    const imageUrl = message.image
      ? `data:${message.image.mimeType};base64,${message.image.data}`
      : null;
    const body = appendMessage(
      message.role,
      message.content,
      imageUrl,
    );
  }
  if (!result.messages.length) {
    welcome.classList.remove("hidden");
    conversation.append(welcome);
  }
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

async function deleteConversation(record) {
  if (!window.confirm(`هل تريد حذف محادثة «${record.title}» نهائيًا؟`)) return;
  try {
    await apiRequest(`/api/conversations/${encodeURIComponent(record.id)}`, {
      method: "DELETE",
    });
    if (currentConversationId === record.id) resetChat();
    await loadHistory();
  } catch (error) {
    showToast(error.message);
  }
}

function setAuthMode(mode) {
  authMode = mode;
  const isRegistering = mode === "register";
  authDescription.textContent = isRegistering
    ? "أنشئ حسابًا بالبريد وكلمة المرور لحفظ محادثاتك."
    : "سجّل الدخول بحسابك للوصول إلى محادثاتك المحفوظة.";
  authSubmit.textContent = isRegistering ? "إنشاء حساب" : "تسجيل الدخول";
  authModeToggle.textContent = isRegistering
    ? "لديك حساب؟ سجّل الدخول"
    : "ليس لديك حساب؟ أنشئ حسابًا";
  forgotPasswordLink.classList.toggle("hidden", isRegistering);
  authPassword.autocomplete = isRegistering ? "new-password" : "current-password";
  authPassword.minLength = isRegistering ? 10 : 1;
  authError.textContent = "";
}

async function initializeApp() {
  try {
    const result = await apiRequest("/api/me", { suppressAuthOverlay: true });
    setAuthenticated(result.user, result.isAdmin, result.isPrimaryAdmin);
    await loadHistory();
  } catch (error) {
    showAuthOverlay("");
  }
}

async function sendMessage(message) {
  const text = message.trim();

  if ((!text && !selectedImage && !selectedFile) || sendButton.disabled) {
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

  const visibleText = displayedFileName
    ? `${text}${text ? "\n" : ""}مرفق ملف: ${displayedFileName}`
    : text;

  appendMessage("user", visibleText, displayedImage);

  removeSelectedImage();
  removeSelectedFile();

  input.value = "";
  input.style.height = "auto";

  const assistantBody = appendMessage("assistant", "");

  const typing = document.createElement("div");
  typing.className = "typing";
  typing.setAttribute("aria-label", "فهيم يفكر");

  const typingLabel = document.createElement("span");
  typingLabel.className = "typing-label";
  typingLabel.textContent = "فهيم يفكّر";

  typing.append(typingLabel);

  for (let index = 0; index < 3; index += 1) {
    typing.append(document.createElement("i"));
  }

  assistantBody.append(typing);

  const name = document.createElement("div");
  name.className = "message-name";
  name.textContent = "فهيم";

  const answer = document.createElement("div");
  answer.className = "message-text";

  setBusy(true);

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
      body: JSON.stringify({
        message: text,
        image,
        file,
        conversationId: currentConversationId,
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
        showAuthOverlay(errorMessage);
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
    );

    currentConversationId = result.conversationId;
    refreshHistory = true;

  } catch (error) {
    assistantBody.remove();

    showToast(
      error instanceof Error
        ? error.message
        : "حدث خطأ غير متوقع.",
    );

    refreshHistory = true;

  } finally {
    setBusy(false);
    input.focus();
  }

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

document.querySelector("#upload-button").addEventListener("click", () => imageInput.click());
document.querySelector("#file-upload-button").addEventListener("click", () => fileInput.click());
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
  if (sendButton.disabled) return;
  conversation.replaceChildren(welcome);
  welcome.classList.remove("hidden");
  removeSelectedImage();
  removeSelectedFile();
  input.value = "";
  input.focus();
  currentConversationId = null;
  setMobileMenuOpen(false);
}

setupSpeechRecognition();
initializeApp();

authModeToggle.addEventListener("click", () => {
  setAuthMode(authMode === "login" ? "register" : "login");
});

function closePasswordOverlay() {
  passwordOverlay.classList.add("hidden");
  changePasswordForm.reset();
  passwordError.textContent = "";
}

forgotPasswordLink.addEventListener("click", () => {
  helpGuestEmail.value = authEmail.value.trim();
  openHelpCenter({ guest: true });
});
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
changePasswordButton.addEventListener("click", () => {
  setProfileSettingsOpen(false);
  passwordError.textContent = "";
  passwordOverlay.classList.remove("hidden");
  currentPasswordInput.focus();
});

function closeHelpCenter() {
  const returnToLogin =
    helpCenterCard.classList.contains("guest-help-card") && !currentUser;
  helpCenterOverlay.classList.add("hidden");
  helpError.textContent = "";
  helpCenterForm.reset();
  if (returnToLogin) authOverlay.classList.remove("hidden");
}

function openHelpCenter({ guest = !currentUser } = {}) {
  setMobileMenuOpen(false);
  helpError.textContent = "";
  if (guest) {
    authError.textContent = "";
    authOverlay.classList.add("hidden");
  }
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

function setProfileSettingsOpen(open) {
  profileSettingsMenu.classList.toggle("hidden", !open);
  profileSettingsToggle.setAttribute("aria-expanded", String(open));
}

profileSettingsToggle.addEventListener("click", () => {
  setProfileSettingsOpen(profileSettingsToggle.getAttribute("aria-expanded") !== "true");
});

document.addEventListener("click", (event) => {
  if (!profileSettings.contains(event.target)) setProfileSettingsOpen(false);
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") setProfileSettingsOpen(false);
});

document.querySelector("#cancel-password-change").addEventListener("click", closePasswordOverlay);
passwordOverlay.addEventListener("click", (event) => {
  if (event.target === passwordOverlay) closePasswordOverlay();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !passwordOverlay.classList.contains("hidden")) {
    closePasswordOverlay();
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
      }),
    });
    closePasswordOverlay();
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

authForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!authForm.reportValidity()) return;
  authSubmit.disabled = true;
  authError.textContent = "";
  try {
    const result = await apiRequest(
      authMode === "register" ? "/api/auth/register" : "/api/auth/login",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: authEmail.value,
          password: authPassword.value,
          remember: rememberDevice.checked,
        }),
      },
    );
    setAuthenticated(result.user, result.isAdmin, result.isPrimaryAdmin);
    authPassword.value = "";
    setAuthMode("login");
    await loadHistory();
  } catch (error) {
    authError.textContent = error.message;
  } finally {
    authSubmit.disabled = false;
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
    setProfileSettingsOpen(false);
    adminButton.classList.add("hidden");
    changePasswordButton.classList.add("hidden");
    closePasswordOverlay();
    userAvatar.classList.add("hidden");
    userAvatarFallback.textContent = "ف";
    userAvatarFallback.classList.remove("hidden");
    showAuthOverlay();
  } catch (error) {
    showToast(error.message);
  }
});

adminButton.addEventListener("click", async () => {
  adminOverlay.classList.remove("hidden");
  setMobileMenuOpen(false);
  await loadAdminDashboard();
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