import test from 'node:test';
import assert from 'node:assert/strict';
import { MahjongTableView } from '../../ui/web/table3d.js';
import { tileAsset, TILE_FONTS } from '../../ui/web/tile-fonts.mjs';

function view(load) {
  return Object.assign(Object.create(MahjongTableView.prototype), {
    ready:Promise.resolve(), fontRequest:0, fontMaterials:new Map(), faceFont:'mahjong-tw',
    faceMaterials:new Map([[9,'original-circle']]), loadFaceMaterial:load,
  });
}

test('unknown stored font falls back to Taiwan tiles and Japanese style covers all faces', () => {
  assert.deepEqual(TILE_FONTS.map(font => font.id), ['mahjong-tw','mahjong-jp']);
  assert.equal(tileAsset(0,'serif'),'assets/tiles/fonts/mahjong-tw/0.svg');
  assert.equal(tileAsset(0,'cns-kai'),'assets/tiles/fonts/mahjong-tw/0.svg');
  assert.equal(tileAsset(0,'unknown'),'assets/tiles/fonts/mahjong-tw/0.svg');
  assert.equal(tileAsset(9,'mahjong-jp'),'assets/tiles/fonts/mahjong-jp/9.svg?v=imahjong-jp-1');
  assert.equal(tileAsset(41,'unknown'),'assets/tiles/41.svg?v=imahjong-tw-1');
});

test('a slow earlier switch cannot replace the latest chosen font', async () => {
  const pending = [];
  const table = view(url => url.includes('/mahjong-tw/')
    ? new Promise(resolve => pending.push(() => resolve(url))) : Promise.resolve(url));
  const slow = table.setFaceFont('mahjong-tw');
  await Promise.resolve();
  await table.setFaceFont('mahjong-jp');
  pending.forEach(resolve => resolve());
  await slow;
  assert.equal(table.faceFont,'mahjong-jp');
  assert.equal(table.faceMaterials.get(0),'assets/tiles/fonts/mahjong-jp/0.svg');
  assert.equal(table.faceMaterials.get(9),'assets/tiles/fonts/mahjong-jp/9.svg?v=imahjong-jp-1');
});

test('failed font load leaves faces intact and can be retried, then reused', async () => {
  let fail = true, loads = 0;
  const table = view(async url => {
    loads++;
    if (fail) throw new Error('load failed');
    return url;
  });
  await assert.rejects(table.setFaceFont('mahjong-jp'),/load failed/);
  assert.equal(table.faceFont,'mahjong-tw');
  assert.equal(table.faceMaterials.size,1);
  fail = false;
  await table.setFaceFont('mahjong-jp');
  const previousLoads = loads;
  await table.setFaceFont('mahjong-jp');
  assert.equal(loads,previousLoads);
  assert.equal(table.faceMaterials.size,42);
});

test('switching back from Japanese restores every Taiwan face', async () => {
  const table = view(async url => url);
  await table.setFaceFont('mahjong-jp');
  await table.setFaceFont('mahjong-tw');
  for (let id=0;id<42;id++) assert.equal(table.faceMaterials.get(id),tileAsset(id,'mahjong-tw'));
});
