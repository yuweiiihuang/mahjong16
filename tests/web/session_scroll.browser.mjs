// Run in CUA against an expanded session with enough records to overflow the dialog.
export async function checkSessionScroll(tab) {
  const position = () => tab.playwright.locator('#session-list').evaluate(el => ({
    top:el.scrollTop + (el.querySelector('.session-records-scroll')?.scrollTop || 0), height:el.clientHeight, total:el.scrollHeight,
  }));
  const header = await tab.playwright.locator('.session-records-scroll').first().evaluate(el => {
    const r=el.getBoundingClientRect();
    const head=el.querySelector('th').getBoundingClientRect();
    const viewport=document.getElementById('session-list').getBoundingClientRect();
    return {actual:head.top,expected:Math.max(r.top,Math.min(viewport.top,r.bottom-head.height))};
  });
  if (Math.abs(header.actual-header.expected)>1) throw Error('Hand table header is not pinned');
  const start = await position();
  if (start.top <= 0 || start.total <= start.height) {
    throw new Error('First scroll the expanded Session down to its hand table.');
  }
  const point = await tab.playwright.locator('.session-records').first().evaluate(el => {
    const table = el.getBoundingClientRect();
    const viewport = document.getElementById('session-list').getBoundingClientRect();
    return [(table.left + table.right) / 2,
      (Math.max(table.top, viewport.top) + Math.min(table.bottom, viewport.bottom)) / 2];
  });
  await tab.scroll(point, 'up', 2);
  await tab.getScreenshot({emit:false});
  const end = await position();
  if (end.top >= start.top) {
    throw new Error(`Wheel trapped over hand table: ${start.top} -> ${end.top}`);
  }
  return {before:start.top, after:end.top};
}
