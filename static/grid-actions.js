/* Local SVG icons; keep existing buttons, events and accessible action names. */
const GridActions = (() => {
  const paths = {
    edit:'<path d="m15 5 4 4M4 20l4-1L20 7a2.8 2.8 0 0 0-4-4L4 15z"/>',
    commitment:'<path d="M13 3H5v18h14v-8M8 7h3M8 11h2m4 3 7-7-3-3-7 7-1 4z"/>',
    remove:'<path d="M3 6h18M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7m4-7v7"/>',
    view:'<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
    history:'<path d="M3 11a9 9 0 1 1 2 7M3 4v7h7m2-4v6l4 2"/>',
    pay:'<rect x="2" y="5" width="20" height="14" rx="3"/><path d="M2 10h20m-14 5h3m4 0h3"/>',
    list:'<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>'
  };
  function decorate(root) {
    root.querySelectorAll("td button:not(.grid-icon-action)").forEach(button => {
      if (button.closest("form") || button.closest(".jalali-dialog")) return;
      const label = button.textContent.trim();
      let icon = /حذف/.test(label) ? "remove" : /ویرایش تعهد/.test(label) ? "commitment" : /ویرایش|تعیین/.test(label) ? "edit" : /تاریخچه/.test(label) ? "history" : /ریز پرداخت|اقساط/.test(label) ? "list" : label === "پرداخت" ? "pay" : /جزئیات|مشاهده/.test(label) ? "view" : null;
      if (!icon) return;
      button.classList.add("grid-icon-action");
      button.dataset.actionHint = label;
      button.setAttribute("aria-label", label);
      button.removeAttribute("title");
      button.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">${paths[icon]}</svg>`;
    });
  }
  document.addEventListener("DOMContentLoaded", () => {
    const hint = document.createElement("div");
    hint.id = "gridActionTooltip"; hint.className = "grid-action-tooltip";
    hint.setAttribute("role", "tooltip"); hint.hidden = true;
    document.body.append(hint);
    let timer = null, active = null;
    const hide = () => {
      clearTimeout(timer); timer = null; hint.hidden = true;
      if (active) active.removeAttribute("aria-describedby");
      active = null;
    };
    const schedule = (button, delay) => {
      hide(); active = button;
      timer = setTimeout(() => {
        if (!button.isConnected || button.disabled || !button.getClientRects().length) return hide();
        hint.textContent = button.dataset.actionHint; hint.hidden = false;
        button.setAttribute("aria-describedby", hint.id);
        const rect = button.getBoundingClientRect(), box = hint.getBoundingClientRect();
        hint.style.left = `${Math.max(8, Math.min(innerWidth-box.width-8, rect.left+(rect.width-box.width)/2))}px`;
        hint.style.top = `${rect.top >= box.height+12 ? rect.top-box.height-8 : rect.bottom+8}px`;
      }, delay);
    };
    document.addEventListener("pointerover", event => {
      const button = event.target.closest(".grid-icon-action");
      if (button && button !== active && event.pointerType !== "touch") schedule(button, 0);
    });
    document.addEventListener("pointerout", event => {
      if (active && event.target.closest(".grid-icon-action") === active && !active.contains(event.relatedTarget)) hide();
    });
    document.addEventListener("focusin", event => { const button=event.target.closest(".grid-icon-action"); if(button) schedule(button, 0); });
    document.addEventListener("focusout", hide);
    document.addEventListener("click", hide);
    document.addEventListener("keydown", event => { if(event.key === "Escape") hide(); });
    document.addEventListener("scroll", hide, true);
    window.addEventListener("resize", hide);
    new MutationObserver(records => {
      if(active && !active.isConnected) hide();
      for(const record of records) for(const node of record.addedNodes) if(node.nodeType===1 && !node.closest(".grid-icon-action")) decorate(node.parentElement || node);
    }).observe(document.querySelector("main"), {childList:true, subtree:true});
    decorate(document.querySelector("main"));
  });
  return {decorate};
})();
