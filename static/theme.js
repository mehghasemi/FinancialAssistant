/* Apply before styles render; preference belongs to this browser/device. */
(() => {
  let theme = "light";
  try { theme = localStorage.getItem("financial-assistant-theme") === "dark" ? "dark" : "light"; } catch (_) {}
  document.documentElement.dataset.theme = theme;
  document.addEventListener("DOMContentLoaded", () => {
    const button = document.getElementById("themeToggle");
    const update = () => {
      const dark = document.documentElement.dataset.theme === "dark";
      button.setAttribute("aria-pressed", String(dark));
      button.textContent = dark ? "☀  نمای روشن" : "☾  نمای تاریک";
      button.setAttribute("aria-label", dark ? "تغییر به نمای روشن" : "تغییر به نمای تاریک");
    };
    button.addEventListener("click", () => {
      const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      try { localStorage.setItem("financial-assistant-theme", next); } catch (_) {}
      update();
    });
    update();
  });
})();
