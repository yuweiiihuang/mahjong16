import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../../ui/web/app.js', import.meta.url), 'utf8');
const handlers = source.slice(source.indexOf('function actionButton('),
  source.indexOf('function renderActions('));

test('discard starts before acknowledgement and restores authoritative state on rejection', async () => {
  for (const roomMode of [false,true]) {
    const before={version:1,phase:'TURN',hand:[4],drawn:5,rivers:[[],[],[],[]]};
    const action={type:'DISCARD',tile:4,from:'hand',index:0};
    const calls=[];
    let resolve,reject;
    const ctx=vm.createContext({
      state:before,selected:action,busy:false,roomMode,tingMode:false,tingPassed:false,
      chiSelection:null,pendingReaction:null,crypto:{randomUUID:()=> 'once'},
      renderActions() {},renderHand() {},beep() {},showResult() {},toast() {},
      tableView:{previewDiscard() {calls.push('preview');return Promise.resolve();},
        animateDiscard() {calls.push('replay');return Promise.resolve();}},
      render() {calls.push(ctx.state===before?'restore':'confirmed');},
      request:path=>path.endsWith('/action')?new Promise((a,b)=>{
        calls.push('request');resolve=a;reject=b;
      }):Promise.resolve(before),
      present:async (result,previewed)=>{calls.push(previewed?'skip-preview':'replay');ctx.state=result;},
    });
    vm.runInContext(source.slice(source.indexOf('async function perform('),
      source.indexOf('async function newGame(')),ctx);
    const pending=ctx.perform(action);
    assert.deepEqual(calls.slice(0,2),['preview','request']);
    assert.equal(ctx.state,before,'visual prediction must not advance the engine state');
    assert.equal(ctx.busy,true);
    resolve({...before,version:2,display_event:{type:'DISCARD',pid:0,tile:4}});
    await pending;
    assert.ok(!calls.includes('replay'),'acknowledgement must not animate the same discard twice');
    assert.equal(ctx.busy,false);
    ctx.state=before;
    const failed=ctx.perform(action);
    reject(new Error('stale'));
    await failed;
    assert.equal(ctx.state,before);
    assert.equal(calls.at(-1),'restore');
    assert.equal(ctx.busy,false);
  }
});

test('practice playback skips only the confirmed preview and keeps other players moving', async () => {
  const action={type:'DISCARD',tile:4,from:'hand'};
  const final={done:false};
  const animations=[],delays=[];
  const ctx=vm.createContext({state:{},selected:action,playbackFrame:null,pace:'natural',
    render() {},beep() {},showResult() {},
    tableView:{animateDiscard:async pid=>animations.push(pid)},
    setTimeout(resolve,delay) {delays.push(delay);resolve();}});
  vm.runInContext(source.slice(source.indexOf('async function present('),
    source.indexOf('async function perform(')),ctx);
  await ctx.present({...final,playback:[
    {pid:0,type:'DISCARD',state:{last_discard:{pid:0,tile:4}}},
    {pid:1,type:'DISCARD',state:{last_discard:{pid:1,tile:9}}},
  ]},action);
  assert.deepEqual(animations,[1]);
  assert.deepEqual(delays,[450]);
  assert.equal(ctx.state.done,false);
  assert.equal(ctx.playbackFrame,null);
});

test('available reactions group by type, keep order after submission, and choose exact chi', () => {
  const sent = [], choices = [];
  const node = () => ({dataset:{},children:[],classList:{add() {}},
    append(...children) { this.children.push(...children); },setAttribute(key,value) { this[key]=value; }});
  const ctx = vm.createContext({
    chiMode:'groups', chiSelection:null,
    state:{phase:'REACTION',round:1,last_discard:{pid:3,tile:1},rivers:[]},
    busy:false, labels:{CHI:'吃', PONG:'碰', GANG:'槓', HU:'胡', PASS:'過'},
    document:{createElement:node},tile:node,
    perform:action => sent.push(action), tileName:String,renderHand() {},
    renderActions() { choices.length=0; ctx.renderChiSelection({append:panel=>choices.push(...panel.children)}); },
  });
  vm.runInContext(handlers, ctx);
  const chi = {type:'CHI', use:[0,2]}, otherChi = {type:'CHI', use:[2,3]};
  const actions = [{type:'PASS'}, otherChi, {type:'PONG'}, chi];
  const buttons = [];
  const target = {dataset:{}, append:button => buttons.push(button)};
  ctx.renderReactionActions(target, [{type:'PASS'}]);
  assert.equal(buttons.length, 0);
  ctx.renderReactionActions(target, [{type:'PASS'}], {type:'PASS'});
  assert.equal(buttons.length, 0, 'automatic pass must not leave a visible button');
  ctx.renderReactionActions(target, actions);
  assert.deepEqual(buttons.map(button => button.textContent), ['吃','碰','過']);
  buttons[0].onclick();
  assert.equal(sent.length, 0, 'opening the chooser must not submit');
  choices[1].onclick();
  assert.deepEqual(sent, [chi]);
  assert.equal(choices[1].children.length,3,'every choice shows the complete sequence');
  buttons.length = 0;
  ctx.renderReactionActions(target, actions, chi);
  assert.deepEqual(buttons.map(button => button.textContent), ['吃','碰','過']);
  assert.ok(buttons.every(button => button.disabled));
  assert.deepEqual(buttons.map(button => button['aria-pressed']), ['true','false','false']);
  buttons.length = 0;
  ctx.renderReactionActions(target, actions, {type:'PASS'});
  assert.equal(buttons.at(-1)['aria-pressed'], 'true', 'a chosen pass remains when claims were available');
  buttons.length = 0;
  ctx.renderReactionActions(target, [{type:'HU'}, {type:'GANG'}, ...actions]);
  assert.deepEqual(buttons.map(button => button.textContent), ['吃','碰','槓','胡','過']);
});

test('chi hand selection rejects incompatible copies and confirms the exact legal pair', () => {
  const node = () => ({dataset:{},children:[],classList:{add() {}},
    append(...children) { this.children.push(...children); },setAttribute() {}});
  const sent=[], panels=[];
  const low={type:'CHI',use:[0,2]}, high={type:'CHI',use:[2,3]};
  const ctx = vm.createContext({
    state:{last_discard:{tile:1}},busy:false,selected:null,tingMode:false,
    chiSelection:{mode:'tiles', options:[low,high],picked:[]},
    document:{createElement:node},tile:node,tileName:String,perform:a=>sent.push(a),
    renderHand() {},renderActions() {},
  });
  vm.runInContext(handlers, ctx);
  vm.runInContext(source.slice(source.indexOf('function selectHandTile('),
    source.indexOf('function setTileFace(')), ctx);
  const click=(tile,index)=>ctx.selectHandTile({tile,index,from:'hand'});
  ctx.renderChiSelection({append:p=>panels.push(p)});
  assert.equal(panels[0].children[1].disabled,true);
  click(0,0); click(3,3); click(0,1);
  assert.deepEqual(Array.from(ctx.chiSelection.picked,p=>p.tile),[0]);
  click(2,2);
  ctx.renderChiSelection({append:p=>panels.push(p)});
  assert.equal(sent.length,0,'two picks do not submit before confirmation');
  panels.at(-1).children[1].onclick();
  assert.deepEqual(sent,[low]);
  click(0,0);
  assert.deepEqual(Array.from(ctx.chiSelection.picked,p=>p.tile),[2]);
  panels.at(-1).children[2].onclick();
  assert.equal(ctx.chiSelection,null,'cancel does not submit');
  assert.equal(sent.length,1);
});

test('ting offers pass immediately and stays dismissed until the next turn', () => {
  const buttons = [], sent = [];
  const target = {dataset:{}, append:b => buttons.push(b), replaceChildren() { buttons.length = 0; }};
  const ctx = vm.createContext({
    state:{phase:'TURN', legal_actions:[{type:'TING',tile:4,from:'hand'},
      {type:'TING',tile:5,from:'hand'}, {type:'DISCARD',tile:4,from:'hand'}]},
    selected:null, tingMode:false, tingPassed:false, busy:false, playbackFrame:null, chiSelection:null,
    $:() => target,
    document:{createElement:() => ({dataset:{},setAttribute() {}})},
    perform:a => sent.push(a), renderHand() {},
  });
  vm.runInContext(source.slice(source.indexOf('function actionButton('),
    source.indexOf('function uniqueTingOptions(')), ctx);
  for (const raiseFirst of [false, true]) {
    ctx.tingPassed = false;
    ctx.renderActions();
    assert.deepEqual(buttons.map(b => b.textContent), ['聽','過']);
    if (raiseFirst) buttons[0].onclick();
    buttons[1].onclick();
    assert.equal(ctx.tingMode, false);
    assert.equal(buttons.length, 0);
    ctx.renderActions();
    assert.equal(buttons.length, 0, 'polling the same turn must not restore ting');
  }
  assert.equal(sent.length, 0, 'passing ting is local and must not discard or declare');
  const legal = ctx.state.legal_actions;
  ctx.state.legal_actions = [];
  ctx.renderActions();
  ctx.state.legal_actions = legal;
  ctx.renderActions();
  assert.deepEqual(buttons.map(b => b.textContent), ['聽','過']);
});

test('switching between a room and practice clears local ting choices', async () => {
  const practice = {legal_actions:[{type:'TING',tile:4,from:'hand'}]};
  const room = {...practice,room:{code:'ABCD1234',members:[{name:'玩家'}]}};
  const ctx = vm.createContext({
    state:practice, selected:null, roomMode:false, busy:false, pollGeneration:0,autoTingDiscard:true,
    tingPassed:true, tingMode:true, URL, location:{href:'http://localhost/'},
    sessionStorage:{setItem() {},removeItem() {}}, history:{replaceState() {}},
    rememberPlayerName() {},pollRoom() {},render() {},toast() {},
    $:() => ({close() {}}), request:async path => ['/api/state','/api/preferences'].includes(path) ? practice : {},
  });
  vm.runInContext(source.slice(source.indexOf('function acceptRoom('),
    source.indexOf('async function pollRoom(')), ctx);
  vm.runInContext(source.slice(source.indexOf('async function leaveRoom('),
    source.indexOf("$('multiplayer').onclick")), ctx);
  ctx.acceptRoom(room);
  assert.equal(ctx.tingPassed, false);
  assert.equal(ctx.tingMode, false);
  ctx.tingPassed = true; ctx.tingMode = true;
  await ctx.leaveRoom();
  assert.equal(ctx.state, practice);
  assert.equal(ctx.tingPassed, false);
  assert.equal(ctx.tingMode, false);
});

test('ting declares a selected or sole tile kind and otherwise offers candidates', () => {
  const hand = {type:'TING',tile:4,from:'hand',waits:[2]};
  const drawn = {type:'TING',tile:4,from:'drawn',waits:[2]};
  const other = {type:'TING',tile:9,from:'hand',waits:[3]};
  for (const [selection, actions, expected] of [
    [{tile:4,from:'hand',index:0},[hand,drawn],hand],
    [{tile:4,from:'drawn'},[hand,drawn],drawn],
    [{tile:4,from:'drawn'},[hand,other],null],
    [{tile:8,from:'hand',index:1},[hand,other],null],
    [null,[hand,other],null],
    [null,[hand],hand],
    [null,[drawn],drawn],
    [null,[hand,drawn],hand],
    [{tile:8,from:'hand',index:1},[hand],hand],
  ]) {
    const buttons=[],sent=[];
    const target={dataset:{},replaceChildren() { buttons.length=0; },append:b=>buttons.push(b)};
    const ctx=vm.createContext({
      state:{phase:'TURN',legal_actions:actions},selected:null,busy:false,playbackFrame:null,
      chiSelection:null,tingMode:false,tingPassed:false,
      $:()=>target,document:{createElement:()=>({dataset:{},setAttribute() {}})},
      renderHand() {},perform:a=>sent.push(a),
    });
    vm.runInContext(source.slice(source.indexOf('function actionButton('),
      source.indexOf('function uniqueTingOptions(')),ctx);
    vm.runInContext(source.slice(source.indexOf('function selectHandTile('),
      source.indexOf('function setTileFace(')),ctx);
    if (selection) ctx.selectHandTile({type:'DISCARD',...selection});
    else ctx.renderActions();
    buttons[0].onclick();
    assert.deepEqual(sent,expected?[expected]:[]);
    assert.equal(ctx.tingMode,!expected,'an invalid or absent selection enters candidate mode');
    if (!expected) assert.equal(ctx.selected,null);
  }
});

test('submitting a chi choice never restores unchosen reactions before acknowledgement', async () => {
  const node=()=>({dataset:{},children:[],classList:{add() {}},
    append(...children) { this.children.push(...children); },setAttribute(k,v) { this[k]=v; }});
  const buttons=[], renders=[];
  const target={dataset:{},replaceChildren() { buttons.length=0; },append:b=>buttons.push(b)};
  const low={type:'CHI',use:[0,2]}, high={type:'CHI',use:[2,3]};
  let resolve,reject;
  const state={phase:'REACTION',round:1,rivers:[],last_discard:{tile:1},
    legal_actions:[low,high,{type:'PASS'}]};
  const ctx=vm.createContext({
    state,chiMode:'groups',chiSelection:null,pendingReaction:null,
    selected:null,busy:false,tingMode:false,tingPassed:false,playbackFrame:null,roomMode:true,
    labels:{CHI:'吃',PASS:'過'},document:{createElement:node},tile:node,tileName:String,
    $:()=>target,renderHand() {},crypto:{randomUUID:()=> 'once'},toast() {},
    request:path=>path==='/api/room/action'?new Promise((a,b)=>{resolve=a;reject=b;}):Promise.resolve(state),
    render() { ctx.renderActions(); renders.push(target.dataset.submitted); },
    showResult() {},
  });
  vm.runInContext(source.slice(source.indexOf('function actionButton('),source.indexOf('function uniqueTingOptions(')),ctx);
  vm.runInContext(source.slice(source.indexOf('async function perform('),source.indexOf('async function newGame(')),ctx);
  ctx.renderActions(); buttons[0].onclick();
  const request=ctx.perform(high);
  assert.equal(target.dataset.submitted,'true');
  assert.deepEqual(buttons.map(b=>b['aria-pressed']),['true','false']);
  assert.ok(buttons.every(b=>b.disabled));
  resolve({...state,legal_actions:[],reaction_choice:high,reaction_actions:state.legal_actions});
  await request;
  assert.ok(renders.every(value=>value==='true'));
  assert.equal(ctx.pendingReaction,null);
  assert.deepEqual(buttons.map(b=>b['aria-pressed']),['true','false']);
  // A rejected request restores the actual available choices.
  ctx.state=state;
  const failed=ctx.perform(low);
  reject(new Error('stale'));
  await failed;
  assert.equal(target.dataset.submitted,'false');
  assert.ok(buttons.every(b=>!b.disabled));
  ctx.roomMode=false;
  ctx.state=state;
  ctx.present=async () => {
    assert.equal(ctx.pendingReaction,null,'acknowledged choices must not leak into playback');
    ctx.state={...state,last_discard:{tile:4},legal_actions:[high,{type:'PASS'}]};
    ctx.render();
  };
  const practice=ctx.perform(low);
  resolve({});
  await practice;
  assert.equal(target.dataset.submitted,'false');
  assert.ok(buttons.every(b=>!b.disabled),'the next reaction window is selectable');
});
