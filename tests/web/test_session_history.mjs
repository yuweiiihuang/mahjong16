import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const source = readFileSync(new URL('../../ui/web/app.js', import.meta.url), 'utf8');

test('session header contains the ID and disables resuming the current table only', async () => {
  const element = tag => ({tag, children:[], attrs:{},
    append(...items) {this.children.push(...items);},
    setAttribute(key,value) {this.attrs[key] = value;}});
  const list = element('div');
  const resumed = [];
  const sessions = ['current','other'].map(id => ({id,hand_id:`hand-${id}`,
    started_at:'2026-10-30T00:00:00Z',established:true,completed_hands:3,resumable:true}));
  let healthy = true;
  const ctx = vm.createContext({document:{createElement:element},state:{session_id:'current'},
    $:()=>list,refreshSessionHeaders(){},request:async path=>{
      if (path === '/api/state' && !healthy) throw Error('recording unavailable');
      return {sessions};
    },modal(){},toast(message){throw Error(message);},
    resumeHand:id=>resumed.push(id)});
  vm.runInContext(source.slice(source.indexOf('async function showHistory('),
    source.indexOf('async function resumeHand(')),ctx);
  await ctx.showHistory();
  const headers = list.children.map(card=>card.children[0]);
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
});
