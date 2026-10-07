import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from '../../ui/web/vendor/three.module.js';
import { MahjongTableView } from '../../ui/web/table3d.js';

test('table zoom uniformly enlarges projection and hit targets without accumulating on resize', () => {
  const view = Object.create(MahjongTableView.prototype);
  Object.assign(view, {zoom:1.19, camera:new THREE.PerspectiveCamera(30,1,.1,180),
    container:{clientWidth:1122,clientHeight:560,style:{setProperty(name,value) {this[name]=value;}}},renderer:{setSize() {}},draw() {},
    scene:new THREE.Scene(),handObjects:[]});
  const tile = new THREE.Mesh(new THREE.BoxGeometry(1,1.4,.42));
  tile.position.set(2,.77,10.9);
  view.scene.add(tile); view.handObjects.push(tile);
  for (const [width,height] of [[1384,774],[1024,768],[828,378],[651,363],[1384,774]]) {
    Object.assign(view.container,{clientWidth:width,clientHeight:height});
    view.resize();
    const expectedZoom=width>950&&width/height>1.6?1.30:1.19;
    assert.equal(view.zoom,expectedZoom);
    assert.equal(view.container.style['--table-zoom'],view.zoom,
      'DOM overlays must use the same zoom as the camera after every resize');
    assert.ok(Math.abs(view.project([0,0,0]).x-width/2)<1e-7,
      'the physical table center must stay on the viewport horizontal center');
    const points = [[-9,.77,10.9],[8,.77,10.9],[10.3,1.75,0],[0,1.75,-9.1]];
    const zoomed = points.map(p => view.project(p));
    const hit = view.hitBoxes()[0];
    view.camera.clearViewOffset();
    const original = points.map(p => view.project(p));
    const originalHit = view.hitBoxes()[0];
    for (let i=1;i<points.length;i++) {
      for (const axis of ['x','y']) {
        assert.ok(Math.abs((zoomed[i][axis]-zoomed[0][axis])-
          expectedZoom*(original[i][axis]-original[0][axis]))<1e-7,
        'every seat must share the same enlargement');
      }
    }
    assert.ok(Math.abs(hit.width-originalHit.width*expectedZoom)<1e-7);
    assert.ok(Math.abs(hit.height-originalHit.height*expectedZoom)<1e-7);
    view.resize();
    assert.deepEqual(points.map(p => view.project(p)),zoomed,
      'repeated resizing must not compound zoom or shift hit targets');
    assert.deepEqual(view.hitBoxes()[0],hit);
  }
});

test('ting mode raises every eligible copy and drawn tile above ordinary selection', () => {
  const view = Object.create(MahjongTableView.prototype);
  const group = new THREE.Group();
  view.seatPositions = [0,1,2,3];
  view.seatGroup = () => group;
  view.makeTile = (id, upright, action, selected) => {
    const tile = new THREE.Group();
    tile.position.y = .705 + (selected ? .22 : 0);
    tile.userData = {id, selected};
    return tile;
  };
  const state = {hand:[4,4,9], drawn:4, legal_actions:[],
    players:[{melds:[], flowers:[]}]};
  view.addConcealed(0, state, {tingCandidates:[{tile:4,from:'hand'}, {tile:4,from:'drawn'}]});
  assert.equal(group.children.filter(tile => tile.userData.selected).length, 3);
  for (const tile of group.children) {
    assert.equal(tile.position.y, tile.userData.selected ? .705 + .22 + .55 : .705);
  }
  group.clear();
  view.addConcealed(0, state, {tingCandidates:[{tile:4,from:'drawn'}]});
  assert.equal(group.children.filter(tile => tile.userData.selected).length, 1,
    'a drawn-tile candidate must not raise identical but ineligible hand tiles');
});

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
test('chi restriction shades every forbidden copy and preserves disabled hit targets', () => {
  const view = Object.create(MahjongTableView.prototype);
  const originalFace = new THREE.MeshBasicMaterial({color:0xffffff});
  Object.assign(view, {tiles:new THREE.Group(),handObjects:[],seatPositions:[0,1,2,3],
    bodyGeometry:new THREE.BoxGeometry(1,1.4,.34),backGeometry:new THREE.BoxGeometry(1,1.4,.12),
    faceGeometry:new THREE.PlaneGeometry(.9,1.3),ivory:new THREE.MeshBasicMaterial(),
    jade:new THREE.MeshBasicMaterial(),faceMaterials:new Map([[2,originalFace],[3,originalFace]])});
  view.addConcealed(0,{hand:[2,2,3],drawn:null,blocked_discards:[2],
    legal_actions:[{type:'DISCARD',tile:3,from:'hand'}],players:[{melds:[],flowers:[]}]},null);
  const tiles=view.tiles.children[0].children;
  assert.equal(view.handObjects.length,3,'forbidden copies still have accessible disabled targets');
  assert.deepEqual(tiles.map(t=>Boolean(t.userData.blocked)),[true,true,false]);
  for(let i=0;i<3;i++) {
    const dark=tiles[0].children[i],normal=tiles[2].children[i];
    assert.notEqual(dark.material,normal.material);
    assert.equal(dark.material,tiles[1].children[i].material,'blocked copies share materials');
    assert.equal(dark.geometry,normal.geometry,'dimming must not add a face-only overlay');
    assert.ok(Math.abs(dark.material.color.r-normal.material.color.r*.55)<1e-9);
    assert.ok(Math.abs(dark.material.color.g-normal.material.color.g*.55)<1e-9);
    assert.ok(Math.abs(dark.material.color.b-normal.material.color.b*.55)<1e-9);
  }
  assert.equal(originalFace.color.getHex(),0xffffff,'shared normal faces must remain unchanged');
  assert.ok(tiles.every(tile=>tile.children.length===3),'all tiles retain the same shape');
});

function layout(meldCount, meldSize, flowerSeat, riverCount = 0, drawn = false) {
  const view = Object.create(MahjongTableView.prototype);
  Object.assign(view, {
    tiles: new THREE.Group(), handObjects: [], seatPositions: [0, 1, 2, 3],
    bodyGeometry: new THREE.BoxGeometry(1, 1.4, .34),
    backGeometry: new THREE.BoxGeometry(1, 1.4, .12),
    ivory: new THREE.MeshBasicMaterial(), jade: new THREE.MeshBasicMaterial(),
    faceMaterials: new Map(),
  });
  const state = {
    hand: Array(16 - 3 * meldCount).fill(0), drawn: drawn ? 3 : null, legal_actions: [],
    players: Array.from({length:4}, (_, pid) => ({
      count:16 - 3 * meldCount + Number(drawn), has_drawn:drawn,
      melds:Array.from({length:meldCount}, () => ({tiles:Array(meldSize).fill(0)})),
      flowers:flowerSeat === -1 || pid === flowerSeat ? Array.from({length:8}, (_, i) => i + 34) : [],
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
      river:seat.userData.riverPid !== undefined, upright:tile.rotation.x === 0,
      flower:tile.userData.id >= 34, box:new THREE.Box3().setFromObject(tile)})));
}

test('flowers remain readable, above the table and clear of exposed melds in every seat', () => {
  for (const flowerSeat of [-1,0,1,2,3]) {
    for (let meldCount = 0; meldCount <= 5; meldCount++) {
      for (const meldSize of [3, 4]) {
        const tiles = layout(meldCount, meldSize, flowerSeat);
        for (const flower of tiles.filter(tile => tile.flower)) {
          const size = flower.box.getSize(new THREE.Vector3());
          assert.ok(Math.min(size.x, size.z) >= .75, 'flower faces must stay large enough to read');
          assert.ok(flower.box.min.y >= 0, 'flowers must not sink into the table');
          for (const other of tiles.filter(tile => tile !== flower)) {
            assert.ok(!flower.box.intersectsBox(other.box),
              `flower seat ${flowerSeat} intersects seat ${other.pid}, ${meldCount} melds × ${meldSize}`);
          }
        }
      }
    }
  }
});

test('adjacent seats clear all melds, concealed tiles and drawn slots at table corners', () => {
  for (let meldCount = 0; meldCount <= 5; meldCount++) {
    for (const meldSize of [3, 4]) {
      const tiles = layout(meldCount, meldSize, -1, 24, true);
      for (let i = 0; i < tiles.length; i++) {
        for (const other of tiles.slice(i + 1).filter(tile => tile.pid !== tiles[i].pid)) {
          assert.ok(!tiles[i].box.intersectsBox(other.box),
            `seat ${tiles[i].pid} intersects seat ${other.pid}, ${meldCount} melds × ${meldSize}`);
        }
      }
    }
  }
});

test('chi places the claimed discard between the sorted hand tiles in every seat', () => {
  const view = Object.create(MahjongTableView.prototype);
  view.seatPositions = [0, 1, 2, 3];
  view.makeTile = id => {
    const tile = new THREE.Group();
    tile.userData.id = id;
    return tile;
  };
  for (let pid = 0; pid < 4; pid++) {
    for (const [claimed, hand] of [[0, [2, 1]], [1, [2, 0]], [2, [1, 0]]]) {
      const meld = {type:'CHI', tiles:[...hand, claimed]};
      const original = [...meld.tiles];
      const group = new THREE.Group();
      view.addMeld(pid, meld, group, 0, 0);
      assert.deepEqual(group.children.map(tile => tile.userData.id),
        [Math.min(...hand), claimed, Math.max(...hand)]);
      assert.ok(group.children[0].position.x < group.children[1].position.x);
      assert.ok(group.children[1].position.x < group.children[2].position.x);
      assert.deepEqual(meld.tiles, original, 'display must not reorder engine data');
    }
  }
});

test('opposite exposed tiles face the viewer after seat rotation', () => {
  for (const seats of [[0, 1, 2, 3], [0, 2, 3, 1]]) {
    const view = Object.create(MahjongTableView.prototype);
    Object.assign(view, {
      tiles:new THREE.Group(), handObjects:[], seatPositions:seats,
      bodyGeometry:new THREE.BoxGeometry(1,1.4,.34),
      backGeometry:new THREE.BoxGeometry(1,1.4,.12),
      faceGeometry:new THREE.PlaneGeometry(.9,1.26),
      ivory:new THREE.MeshBasicMaterial(), jade:new THREE.MeshBasicMaterial(),
      faceMaterials:new Map([0, 34].map(id => [id, new THREE.MeshBasicMaterial()])),
    });
    const state = {
      hand:[], drawn:null, legal_actions:[],
      players:Array.from({length:4}, () => ({
        count:0, flowers:[34], melds:[{type:'PONG', tiles:[0,0,0]}],
      })),
    };
    for (let pid = 0; pid < 4; pid++) {
      view.addConcealed(pid, state, null, [0,1,2,3]);
      view.addRiver(pid, [0], null);
    }
    view.tiles.updateMatrixWorld(true);
    for (const group of view.tiles.children) {
      for (const tile of group.children) {
        const up = new THREE.Vector3(0,1,0).transformDirection(tile.matrixWorld);
        if (Math.abs(group.rotation.y - Math.PI) < 1e-6 || group.rotation.y === 0) {
          assert.ok(up.z < -.99, 'own and opposite faces point toward the viewer');
        } else {
          assert.equal(tile.rotation.z, 0, 'side seats retain their orientation');
        }
      }
    }
  }
});

test('melds stay anchored as concealed counts, draws and exposed groups change', () => {
  const view = Object.create(MahjongTableView.prototype);
  view.tiles = new THREE.Group();
  view.seatPositions = [0, 2, 3, 1];
  view.makeTile = (id, upright) => {
    const tile = new THREE.Group();
    tile.userData.id = id;
    tile.rotation.x = upright ? 0 : -Math.PI/2;
    return tile;
  };
  for (let pid = 0; pid < 4; pid++) {
    let previous = [];
    for (let count = 1; count <= 5; count++) {
      for (const drawn of [null, 8]) {
        const melds = Array.from({length:count}, (_, i) => ({
          type:i % 2 ? 'GANG' : 'PONG', tiles:Array(i % 2 ? 4 : 3).fill(i),
        }));
        const state = {
          hand:Array(16-3*count).fill(8), drawn, legal_actions:[],
          players:Array.from({length:4}, () => ({count:16-3*count, flowers:[], melds})),
        };
        view.tiles.clear();
        view.addConcealed(pid, state, null, [0,1,2,3]);
        view.tiles.updateMatrixWorld(true);
        const group = view.tiles.children[0];
        assert.equal(group.position.x, [0,11.2,0,-11.2][view.seatPositions[pid]]);
        const exposed = group.children.filter(tile => tile.rotation.x !== 0);
        const positions = exposed.map(tile => tile.getWorldPosition(new THREE.Vector3()).toArray());
        assert.deepEqual(positions.slice(0, previous.length), previous,
          'existing meld tiles must not move when another meld or drawn tile appears');
        assert.equal(exposed[0].position.x, -9.1);
        assert.ok(Math.abs(exposed[0].position.z - (pid === 0 ? 1.31 : -.49)) < 1e-9);
        previous = positions;
      }
    }
  }
});

test('concealed slots and drawn tile stay fixed for zero through five melds', () => {
  const view = Object.create(MahjongTableView.prototype);
  view.tiles = new THREE.Group();
  view.seatPositions = [0,1,2,3];
  view.makeTile = (id, upright) => {
    const tile = new THREE.Group();
    tile.rotation.x = upright ? 0 : -Math.PI/2;
    return tile;
  };
  for (let count = 0; count <= 5; count++) {
    for (const stage of ['rest', 'draw', 'claim']) {
      if (count === 0 && stage === 'claim') continue;
      const drawn = stage === 'draw' ? 8 : null;
      const size = 16-3*count+Number(stage === 'claim');
      const state = {
        hand:Array(size).fill(8), drawn, legal_actions:[],
        players:Array.from({length:4}, () => ({count:size+Number(drawn!==null),
          has_drawn:drawn!==null, flowers:[],
          melds:Array.from({length:count}, () => ({type:'PONG',tiles:[0,0,0]}))})),
      };
      for (let pid = 0; pid < 4; pid++) {
        view.tiles.clear();
        view.addConcealed(pid, state, null, [0,1,2,3]);
        const hand = view.tiles.children[0].children.filter(tile => tile.rotation.x === 0);
        assert.equal(hand.length, size + Number(drawn !== null));
        assert.ok(hand.every(tile => tile.position.z === (pid === 0 ? 1.8 : 0)),
          'only the local hand and drawn tile move toward the viewer');
        assert.ok(Math.abs(hand[size-1].position.x - 15*1.045/2) < 1e-9);
        if (count === 0) assert.ok(Math.abs(hand[0].position.x + hand[15].position.x) < 1e-9,
          'the full concealed hand is centered');
        if (pid === 0 && count > 0) {
          const melds = view.tiles.children[0].children.filter(tile => tile.rotation.x !== 0);
          assert.ok(Math.max(...melds.map(tile => tile.position.x)) + .5 < hand[0].position.x - .5,
            'local melds leave clearance before the concealed hand');
        }
        if (drawn !== null) assert.equal(hand.at(-1).position.x, 15*1.045/2+1.045+.55);
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


test('full and overflowing rivers clear hands, melds, flowers and rivers in every seat', () => {
  for (const flowerSeat of [-1,0,1,2,3]) {
    for (let meldCount = 0; meldCount <= 5; meldCount++) {
      for (const meldSize of [3, 4]) {
        for (const riverCount of [18,19,24,30,64]) {
          const tiles = layout(meldCount, meldSize, flowerSeat, riverCount, true);
          assert.equal(tiles.filter(tile => tile.river).length, riverCount * 4);
          for (let pid=0;pid<4;pid++) {
            const row=tiles.filter(tile=>tile.pid===pid&&!tile.river&&!tile.flower);
            const hand=row.find(tile=>tile.upright);
            const edge=box=>[box.max.z,box.max.x,box.min.z,box.min.x][pid];
            for (const meld of row.filter(tile=>!tile.upright)) {
              assert.ok(Math.abs(edge(meld.box)-edge(hand.box))<1e-6,
                'meld and hand bodies must align at their seat outer edge');
            }
          }
          // 64 per seat is intentionally beyond a legal round to stress the layout.
          for (const river of tiles.filter(tile => tile.river)) {
            for (const other of tiles.filter(tile => tile !== river)) {
              assert.ok(!river.box.intersectsBox(other.box),
                `${riverCount} discards: river seat ${river.pid} intersects seat ${other.pid}, ${meldCount} melds × ${meldSize}`);
            }
          }
        }
      }
    }
  }
});


test('waiting rooms draw no concealed tiles even with a stale drawn flag', () => {
  const view = Object.create(MahjongTableView.prototype);
  view.seatGroup = () => { throw new Error('waiting rooms must not build tile groups'); };
  const state = {room:{started:false}, drawn:8, hand:[0],
    players:Array.from({length:4}, () => ({count:0, has_drawn:true}))};
  for (let pid=0;pid<4;pid++) view.addConcealed(pid,state,null,[0,1,2,3]);
});
