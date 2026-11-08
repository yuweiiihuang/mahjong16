import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source = readFileSync(new URL('../../ui/web/app.js', import.meta.url), 'utf8');
const toggleSource = source.slice(source.indexOf('async function toggleAiLevel('),
  source.indexOf('function melds('));

const plain = value => JSON.parse(JSON.stringify(value));
function context(levels, response) {
  const calls = [];
  const toggle = id => ({id, classList:{contains:name => name === 'ai-level-toggle'},
    focus() { ctx.focused = id; }});
  const ctx = vm.createContext({busy:false, state:{ai_levels:levels}, renders:0, toasts:[],
    focused:null, document:{activeElement:null},
    $: id => ({querySelector:() => toggle(`${id}@${ctx.renders}`)}),
    request: async (path, body) => { calls.push([path, body]); return response(body); },
    render() { ctx.renders += 1; }, toast(message) { ctx.toasts.push(message); }});
  ctx.focusToggle = seat => { ctx.document.activeElement = toggle(`seat-${seat}@${ctx.renders}`); };
  vm.runInContext(`${toggleSource};globalThis.run=toggleAiLevel;globalThis.read=()=>({busy,state});`, ctx);
  return {ctx, calls};
}

test('pregame nameplate toggle flips only that seat and adopts the server state', async () => {
  const {ctx, calls} = context(['standard','standard','advanced','standard'],
    body => ({ai_levels:body.levels}));
  await ctx.run(1);
  assert.deepEqual(plain(calls), [['/api/ai', {levels:['standard','advanced','advanced','standard']}]]);
  await ctx.run(2);
  assert.deepEqual(plain(calls[1][1].levels), ['standard','advanced','standard','standard']);
  assert.deepEqual(plain(ctx.read().state.ai_levels), ['standard','advanced','standard','standard']);
  assert.equal(ctx.read().busy, false);
  assert.equal(ctx.renders, 2);
  assert.equal(ctx.focused, null, 'mouse clicks leave focus alone');
});

test('pregame nameplate toggle hands keyboard focus to the re-rendered toggle', async () => {
  const {ctx} = context(['standard','standard','standard','standard'],
    body => ({ai_levels:body.levels}));
  ctx.focusToggle(2);
  await ctx.run(2);
  assert.equal(ctx.focused, 'seat-2@1');
});

test('pregame nameplate toggle keeps the old levels when the server refuses', async () => {
  const {ctx} = context(['standard','standard','standard','standard'],
    () => { throw new Error('牌桌已在其他分頁切換，請重新整理後操作。'); });
  await ctx.run(3);
  assert.deepEqual(plain(ctx.read().state.ai_levels), ['standard','standard','standard','standard']);
  assert.deepEqual(plain(ctx.toasts), ['牌桌已在其他分頁切換，請重新整理後操作。']);
  assert.equal(ctx.read().busy, false);
});
