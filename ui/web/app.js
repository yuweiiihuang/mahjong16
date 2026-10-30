import Sortable from './vendor/sortable.core.esm.js';
import { DEFAULT_ORDER, validOrder, sortHand } from './hand-sort.mjs';
import { TILE_FONTS, DEFAULT_TILE_FONT, validTileFont, tileAsset } from './tile-fonts.mjs?v=imahjong-full-4';
import { loadTileImage } from './tile-images.mjs';
import { randomPlayerName } from './player-names.mjs?v=selected-names-8';
import { renderScoreChart } from './session-chart.mjs?v=session-reveal-1';
import { meldCuePosition } from './meld-cue.mjs?v=right-top-1';

const $ = id => document.getElementById(id);
function syncControlsSide() {
  // Safari's legacy value preserves the physical rotation direction on iPhone.
  const angle=typeof window.orientation==='number'?window.orientation:
    window.screen?.orientation?.angle;
  document.documentElement.dataset.controlsSide=
    ((angle%360)+360)%360===270?'left':'right';
}
syncControlsSide();
const updateControlsSide=()=>{syncControlsSide();tableView?.resize();};
window.addEventListener('orientationchange',updateControlsSide);
window.addEventListener('resize',updateControlsSide);
window.screen?.orientation?.addEventListener('change',updateControlsSide);

let playerName = localStorage.getItem('qinghe-player-name') || '';
let names = [playerName || '玩家', '陳予安', '林小滿', '周子墨'];
const winds = ['東', '南', '西', '北'];
const labels = {DISCARD:'出牌', TING:'聽', HU:'胡', PASS:'過', CHI:'吃', PONG:'碰', GANG:'槓', ANGANG:'暗槓', KAKAN:'加槓', DRAW_GAME:'流局'};
let replay = null;
function displayedState() { return replay ? replay.frames[replay.index].state : state; }
let state, selected = null, busy = false, playbackFrame = null, tingMode = false;
let tingPassed = false;
let autoTingDiscard = localStorage.getItem('qinghe-auto-ting-discard') !== 'false';
let chiMode = localStorage.getItem('qinghe-chi-mode') === 'tiles' ? 'tiles' : 'groups';
let chiSelection = null;
let pendingReaction = null;
let sound = localStorage.getItem('qinghe-sound') === 'true';
let pace = ['fast','natural','relaxed'].includes(localStorage.getItem('qinghe-pace'))
  ? localStorage.getItem('qinghe-pace') : 'natural';
let compact = localStorage.getItem('qinghe-flat') === 'true';
const savedTileFont = localStorage.getItem('qinghe-tile-font');
let tileFont = validTileFont(savedTileFont) ? savedTileFont : DEFAULT_TILE_FONT;
let sortOrder = [...DEFAULT_ORDER];
try {
  const saved = JSON.parse(localStorage.getItem('qinghe-sort-order'));
  if (validOrder(saved)) sortOrder = saved;
} catch {} // Ignore invalid saved preferences and use the default order.
let audio, tableView;
let roomMode = false, pollGeneration = 0;
document.addEventListener('contextmenu', event => {
  if (event.target.closest('.tile-hit,.tile,.table-canvas,.sort-group')) event.preventDefault();
});
document.body.classList.toggle('compact', compact);
function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, char => ({
    '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;',
  }[char]));
}
function tileName(id) {
  if (id < 27) return `${id % 9 + 1}${['萬','筒','條'][Math.floor(id/9)]}`;
  return ['東','南','西','北','中','發','白','春','夏','秋','冬','梅','蘭','竹','菊'][id - 27];
}
function selectHandTile(action) {
  if (replay || busy || state.blocked_discards?.includes(action.tile)) return;
  if (chiSelection?.mode === 'tiles') {
    if (!canPickChi(action)) return;
    const picked = chiSelection.picked;
    const index = picked.findIndex(p => p.index === action.index);
    if (index >= 0) picked.splice(index, 1);
    else picked.push({tile:action.tile, index:action.index});
    renderActions(); renderHand();
    return;
  }
  if (tingMode) {
    const ting = state.legal_actions.find(candidate => candidate.type === 'TING'
      && candidate.tile === action.tile && candidate.from === action.from);
    if (ting) perform(ting);
    return;
  }
  if (selected?.tile === action.tile && selected?.from === action.from &&
      selected?.index === action.index) {
    perform(action);
    return;
  }
  selected = action;
  renderHand();
  renderActions();
}
function setTileFace(face, id, font) {
  const url = tileAsset(id,font);
  face.dataset.source = url;
  face.hidden = true;
  face.removeAttribute('src');
  const tile = face.parentElement;
  tile.title = tileName(id);
  tile.dataset.faceStatus = 'loading';
  tile.dataset.faceText = '載入中';
  loadTileImage(url).then(image => {
    if (face.dataset.source !== url) return;
    face.src = image.src;
    face.hidden = false;
    delete tile.dataset.faceStatus;
  }).catch(() => {
    if (face.dataset.source !== url || !face.isConnected) return;
    tile.dataset.faceStatus = 'error';
    tile.dataset.faceText = tileName(id);
    tile.title = `${tileName(id)}：載入失敗，請重新選擇牌面重試`;
    if ($('modal').open) toast('部分牌面載入失敗，請重新選擇牌面重試');
  });
}
function tile(id, small = false, action = null, font = tileFont) {
  const el = document.createElement(action ? 'button' : 'span');
  el.className = `tile${small?' small flat':''}${id===31?' red':''}${id===32?' green':''}`;
  el.setAttribute('aria-label',tileName(id));
  el.title = tileName(id);
  const face = document.createElement('img');
  face.className = 'tile-face';
  face.dataset.tileId = id;
  face.alt = '';
  face.draggable = false;
  el.append(face);
  setTileFace(face,id,font);
  if(action){
    el.disabled=busy;
    el.setAttribute('aria-pressed', String(selected?.tile===id && selected?.from===action.from));
    if(selected?.tile===id && selected?.from===action.from) el.classList.add('selected');
    el.onclick=()=>selectHandTile(action);
  }
  return el;
}
function person(pid) {
  const state = displayedState();
  const wrap = document.createElement('div');
  wrap.className = 'seat-person';
  const name = escapeHtml(names[pid]);
  const bot = replay ? state.replay_humans?.[pid] === false
    : state.room ? !state.room.members[pid].human : pid !== 0;
  wrap.innerHTML = `<div class="avatar-wrap"><div class="avatar a${pid}">${escapeHtml(Array.from(names[pid])[0])}</div>${bot ? '<span class="bot-status" role="img" aria-label="電腦玩家"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="7" width="16" height="13" rx="3"/><path d="M12 3v4M1 12v5M23 12v5M8 12v3M16 12v3M8 18h8"/></svg></span>' : ''}</div><div class="player-info"><strong><span class="player-name" title="${name}">${name}</span></strong><small>${state.totals[pid]} 點</small><span class="player-badges">${state.dealer === pid ? `<span class="dealer" aria-label="莊家${state.dealer_streak ? `，連莊 ${state.dealer_streak}` : '，起莊'}">莊</span>` : ''}${state.players[pid].ting ? '<span class="ting-status" aria-label="已宣告聽牌">聽</span>' : ''}</span></div>`;
  if (pid === 0 && !replay) {
    const avatar = wrap.querySelector('.avatar');
    const button = document.createElement('button');
    button.type = 'button'; button.className = `${avatar.className} avatar-edit`;
    button.textContent = avatar.textContent;
    button.setAttribute('aria-label', '修改我的顯示名稱');
    button.title = '修改顯示名稱'; button.onclick = showRename;
    avatar.replaceWith(button);
  }
  return wrap;
}
function melds(pid, target, small = true) {
  for(const meld of state.players[pid].melds){
    const group=document.createElement('div');group.className='meld-group';group.title=labels[meld.type]||meld.type;
    for(const id of meld.tiles) group.append(tile(id,small));target.append(group);
  }
}
function renderHand() {
  const state = displayedState();
  if (tableView && state) tableView.update(state, chiSelection?.mode === 'tiles'
    ? {chiCards:chiSelection.picked} : tingMode
    ? {tingCandidates:state.legal_actions.filter(action => action.type === 'TING')}
    : selected, sortOrder);
}
function syncProjection(view) {
  const state = displayedState();
  if (!state) return;
  $('hand').setAttribute('aria-label', `手牌：${state ? sortHand(state.hand, sortOrder).map(tileName).join('、') : ''}`);
  const hand = $('hand');
  const existing = new Map([...hand.children].map(button => [button.dataset.slot, button]));
  const boxes = view.hitBoxes();
  boxes.forEach((box, position) => {
    const slot = `${box.action.from}:${box.index ?? 'drawn'}:${box.id}`;
    const action = {...box.action, index:box.index};
    const button = existing.get(slot) || tile(box.id, false, action);
    existing.delete(slot);
    button.replaceChildren(); // Hit targets have no artwork; the 3D face is the only visible image.
    button.dataset.slot = slot;
    button.classList.add('tile-hit');
    button.disabled = Boolean(replay) || busy || box.blocked || (chiSelection?.mode === 'tiles' && !canPickChi(action))
      || (tingMode && !state.legal_actions.some(candidate =>
      candidate.type === 'TING' && candidate.tile === action.tile && candidate.from === action.from));
    button.setAttribute('aria-pressed', String(box.selected));
    button.title = box.blocked ? '剛吃進的同牌種，本次不能打出' : '';
    button.setAttribute('aria-label', `${tileName(box.id)}${box.blocked ? '，本次不能打出' : ''}`);
    button.onclick = () => selectHandTile(action);
    button.style.cssText = `left:${box.left}px;top:${box.top}px;width:${box.width}px;height:${box.height}px`;
    if (hand.children[position] !== button) hand.insertBefore(button, hand.children[position] || null);
  });
  for (const button of existing.values()) button.remove();
  const actionBar = document.querySelector('.action-bar');
  const actionY = view.project([0,.5,9.4]).y;
  document.querySelector('.my-heading').style.bottom =
    `${view.height-view.project([0,1.475,10.9]).y+16}px`;
  actionBar.style.top = `${actionY}px`;
  $('ting-panel').style.top = `${actionY}px`;
  $('ting-panel').style.setProperty('--ting-max-height',
    `${Math.max(0, (actionY-(view.safeFrame?view.safeFrame.top+38:12))/(view.zoom || 1))}px`);
  const panel = $('ting-panel');
  actionBar.style.right = panel.hidden ? '' :
    `${parseFloat(getComputedStyle(panel).right)+panel.offsetWidth*(view.zoom || 1)+12}px`;
  const positions = {2:[0,2.5,-10.3],3:[-12.2,2.2,-3.1],1:[12.2,2.2,-3.1]};
  const order = state.seating_order;
  for (const pid of [1,2,3]) {
    const seat = (order.indexOf(pid) - order.indexOf(0) + 4) % 4;
    const p=view.project(positions[seat]); const el=$(`seat-${pid}`);
    const halfWidth=el.offsetWidth*(view.zoom || 1)/2;
    const halfHeight=el.offsetHeight*(view.zoom || 1)/2;
    const frame=view.safeFrame;
    const controlsLeft=document.documentElement.dataset.controlsSide==='left';
    el.style.left=`${frame?Math.max(frame.left+(controlsLeft?52:0)+halfWidth,
      Math.min(p.x,frame.right-(controlsLeft?0:52)-halfWidth)):p.x}px`;
    el.style.top=`${frame?Math.max(frame.top+halfHeight,
      Math.min(p.y,frame.bottom-halfHeight)):Math.max(p.y,halfHeight+8)}px`;
  }
  positionMeldCue();
}
let meldCueTimer;
function positionMeldCue() {
  const state = displayedState();
  const cue = $('meld-cue');
  if (cue.hidden) return;
  const pid = Number(cue.dataset.pid);
  const anchor = $(`seat-${pid}`);
  const table = document.querySelector('.table').getBoundingClientRect();
  const card = anchor.getBoundingClientRect();
  const seat = (state.seating_order.indexOf(pid) - state.seating_order.indexOf(0) + 4) % 4;
  const frame = tableView?.safeFrame;
  const position = meldCuePosition(
    {left:card.left-table.left, top:card.top-table.top, width:card.width, height:card.height},
    {width:cue.offsetWidth, height:cue.offsetHeight},
    frame || {left:8, top:8, right:table.width-8, bottom:table.height-8}, seat);
  cue.style.left = `${position.left}px`;
  cue.style.top = `${position.top}px`;
}
function showMeldCue(event) {
  const state = displayedState();
  if (state.done && state.winner != null) event = {pid:state.winner,type:'HU'};
  if (event.pid === 0 || !['CHI','PONG','GANG','ANGANG','KAKAN','HU'].includes(event.type)) return;
  const cue = $('meld-cue');
  clearTimeout(meldCueTimer);
  cue.dataset.pid = event.pid;
  cue.dataset.action = event.type;
  cue.dataset.hand = `${state.session_id || state.room?.code || ''}:${state.round}`;
  const label = event.type === 'HU' && state.win_source === 'TSUMO' ? '自摸' : labels[event.type];
  cue.textContent = label;
  cue.setAttribute('aria-label', `${names[event.pid]} ${label}`);
  cue.hidden = false;
  positionMeldCue();
  meldCueTimer = setTimeout(() => { cue.hidden = true; }, 1800);
}
$('ting-panel').ontoggle = () => { if (tableView) syncProjection(tableView); };
function actionButton(text, action, primary=false) {
  const button=document.createElement('button');button.textContent=text;
  button.className=primary?'primary':'';button.disabled=busy;
  if (action) button.dataset.action = action.type;
  button.onclick=()=>perform(action);return button;
}
function canPickChi(action) {
  const picked = chiSelection.picked;
  return picked.some(p => p.index === action.index) || (picked.length < 2
    && !picked.some(p => p.tile === action.tile)
    && chiSelection.options.some(option => option.use.includes(action.tile)
      && picked.every(p => option.use.includes(p.tile))));
}
function renderChiSelection(target) {
  const panel = document.createElement('div'); panel.className = 'chi-picker';
  panel.setAttribute('role', 'group'); panel.setAttribute('aria-label', '選擇吃牌組合');
  if (chiSelection.mode === 'groups') {
    for (const option of chiSelection.options) {
      const pick = actionButton('', option); pick.className = 'chi-group';
      delete pick.dataset.action;
      const sequence = [...option.use, state.last_discard.tile].sort((a,b) => a-b);
      pick.setAttribute('aria-label', `吃 ${sequence.map(tileName).join('、')}`);
      for (const id of sequence) {
        const face = tile(id, true);
        if (id === state.last_discard.tile) face.classList.add('chi-discard');
        pick.append(face);
      }
      panel.append(pick);
    }
  } else {
    const preview = document.createElement('div'); preview.className = 'chi-preview';
    const discard = tile(state.last_discard.tile, true); discard.classList.add('chi-discard');
    preview.append(discard);
    for (let i=0; i<2; i++) {
      const picked = chiSelection.picked[i];
      const face = picked ? tile(picked.tile, true) : document.createElement('span');
      if (!picked) { face.className = 'chi-empty'; face.textContent = '＋'; }
      preview.append(face);
    }
    panel.append(preview);
    const option = chiSelection.options.find(o => chiSelection.picked.length === 2
      && chiSelection.picked.every(p => o.use.includes(p.tile)));
    const confirm = actionButton('確認', option); confirm.className = 'chi-confirm';
    delete confirm.dataset.action;
    confirm.disabled = busy || !option; panel.append(confirm);
  }
  const cancel = actionButton('取消', null); cancel.className = 'chi-cancel';
  cancel.onclick = () => { chiSelection = null; renderActions(); renderHand(); };
  panel.append(cancel); target.append(panel);
}
function renderReactionActions(target, actions, choice = null) {
  if (!actions.some(action => action.type !== 'PASS')) return;
  target.dataset.submitted = String(Boolean(choice));
  for (const type of ['CHI', 'PONG', 'GANG', 'HU', 'PASS']) {
    const options = actions.filter(action => action.type === type);
    if (!options.length) continue;
    const button = actionButton(labels[type], options[0], type !== 'PASS');
    if (choice) {
      button.disabled = true;
      button.setAttribute('aria-pressed', String(type === choice.type));
      if (type === choice.type) button.title = '已選擇，等待裁決';
    } else if (options.length > 1) {
      button.onclick = () => {
        chiSelection = {mode:chiMode, options, picked:[],
          key:JSON.stringify([state.room?.code, state.round, state.last_discard, state.rivers])};
        renderActions(); renderHand();
      };
    }
    target.append(button);
  }
}
function renderActions(){
  $('actions').hidden = Boolean(replay);
  $('replay-controls').hidden = !replay;
  if (replay) { renderReplayControls(); return; }
  const target=$('actions');target.replaceChildren();
  if (!state.legal_actions.some(action => action.type === 'TING')) tingPassed = false;
  delete target.dataset.submitted;
  if (chiSelection && (state.phase !== 'REACTION' || state.reaction_choice
      || JSON.stringify([state.room?.code, state.round, state.last_discard, state.rivers]) !== chiSelection.key
      || !state.legal_actions.some(a => a.type === 'CHI'))) chiSelection = null;
  if (chiSelection && !playbackFrame) { renderChiSelection(target); return; }
  if (playbackFrame) {
    return;
  }
  if (state.room && !state.room.started) {
    if (state.room.host) {
      const start = actionButton('開始對局', null, true);
      start.onclick = () => roomCommand('/api/room/start'); target.append(start);
    }
    return;
  }
  if (state.room && state.done && !state.room.host) {
    const result = actionButton('結算明細', null); result.onclick = () => showResult();
    target.append(result); return;
  }
  if (state.phase === 'REACTION' && (state.reaction_choice || pendingReaction)) {
    renderReactionActions(target, state.reaction_choice ? state.reaction_actions : state.legal_actions,
      state.reaction_choice || pendingReaction);
    return;
  }
  if (state.room && !state.done && !state.legal_actions.length) {
    return;
  }
  if(state.done){const b=actionButton('下一局',null,true);b.onclick=()=>newGame(true);target.append(b);const result=actionButton('結算明細',null);result.onclick=()=>showResult();target.append(result);return;}
  if(state.phase==='TURN'){
    for(const a of state.legal_actions.filter(a=>!['DISCARD','TING'].includes(a.type))) target.append(actionButton(a.type==='HU'&&a.source==='TSUMO'?'自摸':labels[a.type],a,true));
    if (!tingPassed && state.legal_actions.some(action => action.type === 'TING')) {
      const ting = actionButton('聽', {type:'TING'});
      ting.setAttribute('aria-pressed', String(tingMode));
      ting.onclick = () => {
        if (busy) return;
        const candidates = state.legal_actions.filter(action => action.type === 'TING');
        const declaration = (selected && candidates.find(action =>
          action.tile === selected.tile && action.from === selected.from))
          || (candidates.every(action => action.tile === candidates[0].tile) && candidates[0]);
        if (declaration) { perform(declaration); return; }
        tingMode = !tingMode; selected = null; renderActions(); renderHand();
      };
      target.append(ting);
      const pass = actionButton('過', null);
      pass.dataset.action = 'PASS';
      pass.onclick = () => {
        tingPassed = true; tingMode = false; selected = null; renderActions(); renderHand();
      };
      target.append(pass);
    }
  } else {
    renderReactionActions(target, state.legal_actions);
  }
}
function uniqueTingOptions(options) {
  const seen = new Set();
  return options.filter(option => {
    const waits = option.waits.map(wait => `${wait.tile}:${wait.unseen}`).sort().join(',');
    const key = `${option.tile ?? ''}|${waits}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).map(option => ({...option, waits:[...option.waits].sort((a,b)=>a.tile-b.tile)}))
    .sort((a,b)=>(a.tile ?? -1)-(b.tile ?? -1));
}
function renderTing() {
  const state = displayedState();
  const target = $('ting-panel');
  target.replaceChildren();
  const options = uniqueTingOptions(state.ting_options.length
    ? state.ting_options : state.ting_waits.length ? [{waits:state.ting_waits}] : []);
  target.hidden = Boolean(replay) || !options.length || state.done || Boolean(state.room && !state.room.started);
  if (target.hidden) return;
  const header = document.createElement('summary'); header.className = 'ting-heading';
  const label = document.createElement('span'); label.textContent = '聽牌提示';
  header.title = '數字是未見牌數，包含對手手牌及尾牌，不代表牌牆可摸張數。';
  header.append(label); target.append(header);
  const body = document.createElement('div'); body.className = 'ting-body';
  body.tabIndex = 0; body.setAttribute('role', 'region');
  body.setAttribute('aria-label', '聽牌選項'); target.append(body);
  for (const option of options) {
    const row = document.createElement('div'); row.className = 'ting-row';
    if (option.tile !== undefined) {
      row.append(tile(option.tile, true));
      const arrow = document.createElement('span'); arrow.className = 'ting-arrow';
      arrow.textContent = '→'; row.append(arrow);
    }
    const waits = document.createElement('div'); waits.className = 'wait-tiles';
    for (const wait of option.waits) {
      const item = document.createElement('span'); item.className = 'wait-tile';
      const count = document.createElement('small'); count.textContent = wait.unseen;
      item.setAttribute('aria-label', `${tileName(wait.tile)}，未見 ${wait.unseen} 張`);
      item.append(tile(wait.tile, true), count); waits.append(item);
    }
    row.append(waits); body.append(row);
  }
}
function render(){
  const state = displayedState();
  const cue = $('meld-cue');
  if (cue.dataset.hand !== `${state.session_id || state.room?.code || ''}:${state.round}`) {
    cue.hidden = true;
    clearTimeout(meldCueTimer);
  }
  if (state.done || playbackFrame || !state.legal_actions.some(a => a.type === 'TING')) tingMode = false;
  const waiting = state.room && !state.room.started;
  const humans = waiting ? state.room.members.filter(member => member.human).length : 0;
  setTableStatus(waiting ? `等待開局 · 已有 ${humans} 位玩家\n${state.room.host
    ? '邀請朋友加入後，按「開始對局」。空位由電腦補上。' : '等待房主開始對局。'}` : '');
  names = replay ? state.replay_names : state.room ? state.room.members.map(member => member.name)
    : [state.player_name || playerName || '玩家', '陳予安', '林小滿', '周子墨'];
  if (!replay) rememberPlayerName(names[0]);
  $('connection-status').textContent = replay ? '牌局重播 · 唯讀' : state.room ? `房間 ${state.room.code}` : '';
  $('connection-status').parentElement.hidden = !replay && !state.room;
  $('new-game').textContent = state.room ? '離開房間' : '↻　重新開桌';
  $('new-game').disabled = Boolean(replay) || busy || (!state.room && !state.done);
  $('new-game').title = state.room || state.done ? '' : '胡牌或流局後才能開新 Session';
  $('remaining').textContent=state.remaining;
  $('round').textContent=`第 ${state.round} 局`;
  $('round-wind').textContent=`${winds[['E','S','W','N'].indexOf(state.quan_feng)]}風圈`;
  $('jang').textContent = Number.isInteger(state.jang_count) ? `第 ${state.jang_count + 1} 將` : '將數未記錄';
  const order = state.seating_order, ownSeat = order.indexOf(0);
  ['.wind-bottom','.wind-right','.wind-top','.wind-left'].forEach((selector, seat) => {
    const pid = order[(ownSeat + seat) % 4];
    const el = document.querySelector(selector);
    el.textContent = winds[['E','S','W','N'].indexOf(state.seat_winds[pid])];
    el.classList.toggle('active', !state.done && state.phase !== 'REACTION' && pid === state.actor);
  });
  document.querySelector('.compass').setAttribute('aria-label',
    state.room && !state.room.started ? '等待朋友入座' :
      `${$('round-wind').textContent}；剩餘 ${state.remaining} 張；${state.done ? '本局結束' : state.phase === 'REACTION' || state.actor === null ? '等待回應' : `輪到${winds[['E','S','W','N'].indexOf(state.seat_winds[state.actor])]}家`}`);
  for (const pid of [1,2,3]) $(`seat-${pid}`).replaceChildren(person(pid));
  $('me').replaceChildren(person(0));
  $('flowers').replaceChildren();
  if(state.flowers.length){const label=document.createElement('small');label.textContent='花牌';$('flowers').append(label);for(const id of state.flowers)$('flowers').append(tile(id,true));}
  renderActions();renderTing();renderHand();

}
function beep(){
  if(!sound)return;
  try{audio??=new AudioContext();audio.resume();const o=audio.createOscillator(),g=audio.createGain();o.type='sine';o.frequency.setValueAtTime(660,audio.currentTime);g.gain.setValueAtTime(.05,audio.currentTime);g.gain.exponentialRampToValueAtTime(.001,audio.currentTime+.12);o.connect(g);g.connect(audio.destination);o.start();o.stop(audio.currentTime+.12);}catch{}
}
let toastTimer;
function toast(message) {
  if ($('modal').open && $('modal-status')) {
    $('modal-status').textContent = message;
    $('modal-status').hidden = false;
    return;
  }
  clearTimeout(toastTimer);
  $('toast').textContent=message;
  $('toast').classList.add('visible');
  toastTimer=setTimeout(()=>$('toast').classList.remove('visible'),3500);
}
function setTableStatus(message) {
  $('table-status').textContent = message;
  $('table-status').hidden = !message;
}
async function request(path,body){
  if (replay && body !== undefined) throw new Error('重播中不能操作牌局，請先離開重播。');
  const headers = {'Content-Type':'application/json'};
  if (state?.session_id && ['/api/action','/api/next','/api/new'].includes(path)) {
    headers['X-Qinghe-Session'] = state.session_id;
  }
  const response=await fetch(path,body===undefined?{}:{method:'POST',headers,body:JSON.stringify(body)});
  const data=await response.json();
  if(!response.ok){const error=new Error(data.error||'連線失敗');error.status=response.status;throw error;}
  return data;
}
async function present(result, previewedAction = null) {
  const {playback = [], ...finalState} = result;
  selected = null;
  try {
    for (const frame of playback) {
      const alreadyShown = previewedAction && frame.pid===0 &&
        frame.type===previewedAction.type && frame.state.last_discard?.tile===previewedAction.tile;
      previewedAction = null;
      playbackFrame = frame;
      state = {...frame.state, actor:frame.pid};
      render();
      if (['DISCARD','TING'].includes(frame.type) && !alreadyShown) {
        beep();
        await tableView.animateDiscard(frame.pid);
      } else if (frame.type !== 'THINK' && !alreadyShown) beep();
      const winningCue = state.done && state.winner != null && state.winner !== 0;
      if (winningCue || ['CHI','PONG','GANG','ANGANG','KAKAN','HU'].includes(frame.type)) {
        showMeldCue(frame);
      }
      const delay = winningCue ? 1800
        : (frame.type === 'THINK' ? 500 + Math.random()*250
          : frame.state.done ? 1200 : ['DISCARD','TING'].includes(frame.type) ? 450 : 700)
          * {fast:.35,natural:1,relaxed:1.6}[pace];
      if (!alreadyShown) {
        await new Promise(resolve => setTimeout(resolve, delay));
      }
    }
  } finally {
    playbackFrame = null;
    state = finalState;
    render();
  }
  if (state.done) showResult();
}
async function perform(action){
  if(replay||!action||busy)return;
  pendingReaction = state.phase === 'REACTION' ? action : null;
  chiSelection=null;tingMode=false;tingPassed=false;busy=true;renderActions();renderHand();
  const before = state;
  const preview = ['DISCARD','TING'].includes(action.type) ? tableView.previewDiscard(action) : null;
  if (preview) beep();
  try{
    const move = Object.fromEntries(Object.entries(action).filter(([key])=>key!=='index'));
    if (roomMode) {
      const result = await request('/api/room/action', {action:move, version:state.version, request_id:crypto.randomUUID()});
      await preview;
      state = result;
      pendingReaction = null;
      selected = null;
      render();
      const event = state.display_event;
      const alreadyShown = preview && event?.pid===0 && event.type===action.type &&
        state.last_discard?.pid===0 && state.last_discard.tile===action.tile;
      if (['DISCARD','TING'].includes(event?.type) && !alreadyShown) {
        beep(); await tableView.animateDiscard(state.display_event.pid);
      }
      if (result.version !== before.version && !before.done &&
          ((state.done && state.winner != null) ||
           ['CHI','PONG','GANG','ANGANG','KAKAN','HU'].includes(event?.type))) {
        showMeldCue(event); beep();
        if (state.done && state.winner != null && state.winner !== 0) {
          await new Promise(resolve => setTimeout(resolve,1800));
        }
      }
    } else {
      const result = await request('/api/action', move);
      await preview;
      pendingReaction = null;
      await present(result, preview ? action : null);
    }
  }
  catch(e){
    await preview;
    state=before;selected=null;render();toast(e.message);
    try{state=await request(roomMode ? '/api/room/state' : '/api/state');}catch{}
  }
  finally{pendingReaction=null;busy=false;render();if(roomMode && state.done)showResult();}
}
async function newGame(next = false){
  tingPassed = false;
  if (roomMode) return roomCommand('/api/room/next');
  if(busy)return;busy=true;$('new-game').disabled=true;
  try{const result=await request(next ? '/api/next' : '/api/new',{});$('modal').close();await present(result);if(!state.done && !next)toast('新牌桌開始，每位玩家 1,000 點。');}
  catch(e){toast(e.message);}finally{busy=false;$('new-game').disabled=false;if(state)render();}
}
function modal(title, content, className = '', show = true){
  const tableAction = $('new-game');
  if (tableAction?.closest('#modal')) $('table-actions').append(tableAction);
  $('toast').classList.remove('visible');
  $('modal').className = className;
  $('modal-content').innerHTML=`<h2 id="modal-title"${className === 'result-dialog' ? ' tabindex="-1"' : ''}>${escapeHtml(title)}</h2>${content}<p id="modal-status" role="status" hidden></p>`;
  if(show && !$('modal').open)$('modal').showModal();
  if (className === 'result-dialog') $('modal-title').focus({preventScroll:true});
}
function showResult(snapshot = state, playerNames = names, onBack = null){
  if (replay && !onBack) return;
  const winner = snapshot.winner, result = snapshot.settlement;
  const flower = {qi_qiang_yi:'七搶一', ba_xian:'八仙過海'}[result.flower_win_type];
  const title = winner === null ? '流局' : flower || (snapshot.win_source === 'TSUMO' ? '自摸' : '胡牌');
  const seats = [...snapshot.seating_order];
  const start = winner === null ? 0 : seats.indexOf(winner);
  const order = [...seats.slice(start), ...seats.slice(0, start)];
  modal(winner === null ? title : `${playerNames[winner]} ${title}`, `<p class="result-caption">第 ${snapshot.round} 局 · ${winner === null ? '本局無輸贏' : `底 ${result.base_points} · 每台 ${result.tai_points}`}</p><div id="result-players" role="region" aria-label="四家結算" tabindex="0"></div><div class="result-actions"><button class="modal-primary" id="result-new">下一局　→</button></div>`, 'result-dialog');
  for (const pid of order) {
    const player = snapshot.final_hands?.[pid];
    const card = document.createElement('section');
    card.className = `result-player${pid === winner ? ' result-winner' : ''}`;
    card.setAttribute('data-wind', snapshot.seat_winds[pid]);
    const header = document.createElement('div'); header.className = 'result-player-heading';
    const name = escapeHtml(playerNames[pid]);
    const wind = winds[['E','S','W','N'].indexOf(snapshot.seat_winds[pid])];
    header.innerHTML = `<div class="result-identity"><span class="result-wind" aria-label="${wind}家">${wind}</span><div class="result-person"><div class="result-name-line"><strong title="${name}">${name}</strong>${pid === 0 ? '<span class="result-self">你</span>' : ''}</div><span class="result-status">${snapshot.dealer === pid ? '<span class="dealer">莊家</span>' : ''}${pid === winner ? '<span class="result-badge">胡牌</span>' : ''}${pid === result.payer ? '<span class="result-payer">放槍</span>' : ''}</span></div></div>`;
    const points = document.createElement('div'); points.className = 'result-points';
    for (const [label, value] of [['本局', result.payments[pid]], ['累積', snapshot.totals[pid]]]) {
      const amount = document.createElement('span');
      const caption = document.createElement('small'); caption.textContent = label;
      const number = document.createElement('strong');
      number.textContent = `${label === '本局' && value > 0 ? '+' : ''}${value}`;
      if (label === '本局') number.className = value > 0 ? 'points-positive' : value < 0 ? 'points-negative' : '';
      amount.append(caption, number); points.append(amount);
    }
    header.append(points); card.append(header);
    const tiles = document.createElement('div'); tiles.className = 'result-tiles';
    const handRun = document.createElement('div'); handRun.className = 'result-hand-run';
    const melds = player?.melds ?? snapshot.players[pid].melds.filter(m => m.tiles.every(id => id !== null));
    const meldOrder = sortHand(melds.map(m => Math.min(...m.tiles)), sortOrder);
    const sortedMelds = [...melds].sort((a, b) =>
      meldOrder.indexOf(Math.min(...a.tiles)) - meldOrder.indexOf(Math.min(...b.tiles)));
    const addGroup = (ids, kind, label) => {
      if (!ids.length) return;
      const group = document.createElement('div'); group.className = `result-group result-${kind}`;
      group.setAttribute('role', 'group'); group.setAttribute('aria-label', label); group.title = label;
      for (const id of ids) {
        const face = tile(id);
        if (kind === 'flowers' && pid === winner && id === snapshot.win_tile) face.classList.add('result-winning-tile');
        group.append(face);
      }
      (['concealed','drawn','winning'].includes(kind) ? handRun : tiles).append(group);
    };
    if (player) {
      addGroup([...player.flowers].sort((a, b) => a - b), 'flowers', '花牌');
      for (const meld of sortedMelds) addGroup(sortHand(meld.tiles, sortOrder), 'meld', labels[meld.type] || meld.type);
      addGroup(sortHand(player.hand, sortOrder), 'concealed', '手牌');
      const winning = pid === winner && snapshot.win_tile !== null
        && !(result.flower_win_type && player.flowers.includes(snapshot.win_tile));
      if (player.drawn !== null && (!winning || player.drawn !== snapshot.win_tile)) addGroup([player.drawn], 'drawn', '摸牌');
      if (winning) addGroup([snapshot.win_tile], 'winning', title);
    } else {
      // Older running tables can still show the previously available winner tiles.
      addGroup([...(pid === winner && result.flower_win_type ? snapshot.winning_hand || [] : snapshot.players[pid].flowers)].sort((a, b) => a - b), 'flowers', '花牌');
      for (const meld of sortedMelds) addGroup(sortHand(meld.tiles, sortOrder), 'meld', labels[meld.type]);
      if (pid === winner && !result.flower_win_type) addGroup(sortHand(snapshot.winning_hand || [], sortOrder), 'concealed', '手牌');
    }
    if (handRun.children.length) tiles.append(handRun);
    card.append(tiles);
    if (pid === winner || (winner !== null && pid === snapshot.dealer && result.payments[pid] < 0)) {
      const expandable = pid === winner
        ? result.tai > 0 && result.breakdown.length > 0 : result.payments[pid] < 0;
      const details = document.createElement(expandable ? 'details' : 'div');
      details.className = 'result-scoring';
      if (pid === winner && expandable) details.open = true;
      const summary = document.createElement(expandable ? 'summary' : 'span');
      const streak = snapshot.dealer_streak || 0;
      summary.textContent = pid === winner ? `胡牌 ${result.tai} 台`
        : `莊・連 ${streak}　${result.payments[pid] < 0 ? `加 ${2 * streak + 1} 台` : '本局未收付'}`;
      details.append(summary);
      const addScore = (label, value) => {
        const row = document.createElement('div'); row.className = 'score-row';
        const caption = document.createElement('span'); caption.textContent = label;
        const amount = document.createElement('strong'); amount.textContent = value;
        row.append(caption, amount); details.append(row);
      };
      if (pid === winner && expandable) {
        for (const item of result.breakdown) addScore(item.label, `${item.points} 台`);
      } else if (result.payments[pid] < 0) {
        const basic = result.base_points + result.tai * result.tai_points;
        const payment = -result.payments[pid];
        addScore('基本收付', `${basic}`);
        addScore(`莊家加台　${2 * streak + 1} × ${result.tai_points}`, `${payment - basic}`);
        addScore(`付給 ${playerNames[winner]}`, `${payment}`);
      }
      card.append(details);
    }
    $('result-players').append(card);
  }
  if (onBack) {
    $('result-new').textContent = '返回紀錄';
    $('result-new').onclick = onBack;
    return;
  }
  $('result-new').disabled = !!snapshot.room && !snapshot.room.host;
  if (snapshot.room && !snapshot.room.host) $('result-new').textContent = '等待房主開啟下一局';
  $('result-new').onclick = () => newGame(true);
}
$('close-modal').onclick=()=>$('modal').close();
$('modal').addEventListener('cancel', event => {
  const help = $('modal').querySelector('.session-help[open]');
  if (!help) return;
  event.preventDefault(); help.open = false;
  help.querySelector('summary').focus({preventScroll:true});
});
$('modal').onclick=e=>{const help=$('modal').querySelector('.session-help[open]');if(help&&!help.contains(e.target)){help.open=false;return;}if(e.target===$('modal')){const r=$('modal').getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)$('modal').close();}};
$('sound').onclick=()=>{sound=!sound;localStorage.setItem('qinghe-sound',sound);updateSound();beep();toast(sound?'音效已開啟':'音效已關閉');};
function updateSound(){$('sound').innerHTML=`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9h4l5-4v14l-5-4H4z"/>${sound?'<path d="M16 8q4 4 0 8M19 5q7 7 0 14"/>':'<path d="m17 9 5 6m0-6-5 6"/>'}</svg>`;$('sound').setAttribute('aria-label',sound?'關閉音效':'開啟音效');$('sound').setAttribute('aria-pressed',String(sound));}
updateSound();
const sortNames = ['萬', '筒', '條', '字'];
let settingsOrder, settingsSortable;
function setSettingsOrder(order) {
  if (!validOrder(order)) return;
  settingsOrder = [...order];
  renderSortSettings();
}
function moveSortGroup(group, position) {
  const order = settingsOrder.filter(value => value !== group);
  order.splice(position, 0, group);
  setSettingsOrder(order);
  $(`sort-group-${group}`).focus();
}
function syncSortSettings() {
  const list = $('sort-order');
  const value = settingsOrder.join(',');
  $('sort-preset').value = [...$('sort-preset').options].some(o => o.value === value)
    ? value : 'custom';
  [...list.children].forEach((button, position) => {
    button.setAttribute('aria-label', `${sortNames[Number(button.dataset.group)]}，第 ${position + 1} 位`);
  });
}
function renderSortSettings() {
  const list = $('sort-order');
  settingsSortable?.destroy();
  list.replaceChildren();
  settingsOrder.forEach(group => {
    const button = document.createElement('button');
    button.id = `sort-group-${group}`;
    button.className = 'sort-group';
    button.type = 'button';
    button.dataset.group = group;
    const face = tile([0, 9, 18, 27][group],false,null,$('tile-font-setting').value);
    button.append(face);
    button.onkeydown = event => {
      const step = event.key === 'ArrowLeft' ? -1 : event.key === 'ArrowRight' ? 1 : 0;
      if (!step) return;
      event.preventDefault();
      const next = settingsOrder.indexOf(group) + step;
      if (next >= 0 && next < 4) moveSortGroup(group, next);
    };
    list.append(button);
  });
  syncSortSettings();
  settingsSortable = Sortable.create(list, {
    direction: 'horizontal',
    draggable: '.sort-group',
    animation: 0, // Keep slot geometry stable when the next drag starts immediately.
    forceFallback: true,
    fallbackTolerance: 4,
    ghostClass: 'sort-placeholder',
    fallbackClass: 'sort-floating',
    onEnd: event => {
      settingsOrder = [...list.children].map(button => Number(button.dataset.group));
      syncSortSettings();
      event.item.focus({ preventScroll: true });
    }
  });
}
$('modal').addEventListener('close', () => {
  const tableAction = $('new-game');
  if (tableAction?.closest('#modal')) $('table-actions').append(tableAction);
  settingsSortable?.destroy();
  settingsSortable = null;
});

$('settings').onclick=()=>{
  settingsOrder = [...sortOrder];
  modal('牌桌設定',`
    <div id="settings-table-actions" class="settings-table-actions"></div>
    <section class="settings-section" aria-labelledby="play-settings-heading">
      <h3 id="play-settings-heading">對局與顯示</h3>
      <label class="setting-row"><span class="pace-label">對局節奏${roomMode ? '<small id="pace-help">多人模式由伺服器統一設定</small>' : ''}</span><select id="pace-setting" ${roomMode ? 'disabled aria-describedby="pace-help"' : ''}>${roomMode ? '<option value="shared">統一節奏</option>' : '<option value="fast">快速</option><option value="natural">一般（預設）</option><option value="relaxed">慢速</option>'}</select></label>
      <fieldset class="chi-mode-options"><legend>多種吃牌選擇</legend>
        <label class="chi-mode-card"><input type="radio" name="chi-mode" value="groups" ${chiMode==='groups'?'checked':''}><span id="chi-groups-icon" class="chi-mode-graphic" aria-hidden="true"></span><span class="chi-mode-caption">選整組順子</span></label>
        <label class="chi-mode-card"><input type="radio" name="chi-mode" value="tiles" ${chiMode==='tiles'?'checked':''}><span id="chi-tiles-icon" class="chi-mode-graphic" aria-hidden="true"></span><span class="chi-mode-caption">選兩張牌後確認</span></label>
      </fieldset>
      <div class="settings-toggles">
        <label class="setting-row">聽牌後自動出牌<input id="auto-ting-setting" type="checkbox" ${autoTingDiscard?'checked':''} ${state.auto_ting_discard === undefined?'disabled':''}></label>
        <label class="setting-row">操作音效<input id="sound-setting" type="checkbox" ${sound?'checked':''}></label>
        <label class="setting-row">減少桌面陰影<input id="flat-setting" type="checkbox" ${compact?'checked':''}></label>
      </div>
    </section>
    <section class="settings-section" aria-labelledby="tile-font-heading">
      <h3 id="tile-font-heading">牌面與排列</h3>
      <label class="setting-row">樣式<select id="tile-font-setting">${TILE_FONTS.map(font=>`<option value="${font.id}">${font.name}</option>`).join('')}</select></label>
      <label class="setting-row">排列<select id="sort-preset"><option value="0,1,2,3">萬 → 筒 → 條 → 字（預設）</option><option value="1,2,0,3">筒 → 條 → 萬 → 字</option><option value="3,0,1,2">字 → 萬 → 筒 → 條</option><option value="custom" disabled>自訂順序</option></select></label>
      <div class="settings-tile-row">
        <div id="sort-order" class="sort-order" role="group" aria-label="牌種排序與樣式預覽" aria-describedby="sort-help"></div>
        <div id="fixed-face-preview" class="fixed-face-preview" role="group" aria-label="白板與花牌樣式預覽"></div>
      </div>
      <p id="sort-help">左右拖拉牌圖示調整順序，也可選中後按左右方向鍵。</p>
      <details id="tile-face-details"><summary>查看完整牌面</summary><div id="tile-font-preview" class="full-face-preview"></div></details>
    </section>
    <div class="settings-footer"><p>儲存後套用，下次開啟會保留。<br>牌面來源：<a href="https://github.com/SyaoranHinata/I.Mahjong" target="_blank" rel="noopener">I.Mahjong</a></p><button class="modal-primary" id="save-settings">儲存</button></div>
  `,'settings-dialog');
  $('settings-table-actions').append($('new-game'));
  for (const [id, combinations] of [['chi-groups-icon', [[0,1,2],[1,2,3]]],
    ['chi-tiles-icon', [[0,1,2]]]]) {
    for (const combination of combinations) {
      const group = document.createElement('span'); group.className = 'chi-icon-group';
      for (const value of combination) {
        const face = tile(value, true);
        if (value === 1) face.classList.add('chi-icon-discard');
        group.append(face);
      }
      $(id).append(group);
    }
    if (id === 'chi-tiles-icon') {
      const confirm = document.createElement('span'); confirm.className = 'chi-icon-confirm';
      confirm.textContent = '確認'; $(id).append(confirm);
    }
  }
  $('tile-font-setting').value = tileFont;
  const previewFont = () => {
    const font = $('tile-font-setting').value;
    $('fixed-face-preview').replaceChildren(...[33,34].map(id => {
      return tile(id,false,null,font);
    }));
    if (!$('tile-face-details').open) return;
    $('tile-font-preview').replaceChildren(...[
      ['萬',0,9], ['筒',9,18], ['條',18,27], ['字',27,34], ['花',34,42],
    ].map(([label,start,end]) => {
      const row = document.createElement('div');
      row.className = 'full-face-row';
      row.setAttribute('role','group');
      row.setAttribute('aria-label',`${label}牌`);
      const name = document.createElement('span');
      name.className = 'full-face-label';
      name.textContent = label;
      row.append(name);
      for (let id=start;id<end;id++) {
        row.append(tile(id,false,null,font));
      }
      return row;
    }));
  };
  $('tile-face-details').ontoggle = previewFont;
  $('tile-font-setting').onchange = () => {
    $('modal-status').hidden = true;
    $('modal-status').textContent = '';
    previewFont();
    $('sort-order').querySelectorAll('img').forEach(img => {
      setTileFace(img,Number(img.dataset.tileId),$('tile-font-setting').value);
    });
  };
  previewFont();
  $('pace-setting').value = roomMode ? 'shared' : pace;
  renderSortSettings();
  $('sort-preset').onchange=e=>setSettingsOrder(e.target.value.split(',').map(Number));
  $('save-settings').onclick=async()=>{
    const button = $('save-settings');
    if (button.disabled || busy) return;
    const next = {font:$('tile-font-setting').value, order:[...settingsOrder],
      sound:$('sound-setting').checked, compact:$('flat-setting').checked,
      pace:roomMode ? pace : $('pace-setting').value,
      autoTingDiscard:$('auto-ting-setting').checked,
      chiMode:document.querySelector('input[name="chi-mode"]:checked').value};
    button.disabled = true;
    button.textContent = '儲存中…';
    busy = true;
    try {
      if (tableView) await tableView.setFaceFont(next.font);
      if (!state || state.auto_ting_discard !== undefined) {
        const result = await request('/api/preferences', {auto_ting_discard:next.autoTingDiscard});
        if (roomMode) { state = result; render(); }
        else await present(result);
      }
    } catch (error) {
      busy = false;
      button.disabled = false;
      button.textContent = '儲存';
      toast('設定儲存失敗，請再試一次');
      return;
    }
    busy = false;
    autoTingDiscard = next.autoTingDiscard;
    chiMode = next.chiMode; chiSelection = null;
    localStorage.setItem('qinghe-chi-mode', chiMode);
    localStorage.setItem('qinghe-auto-ting-discard', String(autoTingDiscard));
    tileFont = next.font;
    sortOrder = next.order;
    sound = next.sound;
    compact = next.compact;
    pace = next.pace;
    localStorage.setItem('qinghe-tile-font',tileFont);
    document.querySelectorAll('img[data-tile-id]').forEach(img => {
      setTileFace(img,Number(img.dataset.tileId),tileFont);
    });
    localStorage.setItem('qinghe-pace', pace);
    localStorage.setItem('qinghe-sort-order', JSON.stringify(sortOrder));
    localStorage.setItem('qinghe-sound', sound);
    localStorage.setItem('qinghe-flat', compact);
    updateSound();
    document.body.classList.toggle('compact', compact);
    selected = null;
    if (tableView) tableView.renderer.shadowMap.enabled = !compact;
    renderHand();
    if (state) renderActions();
    if ($('save-settings') === button) $('modal').close();
    toast('設定已儲存');
  };
};
$('new-game').onclick=()=>{if(!state)return;if(roomMode){modal('離開房間？','<p>離開後將由電腦接手；若仍有電腦空位，可再加入並接替該座位。</p><button class="modal-primary" id="confirm-leave">離開房間</button>');$('confirm-leave').onclick=leaveRoom;return;}if(!state.done)return;modal('建立新 Session？','<p>原 Session 的分數、紀錄與接續入口都會保留。新 Session 每位玩家從 1,000 點、東風圈開始。所有單人桌的最新一局都須先打完。</p><button class="modal-primary" id="confirm-new">建立新 Session</button>');$('confirm-new').onclick=()=>newGame();};
function refreshSessionHeaders() {
  const list = $('session-list');
  if (!list) return;
  const top = list.getBoundingClientRect().top;
  for (const table of list.querySelectorAll('.session-table-scroll')) {
    const bounds = table.getBoundingClientRect();
    const header = table.querySelector('thead')?.getBoundingClientRect().height || 0;
    const offset = Math.max(0, Math.min(top - bounds.top, bounds.height - header));
    table.style.setProperty('--table-head-top', `${offset}px`);
  }
}
window.addEventListener('resize', refreshSessionHeaders);
$('hand-history').onclick = () => showHistory();
function historyAction(label, icon, action) {
  const button = document.createElement('button');
  button.className = 'history-action'; button.title = label;
  button.setAttribute('aria-label', label);
  button.innerHTML = icon;
  button.onclick = action;
  return button;
}
async function showHistoricalResult(id, returnButton) {
  if (busy || replay) return;
  const list = $('session-list');
  const content = [...$('modal-content').childNodes];
  const scrollPositions = [list, ...list.querySelectorAll('.session-table-scroll')]
    .map(node => ({node, top:node.scrollTop, left:node.scrollLeft}));
  busy = true;
  try {
    const {frames} = await request(`/api/replay?hand_id=${encodeURIComponent(id)}`);
    if (!$('modal').open || $('session-list') !== list) return;
    const snapshot = frames?.at(-1)?.state;
    if (!snapshot?.done || !snapshot.settlement) throw new Error('找不到完整的結算紀錄。');
    showResult(snapshot, snapshot.replay_names, () => {
      $('modal').className = 'session-dialog';
      $('modal-content').replaceChildren(...content);
      for (const {node, top, left} of scrollPositions) {
        node.scrollTop = top; node.scrollLeft = left;
      }
      refreshSessionHeaders();
      returnButton.focus({preventScroll:true});
    });
  } catch (error) { toast(error.message); }
  finally { busy = false; }
}
async function showHistory(openSessionId = null) {
  const opener = $('hand-history');
  if (opener.disabled) return;
  opener.disabled = true;
  try {
    const {sessions} = await request('/api/sessions');
    let currentReady = false;
    if (sessions.some(session => session.id === state?.session_id)) {
      try { await request(state?.room ? '/api/room/state' : '/api/state'); currentReady = true; } catch {}
    }
    openSessionId ??= sessions[0]?.id;
    modal('Session 紀錄', '<details class="session-help"><summary aria-label="Session 與統計說明" title="Session 與統計說明"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7v1"/></svg></summary><div><ul><li>單人與多人牌桌各自記錄 Session；能否接續依目前座位與牌桌狀態決定。</li><li>首局未完也會保存原牌；完成第一局後正式成立。多人桌須開始對局後才會出現在紀錄。</li><li>和牌包含自摸；各項比率以已結算局數為分母，含流局。</li><li>分數與統計按座位累計，包含中途接替該座位的玩家；配色依最新保存門風。</li><li>僅自己參與過且引擎相容的已完成局可查看暗牌結算與重播。</li></ul></div></details><div id="session-list" role="region" aria-label="Session 清單" tabindex="0"></div>', 'session-dialog', false);
    const sessionList = $('session-list');
    sessionList.onscroll = refreshSessionHeaders;
    if (!sessions.length) sessionList.textContent = '尚無 Session，開始對局後會自動保存。';
    for (const session of sessions) {
      const card = document.createElement('details'); card.className = 'session-card';
      const summary = document.createElement('summary');
      const date = document.createElement('strong');
      date.textContent = new Date(session.started_at).toLocaleString();
      const progress = document.createElement('span');
      progress.textContent = session.established ? `已完成 ${session.completed_hands} 局` : '首局待完成';
      const id = document.createElement('span'); id.className = 'session-id';
      id.textContent = `ID ${session.id.slice(0,8)}`; id.title = `ID ${session.id}`;
      const mode = document.createElement('span'); mode.className = 'session-mode';
      mode.textContent = session.source === 'multiplayer'
        ? `多人${session.room_code ? ` · 房間 ${session.room_code}` : ''}` : '單人';
      summary.append(date, mode, progress, id);
      if (session.id === state?.session_id) {
        const badge = document.createElement('span'); badge.className = 'session-current';
        badge.textContent = '目前牌桌'; summary.append(badge);
      }
      const body = document.createElement('div'); body.className = 'session-body';
      if (session.resumable) {
        const resume = document.createElement('button'); resume.className = 'session-resume';
        resume.textContent = session.source === 'multiplayer' ? '返回牌桌' : '繼續此 Session';
        resume.disabled = session.id === state?.session_id && currentReady;
        if (session.id === state?.session_id && !currentReady) {
          resume.textContent = '恢復此 Session'; resume.title = '從最後保存的進度恢復';
        }
        if (resume.disabled) resume.title = '目前正在此 Session';
        resume.onclick = event => { event.stopPropagation(); resumeHand(session.hand_id); };
        summary.append(resume);
      } else {
        const warning = document.createElement('span'); warning.textContent = '僅供查閱';
        summary.append(warning);
      }
      const content = document.createElement('div'); content.className = 'session-detail';
      body.append(content); card.append(summary, body);
      let loaded = false, loading = false;
      card.ontoggle = async () => {
        refreshSessionHeaders();
        if (!card.open || loaded || loading) return;
        loading = true; content.textContent = '載入統計…';
        try {
          const detail = await request(`/api/session?session_id=${encodeURIComponent(session.id)}`);
          content.replaceChildren();
          const scores = document.createElement('div'); scores.className = 'session-scores';
          const rankings = document.createElement('ol'); rankings.className = 'session-rankings';
          const renderRankings = totals => {
            rankings.replaceChildren();
            const ranked = [0,1,2,3].sort((a,b) => totals[b]-totals[a] || a-b);
            ranked.forEach(pid => {
              const item = document.createElement('li');
              item.className = 'seat-person'; item.dataset.player = pid; item.dataset.wind = detail.seat_winds[pid];
              const avatar = document.createElement('div'); avatar.className = `avatar a${pid}`;
              avatar.textContent = Array.from(detail.players[pid])[0]; avatar.setAttribute('aria-hidden','true');
              const info = document.createElement('div'); info.className = 'player-info';
              const person = document.createElement('strong'); person.className = 'player-name';
              const wind = winds[['E','S','W','N'].indexOf(detail.seat_winds[pid])];
              person.textContent = detail.players[pid]; person.title = `${wind}家：${detail.players[pid]}`;
              const total = document.createElement('small');
              total.textContent = `${totals[pid].toLocaleString()} 點`;
              info.append(person, total);
              const rank = document.createElement('span'); rank.className = 'session-rank-tag';
              const place = ranked.findIndex(other => totals[other] === totals[pid]) + 1;
              rank.textContent = `第 ${place} 名`;
              item.append(avatar, info, rank); rankings.append(item);
            });
          };
          if (detail.points.length > 1) {
            scores.append(renderScoreChart(detail.points, detail.players, detail.seat_winds, point => renderRankings(point.totals)));
          } else {
            renderRankings(detail.totals);
            const empty = document.createElement('p'); empty.className = 'session-chart-empty';
            empty.textContent = '完成第一局後顯示分數走勢'; scores.append(empty);
          }
          scores.append(rankings); content.append(scores);
          const heading = document.createElement('h3'); heading.textContent = '四家統計';
          const stats = document.createElement('table'); stats.className = 'session-stats';
          const header = document.createElement('tr');
          for (const text of ['玩家', '累計分數', '和牌', '和牌率', '自摸', '自摸率', '放槍', '放槍率', '平均收付']) {
            const cell = document.createElement('th'); cell.scope = 'col'; cell.textContent = text; header.append(cell);
          }
          const head = document.createElement('thead'); head.append(header); stats.append(head);
          const rows = document.createElement('tbody');
          const count = detail.hands.length;
          const rate = value => count ? `${(value / count * 100).toFixed(1)}%` : '—';
          detail.seats.forEach((seat, pid) => {
            const row = document.createElement('tr'); row.dataset.wind = detail.seat_winds[pid];
            [detail.players[pid], detail.totals[pid].toLocaleString(), seat.wins, rate(seat.wins),
              seat.tsumo, rate(seat.tsumo), seat.deal_ins, rate(seat.deal_ins),
              seat.average_payment.toFixed(1)].forEach((text, column) => {
              const cell = document.createElement(column === 0 ? 'th' : 'td');
              if (column === 0) cell.scope = 'row';
              cell.textContent = text; row.append(cell);
            });
            rows.append(row);
          });
          stats.append(rows);
          const scroll = document.createElement('div'); scroll.className = 'session-table-scroll';
          scroll.setAttribute('role','region'); scroll.setAttribute('aria-label','四家統計');
          scroll.tabIndex = 0; scroll.append(stats); content.append(heading, scroll);
          const recordHeading = document.createElement('h3');
          recordHeading.textContent = `逐局紀錄（${count} 局，流局 ${detail.draws} 局）`;
          const history = document.createElement('table'); history.className = 'session-records';
          const recordHead = document.createElement('thead');
          const titles = document.createElement('tr');
          for (const text of ['局', '結果', '和牌者', '台數', ...detail.players, '重播', '結算']) {
            const cell = document.createElement('th'); cell.scope = 'col'; cell.textContent = text;
            cell.title = text; titles.append(cell);
          }
          recordHead.append(titles); history.append(recordHead);
          const records = document.createElement('tbody');
          detail.hands.map((hand, index) => ({hand, point:detail.points[index+1]})).reverse().forEach(({hand, point}) => {
            const row = document.createElement('tr');
            for (const text of [hand.round, hand.winner === null ? '流局' : hand.win_source === 'TSUMO' ? '自摸' : '和牌',
              hand.winner === null ? '—' : (hand.players || detail.players)[hand.winner], hand.tai ?? '—']) {
              const cell = document.createElement('td'); cell.textContent = text; row.append(cell);
            }
            point.totals.forEach((value, pid) => {
              const cell = document.createElement('td'); cell.dataset.wind = detail.seat_winds[pid];
              const total = document.createElement('span'); total.textContent = value.toLocaleString();
              const payment = document.createElement('small'); const amount = hand.payments[pid];
              payment.className = amount > 0 ? 'points-positive' : amount < 0 ? 'points-negative' : '';
              payment.textContent = `${amount > 0 ? '+' : ''}${amount}`;
              cell.append(total, payment); row.append(cell);
            });
            const actions = [
              historyAction(`重播第 ${hand.round} 局`, replayIcon('play'), () => showReplay(hand.id)),
              historyAction(`查看第 ${hand.round} 局結算`, '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/></svg>', event => showHistoricalResult(hand.id, event.currentTarget)),
            ];
            for (const action of actions) {
              const cell = document.createElement('td'); cell.className = 'history-actions';
              if (hand.replayable) cell.append(action); else cell.textContent = '—';
              row.append(cell);
            }
            records.append(row);
          });
          history.append(records);
          const recordScroll = document.createElement('div');
          recordScroll.className = 'session-table-scroll session-records-scroll';
          recordScroll.setAttribute('role','region'); recordScroll.setAttribute('aria-label','逐局紀錄');
          recordScroll.tabIndex = 0; recordScroll.append(history);
          const caption = document.createElement('p'); caption.className = 'session-record-caption';
          caption.textContent = '分數上排為累計，下排為本局收付';
          content.append(recordHeading, caption, recordScroll); loaded = true;
          refreshSessionHeaders();
        } catch (error) { content.textContent = error.message; }
        finally { loading = false; }
      };
      sessionList.append(card);
      if (session.id === openSessionId) {
        card.open = true;
        await card.ontoggle();
      }
    }
    if (!$('modal').open) $('modal').showModal();
    refreshSessionHeaders();
  } catch (error) { toast(error.message); }
  finally { opener.disabled = false; }
}
async function resumeHand(id) {
  if (busy) return;
  busy = true;
  try {
    const result = await request('/api/resume', {hand_id:id});
    selected = null; tingPassed = false; tingMode = false;
    if (result.room) {
      if (!roomMode) acceptRoom(result); else state = result;
    } else state = result;
    $('modal').close(); render();
    if (state.done) showResult();
  } catch (error) { toast(error.message); }
  finally { busy = false; if (state) render(); }
}
function replayLabel(frame) {
  const event = frame.event, snapshot = frame.state;
  if (!event) return '開局';
  if (event.type === 'DRAW_GAME') return '流局';
  const type = event.type === 'HU' && snapshot.win_source === 'TSUMO' ? '自摸' : labels[event.type];
  const tiles = event.type === 'CHI' ? [...(event.use || []), event.tile].sort((a,b)=>a-b)
    : event.tile == null ? [] : [event.tile];
  const source = event.from_pid == null ? '' : `（${snapshot.replay_names[event.from_pid]}）`;
  return `${snapshot.replay_names[event.pid]} ${type} ${tiles.map(tileName).join('、')}${source}`.trim();
}
function replayIcon(type) {
  const paths = {
    prev:'M5 5h2v14H5z M19 5v14L8 12z',
    play:'M8 5l11 7-11 7z', pause:'M6 5h4v14H6z M14 5h4v14h-4z',
    next:'M17 5h2v14h-2z M5 5l11 7-11 7z',
    exit:'M9 5H5v14h4 M13 8l4 4-4 4 M8 12h9',
  };
  return `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="${paths[type]}" fill="${type==='exit'?'none':'currentColor'}" stroke="${type==='exit'?'currentColor':'none'}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}
function renderReplayControls() {
  const {frames, index, loading, playing} = replay;
  const snapshot = frames[index].state;
  $('replay-step').max = frames.length - 1;
  $('replay-step').value = index;
  $('replay-label').textContent = `${index} / ${frames.length-1}`;
  $('replay-label').title = replayLabel(frames[index]);
  $('replay-label').setAttribute('aria-label',`第 ${index} 步，共 ${frames.length-1} 步：${replayLabel(frames[index])}`);
  $('replay-prev').disabled = loading || index === 0;
  $('replay-next').disabled = loading || index === frames.length-1;
  $('replay-play').disabled = loading;
  $('replay-play').innerHTML = replayIcon(playing ? 'pause' : 'play');
  $('replay-play').setAttribute('aria-label',playing ? '暫停重播' : '播放重播');
  $('replay-play').setAttribute('aria-pressed',String(Boolean(playing)));
  $('replay-play').title = playing ? '暫停' : '播放';
  $('replay-step').disabled = loading;
  $('replay-speed').disabled = loading;
  for (const [i,wind] of ['E','S','W','N'].entries()) {
    const button = $(`replay-view-${wind}`);
    const seat = snapshot.seat_winds.indexOf(wind);
    const viewer = (snapshot.replay_viewer + seat) % 4;
    button.dataset.viewer = viewer;
    button.disabled = loading;
    button.setAttribute('aria-pressed',String(viewer === snapshot.replay_viewer));
    button.setAttribute('aria-label',`${winds[i]}家視角：${snapshot.replay_names[seat]}`);
    button.title = `${winds[i]}家：${snapshot.replay_names[seat]}`;
  }
  $('replay-exit').disabled = Boolean(replay.exiting);
}
function stopReplay() {
  if (!replay) return;
  clearTimeout(replay.timer);
  replay.timer = null;
  replay.playing = false;
}
function replayStep(index, autoplay = false) {
  if (!replay || replay.loading) return;
  if (!autoplay) stopReplay();
  replay.index = Math.max(0,Math.min(replay.frames.length-1,Number(index)));
  if (replay.index === replay.frames.length-1) stopReplay();
  clearTimeout(meldCueTimer); $('meld-cue').hidden = true;
  render();
  const event = replay.frames[replay.index].event;
  if (event) showMeldCue(event);
}
function scheduleReplay() {
  if (!replay?.playing || replay.loading) return;
  const current = replay;
  clearTimeout(current.timer);
  const type = current.frames[current.index].event?.type;
  const delay = (['DISCARD','TING'].includes(type) ? 450 : 700)
    * {fast:.35,natural:1,relaxed:1.6}[pace] / current.speed;
  current.timer = setTimeout(() => {
    if (replay !== current || !current.playing || current.loading) return;
    replayStep(current.index+1,true);
    scheduleReplay();
  },delay);
  renderReplayControls();
}
function toggleReplay() {
  if (!replay || replay.loading) return;
  if (replay.playing) { stopReplay(); renderReplayControls(); return; }
  if (replay.index === replay.frames.length-1) replayStep(0);
  replay.playing = true;
  scheduleReplay();
}
function lockReplaySurface(locked) {
  document.body.classList.toggle('replaying', locked);
  for (const node of document.querySelectorAll('.table-toolbar,.table-canvas,#ting-panel')) {
    node.inert = locked;
  }
}
async function showReplay(id) {
  if (busy || replay || !tableView) return;
  busy = true;
  try {
    const {frames} = await request(`/api/replay?hand_id=${encodeURIComponent(id)}`);
    if (!Array.isArray(frames) || !frames.length || !frames[0].state?.replay_seats) {
      throw new Error('重播需要更新伺服器，請重新啟動服務後再試。');
    }
    // An in-flight live discard finishes before replacing the shared 3D scene.
    while (tableView.discardAnimating) await new Promise(resolve=>setTimeout(resolve,20));
    replay = {id,frames,index:0,loading:false,playing:false,speed:1,timer:null};
    selected = null; chiSelection = null; tingMode = false; tingPassed = false;
    clearTimeout(meldCueTimer); $('meld-cue').hidden = true;
    $('modal').close();
    lockReplaySurface(true);
    const controls = $('replay-controls');
    controls.innerHTML = `<input id="replay-step" type="range" min="0" value="0" aria-label="重播進度"><button id="replay-prev" class="replay-icon" aria-label="上一步" title="上一步">${replayIcon('prev')}</button><button id="replay-play" class="replay-icon" aria-label="播放重播" title="播放">${replayIcon('play')}</button><button id="replay-next" class="replay-icon" aria-label="下一步" title="下一步">${replayIcon('next')}</button><select id="replay-speed" aria-label="播放速度" title="播放速度"><option value="0.5">0.5×</option><option value="1" selected>1×</option><option value="1.5">1.5×</option><option value="2">2×</option><option value="4">4×</option></select><span id="replay-label" role="status"></span><div class="replay-views" role="group" aria-label="視角"><span class="replay-view-label">視角</span>${['E','S','W','N'].map((wind,i)=>`<button id="replay-view-${wind}" aria-pressed="false">${winds[i]}</button>`).join('')}</div><button id="replay-exit" class="replay-icon" aria-label="離開重播" title="離開重播">${replayIcon('exit')}</button>`;
    $('replay-step').oninput = event => replayStep(event.target.value);
    $('replay-prev').onclick = () => replayStep(replay.index-1);
    $('replay-next').onclick = () => replayStep(replay.index+1);
    $('replay-play').onclick = toggleReplay;
    $('replay-speed').onchange = event => {
      replay.speed = Number(event.target.value);
      if (replay.playing) scheduleReplay();
    };
    for (const wind of ['E','S','W','N']) {
      const button = $(`replay-view-${wind}`);
      button.onclick = () => changeReplayView(Number(button.dataset.viewer));
    }
    $('replay-exit').onclick = exitReplay;
    render(); $('replay-next').focus();
    if (roomMode) toast('重播中；朋友房間仍會繼續進行。');
  } catch (error) { toast(error.message); }
  finally { busy = false; }
}
async function changeReplayView(viewer) {
  const current = replay;
  if (!current || current.loading || current.frames[current.index].state.replay_viewer === viewer) return;
  stopReplay();
  current.loading = true; renderReplayControls();
  try {
    const {frames} = await request(`/api/replay?hand_id=${encodeURIComponent(current.id)}&view=${viewer}`);
    if (replay !== current) return;
    current.frames = frames;
  } catch (error) { toast(error.message); }
  finally {
    if (replay === current) { current.loading = false; replayStep(current.index); }
  }
}
async function exitReplay() {
  if (!replay || replay.exiting) return;
  stopReplay();
  // Replacing the object also invalidates a still-loading perspective response.
  replay = {...replay,loading:true,exiting:true}; renderReplayControls();
  // Invalidate any long poll that began before refreshing the live table.
  ++pollGeneration;
  try {
    const result = await request('/api/state');
    replay = null; state = result;
    clearTimeout(meldCueTimer); $('meld-cue').hidden = true;
    lockReplaySurface(false);
    roomMode = false;
    if (result.room) acceptRoom(result);
    else sessionStorage.removeItem('qinghe-room');
    $('toast').classList.remove('visible');
    render();
    if (state.done) showResult();
  } catch (error) {
    replay.loading = false; replay.exiting = false; renderReplayControls();
    toast(`無法返回目前牌桌：${error.message}，請再按「離開重播」重試。`);
    if (roomMode) pollRoom(pollGeneration);
  }
}
function acceptRoom(result) {
  roomMode = true; state = result; selected = null;
  tingPassed = false; tingMode = false;
  rememberPlayerName(result.room.members[0].name);
  sessionStorage.setItem('qinghe-room', result.room.code);
  const url = new URL(location.href); url.searchParams.set('room', result.room.code);
  history.replaceState(null, '', url);
  const generation = ++pollGeneration;
  pollRoom(generation);
}
async function pollRoom(generation) {
  while (roomMode && generation === pollGeneration) {
    if (busy) { await new Promise(resolve => setTimeout(resolve, 100)); continue; }
    try {
      const result = await request(`/api/room/state?after=${state.version}`);
      if (generation !== pollGeneration || !roomMode) return;
      if (!busy && result.version >= state.version) {
        const old = state; state = result;
        if (replay) continue;
        if (old.version !== result.version) selected = null;
        render();
        const event = state.display_event;
        if (old.version !== state.version && event && ['DISCARD','TING'].includes(event.type)) {
          beep(); await tableView.animateDiscard(event.pid);
        }
        if (replay) continue;
        if (old.version !== state.version && !old.done &&
            ((state.done && state.winner != null) ||
             ['CHI','PONG','GANG','ANGANG','KAKAN','HU'].includes(event?.type))) {
          showMeldCue(event); beep();
          if (state.done && state.winner != null && state.winner !== 0) {
            await new Promise(resolve => setTimeout(resolve,1800));
          }
        }
        if (!roomMode || generation !== pollGeneration) return;
        if (replay) continue;
        if (state.done && (!old.done || old.room.host !== state.room.host)) showResult();
        else if (old.done && !state.done) $('modal').close();
      }
    } catch (error) {
      if (!roomMode || generation !== pollGeneration) return;
      if (error.status === 400) {
        if (replay) { roomMode = false; ++pollGeneration; continue; }
        toast(error.message); await leaveRoom(); return;
      }
      $('connection-status').textContent = '重新連線中…';
      $('connection-status').parentElement.hidden = false;
      await new Promise(resolve => setTimeout(resolve, 2000));
    }
  }
}
async function roomCommand(path, body = {}) {
  if (busy || !tableView) return;
  busy = true;
  try {
    let result = await request(path, body);
    if (result.auto_ting_discard !== undefined && (path === '/api/rooms' || path === '/api/room/join')) {
      result = await request('/api/preferences', {auto_ting_discard:autoTingDiscard});
    }
    $('modal').close();
    if (!roomMode) acceptRoom(result);
    else state = result;
    rememberPlayerName(result.room.members[0].name);
    selected = null; render();
  } catch (error) { toast(error.message); }
  finally { busy = false; if (state) render(); }
}
function rememberPlayerName(name) {
  playerName = name;
  localStorage.setItem('qinghe-player-name',name);
}
function nameField(label = '玩家名稱（可選）') {
  return `<label class="setting-row player-name-row" for="player-name">${label}<span><input id="player-name" autocomplete="nickname" placeholder="留空使用預設名稱"><button id="random-name" class="name-random" type="button">隨機</button></span></label>`;
}
function setupNameField(name = playerName) {
  $('player-name').value = name;
  $('random-name').onclick = () => {
    $('player-name').value = randomPlayerName($('player-name').value);
  };
}
function showRename() {
  modal('修改顯示名稱', `<form id="rename-player">${nameField('顯示名稱')}<div class="join-buttons"><button class="modal-primary" type="submit">儲存</button><button class="outline" id="cancel-rename" type="button">取消</button></div></form>`);
  setupNameField(names[0]);
  $('player-name').required = true;
  $('player-name').focus(); $('player-name').select();
  $('cancel-rename').onclick = () => $('modal').close();
  $('rename-player').onsubmit = async event => {
    event.preventDefault();
    if (busy) { toast('請稍候再儲存'); return; }
    busy = true;
    const button = event.submitter;
    if (button) button.disabled = true;
    try {
      state = await request('/api/player/name', {name:$('player-name').value});
      rememberPlayerName(state.room ? state.room.members[0].name : state.player_name);
      $('modal').close(); render();
    } catch (error) { toast(error.message); }
    finally { busy = false; if (button) button.disabled = false; if (state) render(); }
  };
}
function showJoinRoom(code) {
  modal('加入房間',`<p>按下「加入房間」後才會佔用座位。</p><form id="confirm-join"><label class="setting-row" for="invite-code">房號<input id="invite-code" readonly></label>${nameField()}<div class="join-buttons"><button class="modal-primary" type="submit">加入房間</button><button class="name-random" id="cancel-join" type="button">先不加入</button></div></form>`);
  $('invite-code').value = code.toUpperCase();
  setupNameField();
  $('confirm-join').onsubmit = event => {
    event.preventDefault();
    roomCommand('/api/room/join',{code:$('invite-code').value,name:$('player-name').value});
  };
  $('cancel-join').onclick = () => {
    $('modal').close();
    if (!roomMode) {
      const url = new URL(location.href);
      url.searchParams.delete('room');
      history.replaceState(null,'',url);
    }
  };
}
async function leaveRoom() {
  if (busy) return;
  busy = true;
  try {
    await request('/api/room/leave', {});
    roomMode = false; ++pollGeneration;
    sessionStorage.removeItem('qinghe-room');
    const url = new URL(location.href); url.searchParams.delete('room');
    history.replaceState(null, '', url);
    state = await request('/api/state'); selected = null; tingPassed = false; tingMode = false;
    if (state.auto_ting_discard !== undefined) {
      state = await request('/api/preferences', {auto_ting_discard:autoTingDiscard});
    }
    $('modal').close(); render();
  } catch (error) { toast(error.message); }
  finally { busy = false; if (state) render(); }
}
$('multiplayer').onclick = () => {
  if (roomMode) {
    modal('房間選單', '<p>將網址傳給朋友，對方確認加入後才會佔位。對局中也可加入，接替電腦空位並保留該座位牌局。</p><label class="setting-row">邀請網址<input id="invite-url" readonly></label><div class="join-buttons"><button class="modal-primary" id="copy-invite" aria-live="polite">複製邀請網址</button><button class="outline" id="room-leave">離開房間</button></div>');
    $('room-leave').onclick = $('new-game').onclick;
    $('room-leave').disabled = busy;
    $('invite-url').value = location.href;
    $('copy-invite').onclick = async () => {
      const button = $('copy-invite');
      const input = $('invite-url');
      button.disabled = true;
      button.textContent = '複製中…';
      delete button.dataset.copyState;
      try {
        await navigator.clipboard.writeText(input.value);
        button.textContent = '已複製';
        button.dataset.copyState = 'copied';
      } catch {
        input.focus();
        input.select();
        input.setSelectionRange(0,input.value.length);
        button.textContent = '請長按網址複製';
        button.dataset.copyState = 'failed';
      } finally { button.disabled = false; }
    };
  } else {
    modal('與朋友同桌', `<p>建立房間後分享邀請網址，最多四人，空位由電腦補上。</p>${nameField()}<button class="modal-primary" id="create-room">建立房間</button><form id="join-room"><label class="setting-row">房號<input id="room-code" required minlength="8" maxlength="8" pattern="[a-fA-F0-9]{8}" autocomplete="off" placeholder="八碼房號"></label><button class="outline" type="submit">加入房間</button></form>`);
    setupNameField();
    $('create-room').onclick = () => roomCommand('/api/rooms',{name:$('player-name').value});
    $('join-room').onsubmit = event => {
      event.preventDefault(); roomCommand('/api/room/join', {code:$('room-code').value.trim(),name:$('player-name').value});
    };
  }
};
(async()=>{
  try {
    const { MahjongTableView } = await import('./table3d.js?v=round-wind-ring-1');
    tableView = new MahjongTableView(document.querySelector('.table'),undefined,tileFont);
    tableView.onProject = syncProjection;
    tableView.renderer.shadowMap.enabled=!compact;
    setTableStatus('正在載入牌面…');
    await tableView.ready;
    setTableStatus('正在連線…');
    const code = new URL(location.href).searchParams.get('room');
    state = await request('/api/state');
    if (!state.room && playerName && state.player_name === '玩家') {
      state = await request('/api/player/name', {name:playerName});
    }
    if (state.auto_ting_discard !== undefined) {
      state = await request('/api/preferences', {auto_ting_discard:autoTingDiscard});
    }
    if (!state.room) sessionStorage.removeItem('qinghe-room');
    if (state.room && !roomMode) acceptRoom(state);
    render();
    if (code && (!state.room || state.room.code !== code.toUpperCase())) showJoinRoom(code);
    else if (state.done) showResult();
  } catch (e) {
    setTableStatus(e.status ? `${e.message}\n可從房間資訊開啟「牌局紀錄／續局」。`
      : '牌桌載入失敗，請重新整理重試。');
    toast(e.status ? e.message : '無法載入 3D 牌桌，請重新整理或使用支援 WebGL 的瀏覽器。');
    console.error(e);
  }
})();
