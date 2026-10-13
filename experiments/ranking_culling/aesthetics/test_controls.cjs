// Execute only the generated script in a fake DOM; no browser or network.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const documentText=fs.readFileSync(process.argv[2],'utf8');
const code=documentText.match(/<script>([\s\S]*?)<\/script>/)[1];
function element(value=''){return {value,hidden:true,disabled:false,checked:false,listeners:{},addEventListener(k,f){this.listeners[k]=f}}}
function setup(saved){
 const radios=[element('0'),element('1'),element('none')];
 const fields={'.category':element('unknown'),'.notes':element(),'.assessment':element(),'.reveal':element()};
 const models=[element(),element()];
 const section={id:'group-001',listeners:{},addEventListener(k,f){this.listeners[k]=f},querySelector(s){return s==='input[type=radio]:checked'?radios.find(r=>r.checked):fields[s]},querySelectorAll(s){return s==='input[type=radio]'?radios:models}};
 const globalFields={'#status':element(),'#storage':element(),'#export':element(),'#import':element()};let store=saved||null,clicked=false;
 const ctx={document:{querySelector:s=>globalFields[s],querySelectorAll:()=>[section],createElement:()=>({click(){clicked=true}})},localStorage:{getItem:()=>store,setItem:(k,v)=>store=v},Blob,URL:{createObjectURL:()=>'',revokeObjectURL:()=>{}},setTimeout:f=>f(),alert:msg=>{throw Error(msg)}};
 vm.runInNewContext(code,ctx);return {section,fields,models,radios,globalFields,getSaved:()=>store,getClicked:()=>clicked};
}
const a=setup();assert(a.models.every(m=>m.hidden));assert(a.fields['.reveal'].disabled);
a.radios[0].checked=true;a.section.listeners.change({});assert(!a.fields['.reveal'].disabled);
a.fields['.reveal'].onclick();assert(a.models.every(m=>!m.hidden));assert(a.fields['.reveal'].disabled);
a.radios[0].checked=false;a.radios[1].checked=true;a.section.listeners.change({});
let saved=JSON.parse(a.getSaved());assert.equal(saved['group-001'].blind_choice,0);assert.equal(saved['group-001'].choice,1);assert(saved['group-001'].changed_after_reveal);
a.fields['.reveal'].onclick();assert.equal(JSON.parse(a.getSaved())['group-001'].blind_choice,0);
a.globalFields['#export'].onclick();assert(a.getClicked());
const b=setup(a.getSaved());assert(b.radios[1].checked);assert(b.models.every(m=>!m.hidden));
console.log('Generated JS checks passed: initial blind state, gated reveal, frozen blind choice, change flag, export trigger, browser-storage restoration. Visual browser behavior remains unverified.');
