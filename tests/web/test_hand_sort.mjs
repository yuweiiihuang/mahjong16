import assert from 'node:assert/strict';
import { test } from 'node:test';
import { sortHand, validOrder } from '../../ui/web/hand-sort.mjs';

test('default and custom suit order preserve ranks, duplicates and input', () => {
  const hand = [33, 8, 19, 27, 9, 0, 18, 31, 9];
  assert.deepEqual(sortHand(hand), [0, 8, 9, 9, 18, 19, 27, 31, 33]);
  assert.deepEqual(sortHand(hand, [3, 2, 0, 1]), [27, 31, 33, 18, 19, 0, 8, 9, 9]);
  assert.deepEqual(hand, [33, 8, 19, 27, 9, 0, 18, 31, 9]);
  for (const invalid of [null, '0,1,2,3', [0, 1, 2], [0, 1, 2, 2], [0, 1, 2, 4]]) {
    assert.equal(validOrder(invalid), false);
    assert.deepEqual(sortHand(hand, invalid), sortHand(hand));
  }
});
