const $ = id => document.getElementById(id);
const names = ['你', '陳予安', '林小滿', '周子墨'];
const winds = ['東', '南', '西', '北'];
const labels = {DISCARD:'出牌', TING:'聽', HU:'胡', PASS:'過', CHI:'吃', PONG:'碰', GANG:'槓', ANGANG:'暗槓', KAKAN:'加槓'};
let state, selected = null, busy = false, round = 1, sorted = true;
let sound = localStorage.getItem('qinghe-sound') === 'true';
let compact = localStorage.getItem('qinghe-flat') === 'true';
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
  wrap.innerHTML=`<div class="avatar a${pid}">${pid===0?'禾':names[pid][0]}</div><div class="player-info"><strong>${names[pid]}${state.dealer===pid?'<span class="dealer">莊</span>':''}</strong><small>${winds[pid]}家${pid===0?' · 你': ' · 電腦'}${state.players[pid].ting?' · 已聽牌':''}</small></div>`;
  return wrap;
}
function melds(pid, target, small = true) {
  for(const meld of state.players[pid].melds){
    const group=document.createElement('div');group.className='meld-group';group.title=labels[meld.type]||meld.type;
    for(const id of meld.tiles) group.append(tile(id,small));target.append(group);
  }
}
function renderHand() {
  if (tableView && state) tableView.update(state, selected, sorted);
}
function syncProjection(view) {
  $('hand').setAttribute('aria-label', `手牌：${state ? state.hand.map(tileName).join('、') : ''}`);
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
  for (const [pid, point] of Object.entries(positions)) {
    const p=view.project(point); const el=$(`seat-${pid}`);
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
  if(state.done){const b=actionButton('再來一局',null,true);b.onclick=()=>newGame();target.append(b);return;}
  if(state.phase==='TURN'){
    const sort=document.createElement('button');sort.textContent='理牌';sort.disabled=busy;
    sort.onclick=()=>{sorted=!sorted;selected=null;renderHand();renderActions();};target.append(sort);
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
}
function render(){
  $('remaining').textContent=state.remaining;
  $('round').textContent=`第 ${round} 局`;
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
async function newGame(){
  if(busy)return;busy=true;$('new-game').disabled=true;
  try{state=await request('/api/new',{});round++;selected=null;$('modal').close();render();toast('新局開始，祝你手氣順心。');}
  catch(e){toast(e.message);}finally{busy=false;$('new-game').disabled=false;if(state)render();}
}
function modal(title, content){$('modal-content').innerHTML=`<h2>${title}</h2>${content}`;if(!$('modal').open)$('modal').showModal();}
function showResult(){
  const winner=state.winner;
  modal(winner===null?'本局流局':`${names[winner]}${state.win_source==='TSUMO'?'自摸':'胡牌'}`,`<p>${winner===null?'可摸牌已用盡，這一局沒有贏家。':'本局結束，看看贏家的牌型，準備下一場。'}</p><div class="result-hand" id="result-hand"></div><button class="modal-primary" id="result-new">再來一局　→</button>`);
  for(const id of state.winning_hand||[])$('result-hand').append(tile(id));
  if(winner!==null)melds(winner,$('result-hand'));
  $('result-new').onclick=newGame;
}
$('help').onclick=()=>modal('台灣十六張，從容開局',`<p>與三位電腦玩家一起練習台灣十六張麻將。</p><ol><li>每家起手 16 張，輪到你時會自動摸牌。</li><li>點選手牌或摸牌，再按「出牌」。也可以雙擊牌面或按 Enter 確認。</li><li>有人出牌時，符合規則的吃、碰、槓、胡與過會出現在右下方。吃牌有多種組合時，可直接選擇所需的兩張牌。</li><li>花牌會自動補花。可聽牌時，選中對應棄牌後會出現「聽牌」。</li><li>五組面子與一對將眼即可胡牌。牌牆保留尾牌；可摸牌用盡則流局。</li></ol><p>這是單人練習桌，目前顯示本局結果，不含帳戶、金流與累積台數結算。</p>`);
$('table-nav').onclick=()=>$('modal').close();
$('close-modal').onclick=()=>$('modal').close();
$('modal').onclick=e=>{if(e.target===$('modal')){const r=$('modal').getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)$('modal').close();}};
$('sound').onclick=()=>{sound=!sound;localStorage.setItem('qinghe-sound',sound);updateSound();beep();toast(sound?'音效已開啟':'音效已關閉');};
function updateSound(){$('sound').innerHTML=`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9h4l5-4v14l-5-4H4z"/>${sound?'<path d="M16 8q4 4 0 8M19 5q7 7 0 14"/>':'<path d="m17 9 5 6m0-6-5 6"/>'}</svg>`;$('sound').setAttribute('aria-label',sound?'關閉音效':'開啟音效');$('sound').setAttribute('aria-pressed',String(sound));}
updateSound();
$('settings').onclick=()=>{
  modal('牌桌設定',`<label class="setting-row">操作音效<input id="sound-setting" type="checkbox" ${sound?'checked':''}></label><label class="setting-row">減少桌面陰影<input id="flat-setting" type="checkbox" ${compact?'checked':''}></label><p>設定會儲存在這個瀏覽器。對局依台灣十六張規則進行，花牌自動補花。</p>`);
  $('sound-setting').onchange=e=>{sound=e.target.checked;localStorage.setItem('qinghe-sound',sound);updateSound();};
  $('flat-setting').onchange=e=>{compact=e.target.checked;localStorage.setItem('qinghe-flat',compact);document.body.classList.toggle('compact',compact);if(tableView){tableView.renderer.shadowMap.enabled=!compact;tableView.draw();}};
};
$('history').onclick=()=>{
  modal('對局紀錄','<div class="history-scroll" id="history-list"></div>');
  if(!state.events.length)$('history-list').innerHTML='<p>對局剛開始，出牌後就會出現紀錄。</p>';
  for(const event of [...state.events].reverse()){
    if(event.type==='PASS')continue;
    const row=document.createElement('div');row.className='history-row';
    const label=document.createElement('span');label.textContent=`${names[event.pid]} · ${labels[event.type]||event.type}`;row.append(label);
    if(event.tile!==undefined)row.append(tile(event.tile,true));
    for(const id of event.use||[])row.append(tile(id,true));$('history-list').append(row);
  }
};
$('new-game').onclick=()=>{if(!state||state.done||!state.events.length){newGame();return;}modal('重新開局？','<p>目前的對局會結束，重新發牌開始一局。</p><button class="modal-primary" id="confirm-new">重新開局</button>');$('confirm-new').onclick=newGame;};
document.addEventListener('keydown',e=>{if(e.key==='Enter'&&!$('modal').open&&selected&&!busy){e.preventDefault();perform(selected);}});
(async()=>{
  try {
    const { MahjongTableView } = await import('./table3d.js');
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
