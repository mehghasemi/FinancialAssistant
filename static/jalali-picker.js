/* Shared Persian calendar for static forms and dynamically inserted editors. */
const JalaliPicker = (()=>{
  const fa=value=>String(value).replace(/\d/g,d=>"۰۱۲۳۴۵۶۷۸۹"[d]);
  const en=value=>String(value).replace(/[۰-۹]/g,d=>"۰۱۲۳۴۵۶۷۸۹".indexOf(d)).replace(/[٠-٩]/g,d=>"٠١٢٣٤٥٦٧٨٩".indexOf(d));
  function normalize(value,mode="day") {
    const raw=en(value).trim().replace(/-/g,"/");
    const parts=raw.split("/");
    if(parts.length!==({day:3,month:2,year:1}[mode]) || parts.some(p=>!/^\d+$/.test(p))) return fa(raw);
    return fa(parts.map((p,i)=>String(Number(p)).padStart(i===0?4:2,"0")).join("/"));
  }
  if(typeof document==="undefined") return {normalize,en};
  const dialog=document.createElement("dialog");dialog.className="jalali-dialog";dialog.setAttribute("aria-labelledby","jalaliTitle");
  dialog.innerHTML=`<h2 id="jalaliTitle">انتخاب تاریخ شمسی</h2><div class="jalali-controls"><button type="button" class="quiet" data-shift="-1" aria-label="ماه قبل">→</button><label>ماه<select id="jalaliMonth">${jalaliMonths.map((m,i)=>`<option value="${i+1}">${m}</option>`).join("")}</select></label><label>سال<input id="jalaliYear" inputmode="numeric" maxlength="4" /></label><button type="button" class="quiet" data-shift="1" aria-label="ماه بعد">←</button></div><p id="jalaliMessage" role="status"></p><div class="jalali-days" id="jalaliDays"></div><div class="jalali-actions"><button type="button" class="quiet" id="jalaliToday">امروز</button><button type="button" class="primary" id="jalaliChoosePeriod" hidden>انتخاب</button><button type="button" class="quiet" id="jalaliClear">پاک کردن</button><button type="button" class="quiet" id="jalaliClose">انصراف</button></div>`;
  document.body.append(dialog);
  const yearInput=dialog.querySelector("#jalaliYear"),monthInput=dialog.querySelector("#jalaliMonth"),days=dialog.querySelector("#jalaliDays"),message=dialog.querySelector("#jalaliMessage");
  let target=null,trigger=null,year,month,request=0;
  const today=()=>currentJalaliParts();
  function close(){++request;dialog.close();trigger?.focus();}
  function choose(day){
    if(Number(en(yearInput.value))!==year){message.textContent="سال معتبر وارد کنید.";yearInput.focus();return;}
    const mode=target.dataset.jalali;
    const parts=mode==="year"?[year]:mode==="month"?[year,month]:[year,month,day];
    target.value=normalize(parts.join("/"),mode);target.setCustomValidity("");
    target.dispatchEvent(new Event("input",{bubbles:true}));target.dispatchEvent(new Event("change",{bubbles:true}));close();
  }
  async function render(){
    const token=++request;days.replaceChildren();message.textContent="";
    yearInput.value=fa(year);monthInput.value=String(month);
    const period=target.dataset.jalali!=="day";
    document.getElementById("jalaliChoosePeriod").hidden=!period;
    if(period) return;
    message.textContent="در حال نمایش تقویم…";
    try {
      const data=await api(`/calendar?year=${year}&month=${month}`);
      if(token!==request || !dialog.open) return;
      const now=today(), selected=normalize(target.value);
      message.textContent=`${jalaliMonths[month-1]} ${fa(year)}`;
      days.innerHTML=["شنبه","یکشنبه","دوشنبه","سه‌شنبه","چهارشنبه","پنجشنبه","جمعه"].map(label=>`<span>${label}</span>`).join("")+"<i></i>".repeat(data.weekday)+Array.from({length:data.days},(_,index)=>{
        const day=index+1, value=normalize(`${year}/${month}/${day}`),isToday=now.year===year&&now.month===month&&now.day===day;
        return `<button type="button" data-day="${day}" aria-label="${fa(day)} ${jalaliMonths[month-1]} ${fa(year)}" aria-pressed="${value===selected}" ${isToday?'aria-current="date"':''}>${fa(day)}</button>`;
      }).join("");
    } catch(error){if(token===request)message.textContent=error.message;}
  }
  function open(input,button){
    target=input;trigger=button;const now=today(),parts=en(input.value).split(/[/-]/).map(Number);
    year=parts[0]>=1&&parts[0]<=9377?parts[0]:now.year;month=parts[1]>=1&&parts[1]<=12?parts[1]:now.month;
    dialog.showModal();render();
  }
  function scan(root=document){
    root.querySelectorAll('input[data-jalali]:not([data-calendar-ready])').forEach(input=>{
      input.dataset.calendarReady="true";input.inputMode="numeric";
      input.placeholder=({day:"۱۴۰۵/۰۷/۱۵",month:"۱۴۰۵/۰۷",year:"۱۴۰۵"})[input.dataset.jalali];
      input.value=normalize(input.value,input.dataset.jalali);
      const wrapper=document.createElement("span");wrapper.className="date-entry";input.before(wrapper);wrapper.append(input);
      const button=document.createElement("button");button.type="button";button.className="quiet";button.textContent="▦";
      const label=input.labels?.[0]?.textContent.trim()||input.getAttribute("aria-label")||"تاریخ";
      button.setAttribute("aria-label",`انتخاب شمسی: ${label}`);button.setAttribute("aria-haspopup","dialog");wrapper.append(button);
      button.addEventListener("click",()=>open(input,button));
      input.addEventListener("input",()=>{const start=input.selectionStart,end=input.selectionEnd;input.value=fa(en(input.value));if(start!==null)input.setSelectionRange(start,end);input.setCustomValidity("");});
      input.addEventListener("blur",()=>{input.value=normalize(input.value,input.dataset.jalali);});
      input.addEventListener("keydown",event=>{if(event.key==="ArrowDown"&&event.altKey){event.preventDefault();open(input,button);}});
    });
  }
  dialog.addEventListener("click",event=>{
    const shift=event.target.closest("[data-shift]"),day=event.target.closest("[data-day]");
    if(shift){const key=year*12+month-1+Number(shift.dataset.shift);year=Math.floor(key/12);month=key%12+1;if(year<1||year>9377){year=Math.min(9377,Math.max(1,year));}render();}
    if(day)choose(Number(day.dataset.day));
  });
  yearInput.addEventListener("input",()=>{yearInput.value=fa(en(yearInput.value));});
  yearInput.addEventListener("change",()=>{const value=Number(en(yearInput.value));if(Number.isInteger(value)&&value>=1&&value<=9377){year=value;render();}else message.textContent="سال معتبر وارد کنید.";});
  monthInput.addEventListener("change",()=>{month=Number(monthInput.value);render();});
  document.getElementById("jalaliToday").addEventListener("click",()=>{const now=today();year=now.year;month=now.month;yearInput.value=fa(year);choose(now.day);});
  document.getElementById("jalaliChoosePeriod").addEventListener("click",()=>choose(1));
  document.getElementById("jalaliClear").addEventListener("click",()=>{target.value="";target.dispatchEvent(new Event("input",{bubbles:true}));target.dispatchEvent(new Event("change",{bubbles:true}));close();});
  document.getElementById("jalaliClose").addEventListener("click",close);
  dialog.addEventListener("cancel",event=>{event.preventDefault();close();});
  days.addEventListener("keydown",event=>{
    const steps={ArrowLeft:1,ArrowRight:-1,ArrowDown:7,ArrowUp:-7};
    if(!(event.key in steps) || !event.target.dataset.day) return;
    event.preventDefault();
    const next=Number(event.target.dataset.day)+steps[event.key];
    days.querySelector(`[data-day="${next}"]`)?.focus();
  });
  new MutationObserver(records=>{if(records.some(record=>record.addedNodes.length))scan();}).observe(document.body,{childList:true,subtree:true});
  scan();return {normalize,en,scan};
})();
if(typeof module!=="undefined")module.exports=JalaliPicker;
