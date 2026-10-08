let cashDetailView = "actual";
let cashDetailMonth = "";
let cashDetailData = null;

function renderDashboardCash(data) {
  const cash = data.cash;
  document.getElementById("dashboardArrearsPaid").textContent=currency(cash.arrears_paid);
  document.getElementById("dashboardCash").textContent=cash.available === null ? (cash.account_mode ? "تکمیل موجودی حساب‌ها" : "ثبت موجودی اولیه") : currency(cash.available);
  document.getElementById("dashboardCashCaption").textContent=`موجودی نقدی تا ${cash.as_of} − ماندهٔ اقساط و هزینه‌های ${data.month_label}`;
  document.getElementById("cashAnnualTitle").textContent=`مقایسهٔ درآمد و هزینهٔ واقعی ماه‌های سال ${persianDigits(cash.year)}`;
  document.querySelectorAll("#dashboard .dashboard-stats article").forEach(card=>{card.title=card.querySelector("p")?.textContent || "";});
  renderCashCharts(cash);
  const maximum=Math.max(1,...cash.annual.flatMap(row=>[row.income||0,row.paid||0]));
  document.getElementById("cashAnnualBars").innerHTML=cash.annual.map((row,index)=>{
    const label=row.future ? `${row.label}؛ هنوز نرسیده` : `${row.label}؛ دریافت ${currency(row.income)}؛ پرداخت ${currency(row.paid)}`;
    return `<button type="button" class="cash-month ${row.future ? "future-month" : ""}" data-cash-month="${row.month}" title="${label}" aria-label="${label}"><span class="bar-pair" aria-hidden="true"><i class="income-bar" style="height:${row.income ? Math.max(1,row.income/maximum*100) : 0}%"></i><i class="expense-bar" style="height:${row.paid ? Math.max(1,row.paid/maximum*100) : 0}%"></i></span><span>${jalaliMonths[index]}</span></button>`;
  }).join("");
  document.getElementById("cashAnnualTable").innerHTML=`<div class="table-wrap"><table><thead><tr><th>ماه</th><th>دریافت واقعی</th><th>پرداخت واقعی</th></tr></thead><tbody>${cash.annual.map(row=>`<tr><td>${row.label}</td><td>${row.future ? "—" : currency(row.income)}</td><td>${row.future ? "—" : currency(row.paid)}</td></tr>`).join("")}</tbody></table></div>`;
}

function openPlannedReport(kind="") {
  Object.keys(reportFields).forEach(id=>document.getElementById(id).value="");
  const [year,month]=document.getElementById("dashboardMonth").value.split("-");
  document.getElementById("transactionMonth").value=month;
  document.getElementById("reportYear").value=persianDigits(year);
  document.getElementById("reportType").value=kind;
  document.querySelector('.nav-link[data-page="transactions"]').click();
}

async function showCashDetails(view,month=document.getElementById("dashboardMonth").value) {
  cashDetailView=view; cashDetailMonth=month;
  const data=await api(`/dashboard?month=${month}`);
  cashDetailData=data;
  const ledger=["month","payments","arrears","current","advance"].includes(view);
  document.getElementById("cashLedgerFilters").hidden=!ledger;
  if(ledger) setupCashFilters(data.cash.all_items,view,month);
  renderCashDetails(data);
}

function renderCashDetails(data) {
  if (typeof refreshPeriodButtons === "function") refreshPeriodButtons();
  const view=cashDetailView, month=cashDetailMonth, cash=data.cash;
  const ledger=["month","payments","arrears","current","advance"].includes(view);
  document.querySelectorAll(".page").forEach(page=>page.classList.toggle("active",page.id==="cashActivity"));
  updateNavigation("dashboard");
  const actual=view==="actual", arrears=view==="arrears", review=view==="dates";
  document.getElementById("cashDateReviewFilters").hidden=!review;
  const dateFilter=document.getElementById("cashDateReviewFilter").value;
  const reviewRows=cash.date_review_items.filter(row=>dateFilter==="assumed" ? row.assumed : dateFilter==="different" ? row.date!==row.due_date : dateFilter==="month" ? cashMonthOf(row.date)!==cashMonthOf(row.due_date) : true);
  const rows=ledger ? filterCashRows(cash.all_items,readCashFilters()) : review ? reviewRows : actual ? cash.cash_items : arrears ? cash.arrears_items : ["current","advance"].includes(view) ? cash.period_items.filter(row=>row.kind!=="income" && (view==="advance" ? cashMonthOf(row.due_date)>month : cashMonthOf(row.due_date)===month)) : cash.period_items;
  document.getElementById("cashActivityTitle").textContent=review ? "بررسی تاریخ دریافت و پرداخت" : actual ? "ماندهٔ قابل پس‌انداز ماه" : "گردش دریافت و پرداخت";
  document.getElementById("cashActivityCaption").textContent=review ? "تمام تاریخ‌ها؛ شامل پرداخت‌های ثبت‌شده با تاریخ آینده" : actual ? `نقد موجود تا ${cash.as_of} پس از کنارگذاشتن تعهدات ${data.month_label}؛ ممکن است شامل پس‌انداز قبلی باشد. درآمد وصول‌نشده و معوقات پرداخت‌نشده لحاظ نمی‌شوند.` : `بر اساس تاریخ واقعی دریافت/پرداخت، تا ${cash.as_of}؛ مستقل از ماه سررسید. جمع‌ها مربوط به فیلترهای زیر هستند.`;
  document.getElementById("cashOpeningForm").hidden=!actual || cash.account_mode;
  document.getElementById("cashAccountsLink").hidden=!actual;
  document.getElementById("cashOpeningDate").value=cash.opening?.as_of_date || todayJalali();
  document.getElementById("cashOpeningAmount").value=cash.opening?.amount ?? "";
  document.getElementById("cashReservePanel").hidden=!actual;
  if(actual) {
    renderRows("cashReserveRows",cash.reserved_items.map(row=>`<tr><td>${row.due_date}</td><td>${escapeHtml(row.title)}</td><td>${row.kind==="installment" ? "قسط" : "هزینه"}</td><td>${currency(row.remaining)}</td><td><button class="quiet" type="button" ${row.source==="payment" ? `data-cash-commitment="${row.commitment_id}"` : `data-cash-transaction="${row.id}"`}>بررسی و ویرایش</button></td></tr>`),5);
    document.getElementById("cashReserveTotal").textContent=currency(cash.reserved);
  }
  Money.scan();
  const incoming=rows.reduce((sum,row)=>sum+(row.kind==="income" ? row.amount : 0),0);
  const outgoing=rows.reduce((sum,row)=>sum+(row.kind!=="income" ? row.amount : 0),0);
  const cards=actual ? [["موجودی نقدی فعلی",cash.cash_balance],["ماندهٔ اقساط ماه",cash.reserved_installments],["هزینه‌های پرداخت‌نشدهٔ ماه",cash.reserved_expenses],["ماندهٔ قابل پس‌انداز",cash.available]] : [["تعداد",persianDigits(rows.length)],["دریافت",incoming],["پرداخت",outgoing],["خالص گردش",incoming-outgoing]];
  document.getElementById("cashActivitySummary").innerHTML=cards.map(([label,value])=>`<div><span>${label}</span><strong>${value==null ? "موجودی اولیه ثبت نشده" : label==="تعداد" ? value : currency(value)}</strong></div>`).join("");
  const assumed=rows.filter(row=>row.assumed).length;
  document.getElementById("cashDateWarning").textContent=assumed ? `تاریخ ${persianDigits(assumed)} مورد نیازمند تأیید است؛ تاریخ واقعی را در ویرایش تراکنش یا ریز پرداخت‌های قسط بررسی و ذخیره کنید.` : "";
  if(actual && cash.unassigned_count) document.getElementById("cashDateWarning").textContent+=` ${persianDigits(cash.unassigned_count)} دریافت/پرداخت بدون حساب ثبت شده؛ برای تطبیق موجودی تک‌تک حساب‌ها، حساب آن‌ها را مشخص کنید.`;
  renderRows("cashActivityRows",rows.map(row=>`<tr class="${row.kind==="income" ? "payment-paid" : "payment-unpaid"}"><td>${row.date}${row.assumed ? " (نیازمند بررسی)" : ""}</td><td>${row.due_date}</td><td>${escapeHtml(row.title)}</td><td>${row.kind==="income" ? "درآمد" : row.kind==="installment" ? "پرداخت قسط" : "هزینه"}</td><td>${escapeHtml(row.account_name)}</td><td>${row.kind==="income" ? currency(row.amount) : "—"}</td><td>${row.kind!=="income" ? currency(row.amount) : "—"}</td><td><button type="button" class="quiet" ${row.source==="payment" ? `data-cash-commitment="${row.commitment_id}"` : `data-cash-transaction="${row.id}"`}>${row.source==="payment" ? "اقساط و پرداخت‌ها" : "ویرایش تراکنش"}</button></td></tr>`),8);
  document.getElementById("cashActivityFooter").innerHTML=`<tr><th colspan="5">جمع همین فهرست</th><td>${currency(incoming)}</td><td>${currency(outgoing)}</td><td></td></tr>`;
}

async function dashboardCardAction(view) {
  if(view==="actual" || view==="arrears") return showCashDetails(view);
  if(view==="installments") { document.getElementById("dashboardMonthDetails").click(); return; }
  openPlannedReport(view==="expected" ? "" : view);
}
document.getElementById("dashboard").addEventListener("click",event=>{
  const card=event.target.closest("[data-dashboard-view]"), month=event.target.closest("[data-cash-month]");
  if(card) dashboardCardAction(card.dataset.dashboardView).catch(error=>alert(error.message));
  if(month) showCashDetails("month",month.dataset.cashMonth).catch(error=>alert(error.message));
});
document.querySelectorAll("[data-dashboard-view]").forEach(card=>card.addEventListener("keydown",event=>{
  if(event.key==="Enter" || event.key===" ") { event.preventDefault(); card.click(); }
}));
document.getElementById("cashActivity").addEventListener("click",async event=>{
  const commitment=event.target.closest("[data-cash-commitment]"), transaction=event.target.closest("[data-cash-transaction]");
  try {
    if(commitment) await openCommitmentDetails(Number(commitment.dataset.cashCommitment));
    if(transaction) {
      document.querySelector('.nav-link[data-page="transactions"]').click();
      await editTransactionById(Number(transaction.dataset.cashTransaction));
    }
  } catch(error) { setMessage("cashActivityMessage",error.message,true); }
});
document.getElementById("cashOpeningForm").addEventListener("submit",async event=>{
  event.preventDefault();
  if(!confirm("مجموع موجودی ابتدای روز ثبت شود؟ موجودی نقدی و ماندهٔ قابل پس‌انداز از این تاریخ دوباره محاسبه می‌شوند.")) return;
  const button=event.target.querySelector('button[type="submit"]'); button.disabled=true;
  try {
    await api("/cash-opening",{method:"PUT",body:JSON.stringify({amount:amountNumber(document.getElementById("cashOpeningAmount").value),as_of_date:document.getElementById("cashOpeningDate").value})});
    await loadDashboard(); await showCashDetails("actual",cashDetailMonth);
    setMessage("cashActivityMessage","موجودی اولیه ذخیره شد.");
  } catch(error) { setMessage("cashActivityMessage",error.message,true); }
  finally { button.disabled=false; }
});

function cashMonthOf(value) { return value.replace(/[۰-۹]/g,d=>"۰۱۲۳۴۵۶۷۸۹".indexOf(d)).slice(0,7).replace("/","-"); }
function renderCashCharts(cash) {
  const labels={current:"پرداخت بابت همین ماه",arrears:"پرداخت معوقات",advance:"پیش‌پرداخت ماه‌های آینده"};
  const total=Math.max(1,cash.paid);
  document.getElementById("cashComposition").innerHTML=Object.entries(cash.components).map(([key,amount])=>`<button class="composition-row" data-cash-component="${key}"><span>${labels[key]}</span><strong>${currency(amount)}</strong><i style="width:${amount/total*100}%"></i></button>`).join("");
  const known=cash.annual.filter(row=>row.balance!==null), max=Math.max(1,...known.map(row=>Math.abs(row.balance)));
  document.getElementById("cashBalanceTrend").innerHTML=known.length ? `<div class="balance-trend">${cash.annual.map((row,index)=>`<div title="${row.label}: ${row.balance===null ? "بدون مقدار" : currency(row.balance)}"><span class="trend-track"><i class="${row.balance<0 ? "negative" : ""}" style="height:${row.balance===null ? 0 : Math.max(1,Math.abs(row.balance)/max*100)}%"></i></span><small>${persianDigits(index+1)}</small></div>`).join("")}</div><p class="help-text">سبز: موجودی مثبت؛ قرمز: کسری موجودی</p><details class="help"><summary>اعداد روند موجودی</summary>${known.map(row=>`<p>${row.label}: ${currency(row.balance)}</p>`).join("")}</details>` : '<p class="help-text">برای مشاهدهٔ روند، موجودی اولیه را ثبت کنید.</p>';
}
document.getElementById("cashComposition").addEventListener("click",event=>{
  const button=event.target.closest("[data-cash-component]");
  if(button) showCashDetails(button.dataset.cashComponent).catch(error=>alert(error.message));
});

document.getElementById("reviewPaymentDates").addEventListener("click",()=>showCashDetails("dates").catch(error=>alert(error.message)));
document.getElementById("cashDateReviewFilter").addEventListener("change",()=>showCashDetails("dates").catch(error=>alert(error.message)));

function cashDateKey(value) {
  return value.replace(/[۰-۹]/g,d=>"۰۱۲۳۴۵۶۷۸۹".indexOf(d)).replace(/[٠-٩]/g,d=>"٠١٢٣٤٥٦٧٨٩".indexOf(d)).replaceAll("/","-").trim();
}

function filterCashRows(rows, filters) {
  return rows.filter(row=>{
    const date=cashDateKey(row.date), due=cashDateKey(row.due_date);
    const relation=due.slice(0,7)<date.slice(0,7) ? "arrears" : due.slice(0,7)>date.slice(0,7) ? "advance" : "current";
    return (!filters.year || date.slice(0,4)===filters.year)
      && (!filters.month || date.slice(5,7)===filters.month)
      && (!filters.from || date>=filters.from) && (!filters.to || date<=filters.to)
      && (!filters.kind || (filters.kind==="outgoing" ? row.kind!=="income" : row.kind===filters.kind))
      && (!filters.account || String(row.account_id ?? "none")===filters.account)
      && (!filters.relation || relation===filters.relation)
      && (!filters.assumed || (filters.assumed==="yes" ? !!row.assumed : !row.assumed))
      && (!filters.search || (row.title+" "+row.account_name).toLocaleLowerCase().includes(filters.search.toLocaleLowerCase()))
      && (filters.min===null || row.amount>=filters.min) && (filters.max===null || row.amount<=filters.max);
  });
}

function readCashFilters() {
  const value=id=>document.getElementById(id).value;
  return {year:value("cashFilterYear"),month:value("cashFilterMonth"),from:cashDateKey(value("cashFilterFrom")),to:cashDateKey(value("cashFilterTo")),
    kind:value("cashFilterKind"),account:value("cashFilterAccount"),relation:value("cashFilterRelation"),assumed:value("cashFilterAssumed"),search:value("cashFilterSearch").trim(),
    min:value("cashFilterMin").trim() ? amountNumber(value("cashFilterMin")) : null,max:value("cashFilterMax").trim() ? amountNumber(value("cashFilterMax")) : null};
}

function setupCashFilters(rows,view,month) {
  const years=[...new Set([month.slice(0,4),...rows.map(row=>cashDateKey(row.date).slice(0,4))])].sort().reverse();
  document.getElementById("cashFilterYear").innerHTML='<option value="">همهٔ سال‌ها</option>'+years.map(year=>`<option value="${year}">${persianDigits(year)}</option>`).join("");
  document.getElementById("cashFilterMonth").innerHTML='<option value="">همهٔ ماه‌ها</option>'+jalaliMonths.map((label,index)=>`<option value="${String(index+1).padStart(2,"0")}">${label}</option>`).join("");
  const accounts=new Map(rows.filter(row=>row.account_id!==null).map(row=>[row.account_id,row.account_name]));
  document.getElementById("cashFilterAccount").innerHTML='<option value="">همهٔ حساب‌ها</option><option value="none">بدون حساب</option>'+[...accounts].map(([id,name])=>`<option value="${id}">${escapeHtml(name)}</option>`).join("");
  document.getElementById("cashLedgerFilters").reset();
  document.getElementById("cashFilterYear").value=month.slice(0,4);
  document.getElementById("cashFilterMonth").value=month.slice(5,7);
  document.getElementById("cashFilterKind").value=view==="month" ? "" : "outgoing";
  document.getElementById("cashFilterRelation").value=["arrears","current","advance"].includes(view) ? view : "";
}

document.getElementById("openCashLedger").addEventListener("click",()=>showCashDetails("payments").catch(error=>alert(error.message)));
document.getElementById("cashLedgerFilters").addEventListener("submit",event=>event.preventDefault());
for(const eventName of ["input","change"]) document.getElementById("cashLedgerFilters").addEventListener(eventName,()=>renderCashDetails(cashDetailData));
document.getElementById("clearCashFilters").addEventListener("click",()=>{document.getElementById("cashLedgerFilters").reset();renderCashDetails(cashDetailData);});
