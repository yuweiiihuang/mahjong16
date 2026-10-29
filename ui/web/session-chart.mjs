// Scores are seat totals, never individual rewards when ownership changes.
export function renderScoreChart(points, names, doc = document) {
  const ns = 'http://www.w3.org/2000/svg';
  const svg = doc.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', '0 0 600 220');
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', '四家累計分數走勢；各局分數也列在下方紀錄。');
  svg.classList.add('session-chart');
  const colors = ['#176b53', '#ad5525', '#475cb4', '#97517e'];
  const values = points.flatMap(point => point.totals);
  const low = Math.min(...values), high = Math.max(...values);
  const span = Math.max(high - low, 100);
  const bottom = low - (span - (high - low)) / 2;
  const label = (x, y, text) => {
    const node = doc.createElementNS(ns, 'text');
    node.setAttribute('x', x); node.setAttribute('y', y);
    node.textContent = text; svg.append(node);
  };
  label(4, 18, String(bottom + span)); label(4, 180, String(bottom));
  label(52, 210, '開局'); label(470, 210, `完成 ${points.length - 1} 局`);
  for (let pid = 0; pid < 4; pid++) {
    const line = doc.createElementNS(ns, 'polyline');
    line.setAttribute('points', points.map((point, i) =>
      `${55 + i * 525 / Math.max(1, points.length - 1)},${180 - (point.totals[pid] - bottom) * 160 / span}`
    ).join(' '));
    line.setAttribute('fill', 'none'); line.setAttribute('stroke', colors[pid]);
    line.setAttribute('stroke-width', '2');
    line.setAttribute('stroke-dasharray', ['none', '8 3', '3 3', '10 3 2 3'][pid]);
    const title = doc.createElementNS(ns, 'title'); title.textContent = names[pid];
    line.append(title); svg.append(line);
  }
  return svg;
}
