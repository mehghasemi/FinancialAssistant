let financialReportRequest = 0;
let transactionEditId = null;
let assetEditId = null;
let assetItems = [];
const reportTypeNames = {income:"درآمد", expense:"هزینه", installment:"قسط", commitment:"تعهد (تجمیع)"};
const financialStatusNames = {...statusLabel, paid:"انجام‌شده / تسویه", unpaid:"در انتظار / پرداخت‌نشده", cancelled:"لغوشده"};
const moneyDisplay = value => currency(value);
const reportFields = {reportYear:"year", reportStart:"start_date", reportEnd:"end_date", reportType:"record_type", reportCategory:"category", reportStatus:"status", reportParty:"counterparty", reportSearch:"search", reportMin:"min_amount", reportMax:"max_amount"};

function reportQuery() {
  const params = new URLSearchParams();
  const month = document.getElementById("transactionMonth").value;
  if (month) {
    const year = latinDigits(document.getElementById("reportYear").value.trim());
    if (!/^\d{4}$/.test(year)) throw new Error("برای انتخاب ماه، سال شمسی را هم وارد کنید.");
    params.set("month", `${year}-${month}`);
  }
  for (const [id, key] of Object.entries(reportFields)) {
    const input = document.getElementById(id), value = input.value.trim();
    if (!input.checkValidity()) throw new Error("مبلغ فیلتر معتبر نیست.");
    if (value) params.set(key, id === "reportYear" ? latinDigits(value) : input.hasAttribute("data-amount") ? amountNumber(value) : value);
  }
  return params;
}
async function loadFinancialReport() {
  const request = ++financialReportRequest;
  try {
    const data = await api(`/financial-report?${reportQuery()}`);
    if (request !== financialReportRequest) return;
    setMessage("financeMessage", "");
    const s = data.summary;
    const periodLabel = document.getElementById("transactionMonth").value ? "ماه" : "بازه";
    const cards = [["مجموع درآمد",s.income,s.income_count],["تعهدات برنامه‌ریزی‌شده",s.installment_total,`${persianDigits(s.installment_count)} قسط از ${persianDigits(s.commitment_count)} تعهد`],["سایر هزینه‌ها",s.expense,s.expense_count],[`مجموع هزینه‌ها و تعهدات ${periodLabel}`,s.total_expenses],[`ماندهٔ ${periodLabel}`,s.monthly_balance],["ماندهٔ پرداخت اقساط",s.remaining_installments]];
    document.getElementById("financeSummary").innerHTML = cards.map(([label,value,count]) => `<div><span>${label}</span><strong>${moneyDisplay(value)}</strong>${count === undefined ? "" : `<small>${typeof count === "string" ? count : `${persianDigits(count)} مورد`}</small>`}</div>`).join("");
    renderRows("transactionRows", data.items.filter(item => item.record_type !== "commitment" || document.getElementById("reportType").value === "commitment").map(item => `<tr class="${item.record_type === "commitment" ? "aggregate-row" : ""}"><td>${item.date}</td><td>${reportTypeNames[item.record_type]}</td><td>${escapeHtml(item.title)}</td><td>${escapeHtml(item.category)}</td><td>${moneyDisplay(item.amount)}</td><td>${financialStatusNames[item.status]}</td><td>${escapeHtml(item.counterparty)}</td><td>${item.installment_count ? `${item.installment_number ? persianDigits(item.installment_number) + " / " : ""}${persianDigits(item.installment_count)}` : "—"}</td><td>${escapeHtml(item.note)}</td><td class="row-actions">${["income","expense"].includes(item.record_type) ? `<button class="quiet edit-transaction" data-id="${item.id}">ویرایش</button><button class="quiet delete-transaction" data-id="${item.id}">حذف</button>` : `<button class="quiet report-details" data-id="${item.commitment_id}">اقساط و پرداخت</button>`}</td></tr>`),10);
    document.getElementById("financeFooter").innerHTML = `<tr><th scope="row">جمع همین فیلتر</th><td colspan="9"><div class="report-footer">${cards.slice(0,6).map(([label,value])=>`<span>${label}: <b>${currency(value)}</b></span>`).join("")}</div></td></tr>`;
  } catch (error) {
    if (request !== financialReportRequest) return;
    setMessage("financeMessage", error.message, true);
    document.getElementById("financeSummary").innerHTML = "";
    document.getElementById("financeFooter").innerHTML = "";
    renderRows("transactionRows", [],10);
  }
}
function setTransactionFormOpen(open) {
  document.getElementById("transactionEntry").hidden = !open;
  const toggle = document.getElementById("toggleTransactionEntry");
  toggle.setAttribute("aria-expanded", String(open));
  toggle.textContent = open ? "بستن فرم" : "＋ ثبت درآمد / هزینه";
}
document.getElementById("toggleTransactionEntry").addEventListener("click", () => {
  const open = document.getElementById("transactionEntry").hidden;
  setTransactionFormOpen(open);
  if (open) document.getElementById("transactionTitle").focus();
});
document.querySelectorAll('.primary[data-page="transactions"]').forEach(button=>button.addEventListener("click",()=>setTransactionFormOpen(true)));
function resetTransaction() {
  transactionEditId = null;
  document.getElementById("transactionForm").reset();
  document.getElementById("transactionDate").value = todayJalali();
  document.getElementById("transactionFormTitle").textContent = "تراکنش جدید";
  document.getElementById("cancelTransactionEdit").hidden = true;
  updateCategories(); Money.scan(); setTransactionFormOpen(false);
}
document.getElementById("cancelTransactionEdit").addEventListener("click", resetTransaction);
document.getElementById("transactionForm").addEventListener("submit", async event => {
  event.preventDefault();
  const button = event.target.querySelector('[type="submit"]'); button.disabled = true;
  try {
    const payload = {title:document.getElementById("transactionTitle").value.trim(), transaction_type:document.getElementById("transactionType").value, amount:amountNumber(document.getElementById("transactionAmount").value), occurred_on:document.getElementById("transactionDate").value, category_id:Number(document.getElementById("transactionCategory").value)||null, account_id:Number(document.getElementById("transactionAccount").value)||null, counterparty:document.getElementById("transactionParty").value, status:document.getElementById("transactionStatus").value, note:document.getElementById("transactionNote").value};
    if (!payload.title) throw new Error("عنوان ضروری است.");
    await api(`/transactions${transactionEditId ? "/"+transactionEditId : ""}`, {method:transactionEditId ? "PATCH":"POST",body:JSON.stringify(payload)});
    resetTransaction(); setMessage("transactionMessage","تراکنش ذخیره شد."); await refreshAll();
  } catch (error) { setMessage("transactionMessage",error.message,true); }
  finally { button.disabled = false; }
});
document.getElementById("transactionRows").addEventListener("click",async event=>{
  const edit = event.target.closest(".edit-transaction"), remove = event.target.closest(".delete-transaction"), details=event.target.closest(".report-details");
  try {
    if (details) { await openCommitmentDetails(Number(details.dataset.id)); return; }
    if (remove && confirm("این درآمد یا هزینه حذف شود؟ تغییر در رویدادنگاری ثبت می‌شود.")) {
      await api(`/transactions/${remove.dataset.id}?confirm=true`,{method:"DELETE"});
      if (transactionEditId === Number(remove.dataset.id)) resetTransaction();
      await refreshAll(); return;
    }
    if (!edit) return;
    const items = await api("/transactions");
    const item = items.find(row=>row.id===Number(edit.dataset.id));
    if (!item) throw new Error("تراکنش پیدا نشد؛ گزارش را تازه کنید.");
    transactionEditId = item.id;
    setTransactionFormOpen(true);
    document.getElementById("transactionType").value = item.transaction_type; updateCategories();
    for (const [id,key] of Object.entries({transactionTitle:"title",transactionAmount:"amount",transactionDate:"occurred_on",transactionCategory:"category_id",transactionAccount:"account_id",transactionNote:"note",transactionParty:"counterparty",transactionStatus:"status"})) document.getElementById(id).value=item[key]??"";
    document.getElementById("transactionFormTitle").textContent="ویرایش تراکنش";
    document.getElementById("cancelTransactionEdit").hidden=false; Money.scan();
    document.getElementById("transactionForm").scrollIntoView({block:"start"});
  } catch(error) { setMessage("financeMessage",error.message,true); }
});
let reportTimer;
document.getElementById("financeFilters").addEventListener("input",event=>{
  if (event.target.id === "transactionMonth") return;
  if (["reportStart","reportEnd"].includes(event.target.id)) { document.getElementById("transactionMonth").value=""; document.getElementById("reportYear").value=""; }
  clearTimeout(reportTimer); reportTimer=setTimeout(loadFinancialReport,250);
});
document.getElementById("transactionMonth").addEventListener("change",()=>{
  ["reportStart","reportEnd"].forEach(id=>document.getElementById(id).value="");
  if (!document.getElementById("reportYear").value) document.getElementById("reportYear").value=persianDigits(currentJalaliParts().year);
  loadFinancialReport();
});
document.getElementById("resetReport").addEventListener("click",()=>{
  Object.keys(reportFields).forEach(id=>document.getElementById(id).value="");
  document.getElementById("transactionMonth").value=""; Money.scan(); loadFinancialReport();
});

async function loadAssets() {
  try {
    assetItems=await api("/assets");
    renderRows("assetRows",assetItems.map(item=>`<tr><td>${escapeHtml(item.title)}</td><td>${escapeHtml(item.kind)}</td><td>${item.registered_on}</td><td>${moneyDisplay(item.initial_value)}</td><td>${moneyDisplay(item.current_value)}</td><td>${moneyDisplay(item.current_value-item.initial_value)}</td><td>${escapeHtml(item.note)}</td><td><button class="quiet edit-asset" data-id="${item.id}">ویرایش / تغییر ارزش</button><button class="quiet history-asset" data-id="${item.id}">تاریخچهٔ ارزش</button></td></tr>`),8);
    renderTotals("assetRows",["جمع دارایی‌ها","","",currency(sumField(assetItems,"initial_value")),currency(sumField(assetItems,"current_value")),currency(sumField(assetItems,"current_value")-sumField(assetItems,"initial_value")),"",""]);
  } catch(error) { setMessage("assetMessage",error.message,true); }
}
function resetAsset() {
  assetEditId=null; document.getElementById("assetForm").reset();
  document.getElementById("assetForm").elements.registered_on.value=todayJalali(); Money.scan();
}
document.getElementById("cancelAssetEdit").addEventListener("click",resetAsset);
document.getElementById("closeAssetHistory").addEventListener("click",()=>document.getElementById("assetHistory").hidden=true);
document.getElementById("assetForm").addEventListener("submit",async event=>{
  event.preventDefault(); const form=event.target, button=form.querySelector('[type="submit"]'); button.disabled=true;
  try {
    const payload=Object.fromEntries(new FormData(form));
    payload.initial_value=amountNumber(payload.initial_value); payload.current_value=amountNumber(payload.current_value);
    await api(`/assets${assetEditId ? "/"+assetEditId : ""}`,{method:assetEditId?"PATCH":"POST",body:JSON.stringify(payload)});
    resetAsset(); document.getElementById("assetHistory").hidden=true; setMessage("assetMessage","دارایی ذخیره شد."); await loadAssets();
  } catch(error) { setMessage("assetMessage",error.message,true); }
  finally { button.disabled=false; }
});
document.getElementById("assetRows").addEventListener("click",async event=>{
  const edit=event.target.closest(".edit-asset"), history=event.target.closest(".history-asset");
  if (edit) {
    const item=assetItems.find(row=>row.id===Number(edit.dataset.id)); if(!item) return;
    assetEditId=item.id; const form=document.getElementById("assetForm");
    for(const key of ["title","kind","registered_on","initial_value","current_value","note"]) form.elements[key].value=item[key];
    form.elements.change_note.value=""; Money.scan(); form.scrollIntoView({block:"start"});
  }
  if (history) {
    try {
      const rows=await api(`/assets/${history.dataset.id}/history`);
      document.getElementById("assetHistoryTitle").textContent=`تاریخچهٔ ارزش: ${assetItems.find(item=>item.id===Number(history.dataset.id))?.title||""}`;
      renderRows("assetHistoryRows",rows.map(row=>`<tr><td>${row.changed_at}</td><td>${row.old_value===null ? "ثبت اولیه" : moneyDisplay(row.old_value)}</td><td>${moneyDisplay(row.new_value)}</td><td>${escapeHtml(row.note)}</td></tr>`),4);
      document.getElementById("assetHistory").hidden=false; document.getElementById("assetHistory").scrollIntoView({block:"nearest"});
    } catch(error) {setMessage("assetMessage",error.message,true);}
  }
});
resetAsset();

populateMonthSelectors(); setJalaliDateDefaults(); loadReferenceData().then(async () => { await refreshAll(); await loadReleases(); }).catch(error => document.body.insertAdjacentHTML("afterbegin", `<p class="fatal" role="alert">${escapeHtml(error.message)}</p>`));

let dataStatusRequest = 0;
async function loadDataStatus() {
  const request = ++dataStatusRequest;
  try {
    const data = await api("/data-status");
    if (request !== dataStatusRequest) return;
    document.getElementById("applicationVersion").textContent = `نسخهٔ ${persianDigits(data.version)}`;
    const time = document.getElementById("lastDataChange");
    time.textContent = data.last_changed_label || "هنوز تغییری ثبت نشده";
    if (data.last_changed_at) time.setAttribute("datetime",data.last_changed_at); else time.removeAttribute("datetime");
  } catch { if (request === dataStatusRequest) document.getElementById("lastDataChange").textContent = "زمان تغییر در دسترس نیست"; }
}
loadDataStatus();
document.addEventListener("visibilitychange",()=>{ if (!document.hidden) loadDataStatus(); });
