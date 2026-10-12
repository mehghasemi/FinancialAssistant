// Presentation privacy is reset on each page load; it is not authentication.
const DashboardPrivacy = (() => {
  const dashboard = document.getElementById("dashboard");
  const toggle = document.getElementById("dashboardPrivacy");
  const cards = [...dashboard.querySelectorAll(".dashboard-card")];
  function mask() {
    dashboard.classList.add("privacy-masked");
    cards.forEach(card => card.removeAttribute("data-revealed"));
    toggle.textContent = "نمایش همهٔ اعداد";
    toggle.setAttribute("aria-pressed", "false");
  }
  dashboard.addEventListener("click", event => {
    const card = event.target.closest(".dashboard-card");
    if (card && dashboard.classList.contains("privacy-masked") && !card.hasAttribute("data-revealed")) {
      event.preventDefault(); event.stopImmediatePropagation();
      card.setAttribute("data-revealed", "true");
      toggle.textContent = "پنهان‌کردن اعداد";
      toggle.setAttribute("aria-pressed", "true");
    }
  }, true);
  toggle.addEventListener("click", () => {
    if (!dashboard.classList.contains("privacy-masked") || cards.some(card => card.hasAttribute("data-revealed"))) return mask();
    dashboard.classList.remove("privacy-masked");
    toggle.textContent = "پنهان‌کردن اعداد";
    toggle.setAttribute("aria-pressed", "true");
  });
  window.addEventListener("pageshow", mask);
  mask();
  return {mask};
})();

function renderProfile(name) {
  const greeting = document.getElementById("profileGreeting");
  greeting.textContent = name ? `خوش آمدید، ${name}` : "";
  greeting.hidden = !name;
  document.getElementById("displayName").value = name;
}
document.getElementById("profileForm").addEventListener("submit", async event => {
  event.preventDefault();
  try {
    const profile = await api("/settings/profile", {method:"PUT",body:JSON.stringify({display_name:document.getElementById("displayName").value})});
    renderProfile(profile.display_name);
    setMessage("profileMessage", "نام نمایشی ذخیره شد.");
  } catch (error) { setMessage("profileMessage", error.message, true); }
});
api("/settings").then(settings => renderProfile(settings.display_name || "")).catch(error => setMessage("profileMessage", error.message, true));

function entryTrigger(id) {
  return document.getElementById(id === "transactionEntry" ? "toggleTransactionEntry" : "createNewCommitment");
}
function openEntryPanel(id) {
  const panel = document.getElementById(id);
  if (panel.hidden) { panel.returnFocus = document.activeElement; panel.hidden = false; }
  entryTrigger(id).setAttribute("aria-expanded", "true");
  entryTrigger(id).disabled = true;
}
function closeEntryPanel(id, saved = false) {
  const panel = document.getElementById(id);
  if (!saved && panel.dataset.dirty === "true" && !confirm("تغییرات هنوز ذخیره نشده‌اند. فرم بسته شود؟")) return false;
  panel.dataset.dirty = "false";
  panel.hidden = true;
  entryTrigger(id).setAttribute("aria-expanded", "false");
  entryTrigger(id).disabled = false;
  entryTrigger(id).focus({preventScroll:true});
  return true;
}
document.querySelectorAll(".entry-panel").forEach(panel => {
  panel.addEventListener("input", () => { panel.dataset.dirty = "true"; });
  panel.addEventListener("change", () => { panel.dataset.dirty = "true"; });
});
document.querySelectorAll("[data-close-entry]").forEach(button => button.addEventListener("click", () => closeEntryPanel(button.dataset.closeEntry)));
// Keep the create action on the installment page consistent with the main list.
document.querySelector('#installmentManagement .primary[data-page="commitmentManagement"]')?.addEventListener("click", () => document.getElementById("createNewCommitment").click());
