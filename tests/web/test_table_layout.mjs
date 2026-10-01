import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from '../../ui/web/vendor/three.module.js';
import { MahjongTableView } from '../../ui/web/table3d.js';

// Exercise the real tile builder and seat transforms without creating a WebGL renderer.
function layout(meldCount, meldSize, flowerSeat) {
  const view = Object.create(MahjongTableView.prototype);
  Object.assign(view, {
    tiles: new THREE.Group(), handObjects: [], seatPositions: [0, 1, 2, 3],
    bodyGeometry: new THREE.BoxGeometry(1, 1.4, .34),
    backGeometry: new THREE.BoxGeometry(1, 1.4, .12),
    ivory: new THREE.MeshBasicMaterial(), jade: new THREE.MeshBasicMaterial(),
    faceMaterials: new Map(),
  });
  const state = {
    hand: Array(16 - 3 * meldCount).fill(0), drawn: null, legal_actions: [],
    players: Array.from({length:4}, (_, pid) => ({
      count:16 - 3 * meldCount,
      melds:Array.from({length:meldCount}, () => ({tiles:Array(meldSize).fill(0)})),
      flowers:pid === flowerSeat ? Array.from({length:8}, (_, i) => i + 34) : [],
    })),
  };
  for (let pid = 0; pid < 4; pid++) view.addConcealed(pid, state, null, [0,1,2,3]);
  view.tiles.updateMatrixWorld(true);
  return view.tiles.children.flatMap((seat, pid) => seat.children
    .filter(tile => tile.rotation.x !== 0)
    .map(tile => ({pid, flower:tile.userData.id >= 34, box:new THREE.Box3().setFromObject(tile)})));
}

test('flowers never intersect their own or adjacent exposed melds in any seat', () => {
  for (let flowerSeat = 0; flowerSeat < 4; flowerSeat++) {
    for (let meldCount = 0; meldCount <= 5; meldCount++) {
      for (const meldSize of [3, 4]) {
        const tiles = layout(meldCount, meldSize, flowerSeat);
        for (const flower of tiles.filter(tile => tile.flower)) {
          for (const other of tiles.filter(tile => tile !== flower)) {
            assert.ok(!flower.box.intersectsBox(other.box),
              `flower seat ${flowerSeat} intersects seat ${other.pid}, ${meldCount} melds × ${meldSize}`);
          }
        }
      }
    }
  }
});

test('kongs use three base tiles and one centered top tile with correct visibility', () => {
  for (const type of ['GANG', 'KAKAN', 'ANGANG']) {
    for (let pid = 0; pid < 4; pid++) {
      const view = Object.create(MahjongTableView.prototype);
      Object.assign(view, {
        tiles:new THREE.Group(), handObjects:[], seatPositions:[0,1,2,3],
        bodyGeometry:new THREE.BoxGeometry(1,1.4,.34),
        backGeometry:new THREE.BoxGeometry(1,1.4,.12),
        ivory:new THREE.MeshBasicMaterial(), jade:new THREE.MeshBasicMaterial(),
        faceMaterials:new Map(),
      });
      const state = {
        hand:Array(13).fill(1), drawn:null, legal_actions:[],
        players:Array.from({length:4}, () => ({count:13, flowers:[], melds:[]})),
      };
      state.players[pid].melds = [{type, tiles:[27,27,27,27]}];
      view.addConcealed(pid, state, null, [0,1,2,3]);
      const kong = view.tiles.children[0].children.filter(tile => tile.rotation.x !== 0);
      assert.equal(kong.length, 4);
      const [left, middle, right, top] = kong;
      assert.ok(left.position.x < middle.position.x && middle.position.x < right.position.x);
      assert.equal(top.position.x, middle.position.x);
      assert.equal(top.position.z, middle.position.z);
      view.tiles.updateMatrixWorld(true);
      const baseBox = new THREE.Box3().setFromObject(middle);
      const topBox = new THREE.Box3().setFromObject(top);
      assert.ok(topBox.min.y >= baseBox.max.y - 1e-6, 'top tile must rest above the base');
      kong.forEach((tile, i) => {
        const faceDown = type === 'ANGANG' && (pid !== 0 || i < 3);
        assert.equal(tile.rotation.x, faceDown ? Math.PI/2 : -Math.PI/2);
        assert.equal(tile.userData.id, faceDown ? null : 27);
      });
    }
  }
});

test('table indicator has five panels and highlights the actor after seat changes', () => {
  const text = [], arcs = [];
  const ctx = {
    clearRect() { text.length = 0; arcs.length = 0; },
    fillRect() {}, beginPath() {}, fill() {}, stroke() {},
    arc(...args) { arcs.push(args); }, closePath() {},
    fillText(value, x, y) { text.push({value,x,y,color:this.fillStyle}); },
  };
  const view = Object.create(MahjongTableView.prototype);
  Object.assign(view, {indicatorContext:ctx, indicatorTexture:{}});
  const state = {
    seating_order:[2,3,0,1], seat_winds:['W','N','E','S'],
    remaining:28, actor:0, done:false,
  };
  for (let actor = 0; actor < 4; actor++) {
    state.actor = actor;
    view.updateIndicator(state);
    assert.equal(arcs.length, 10, 'four ring segments plus outer and center circles');
    assert.deepEqual(arcs.slice(1,9).map(a => a[2]), [238,132,238,132,238,132,238,132]);
    assert.ok(text.some(t => t.value === '28'));
    const lamps = text.filter(t => ['東','南','西','北'].includes(t.value));
    const lit = lamps.filter(t => t.color === '#102d29');
    assert.equal(lit.length, 1);
    assert.equal(lit[0].value, ['西','北','東','南'][actor]);
    assert.deepEqual(lamps.map(t => t.value), ['西','北','東','南']);
  }
  state.done = true;
  view.updateIndicator(state);
  assert.ok(!text.some(t => t.color === '#102d29'));
  view.updateIndicator(null);
  assert.ok(text.some(t => t.value === '—'));
});
