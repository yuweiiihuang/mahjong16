import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const source = readFileSync(new URL('../../ui/web/app.js', import.meta.url), 'utf8');

test('session header contains the ID and disables resuming the current table only', async () => {
  const element = tag => ({tag, children:[], attrs:{}, dataset:{},
    replaceChildren(...items) {this.children = items;},
    append(...items) {this.children.push(...items);},
    setAttribute(key,value) {this.attrs[key] = value;}});
  const list = element('div');
  const resumed = [];
  const requests = [];
  const opened = [];
  const dialog = {open:false,showModal() {
    this.open = true;
    const content = list.children[0]?.children[1].children[0];
    opened.push(Boolean(content?.children.length));
  }};
  const detail = {players:['甲','乙','丙','丁'],seat_winds:['E','S','W','N'],
    totals:[1000,1000,1000,1000],points:[],seats:[],hands:[],draws:0};
  const sessions = ['current','other'].map(id => ({id,hand_id:`hand-${id}`,
    started_at:'2026-10-30T00:00:00Z',established:true,completed_hands:3,resumable:true}));
  sessions.unshift({id:'abandoned',hand_id:'hand-abandoned',
    started_at:'2026-10-30T00:00:00Z',established:false,completed_hands:0,resumable:false});
  sessions.push({id:'unfinished',hand_id:'hand-unfinished',
    started_at:'2026-10-30T00:00:00Z',established:false,completed_hands:0,resumable:true});
  sessions.push({id:'read-only',hand_id:'hand-read-only',
    started_at:'2026-10-30T00:00:00Z',established:true,completed_hands:1,resumable:false});
  let healthy = true;
  const ctx = vm.createContext({document:{createElement:element},state:{session_id:'current'},
    $:id=>id === 'modal' ? dialog : list,winds:['東','南','西','北'],refreshSessionHeaders(){},request:async path=>{
      requests.push(path);
      if (path === '/api/state' && !healthy) throw Error('recording unavailable');
      return path.startsWith('/api/session?') ? detail : {sessions};
    },modal(title,html,className,show = true){if(show) dialog.showModal();},toast(message){throw Error(message);},
    resumeHand:id=>resumed.push(id)});
  vm.runInContext(source.slice(source.indexOf('async function showHistory('),
    source.indexOf('async function resumeHand(')),ctx);
  await Promise.all([ctx.showHistory(),ctx.showHistory()]);
  assert.equal(requests.filter(path=>path==='/api/sessions').length,1,
    'repeated clicks during loading must share one opening');
  assert.deepEqual(opened,[true],'open the dialog with its initial Session already rendered');
  const headers = list.children.map(card=>card.children[0]);
  assert.deepEqual(headers.map(header => header.children.find(el=>el.className==='session-id').textContent),
    ['ID current','ID other','ID unfinish','ID read-onl'],
    'hide only unfinished sessions that cannot be resumed');
  assert.equal(list.children[0].open,true);
  assert.equal(headers[0].children.find(el=>el.className==='session-id').textContent,'ID current');
  const buttons = headers.map(header=>header.children.find(el=>el.tag==='button'));
  assert.equal(buttons[0].disabled,true);
  assert.equal(buttons[1].disabled,false);
  let stopped = false;
  buttons[1].onclick({stopPropagation(){stopped = true;}});
  assert.equal(stopped,true,'resume should not also toggle the details');
  assert.deepEqual(resumed,['hand-other']);
  healthy = false;
  list.children = [];
  await ctx.showHistory();
  const recovery = list.children[0].children[0].children.find(el=>el.tag==='button');
  assert.equal(recovery.disabled,false,'a frozen current table must remain recoverable');
  assert.equal(recovery.textContent,'恢復此 Session');
  recovery.onclick({stopPropagation(){}});
  assert.deepEqual(resumed,['hand-other','hand-current']);
  healthy = true;
  ctx.state.room = {code:'ABCD'};
  const current = sessions.find(session => session.id === 'current');
  current.source = 'multiplayer'; current.room_code = 'ABCD';
  list.children = [];
  await ctx.showHistory();
  const roomHeader = list.children[0].children[0];
  assert.equal(roomHeader.children.find(el=>el.className==='session-mode').textContent,
    '多人 · 房間 ABCD');
  const roomButton = roomHeader.children.find(el=>el.tag==='button');
  assert.equal(roomButton.textContent,'返回牌桌');
  assert.equal(roomButton.disabled,true);

});
