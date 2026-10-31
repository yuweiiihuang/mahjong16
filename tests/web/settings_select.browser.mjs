import assert from 'node:assert/strict';

// Exercise real menus, backing form values and handlers; leave all preferences unsaved.
export async function checkSettingsSelects(tab) {
  const initialAI = await tab.playwright.locator('select[data-ai-seat="0"]').evaluate(el=>el.value);
  for (const name of ['席位 A AI 強度','席位 B AI 強度','席位 C AI 強度','席位 D AI 強度',
    '對局節奏','樣式','排列']) {
    const trigger = tab.playwright.getByRole('combobox', {name,exact:true});
    const before = await trigger.evaluate(el => {
      const select = el.closest('.setting-select').querySelector('select');
      return {value:select.value, items:[...select.options].map(option =>
        ({value:option.value,label:option.textContent,disabled:option.disabled}))};
    });
    const menuId = await trigger.getAttribute('aria-controls');
    const menu = tab.playwright.locator(`#${menuId}`);
    await trigger.click();
    await tab.getAXState({emit:false});
    const geometry = await trigger.evaluate(el => {
      const a = el.getBoundingClientRect();
      const b = document.getElementById(el.getAttribute('aria-controls')).getBoundingClientRect();
      return {left:a.left, width:a.width, bottom:a.bottom, top:a.top,
        menuLeft:b.left, menuWidth:b.width, menuTop:b.top, menuBottom:b.bottom};
    });
    assert.ok(Math.abs(geometry.left-geometry.menuLeft)<1, `${name}: align left edges`);
    assert.ok(Math.abs(geometry.width-geometry.menuWidth)<1, `${name}: equal widths`);
    assert.ok(geometry.menuTop>=geometry.bottom || geometry.menuBottom<=geometry.top,
      `${name}: menu must not cover its own field`);
    await trigger.click();
    await tab.getAXState({emit:false});
    assert.equal(await trigger.getAttribute('aria-expanded'),'false',
      `${name}: clicking the same field again must close it`);
    await trigger.click();
    await tab.getAXState({emit:false});
    const original = before.items.find(item => item.value === before.value);
    const alternate = original.disabled ? null
      : before.items.find(item => !item.disabled && item.value !== before.value);
    if (!alternate) { await trigger.press('Escape'); continue; }
    await menu.getByRole('option', {name:alternate.label,exact:true}).click();
    await tab.getAXState({emit:false});
    assert.equal(await trigger.evaluate(el=>el.closest('.setting-select').querySelector('select').value),
      alternate.value, `${name}: selected option reaches original form state`);
    await trigger.click();
    await tab.getAXState({emit:false});
    await menu.getByRole('option', {name:before.items.find(item=>item.value===before.value).label,
      exact:true}).click();
    await tab.getAXState({emit:false});
    assert.equal(await trigger.evaluate(el=>el.closest('.setting-select').querySelector('select').value),
      before.value);
  }
  const ai = tab.playwright.getByRole('combobox', {name:'席位 A AI 強度',exact:true});
  await ai.press('ArrowDown');
  await tab.getAXState({emit:false});
  await tab.pressKey(null,'End');
  await tab.pressKey(null,'Enter');
  await tab.getAXState({emit:false});
  assert.equal(await ai.textContent(),'進階');
  await ai.press('ArrowUp');
  await tab.getAXState({emit:false});
  await tab.pressKey(null,'Home');
  await tab.pressKey(null,'Enter');
  await tab.getAXState({emit:false});
  assert.equal(await ai.textContent(),'標準');
  await ai.click();
  await tab.getAXState({emit:false});
  await tab.pressKey(null,'Escape');
  await tab.getAXState({emit:false});
  assert.equal(await ai.getAttribute('aria-expanded'),'false');
  assert.equal(await tab.playwright.locator('#modal').isVisible(),true);
  if (initialAI !== 'standard') {
    await ai.click();
    await tab.getAXState({emit:false});
    await tab.playwright.getByRole('option', {name:'進階',exact:true}).click();
    await tab.getAXState({emit:false});
  }
  return {alignedMenus:7, originalHandlers:true, keyboard:true, escapePreservesSettings:true};
}
