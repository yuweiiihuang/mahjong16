import Sortable from './vendor/sortable.core.esm.js';
import { DEFAULT_ORDER, validOrder, sortHand } from './hand-sort.mjs';
import { TILE_FONTS, DEFAULT_TILE_FONT, validTileFont, tileAsset } from './tile-fonts.mjs?v=imahjong-full-4';
import { loadTileImage } from './tile-images.mjs';
import { randomPlayerName } from './player-names.mjs?v=selected-names-8';

const $ = id => document.getElementById(id);
let playerName = localStorage.getItem('qinghe-player-name') || '';
let names = [playerName || '玩家', '陳予安', '林小滿', '周子墨'];
const winds = ['東', '南', '西', '北'];
const labels = {DISCARD:'出牌', TING:'聽', HU:'胡', PASS:'過', CHI:'吃', PONG:'碰', GANG:'槓', ANGANG:'暗槓', KAKAN:'加槓', DRAW_GAME:'流局'};
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
  if (busy) return;
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
function person(pid, sidebar = false) {
  const wrap = document.createElement('div'); wrap.className = sidebar ? 'player-row' : 'seat-person';
  const wind = winds[['E','S','W','N'].indexOf(state.seat_winds[pid])];
  wrap.innerHTML=`<div class="avatar a${pid}">${escapeHtml(Array.from(names[pid])[0])}</div><div class="player-info"><strong>${escapeHtml(names[pid])}${state.dealer===pid?'<span class="dealer">莊</span>':''}</strong><small>${wind}家 · ${state.totals[pid]} 點${state.players[pid].ting?' · 已宣告聽牌':''}</small></div>`;
  if (state.room) {
    const member = state.room.members[pid];
    const detail = wrap.querySelector('small');
    detail.textContent += member.human ? (member.connected ? ' · 真人' : ' · 暫時離線') : ' · 電腦';
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
  if (tableView && state) tableView.update(state, chiSelection?.mode === 'tiles'
    ? {chiCards:chiSelection.picked} : tingMode
    ? {tingCandidates:state.legal_actions.filter(action => action.type === 'TING')}
    : selected, sortOrder);
}
function syncProjection(view) {
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
    button.disabled = busy || (chiSelection?.mode === 'tiles' && !canPickChi(action))
      || (tingMode && !state.legal_actions.some(candidate =>
      candidate.type === 'TING' && candidate.tile === action.tile && candidate.from === action.from));
    button.setAttribute('aria-pressed', String(box.selected));
    button.onclick = () => selectHandTile(action);
    button.style.cssText = `left:${box.left}px;top:${box.top}px;width:${box.width}px;height:${box.height}px`;
    if (hand.children[position] !== button) hand.insertBefore(button, hand.children[position] || null);
  });
  for (const button of existing.values()) button.remove();
  const actionBar = document.querySelector('.action-bar');
  const actionY = view.project([0,.5,9.4]).y;
  actionBar.style.top = `${actionY}px`;
  $('ting-panel').style.top = `${actionY}px`;
  const positions = {2:[0,2.5,-10.3],3:[-12.2,2.2,-3.1],1:[12.2,2.2,-3.1]};
  const order = state.seating_order;
  for (const pid of [1,2,3]) {
    const seat = (order.indexOf(pid) - order.indexOf(0) + 4) % 4;
    const p=view.project(positions[seat]); const el=$(`seat-${pid}`);
    el.style.left=`${p.x}px`;el.style.top=`${p.y}px`;
  }
}
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
    const result = actionButton('結算明細', null); result.onclick = showResult;
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
  if(state.done){const b=actionButton('下一局',null,true);b.onclick=()=>newGame(true);target.append(b);const result=actionButton('結算明細',null);result.onclick=showResult;target.append(result);return;}
  if(state.phase==='TURN'){
    for(const a of state.legal_actions.filter(a=>!['DISCARD','TING'].includes(a.type))) target.append(actionButton(a.type==='HU'&&a.source==='TSUMO'?'自摸':labels[a.type],a,true));
    if (!tingPassed && state.legal_actions.some(action => action.type === 'TING')) {
      const ting = actionButton('聽', {type:'TING'});
      ting.setAttribute('aria-pressed', String(tingMode));
      ting.onclick = () => {
        if (busy) return;
        const declaration = selected && state.legal_actions.find(action => action.type === 'TING'
          && action.tile === selected.tile && action.from === selected.from);
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
  });
}
function renderTing() {
  const target = $('ting-panel');
  target.replaceChildren();
  const options = uniqueTingOptions(state.ting_options.length
    ? state.ting_options : state.ting_waits.length ? [{waits:state.ting_waits}] : []);
  target.hidden = !options.length || state.done || Boolean(state.room && !state.room.started);
  if (target.hidden) return;
  const header = document.createElement('summary'); header.className = 'ting-heading';
  const label = document.createElement('span'); label.textContent = '聽牌提示';
  header.title = '數字是未見牌數，包含對手手牌及尾牌，不代表牌牆可摸張數。';
  header.append(label); target.append(header);
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
    row.append(waits); target.append(row);
  }
}
function render(){
  if (state.done || playbackFrame || !state.legal_actions.some(a => a.type === 'TING')) tingMode = false;
  const waiting = state.room && !state.room.started;
  const humans = waiting ? state.room.members.filter(member => member.human).length : 0;
  setTableStatus(waiting ? `等待開局 · 已有 ${humans} 位玩家\n${state.room.host
    ? '邀請朋友加入後，按「開始對局」。空位由電腦補上。' : '等待房主開始對局。'}` : '');
  names = state.room ? state.room.members.map(member => member.name)
    : [playerName || '玩家', '陳予安', '林小滿', '周子墨'];
  $('room-name').textContent = state.room ? `房間 ${state.room.code}` : '自由練習';
  $('table-title').textContent = state.room ? (state.room.started ? '朋友牌桌' : '等待朋友入座') : '練習牌桌';
  $('opponent-type').textContent = state.room ? '朋友與電腦' : '電腦玩家';
  $('table-caption').textContent = state.room ? '台灣十六張 · 朋友連線' : '台灣十六張 · 單人練習';
  $('connection-status').textContent = state.room ? '房間已連線' : '練習模式';
  $('new-game').textContent = state.room ? '離開房間' : '↻　重新開桌';
  $('remaining').textContent=state.remaining;
  $('round').textContent=`第 ${state.round} 局`;
  $('round-wind').textContent=`${winds[['E','S','W','N'].indexOf(state.quan_feng)]}風圈`;
  $('dealer-status').textContent=`${names[state.dealer]}${state.dealer_streak ? ` · 連莊 ${state.dealer_streak}` : ' · 起莊'}`;
  const order = state.seating_order, ownSeat = order.indexOf(0);
  ['.wind-bottom','.wind-right','.wind-top','.wind-left'].forEach((selector, seat) => {
    const pid = order[(ownSeat + seat) % 4];
    const el = document.querySelector(selector);
    el.textContent = winds[['E','S','W','N'].indexOf(state.seat_winds[pid])];
    el.classList.toggle('active', !state.done && state.phase !== 'REACTION' && pid === state.actor);
  });
  document.querySelector('.compass').setAttribute('aria-label',
    state.room && !state.room.started ? '等待朋友入座' :
      `剩餘 ${state.remaining} 張；${state.done ? '本局結束' : state.phase === 'REACTION' || state.actor === null ? '等待回應' : `輪到${winds[['E','S','W','N'].indexOf(state.seat_winds[state.actor])]}家`}`);
  $('player-list').replaceChildren(...names.map((_,p)=>person(p,true)));
  for (const pid of [1,2,3]) $(`seat-${pid}`).replaceChildren(person(pid));
  $('me').replaceChildren(...person(0).childNodes);
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
  const response=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data=await response.json();
  if(!response.ok){const error=new Error(data.error||'連線失敗');error.status=response.status;throw error;}
  return data;
}
async function present(result) {
  const {playback = [], ...finalState} = result;
  selected = null;
  try {
    for (const frame of playback) {
      playbackFrame = frame;
      state = {...frame.state, actor:frame.pid};
      render();
      if (['DISCARD','TING'].includes(frame.type)) {
        beep();
        await tableView.animateDiscard(frame.pid);
      } else if (frame.type !== 'THINK') beep();
      const delay = frame.type === 'THINK' ? 500 + Math.random()*250
        : frame.state.done ? 1200 : ['DISCARD','TING'].includes(frame.type) ? 450 : 700;
      await new Promise(resolve => setTimeout(resolve, delay * {fast:.35,natural:1,relaxed:1.6}[pace]));
    }
  } finally {
    playbackFrame = null;
    state = finalState;
    render();
  }
  if (state.done) showResult();
}
async function perform(action){
  if(!action||busy)return;
  pendingReaction = state.phase === 'REACTION' ? action : null;
  chiSelection=null;tingMode=false;tingPassed=false;busy=true;renderActions();renderHand();
  try{
    const move = Object.fromEntries(Object.entries(action).filter(([key])=>key!=='index'));
    if (roomMode) {
      state = await request('/api/room/action', {action:move, version:state.version, request_id:crypto.randomUUID()});
      pendingReaction = null;
      selected = null;
      render();
      if (['DISCARD','TING'].includes(state.display_event?.type)) {
        beep(); await tableView.animateDiscard(state.display_event.pid);
      }
    } else {
      const result = await request('/api/action', move);
      pendingReaction = null;
      await present(result);
    }
  }
  catch(e){toast(e.message);try{state=await request(roomMode ? '/api/room/state' : '/api/state');selected=null;}catch{}}
  finally{pendingReaction=null;busy=false;render();if(roomMode && state.done)showResult();}
}
async function newGame(next = false){
  tingPassed = false;
  if (roomMode) return roomCommand('/api/room/next');
  if(busy)return;busy=true;$('new-game').disabled=true;
  try{const result=await request(next ? '/api/next' : '/api/new',{});$('modal').close();await present(result);if(!state.done)toast(next?'下一局開始，點數已保留。':'新牌桌開始，每位玩家 1,000 點。');}
  catch(e){toast(e.message);}finally{busy=false;$('new-game').disabled=false;if(state)render();}
}
function modal(title, content, className = ''){
  $('toast').classList.remove('visible');
  $('modal').className = className;
  $('modal-content').innerHTML=`<h2>${escapeHtml(title)}</h2>${content}<p id="modal-status" role="status" hidden></p>`;
  if(!$('modal').open)$('modal').showModal();}
function showResult(){
  const winner=state.winner;
  const result = state.settlement;
  const flower = {qi_qiang_yi:'七搶一', ba_xian:'八仙過海'}[result.flower_win_type];
  modal(winner===null?'本局流局':`${names[winner]}${flower || (state.win_source==='TSUMO'?'自摸':'胡牌')}`,`<p>${winner===null?'本局無輸贏，莊家續莊。':`${result.tai} 台 · 底 ${result.base_points} 點／每台 ${result.tai_points} 點${result.payer!==null?` · ${escapeHtml(names[result.payer])} 放銃`:''}`}</p><div class="result-hand" id="result-hand"></div><div id="score-breakdown"></div><table class="settlement-table"><thead><tr><th>玩家</th><th>本局</th><th>累積點數</th></tr></thead><tbody id="score-players"></tbody></table><p>莊家付款可能另含莊家台。</p><button class="modal-primary" id="result-new">下一局　→</button>`, 'result-dialog');
  for(const id of state.winning_hand||[])$('result-hand').append(tile(id));
  if(winner!==null && !result.flower_win_type)melds(winner,$('result-hand'));
  for (const item of result.breakdown) {
    const row = document.createElement('div'); row.className = 'score-row';
    const label = document.createElement('span'); label.textContent = item.label;
    const count = document.createElement('strong'); count.textContent = `${item.points} 台`;
    row.append(label, count); $('score-breakdown').append(row);
  }
  names.forEach((name, pid) => {
    const row = document.createElement('tr');
    for (const text of [name, `${result.payments[pid] > 0 ? '+' : ''}${result.payments[pid]}`, state.totals[pid]]) {
      const cell = document.createElement('td'); cell.textContent = text; row.append(cell);
    }
    $('score-players').append(row);
  });
  $('result-new').disabled = !!state.room && !state.room.host;
  if (state.room && !state.room.host) $('result-new').textContent = '等待房主開啟下一局';
  $('result-new').onclick=()=>newGame(true);
}
$('help').onclick=()=>modal('遊戲說明',`<p>${roomMode ? "與朋友和電腦玩家同桌，操作與計分由伺服器同步。" : "與三位電腦玩家一起練習台灣十六張麻將。"}</p><ol><li>每家起手 16 張，輪到你時會自動摸牌。</li><li>點選手牌或摸牌，再點一次已選中的同一張牌出牌，兩次點擊不限制速度。</li><li>有人出牌時，符合規則的吃、碰、槓、胡與過會出現在右下方。吃牌有多種組合時，點「吃」後再選擇牌組。</li><li>花牌會自動補花。可聽牌時，右下角會顯示提示。按「聽」讓候選牌跳起，再點一張即可出牌並宣告聽牌。再按「聽」可取消選擇模式。</li><li>五組面子與一對將眼即可胡牌。牌牆保留尾牌；可摸牌用盡則流局。</li></ol><p>本局結束會顯示台數明細與四家輸贏；下一局保留點數，依結果連莊或輪莊。提示牌面旁的數字代表未見張數。重新開桌會清除累積點數。${roomMode ? "斷線後保留座位，超過 90 秒由電腦接手；回到原瀏覽器即可繼續。" : "這是單人練習桌，不含帳戶與金流。"}</p>`);
$('table-nav').onclick=()=>$('modal').close();
$('close-modal').onclick=()=>$('modal').close();
$('modal').onclick=e=>{if(e.target===$('modal')){const r=$('modal').getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)$('modal').close();}};
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
  settingsSortable?.destroy();
  settingsSortable = null;
});

$('settings').onclick=()=>{
  settingsOrder = [...sortOrder];
  modal('牌桌設定',`
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
$('history').onclick=()=>{
  modal('對局紀錄','<div class="history-scroll" id="history-list"></div>');
  if(!state.events.length)$('history-list').innerHTML='<p>對局剛開始，出牌後就會出現紀錄。</p>';
  for(const event of [...state.events].reverse()){
    if(event.type==='PASS')continue;
    const row=document.createElement('div');row.className='history-row';
    const label=document.createElement('span');label.textContent=`${names[event.pid]} · ${labels[event.type]||event.type}`;row.append(label);
    if(event.tile!==undefined && !(event.pid!==0 && event.type==='ANGANG'))row.append(tile(event.tile,true));
    for(const id of event.use||[])row.append(tile(id,true));$('history-list').append(row);
  }
};
$('new-game').onclick=()=>{if(!state)return;if(roomMode){modal('離開房間？','<p>離開後將由電腦接手。本局開始後無法重新加入。</p><button class="modal-primary" id="confirm-leave">離開房間</button>');$('confirm-leave').onclick=leaveRoom;return;}modal('重新開桌？','<p>目前的對局與累積點數會清除，每位玩家回到 1,000 點，從東風圈開始。</p><button class="modal-primary" id="confirm-new">重新開桌</button>');$('confirm-new').onclick=()=>newGame();};
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
        if (old.version !== result.version) selected = null;
        render();
        if (state.done && (!old.done || old.room.host !== state.room.host)) showResult();
        else if (old.done && !state.done) $('modal').close();
        const event = state.display_event;
        if (old.version !== state.version && event && ['DISCARD','TING'].includes(event.type)) {
          beep(); await tableView.animateDiscard(event.pid);
        }
      }
    } catch (error) {
      if (!roomMode || generation !== pollGeneration) return;
      if (error.status === 400) { toast(error.message); await leaveRoom(); return; }
      $('connection-status').textContent = '重新連線中…';
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
function nameField() {
  return '<label class="setting-row player-name-row" for="player-name">玩家名稱（可選）<span><input id="player-name" maxlength="20" autocomplete="nickname" placeholder="留空使用預設名稱"><button id="random-name" class="name-random" type="button">隨機</button></span></label>';
}
function setupNameField(name = playerName) {
  $('player-name').value = name;
  $('random-name').onclick = () => {
    $('player-name').value = randomPlayerName($('player-name').value);
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
    modal('邀請朋友', '<p>將網址傳給朋友，對方確認加入後才會佔位。開局前皆可加入。</p><label class="setting-row">邀請網址<input id="invite-url" readonly></label><button class="modal-primary" id="copy-invite" aria-live="polite">複製邀請網址</button>');
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
    const { MahjongTableView } = await import('./table3d.js?v=chi-hand-selection-1');
    tableView = new MahjongTableView(document.querySelector('.table'),undefined,tileFont);
    tableView.onProject = syncProjection;
    tableView.renderer.shadowMap.enabled=!compact;
    setTableStatus('正在載入牌面…');
    await tableView.ready;
    setTableStatus('正在連線…');
    const code = new URL(location.href).searchParams.get('room');
    state = await request('/api/state');
    if (state.auto_ting_discard !== undefined) {
      state = await request('/api/preferences', {auto_ting_discard:autoTingDiscard});
    }
    if (!state.room) sessionStorage.removeItem('qinghe-room');
    if (state.room && !roomMode) acceptRoom(state);
    render();
    if (code && (!state.room || state.room.code !== code.toUpperCase())) showJoinRoom(code);
    else if (state.done) showResult();
  } catch (e) {
    setTableStatus('牌桌載入失敗，請重新整理重試。');
    toast('無法載入 3D 牌桌，請重新整理或使用支援 WebGL 的瀏覽器。');
    console.error(e);
  }
})();
