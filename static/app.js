const api = (path, options = {}) => fetch(`/api${path}`, { headers: { "Content-Type": "application/json" }, ...options }).catch(() => { throw new Error("ارتباط با برنامه قطع شده است. فایل FinancialAssistant.exe را اجرا کنید و صفحه را دوباره بارگذاری کنید."); }).then(async response => {
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(typeof data.detail === "object" ? data.detail.message : data.detail || "خطا در ارتباط با برنامه");
    error.code = data.detail?.code; error.candidates = data.detail?.candidates; throw error;
  }
  if (options.method && options.method !== "GET" && typeof loadDataStatus === "function") loadDataStatus();
  return data;
});

const currency = value => `${Number(value || 0).toLocaleString("fa-IR")} تومان`;
// Status classes are shared by report, commitment and installment grids.
const paymentRowClass = status => ({paid:"payment-paid", settled:"payment-paid", unpaid:"payment-unpaid", unsettled:"payment-unpaid", partial:"payment-partial", overdue:"payment-overdue", cancelled:"payment-cancelled"}[status] || "");
function summaryHint(label, description, id) {
  return `<span class="card-hint"><button type="button" aria-label="راهنمای ${escapeHtml(label)}" aria-describedby="${id}">؟</button><span class="hint-text" role="tooltip" id="${id}">${escapeHtml(description)}</span></span>`;
}
function updateNavigation(page) {
  document.querySelectorAll(".nav-link").forEach(link => link.classList.toggle("active", link.dataset.page === page));
  const groups = [
    ["settingsNavigation","settingsSubmenu",["settings","baseData","backupSettings","importSettings","maintenanceSettings","auditLog","releases"]],
    ["financeNavigation","financeSubmenu",["financeHome","transactions","budgets"]],
    ["commitmentsNavigation","commitmentsSubmenu",["commitmentsHome","commitmentManagement","installmentManagement"]]
  ];
  for(const [buttonId,menuId,pages] of groups) {
    const active=pages.includes(page), button=document.getElementById(buttonId);
    document.getElementById(menuId).hidden=!active;
    button.setAttribute("aria-expanded",String(active));
    button.classList.toggle("active",active);
  }
}

const statusLabel = { paid: "پرداخت‌شده", partial: "پرداخت جزئی", overdue: "معوق", unpaid: "پرداخت‌نشده" };
const jalaliMonths = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"];
let accounts = [], categories = [], commitmentFilters = [], commitmentList = [], currentInstallments = [], baseInstallments = [], commitmentPreview = null;
let commitmentSort = { key: "unique_code", direction: "asc" };
let selectedCommitmentId = null;
let commitmentGridFilters = { kind: new Set(), start_year: new Set(), end_year: new Set(), status: new Set(), overdue: new Set() };
const commitmentStatusNames = { settled: "تسویه‌شده", unsettled: "تسویه‌نشده" };
const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
const persianDigits = value => String(value).replace(/\d/g, digit => "۰۱۲۳۴۵۶۷۸۹"[digit]);
const latinDigits = value => String(value).replace(/[۰-۹]/g, digit => "۰۱۲۳۴۵۶۷۸۹".indexOf(digit)).replace(/[٠-٩]/g, digit => "٠١٢٣٤٥٦٧٨٩".indexOf(digit));
const amountNumber = value => Number(latinDigits(value).replace(/[٬,\s]/g, "")) || 0;
function auditText(value) {
  if (typeof value === "string") return value.replace(/\b\d{4}-\d{2}-\d{2}\b/g, date => {
    const formatted = new Intl.DateTimeFormat("fa-IR-u-ca-persian", { year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(`${date}T12:00:00`));
    return formatted;
  });
  return auditText(JSON.stringify(value));
}

function currentJalaliParts() {
  const parts = new Intl.DateTimeFormat("en-US-u-ca-persian", { year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date());
  return Object.fromEntries(parts.filter(part => ["year", "month", "day"].includes(part.type)).map(part => [part.type, Number(part.value)]));
}
function jalaliMonthKey(year, month) { return `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}`; }
function offsetJalaliMonth(year, month, offset) { const index = year * 12 + month - 1 + offset; return { year: Math.floor(index / 12), month: index % 12 + 1 }; }
function jalaliMonthLabel(key) { const [year, month] = key.split("-").map(Number); return `${jalaliMonths[month - 1]} ${persianDigits(year)}`; }
function todayJalali() { const now = currentJalaliParts(); return `${persianDigits(String(now.year).padStart(4, "0"))}/${persianDigits(String(now.month).padStart(2, "0"))}/${persianDigits(String(now.day).padStart(2, "0"))}`; }
function toJalaliDate(isoDate) {
  if (!isoDate) return "";
  const date = new Date(`${isoDate}T12:00:00`);
  const parts = new Intl.DateTimeFormat("fa-IR-u-ca-persian", { year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(date);
  const year = parts.find(p => p.type === "year")?.value || "";
  const month = parts.find(p => p.type === "month")?.value || "";
  const day = parts.find(p => p.type === "day")?.value || "";
  return `${year}/${month}/${day}`;
}
function setMessage(id, message, error = false) { const node = document.getElementById(id); node.textContent = message; node.classList.toggle("error", error); }
function renderTotals(id, cells) {
  const table = document.getElementById(id).closest("table");
  const footer = table.tFoot || table.createTFoot();
  footer.innerHTML = `<tr>${cells.map((cell, index) => index === 0 ? `<th scope="row">${cell}</th>` : `<td>${cell}</td>`).join("")}</tr>`;
}
function sumField(items, field) { return items.reduce((sum, item) => sum + Number(item[field] || 0), 0); }
function renderRows(id, rows, colspan) { document.getElementById(id).innerHTML = rows.length ? rows.join("") : `<tr><td colspan="${colspan}" class="empty-cell">داده‌ای برای نمایش نیست.</td></tr>`; TableSort.refresh(id); }
function accountOptions() { return `<option value="">حساب انتخاب نشده</option>${accounts.map(account => `<option value="${account.id}">${escapeHtml(account.name)}</option>`).join("")}`; }
function formatAmountInput(input) { Money.format(input); }

function populateMonthSelectors() {
  const now = currentJalaliParts(); const current = jalaliMonthKey(now.year, now.month);

  document.getElementById("transactionMonth").innerHTML = `<option value="">همهٔ ماه‌ها</option>${jalaliMonths.map((name,index)=>`<option value="${String(index+1).padStart(2,"0")}">${name}</option>`).join("")}`;

  document.getElementById("dashboardMonth").value = current;
  document.getElementById("transactionMonth").value = String(now.month).padStart(2,"0");
  document.getElementById("reportYear").value = persianDigits(now.year);
  document.getElementById("installmentMonth").value = current;
}
function setJalaliDateDefaults() {
  const now = currentJalaliParts(); const next = offsetJalaliMonth(now.year, now.month, 1);
  document.getElementById("transactionDate").value = todayJalali();
  document.getElementById("firstDueDate").value = `${persianDigits(String(next.year).padStart(4, "0"))}/${persianDigits(String(next.month).padStart(2, "0"))}/۰۱`;
}

async function loadReferenceData() {
  [accounts, categories, commitmentFilters, commitmentList] = await Promise.all([api("/accounts"), api("/categories"), api("/commitment-filters"), api("/commitments")]);
  document.getElementById("transactionAccount").innerHTML = accountOptions();
  document.getElementById("installmentCommitment").innerHTML = `<option value="">همهٔ تعهدات</option>${commitmentFilters.map(item => `<option value="${escapeHtml(JSON.stringify([item.title, item.total_amount]))}">${escapeHtml(item.title)}${item.total_amount === null ? "" : ` (${currency(item.total_amount)})`}</option>`).join("")}`;
  renderCommitmentGrid();
  updateCategories();
}
function updateCategories() { const type = document.getElementById("transactionType").value; document.getElementById("transactionCategory").innerHTML = `<option value="">بدون دسته‌بندی</option>` + categories.filter(item => item.transaction_type === type).map(item => `<option value="${item.id}">${escapeHtml(item.name)}</option>`).join(""); }
function commitmentDisplay(item) {
  const year = value => value ? latinDigits(toJalaliDate(value)).split("/")[0] : "نامشخص";
  const remainingCount = Math.max(0, item.installment_count - item.paid_installment_count);
  return { ...item, remaining_amount: Math.max(0, item.planned_amount - item.paid_amount),
    remaining_installment_count: remainingCount,
    status: item.installment_count > 0 && remainingCount === 0 ? "settled" : "unsettled",
    start_year: year(item.first_due_date), end_year: year(item.last_due_date),
    overdue: item.overdue_installment_count > 0 ? "yes" : "no" };
}
function matchesCommitmentFilters(item, excluded = null) {
  const search = latinDigits(document.getElementById("commitmentSearch").value).trim().toLocaleLowerCase();
  if (search && !latinDigits(`${item.unique_code} ${item.title}`).toLocaleLowerCase().includes(search)) return false;
  return Object.entries(commitmentGridFilters).every(([key, values]) => key === excluded || !values.size || values.has(item[key]));
}
function renderCommitmentFilters(items) {
  for (const [filter, selected] of Object.entries(commitmentGridFilters)) {
    const facet = document.querySelector(`#commitmentGridFilters [data-filter="${filter}"]`);
    const label = { kind: "همهٔ انواع", start_year: "همهٔ سال‌ها", end_year: "همهٔ سال‌ها", status: "همهٔ وضعیت‌ها", overdue: "همه" }[filter];
    const available = new Set(items.filter(item => matchesCommitmentFilters(item, filter)).map(item => item[filter]));
    const values = filter === "status" ? Object.keys(commitmentStatusNames) : filter === "overdue" ? ["yes", "no"] : [...new Set(items.map(item => item[filter]))].sort((a,b) => a.localeCompare(b,"fa"));
    const display = value => filter === "status" ? commitmentStatusNames[value] : filter === "overdue" ? (value === "yes" ? "دارد" : "ندارد") : filter.endsWith("year") ? persianDigits(value) : value;
    facet.querySelector("summary").textContent = selected.size ? [...selected].map(display).join("، ") : label;
    facet.querySelector(".facet-options").innerHTML = `<label><input type="checkbox" value="" ${selected.size ? "" : "checked"}>${label}</label>` + values.map(value => `<label><input type="checkbox" value="${escapeHtml(value)}" ${selected.has(value) ? "checked" : ""} ${!available.has(value) && !selected.has(value) ? "disabled" : ""}>${escapeHtml(display(value))}</label>`).join("");
  }
}
function renderCommitmentGrid() {
  const items = commitmentList.map(commitmentDisplay);
  renderCommitmentFilters(items);
  const filtered = items.filter(item => matchesCommitmentFilters(item));
  const { key, direction } = commitmentSort;
  filtered.sort((a, b) => {
    const x = a[key], y = b[key];
    if (x == null || y == null) return x == null && y == null ? a.id - b.id : x == null ? 1 : -1;
    const comparison = typeof x === "string" ? x.localeCompare(y, "fa") : x - y;
    return (direction === "asc" ? comparison : -comparison) || a.id - b.id;
  });
  document.querySelectorAll(".commitment-grid-panel th[data-sort]").forEach(th => {
    const active = th.dataset.sort === key;
    th.setAttribute("aria-sort", active ? direction === "asc" ? "ascending" : "descending" : "none");
    th.classList.toggle("sort-active", active);
    th.querySelector(".sort-indicator")?.remove();
    if (active) th.insertAdjacentHTML("beforeend", `<span class="sort-indicator" aria-hidden="true"> ${direction === "asc" ? "▲" : "▼"}</span>`);
  });
  renderTotals("commitmentRows", ["جمع نتایج فیلتر", "", "", "", "", currency(sumField(filtered, "total_amount")), "—", persianDigits(sumField(filtered, "installment_count")), currency(sumField(filtered, "remaining_amount")), persianDigits(sumField(filtered, "remaining_installment_count")), "", persianDigits(sumField(filtered, "overdue_installment_count")), ""]);
  renderRows("commitmentRows", filtered.map(item => `<tr class="commitment-${item.status} ${paymentRowClass(item.status)}"><td>${escapeHtml(item.unique_code)}</td><td>${escapeHtml(item.kind)}</td><td>${escapeHtml(item.title)}</td><td>${toJalaliDate(item.first_due_date) || "—"}</td><td>${toJalaliDate(item.last_due_date) || "—"}</td><td>${item.total_amount == null ? "—" : currency(item.total_amount)}</td><td>${item.installment_amount_variants > 1 ? "متغیر" : item.installment_amount == null ? "—" : currency(item.installment_amount)}</td><td>${persianDigits(item.installment_count)}</td><td>${currency(item.remaining_amount)}</td><td>${persianDigits(item.remaining_installment_count)}</td><td><span class="badge ${item.status}">${commitmentStatusNames[item.status]}</span></td><td><span class="badge ${item.overdue === "yes" ? "overdue" : ""}">${item.overdue === "yes" ? `${persianDigits(item.overdue_installment_count)} قسط` : "ندارد"}</span></td><td><button class="quiet view-commitment" data-id="${item.id}">مشاهدهٔ جزئیات</button><button class="quiet edit-grid-group" data-id="${item.id}">ویرایش تعهد</button><button class="quiet delete-commitment" data-id="${item.id}">حذف کامل</button></td></tr>`), 13);
}

let dashboardData = null;
let dashboardActionPeriod = "overdue";
let dashboardExpanded = false;

function renderDashboardActions() {
  if (!dashboardData) return;
  const groups = { overdue: dashboardData.overdue_installments, today: dashboardData.today_installments, week: dashboardData.next_week_installments };
  const items = groups[dashboardActionPeriod];
  const emptyMessages = { overdue: "قسط معوق ندارید", today: "برای امروز پرداختی باقی نمانده است", week: "در ۷ روز آینده قسط پرداخت‌نشده‌ای ندارید" };
  document.querySelectorAll("[data-action-period]").forEach(button => {
    button.setAttribute("aria-pressed", String(button.dataset.actionPeriod === dashboardActionPeriod));
    button.querySelector("span").textContent = persianDigits(groups[button.dataset.actionPeriod].length);
  });
  document.getElementById("dashboardActionSummary").textContent = items.length ? `${persianDigits(items.length)} قسط · جمع مانده: ${currency(items.reduce((sum, item) => sum + item.remaining_amount, 0))}` : "";
  const visible = dashboardExpanded ? items : items.slice(0, 4);
  document.getElementById("dashboardActionList").innerHTML = visible.length ? visible.map(item => {
    const timing = item.days_overdue > 0 ? `${persianDigits(item.days_overdue)} روز تأخیر` : item.days_overdue === 0 ? "سررسید امروز" : `${persianDigits(-item.days_overdue)} روز دیگر`;
    return `<div class="dashboard-action-row"><div class="action-description"><b>${escapeHtml(item.title)}</b><small>${persianDigits(escapeHtml(item.due_date))} <span class="due-badge ${dashboardActionPeriod}">${timing}</span></small></div><strong>${currency(item.remaining_amount)}</strong><button class="quiet dashboard-detail" data-id="${item.commitment_id}">جزئیات و پرداخت</button></div>`;
  }).join("") : `<div class="dashboard-empty"><span aria-hidden="true">✓</span><p>${emptyMessages[dashboardActionPeriod]}</p></div>`;
  const more = document.getElementById("dashboardShowAll");
  more.hidden = items.length <= 4;
  more.textContent = dashboardExpanded ? "نمایش کمتر" : `مشاهدهٔ همهٔ ${persianDigits(items.length)} قسط`;
  more.setAttribute("aria-expanded", String(dashboardExpanded));
}

async function loadDashboard() {
  if (typeof refreshPeriodButtons === "function") refreshPeriodButtons();
  const data = await api(`/dashboard?month=${document.getElementById("dashboardMonth").value}`);
  if (data.month !== document.getElementById("dashboardMonth").value) return;
  dashboardData = data;
  [["dashboardPlanned", data.planned_commitments], ["dashboardTotal", data.total_expenses], ["dashboardBalance", data.monthly_balance], ["incomeValue", data.income], ["expenseValue", data.expense], ["remainingValue", data.remaining_commitments], ["plannedValue", data.planned_commitments], ["paidValue", data.paid_commitments]].forEach(([id, value]) => {
    document.getElementById(id).innerHTML = `${Number(value || 0).toLocaleString("fa-IR")} <span class="currency-unit">تومان</span>`;
  });
  document.getElementById("dashboardPeriod").textContent = `خلاصهٔ ${data.month_label}`;
  document.getElementById("dashboardToday").textContent = todayJalali();
  document.getElementById("commitmentSummary").textContent = `${data.month_label} · ${persianDigits(data.open_count)} سررسید باز`;
  const percent = data.planned_commitments ? Math.min(100, data.paid_commitments / data.planned_commitments * 100) : 0;
  document.getElementById("commitmentProgress").style.width = `${percent}%`;
  document.getElementById("commitmentProgressTrack").setAttribute("aria-valuenow", String(percent));
  document.getElementById("commitmentPercent").textContent = data.planned_commitments ? `${percent.toLocaleString("fa-IR", { maximumFractionDigits: 1 })}٪` : "—";
  document.getElementById("commitmentProgressLabel").textContent = data.planned_commitments ? "از مبلغ اقساط این ماه پرداخت شده" : "برای این ماه قسطی ثبت نشده است";
  renderDashboardActions();
  renderDashboardCash(data);
}
async function loadTransactions() { await loadFinancialReport(); }
function installmentQuery(includeStatus = false) {
  if (typeof refreshPeriodButtons === "function") refreshPeriodButtons();
  const params = new URLSearchParams();
  if (selectedCommitmentId !== null) return new URLSearchParams({ commitment_id: selectedCommitmentId }).toString();
  [["month", "installmentMonth"], ["search", "installmentSearch"]].forEach(([key, id]) => { const value = document.getElementById(id).value.trim(); if (value) params.set(key, value); });
  if (includeStatus && document.getElementById("installmentStatus").value) params.set("status", document.getElementById("installmentStatus").value);
  const filterValue = document.getElementById("installmentCommitment").value;
  if (filterValue) {
    const [title, total] = JSON.parse(filterValue);
    params.set("commitment_title", title);
    if (total === null) params.set("commitment_total_missing", "true");
    else params.set("commitment_total", total);
  }
  return params.toString();
}

function updateStatusFilter(items) {
  const select = document.getElementById("installmentStatus");
  const selected = select.value;
  const order = ["unpaid", "partial", "overdue", "paid"];
  const counts = Object.fromEntries(order.map(status => [status, items.filter(item => item.status === status).length]));
  select.innerHTML = `<option value="">همهٔ وضعیت‌ها</option>${order.filter(status => counts[status]).map(status => `<option value="${status}">${statusLabel[status]} (${persianDigits(counts[status])})</option>`).join("")}`;
  select.value = counts[selected] ? selected : "";
}

function renderInstallmentRows() {
  const selectedStatus = document.getElementById("installmentStatus").value;
  currentInstallments = selectedStatus ? baseInstallments.filter(item => item.status === selectedStatus) : baseInstallments;
  renderTotals("installmentRows", ["جمع نتایج فیلتر", "", "", currency(sumField(currentInstallments, "amount")), currency(sumField(currentInstallments, "paid_amount")), currency(sumField(currentInstallments, "remaining_amount")), "", ""]);
  renderRows("installmentRows", currentInstallments.map(item => {
    const paymentButton = item.remaining_amount > 0 ? `<button class="quiet pay-installment" data-id="${item.id}">پرداخت</button>` : "";
    return `<tr class="${paymentRowClass(item.status)}"><td>${selectedCommitmentId !== null ? `قسط ${persianDigits(baseInstallments.indexOf(item) + 1)}` : escapeHtml(item.title)}</td><td>${item.due_date}</td><td>${item.payment_dates.map(persianDigits).join("، ") || "—"}${item.payment_date_assumed ? " (نیازمند تأیید)" : ""}</td><td>${currency(item.amount)}</td><td>${currency(item.paid_amount)}</td><td>${currency(item.remaining_amount)}</td><td><span class="badge ${item.status}">${statusLabel[item.status]}</span></td><td class="row-actions"><button class="quiet edit-commitment" data-id="${item.id}">ویرایش تعهد</button><button class="quiet edit-installment" data-id="${item.id}">ویرایش قسط</button>${paymentButton}<button class="quiet payment-details" data-id="${item.id}">ریز پرداخت‌ها</button></td></tr>`;
  }), 8);
}
async function openCommitmentDetails(id) {
  selectedCommitmentId = id;
  document.getElementById("installmentStatus").value = "";
  document.querySelectorAll(".page").forEach(section => section.classList.toggle("active", section.id === "installmentManagement"));
  updateNavigation("commitmentManagement");
  await loadInstallments();
}
function renderCommitmentDetailSummary() {
  const item = commitmentList.find(item => item.id === selectedCommitmentId);
  const detail = document.getElementById("commitmentDetailSummary");
  detail.hidden = !item;
  document.querySelector("#installmentManagement thead th").textContent = item ? "شمارهٔ قسط" : "تعهد";
  document.querySelector("#installmentManagement header h1").textContent = item ? `اقساط تعهد ${item.unique_code} — ${item.title}` : "مدیریت اقساط و پرداخت‌ها";
  for (const id of ["installmentMonth", "installmentCommitment", "installmentSearch"]) document.getElementById(id).closest(".field").hidden = !!item;
  document.getElementById("clearInstallmentFilters").hidden = !!item;
  if (item) {
    const display = commitmentDisplay(item);
    document.getElementById("commitmentDetailValues").textContent = `نوع: ${item.kind} | اصل تعهد: ${item.total_amount == null ? "—" : currency(item.total_amount)} | بازپرداخت: ${currency(item.repayment_amount ?? item.planned_amount)} | پرداخت‌شده: ${currency(item.paid_amount)} | ماندهٔ اقساط: ${currency(display.remaining_amount)} | ${commitmentStatusNames[display.status]}`;
  }
}
async function loadInstallments() {
  renderCommitmentDetailSummary();
  const query = installmentQuery(); baseInstallments = await api(`/installments${query ? `?${query}` : ""}`);
  updateStatusFilter(baseInstallments); renderInstallmentRows();
}

function openInlinePayment(installmentId) {
  const item = currentInstallments.find(row => row.id === installmentId); if (!item) return;
  document.querySelectorAll(".inline-payment-row").forEach(row => row.remove());
  const target = document.querySelector(`.pay-installment[data-id="${installmentId}"]`)?.closest("tr"); if (!target) return;
  target.insertAdjacentHTML("afterend", `<tr class="inline-payment-row"><td colspan="8"><form class="inline-payment-form" data-id="${item.id}"><b>ثبت پرداخت: ${escapeHtml(item.title)} — ${item.due_date}</b><div class="inline-payment-fields"><div class="field"><label>مبلغ پرداخت</label><input name="amount" data-amount inputmode="numeric" value="${item.remaining_amount.toLocaleString("fa-IR")}" required /></div><div class="field"><label>تاریخ پرداخت شمسی</label><input data-jalali="day" name="paid_on" inputmode="numeric" value="${todayJalali()}" required /></div><div class="field"><label>حساب</label><select name="account_id">${accountOptions()}</select></div><div class="field"><label>یادداشت</label><input name="note" maxlength="300" placeholder="اختیاری" /></div><button class="primary" type="submit">ثبت پرداخت</button><button class="quiet cancel-inline-payment" type="button">انصراف</button></div><p class="form-message" role="status"></p></form></td></tr>`);
}
async function openPaymentDetails(installmentId, trigger) {
  document.querySelectorAll(".payment-details-row").forEach(row => row.remove());
  const row = trigger.closest("tr");
  const details = await api(`/installments/${installmentId}/details`);
  const payments = details.payments.map(payment => `<form class="payment-edit-form inline-edit-fields" data-id="${payment.id}"><span>پرداخت #${persianDigits(payment.id)}${payment.paid_date_assumed ? "؛ تاریخ فرض‌شده: بررسی و با ذخیره تأیید کنید" : ""}</span><input name="amount" aria-label="مبلغ پرداخت" data-amount inputmode="numeric" value="${Number(payment.amount).toLocaleString("fa-IR")}" required /><input data-jalali="day" name="paid_on" aria-label="تاریخ پرداخت شمسی" value="${escapeHtml(payment.paid_on)}" required /><select name="account_id" aria-label="حساب"><option value="">بدون حساب</option>${accounts.map(account => `<option value="${account.id}" ${account.id === payment.account_id ? "selected" : ""}>${escapeHtml(account.name)}</option>`).join("")}</select><input name="note" aria-label="یادداشت" maxlength="300" value="${escapeHtml(payment.note || "")}" /><button class="quiet" type="submit">ذخیره پرداخت</button><button class="quiet delete-payment" type="button" data-id="${payment.id}">حذف پرداخت</button></form>`).join("") || "پرداختی ثبت نشده است.";
  const history = details.history.map(log => `<li>${escapeHtml(log.created_at)} · ${escapeHtml({ restore: "بازیابی", create: "ثبت", update: "ویرایش", delete: "حذف" }[log.action] || log.action)} ${escapeHtml({ commitment: "تعهد", installment: "قسط", payment: "پرداخت", asset: "دارایی" }[log.resource_type] || log.resource_type)} · ${auditDetails(log.details)}</li>`).join("") || "<li>تغییری ثبت نشده است.</li>";
  row.insertAdjacentHTML("afterend", `<tr class="payment-details-row"><td colspan="8"><b>ریز پرداخت‌ها</b>${payments}<details><summary>تاریخچه تغییرات</summary><ul>${history}</ul></details><p class="form-message" role="status"></p><button class="quiet close-payment-details" type="button">بستن</button></td></tr>`);
}
function openInlineCommitmentEdit(installmentId) {
  const installment = currentInstallments.find(row => row.id === installmentId);
  const item = commitmentList.find(row => row.id === installment?.commitment_id);
  const target = document.querySelector(`.edit-commitment[data-id="${installmentId}"]`)?.closest("tr");
  if (item && target) openCommitmentEditor(item, target, false);
}
function openInlineInstallmentEdit(installmentId) {
  const item = currentInstallments.find(row => row.id === installmentId); if (!item) return;
  document.querySelectorAll(".inline-edit-row").forEach(row => row.remove());
  const target = document.querySelector(`.edit-installment[data-id="${installmentId}"]`)?.closest("tr"); if (!target) return;
  target.insertAdjacentHTML("afterend", `<tr class="inline-edit-row"><td colspan="8"><form class="inline-installment-form" data-id="${item.id}"><b>ویرایش جزئی قسط</b><p>تغییر مبلغ، بازپرداخت کل تعهد را به همان اندازه تغییر می‌دهد؛ سایر اقساط ثابت می‌مانند.</p><div class="inline-edit-fields"><div class="field"><label>سررسید شمسی</label><input data-jalali="day" name="due_date" inputmode="numeric" value="${item.due_date}" required /></div><div class="field"><label>مبلغ قسط</label><input name="amount" data-amount inputmode="numeric" value="${Number(item.amount).toLocaleString("fa-IR")}" required /></div><div class="field"><label>یادداشت</label><input name="note" maxlength="300" value="${escapeHtml(item.note || "")}" /></div><button class="primary" type="submit">ذخیرهٔ قسط</button><button class="quiet cancel-inline-edit" type="button">انصراف</button></div><p class="form-message" role="status"></p></form></td></tr>`);
}
function openGridCommitmentEdit(commitmentId, trigger = null) {
  const item = commitmentList.find(row => row.id === commitmentId);
  const target = (trigger || document.querySelector(`.edit-grid-group[data-id="${commitmentId}"]`))?.closest("tr");
  if (item && target) openCommitmentEditor(item, target, true);
}
function openCommitmentEditor(item, target, grid) {
  document.querySelectorAll(".inline-grid-edit-row, .inline-edit-row").forEach(row => row.remove());
  const amount = value => value == null ? "" : Number(value).toLocaleString("fa-IR");
  const firstDue = item.first_due_date ? toJalaliDate(item.first_due_date) : "";
  const rowClass = grid ? "inline-grid-edit-row" : "inline-edit-row";
  const cancelClass = grid ? "cancel-grid-edit" : "cancel-inline-edit";
  target.insertAdjacentHTML("afterend", `<tr class="${rowClass}"><td colspan="${grid ? 13 : 7}">
    <form class="inline-commitment-form" data-id="${item.id}"><b>ویرایش تعهد و همهٔ اقساط آن</b>
    <div class="inline-edit-fields">
      <div class="field"><label>کد تعهد (ثابت)<input name="unique_code" value="${escapeHtml(item.unique_code)}" readonly /></label></div>
      <div class="field"><label>عنوان<input name="title" minlength="2" maxlength="120" value="${escapeHtml(item.title)}" required /></label></div>
      <div class="field"><label>نوع<input name="kind" minlength="2" maxlength="50" value="${escapeHtml(item.kind)}" required /></label></div>
      <div class="field"><label>مبلغ وام / اصل تعهد<input name="total_amount" data-amount inputmode="numeric" value="${amount(item.total_amount)}" /></label></div>
      <div class="field"><label>مبلغ بازپرداخت<input name="repayment_amount" data-amount inputmode="numeric" value="${amount(item.repayment_amount ?? item.total_amount ?? item.planned_amount)}" required /></label></div>
      <div class="field"><label>تعداد اقساط<input name="installment_count" type="text" data-count inputmode="numeric" min="1" max="600" value="${item.installment_count}" required /></label></div>
      <div class="field"><label>مبلغ اقساط عادی<input name="installment_amount" data-amount inputmode="numeric" value="${amount(item.installment_amount)}" required /></label></div>
      <div class="field"><label>دورهٔ پرداخت (ماه)<input name="interval_months" type="text" data-count inputmode="numeric" min="1" max="12" value="${item.interval_months ?? ""}" placeholder="برای بازتنظیم سررسیدها وارد کنید" /></label></div>
      <div class="field"><label>تاریخ اولین قسط (شمسی)<input data-jalali="day" name="first_due_date" inputmode="numeric" value="${escapeHtml(firstDue)}" required /></label></div>
      <div class="field"><label>تاریخ پایان فعلی (محاسبه‌شده)<input value="${escapeHtml(toJalaliDate(item.last_due_date))}" readonly /></label></div>
      <div class="field"><label>جمع اقساط فعلی<input value="${amount(item.planned_amount)}" readonly /></label></div>
      <div class="field"><label>پرداخت‌شده<input value="${amount(item.paid_amount)}" readonly /></label></div>
    </div><p class="help-text">تغییرات روی اقساط همین کد اعمال می‌شود. پرداخت‌های ثبت‌شده حفظ می‌شوند؛ اختلاف مبلغ روی قسط آخر محاسبه می‌شود.</p>
    <button class="primary" type="submit">ذخیرهٔ تعهد و اقساط</button><button class="quiet ${cancelClass}" type="button">انصراف</button>
    <p class="form-message" role="status"></p></form></td></tr>`);
  const form = target.nextElementSibling.querySelector("form");
  if (item.installment_amount_variants > 1) {
    form.querySelector(".inline-edit-fields").insertAdjacentHTML("beforebegin", `<label class="toggle-field"><input type="checkbox" name="normalize_amounts" /> یکسان‌سازی مبلغ همهٔ اقساط با مبلغ اقساط عادی و محاسبهٔ بازپرداخت کل (اقساط فعلی مبالغ متفاوت دارند)</label>`);
  }
  const syncRepayment = () => {
    const amount = amountNumber(form.elements.namedItem("installment_amount").value);
    const count = amountNumber(form.elements.namedItem("installment_count").value);
    if (amount > 0 && count > 0) form.elements.namedItem("repayment_amount").value = (amount * count).toLocaleString("fa-IR");
  };
  form.elements.namedItem("installment_amount").addEventListener("input", () => {
    if (form.elements.namedItem("normalize_amounts")) form.elements.namedItem("normalize_amounts").checked = true;
    syncRepayment(); Money.scan(form);
  });
  form.elements.namedItem("normalize_amounts")?.addEventListener("change", event => { if (event.target.checked) { syncRepayment(); Money.scan(form); } });

  form.querySelectorAll("input").forEach(input => { input.dataset.original = input.value; });
  ["repayment_amount", "installment_count"].forEach(name => form.elements.namedItem(name).addEventListener("input", () => {
    const total = amountNumber(form.elements.namedItem("repayment_amount").value);
    const count = amountNumber(form.elements.namedItem("installment_count").value);
    if (total > 0 && count > 0) form.elements.namedItem("installment_amount").value = Math.floor(total / count).toLocaleString("fa-IR");
  }));
}
function commitmentPayload() { return { title: document.getElementById("commitmentTitle").value, kind: document.getElementById("commitmentKind").value, total_amount: amountNumber(document.getElementById("commitmentTotal").value) || null, repayment_amount: amountNumber(document.getElementById("installmentAmount").value) * amountNumber(document.getElementById("installmentCount").value), installment_amount: amountNumber(document.getElementById("installmentAmount").value), installment_count: amountNumber(document.getElementById("installmentCount").value), first_due_date: document.getElementById("firstDueDate").value, interval_months: amountNumber(document.getElementById("intervalMonths").value) }; }
async function previewCommitment() {
  setMessage("commitmentMessage", "");
  try {
    if (!document.getElementById("commitmentForm").reportValidity()) return;
    commitmentPreview = await api("/commitments/preview", { method: "POST", body: JSON.stringify(commitmentPayload()) });
    document.getElementById("previewSummary").textContent = `${persianDigits(commitmentPreview.installments.length)} قسط · از ${commitmentPreview.first_due_date} تا ${commitmentPreview.last_due_date} · جمع ${currency(commitmentPreview.planned_total)}`;
    document.getElementById("lastDueDate").value = commitmentPreview.last_due_date;
    renderTotals("previewRows", ["جمع اقساط", "", currency(sumField(commitmentPreview.installments, "amount"))]);
    renderRows("previewRows", commitmentPreview.installments.map(item => `<tr><td>${persianDigits(item.number)}</td><td>${item.due_date}</td><td>${currency(item.amount)}</td></tr>`), 3);
    document.getElementById("saveCommitment").disabled = false;
  } catch (error) { commitmentPreview = null; document.getElementById("saveCommitment").disabled = true; setMessage("commitmentMessage", error.message, true); }
}
async function refreshAll() { await Promise.all([loadDashboard(), loadTransactions(), loadInstallments()]); if (document.getElementById("transactionDuplicateReview").open) await loadDuplicateTransactions(); }
async function loadReleases() { const items = await api("/releases"); document.getElementById("releaseList").innerHTML = items.length ? items.map(item => `<article class="release-item"><h2>نگارش ${escapeHtml(item.version)} — ${escapeHtml(item.title)}</h2><p class="release-meta">${escapeHtml(item.released_at)} · بخش‌های تحت تأثیر: ${escapeHtml(item.affected_areas)}</p><p>${escapeHtml(item.description)}</p></article>`).join("") : "<p>تاریخچه‌ای ثبت نشده است.</p>"; }
async function loadSettings() { const settings = await api("/settings"); document.getElementById("backupEnabled").checked = settings.backup_enabled; document.getElementById("backupDirectory").value = settings.backup_directory; }

document.getElementById("clearFinancialData").addEventListener("click", async event => {
  if (!confirm("همهٔ اطلاعات مالی و سابقهٔ ایمپورت حذف شوند؟\nپیش از حذف پشتیبان تهیه می‌شود. بازگردانی فقط از طریق پشتیبان امکان‌پذیر است.\nتنظیمات، حساب‌ها و دسته‌بندی‌ها باقی می‌مانند.")) return;
  const button = event.currentTarget;
  button.disabled = true;
  setMessage("clearDataMessage", "در حال تهیهٔ پشتیبان و پاک‌سازی…");
  try {
    const result = await api("/settings/clear-data", {
      method: "POST", body: JSON.stringify({ confirmation: "DELETE_ALL_FINANCIAL_DATA" })
    });
    document.getElementById("importSheet4Result").textContent = "";
    setMessage("importSheet4Message", "");
    setMessage("clearDataMessage", `اطلاعات مالی پاک شد؛ اکنون می‌توانید دوباره ایمپورت کنید. پشتیبان: ${result.backup_path}`);
    try {
      await loadReferenceData();
      await refreshAll();
    } catch (error) {
      setMessage("clearDataMessage", `اطلاعات پاک شد. برای نمایش وضعیت جدید صفحه را تازه کنید. پشتیبان: ${result.backup_path}`, true);
    }
  } catch (error) {
    setMessage("clearDataMessage", error.message, true);
  } finally {
    button.disabled = false;
  }
});

document.querySelectorAll(".nav-link,[data-page]").forEach(button => button.addEventListener("click", () => { const page = button.dataset.page; if (!page || !document.getElementById(page)?.classList.contains("page")) return; document.querySelectorAll(".page").forEach(section => section.classList.toggle("active", section.id === page)); updateNavigation(page); if (page === "commitmentManagement") loadReferenceData().catch(error => setMessage("commitmentMessage", error.message, true)); if (page === "installmentManagement") { selectedCommitmentId = null; loadInstallments().catch(error => alert(error.message)); } if (page === "baseData") loadBaseData().catch(error => setMessage("baseMessage",error.message,true)); if (page === "budgets") loadBudgets(); if (page === "assets") loadAssets(); if (page === "transactions") loadTransactions(); if (page === "backupSettings") loadSettings(); if (page === "auditLog") loadAuditLogs(); }));
document.getElementById("createNewCommitment").addEventListener("click", () => {
  document.getElementById("commitmentForm").reset();
  document.getElementById("previewRows").closest("table").tFoot?.remove(); document.getElementById("previewRows").innerHTML = `<tr><td colspan="3" class="empty-cell">پیش‌نمایشی ایجاد نشده است.</td></tr>`;
  document.getElementById("previewSummary").textContent = "ابتدا اطلاعات را وارد کنید.";
  document.getElementById("saveCommitment").disabled = true;
  commitmentPreview = null;
  setJalaliDateDefaults();
  document.getElementById("installmentCount").value = 12;
  document.getElementById("intervalMonths").value = 1;
  document.getElementById("commitmentForm").scrollIntoView({ behavior: "smooth", block: "start" });
});
document.getElementById("transactionType").addEventListener("change", updateCategories);
document.getElementById("dashboardMonth").addEventListener("change", loadDashboard);

["installmentMonth", "installmentCommitment"].forEach(id => document.getElementById(id).addEventListener("change", loadInstallments));
document.getElementById("installmentStatus").addEventListener("change", renderInstallmentRows);
document.getElementById("installmentSearch").addEventListener("input", () => { clearTimeout(window.installmentSearchTimer); window.installmentSearchTimer = setTimeout(loadInstallments, 250); });
document.getElementById("clearInstallmentFilters").addEventListener("click", () => { ["installmentStatus", "installmentCommitment", "installmentSearch"].forEach(id => document.getElementById(id).value = ""); const now = currentJalaliParts(); document.getElementById("installmentMonth").value = jalaliMonthKey(now.year, now.month); loadInstallments(); });
["installmentAmount", "installmentCount"].forEach(id => document.getElementById(id).addEventListener("input", () => {
  const total = amountNumber(document.getElementById("installmentAmount").value) * amountNumber(document.getElementById("installmentCount").value);
  document.getElementById("commitmentRepayment").value = total > 0 ? total.toLocaleString("fa-IR") : "";
}));
document.getElementById("previewCommitment").addEventListener("click", previewCommitment);
document.querySelectorAll("#commitmentForm input, #commitmentForm select").forEach(input => ["input", "change"].forEach(eventName => input.addEventListener(eventName, () => { if (input.id === "lastDueDate") return; commitmentPreview = null; document.getElementById("saveCommitment").disabled = true; document.getElementById("lastDueDate").value = ""; })));


document.getElementById("commitmentForm").addEventListener("submit", async event => { event.preventDefault(); if (!commitmentPreview) return previewCommitment(); setMessage("commitmentMessage", ""); try { await api("/commitments", { method: "POST", body: JSON.stringify(commitmentPayload()) }); event.target.reset(); setJalaliDateDefaults(); document.getElementById("installmentCount").value = 12; document.getElementById("intervalMonths").value = 1; commitmentPreview = null; document.getElementById("saveCommitment").disabled = true; document.getElementById("previewRows").closest("table").tFoot?.remove(); document.getElementById("previewRows").innerHTML = `<tr><td colspan="3" class="empty-cell">پیش‌نمایشی ایجاد نشده است.</td></tr>`; document.getElementById("previewSummary").textContent = "تعهد ثبت شد."; setMessage("commitmentMessage", "تعهد و همهٔ اقساط آن ثبت شد."); await loadReferenceData(); await refreshAll(); } catch (error) { setMessage("commitmentMessage", error.message, true); } });
document.getElementById("installmentRows").addEventListener("click", async event => { const payment = event.target.closest(".pay-installment"), commitment = event.target.closest(".edit-commitment"), installment = event.target.closest(".edit-installment"), details = event.target.closest(".payment-details"), deletion = event.target.closest(".delete-payment"); if (payment) openInlinePayment(Number(payment.dataset.id)); if (commitment) openInlineCommitmentEdit(Number(commitment.dataset.id)); if (installment) openInlineInstallmentEdit(Number(installment.dataset.id)); if (details) { try { await openPaymentDetails(Number(details.dataset.id), details); } catch (error) { alert(error.message); } } if (deletion && confirm("این پرداخت حذف شود؟ اگر هزینه‌ای به آن متصل باشد، اتصال حذف می‌شود و هزینه در سایر هزینه‌ها محاسبه خواهد شد.")) { try { await api(`/payments/${deletion.dataset.id}`, { method: "DELETE" }); await loadReferenceData(); await refreshAll(); } catch (error) { deletion.closest("tr").querySelector(".form-message").textContent = error.message; } } if (event.target.closest(".cancel-inline-payment, .cancel-inline-edit, .close-payment-details")) event.target.closest("tr").remove(); });
document.getElementById("installmentRows").addEventListener("submit", async event => { const form = event.target.closest(".payment-edit-form"); if (!form) return; event.preventDefault(); const data = new FormData(form); try { await api(`/payments/${form.dataset.id}`, { method: "PATCH", body: JSON.stringify({ amount: amountNumber(data.get("amount")), paid_on: data.get("paid_on"), account_id: Number(data.get("account_id")) || null, note: data.get("note") }) }); await loadReferenceData(); await refreshAll(); } catch (error) { form.closest("tr").querySelector(".form-message").textContent = error.message; } });
document.getElementById("commitmentRows").addEventListener("click", async event => {
  const deletion = event.target.closest(".delete-commitment");
  if (deletion) {
    const item = commitmentList.find(item => item.id === Number(deletion.dataset.id));
    if (!item || !confirm(`تعهد «${item.title}» با کد ${item.unique_code} و تمام اقساط و پرداخت‌های آن حذف شود؟ هزینه‌های متصل مستقل باقی می‌مانند و در سایر هزینه‌ها محاسبه می‌شوند. این کار قابل بازگشت از رابط نیست.`)) return;
    try { await api(`/commitments/${item.id}?confirm=true`, { method: "DELETE" }); selectedCommitmentId = null; await loadReferenceData(); await refreshAll(); }
    catch (error) { alert(error.message); }
    return;
  }
  const view = event.target.closest(".view-commitment");
  if (view) openCommitmentDetails(Number(view.dataset.id)).catch(error => alert(error.message));
  const edit = event.target.closest(".edit-grid-group");
  if (edit) openGridCommitmentEdit(Number(edit.dataset.id), edit.closest("tr"));
  if (event.target.closest(".cancel-grid-edit")) event.target.closest("tr").remove();
});
for (const id of ["installmentRows", "commitmentRows"]) document.getElementById(id).addEventListener("submit", async event => {
  const form = event.target.closest(".inline-commitment-form"); if (!form) return;
  event.preventDefault();
  const message = form.querySelector(".form-message"); message.textContent = "";
  const data = new FormData(form);
  try {
    const changed = (name, numeric = false) => {
      const input = form.elements.namedItem(name);
      return input && (numeric ? amountNumber(input.value) !== amountNumber(input.dataset.original) : input.value !== input.dataset.original);
    };
    const payload = { title: data.get("title"), kind: data.get("kind"), total_amount: amountNumber(data.get("total_amount")) || null };
    for (const name of ["installment_count", "repayment_amount", "installment_amount", "interval_months"]) {
      if (changed(name, true)) payload[name] = amountNumber(data.get(name));
    }
    if (form.elements.namedItem("normalize_amounts")?.checked) {
      payload.installment_amount = amountNumber(data.get("installment_amount"));
      payload.repayment_amount = payload.installment_amount * amountNumber(data.get("installment_count"));
    }
    if (changed("first_due_date") && data.get("first_due_date")) payload.first_due_date = data.get("first_due_date");
    await api(`/commitments/${form.dataset.id}`, { method: "PATCH", body: JSON.stringify(payload) });
    await loadReferenceData(); await refreshAll();
  } catch (error) { message.textContent = error.message; message.classList.add("error"); }
});
document.getElementById("commitmentGridFilters").addEventListener("change", event => {
  const input = event.target.closest('input[type="checkbox"]');
  if (!input) return;
  const facet = input.closest("[data-filter]");
  const filter = facet.dataset.filter;
  if (input.value === "") commitmentGridFilters[filter].clear();
  else if (input.checked) commitmentGridFilters[filter].add(input.value);
  else commitmentGridFilters[filter].delete(input.value);
  renderCommitmentGrid();
  facet.open = false;
});
document.addEventListener("click", event => {
  const currentFacet = event.target.closest("#commitmentGridFilters .facet");
  document.querySelectorAll("#commitmentGridFilters .facet[open]").forEach(facet => {
    if (facet !== currentFacet) facet.open = false;
  });
});
document.addEventListener("keydown", event => {
  if (event.key === "Escape") document.querySelectorAll("#commitmentGridFilters .facet[open]").forEach(facet => { facet.open = false; });
});
document.getElementById("resetCommitmentFilters").addEventListener("click", () => {
  document.getElementById("commitmentSearch").value = "";
  Object.values(commitmentGridFilters).forEach(values => values.clear());
  renderCommitmentGrid();
});
document.querySelectorAll(".commitment-grid-panel th[data-sort]").forEach(th => {
  const sort = () => { commitmentSort = { key: th.dataset.sort, direction: commitmentSort.key === th.dataset.sort && commitmentSort.direction === "asc" ? "desc" : "asc" }; renderCommitmentGrid(); };
  th.addEventListener("click", sort);
  th.addEventListener("keydown", event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); sort(); } });
});
document.addEventListener("change", event => { if (event.target.matches("[data-amount]")) formatAmountInput(event.target); });
document.getElementById("installmentRows").addEventListener("submit", async event => { const form = event.target.closest(".inline-payment-form"); if (!form) return; event.preventDefault(); const message = form.querySelector(".form-message"); message.textContent = ""; const data = new FormData(form); try { await api("/payments", { method: "POST", body: JSON.stringify({ installment_id: Number(form.dataset.id), amount: amountNumber(data.get("amount")), paid_on: data.get("paid_on"), account_id: Number(data.get("account_id")) || null, note: data.get("note") }) }); await refreshAll(); } catch (error) { message.textContent = error.message; message.classList.add("error"); } });
document.getElementById("installmentRows").addEventListener("submit", async event => { const form = event.target.closest(".inline-installment-form"); if (!form) return; event.preventDefault(); const message = form.querySelector(".form-message"); message.textContent = ""; const data = new FormData(form); const payload = { due_date: data.get("due_date"), amount: amountNumber(data.get("amount")), note: data.get("note") }; try { await api(`/installments/${form.dataset.id}`, { method: "PATCH", body: JSON.stringify(payload) }); await loadReferenceData(); await refreshAll(); } catch (error) { message.textContent = error.message; message.classList.add("error"); } });
document.getElementById("settingsForm").addEventListener("submit", async event => { event.preventDefault(); setMessage("settingsMessage", ""); try { await api("/settings", { method: "PUT", body: JSON.stringify({ backup_enabled: document.getElementById("backupEnabled").checked, backup_directory: document.getElementById("backupDirectory").value }) }); setMessage("settingsMessage", "تنظیمات پشتیبان‌گیری ذخیره شد."); } catch (error) { setMessage("settingsMessage", error.message, true); } });
document.getElementById("manualBackup").addEventListener("click", async event => { const button=event.currentTarget; button.disabled=true; document.getElementById("backupMessage").textContent="در حال تهیهٔ پشتیبان…"; try { const result=await api("/backups",{method:"POST"}); document.getElementById("backupMessage").textContent=`پشتیبان ذخیره شد: ${result.path}`; } catch(error) { document.getElementById("backupMessage").textContent=error.message; } finally { button.disabled=false; } });



document.getElementById("importSheet4Submit").addEventListener("click", async () => {
  const input = document.getElementById("importSheet4File");
  const resultBox = document.getElementById("importSheet4Result");
  setMessage("importSheet4Message", "");
  resultBox.innerHTML = "";
  const file = input.files[0];
  if (!file) { setMessage("importSheet4Message", "ابتدا یک فایل اکسل انتخاب کنید.", true); return; }
  const formData = new FormData();
  formData.append("file", file);
  const submitButton = document.getElementById("importSheet4Submit");
  submitButton.disabled = true;
  setMessage("importSheet4Message", "در حال اعتبارسنجی فایل؛ ثبت فقط پس از تأیید صحت همهٔ ردیف‌ها انجام می‌شود…");
  try {
    const result = await api("/imports/sheet4", { method: "POST", body: formData, headers: {} });
    setMessage("importSheet4Message", "ورود اطلاعات با موفقیت انجام شد.");
    const skippedText = result.skipped_rows.length
      ? `${result.skipped_rows.length} ردیف بدون مبلغ معتبر نادیده گرفته شد (ردیف‌های: ${result.skipped_rows.join("، ")})`
      : "همهٔ ردیف‌ها با موفقیت پردازش شدند.";
    resultBox.innerHTML = `
      <div class="list-item"><span>تعهدات ساخته/به‌روزشده</span><b>${result.commitments}</b></div>
      <div class="list-item"><span>اقساط ثبت‌شده</span><b>${result.installments}</b></div>
      <div class="list-item"><span>پرداخت‌های ثبت‌شده</span><b>${result.payments}</b></div>
      <div class="list-item"><span>${skippedText}</span></div>
    `;
    input.value = "";
    await loadReferenceData();
    await refreshAll();
  } catch (error) {
    setMessage("importSheet4Message", error.message, true);
  } finally {
    submitButton.disabled = false;
  }
});

document.getElementById("commitmentSearch").addEventListener("input", renderCommitmentGrid);

const auditLabels = {settled_on:"تاریخ واقعی دریافت/پرداخت",as_of_date:"تاریخ موجودی اولیه",payment_id:"پرداخت متصل",month:"ماه",category_id:"دسته‌بندی",reason:"علت", before:"قبل", after:"بعد", amount:"مبلغ", repayment_amount:"بازپرداخت", total_amount:"اصل تعهد", title:"عنوان", kind:"نوع", due_date:"سررسید", paid_on:"تاریخ پرداخت", note:"یادداشت", account_id:"شناسه حساب", installment_id:"شناسه قسط", commitment_id:"شناسه تعهد", installment_count:"تعداد اقساط", interval_months:"دوره پرداخت", first_due_date:"اولین سررسید", installment_amount:"مبلغ قسط", unique_code:"کد تعهد", installments:"اقساط", backup_enabled:"پشتیبان خودکار", backup_directory:"مسیر پشتیبان", backup_path:"فایل پشتیبان", source:"منبع", transaction_type:"نوع تراکنش", occurred_on:"تاریخ تراکنش", category_id:"شناسه دسته‌بندی", current_value:"ارزش جاری", initial_value:"ارزش اولیه", registered_on:"تاریخ ثبت", change_note:"توضیح تغییر ارزش", counterparty:"طرف حساب", status:"وضعیت" };
const auditTypes = {banks:"بانک",accounts:"حساب",categories:"دسته‌بندی",cash_opening:"موجودی اولیه",budget:"بودجهٔ ماهانه", asset:"دارایی", commitment:"تعهد", installment:"قسط", payment:"پرداخت", transaction:"درآمد و هزینه", settings:"تنظیمات", system:"سیستم" };
function auditDetails(value) {
  if (value && typeof value === "object") return `<dl class="audit-details">${Object.entries(value).map(([key, item]) => `<dt>${escapeHtml(auditLabels[key] || key)}</dt><dd>${auditDetails(item)}</dd>`).join("")}</dl>`;
  return escapeHtml(value == null ? "—" : auditText(String(value)));
}
let auditCursor = null;
async function loadAuditLogs(append = false) {
  const params = new URLSearchParams();
  const type = document.getElementById("auditType").value;
  const id = document.getElementById("auditResourceId").value;
  if (type) params.set("resource_type", type);
  if (id !== "") params.set("resource_id", id);
  if (append && auditCursor) params.set("before_id", auditCursor);
  try {
    const result = await api(`/audit-logs?${params}`);
    const html = result.items.map(item => `<article class="audit-event"><b>${escapeHtml(item.created_at)} · ${{create:"ثبت",update:"ویرایش",delete:"حذف",import:"ورود اکسل"}[item.action] || escapeHtml(item.action)} · ${escapeHtml(auditTypes[item.resource_type.replace("archived_", "")] || item.resource_type)} #${persianDigits(item.resource_id)}${item.resource_type.startsWith("archived_") ? " (بایگانی پیش از پاک‌سازی)" : ""}</b><small>شناسهٔ رویداد: ${persianDigits(item.id)}</small><details><summary>جزئیات تغییر</summary>${auditDetails(item.details)}</details></article>`).join("");
    const target = document.getElementById("auditEvents");
    if (append) target.insertAdjacentHTML("beforeend", html); else target.innerHTML = html || "رویدادی ثبت نشده است.";
    auditCursor = result.next_cursor;
    document.getElementById("auditMore").hidden = !auditCursor;
    setMessage("auditMessage", "");
  } catch (error) { setMessage("auditMessage", error.message, true); }
}
document.getElementById("auditRefresh").addEventListener("click", () => loadAuditLogs());
document.getElementById("auditMore").addEventListener("click", () => loadAuditLogs(true));
function openAuditSection(type, id = "") {
  document.querySelectorAll(".page").forEach(page => page.classList.toggle("active", page.id === "auditLog"));
  updateNavigation("auditLog");
  document.getElementById("auditType").value = type;
  document.getElementById("auditResourceId").value = id;
  loadAuditLogs();
}
for (const [page, type] of [["commitmentManagement","commitment"], ["installmentManagement","installment"], ["transactions","transaction"], ["backupSettings","settings"]]) {
  const header = document.querySelector(`#${page} header`);
  if (!header) continue;
  const button = document.createElement("button"); button.className = "quiet"; button.textContent = "رویدادهای این بخش";
  button.addEventListener("click", () => openAuditSection(type)); header.append(button);
}

document.querySelectorAll("[data-action-period]").forEach(button => button.addEventListener("click", () => {
  dashboardActionPeriod = button.dataset.actionPeriod;
  dashboardExpanded = false;
  renderDashboardActions();
}));
document.getElementById("dashboardShowAll").addEventListener("click", () => {
  dashboardExpanded = !dashboardExpanded;
  renderDashboardActions();
});
document.getElementById("dashboardMonthDetails").addEventListener("click", () => {
  document.getElementById("installmentMonth").value = document.getElementById("dashboardMonth").value;
  ["installmentStatus", "installmentCommitment", "installmentSearch"].forEach(id => document.getElementById(id).value = "");
  document.querySelector('.nav-link[data-page="installmentManagement"]').click();
});
document.getElementById("dashboard").addEventListener("click", event => {
  const button = event.target.closest(".dashboard-detail");
  if (button) openCommitmentDetails(Number(button.dataset.id)).catch(error => alert(error.message));
});


const sidebarDateFormatter = new Intl.DateTimeFormat("fa-IR-u-ca-persian", {timeZone:"Asia/Tehran",weekday:"long",year:"numeric",month:"long",day:"numeric"});
function updateSidebarDate() {
  const parts=Object.fromEntries(sidebarDateFormatter.formatToParts(new Date()).map(part=>[part.type,part.value]));
  document.getElementById("currentDate").textContent=`${parts.weekday}، ${parts.day} ${parts.month} ${parts.year}`;
}
updateSidebarDate();
setInterval(updateSidebarDate, 60000);
document.addEventListener("visibilitychange", () => { if (!document.hidden) updateSidebarDate(); });
document.addEventListener("keydown", event => {
  if (event.key === "Escape" && event.target.matches(".card-hint button")) event.target.blur();
});
