import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source = readFileSync(new URL('../../ui/web/app.js', import.meta.url), 'utf8');

test('toast follows a right toolbar and stays onscreen with left phone controls', () => {
  for (const [toolbarRight,width,expectedRight] of [[653,95,14],[44,95,560],[44,360,295]]) {
    const nodes = {modal:{open:false},settings:{closest:()=>({getBoundingClientRect:()=>
      ({right:toolbarRight,bottom:160})})},toast:{style:{},offsetWidth:width,
      classList:{add(){}}}};
    const context = vm.createContext({$:id=>nodes[id],window:{innerWidth:667},
      toastTimer:null,clearTimeout(){},setTimeout(){}});
    vm.runInContext(source.slice(source.indexOf('function toast('),
      source.indexOf('function setTableStatus(')),context);
    context.toast('測試提示');
    assert.equal(nodes.toast.style.right,`${expectedRight}px`);
    assert.equal(nodes.toast.style.top,'172px');
    assert.equal(nodes.toast.textContent,'測試提示');
  }
});
