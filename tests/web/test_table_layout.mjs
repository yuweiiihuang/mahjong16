import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from '../../ui/web/vendor/three.module.js';
import { MahjongTableView } from '../../ui/web/table3d.js';

test('thin discard frame and triangular bipyramid follow the tile without lifting it', () => {
  const view = Object.create(MahjongTableView.prototype);
  const tile = new THREE.Group();
  tile.rotation.x = -Math.PI / 2;
  tile.position.y = .235;
  view.markLatest(tile);
  assert.equal(tile.position.y, .235);
  const [outline,pointer] = tile.children;
  outline.geometry.computeBoundingBox();
  assert.ok(outline.geometry.boundingBox.max.x < .56, 'frame stays close to tile edges');
  assert.equal(pointer.children.length, 2);
  assert.equal(pointer.children[0].geometry.parameters.radialSegments, 3);
  assert.equal(pointer.children[0].geometry.parameters.openEnded, true);
  assert.equal(pointer.children[1].rotation.z, Math.PI);
  tile.updateMatrixWorld(true);
  assert.ok(new THREE.Box3().setFromObject(pointer).min.y > .6,
    'pointer is suspended above the face');
  const next = new THREE.Group();
  view.markLatest(next);
  assert.equal(next.children[0].geometry, outline.geometry);
  assert.equal(next.children[1].children[0].material, pointer.children[0].material);
});

test('pointer rotates slowly with one animation loop and stops when no discard remains', () => {
  const original = globalThis.requestAnimationFrame;
  const callbacks = [];
  globalThis.requestAnimationFrame = callback => { callbacks.push(callback); return callbacks.length; };
  try {
    const view = Object.create(MahjongTableView.prototype);
    let renders = 0;
    Object.assign(view,{latestPointer:new THREE.Group(),width:800,height:500,
      renderer:{render() { renders++; }},scene:{},camera:{}});
    view.rotateLatest(); view.rotateLatest();
    assert.equal(callbacks.length,1, 'redraws must not start duplicate animation loops');
    callbacks[0](2500);
    assert.ok(Math.abs(view.latestPointer.rotation.y - (.35 + Math.PI / 2)) < 1e-9);
    assert.equal(renders,1);
    const replacement = new THREE.Group();
    view.latestPointer = replacement;
    callbacks[1](5000);
    assert.ok(Math.abs(replacement.rotation.y - (.35 + Math.PI)) < 1e-9);
    view.latestPointer = null;
    callbacks[2](6000);
    assert.equal(callbacks.length,3, 'no pointer means no further frames');
    assert.equal(view.latestAnimation,null);
  } finally { globalThis.requestAnimationFrame = original; }
});

test('latest marker survives the next draw and disappears after a resolved claim', () => {
  const view = Object.create(MahjongTableView.prototype);
  let latest;
  Object.assign(view,{tiles:new THREE.Group(),updateIndicator() {},addConcealed() {},
    addRiver(pid,river,last) { latest = last; },draw() {}});
  const discard = {pid:3,type:'DISCARD',tile:12};
  const state = {players:[{},{},{},{}],seating_order:[0,1,2,3],
    rivers:[[],[],[],[12]],last_discard:null,events:[discard]};
  view.update(state,null);
  assert.equal(latest,discard);
  state.events.push({pid:0,type:'PONG',tile:12,from_pid:3});
  view.update(state,null);
  assert.equal(latest,null);
});

test('discard frame and pointer appear only after the flying tile lands', async () => {
  const original = globalThis.requestAnimationFrame;
  const callbacks = [];
  globalThis.requestAnimationFrame = callback => { callbacks.push(callback); return callbacks.length; };
  try {
    const view = Object.create(MahjongTableView.prototype);
    const scene = new THREE.Scene(), tiles = new THREE.Group();
    scene.add(tiles);
    const river = new THREE.Group(), tile = new THREE.Group();
    river.userData.riverPid = 0;
    tile.userData.riverIndex = 0;
    tile.position.set(2,.235,1.58);
    const markers = [new THREE.Group(),new THREE.Group()];
    tile.add(...markers); tile.userData.latestMarkers = markers;
    river.add(tile); tiles.add(river);
    Object.assign(view,{scene,tiles,seatPositions:[0,1,2,3],snapshot:{rivers:[[0]]},
      draw() {}});
    const destination = tile.position.clone();
    const motion = view.animateDiscard(0);
    assert.ok(markers.every(marker => !marker.visible));
    let rebuilt = false;
    view.updateIndicator = () => { rebuilt = true; };
    view.addConcealed = () => {};
    view.addRiver = () => {};
    const nextState = {players:[{},{},{},{}],seating_order:[0,1,2,3],rivers:[[0],[],[],[]],
      last_discard:{pid:0,tile:0},events:[]};
    view.update(nextState,{tile:5,from:'hand',index:0});
    assert.equal(rebuilt,false, 'selection redraw waits while the tile is in flight');
    assert.equal(river.children[0],tile, 'keep the animated tile instead of rebuilding it');
    assert.ok(markers.every(marker => !marker.visible));
    callbacks.shift()(performance.now());
    assert.ok(markers.every(marker => !marker.visible), 'in-flight frame stays unmarked');
    callbacks.shift()(performance.now() + 251);
    await motion;
    assert.ok(markers.every(marker => marker.visible));
    assert.ok(tile.position.distanceTo(destination) < 1e-9);
    assert.equal(rebuilt,true);
    assert.equal(view.selection.tile,5, 'latest selection is applied after landing');
    assert.equal(view.pendingUpdate,null);
  } finally { globalThis.requestAnimationFrame = original; }
});

// Exercise the real tile builder and seat transforms without creating a WebGL renderer.
function layout(meldCount, meldSize, flowerSeat, riverCount = 0) {
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
  if (riverCount) for (let pid = 0; pid < 4; pid++) {
    view.addRiver(pid, Array(riverCount).fill(0), null);
  }
  view.tiles.updateMatrixWorld(true);
  return view.tiles.children.flatMap((seat, pid) => seat.children
    .filter(tile => riverCount || tile.rotation.x !== 0)
    .map(tile => ({pid:seat.userData.riverPid ?? pid,
      river:seat.userData.riverPid !== undefined,
      flower:tile.userData.id >= 34, box:new THREE.Box3().setFromObject(tile)})));
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
  state.done = false;
  state.phase = 'REACTION';
  view.updateIndicator(state);
  assert.ok(!text.some(t => t.color === '#102d29'), 'reaction actor never lights a wind');
  view.updateIndicator(null);
  assert.ok(text.some(t => t.value === '—'));
});


test('three-row rivers clear hands, melds, flowers and other rivers in every seat', () => {
  for (let flowerSeat = 0; flowerSeat < 4; flowerSeat++) {
    for (let meldCount = 0; meldCount <= 5; meldCount++) {
      for (const meldSize of [3, 4]) {
        const tiles = layout(meldCount, meldSize, flowerSeat, 18);
        for (const river of tiles.filter(tile => tile.river)) {
          for (const other of tiles.filter(tile => tile !== river)) {
            assert.ok(!river.box.intersectsBox(other.box),
              `river seat ${river.pid} intersects seat ${other.pid}, ${meldCount} melds × ${meldSize}`);
          }
        }
      }
    }
  }
});
