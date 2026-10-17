// Verify generated static review controls with a fake DOM, no browser/network.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync(process.argv[2],'utf8');const code=html.match(/<script>([\s\S]*?)<\/script>/)[1];
const top={'#reveal':{},'#boxes':{},'#filter':{},'#export':{}};let clicked=false,blob=null;const toggles={};
const fields=[{name:'interest',value:'interesting'},{name:'keep',value:'yes'},{name:'notes',value:'moment'}];
function card(id,kind){return {dataset:{id,kind},hidden:false,listeners:{},addEventListener(k,f){this.listeners[k]=f},querySelectorAll:()=>fields}}
const a=card('image-000','grouped'),b=card('image-065','solo');
const context={document:{querySelector:k=>top[k],querySelectorAll:()=>[a,b],body:{classList:{toggle:(name,value)=>toggles[name]=value}},createElement:()=>({click(){clicked=true}})},Blob:class {constructor(parts){blob=JSON.parse(parts[0])}},URL:{createObjectURL:()=>'',revokeObjectURL:()=>{}},setTimeout:f=>f()};
vm.runInNewContext(code,context);
a.listeners.change();top['#export'].onclick();assert(clicked);assert.equal(blob.answers['image-000'].cull,'no');assert.equal(blob.answers['image-000'].model_revealed,false);
fields.find(f=>f.name==='keep').value='no';a.listeners.change();top['#export'].onclick();assert.equal(blob.answers['image-000'].cull,'yes');
fields.find(f=>f.name==='keep').value='';a.listeners.change();top['#export'].onclick();assert.equal(blob.answers['image-000'].cull,'');
assert(!html.includes('select name="cull"'));
top['#reveal'].onchange({target:{checked:true}});assert(toggles.revealed);a.listeners.change();top['#export'].onclick();assert.equal(blob.answers['image-000'].model_revealed,true);
top['#filter'].onchange({target:{value:'solo'}});assert(a.hidden&&!b.hidden);
top['#filter'].onchange({target:{value:'all'}});assert(!a.hidden&&!b.hidden);
top['#boxes'].onchange({target:{checked:true}});assert(toggles.showboxes);
assert(html.includes('.models{display:none}'));assert(!html.includes('fetch('));
console.log('Report controls passed: hidden suggestions, label export/reveal provenance, grouped/solo filters and optional boxes.');
