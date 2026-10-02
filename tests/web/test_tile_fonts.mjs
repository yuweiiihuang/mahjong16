import test from 'node:test';
import assert from 'node:assert/strict';
import { MahjongTableView } from '../../ui/web/table3d.js';
import { tileAsset } from '../../ui/web/tile-fonts.mjs';

function view(load) {
  return Object.assign(Object.create(MahjongTableView.prototype), {
    ready:Promise.resolve(), fontRequest:0, fontMaterials:new Map(), faceFont:'serif',
    faceMaterials:new Map([[9,'original-circle']]), loadFaceMaterial:load,
  });
}

test('unknown stored font falls back to A and non-wan faces keep their assets', () => {
  assert.equal(tileAsset(0,'unknown'),'assets/tiles/fonts/serif/0.svg');
  assert.equal(tileAsset(9,'brush'),'assets/tiles/9.svg');
  assert.equal(tileAsset(41,'wenkai'),'assets/tiles/41.svg');
});

test('a slow earlier switch cannot replace the latest chosen font', async () => {
  const pending = [];
  const table = view(url => url.includes('/wenkai/')
    ? new Promise(resolve => pending.push(() => resolve(url))) : Promise.resolve(url));
  const slow = table.setFaceFont('wenkai');
  await Promise.resolve();
  await table.setFaceFont('brush');
  pending.forEach(resolve => resolve());
  await slow;
  assert.equal(table.faceFont,'brush');
  assert.equal(table.faceMaterials.get(0),'assets/tiles/fonts/brush/0.svg');
  assert.equal(table.faceMaterials.get(9),'original-circle');
});

test('failed font load leaves faces intact and can be retried, then reused', async () => {
  let fail = true, loads = 0;
  const table = view(async url => {
    loads++;
    if (fail) throw new Error('load failed');
    return url;
  });
  await assert.rejects(table.setFaceFont('wenkai'),/load failed/);
  assert.equal(table.faceFont,'serif');
  assert.equal(table.faceMaterials.size,1);
  fail = false;
  await table.setFaceFont('wenkai');
  const previousLoads = loads;
  await table.setFaceFont('wenkai');
  assert.equal(loads,previousLoads);
  assert.equal(table.faceMaterials.size,10);
});
