import Sortable from './vendor/sortable.core.esm.js';
import { DEFAULT_ORDER, validOrder, sortHand } from './hand-sort.mjs';

const $ = id => document.getElementById(id);
const names = ['你', '陳予安', '林小滿', '周子墨'];
const winds = ['東', '南', '西', '北'];
const labels = {DISCARD:'出牌', TING:'聽', HU:'胡', PASS:'過', CHI:'吃', PONG:'碰', GANG:'槓', ANGANG:'暗槓', KAKAN:'加槓'};
let state, selected = null, busy = false;
let sound = localStorage.getItem('qinghe-sound') === 'true';
let compact = localStorage.getItem('qinghe-flat') === 'true';
let sortOrder = [...DEFAULT_ORDER];
try {
  const saved = JSON.parse(localStorage.getItem('qinghe-sort-order'));
  if (validOrder(saved)) sortOrder = saved;
} catch {} // Ignore invalid saved preferences and use the default order.
let audio, tableView;
document.body.classList.toggle('compact', compact);
function tileName(id) {
  if (id < 27) return `${id % 9 + 1}${['萬','筒','條'][Math.floor(id/9)]}`;
  return ['東','南','西','北','中','發','白','春','夏','秋','冬','梅','蘭','竹','菊'][id - 27];
}
function tile(id, small = false, action = null) {
  const el = document.createElement(action ? 'button' : 'span');
  el.className = `tile${small?' small flat':''}${id===31?' red':''}${id===32?' green':''}`;
  el.setAttribute('aria-label',tileName(id));
  el.title = tileName(id);
  const face = document.createElement('img');
  face.className = 'tile-face';
  face.src = `assets/tiles/${id}.svg`;
  face.alt = '';
  face.draggable = false;
  el.append(face);
  if(action){
    el.disabled=busy;
    el.setAttribute('aria-pressed', String(selected?.tile===id && selected?.from===action.from));
    if(selected?.tile===id && selected?.from===action.from) el.classList.add('selected');
    el.onclick=()=>{selected=action;renderHand();renderActions();};
    el.ondblclick=()=>perform(action);
  }
  return el;
}
function person(pid, sidebar = false) {
  const wrap = document.createElement('div'); wrap.className = sidebar ? 'player-row' : 'seat-person';
  const wind = winds[['E','S','W','N'].indexOf(state.seat_winds[pid])];
  wrap.innerHTML=`<div class="avatar a${pid}">${pid===0?'禾':names[pid][0]}</div><div class="player-info"><strong>${names[pid]}${state.dealer===pid?'<span class="dealer">莊</span>':''}</strong><small>${wind}家 · ${state.totals[pid]} 點${state.players[pid].ting?' · 已聽牌':''}</small></div>`;
  return wrap;
}
function melds(pid, target, small = true) {
  for(const meld of state.players[pid].melds){
    const group=document.createElement('div');group.className='meld-group';group.title=labels[meld.type]||meld.type;
    for(const id of meld.tiles) group.append(tile(id,small));target.append(group);
  }
}
function renderHand() {
  if (tableView && state) tableView.update(state, selected, sortOrder);
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
    button.disabled = busy;
    button.setAttribute('aria-pressed', String(box.selected));
    button.onclick = () => { selected=action; renderHand(); renderActions(); };
    button.ondblclick = () => perform(action);
    button.style.cssText = `left:${box.left}px;top:${box.top}px;width:${box.width}px;height:${box.height}px`;
    if (hand.children[position] !== button) hand.insertBefore(button, hand.children[position] || null);
  });
  for (const button of existing.values()) button.remove();
  const center = view.project([0,.1,0]);
  const compass = document.querySelector('.compass');
  compass.style.left = `${center.x}px`; compass.style.top = `${center.y}px`;
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
  button.onclick=()=>perform(action);return button;
}
function renderActions(){
  const target=$('actions');target.replaceChildren();
  if(state.done){const b=actionButton('下一局',null,true);b.onclick=()=>newGame(true);target.append(b);const result=actionButton('結算明細',null);result.onclick=showResult;target.append(result);return;}
  if(state.phase==='TURN'){
    for(const a of state.legal_actions.filter(a=>!['DISCARD','TING'].includes(a.type))) target.append(actionButton(a.type==='HU'&&a.source==='TSUMO'?'自摸':labels[a.type],a,true));
    const ting=selected && state.legal_actions.find(a=>a.type==='TING'&&a.tile===selected.tile&&a.from===selected.from);
    if(ting) target.append(actionButton('聽牌',ting));
    const discard=actionButton('出牌　→',selected,true);discard.disabled=busy||!selected;target.append(discard);
  } else {
    for(const a of state.legal_actions){
      const text=labels[a.type]+(a.use?` ${a.use.map(tileName).join('・')}`:'');
      target.append(actionButton(text,a,a.type!=='PASS'));
    }
  }
  if (state.ting_options.length || state.ting_waits.length) {
    const hints = actionButton('聽牌提示', null);
    hints.onclick = showTing;
    target.prepend(hints);
  }
  const option = selected && state.ting_options.find(a => a.tile === selected.tile && a.from === selected.from);
  $('hint').textContent = option ? `打${tileName(option.tile)} → ${waitText(option.waits)}`
    : state.declared_ting ? waitText(state.ting_waits)
    : state.phase === 'REACTION' ? `有人打出「${tileName(state.last_discard.tile)}」，是否要接牌？`
    : '點選手牌，再按「出牌」';
}
function waitText(waits) {
  return `聽 ${waits.map(w => `${tileName(w.tile)}（未見 ${w.unseen}）`).join('、')}`;
}
function showTing() {
  modal('聽牌提示', '<p>未見張數依自己的牌與公開牌估算，包含對手手牌及尾牌，不代表牌牆可摸張數。</p><div id="ting-list"></div>');
  const options = state.ting_options.length ? state.ting_options : [{waits:state.ting_waits}];
  for (const option of options) {
    const row = document.createElement('div'); row.className = 'ting-row';
    if (option.tile !== undefined) {
      const pick = document.createElement('button'); pick.className = 'ting-pick';
      pick.setAttribute('aria-label', `選擇打${tileName(option.tile)}${option.from === 'drawn' ? '（摸牌）' : ''}`);
      const label = document.createElement('span'); label.textContent = option.from === 'drawn' ? '打摸牌' : '打';
      pick.append(label, tile(option.tile, true));
      pick.onclick = () => {
        selected = state.legal_actions.find(a => a.type === 'DISCARD' && a.tile === option.tile && a.from === option.from);
        $('modal').close(); renderHand(); renderActions();
      };
      row.append(pick);
    }
    const label = document.createElement('span'); label.textContent = '聽'; row.append(label);
    const waits = document.createElement('div'); waits.className = 'wait-tiles';
    for (const wait of option.waits) {
      const item = document.createElement('span'); item.className = 'wait-tile';
      const count = document.createElement('small'); count.textContent = `未見 ${wait.unseen}`;
      item.append(tile(wait.tile, true), count); waits.append(item);
    }
    row.append(waits); $('ting-list').append(row);
  }
}
function render(){
  $('remaining').textContent=state.remaining;
  $('round').textContent=`第 ${state.round} 局`;
  $('round-wind').textContent=`${winds[['E','S','W','N'].indexOf(state.quan_feng)]}風圈`;
  $('dealer-status').textContent=`${names[state.dealer]}${state.dealer_streak ? ` · 連莊 ${state.dealer_streak}` : ' · 起莊'}`;
  const order = state.seating_order, ownSeat = order.indexOf(0);
  ['.wind-bottom','.wind-right','.wind-top','.wind-left'].forEach((selector, seat) => {
    const pid = order[(ownSeat + seat) % 4];
    const el = document.querySelector(selector);
    el.textContent = winds[['E','S','W','N'].indexOf(state.seat_winds[pid])];
    el.classList.toggle('active', pid === state.dealer);
  });
  $('player-list').replaceChildren(...names.map((_,p)=>person(p,true)));
  for (const pid of [1,2,3]) $(`seat-${pid}`).replaceChildren(person(pid));
  $('me').replaceChildren(...person(0).childNodes);
  $('flowers').replaceChildren();
  if(state.flowers.length){const label=document.createElement('small');label.textContent='花牌';$('flowers').append(label);for(const id of state.flowers)$('flowers').append(tile(id,true));}
  $('notice').textContent=state.done?'本局結束':state.phase==='REACTION'?'選擇回應':state.declared_ting?'已聽牌 · 等待好牌':'輪到你出牌';
  $('hint').textContent=state.done?'好牌不怕晚，下局再見。':state.phase==='REACTION'?`有人打出「${tileName(state.last_discard.tile)}」，是否要接牌？`:'點選手牌，再按「出牌」';
  renderHand();renderActions();

}
function beep(){
  if(!sound)return;
  try{audio??=new AudioContext();audio.resume();const o=audio.createOscillator(),g=audio.createGain();o.type='sine';o.frequency.setValueAtTime(660,audio.currentTime);g.gain.setValueAtTime(.05,audio.currentTime);g.gain.exponentialRampToValueAtTime(.001,audio.currentTime+.12);o.connect(g);g.connect(audio.destination);o.start();o.stop(audio.currentTime+.12);}catch{}
}
function toast(message){$('toast').textContent=message;$('toast').classList.add('visible');setTimeout(()=>$('toast').classList.remove('visible'),3500);}
async function request(path,body){
  const response=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data=await response.json();if(!response.ok)throw new Error(data.error||'連線失敗');return data;
}
async function perform(action){
  if(!action||busy)return;busy=true;renderActions();renderHand();
  try{state=await request('/api/action',Object.fromEntries(Object.entries(action).filter(([key])=>key!=='index')));selected=null;beep();render();if(state.done)showResult();}
  catch(e){toast(e.message);try{state=await request('/api/state');selected=null;}catch{}}
  finally{busy=false;render();}
}
async function newGame(next = false){
  if(busy)return;busy=true;$('new-game').disabled=true;
  try{state=await request(next ? '/api/next' : '/api/new',{});selected=null;$('modal').close();render();if(state.done)showResult();else toast(next?'下一局開始，點數已保留。':'新牌桌開始，每位玩家 1,000 點。');}
  catch(e){toast(e.message);}finally{busy=false;$('new-game').disabled=false;if(state)render();}
}
function modal(title, content, className = ''){
  $('modal').className = className;$('modal-content').innerHTML=`<h2>${title}</h2>${content}`;if(!$('modal').open)$('modal').showModal();}
function showResult(){
  const winner=state.winner;
  const result = state.settlement;
  const flower = {qi_qiang_yi:'七搶一', ba_xian:'八仙過海'}[result.flower_win_type];
  modal(winner===null?'本局流局':`${names[winner]}${flower || (state.win_source==='TSUMO'?'自摸':'胡牌')}`,`<p>${winner===null?'本局無輸贏，莊家續莊。':`${result.tai} 台 · 底 ${result.base_points} 點／每台 ${result.tai_points} 點${result.payer!==null?` · ${names[result.payer]} 放銃`:''}`}</p><div class="result-hand" id="result-hand"></div><div id="score-breakdown"></div><table class="settlement-table"><thead><tr><th>玩家</th><th>本局</th><th>累積點數</th></tr></thead><tbody id="score-players"></tbody></table><p>莊家付款可能另含莊家台。</p><button class="modal-primary" id="result-new">下一局　→</button>`, 'result-dialog');
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
  $('result-new').onclick=()=>newGame(true);
}
$('help').onclick=()=>modal('台灣十六張，從容開局',`<p>與三位電腦玩家一起練習台灣十六張麻將。</p><ol><li>每家起手 16 張，輪到你時會自動摸牌。</li><li>點選手牌或摸牌，再按「出牌」。也可以雙擊牌面或按 Enter 確認。</li><li>有人出牌時，符合規則的吃、碰、槓、胡與過會出現在右下方。吃牌有多種組合時，可直接選擇所需的兩張牌。</li><li>花牌會自動補花。可聽牌時，選中對應棄牌後會出現「聽牌」。</li><li>五組面子與一對將眼即可胡牌。牌牆保留尾牌；可摸牌用盡則流局。</li></ol><p>本局結束會顯示台數明細與四家輸贏；下一局保留點數，依結果連莊或輪莊。聽牌提示顯示候選棄牌與未見張數。重新開桌會清除累積點數。這是單人練習桌，不含帳戶與金流。</p>`);
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
    button.append(tile([0, 9, 18, 27][group]));
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
  modal('牌桌設定',`<label class="setting-row">操作音效<input id="sound-setting" type="checkbox" ${sound?'checked':''}></label><label class="setting-row">減少桌面陰影<input id="flat-setting" type="checkbox" ${compact?'checked':''}></label><section class="sort-settings" aria-labelledby="sort-heading"><h3 id="sort-heading">手牌排序</h3><label class="setting-row">常用順序<select id="sort-preset"><option value="0,1,2,3">萬 → 筒 → 條 → 字（預設）</option><option value="1,2,0,3">筒 → 條 → 萬 → 字</option><option value="3,0,1,2">字 → 萬 → 筒 → 條</option><option value="custom" disabled>自訂順序</option></select></label><p id="sort-help">左右拖拉牌圖示調整順序，也可選中後按左右方向鍵。</p><div id="sort-order" class="sort-order" role="group" aria-label="牌種排序" aria-describedby="sort-help"></div></section><div class="settings-footer"><button class="modal-primary" id="save-settings">儲存</button></div>`);
  renderSortSettings();
  $('sort-preset').onchange=e=>setSettingsOrder(e.target.value.split(',').map(Number));
  $('save-settings').onclick=()=>{
    sortOrder = [...settingsOrder];
    sound = $('sound-setting').checked;
    compact = $('flat-setting').checked;
    localStorage.setItem('qinghe-sort-order', JSON.stringify(sortOrder));
    localStorage.setItem('qinghe-sound', sound);
    localStorage.setItem('qinghe-flat', compact);
    updateSound();
    document.body.classList.toggle('compact', compact);
    selected = null;
    if (tableView) tableView.renderer.shadowMap.enabled = !compact;
    renderHand();
    if (state) renderActions();
    $('modal').close();
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
$('new-game').onclick=()=>{if(!state)return;modal('重新開桌？','<p>目前的對局與累積點數會清除，每位玩家回到 1,000 點，從東風圈開始。</p><button class="modal-primary" id="confirm-new">重新開桌</button>');$('confirm-new').onclick=()=>newGame();};
document.addEventListener('keydown',e=>{if(e.key==='Enter'&&!$('modal').open&&selected&&!busy){e.preventDefault();perform(selected);}});
(async()=>{
  try {
    const { MahjongTableView } = await import('./table3d.js?v=kong-stack-3');
    tableView = new MahjongTableView(document.querySelector('.table'));
    tableView.onProject = syncProjection;
    tableView.renderer.shadowMap.enabled=!compact;
    await tableView.ready;
    state = await request('/api/state'); render();
    if (state.done) showResult();
  } catch (e) {
    $('notice').textContent = '牌桌載入失敗';
    toast('無法載入 3D 牌桌，請重新整理或使用支援 WebGL 的瀏覽器。');
    console.error(e);
  }
})();
