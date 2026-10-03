import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

// Run the actual shared DOM click handler, with rendering and submission spies.
const source = readFileSync(new URL('../../ui/web/app.js', import.meta.url), 'utf8');
const handler = source.slice(source.indexOf('function selectHandTile('),
  source.indexOf('function tile('));
function input() {
  const sent = [];
  const ctx = vm.createContext({selected:null, busy:false, tingMode:false,
    renderHand() {}, renderActions() {},
    perform(action) { sent.push(action); ctx.busy = true; },
  });
  vm.runInContext(handler, ctx);
  return {ctx, sent, click:action => ctx.selectHandTile(action)};
}

test('same tile submits on the second click even after the double-click window', async () => {
  const {ctx, sent, click} = input();
  const tile = {type:'DISCARD', tile:4, from:'hand', index:0};
  click(tile);
  assert.equal(ctx.selected, tile);
  assert.equal(sent.length, 0);
  await new Promise(resolve => setTimeout(resolve, 650));
  click({...tile});
  assert.deepEqual(sent, [tile]);
  click(tile);
  assert.equal(sent.length, 1, 'extra clicks during submission cannot duplicate it');
});

test('identical tiles in different slots and the drawn tile select independently', () => {
  const {ctx, sent, click} = input();
  const first = {type:'DISCARD', tile:4, from:'hand', index:0};
  const second = {...first, index:1};
  const drawn = {type:'DISCARD', tile:4, from:'drawn'};
  click(first); click(second); click(drawn);
  assert.equal(ctx.selected, drawn);
  assert.equal(sent.length, 0);
  click(drawn);
  assert.deepEqual(sent, [drawn]);
});

test('ting mode declares on one candidate click and never discards another tile', () => {
  const {ctx, sent, click} = input();
  const ting = {type:'TING', tile:4, from:'hand', waits:[2]};
  const drawnTing = {...ting, from:'drawn'};
  ctx.state = {legal_actions:[ting, drawnTing]};
  ctx.tingMode = true;
  click({type:'DISCARD', tile:9, from:'hand', index:0});
  assert.equal(sent.length, 0);
  click({type:'DISCARD', tile:4, from:'drawn'});
  assert.deepEqual(sent, [drawnTing]);
});

test('hint deduplication ignores hand/drawn origin but preserves distinct wait sets', () => {
  const ctx = vm.createContext({});
  vm.runInContext(source.slice(source.indexOf('function uniqueTingOptions('),
    source.indexOf('function renderTing(')), ctx);
  const first = {tile:4, from:'hand', waits:[{tile:7,unseen:2},{tile:32,unseen:1}]};
  const duplicate = {...first, from:'drawn', waits:[...first.waits].reverse()};
  const different = {...first, waits:[{tile:8,unseen:2}]};
  assert.deepEqual(Array.from(ctx.uniqueTingOptions([first,duplicate,different])), [first,different]);
});
