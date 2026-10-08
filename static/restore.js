const restoreDialog=document.createElement("dialog");
restoreDialog.className="restore-dialog";restoreDialog.setAttribute("aria-labelledby","restoreTitle");
restoreDialog.innerHTML='<h2 id="restoreTitle">تأیید بازیابی اطلاعات</h2><p id="restoreConfirmText"></p><p id="restoreProgress" role="status"></p><div class="settings-actions"><button class="primary" id="restoreConfirmButton" type="button">تأیید و جایگزینی اطلاعات</button><button class="quiet" id="restoreCancelButton" type="button">انصراف</button><button class="primary" id="restoreReloadButton" type="button" hidden>نمایش اطلاعات بازیابی‌شده</button></div>';
document.body.append(restoreDialog);
let restoreSelectedFile=null,restoreBusy=false,restoreDone=false;
const restoreConfirm=document.getElementById("restoreConfirmButton"),restoreCancel=document.getElementById("restoreCancelButton");
document.getElementById("restoreForm").addEventListener("submit",event=>{
  event.preventDefault();restoreSelectedFile=document.getElementById("restoreFile").files[0];
  if(!restoreSelectedFile)return;
  if(restoreSelectedFile.size>100*1024*1024)return setMessage("restoreMessage","حداکثر حجم فایل ۱۰۰ مگابایت است.",true);
  document.getElementById("restoreConfirmText").textContent=`تمام اطلاعات فعلی با فایل «${restoreSelectedFile.name}» جایگزین می‌شود. قبل از جایگزینی، پشتیبان از اطلاعات فعلی تهیه خواهد شد. ادامه می‌دهید؟`;
  document.getElementById("restoreProgress").textContent="";restoreDialog.showModal();
});
restoreCancel.addEventListener("click",()=>restoreDialog.close());
restoreDialog.addEventListener("cancel",event=>{if(restoreBusy||restoreDone)event.preventDefault();});
document.getElementById("restoreReloadButton").addEventListener("click",()=>location.reload());
restoreConfirm.addEventListener("click",async()=>{
  restoreBusy=true;restoreConfirm.disabled=true;restoreCancel.disabled=true;
  const progress=document.getElementById("restoreProgress");progress.textContent="در حال اعتبارسنجی و بازیابی؛ این صفحه را نبندید…";
  try {
    const data=new FormData();data.append("file",restoreSelectedFile);
    const response=await fetch("/api/backups/restore?confirm=true",{method:"POST",body:data});const result=await response.json();
    if(!response.ok)throw new Error(result.detail||"بازیابی انجام نشد.");
    restoreDone=true;document.getElementById("restoreTitle").textContent="بازیابی انجام شد";
    document.getElementById("restoreConfirmText").textContent="اطلاعات با موفقیت بازیابی شد. برای مشاهدهٔ آن، دکمهٔ زیر را بزنید.";
    progress.textContent=`پشتیبان اطلاعات پیشین: ${result.backup_path}`;
    restoreConfirm.hidden=true;restoreCancel.hidden=true;document.getElementById("restoreReloadButton").hidden=false;document.getElementById("restoreReloadButton").focus();
  } catch(error){progress.textContent=error.message||"ارتباط قطع شد؛ پیش از تلاش دوباره وضعیت داده‌ها را بررسی کنید.";}
  finally {restoreBusy=false;restoreConfirm.disabled=false;restoreCancel.disabled=false;}
});
