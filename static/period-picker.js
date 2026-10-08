/* Keep API month keys stable; expose one explicit apply/cancel dialog. */
const periodTargets = {
  dashboard: {month:"dashboardMonth"},
  installment: {month:"installmentMonth",all:true},
  budget: {month:"budgetMonth",slash:true},
  report: {month:"transactionMonth",year:"reportYear",all:true},
  cash: {month:"cashFilterMonth",year:"cashFilterYear",all:true}
};
let activePeriod = null;
const periodLatin = value => String(value).replace(/[۰-۹]/g,d=>"۰۱۲۳۴۵۶۷۸۹".indexOf(d)).replaceAll("/","-");

function readPeriod(target) {
  const month=periodLatin(document.getElementById(target.month).value);
  return target.year ? [periodLatin(document.getElementById(target.year).value),month] : month.split("-");
}

function refreshPeriodButtons() {
  document.querySelectorAll("[data-period]").forEach(button=>{
    const [year,month]=readPeriod(periodTargets[button.dataset.period]);
    button.textContent=year ? `${month ? jalaliMonths[Number(month)-1] : "همهٔ ماه‌های"} ${persianDigits(year)} ▾` : month ? `${jalaliMonths[Number(month)-1]}، همهٔ سال‌ها ▾` : "همهٔ دوره‌ها ▾";
  });
}

function setPeriodValue(id,value) {
  const input=document.getElementById(id);
  if(input.tagName==="SELECT" && ![...input.options].some(option=>option.value===value)) input.add(new Option(persianDigits(value),value));
  input.value=value;
}

function applyPeriod(year,month) {
  const target=periodTargets[activePeriod];
  if(target.year) {
    setPeriodValue(target.year,year);
    setPeriodValue(target.month,month);
  } else document.getElementById(target.month).value=year && month ? `${year}${target.slash ? "/" : "-"}${month}` : "";
  document.getElementById("periodDialog").close();
  refreshPeriodButtons();
  // Existing listeners own fetching and clearing incompatible date ranges.
  if(activePeriod==="report") {
    document.getElementById("reportStart").value="";
    document.getElementById("reportEnd").value="";
    loadFinancialReport();
  } else document.getElementById(target.month).dispatchEvent(new Event("change",{bubbles:true}));
}

document.querySelectorAll("[data-period]").forEach(button=>button.addEventListener("click",()=>{
  activePeriod=button.dataset.period;
  document.getElementById("periodYear").setCustomValidity("");
  const target=periodTargets[activePeriod], now=currentJalaliParts();
  const [year,month]=readPeriod(target);
  document.getElementById("periodYear").innerHTML=(target.year ? '<option value="">همهٔ سال‌ها</option>' : '')+Array.from({length:401},(_,i)=>`<option value="${1200+i}">${persianDigits(1200+i)}</option>`).join("");
  document.getElementById("periodMonth").innerHTML=(target.year ? '<option value="">همهٔ ماه‌ها</option>' : '')+jalaliMonths.map((label,i)=>`<option value="${String(i+1).padStart(2,"0")}">${label}</option>`).join("");
  document.getElementById("periodYear").value=year || (target.year ? "" : String(now.year));
  document.getElementById("periodMonth").value=month || (target.year ? "" : String(now.month).padStart(2,"0"));
  document.getElementById("periodAll").hidden=!target.all;
  document.getElementById("periodDialog").showModal();
}));
document.getElementById("periodForm").addEventListener("submit",event=>{
  event.preventDefault();
  const year=document.getElementById("periodYear").value,month=document.getElementById("periodMonth").value;
  if(activePeriod==="report" && month && !year) {
    document.getElementById("periodYear").setCustomValidity("برای انتخاب ماه، سال را هم انتخاب کنید.");
    document.getElementById("periodYear").reportValidity();
    return;
  }
  applyPeriod(year,month);
});
document.getElementById("periodYear").addEventListener("change",event=>event.target.setCustomValidity(""));
document.getElementById("periodToday").addEventListener("click",()=>{
  const now=currentJalaliParts(); applyPeriod(String(now.year),String(now.month).padStart(2,"0"));
});
document.getElementById("periodAll").addEventListener("click",()=>applyPeriod("",""));
document.getElementById("periodCancel").addEventListener("click",()=>document.getElementById("periodDialog").close());
refreshPeriodButtons();
