// Scores are seat totals, never individual rewards when ownership changes.
export function renderScoreChart(points, names, seatWinds, onSelect = () => {}, doc = document) {
  const ns = 'http://www.w3.org/2000/svg';
  const chart = doc.createElement('figure');
  chart.className = 'session-chart'; chart.tabIndex = 0;
  chart.setAttribute('role', 'group');
  chart.setAttribute('aria-label', '四家累計分數走勢；左右方向鍵查看各局分數。');
  const colors = {E:'#efbd62', S:'#ed8690', W:'#76cbd8', N:'#b9a0e6'};
  const values = points.flatMap(point => point.totals);
  const low = Math.min(...values), high = Math.max(...values);
  const span = Math.max(high - low, 100);
  const bottom = low - (span - (high - low)) / 2;
  const y = value => 160 - (value - bottom) * 160 / span;
  const plot = doc.createElement('div'); plot.className = 'chart-plot';
  const svg = doc.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', '0 0 525 160');
  svg.setAttribute('preserveAspectRatio', 'none');
  svg.setAttribute('aria-hidden', 'true');
  const label = (className, text) => {
    const node = doc.createElement('span'); node.className = className;
    node.textContent = text; chart.append(node); return node;
  };
  label('chart-y-max', Math.round(bottom + span).toLocaleString());
  label('chart-y-min', Math.round(bottom).toLocaleString());
  if (1000 >= bottom && 1000 <= bottom + span) {
    const baseline = doc.createElementNS(ns, 'line');
    for (const [key, value] of Object.entries({x1:0, x2:525, y1:y(1000), y2:y(1000)})) {
      baseline.setAttribute(key, value);
    }
    baseline.setAttribute('class', 'chart-baseline'); svg.append(baseline);
    if (y(1000) > 14 && y(1000) < 146) {
      const caption = doc.createElement('span'); caption.className = 'chart-baseline-label';
      caption.textContent = '1,000'; caption.style.top = `${y(1000) / 160 * 100}%`;
      plot.append(caption);
    }
  }
  const lines = [];
  for (let pid = 0; pid < 4; pid++) {
    const line = doc.createElementNS(ns, 'polyline');
    line.setAttribute('class', 'chart-series');
    line.setAttribute('points', points.map((point, i) =>
      `${i * 525 / Math.max(1, points.length - 1)},${y(point.totals[pid])}`
    ).join(' '));
    line.setAttribute('fill', 'none'); line.setAttribute('stroke', colors[seatWinds[pid]]);
    line.setAttribute('stroke-width', '3');
    line.setAttribute('vector-effect', 'non-scaling-stroke');
    const title = doc.createElementNS(ns, 'title'); title.textContent = names[pid];
    line.append(title); svg.append(line); lines.push(line);
  }
  plot.append(svg); chart.append(plot);
  const ticks = doc.createElement('div'); ticks.className = 'chart-ticks';
  for (const index of new Set([0, Math.floor((points.length - 1) / 2), points.length - 1])) {
    const tick = doc.createElement('span');
    tick.textContent = String(points[index].round ?? index);
    tick.dataset.position = index / Math.max(1, points.length - 1);
    tick.className = index === 0 ? 'chart-tick-start' : index === points.length - 1 ? 'chart-tick-end' : '';
    tick.style.left = `${index / Math.max(1, points.length - 1) * 100}%`; ticks.append(tick);
  }
  chart.append(ticks);
  const activeTick = doc.createElement('span'); activeTick.className = 'chart-active-tick';
  activeTick.setAttribute('role','status'); ticks.append(activeTick);
  const guide = doc.createElement('span'); guide.className = 'chart-guide';
  guide.setAttribute('aria-hidden','true'); plot.append(guide);
  const markers = seatWinds.map(wind => {
    const marker = doc.createElement('span'); marker.className = 'chart-point';
    marker.style.backgroundColor = colors[wind]; marker.setAttribute('aria-hidden','true');
    plot.append(marker); return marker;
  });
  label('chart-axis-label', '局數');
  const play = () => {
    if (doc.defaultView?.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    for (const line of lines) {
      line.getAnimations().forEach(animation => animation.cancel());
      line.animate([{clipPath:'inset(-4px 100% -4px -4px)'},
        {clipPath:'inset(-4px -4px -4px -4px)'}], {duration:900, easing:'ease-out'});
    }
  };
  const replay = doc.createElement('button'); replay.className = 'chart-replay';
  replay.type = 'button'; replay.title = '重播分數曲線動畫';
  replay.setAttribute('aria-label', replay.title);
  replay.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 10a8 8 0 1 1 1 8M4 4v6h6"/></svg>';
  replay.onclick = play; chart.append(replay);
  play();
  let selected = -1, showingGuide = false;
  const select = (index, inspecting = true) => {
    const next = Math.max(0, Math.min(points.length - 1, index));
    if (next === selected && inspecting === showingGuide) return;
    const changed = next !== selected;
    selected = next; showingGuide = inspecting;
    const point = points[selected];
    const position = selected / Math.max(1, points.length - 1);
    const left = `${position * 100}%`;
    guide.style.left = left; guide.hidden = !inspecting;
    markers.forEach((marker, pid) => {
      marker.style.left = left; marker.style.top = `${y(point.totals[pid]) / 160 * 100}%`;
      marker.hidden = !inspecting;
    });
    activeTick.textContent = String(point.round ?? selected);
    activeTick.dataset.edge = selected === 0 ? 'start' : selected === points.length - 1 ? 'end' : '';
    activeTick.style.left = left;
    activeTick.style.transform = selected === 0 ? 'none' : selected === points.length - 1
      ? 'translateX(-100%)' : 'translateX(-50%)';
    activeTick.hidden = !inspecting;
    for (const tick of ticks.children) {
      if (tick !== activeTick) tick.hidden = inspecting && Math.abs(Number(tick.dataset.position) - position) < .06;
    }
    if (changed) onSelect(point);
  };
  const pick = event => {
    const bounds = plot.getBoundingClientRect();
    select(Math.round((event.clientX - bounds.left) / bounds.width * (points.length - 1)));
  };
  plot.onpointermove = pick; ticks.onpointermove = pick;
  chart.onpointerleave = () => select(points.length - 1, false);
  chart.onblur = () => select(points.length - 1, false);
  chart.onkeydown = event => {
    if (!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
    event.preventDefault();
    select(event.key === 'Home' ? 0 : event.key === 'End' ? points.length - 1
      : selected + (event.key === 'ArrowRight' ? 1 : -1));
  };
  select(points.length - 1, false);
  return chart;
}
