const assert=require("node:assert/strict");
const picker=require("../static/jalali-picker.js");
assert.equal(picker.normalize("1405-7-5"),"۱۴۰۵/۰۷/۰۵");
assert.equal(picker.normalize("١٤٠٥/٧/٥"),"۱۴۰۵/۰۷/۰۵");
assert.equal(picker.normalize("1405/7","month"),"۱۴۰۵/۰۷");
assert.equal(picker.normalize("1405","year"),"۱۴۰۵");
assert.equal(picker.normalize(""),"");
assert.equal(picker.normalize("1405/0"),"۱۴۰۵/۰");
console.log("Persian date normalization: OK");
