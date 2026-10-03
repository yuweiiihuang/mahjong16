import test from 'node:test';
import assert from 'node:assert/strict';
import { RANDOM_NAMES, randomPlayerName } from '../../ui/web/player-names.mjs';

test('random names stay within the form limit and never repeat the current name', () => {
  assert.equal(RANDOM_NAMES.length,8);
  for (const removed of ['臭豆腐炒飯','麻雀雖小','紅中配綠茶','摸牌摸到魚']) {
    assert.ok(!RANDOM_NAMES.includes(removed));
  }
  assert.equal(new Set(RANDOM_NAMES).size,RANDOM_NAMES.length);
  for (const previous of RANDOM_NAMES) {
    assert.ok(previous.length <= 20);
    const next = randomPlayerName(previous);
    assert.ok(RANDOM_NAMES.includes(next));
    assert.notEqual(next,previous);
  }
});
