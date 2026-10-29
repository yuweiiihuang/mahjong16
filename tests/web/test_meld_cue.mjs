import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {appContext} from './app-context.mjs';
import {meldCuePosition} from '../../ui/web/meld-cue.mjs';

const bounds = {left:8, top:8, right:792, bottom:442};
const size = {width:96, height:72};
test('meld cue follows side cards inward, top card rightward, and stays in the safe frame', () => {
  const card = {left:350, top:150, width:100, height:40};
  assert.deepEqual(meldCuePosition(card, size, bounds, 3), {left:462,top:134});
  assert.deepEqual(meldCuePosition(card, size, bounds, 1), {left:242,top:134});
  assert.deepEqual(meldCuePosition(card, size, bounds, 2), {left:462,top:134});
  const mobile = {left:40, top:6, right:352, bottom:224};
  assert.deepEqual(meldCuePosition({left:330,top:205,width:80,height:30},
    {width:72,height:56},mobile,3), {left:280,top:168});
  assert.deepEqual(meldCuePosition({left:0,top:0,width:80,height:30},
    {width:72,height:56},mobile,1), {left:40,top:6});
});

test('accepted meld cue replaces the previous notice, names the player and expires once', () => {
  const source = readFileSync(new URL('../../ui/web/app.js', import.meta.url), 'utf8');
  const cue = {hidden:true,dataset:{},style:{},offsetWidth:96,offsetHeight:72,
    setAttribute(key,value) {this[key] = value;}};
  const cards = {
    me: {left:50,top:350,width:100,height:40},
    'seat-3': {left:50,top:120,width:100,height:40},
    'seat-1': {left:650,top:120,width:100,height:40},
  };
  const timers = new Map(); let sequence = 0;
  const ctx = appContext({
    $: id => id === 'meld-cue' ? cue : {getBoundingClientRect:() => cards[id]},
    document:{querySelector:() => ({getBoundingClientRect:() =>
      ({left:0,top:0,width:800,height:450})})},
    state:{seating_order:[0,1,2,3],round:1,session_id:'A'},
    tableView:{safeFrame:null},names:['你','右家','對家','左家'],
    labels:{CHI:'吃',PONG:'碰',ANGANG:'暗槓',HU:'胡'},meldCuePosition,
    clearTimeout:id => timers.delete(id),
    setTimeout(callback,delay) {timers.set(++sequence,{callback,delay});return sequence;},
  });
  vm.runInContext(source.slice(source.indexOf('let meldCueTimer;'),
    source.indexOf("$('ting-panel').ontoggle")),ctx);
  ctx.showMeldCue({pid:0,type:'ANGANG'});
  assert.equal(cue.hidden,true,'own actions must not create a notice');
  assert.equal(timers.size,0);
  ctx.showMeldCue({pid:3,type:'PONG'});
  assert.equal(cue.hidden,false);
  assert.equal(cue.textContent,'碰');
  assert.equal(cue['aria-label'],'左家 碰');
  assert.equal(cue.style.left,'162px');
  ctx.showMeldCue({pid:1,type:'CHI'});
  assert.equal(cue.textContent,'吃');
  assert.equal(cue.style.left,'542px');
  assert.equal(timers.size,1,'old timeout must not hide a newer claim');
  const timer = [...timers.values()][0];
  assert.equal(timer.delay,1800);
  ctx.showMeldCue({pid:0,type:'PONG'});
  assert.equal(cue.textContent,'吃','own actions leave the opponent notice alone');
  assert.equal([...timers.values()][0],timer,'own actions do not extend the notice');
  ctx.showMeldCue({pid:3,type:'THINK'});
  assert.equal(cue.textContent,'吃','pending thinking is never an accepted meld');
  timer.callback();
  assert.equal(cue.hidden,true);
  ctx.state.done = true;
  ctx.state.winner = 1;
  ctx.state.win_source = 'RON';
  ctx.showMeldCue({pid:3,type:'DISCARD'});
  assert.equal(cue.textContent,'胡');
  assert.equal(cue['aria-label'],'右家 胡','use the winner, never the discarder');
  ctx.state.win_source = 'TSUMO';
  ctx.showMeldCue({pid:1,type:'HU'});
  assert.equal(cue.textContent,'自摸');
  assert.equal(cue.dataset.action,'HU','wins share the existing red action palette');
  cue.hidden = true;
  ctx.state.winner = 0;
  ctx.showMeldCue({pid:0,type:'HU'});
  assert.equal(cue.hidden,true,'own wins are also silent');
});
