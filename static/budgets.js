let budgetRequest = 0, budgetItems = [];
const budgetMonthValue = () => latinDigits(document.getElementById("budgetMonth").value.trim()).replace("/", "-");
document.getElementById("budgetMonth").value = todayJalali().slice(0,7);

async function loadBudgets() {
  const request = ++budgetRequest;
  try {
    const month = budgetMonthValue();
    if (!/^\d{4}-\d{2}$/.test(month)) throw new Error("ماه را مانند ۱۴۰۵/۰۷ وارد کنید.");
    const data = await api(`/budgets?month=${month}`);
    if (request !== budgetRequest) return;
    budgetItems = data.items;
    const category = document.getElementById("budgetCategory"), selected = category.value;
    category.innerHTML = '<option value="">انتخاب دسته</option>' + data.items.filter(item=>item.category_id).map(item=>`<option value="${item.category_id}">${escapeHtml(item.category)}</option>`).join("");
    category.value = selected;
    const amount = value => value === null ? "تعیین نشده" : currency(value);
    renderRows("budgetRows", data.items.map(item=>{
      const state = item.amount === null ? "بدون بودجه" : item.remaining < 0 ? "بیش از بودجه" : item.available < 0 ? "هشدار هزینه‌های در انتظار" : "در محدودهٔ بودجه";
      return `<tr class="${item.remaining < 0 ? "payment-overdue" : item.available < 0 ? "payment-partial" : ""}"><td>${escapeHtml(item.category)}</td><td>${amount(item.amount)}</td><td>${currency(item.spent)}</td><td>${currency(item.pending)}</td><td>${amount(item.remaining)}</td><td>${amount(item.available)}</td><td>${state}</td><td>${item.category_id ? `<button class="quiet edit-budget" data-id="${item.category_id}">تعیین / ویرایش</button>${item.amount !== null ? `<button class="quiet delete-budget" data-id="${item.category_id}">حذف بودجه</button>` : ""}` : "برای بودجه‌گذاری، دستهٔ تراکنش را مشخص کنید."}</td></tr>`;
    }),8);
    const summary = data.summary;
    const cards = [["مجموع بودجه",summary.amount],["مصرف دسته‌های بودجه‌دار",summary.spent],["در انتظار دسته‌های بودجه‌دار",summary.pending],["ماندهٔ واقعی بودجه",summary.remaining],["مانده با احتساب در انتظار",summary.available],["هزینه‌های بدون بودجه",summary.unbudgeted_expenses]];
    document.getElementById("budgetSummary").innerHTML = cards.map(([title,value])=>`<div><span>${title}</span><strong>${currency(value)}</strong></div>`).join("");
    document.getElementById("budgetFooter").innerHTML=`<tr><th>جمع دسته‌های بودجه‌دار</th>${[summary.amount,summary.spent,summary.pending,summary.remaining,summary.available].map(value=>`<td>${currency(value)}</td>`).join("")}<td colspan="2">اقساط و هزینه‌های متصل به آن‌ها در بودجه نیستند.</td></tr>`;
  } catch(error) {
    if (request !== budgetRequest) return;
    setMessage("budgetMessage", error.message, true);
    renderRows("budgetRows",[],8);
    document.getElementById("budgetSummary").innerHTML="";
    document.getElementById("budgetFooter").innerHTML="";
  }
}
document.getElementById("budgetMonth").addEventListener("change",()=>{ setMessage("budgetMessage",""); document.getElementById("budgetAmount").value=""; Money.scan(); loadBudgets(); });
document.getElementById("budgetForm").addEventListener("submit",async event=>{
  event.preventDefault();
  const button=event.target.querySelector('button[type="submit"]'); button.disabled=true;
  try {
    await api("/budgets",{method:"PUT",body:JSON.stringify({month:budgetMonthValue(),category_id:Number(document.getElementById("budgetCategory").value),amount:amountNumber(document.getElementById("budgetAmount").value)})});
    setMessage("budgetMessage","بودجه ذخیره شد."); await loadBudgets();
  } catch(error) { setMessage("budgetMessage",error.message,true); }
  finally { button.disabled=false; }
});
document.getElementById("budgetRows").addEventListener("click",async event=>{
  const edit=event.target.closest(".edit-budget"), remove=event.target.closest(".delete-budget");
  if(edit) {
    const item=budgetItems.find(row=>row.category_id===Number(edit.dataset.id));
    document.getElementById("budgetCategory").value=item.category_id;
    document.getElementById("budgetAmount").value=item.amount ?? "";
    Money.scan(); document.getElementById("budgetAmount").focus();
  }
  if(remove && confirm("بودجهٔ این دسته در ماه انتخابی حذف شود؟ تراکنش‌ها حفظ می‌شوند.")) {
    try {
      await api(`/budgets/${remove.dataset.id}?month=${budgetMonthValue()}&confirm=true`,{method:"DELETE"});
      setMessage("budgetMessage","بودجه حذف شد."); await loadBudgets();
    } catch(error) { setMessage("budgetMessage",error.message,true); }
  }
});

document.getElementById("budgetCategory").addEventListener("change",event=>{
  const item=budgetItems.find(row=>row.category_id===Number(event.target.value));
  document.getElementById("budgetAmount").value=item?.amount ?? "";
  Money.scan();
});
