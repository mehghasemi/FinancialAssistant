let cashDetailView = "actual";
let cashDetailMonth = "";

function renderDashboardCash(data) {
  const cash = data.cash;
  document.getElementById("dashboardArrearsPaid").textContent=currency(cash.arrears_paid);
  document.getElementById("dashboardCash").textContent=cash.available === null ? (cash.account_mode ? "تکمیل موجودی حساب‌ها" : "ثبت موجودی اولیه") : currency(cash.available);
  document.getElementById("dashboardCashCaption").textContent=`تا ${cash.as_of}؛ بر اساس موجودی اولیه و دریافت/پرداخت ثبت‌شده، مستقل از ماه انتخابی`;
  document.getElementById("cashAnnualTitle").textContent=`مقایسهٔ درآمد و هزینهٔ واقعی ماه‌های سال ${persianDigits(cash.year)}`;
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
  const data=await api(`/dashboard?month=${month}`), cash=data.cash;
  document.querySelectorAll(".page").forEach(page=>page.classList.toggle("active",page.id==="cashActivity"));
  updateNavigation("dashboard");
  const actual=view==="actual", arrears=view==="arrears";
  const rows=actual ? cash.cash_items : arrears ? cash.arrears_items : ["current","advance"].includes(view) ? cash.period_items.filter(row=>row.kind!=="income" && (view==="advance" ? cashMonthOf(row.due_date)>month : cashMonthOf(row.due_date)===month)) : cash.period_items;
  document.getElementById("cashActivityTitle").textContent=actual ? "موجودی واقعی قابل‌خرج" : arrears ? "پرداخت بابت معوقات گذشته" : view==="current" ? "پرداخت بابت همین ماه" : view==="advance" ? "پیش‌پرداخت ماه‌های آینده" : "دریافت و پرداخت واقعی ماه";
  document.getElementById("cashActivityCaption").textContent=actual ? `تا ${cash.as_of}؛ مجموع وجه نقد و حساب‌ها بر اساس اطلاعات ثبت‌شده` : data.month_label;
  document.getElementById("cashOpeningForm").hidden=!actual || cash.account_mode;
  document.getElementById("cashAccountsLink").hidden=!actual;
  document.getElementById("cashOpeningDate").value=cash.opening?.as_of_date || todayJalali();
  document.getElementById("cashOpeningAmount").value=cash.opening?.amount ?? "";
  Money.scan();
  const incoming=rows.reduce((sum,row)=>sum+(row.kind==="income" ? row.amount : 0),0);
  const outgoing=rows.reduce((sum,row)=>sum+(row.kind!=="income" ? row.amount : 0),0);
  const cards=actual ? [["موجودی اولیه",cash.opening?.amount],["دریافت از تاریخ مبنا",incoming],["پرداخت از تاریخ مبنا",outgoing],["موجودی قابل‌خرج",cash.available]] : [["دریافت",incoming],["پرداخت",outgoing],["خالص این فهرست",incoming-outgoing]];
  document.getElementById("cashActivitySummary").innerHTML=cards.map(([label,value])=>`<div><span>${label}</span><strong>${value==null ? "موجودی اولیه ثبت نشده" : currency(value)}</strong></div>`).join("");
  const assumed=rows.filter(row=>row.assumed).length;
  document.getElementById("cashDateWarning").textContent=assumed ? `تاریخ واقعی ${persianDigits(assumed)} تراکنش از تاریخ قبلی فرض شده است؛ در صورت تفاوت، از «ویرایش تراکنش» اصلاح کنید.` : "";
  if(actual && cash.unassigned_count) document.getElementById("cashDateWarning").textContent+=` ${persianDigits(cash.unassigned_count)} دریافت/پرداخت بدون حساب ثبت شده؛ برای تطبیق موجودی تک‌تک حساب‌ها، حساب آن‌ها را مشخص کنید.`;
  renderRows("cashActivityRows",rows.map(row=>`<tr class="${row.kind==="income" ? "payment-paid" : "payment-unpaid"}"><td>${row.date}${row.assumed ? " (نیازمند بررسی)" : ""}</td><td>${row.due_date}</td><td>${escapeHtml(row.title)}</td><td>${row.kind==="income" ? "درآمد" : row.kind==="installment" ? "پرداخت قسط" : "هزینه"}</td><td>${row.kind==="income" ? currency(row.amount) : "—"}</td><td>${row.kind!=="income" ? currency(row.amount) : "—"}</td><td><button type="button" class="quiet" ${row.source==="payment" ? `data-cash-commitment="${row.commitment_id}"` : `data-cash-transaction="${row.id}"`}>${row.source==="payment" ? "اقساط و پرداخت‌ها" : "ویرایش تراکنش"}</button></td></tr>`),7);
  document.getElementById("cashActivityFooter").innerHTML=`<tr><th colspan="4">جمع همین فهرست</th><td>${currency(incoming)}</td><td>${currency(outgoing)}</td><td></td></tr>`;
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
document.getElementById("cashActivityRows").addEventListener("click",async event=>{
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
  if(!confirm("مجموع موجودی ابتدای روز ثبت شود؟ موجودی قابل‌خرج از این تاریخ دوباره محاسبه می‌شود.")) return;
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
  document.getElementById("cashBalanceTrend").innerHTML=known.length ? `<div class="balance-trend">${cash.annual.map((row,index)=>`<div title="${row.balance===null ? "بدون مقدار" : currency(row.balance)}"><span class="trend-track"><i class="${row.balance<0 ? "negative" : ""}" style="height:${row.balance===null ? 0 : Math.max(1,Math.abs(row.balance)/max*100)}%"></i></span><small>${jalaliMonths[index]}</small></div>`).join("")}</div><p class="help-text">سبز: موجودی مثبت؛ قرمز: کسری موجودی</p><details class="help"><summary>اعداد روند موجودی</summary>${known.map(row=>`<p>${row.label}: ${currency(row.balance)}</p>`).join("")}</details>` : '<p class="help-text">برای مشاهدهٔ روند، موجودی اولیه را ثبت کنید.</p>';
}
document.getElementById("cashComposition").addEventListener("click",event=>{
  const button=event.target.closest("[data-cash-component]");
  if(button) showCashDetails(button.dataset.cashComponent).catch(error=>alert(error.message));
});
