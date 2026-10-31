import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../../ui/web/app.js', import.meta.url), 'utf8');
const readLevels = source.slice(source.indexOf('  const readAiLevels ='),
  source.indexOf('  const updateAiNote ='));
const handler = source.slice(source.indexOf("  $('save-settings').onclick=async"),
  source.indexOf("\n};\n$('new-game').onclick"));

test('settings save syncs preferences, preserves newer dialogs and restores controls after failure', async () => {
  for (const [replaced, roomMode, failure, done] of [
    [false,false], [true,false], [false,true], [false,false,'font'], [false,true,'request'], [false,false,null,true],
  ]) {
    let finish, closed = 0, presented = 0;
    const stored = new Map(), requests = [], messages = [];
    const nodes = {
      'save-settings': {}, 'tile-font-setting': {value:'mahjong-jp'},
      'sound-setting': {checked:false}, 'flat-setting': {checked:false},
      'auto-ting-setting': {checked:false},
      'pace-setting': {value:roomMode ? 'shared' : 'natural'}, modal:{close() { closed++; }},
    };
    const context = vm.createContext({
      $:id => nodes[id], settingsOrder:[0,1,2,3], state:{auto_ting_discard:true,done}, roomMode, pace:'fast',
      tableView:{
        setFaceFont:() => new Promise((resolve,reject) => {
          finish = () => failure === 'font' ? reject(new Error('font failed')) : resolve();
        }),
        renderer:{shadowMap:{}},
      },
      localStorage:{setItem:(key,value) => stored.set(key,value)},
      document:{querySelector:() => ({value:'tiles'}), querySelectorAll:() => [], body:{classList:{toggle() {}}}},
      updateSound() {}, renderHand() {}, renderActions() {}, toast:message => messages.push(message),
      busy:false, request:async (path,body) => {
        requests.push({path,auto_ting_discard:body.auto_ting_discard});
        if (failure === 'request') throw new Error('request failed');
        return {auto_ting_discard:false,done};
      }, present:async () => {presented++;}, render() {},
    });
    vm.runInContext(readLevels + handler, context);
    context.busy = true;
    const blocked = nodes['save-settings'].onclick();
    assert.equal(finish, undefined);
    await blocked;
    assert.equal(context.busy, true);
    assert.equal(stored.size, 0);
    context.busy = false;
    const pending = nodes['save-settings'].onclick();
    assert.equal(context.busy, true);
    assert.equal(nodes['save-settings'].disabled, true);
    if (replaced) nodes['save-settings'] = undefined;
    finish();
    await pending;
    assert.equal(context.busy, false);
    assert.deepEqual(requests,failure === 'font' ? [] : [
      {path:'/api/preferences',auto_ting_discard:false},
    ]);
    if (failure) {
      assert.equal(closed,0);
      assert.equal(stored.size,0);
      assert.equal(nodes['save-settings'].disabled,false);
      assert.equal(nodes['save-settings'].textContent,'儲存');
      assert.deepEqual(messages,['設定儲存失敗，請再試一次']);
      continue;
    }
    assert.equal(closed, replaced ? 0 : 1);
    assert.equal(presented, roomMode || done ? 0 : 1,
      'saving an already completed hand must keep settings until they close');
    assert.equal(stored.get('qinghe-tile-font'), 'mahjong-jp');
    assert.equal(stored.get('qinghe-pace'), roomMode ? 'fast' : 'natural');
    assert.equal(stored.get('qinghe-auto-ting-discard'), 'false');
    assert.equal(stored.get('qinghe-chi-mode'), 'tiles');
  }
});
