const fs=require('fs'),vm=require('vm'),assert=require('assert');
const code=fs.readFileSync(process.argv[2],'utf8').match(/<script>([\s\S]*?)<\/script>/)[1];
const input={value:''},status={},exportButton={};let exported;
function card(id,score){const flag={hidden:true};return {dataset:{id,score},flag,classList:{toggle(){}},querySelector:()=>flag}}
const cards=[card('a','0.425'),card('b','0.383'),card('c','')];
const context={document:{querySelector:s=>({'#cutoff':input,'#status':status,'#export':exportButton}[s]),querySelectorAll:()=>cards,createElement:()=>({click(){}})},Number,Blob:class{constructor(parts){exported=JSON.parse(parts[0])}},URL:{createObjectURL:()=>'',revokeObjectURL:()=>{}},setTimeout:f=>f()};
vm.runInNewContext(code,context);exportButton.onclick();assert.equal(exported.solo_threshold,null);assert.equal(exported.interesting_solo_ids.length,0);
input.value='0.4';input.oninput();exportButton.onclick();assert.deepEqual(exported.interesting_solo_ids,['a']);assert(!cards[0].flag.hidden);assert(cards[1].flag.hidden&&cards[2].flag.hidden);
input.value='0';input.oninput();exportButton.onclick();assert.deepEqual(exported.interesting_solo_ids,['a','b']);assert(cards[2].flag.hidden);
input.value='1.2';input.oninput();exportButton.onclick();assert.equal(exported.solo_threshold,null);assert.equal(exported.interesting_solo_ids.length,0);
console.log('Cutoff controls passed: unset stays off, threshold highlights/export agree, unscored never treated as zero, invalid values disable.');
