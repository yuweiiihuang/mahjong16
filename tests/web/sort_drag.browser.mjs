import assert from 'node:assert/strict';

// Run with the browser tab supplied by the CUA REPL. Uses real pointer input and DOM geometry.
export async function checkSortDrag(tab, rounds = 12) {
  await tab.playwright.getByRole('button', { name: '設定', exact: true }).click();
  const read = () => tab.playwright.evaluate(() => ({
    hand: document.querySelector('#hand').getAttribute('aria-label'),
    locked: document.querySelector('#sort-order').hasAttribute('inert'),
    cards: [...document.querySelector('#sort-order').children].map(el => {
      const r = el.getBoundingClientRect();
      return { group: el.dataset.group, x: r.x + r.width / 2,
        y: r.y + r.height / 2, style: el.getAttribute('style') || '',
        label: el.getAttribute('aria-label') };
    })
  }));
  const initial = await read();
  for (let i = 0; i < rounds; i++) {
    const before = await read();
    const from = i % 2 === 0 ? 0 : 3;
    const to = i % 2 === 0 ? 3 : 0;
    const source = before.cards[from];
    const start = initial.cards[from];
    const target = initial.cards[to];
    await tab.drag([start.x, start.y], [target.x, target.y]);
    await tab.playwright.locator('.sortable-chosen').waitFor({ state: 'hidden', timeoutMs: 1000 });
    assert.equal((await read()).locked, false, 'drop must not lock the next drag');
    await tab.getAXState({ emit: false }); // Refresh presented-frame geometry after native input.
    const after = await read();
    const actual = after.cards.map(c => c.group);
    const moved = actual.indexOf(source.group);
    assert.ok(from === 0 ? moved > from : moved < from,
      `drop ${i + 1}: dragging across the row must change the order`);
    // Fixed flex slots must not retain the old implementation's translated cards.
    // Use DOM styles here: the CUA read-only evaluator can cache layout rectangles.
    after.cards.forEach((card, slot) => {
      assert.ok(!/transform\s*:\s*(?!none)[^;]+/.test(card.style),
        `drop ${i + 1}: card ${slot + 1} retained a drag translation`);
      assert.ok(card.label.endsWith(`第 ${slot + 1} 位`), 'accessible order matches the drop');
    });
    assert.equal(after.hand, initial.hand, 'unsaved drag must not rearrange the table');
    assert.equal(new Set(after.cards.map(c => c.group)).size, 4, 'no duplicate/lost cards');
  }
  await tab.playwright.getByRole('button', { name: '關閉', exact: true }).click();
  await tab.playwright.getByRole('button', { name: '設定', exact: true }).click();
  assert.deepEqual((await read()).cards.map(c => c.group), initial.cards.map(c => c.group),
    'closing without saving must discard the draft');
  return { passed: rounds, unchangedHand: true, cancelledDraft: true };
}
