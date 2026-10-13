import test from 'node:test';
import assert from 'node:assert/strict';
import { RANDOM_NAMES, randomPlayerName } from '../../ui/web/player-names.mjs';

test('random names stay within the form limit and never repeat the current name', t => {
  const random = Math.random;
  t.after(() => { Math.random = random; });
  assert.equal(RANDOM_NAMES.length,8);
  for (const removed of ['臭豆腐炒飯','麻雀雖小','紅中配綠茶','摸牌摸到魚']) {
    assert.ok(!RANDOM_NAMES.includes(removed));
  }
  assert.equal(new Set(RANDOM_NAMES).size,RANDOM_NAMES.length);
  for (const name of RANDOM_NAMES) assert.ok(name.length <= 20);
  for (const previous of ['', '自訂名稱', ...RANDOM_NAMES]) {
    const seen = new Set();
    for (let slot=0;slot<RANDOM_NAMES.length;slot++) {
      Math.random = () => slot / RANDOM_NAMES.length;
      const next = randomPlayerName(previous);
      assert.ok(RANDOM_NAMES.includes(next));
      assert.notEqual(next,previous);
      seen.add(next);
    }
    Math.random = () => 1 - Number.EPSILON;
    const last = randomPlayerName(previous);
    assert.ok(RANDOM_NAMES.includes(last));
    assert.notEqual(last,previous);
    assert.equal(seen.size,RANDOM_NAMES.length-Number(RANDOM_NAMES.includes(previous)));
  }
});
