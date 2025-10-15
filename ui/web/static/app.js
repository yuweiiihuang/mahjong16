const statusEl = document.getElementById('status');
const lastActionEl = document.getElementById('last-action');
const actionMetaEl = document.getElementById('action-meta');
const actionButtonsEl = document.getElementById('action-buttons');
const summaryListEl = document.getElementById('summary-list');
const revealOverlay = document.getElementById('reveal-overlay');
const revealContent = document.getElementById('reveal-content');
const closeRevealBtn = document.getElementById('close-reveal');

const slotEls = {
  north: document.getElementById('slot-north'),
  south: document.getElementById('slot-south'),
  east: document.getElementById('slot-east'),
  west: document.getElementById('slot-west'),
};

const seatToSlot = { E: 'south', S: 'west', W: 'north', N: 'east' };
let currentSerial = null;
let revealDismissed = false;
let latestState = null;

const quanLabel = (code) => {
  if (!code) return '?';
  const key = String(code).toUpperCase();
  const mapping = { E: '東', S: '南', W: '西', N: '北' };
  return mapping[key] ?? key;
};

const tileSuit = (label) => {
  if (!label) return 'z';
  if (label === '##') return 'concealed';
  const last = label[label.length - 1];
  if ('mps'.includes(last)) return last;
  if ('ESWN'.includes(last)) return 'z';
  if ('1234567'.includes(last)) return 'z';
  return 'f';
};

function makeTile(label, { highlight = false } = {}) {
  const span = document.createElement('span');
  span.classList.add('tile');
  const suit = tileSuit(label);
  if (suit === 'concealed') {
    span.classList.add('concealed');
  } else {
    span.classList.add(`suit-${suit}`);
  }
  if (highlight) {
    span.classList.add('highlight');
  }
  span.dataset.label = label ?? '';
  return span;
}

function clearSlots() {
  Object.values(slotEls).forEach((slot) => {
    slot.innerHTML = '';
  });
}

function renderStatus(status = {}) {
  const totals = (status.totals || [])
    .map((value, idx) => `P${idx}:${value}`)
    .join(' · ');
  const deltas = (status.deltas || [])
    .map((value, idx) => `P${idx}:${value >= 0 ? '+' : ''}${value}`)
    .join(' · ');
  const last = status.last_action;

  statusEl.innerHTML = `
    <div class="status-block">
      <span class="status-label">圈風 / 莊家</span>
      <span class="status-value">${quanLabel(status.quan_feng)} · P${
        status.dealer_pid ?? '?'
      }</span>
    </div>
    <div class="status-block">
      <span class="status-label">輪到 / 阶段</span>
      <span class="status-value">P${status.turn ?? '?'} · ${status.phase ?? ''}</span>
    </div>
    <div class="status-block">
      <span class="status-label">剩餘牌 / 死牌區</span>
      <span class="status-value">${status.remaining ?? '?'} · Dead ${
        status.dead_wall ?? '?'
      }</span>
    </div>
    <div class="status-block">
      <span class="status-label">總分</span>
      <span class="status-value">${totals || '—'}</span>
    </div>
    <div class="status-block">
      <span class="status-label">本局增減</span>
      <span class="status-value">${deltas || '—'}</span>
    </div>
  `;

  if (last) {
    lastActionEl.innerHTML = `<strong>${last.who ?? ''}</strong> ${
      last.type ?? ''
    } ${last.detail ?? ''}`;
  } else {
    lastActionEl.textContent = '等待更新…';
  }
}

function renderPlayer(slot, player) {
  slot.innerHTML = '';
  const header = document.createElement('div');
  header.className = 'player-header';
  const name = document.createElement('div');
  name.className = 'player-name';
  name.textContent = `P${player.pid}`;
  const tags = document.createElement('div');
  tags.className = 'tags';
  if (player.is_self) {
    const tag = document.createElement('span');
    tag.className = 'tag';
    tag.textContent = 'YOU';
    tags.appendChild(tag);
  }
  if (player.seat) {
    const tag = document.createElement('span');
    tag.className = 'tag';
    tag.textContent = player.seat;
    tags.appendChild(tag);
  }
  if (player.is_dealer) {
    const tag = document.createElement('span');
    tag.className = 'tag';
    tag.textContent = '莊';
    tags.appendChild(tag);
  }
  if (player.declared_ting) {
    const tag = document.createElement('span');
    tag.className = 'tag';
    tag.textContent = '聽牌';
    tags.appendChild(tag);
  }
  header.appendChild(name);
  header.appendChild(tags);
  slot.appendChild(header);

  const sections = [
    {
      label: '手牌',
      render: () => {
        if (player.is_self) {
          const wrap = document.createElement('div');
          wrap.className = 'tiles hand';
          player.hand.forEach((tile) => {
            wrap.appendChild(makeTile(tile));
          });
          return wrap;
        }
        const text = document.createElement('div');
        text.textContent = `(${player.hand_count} 張)`;
        text.className = 'text-dim';
        return text;
      },
    },
    {
      label: '摸牌',
      render: () => {
        const wrap = document.createElement('div');
        wrap.className = 'tiles';
        if (player.is_self && player.drawn) {
          wrap.appendChild(makeTile(player.drawn));
        } else {
          wrap.textContent = player.is_self ? '無' : '隱藏';
        }
        return wrap;
      },
    },
    {
      label: '副露',
      render: () => {
        const wrap = document.createElement('div');
        wrap.className = 'tiles';
        if (!player.melds || player.melds.length === 0) {
          wrap.textContent = '—';
          return wrap;
        }
        player.melds.forEach((meld) => {
          const meldWrap = document.createElement('div');
          meldWrap.className = 'tiles';
          meld.tiles.forEach((tile) => {
            const el = makeTile(tile);
            if (tile === '##') {
              el.classList.add('concealed');
            }
            meldWrap.appendChild(el);
          });
          wrap.appendChild(meldWrap);
        });
        return wrap;
      },
    },
    {
      label: '河牌',
      render: () => {
        const wrap = document.createElement('div');
        wrap.className = 'tiles';
        if (!player.river || player.river.length === 0) {
          wrap.textContent = '—';
          return wrap;
        }
        player.river.forEach((tile, idx) => {
          wrap.appendChild(
            makeTile(tile, { highlight: idx === player.river_highlight })
          );
        });
        return wrap;
      },
    },
    {
      label: '花牌',
      render: () => {
        const wrap = document.createElement('div');
        wrap.className = 'tiles';
        if (!player.flowers || player.flowers.length === 0) {
          wrap.textContent = '—';
          return wrap;
        }
        player.flowers.forEach((tile) => wrap.appendChild(makeTile(tile)));
        return wrap;
      },
    },
  ];

  sections.forEach((section) => {
    const container = document.createElement('div');
    container.className = 'player-section';
    const label = document.createElement('div');
    label.className = 'section-label';
    label.textContent = section.label;
    container.appendChild(label);
    container.appendChild(section.render());
    slot.appendChild(container);
  });
}

function renderPlayers(players = []) {
  clearSlots();
  const used = new Set();
  const fallback = ['south', 'west', 'north', 'east'];
  players.forEach((player) => {
    const seat = player.seat ? String(player.seat).toUpperCase() : null;
    let slotName = seat && seatToSlot[seat];
    if (!slotName || used.has(slotName)) {
      slotName = fallback.find((name) => !used.has(name)) || 'south';
    }
    used.add(slotName);
    const slot = slotEls[slotName];
    if (slot) {
      renderPlayer(slot, player);
    }
  });
}

function renderActions(pending) {
  actionButtonsEl.innerHTML = '';
  if (!pending) {
    currentSerial = null;
    actionMetaEl.textContent = '等待其他玩家…';
    return;
  }
  currentSerial = pending.serial;
  actionMetaEl.textContent = `玩家 P${pending.player} · ${pending.phase} · 牌牆剩餘 ${pending.n_remaining}`;

  pending.actions.forEach((action) => {
    const btn = document.createElement('button');
    if (['PASS', 'HU'].includes(action.type)) {
      btn.classList.add('secondary');
    }
    btn.innerHTML = `<strong>${action.label}</strong>`;
    if (action.waits && action.waits.length > 0) {
      const waits = document.createElement('div');
      waits.className = 'waits';
      const text = action.waits
        .map((tile, idx) => {
          const remaining = action.waits_remaining?.[idx]?.remaining;
          return `${tile}${remaining !== undefined ? `(${remaining})` : ''}`;
        })
        .join(' · ');
      waits.textContent = `聽牌: ${text}`;
      btn.appendChild(waits);
    }
    btn.addEventListener('click', () => submitAction(action.id, btn));
    actionButtonsEl.appendChild(btn);
  });
}

async function submitAction(actionId, button) {
  if (currentSerial == null) return;
  if (button) {
    button.disabled = true;
  }
  try {
    const response = await fetch('/action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ serial: currentSerial, action_id: actionId }),
    });
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail);
    }
  } catch (err) {
    console.error('Failed to submit action', err);
  }
}

function renderSummaries(summaries = []) {
  summaryListEl.innerHTML = '';
  summaries.slice().reverse().forEach((summary) => {
    const card = document.createElement('div');
    card.className = 'summary-card';
    const meta = document.createElement('div');
    meta.className = 'meta';
    meta.innerHTML = `牌局 ${summary.hand_index} · 將 ${summary.jang_index ?? '-'} · 莊家 P${summary.dealer_pid ?? '?'}`;
    card.appendChild(meta);
    const winner = document.createElement('div');
    winner.className = 'winner';
    if (summary.winner != null) {
      winner.textContent = `胡牌: P${summary.winner} ${
        summary.win_source ?? ''
      } ${summary.win_tile ?? ''}`;
    } else {
      winner.textContent = '流局';
    }
    card.appendChild(winner);
    if (summary.payments) {
      const pay = document.createElement('div');
      pay.textContent = `得失: ${summary.payments.join(' / ')}`;
      card.appendChild(pay);
    }
    summaryListEl.appendChild(card);
  });
}

function renderReveal(reveal) {
  if (!reveal) {
    revealOverlay.hidden = true;
    revealDismissed = false;
    return;
  }
  if (revealDismissed) {
    return;
  }
  revealContent.innerHTML = '';
  reveal.players.forEach((player) => {
    const block = document.createElement('div');
    block.className = 'reveal-player';
    const header = document.createElement('h3');
    header.textContent = `P${player.pid} ${player.is_dealer ? '(莊)' : ''}`;
    block.appendChild(header);

    const meta = document.createElement('div');
    meta.className = 'reveal-meta';
    if (player.win_source) {
      meta.textContent = `${player.win_source} ${player.win_tile ?? ''}`;
      if (player.ron_from != null) {
        meta.textContent += ` from P${player.ron_from}`;
      }
    }
    block.appendChild(meta);

    const sections = [
      { label: '手牌', tiles: player.hand },
      { label: '副露', melds: player.melds },
      { label: '花牌', tiles: player.flowers },
      { label: '河牌', tiles: player.river },
    ];

    sections.forEach((section) => {
      const container = document.createElement('div');
      container.className = 'player-section';
      const label = document.createElement('div');
      label.className = 'section-label';
      label.textContent = section.label;
      container.appendChild(label);
      const wrap = document.createElement('div');
      wrap.className = 'tiles';
      if (section.tiles) {
        section.tiles.forEach((tile) => wrap.appendChild(makeTile(tile)));
      } else if (section.melds) {
        section.melds.forEach((meld) => {
          const meldWrap = document.createElement('div');
          meldWrap.className = 'tiles';
          meld.tiles.forEach((tile) => meldWrap.appendChild(makeTile(tile)));
          wrap.appendChild(meldWrap);
        });
      }
      container.appendChild(wrap);
      block.appendChild(container);
    });

    revealContent.appendChild(block);
  });

  revealOverlay.hidden = false;
}

closeRevealBtn.addEventListener('click', () => {
  revealDismissed = true;
  revealOverlay.hidden = true;
});

function renderState(state) {
  latestState = state;
  if (!state) return;
  renderStatus(state.status || {});
  renderPlayers(state.players || []);
  renderActions(state.pending_request);
  renderSummaries(state.hand_summaries || []);
  renderReveal(state.reveal);
}

function connectWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${protocol}://${window.location.host}/ws`);
  ws.onmessage = (event) => {
    const payload = JSON.parse(event.data);
    renderState(payload);
  };
  ws.onclose = () => {
    setTimeout(connectWebSocket, 1500);
  };
  ws.onerror = () => {
    ws.close();
  };
}

async function bootstrap() {
  try {
    const response = await fetch('/state');
    if (response.ok) {
      const data = await response.json();
      if (data) {
        renderState(data);
      }
    }
  } catch (err) {
    console.warn('Unable to fetch initial state', err);
  }
  connectWebSocket();
}

bootstrap();
