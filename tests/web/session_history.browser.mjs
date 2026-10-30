// Requires an expanded Session with its hand table visible in CUA.
export async function checkHistoryReturn(tab) {
  const before = await tab.playwright.locator('.session-records-scroll').first().evaluate(el => {
    const box=el.getBoundingClientRect();
    const button=[...el.querySelectorAll('button')].find(button=>{
      const r=button.getBoundingClientRect();
      return button.getAttribute('aria-label').includes('結算') && r.top>box.top+45 && r.bottom<box.bottom;
    });
    if (!button) throw Error('Scroll the hand table so a settlement button is visible.');
    const r=button.getBoundingClientRect();
    return {point:[r.x+r.width/2,r.y+r.height/2],label:button.getAttribute('aria-label'),
      outer:document.querySelector('#session-list').scrollTop,top:el.scrollTop,left:el.scrollLeft};
  });
  // A coordinate click avoids the locator's automatic scroll changing the position under test.
  await tab.click(before.point);
  await tab.playwright.locator('.result-dialog').waitFor({state:'visible',timeoutMs:15000});
  await tab.playwright.getByRole('button',{name:'返回紀錄',exact:true}).click();
  const after = await tab.playwright.locator('.session-records-scroll').first().evaluate(el=>({
    outer:document.querySelector('#session-list').scrollTop,top:el.scrollTop,left:el.scrollLeft,
    label:document.activeElement.getAttribute('aria-label'),
  }));
  for (const key of ['outer','top','left','label']) {
    if (before[key] !== after[key]) throw Error(`History return lost ${key}: ${before[key]} -> ${after[key]}`);
  }
  return after;
}
