import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import {appContext} from './app-context.mjs';

const source = readFileSync(new URL('../../ui/web/app.js', import.meta.url),'utf8');
const helpers = source.slice(source.indexOf('function replayLabel('),source.indexOf('function acceptRoom('));
function fixture() {
  const nodes = Object.fromEntries(['replay-step','replay-label','replay-prev','replay-next',
    'replay-play','replay-speed','replay-view-E','replay-view-S','replay-view-W','replay-view-N',
    'replay-exit','meld-cue','toast'].map(id=>[id,{dataset:{},classList:{remove(){}},
      setAttribute(key,value){this[key]=value;}}]));
  const live = {hand:[1],session_id:'live'};
  const frames = [
    {seq:0,event:null,state:{seat_winds:['E','S','W','N'],replay_viewer:0,replay_names:['你','右','對','左']}},
    {seq:4,event:{type:'PONG',pid:3,tile:4,from_pid:1},state:{seat_winds:['E','S','W','N'],replay_viewer:0,replay_names:['你','右','對','左']}},
    {seq:8,event:{type:'HU',pid:1,tile:7},state:{seat_winds:['E','S','W','N'],replay_viewer:0,replay_names:['你','右','對','左'],win_source:'TSUMO'}},
  ];
  const notices=[],requests=[];
  const ctx=appContext({state:live,replay:{id:'saved',frames,index:0,loading:false,playing:false,speed:1,timer:null},
    $:id=>nodes[id],clearTimeout() {},meldCueTimer:null,
    pace:'natural',winds:['東','南','西','北'],tileName:id=>`牌${id}`,labels:{PONG:'碰',HU:'胡'},
    render() {ctx.renderReplayControls();},showMeldCue:event=>notices.push(event.type),
    toast:message=>notices.push(message),
    request:async path=>{requests.push(path);return {frames};},
  });
  vm.runInContext(helpers,ctx);
  return {ctx,nodes,live,frames,notices,requests};
}

test('replay seeks and steps without changing live state, keeps controls at both boundaries',()=>{
  const {ctx,nodes,live,frames,notices}=fixture();
  ctx.replayStep(1);
  assert.equal(ctx.replay.index,1);
  assert.equal(nodes['replay-step'].value,1);
  assert.match(nodes['replay-label'].title,/左 碰 牌4（右）/);
  assert.deepEqual(notices,['PONG']);
  assert.equal(ctx.state,live);
  assert.equal(ctx.displayedState(),frames[1].state);
  ctx.replayStep(900);
  assert.equal(ctx.replay.index,2);
  assert.equal(nodes['replay-next'].disabled,true);
  assert.match(nodes['replay-label'].title,/右 自摸 牌7/);
  ctx.replayStep(-9);
  assert.equal(ctx.replay.index,0);
  assert.equal(nodes['replay-prev'].disabled,true);
});

test('changing perspective keeps the current event and failed fetch preserves previous view',async()=>{
  const {ctx,nodes,frames,requests}=fixture();
  ctx.replayStep(1);
  const other=frames.map(frame=>({...frame,state:{...frame.state,replay_viewer:2,seat_winds:['W','N','E','S']}}));
  ctx.request=async path=>{requests.push(path);return {frames:other};};
  await ctx.changeReplayView(2);
  assert.equal(ctx.replay.index,1);
  assert.equal(ctx.replay.frames,other);
  assert.equal(nodes['replay-view-W']['aria-pressed'],'true');
  assert.match(requests[0],/&view=2$/);
  ctx.request=async()=>{throw new Error('offline');};
  await ctx.changeReplayView(3);
  assert.equal(ctx.replay.frames,other);
  assert.equal(nodes['replay-view-W']['aria-pressed'],'true');
  assert.equal(ctx.replay.loading,false);
});

test('read-only replay prevents game writes and tile selection even through direct handlers',async()=>{
  let writes=0;
  const ctx=appContext({state:{hand:[1]},replay:{frames:[],index:0},busy:false,
    fetch:async()=>{writes++;},selected:null});
  vm.runInContext(source.slice(source.indexOf('async function request('),
    source.indexOf('async function present(')),ctx);
  await assert.rejects(ctx.request('/api/action',{type:'DISCARD'}),/重播中/);
  vm.runInContext(source.slice(source.indexOf('function selectHandTile('),
    source.indexOf('function setTileFace(')),ctx);
  ctx.selectHandTile({type:'DISCARD',tile:1});
  assert.equal(ctx.selected,null);
  vm.runInContext(source.slice(source.indexOf('async function perform('),
    source.indexOf('async function newGame(')),ctx);
  await ctx.perform({type:'DISCARD',tile:1});
  assert.equal(writes,0);
});

test('multiplayer polls retain heartbeats and live updates without touching the replay scene',async()=>{
  let reads=0,renders=0;
  const live={version:1};
  const ctx=appContext({state:live,replay:{},roomMode:true,pollGeneration:1,busy:false,
    request:async()=>{if(++reads===2)ctx.roomMode=false;return {version:reads+1};},
    render(){renders++;},
  });
  vm.runInContext(source.slice(source.indexOf('async function pollRoom('),
    source.indexOf('async function roomCommand(')),ctx);
  await ctx.pollRoom(1);
  assert.equal(reads,2);
  assert.equal(ctx.state.version,2);
  assert.equal(renders,0);
  assert.ok(ctx.replay);
});

test('exit refreshes authoritative live state and ignores a late perspective response',async()=>{
  const {ctx,nodes,frames}=fixture();
  let finishView;
  const latest={version:9,hand:[7],done:false};
  ctx.pollGeneration=1;ctx.roomMode=false;
  ctx.sessionStorage={removeItem(){}};
  ctx.lockReplaySurface=()=>{};
  ctx.request=path=>path==='/api/state'?Promise.resolve(latest)
    :new Promise(resolve=>{finishView=resolve;});
  const loading=ctx.changeReplayView(2);
  assert.equal(ctx.replay.loading,true);
  assert.equal(nodes['replay-exit'].disabled,false,'exit stays available while a view loads');
  ctx.render=()=>{};
  await ctx.exitReplay();
  assert.equal(ctx.state,latest);
  assert.equal(ctx.replay,null);
  finishView({frames});await loading;
  assert.equal(ctx.state,latest);
  assert.equal(ctx.replay,null);
});

test('failed exit keeps replay read-only and allows retry',async()=>{
  const {ctx,nodes}=fixture();
  ctx.pollGeneration=0;ctx.roomMode=false;
  ctx.request=async()=>{throw new Error('offline');};
  await ctx.exitReplay();
  assert.ok(ctx.replay);
  assert.equal(ctx.replay.loading,false);
  assert.equal(ctx.replay.exiting,false);
  assert.equal(nodes['replay-exit'].disabled,false);
  assert.equal(nodes['replay-next'].disabled,false);
});

test('an older replay API fails visibly without locking the live table',async()=>{
  const messages=[];
  const ctx=appContext({busy:false,tableView:{},request:async()=>({frames:[{state:{}}]}),
    toast:message=>messages.push(message)});
  vm.runInContext(helpers,ctx);
  await ctx.showReplay('old-record');
  assert.equal(ctx.replay,null);
  assert.equal(ctx.busy,false);
  assert.match(messages[0],/更新伺服器/);
});

test('autoplay follows the table pace, applies speed, pauses on seek and stops at the end',()=>{
  const {ctx,nodes}=fixture();
  ctx.replay.frames[1].event.type='DISCARD';ctx.labels.DISCARD='出牌';
  const timers=new Map();let serial=0;
  ctx.setTimeout=(callback,delay)=>{timers.set(++serial,{callback,delay});return serial;};
  ctx.clearTimeout=id=>timers.delete(id);
  const tick=()=>{const [id,timer]=timers.entries().next().value;timers.delete(id);timer.callback();};
  const delay=()=>timers.values().next().value.delay;
  ctx.toggleReplay();
  assert.equal(delay(),700);
  assert.equal(nodes['replay-play']['aria-label'],'暫停重播');
  tick();
  assert.equal(ctx.replay.index,1);
  assert.equal(delay(),450);
  ctx.replay.speed=2;ctx.scheduleReplay();
  assert.equal(timers.size,1,'speed change replaces rather than duplicates the timer');
  assert.equal(delay(),225);
  ctx.toggleReplay();
  assert.equal(timers.size,0);
  assert.equal(nodes['replay-play']['aria-label'],'播放重播');
  ctx.toggleReplay();tick();
  assert.equal(ctx.replay.index,2);
  assert.equal(ctx.replay.playing,false);
  assert.equal(timers.size,0,'terminal frame never starts another timer');
  ctx.toggleReplay();
  assert.equal(ctx.replay.index,0,'play at the end restarts from the beginning');
  ctx.replayStep(1);
  assert.equal(ctx.replay.playing,false);
  assert.equal(timers.size,0,'manual seek pauses playback');
  ctx.pace='fast';ctx.toggleReplay();
  assert.equal(delay(),450*.35/2,'1x cadence still respects the table pace setting');
});

test('wind buttons map physical winds to the recorded seat, including rotated seating',()=>{
  const {ctx,nodes,frames}=fixture();
  frames[0].state={...frames[0].state,replay_viewer:2,seat_winds:['N','E','S','W']};
  ctx.renderReplayControls();
  assert.equal(nodes['replay-view-N'].dataset.viewer,2);
  assert.equal(nodes['replay-view-N']['aria-pressed'],'true');
  assert.equal(nodes['replay-view-E'].dataset.viewer,3);
  assert.equal(nodes['replay-view-S'].dataset.viewer,0);
  assert.equal(nodes['replay-view-W'].dataset.viewer,1);
  assert.equal(nodes['replay-view-E']['aria-pressed'],'false');
});

test('replay keeps the hand description accessible while locking game controls',()=>{
  const elements=Object.fromEntries(['.table-toolbar','.table-canvas','#hand','#ting-panel',
    '#room-panel'].map(selector=>[selector,{inert:false}]));
  elements['#hand'].ariaLabel='手牌：一萬、二萬、三萬';
  const ctx=appContext({document:{body:{classList:{toggle(){}}},
    querySelectorAll:selectors=>selectors.split(',').map(selector=>elements[selector])}});
  vm.runInContext(helpers,ctx);
  ctx.lockReplaySurface(true);
  assert.equal(elements['#hand'].inert,false,'a read-only hand must remain in the accessibility tree');
  assert.equal(elements['#hand'].ariaLabel,'手牌：一萬、二萬、三萬');
  assert.equal(elements['.table-toolbar'].inert,true);
  ctx.lockReplaySurface(false);
  assert.ok(Object.values(elements).every(element=>!element.inert));
});
