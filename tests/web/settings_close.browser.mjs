import assert from 'node:assert/strict';

// Uses the real settings dialog without saving or changing persistent preferences.
export async function checkSettingsClose(tab) {
  const button = name => tab.playwright.getByRole('button', {name, exact:true});
  const open = async () => {
    await button('設定').click();
    await tab.getAXState({emit:false});
  };
  const visible = () => tab.playwright.locator('.settings-close-prompt').isVisible();
  const select = () => tab.playwright.locator('select[data-ai-seat="0"]');
  const choose = async value => {
    await tab.playwright.getByRole('combobox', {name:'席位 A AI 強度', exact:true}).click();
    await tab.getAXState({emit:false});
    await tab.playwright.getByRole('option', {name:value === 'advanced' ? '進階' : '標準', exact:true}).click();
    await tab.getAXState({emit:false});
  };
  await open();
  const original = await select().evaluate(el => el.value);
  const alternate = original === 'standard' ? 'advanced' : 'standard';
  await button('關閉').click();
  assert.equal(await tab.playwright.locator('#modal').isVisible(), false);
  await open();
  await choose(alternate);
  await button('關閉').click();
  assert.equal(await visible(), true);
  await button('繼續編輯').click();
  assert.equal(await select().evaluate(el => el.value), alternate);
  await choose(original);
  await button('關閉').click();
  assert.equal(await tab.playwright.locator('#modal').isVisible(), false);
  await open();
  await choose(alternate);
  await tab.pressKey(null, 'Escape');
  await tab.getAXState({emit:false});
  assert.equal(await visible(), true);
  await tab.pressKey(null, 'Escape');
  await tab.getAXState({emit:false});
  assert.equal(await visible(), false);
  assert.equal(await tab.playwright.locator('#modal').isVisible(), true);
  await tab.click([2,2]);
  await tab.getAXState({emit:false});
  assert.equal(await visible(), true);
  await button('捨棄').click();
  await open();
  assert.equal(await select().evaluate(el => el.value), original);
  await button('關閉').click();
  return {closeButton:true, escape:true, backdrop:true, revertedDraft:true, discardedDraft:true};
}
