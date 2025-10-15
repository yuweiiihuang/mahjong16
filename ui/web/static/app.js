const stateUrl = "/api/state";
const actionUrl = "/api/action";
const startUrl = "/api/session/start";

const statusSummary = document.getElementById("status-summary");
const statusTurn = document.getElementById("status-turn");
const statusScore = document.getElementById("status-score");
const statusLastAction = document.getElementById("status-last-action");
const tableContainer = document.getElementById("table");
const promptContainer = document.getElementById("prompt-content");
const historyList = document.getElementById("history-list");
const startButton = document.getElementById("start-session");

let pollingHandle = null;
let lastVersion = null;
let submitting = false;

async function fetchState() {
  try {
    const res = await fetch(stateUrl, { cache: "no-cache" });
    if (!res.ok) {
      throw new Error(`state fetch failed: ${res.status}`);
    }
    const data = await res.json();
    if (data.version !== lastVersion) {
      lastVersion = data.version;
      renderState(data);
    }
  } catch (err) {
    console.error("state poll error", err);
  }
}

function renderState(state) {
  renderStatus(state.session, state.table);
  renderTable(state.table);
  renderPrompt(state.prompt, state.table);
  renderHistory(state.history || []);
}

function renderStatus(session, table) {
  if (!session) {
    statusSummary.textContent = "等待桌局啟動";
    statusTurn.textContent = "";
    statusScore.textContent = "";
    statusLastAction.textContent = "";
    return;
  }
  statusSummary.textContent = `狀態：${session.status || "?"}｜完成局數：${session.completed_hands || 0}`;
  if (session.error) {
    statusSummary.textContent += `｜錯誤：${session.error}`;
  }

  if (!table) {
    statusTurn.textContent = "等待桌面資訊";
    statusScore.textContent = "";
    statusLastAction.textContent = "";
    return;
  }

  const qf = table.quan_feng ?? "?";
  const dealer = table.dealer_pid ?? "?";
  const turn = table.turn ?? "?";
  const phase = table.phase ?? "?";
  const remaining = table.wall_remaining ?? "?";
  const reserved = table.dead_wall_reserved ?? "?";

  statusTurn.textContent = `圈風：${qf} ｜ 莊家：P${dealer} ｜ 回合：P${turn} ｜ 階段：${phase} ｜ 牌牆剩餘：${remaining}｜死牌堆：${reserved}`;

  if (Array.isArray(table.score_totals) && table.score_totals.length) {
    const totals = table.score_totals
      .map((v, idx) => `P${idx}=${v}`)
      .join("  ");
    statusScore.textContent = `總點數：${totals}`;
  } else {
    statusScore.textContent = "";
  }

  if (table.last_action) {
    statusLastAction.textContent = `${table.last_action.who || "?"} ${table.last_action.type || ""} ${
      table.last_action.detail || ""
    }`;
  } else {
    statusLastAction.textContent = "最近動作：無";
  }
}

function renderTable(table) {
  tableContainer.innerHTML = "";
  if (!table || !Array.isArray(table.players)) {
    return;
  }
  table.players.forEach((player) => {
    const card = document.createElement("article");
    card.className = "player-card";

    const header = document.createElement("div");
    header.className = "player-header";

    const label = document.createElement("div");
    label.className = "label";
    const seatTag = player.seat ? ` [${player.seat}]` : "";
    label.textContent = `P${player.pid}${seatTag}${player.is_self ? " (你)" : ""}`;
    header.appendChild(label);

    const badges = document.createElement("div");
    badges.className = "badges";
    if (player.is_dealer) {
      const badge = document.createElement("span");
      badge.className = "badge dealer";
      badge.textContent = "莊";
      badges.appendChild(badge);
    }
    if (player.declared_ting) {
      const badge = document.createElement("span");
      badge.className = "badge ting";
      badge.textContent = "TING";
      badges.appendChild(badge);
    }
    header.appendChild(badges);
    card.appendChild(header);

    const handSection = document.createElement("div");
    handSection.className = "section";
    const handLabel = document.createElement("div");
    handLabel.className = "section-label";
    handLabel.textContent = "手牌";
    handSection.appendChild(handLabel);

    if (player.is_self) {
      handSection.appendChild(renderTiles(player.hand));
      if (player.drawn) {
        const drawnLine = document.createElement("div");
        drawnLine.className = "section-label";
        drawnLine.textContent = `摸牌：${player.drawn.label}`;
        handSection.appendChild(drawnLine);
      }
    } else {
      const text = document.createElement("p");
      text.className = "empty";
      text.textContent = `(${player.hand_size || 0} 張)`;
      handSection.appendChild(text);
    }
    card.appendChild(handSection);

    const meldSection = document.createElement("div");
    meldSection.className = "section";
    const meldLabel = document.createElement("div");
    meldLabel.className = "section-label";
    meldLabel.textContent = "副露";
    meldSection.appendChild(meldLabel);
    if (player.melds && player.melds.length) {
      const list = document.createElement("div");
      list.className = "melds";
      player.melds.forEach((meld) => {
        const row = document.createElement("div");
        row.className = "meld";
        const tag = document.createElement("span");
        tag.className = "badge";
        tag.textContent = meld.type || "?";
        row.appendChild(tag);
        row.appendChild(renderTiles(meld.tiles));
        list.appendChild(row);
      });
      meldSection.appendChild(list);
    } else {
      const empty = document.createElement("p");
      empty.className = "empty";
      empty.textContent = "(無)";
      meldSection.appendChild(empty);
    }
    card.appendChild(meldSection);

    const flowerSection = document.createElement("div");
    flowerSection.className = "section";
    const flowerLabel = document.createElement("div");
    flowerLabel.className = "section-label";
    flowerLabel.textContent = "花牌";
    flowerSection.appendChild(flowerLabel);
    if (player.flowers && player.flowers.length) {
      flowerSection.appendChild(renderTiles(player.flowers));
    } else {
      const empty = document.createElement("p");
      empty.className = "empty";
      empty.textContent = "(無)";
      flowerSection.appendChild(empty);
    }
    card.appendChild(flowerSection);

    const discardsSection = document.createElement("div");
    discardsSection.className = "section";
    const discardsLabel = document.createElement("div");
    discardsLabel.className = "section-label";
    discardsLabel.textContent = "棄牌";
    discardsSection.appendChild(discardsLabel);
    if (player.discards && player.discards.length) {
      discardsSection.appendChild(renderTiles(player.discards));
    } else {
      const empty = document.createElement("p");
      empty.className = "empty";
      empty.textContent = "(無)";
      discardsSection.appendChild(empty);
    }
    card.appendChild(discardsSection);

    tableContainer.appendChild(card);
  });
}

function renderTiles(tiles) {
  const wrapper = document.createElement("div");
  wrapper.className = "tiles";
  tiles.forEach((tile) => {
    const span = document.createElement("span");
    span.className = "tile";
    span.textContent = tile.label || tile;
    if (tile.highlight) {
      span.classList.add("highlight");
    }
    wrapper.appendChild(span);
  });
  return wrapper;
}

function renderPrompt(prompt, table) {
  promptContainer.innerHTML = "";
  if (!prompt) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "目前沒有需要操作的行動";
    promptContainer.appendChild(empty);
    return;
  }

  const phase = document.createElement("p");
  phase.textContent = `玩家 P${prompt.player} ｜ 階段：${prompt.phase}`;
  promptContainer.appendChild(phase);

  if (prompt.phase === "TURN") {
    if (prompt.current_waits && prompt.current_waits.length) {
      const ting = document.createElement("p");
      ting.innerHTML = `<strong>目前聽牌：</strong> ${prompt.current_waits
        .map((w) => `${w.label}(${w.remaining})`)
        .join("  ")}`;
      promptContainer.appendChild(ting);
    }

    const discardBlock = document.createElement("div");
    discardBlock.className = "section";
    const label = document.createElement("div");
    label.className = "section-label";
    label.textContent = "丟牌候選與聽牌";
    discardBlock.appendChild(label);
    const list = document.createElement("div");
    list.className = "melds";
    (prompt.discard_options || []).forEach((option) => {
      const row = document.createElement("div");
      row.className = "history-item";
      row.innerHTML = `<span>丟 ${option.label}</span><span class="detail">${
        option.waits && option.waits.length
          ? option.waits.map((w) => `${w.label}(${w.remaining})`).join("  ")
          : ""
      }</span>`;
      list.appendChild(row);
    });
    discardBlock.appendChild(list);
    promptContainer.appendChild(discardBlock);
  }

  const actions = document.createElement("div");
  actions.className = "prompt-actions";
  (prompt.actions || []).forEach((action) => {
    const btn = document.createElement("button");
    btn.textContent = action.label || action.type;
    btn.dataset.actionId = action.id;
    btn.dataset.promptId = prompt.id;
    if (action.type === "DISCARD") {
      btn.classList.add("discard");
    }
    if (action.type === "HU") {
      btn.classList.add("hu");
    }
    btn.addEventListener("click", () => {
      if (!submitting) {
        submitAction(prompt.id, action.id);
      }
    });
    actions.appendChild(btn);
  });
  promptContainer.appendChild(actions);
}

function renderHistory(items) {
  historyList.innerHTML = "";
  items.slice(0, 10).forEach((item) => {
    const li = document.createElement("li");
    li.className = "history-item";
    const ts = new Date(item.timestamp * 1000).toLocaleTimeString();
    const detail = item.detail ? `<span class="detail">${item.detail}</span>` : "";
    li.innerHTML = `<span>${ts}</span><span>${item.event || ""} ${detail}</span>`;
    historyList.appendChild(li);
  });
}

async function submitAction(promptId, actionId) {
  submitting = true;
  try {
    const res = await fetch(actionUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt_id: promptId, action_id: actionId }),
    });
    if (!res.ok) {
      const text = await res.text();
      console.error("action rejected", text);
      alert(`動作失敗：${text}`);
    }
  } catch (err) {
    console.error("submit error", err);
    alert("送出動作失敗，請查看主控台。");
  } finally {
    submitting = false;
  }
}

async function startSession() {
  try {
    const res = await fetch(startUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    if (!res.ok) {
      const text = await res.text();
      alert(`啟動失敗：${text}`);
    }
  } catch (err) {
    console.error("start session error", err);
  }
}

startButton.addEventListener("click", () => {
  startSession();
});

pollingHandle = setInterval(fetchState, 900);
fetchState();
