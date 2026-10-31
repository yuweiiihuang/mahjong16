import test from 'node:test';
import assert from 'node:assert/strict';
import {botGlyph, botIndicator, seatChoices} from '../../ui/web/bot-indicator.mjs';
const node = tag=>({tag,attrs:{},children:[],dataset:{},style:{setProperty(key,value){this[key]=value;}},
  append(...items){this.children.push(...items);},setAttribute(key,value){this.attrs[key]=value;},
  closest(){return null;},contains(){return false;},getBoundingClientRect(){return {left:10,top:10,right:34,bottom:34,width:220,height:120};},
  showPopover(){this.open=true;},hidePopover(){this.open=false;this.ontoggle?.({newState:'closed'});},remove(){this.removed=true;}});
const doc={createElement:node,body:node('body'),defaultView:{innerWidth:500,innerHeight:400,matchMedia:()=>({matches:true})}};
test('bot levels use different silhouettes; only degraded robots carry a warning',()=>{
  assert.notEqual(botGlyph('standard'),botGlyph('advanced'));
  assert.equal(botIndicator({used:false},false,doc),null);
  const advanced=botIndicator({used:true,level:'advanced'},true,doc);
  assert.equal(advanced.attrs['aria-label'],'進階機器人');
  assert.ok(advanced.className.includes('ai-avatar avatar'));
  assert.ok(!advanced.className.includes('bot-status'));
  assert.equal(advanced.onpointerenter,undefined);
  assert.equal(advanced.onclick,undefined);
  assert.ok(!advanced.className.includes('is-degraded'));
  const fallback=botIndicator({used:true,level:'standard',degraded:true,fallback_after:7,
    fallback_reason:'timeout',mixed:true,segments:[{start:3,end:5,controller:'bot',level:'advanced'}]},false,doc);
  assert.ok(fallback.className.includes('is-degraded'));
  fallback.closest = selector => selector === '.seat-person' ? {getBoundingClientRect:()=>({left:60,top:30,right:200,bottom:90,width:140})} : null;
  let stopped=false;
  fallback.onclick({stopPropagation(){stopped=true;}});
  assert.ok(stopped);
  const dialog=doc.body.children.at(-1);
  assert.ok(dialog.open);
  assert.equal(dialog.tag,'div');
  assert.equal(dialog.attrs.popover,'auto');
  assert.equal(dialog.style.width,undefined,'keep the natural text width');
  assert.equal(dialog.style.left,'60px');
  assert.equal(dialog.children[1].textContent,'思考逾時，本局暫用標準。');
  dialog.children[0].onclick();
  assert.ok(!dialog.open && dialog.removed);
  assert.equal(botIndicator({used:null,level:'unknown'},false,doc).attrs['aria-label'],'AI 強度未記錄');
});
test('fixed seats sort consistently while retaining viewer-relative form indices',()=>{
  const choices=seatChoices({seat_ids:[1,2,3,0],seat_winds:['S','W','N','E'],
    ai_levels:['advanced','standard','standard','advanced']});
  assert.deepEqual(choices.map(row=>[row.id,row.pid,row.wind,row.level]),[
    [0,3,'E','advanced'],[1,0,'S','advanced'],[2,1,'W','standard'],[3,2,'N','standard']]);
});
