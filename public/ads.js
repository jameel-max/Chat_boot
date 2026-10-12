(() => {
  "use strict";

  const ADS_CONFIG = {
    enabled: true,
    inlineEvery: 1,

    // طريقة إعلان الدخول:
    //  "card"  = مربع بزر X داخل الشاشة الترحيبية (الأكثر أمانًا لسياسات AdSense)
    //  "popup" = مربع فوق الصفحة بخلفية معتمة (سياسة AdSense تمنع وضع الإعلانات في النوافذ المنبثقة)
    entryMode: "card",

    // Google AdSense فقط
    adsense: {
      client: "ca-pub-7336064867071445",
      inlineSlot: "9936639651",
      entrySlot: "", // اتركه فارغًا ليستخدم inlineSlot، أو ضع رقم وحدة مربعة (Rectangle) خاصة بالدخول
      rewardedSlot: ""
    }
  };

  const FILL_TIMEOUT_MS = 6000; // إن لم يصل إعلان خلال هذه المدة نُخفي المكان بدل ترك فراغ
  const ENTRY_DELAY_MS = 900;

  let adsenseLoaded = false;
  let adsenseLoadFailed = false;
  let answersSinceAd = 0;

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function loadAdsenseScript() {
    if (adsenseLoaded || adsenseLoadFailed) return;

    adsenseLoaded = true;

    const script = document.createElement("script");
    script.async = true;
    script.crossOrigin = "anonymous";
    script.src =
      "https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=" +
      encodeURIComponent(ADS_CONFIG.adsense.client);

    script.onerror = () => {
      adsenseLoadFailed = true;
      console.error("Faheem: تعذّر تحميل Google AdSense.");
    };

    document.head.append(script);
  }

  const KIND_OPTIONS = {
    inline: { slot: () => ADS_CONFIG.adsense.inlineSlot, format: "horizontal" },
    entry: {
      slot: () => ADS_CONFIG.adsense.entrySlot || ADS_CONFIG.adsense.inlineSlot,
      format: "rectangle"
    },
    rewarded: { slot: () => ADS_CONFIG.adsense.rewardedSlot, format: "rectangle" }
  };

  // يبني البطاقة ووحدة الإعلان دون إطلاقها؛ الإطلاق يتم بعد إدخالها في الصفحة.
  function buildCard(kind, { dismissible = false } = {}) {
    const { client } = ADS_CONFIG.adsense;
    const options = KIND_OPTIONS[kind];
    const slot = options.slot();

    // لا يوجد أي بديل إعلاني غير Google.
    if (!client || !slot || adsenseLoadFailed) return null;

    loadAdsenseScript();

    const card = element("aside", `ad-card ad-card--network ad-card--${kind}`);
    card.setAttribute("aria-label", "إعلان");

    // الوسم وزر الإغلاق في شريط علوي منفصل، ولا يتداخلان مع منطقة الإعلان.
    const head = element("div", "ad-card__head");
    head.append(element("span", "ad-card__tag", "إعلان"));
    let dismiss = null;
    if (dismissible) {
      dismiss = element("button", "ad-card__dismiss", "×");
      dismiss.type = "button";
      dismiss.setAttribute("aria-label", "إغلاق الإعلان");
      head.append(dismiss);
    }
    card.append(head);

    const unit = document.createElement("ins");
    unit.className = "adsbygoogle";
    unit.style.display = "block";
    unit.dataset.adClient = client;
    unit.dataset.adSlot = slot;
    unit.dataset.adFormat = options.format;
    unit.dataset.fullWidthResponsive = "false";
    card.append(unit);

    return { card, unit, dismiss };
  }

  // يطلق الإعلان بعد أن صار داخل الصفحة، ثم يراقب هل امتلأ أم لا.
  function activate(unit, { onFilled, onFailed }) {
    let settled = false;
    let timer = 0;
    let observer = null;

    function finish(filled) {
      if (settled) return;
      settled = true;
      if (observer) observer.disconnect();
      window.clearTimeout(timer);
      (filled ? onFilled : onFailed)();
    }

    function check() {
      const status = unit.dataset.adStatus;
      if (status === "filled") finish(true);
      else if (status === "unfilled") finish(false);
    }

    if (typeof MutationObserver === "function") {
      observer = new MutationObserver(check);
      observer.observe(unit, { attributes: true, attributeFilter: ["data-ad-status"] });
    }
    timer = window.setTimeout(() => finish(unit.dataset.adStatus === "filled"), FILL_TIMEOUT_MS);

    try {
      (window.adsbygoogle = window.adsbygoogle || []).push({});
    } catch (error) {
      console.error("Faheem AdSense error:", error);
      finish(false);
    }
  }

  function reveal(node, delay = 0) {
    window.setTimeout(() => {
      if (node.isConnected) node.classList.add("visible");
    }, delay);
  }

  // بعد اكتمال الإجابة: شريط أفقي صغير تحتها، ويبقى مطويًّا حتى يصل الإعلان فعلًا.
  function renderInlineAd(afterNode) {
    if (!ADS_CONFIG.enabled || !afterNode) return null;

    answersSinceAd += 1;

    if (answersSinceAd < ADS_CONFIG.inlineEvery) return null;
    answersSinceAd = 0;

    const built = buildCard("inline");
    if (!built) return null;

    const slot = element("div", "ad-slot ad-slot--pending");
    slot.append(built.card);
    afterNode.after(slot);

    activate(built.unit, {
      onFilled: () => {
        slot.classList.remove("ad-slot--pending");
        reveal(built.card, 250);
      },
      onFailed: () => slot.remove()
    });
    return slot;
  }

  // عند الدخول: مربع بزر X في الزاوية.
  function renderEntryAd(container) {
    if (!ADS_CONFIG.enabled) return null;

    window.setTimeout(() => {
      const built = buildCard("entry", { dismissible: true });
      if (!built) return;

      const popup = ADS_CONFIG.entryMode === "popup";
      let host;
      let close;

      if (popup) {
        host = element("div", "ad-popup ad-popup--pending");
        host.setAttribute("role", "dialog");
        host.setAttribute("aria-label", "إعلان");
        host.append(built.card);
        close = () => {
          built.card.classList.remove("visible");
          host.classList.add("ad-popup--pending");
          window.setTimeout(() => host.remove(), 300);
          document.removeEventListener("keydown", onKey);
        };
        host.addEventListener("click", (event) => {
          if (event.target === host) close();
        });
        document.body.append(host);
      } else {
        if (!container) return;
        host = container;
        host.replaceChildren();
        host.classList.add("ad-slot--pending");
        host.append(built.card);
        close = () => {
          built.card.classList.remove("visible");
          window.setTimeout(() => host.replaceChildren(), 250);
          document.removeEventListener("keydown", onKey);
        };
      }

      function onKey(event) {
        if (event.key === "Escape") close();
      }
      document.addEventListener("keydown", onKey);
      built.dismiss.addEventListener("click", close);

      activate(built.unit, {
        onFilled: () => {
          host.classList.remove("ad-slot--pending", "ad-popup--pending");
          reveal(built.card, 50);
        },
        onFailed: () => {
          document.removeEventListener("keydown", onKey);
          if (popup) host.remove();
          else host.replaceChildren();
        }
      });
    }, ENTRY_DELAY_MS);

    return true;
  }

  function renderRewardAd(container) {
    if (!ADS_CONFIG.enabled || !container) return null;

    container.replaceChildren();

    // لن يظهر إعلان مكافأة حتى يتم إعداد وحدته.
    const built = buildCard("rewarded");
    if (!built) return null;

    container.append(built.card);
    activate(built.unit, {
      onFilled: () => reveal(built.card, 50),
      onFailed: () => built.card.remove()
    });
    return built.card;
  }

  window.FaheemAds = {
    config: ADS_CONFIG,
    renderInlineAd,
    renderEntryAd,
    renderRewardAd
  };
})();
