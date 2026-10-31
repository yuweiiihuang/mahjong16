const levels = {standard:'標準機器人',advanced:'進階機器人',unknown:'AI 強度未記錄'};
export function botGlyph(level) {
  const shape = level === 'advanced'
    ? '<path d="M7 3h10l5 6-2 11H4L2 9Z"/><path d="m6 10 4 2m8-2-4 2M8 16h8"/>'
    : level === 'standard'
      ? '<rect x="4" y="7" width="16" height="13" rx="3"/><path d="M12 3v4M1 12v5M23 12v5M8 12v3M16 12v3M8 18h8"/>'
      : '<circle cx="12" cy="12" r="9"/><path d="M9 9a3 3 0 1 1 5 2c-2 1-2 2-2 3m0 3h.01"/>';
  return `<svg viewBox="0 0 24 24" aria-hidden="true">${shape}</svg>`;
}
export function seatChoices(state) {
  return (state.ai_levels || ['standard','standard','standard','standard'])
    .map((level,pid)=>({pid,level,id:state.seat_ids?.[pid] ?? pid,wind:state.seat_winds[pid]}))
    .sort((a,b)=>a.id-b.id);
}
export function botIndicator(status, avatar = false, doc = document) {
  if (!status || status.used === false) return null;
  const level = status.level || 'unknown';
  const label = status.degraded ? '進階機器人 · 本局暫用標準' : levels[level];
  const button = doc.createElement(status.degraded ? 'button' : 'span');
  if (status.degraded) button.type = 'button';
  button.className = `ai-indicator${avatar ? ' ai-avatar avatar' : ''}${status.degraded ? ' is-degraded' : ''}`;
  button.innerHTML = botGlyph(level);
  button.setAttribute('aria-label',label);
  if (!status.degraded) { button.setAttribute('role','img'); return button; }
  button.setAttribute('aria-expanded','false');
  let panel = null;
  const hide = () => panel?.hidePopover();
  const show = () => {
    if (panel) return;
    const tip = doc.createElement('div'); tip.className = 'ai-popover';
    tip.setAttribute('popover','auto'); tip.setAttribute('role','dialog');
    tip.setAttribute('aria-label',label);
    const close = doc.createElement('button'); close.className = 'ai-popover-close'; close.textContent = '×';
    close.setAttribute('aria-label','關閉機器人資訊'); close.onclick = hide;
    const body = doc.createElement('div'); body.className = 'ai-popover-body';
    const reason = {busy:'服務忙碌',timeout:'思考逾時',unavailable:'進階暫不可用',error:'進階執行異常'}[status.fallback_reason] || '進階暫不可用';
    body.textContent = `${reason}，本局暫用標準。`;
    tip.append(close,body);
    panel = tip;
    tip.ontoggle = event => {
      if (event.newState === 'closed') {
        tip.remove(); if (panel === tip) panel = null;
        button.setAttribute('aria-expanded','false');
      }
    };
    tip.onpointerleave = event => { if (event.pointerType !== 'touch' && !button.contains(event.relatedTarget)) hide(); };
    (button.closest('dialog') || doc.body).append(tip);
    button.popoverTargetElement = tip; button.popoverTargetAction = 'show';
    tip.showPopover(); button.setAttribute('aria-expanded','true');
    const card = button.closest('.seat-person')?.getBoundingClientRect();
    const anchor = card || button.getBoundingClientRect();
    const viewport = doc.defaultView;
    const box = tip.getBoundingClientRect();
    tip.style.left = `${Math.max(8,Math.min(anchor.left,viewport.innerWidth - box.width - 8))}px`;
    const above = anchor.bottom + 6 + box.height > viewport.innerHeight - 8;
    tip.style.top = `${Math.max(8,above ? anchor.top - box.height - 6 : anchor.bottom + 6)}px`;

  };
  button.onpointerenter = event => { if (event.pointerType !== 'touch') show(); };
  button.onpointerleave = event => { if (event.pointerType !== 'touch' && !panel?.contains(event.relatedTarget)) hide(); };
  button.onfocus = () => { if (button.matches(':focus-visible')) show(); };
  button.onblur = event => { if (!panel?.contains(event.relatedTarget)) hide(); };
  button.onclick = event => {
    event.stopPropagation(); event.preventDefault?.();
    if (doc.defaultView.matchMedia('(hover: none), (pointer: coarse)').matches || event.detail === 0) show();
  };
  return button;
}
