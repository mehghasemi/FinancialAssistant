const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const context = vm.createContext({document:{getElementById:()=>({addEventListener(){}}),querySelectorAll:()=>[]}});
vm.runInContext(fs.readFileSync("static/dashboard-cash.js","utf8"),context);
const rows = [
  {id:1,date:"۱۴۰۵/۰۷/۰۲",due_date:"۱۴۰۵/۰۶/۰۱",kind:"installment",account_id:1,account_name:"بانک",title:"قسط",amount:300,assumed:1},
  {id:2,date:"۱۴۰۵/۰۷/۰۳",due_date:"۱۴۰۵/۰۷/۰۱",kind:"expense",account_id:null,account_name:"بدون حساب",title:"خرید",amount:200,assumed:0},
  {id:3,date:"۱۴۰۵/۰۶/۰۲",due_date:"۱۴۰۵/۰۷/۰۱",kind:"installment",account_id:1,account_name:"بانک",title:"پیش‌پرداخت",amount:100,assumed:0},
  {id:4,date:"۱۴۰۵/۰۷/۰۱",due_date:"۱۴۰۵/۰۷/۰۱",kind:"income",account_id:1,account_name:"بانک",title:"حقوق",amount:1000,assumed:0}
];
const ids=filters=>Array.from(context.filterCashRows(rows,{min:null,max:null,...filters}),row=>row.id);
assert.deepEqual(ids({year:"1405",month:"07",kind:"outgoing"}),[1,2]);
assert.deepEqual(ids({month:"07",relation:"arrears"}),[1]);
assert.deepEqual(ids({relation:"advance"}),[3]);
assert.deepEqual(ids({account:"none"}),[2]);
assert.deepEqual(ids({assumed:"yes"}),[1]);
assert.deepEqual(ids({from:"1405-07-02",to:"1405-07-03",min:250,max:500}),[1]);
assert.deepEqual(ids({search:"خرید"}),[2]);
assert.deepEqual(ids({year:"1404"}),[]);
assert.deepEqual(ids({}),[1,2,3,4]);
console.log("Cash filters: settlement month, arrears, account, range and amount OK");
