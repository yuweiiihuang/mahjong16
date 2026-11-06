import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

// The thinking pause is a minimum: time already spent waiting on a native search counts.
function presenter() {
  const source = readFileSync(new URL('../../ui/web/app.js', import.meta.url), 'utf8');
  const pauses = [];
  const clock = {now: 0};
  const ctx = vm.createContext({
    Math: Object.assign(Object.create(Math), {random: () => 0}),
    performance: {now: () => clock.now},
    setTimeout(resolve, delay) { pauses.push(delay); resolve(); },
    tableView: {animateDiscard: async () => {}},
    render() {}, beep() {}, showMeldCue() {}, showResult() {},
  });
  vm.runInContext("var aiWaitSince = null, playbackFrame = null, selected = null, " +
    "state = null, pace = 'natural';", ctx);
  vm.runInContext(source.slice(source.indexOf('async function present('),
    source.indexOf('async function perform(')), ctx);
  return {ctx, pauses, clock};
}

const frame = (type) => ({pid: 1, type, state: {done: false}});

test('waiting on a pending search shortens only the next thinking pause', async () => {
  const {ctx, pauses, clock} = presenter();
  await ctx.present({playback: [], ai_pending: true});
  clock.now = 300;
  await ctx.present({playback: [], ai_pending: true});  // An empty poll keeps the start time.
  clock.now = 380;
  await ctx.present({playback: [frame('THINK'), frame('DISCARD')], ai_pending: false});
  assert.deepEqual(pauses, [120, 450], '500 ms think minus 380 ms waited; discard unchanged');
  assert.equal(ctx.aiWaitSince, null);
});

test('a search longer than the pause skips it, and no prior wait keeps it whole', async () => {
  const {ctx, pauses, clock} = presenter();
  await ctx.present({playback: [], ai_pending: true});
  clock.now = 900;
  await ctx.present({playback: [frame('THINK')], ai_pending: true});
  assert.deepEqual(pauses, [0]);
  assert.equal(ctx.aiWaitSince, 900, 'new frames restart the wait for the next search');
  ctx.aiWaitSince = null;
  await ctx.present({playback: [frame('THINK')], ai_pending: false});
  assert.deepEqual(pauses, [0, 500]);
});
