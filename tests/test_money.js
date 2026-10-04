const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const document = {addEventListener() {}, activeElement:null};
const context = vm.createContext({document});
vm.runInContext(fs.readFileSync("static/money.js","utf8") + "\nthis.money = Money;",context);
const {words,format} = context.money;
assert.equal(words("1250000"),"یک میلیون و دویست و پنجاه هزار تومان");
assert.equal(words("۱٬۲۵۰٬۰۰۰٬۰۰۰"),"یک میلیارد و دویست و پنجاه میلیون تومان");
assert.equal(words("0"),"صفر تومان");
assert.equal(words("-1200"),"منفی یک هزار و دویست تومان");
assert.equal(words(""),"");
assert.match(words("9007199254740992"),/محدوده/);
function input(value, cursor) {
  return {value,selectionStart:cursor, nextElementSibling:{classList:{contains:()=>true},textContent:""},
          setCustomValidity(value) { this.error=value; }, setSelectionRange(start,end) {this.selectionStart=start;this.selectionEnd=end;}};
}
const field = input("١٢50000",7); document.activeElement=field; format(field);
assert.equal(field.value,"۱٬۲۵۰٬۰۰۰"); assert.equal(field.selectionStart,9);
assert.equal(field.nextElementSibling.textContent,words("1250000"));
field.value="۱٬۹۲۵۰٬۰۰۰"; field.selectionStart=3; format(field);
assert.equal(field.value,"۱۹٬۲۵۰٬۰۰۰"); assert.equal(field.selectionStart,2);
field.value="0";field.selectionStart=1;format(field);assert.equal(field.value,"۰");
field.value="-1";format(field);assert.ok(field.error);
field.value="";format(field);assert.equal(field.error,"");assert.equal(field.nextElementSibling.textContent,"");
console.log("Money words, grouping, caret, zero and invalid-input checks: OK");
