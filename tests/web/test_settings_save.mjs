import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../../ui/web/app.js', import.meta.url), 'utf8');
const handler = source.slice(source.indexOf("  $('save-settings').onclick=async"),
  source.indexOf("\n};\n$('new-game').onclick"));

test('a delayed settings save closes its own dialog but preserves a newer dialog', async () => {
  for (const [replaced, roomMode] of [[false,false], [true,false], [false,true]]) {
    let finish, closed = 0;
    const stored = new Map();
    const nodes = {
      'save-settings': {}, 'tile-font-setting': {value:'mahjong-jp'},
      'sound-setting': {checked:false}, 'flat-setting': {checked:false},
      'auto-ting-setting': {checked:false},
      'pace-setting': {value:roomMode ? 'shared' : 'natural'}, modal:{close() { closed++; }},
    };
    const context = vm.createContext({
      $:id => nodes[id], settingsOrder:[0,1,2,3], state:null, roomMode, pace:'fast',
      tableView:{
        setFaceFont:() => new Promise(resolve => { finish = resolve; }),
        renderer:{shadowMap:{}},
      },
      localStorage:{setItem:(key,value) => stored.set(key,value)},
      document:{querySelector:() => ({value:'tiles'}), querySelectorAll:() => [], body:{classList:{toggle() {}}}},
      updateSound() {}, renderHand() {}, renderActions() {}, toast() {},
      busy:false, request:async () => ({}), present:async () => {}, render() {},
    });
    vm.runInContext(handler, context);
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
    assert.equal(closed, replaced ? 0 : 1);
    assert.equal(stored.get('qinghe-tile-font'), 'mahjong-jp');
    assert.equal(stored.get('qinghe-pace'), roomMode ? 'fast' : 'natural');
    assert.equal(stored.get('qinghe-auto-ting-discard'), 'false');
    assert.equal(stored.get('qinghe-chi-mode'), 'tiles');
  }
});
