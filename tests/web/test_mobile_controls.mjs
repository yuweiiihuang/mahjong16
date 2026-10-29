import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source=readFileSync(new URL('../../ui/web/app.js',import.meta.url),'utf8');
const controls=source.slice(source.indexOf('function syncControlsSide('),
  source.indexOf("let playerName ="));

test('mobile controls follow both iPhone rotations, including initial landscape loading', () => {
  const events=new Map(),dataset={};
  const orientation={angle:90,addEventListener:(name,callback)=>events.set(`screen:${name}`,callback)};
  const window={orientation:-90,screen:{orientation},
    addEventListener:(name,callback)=>events.set(name,callback)};
  let projections=0;
  const ctx=vm.createContext({window,document:{documentElement:{dataset}},
    tableView:{resize() {projections++;}}});
  vm.runInContext(controls,ctx);
  assert.equal(dataset.controlsSide,'left',
    'charging port left means the controls stay opposite the right-side island');
  window.orientation=90;
  events.get('orientationchange')();
  assert.equal(dataset.controlsSide,'right');
  window.orientation=-90;
  events.get('resize')();
  assert.equal(dataset.controlsSide,'left');
  delete window.orientation;
  orientation.angle=270;
  events.get('screen:change')();
  assert.equal(dataset.controlsSide,'left');
  orientation.angle=90;
  events.get('screen:change')();
  assert.equal(dataset.controlsSide,'right');
  delete window.screen;
  ctx.syncControlsSide();
  assert.equal(dataset.controlsSide,'right','unsupported devices keep the default right rail');
  assert.equal(projections,4,'rotating refreshes projected overlays even if viewport dimensions stay equal');
});

test('long-press context menus are suppressed on tile surfaces but not text inputs', () => {
  let handler, prevented=0;
  const context=vm.createContext({document:{addEventListener:(name,callback)=>{
    assert.equal(name,'contextmenu'); handler=callback;
  }}});
  const start=source.indexOf("document.addEventListener('contextmenu'");
  vm.runInContext(source.slice(start,source.indexOf('document.body.classList.toggle',start)),context);
  handler({target:{closest:()=>({})},preventDefault:()=>prevented++});
  handler({target:{closest:()=>null},preventDefault:()=>prevented++});
  assert.equal(prevented,1);
});
