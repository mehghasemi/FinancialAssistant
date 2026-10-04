/* Shared amount entry and Persian words, without floating-point formatting. */
const Money = (() => {
  const digits = value => String(value).replace(/[۰-۹]/g, c => "۰۱۲۳۴۵۶۷۸۹".indexOf(c)).replace(/[٠-٩]/g, c => "٠١٢٣٤٥٦٧٨٩".indexOf(c));
  const fa = value => String(value).replace(/\d/g, c => "۰۱۲۳۴۵۶۷۸۹"[c]);
  const small = ["", "یک", "دو", "سه", "چهار", "پنج", "شش", "هفت", "هشت", "نه", "ده", "یازده", "دوازده", "سیزده", "چهارده", "پانزده", "شانزده", "هفده", "هجده", "نوزده"];
  const tens = ["", "", "بیست", "سی", "چهل", "پنجاه", "شصت", "هفتاد", "هشتاد", "نود"];
  const hundreds = ["", "صد", "دویست", "سیصد", "چهارصد", "پانصد", "ششصد", "هفتصد", "هشتصد", "نهصد"];
  function triple(n) {
    const parts = [];
    if (n >= 100) { parts.push(hundreds[Math.floor(n / 100)]); n %= 100; }
    if (n >= 20) { parts.push(tens[Math.floor(n / 10)]); n %= 10; }
    if (n) parts.push(small[n]);
    return parts.join(" و ");
  }
  function words(value) {
    let text = digits(value).replace(/[٬,\s]/g, "");
    if (!text) return "";
    if (!/^-?\d+$/.test(text)) return "مبلغ معتبر نیست";
    let n = BigInt(text), negative = n < 0n;
    if (negative) n = -n;
    if (n > 9007199254740991n) return "مبلغ از محدودهٔ مجاز بیشتر است";
    if (!n) return "صفر تومان";
    const units = ["", "هزار", "میلیون", "میلیارد", "تریلیون", "کوادریلیون"], parts = [];
    let index = 0;
    while (n) { const part = Number(n % 1000n); if (part) parts.unshift(`${triple(part)} ${units[index]}`.trim()); n /= 1000n; index++; }
    return `${negative ? "منفی " : ""}${parts.join(" و ")} تومان`;
  }
  function format(input) {
    const original = digits(input.value), position = input.selectionStart;
    const before = position === null ? null : original.slice(0, position).replace(/[^0-9]/g, "").length;
    const raw = original.replace(/[٬,\s]/g, "");
    const valid = /^\d*$/.test(raw) && (!raw || BigInt(raw) <= 9007199254740991n);
    input.setCustomValidity(valid ? "" : "فقط مبلغ صحیح و نامنفی تا ۹٬۰۰۷٬۱۹۹٬۲۵۴٬۷۴۰٬۹۹۱ وارد کنید.");
    const formatted = valid ? fa(raw.replace(/\B(?=(\d{3})+(?!\d))/g, "٬")) : fa(original);
    if (input.value !== formatted) {
      input.value = formatted;
      if (before !== null && document.activeElement === input) {
        let cursor = 0, seen = 0;
        while (cursor < formatted.length && seen < before) { if (/[۰-۹]/.test(formatted[cursor])) seen++; cursor++; }
        input.setSelectionRange(cursor, cursor);
      }
    }
    let hint = input.nextElementSibling;
    if (!hint?.classList.contains("amount-words")) {
      if (!input.hasAttribute("aria-label") && input.labels?.length) input.setAttribute("aria-label", input.labels[0].textContent.trim());
      hint = document.createElement("small"); hint.className = "amount-words";
      input.insertAdjacentElement("afterend", hint);
    }
    const message = valid ? words(raw) : "مبلغ معتبر نیست";
    if (hint.textContent !== message) hint.textContent = message;
  }
  function formatCount(input) {
    const raw = digits(input.value).replace(/[٬,\s]/g, "");
    const valid = /^\d*$/.test(raw) && (!raw || ((!input.min || Number(raw)>=Number(input.min)) && (!input.max || Number(raw)<=Number(input.max))));
    input.setCustomValidity(valid ? "" : "عدد خارج از محدودهٔ مجاز است.");
    const formatted = fa(raw);
    if (input.value !== formatted) {
      const start = input.selectionStart, end = input.selectionEnd;
      input.value = formatted;
      if (document.activeElement === input && start !== null) input.setSelectionRange(start,end);
    }
  }
  function scan(root = document) {
    root.querySelectorAll("input[data-amount]").forEach(format);
    root.querySelectorAll("input[data-count]").forEach(formatCount);
  }
  document.addEventListener("input", event => { if (event.target.matches("input[data-amount]") && !event.isComposing) format(event.target); if(event.target.matches("input[data-count]")) formatCount(event.target); }, true);
  document.addEventListener("compositionend", event => { if (event.target.matches("input[data-amount]")) format(event.target); });
  document.addEventListener("beforeinput", event => {
    const input = event.target;
    if (!input.matches("input[data-amount]") || input.selectionStart !== input.selectionEnd) return;
    const pos = input.selectionStart;
    if (event.inputType === "deleteContentBackward" && /[٬,]/.test(input.value[pos - 1] || "")) input.setSelectionRange(Math.max(0, pos - 2), pos);
    if (event.inputType === "deleteContentForward" && /[٬,]/.test(input.value[pos] || "")) input.setSelectionRange(pos, pos + 2);
  });
  document.addEventListener("reset", () => setTimeout(() => scan(), 0));
  document.addEventListener("DOMContentLoaded", () => {
    scan();
    new MutationObserver(records => {
      if (records.some(record => Array.from(record.addedNodes).some(node => node.nodeType === 1 && (node.matches?.("input[data-amount],input[data-count]") || node.querySelector?.("input[data-amount],input[data-count]"))))) scan();
    }).observe(document.body, {childList:true, subtree:true});
    document.addEventListener("input", () => scan());
  });
  return {words, format, scan};
})();
