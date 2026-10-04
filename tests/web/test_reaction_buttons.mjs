import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../../ui/web/app.js', import.meta.url), 'utf8');
const handlers = source.slice(source.indexOf('function actionButton('),
  source.indexOf('function renderActions('));

test('available reactions group by type, keep order after submission, and choose exact chi', () => {
  const sent = [], choices = [];
  let closed = false;
  const ctx = vm.createContext({
    busy:false, labels:{CHI:'吃', PONG:'碰', GANG:'槓', HU:'胡', PASS:'過'},
    document:{createElement:() => ({dataset:{}, setAttribute(key, value) { this[key] = value; }})},
    perform:action => sent.push(action), tileName:String, modal() {},
    $:id => id === 'modal' ? {close() { closed = true; }} : {append:button => choices.push(button)},
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
  assert.equal(closed, true);
  assert.deepEqual(sent, [chi]);
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

test('ting offers pass immediately and stays dismissed until the next turn', () => {
  const buttons = [], sent = [];
  const target = {dataset:{}, append:b => buttons.push(b), replaceChildren() { buttons.length = 0; }};
  const ctx = vm.createContext({
    state:{phase:'TURN', legal_actions:[{type:'TING',tile:4,from:'hand'},
      {type:'DISCARD',tile:4,from:'hand'}]},
    selected:null, tingMode:false, tingPassed:false, busy:false, playbackFrame:null,
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
    state:practice, selected:null, roomMode:false, busy:false, pollGeneration:0,
    tingPassed:true, tingMode:true, URL, location:{href:'http://localhost/'},
    sessionStorage:{setItem() {},removeItem() {}}, history:{replaceState() {}},
    rememberPlayerName() {},pollRoom() {},render() {},toast() {},
    $:() => ({close() {}}), request:async path => path === '/api/state' ? practice : {},
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
