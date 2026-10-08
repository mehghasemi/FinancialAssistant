let baseData = {banks:[], accounts:[], categories:[]};
const baseValue = id => document.getElementById(id).value;
function resetBaseForm() {
  document.getElementById("baseForm").reset(); document.getElementById("baseId").value="";
  const resource=baseValue("baseResource");
  document.querySelectorAll("[data-base-account]").forEach(field=>field.hidden=resource!=="accounts");
  document.getElementById("baseCategoryField").hidden=resource!=="categories";
  document.getElementById("baseHelp").hidden=resource!=="accounts"; Money.scan();
}
async function loadBaseData() {
  baseData=await api("/base-data");
  document.getElementById("baseBank").innerHTML='<option value="">بدون بانک</option>'+baseData.banks.map(row=>`<option value="${row.id}">${escapeHtml(row.name)}</option>`).join("");
  renderBaseData();
}
function renderBaseData() {
  const resource=baseValue("baseResource"), isAccount=resource==="accounts";
  const headers=isAccount ? ["عنوان","بانک / نوع","شماره حساب","روز مبنا","موجودی اولیه","موجودی محاسبه‌شده","عملیات"] : ["عنوان",...(resource==="categories" ? ["نوع"] : []),"عملیات"];
  document.getElementById("baseHead").innerHTML=`<tr>${headers.map(label=>`<th>${label}</th>`).join("")}</tr>`;
  delete document.getElementById("baseRows").closest("table").dataset.sortColumn;
  renderRows("baseRows",baseData[resource].map(row=>`<tr><td>${escapeHtml(row.name)}</td>${isAccount ? `<td>${row.kind==="cash" ? "نقدی" : escapeHtml(baseData.banks.find(bank=>bank.id===row.bank_id)?.name||"بانکی")}</td><td dir="ltr">${escapeHtml(row.account_number)}</td><td>${row.opening_date||"—"}</td><td>${row.opening_amount==null ? "ثبت نشده" : currency(row.opening_amount)}</td><td>${row.balance==null ? "نامشخص" : currency(row.balance)}</td>` : resource==="categories" ? `<td>${row.transaction_type==="income" ? "درآمد" : "هزینه"}</td>` : ""}<td><button type="button" class="quiet" data-base-edit="${row.id}">ویرایش</button> <button type="button" class="quiet" data-base-delete="${row.id}">حذف</button></td></tr>`),headers.length);
  const complete=baseData.accounts.length && baseData.accounts.every(row=>row.balance!=null);
  document.getElementById("baseFoot").innerHTML=isAccount ? `<tr><th colspan="5">جمع موجودی حساب‌ها</th><td>${complete ? currency(baseData.accounts.reduce((sum,row)=>sum+row.balance,0)) : "ابتدا موجودی همهٔ حساب‌ها ثبت شود"}</td><td></td></tr>` : "";
  document.getElementById("baseWarning").textContent=isAccount && baseData.unassigned_count ? `${persianDigits(baseData.unassigned_count)} دریافت/پرداخت بدون حساب وجود دارد؛ در موجودی حساب‌ها نیست، ولی از روز مبنا در موجودی کل داشبورد لحاظ می‌شود. حساب آن‌ها را اصلاح کنید.` : "";
}
document.getElementById("baseResource").addEventListener("change",()=>{resetBaseForm();renderBaseData();});
document.getElementById("baseReset").addEventListener("click",resetBaseForm);
document.getElementById("baseRows").addEventListener("click",async event=>{
  const edit=event.target.closest("[data-base-edit]"), remove=event.target.closest("[data-base-delete]"); const resource=baseValue("baseResource");
  try {
    if(edit) {
      const row=baseData[resource].find(item=>item.id===Number(edit.dataset.baseEdit));
      for(const [id,key] of Object.entries({baseId:"id",baseName:"name",baseKind:"kind",baseBank:"bank_id",baseNumber:"account_number",baseOpening:"opening_amount",baseDate:"opening_date",baseCategory:"transaction_type"})) document.getElementById(id).value=row[key]??"";
      Money.scan();document.getElementById("baseName").focus();
    }
    if(remove && confirm("این مورد حذف شود؟ موارد استفاده‌شده قابل حذف نیستند.")) {
      await api(`/base-data/${resource}/${remove.dataset.baseDelete}?confirm=true`,{method:"DELETE"}); resetBaseForm();await loadBaseData();await loadReferenceData();await loadDashboard();
    }
  } catch(error) {setMessage("baseMessage",error.message,true);}
});
document.getElementById("baseForm").addEventListener("submit",async event=>{
  event.preventDefault();const resource=baseValue("baseResource"), id=baseValue("baseId"); const payload={name:baseValue("baseName")};
  if(resource==="accounts") Object.assign(payload,{kind:baseValue("baseKind"),bank_id:Number(baseValue("baseBank"))||null,account_number:baseValue("baseNumber"),opening_amount:baseValue("baseOpening").trim() ? amountNumber(baseValue("baseOpening")) : null,opening_date:baseValue("baseDate")||null});
  if(resource==="categories") payload.transaction_type=baseValue("baseCategory");
  const button=event.target.querySelector('[type="submit"]');button.disabled=true;
  try { await api(`/base-data/${resource}${id ? '/'+id : ''}`,{method:id ? "PUT" : "POST",body:JSON.stringify(payload)});resetBaseForm();await loadBaseData();await loadReferenceData();await loadDashboard();setMessage("baseMessage","اطلاعات ذخیره شد."); }
  catch(error) {setMessage("baseMessage",error.message,true);} finally {button.disabled=false;}
});
