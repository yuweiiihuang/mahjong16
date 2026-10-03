import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../../ui/web/app.js', import.meta.url), 'utf8');
const handlers = source.slice(source.indexOf('function actionButton('),
  source.indexOf('function renderActions('));

test('available reactions group by type, keep order after submission, and choose exact chi', () => {
  const sent = [], choices = [];
  let closed = false;
  const ctx = vm.createContext({
    busy:false, labels:{CHI:'吃', PONG:'碰', GANG:'槓', HU:'胡', PASS:'過'},
    document:{createElement:() => ({dataset:{}, setAttribute(key, value) { this[key] = value; }})},
    perform:action => sent.push(action), tileName:String, modal() {},
    $:id => id === 'modal' ? {close() { closed = true; }} : {append:button => choices.push(button)},
  });
  vm.runInContext(handlers, ctx);
  const chi = {type:'CHI', use:[0,2]}, otherChi = {type:'CHI', use:[2,3]};
  const actions = [{type:'PASS'}, otherChi, {type:'PONG'}, chi];
  const buttons = [];
  const target = {dataset:{}, append:button => buttons.push(button)};
  ctx.renderReactionActions(target, actions);
  assert.deepEqual(buttons.map(button => button.textContent), ['吃','碰','過']);
  buttons[0].onclick();
  assert.equal(sent.length, 0, 'opening the chooser must not submit');
  choices[1].onclick();
  assert.equal(closed, true);
  assert.deepEqual(sent, [chi]);
  buttons.length = 0;
  ctx.renderReactionActions(target, actions, chi);
  assert.deepEqual(buttons.map(button => button.textContent), ['吃','碰','過']);
  assert.ok(buttons.every(button => button.disabled));
  assert.deepEqual(buttons.map(button => button['aria-pressed']), ['true','false','false']);
  buttons.length = 0;
  ctx.renderReactionActions(target, [{type:'HU'}, {type:'GANG'}, ...actions]);
  assert.deepEqual(buttons.map(button => button.textContent), ['吃','碰','槓','胡','過']);
});
