import assert from 'node:assert/strict';

// Run with a result dialog open; checks rendered focus, not CSS source strings.
export async function checkResultFocus(tab) {
  const read = () => tab.playwright.evaluate(() => {
    const title = document.querySelector('#modal-title');
    const active = document.activeElement;
    return {titleOutline:getComputedStyle(title).outlineStyle,
      activeOutline:getComputedStyle(active).outlineStyle,
      activeWidth:getComputedStyle(active).outlineWidth};
  });
  assert.equal((await read()).titleOutline, 'none', 'static title must not have a focus ring');
  await tab.pressKey(null, 'Tab');
  await tab.getAXState({emit:false});
  assert.notEqual((await read()).activeWidth, '0px', 'keyboard focus must remain visible');
  await tab.playwright.locator('.result-winner .result-scoring summary').click();
  await tab.getAXState({emit:false});
  assert.equal((await read()).activeOutline, 'none', 'pointer focus must not leave a ring');
  await tab.pressKey(null, 'Tab');
  await tab.getAXState({emit:false});
  assert.notEqual((await read()).activeWidth, '0px', 'keyboard ring returns after pointer use');
  return {noTitleRing:true, noPointerRing:true, keyboardRing:true};
}
