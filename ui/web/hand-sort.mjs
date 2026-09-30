export const DEFAULT_ORDER = [0, 1, 2, 3];

export function validOrder(order) {
  return Array.isArray(order) && order.length === 4 &&
    DEFAULT_ORDER.every(group => order.includes(group));
}

export function sortHand(hand, order = DEFAULT_ORDER) {
  const groups = validOrder(order) ? order : DEFAULT_ORDER;
  return [...hand].sort((a, b) =>
    groups.indexOf(Math.min(3, Math.floor(a / 9))) -
    groups.indexOf(Math.min(3, Math.floor(b / 9))) || a - b);
}
