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

function openEntryDialog(id) {
  const dialog = document.getElementById(id);
  if (!dialog.open) {
    dialog.returnFocus = document.activeElement;
    dialog.showModal();
    dialog.scrollTop = 0;
  }
}
function closeEntryDialog(id, saved = false) {
  const dialog = document.getElementById(id);
  if (!saved && dialog.dataset.dirty === "true" && !confirm("تغییرات هنوز ذخیره نشده‌اند. فرم بسته شود؟")) return false;
  dialog.dataset.dirty = "false";
  dialog.close();
  dialog.returnFocus?.focus({preventScroll:true});
  if (id === "transactionEntry") document.getElementById("toggleTransactionEntry").setAttribute("aria-expanded", "false");
  return true;
}
document.querySelectorAll(".entry-dialog").forEach(dialog => {
  dialog.addEventListener("input", () => { dialog.dataset.dirty = "true"; });
  dialog.addEventListener("change", () => { dialog.dataset.dirty = "true"; });
  dialog.addEventListener("cancel", event => { event.preventDefault(); closeEntryDialog(dialog.id); });
});
document.querySelectorAll("[data-close-entry]").forEach(button => button.addEventListener("click", () => closeEntryDialog(button.dataset.closeEntry)));
// Keep the create action on the installment page consistent with the main list.
document.querySelector('#installmentManagement .primary[data-page="commitmentManagement"]')?.addEventListener("click", () => document.getElementById("createNewCommitment").click());
