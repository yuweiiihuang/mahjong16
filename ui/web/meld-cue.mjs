// Anchor to the displayed card bounds, so seating changes and table zoom agree.
export function meldCuePosition(card, cue, bounds, seat) {
  const gap = 12;
  let left = card.left + (card.width - cue.width) / 2;
  let top = card.top + (card.height - cue.height) / 2;
  if (seat === 3 || seat === 2) left = card.left + card.width + gap;
  else if (seat === 1) left = card.left - cue.width - gap;
  return {
    left: Math.max(bounds.left, Math.min(left, bounds.right - cue.width)),
    top: Math.max(bounds.top, Math.min(top, bounds.bottom - cue.height)),
  };
}
