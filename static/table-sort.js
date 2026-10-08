/* Sort only data rows; inline editors travel with their parent row. */
const TableSort = (() => {
  const columns = {
    cashActivityRows: ["date","date","text","text","text","number","number"],
    cashReserveRows: ["date","text","text","number"],
    budgetRows: ["text","number","number","number","number","number","text"],
    transactionRows: ["date","text","text","text","number","text","text","text","text"],
    installmentRows: ["text","date","date","number","number","number","text"],
    assetRows: ["text","text","date","number","number","number","text"],
    assetHistoryRows: ["date","number","number","text"],
    previewRows: ["number","date","number"]
  };
  const collator = new Intl.Collator("fa", {numeric:true, sensitivity:"base"});
  function normalized(text) {
    return text.replace(/[۰-۹]/g,c=>"۰۱۲۳۴۵۶۷۸۹".indexOf(c)).replace(/[٠-٩]/g,c=>"٠١٢٣٤٥٦٧٨٩".indexOf(c)).replace(/[\u200e\u200f\u061c]/g,"").replace(/−/g,"-").trim();
  }
  function value(cell,type) {
    const copy=cell.cloneNode(true); copy.querySelectorAll(".amount-words,button").forEach(node=>node.remove());
    const text=normalized(copy.textContent);
    if(type === "number") { const raw=text.replace(/[٬,\s]|تومان/g,""); return /^-?\d+$/.test(raw) ? Number(raw) : null; }
    if(type === "date") {
      const parts=text.match(/(\d{4})[/-](\d{1,2})[/-](\d{1,2})(?:[،, ]+(\d{1,2}):(\d{2}))?/);
      return parts ? parts.slice(1).map(part=>(part||"0").padStart(2,"0")).join("") : null;
    }
    return text;
  }
  function compare(left,right,type) {
    if(left===null) return right===null ? 0 : 1;
    if(right===null) return -1;
    return type==="number" ? left-right : collator.compare(left,right);
  }
  function apply(body) {
    const table=body.closest("table"), index=Number(table.dataset.sortColumn), type=columns[body.id]?.[index];
    if(table.dataset.sortColumn===undefined || !type) return;
    const descending=table.dataset.sortDirection==="descending";
    const groups=[];
    Array.from(body.rows).forEach(row=>{
      if(row.cells.length===1 && row.cells[0].colSpan>1) {
        if(groups.length) groups[groups.length-1].rows.push(row);
      } else groups.push({rows:[row],key:value(row.cells[index],type),position:groups.length});
    });
    groups.sort((a,b)=>{
      const result=compare(a.key,b.key,type);
      return (a.key===null || b.key===null ? result : descending ? -result : result) || a.position-b.position;
    });
    for(const group of groups) for(const row of group.rows) body.append(row);
  }
  function refresh(id) {
    if(id==="baseRows") columns.baseRows=document.getElementById("baseResource").value==="accounts" ? ["text","text","text","date","number","number"] : document.getElementById("baseResource").value==="categories" ? ["text","text"] : ["text"];
    if(!columns[id]) return;
    const body=document.getElementById(id), table=body.closest("table");
    const headers=Array.from(table.tHead.rows[0].cells);
    headers.forEach((header,index)=>{
      if(!columns[id][index]) return;
      if(header.dataset.tableSortReady) {
        if(!header.querySelector(".sort-arrow")) {
          const arrow=document.createElement("span"); arrow.className="sort-arrow"; arrow.setAttribute("aria-hidden","true");
          arrow.textContent=table.dataset.sortColumn===String(index)?(table.dataset.sortDirection==="ascending"?" ↑":" ↓"):" ↕"; header.append(arrow);
        }
        return;
      }
      header.dataset.tableSortReady="true"; header.tabIndex=0; header.setAttribute("aria-sort","none");
      header.classList.add("sortable-heading");
      const indicator=document.createElement("span"); indicator.className="sort-arrow"; indicator.setAttribute("aria-hidden","true"); indicator.textContent=" ↕"; header.append(indicator);
      const toggle=()=>{
        const direction=table.dataset.sortColumn===String(index) && table.dataset.sortDirection==="ascending" ? "descending":"ascending";
        table.dataset.sortColumn=String(index); table.dataset.sortDirection=direction;
        headers.forEach((cell,i)=>{ if(!columns[id][i]) return; cell.setAttribute("aria-sort",i===index?direction:"none"); cell.querySelector(".sort-arrow").textContent=i===index?(direction==="ascending"?" ↑":" ↓"):" ↕"; });
        apply(body);
      };
      header.addEventListener("click",toggle);
      header.addEventListener("keydown",event=>{if(event.key==="Enter"||event.key===" "){event.preventDefault();toggle();}});
    });
    apply(body);
  }
  return {refresh, compare, normalized};
})();
