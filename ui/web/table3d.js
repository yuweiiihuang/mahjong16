import { DEFAULT_ORDER, sortHand } from './hand-sort.mjs';
import * as THREE from './vendor/three.module.js';
import { RoundedBoxGeometry } from './vendor/RoundedBoxGeometry.js';

// All seats share these physical dimensions, this table, and this camera.
const TILE = { width: 1, height: 1.4, depth: .42, pitch: 1.045 };
const ANGLES = [0, Math.PI / 2, Math.PI, -Math.PI / 2];
const SEATS = [[0, 9.1], [10.3, 0], [0, -9.1], [-10.3, 0]];
const RIVERS = [[0, 3.3], [4.45, 0], [0, -3.3], [-4.45, 0]];

export class MahjongTableView {
  constructor(container, onPick) {
    this.container = container;
    this.onPick = onPick;
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(30, 1, .1, 180);
    this.camera.position.set(0, 24, 42);
    this.camera.lookAt(0, 0, .2);
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.22;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.domElement.className = 'table-canvas';
    this.renderer.domElement.setAttribute('aria-hidden', 'true');
    container.prepend(this.renderer.domElement);
    this.scene.add(new THREE.HemisphereLight(0xf2f8f5, 0x476451, 2.25));
    const key = new THREE.DirectionalLight(0xfff8ee, 3.2);
    key.position.set(-12, 30, 18);
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    key.shadow.camera.left = -24; key.shadow.camera.right = 24;
    key.shadow.camera.top = 24; key.shadow.camera.bottom = -24;
    key.shadow.camera.far = 90;
    key.shadow.normalBias = .03; key.shadow.bias = -.0002;
    key.shadow.radius = 3;
    this.scene.add(key);
    const fill = new THREE.DirectionalLight(0xdbeae5, .6);
    fill.position.set(18, 12, -12); this.scene.add(fill);
    this.ivory = new THREE.MeshPhysicalMaterial({ color: 0xf7f6ef, roughness: .32,
      metalness: 0, clearcoat: .18, clearcoatRoughness: .3 });
    this.jade = new THREE.MeshPhysicalMaterial({ color: 0x196241, roughness: .35,
      metalness: 0, clearcoat: .22, clearcoatRoughness: .3 });
    this.bodyGeometry = new RoundedBoxGeometry(TILE.width, TILE.height, .34, 3, .045);
    this.backGeometry = new RoundedBoxGeometry(TILE.width, TILE.height, .12, 3, .045);
    this.faceGeometry = new THREE.PlaneGeometry(.9,1.26);
    this.faceMaterials = new Map();
    this.tiles = new THREE.Group(); this.scene.add(this.tiles);
    this.handObjects = [];
    this.makeTable();
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(container);
    this.renderer.domElement.addEventListener('webglcontextlost', e => {
      e.preventDefault(); container.classList.add('context-lost');
    });
    this.renderer.domElement.addEventListener('webglcontextrestored', () => {
      container.classList.remove('context-lost'); this.draw();
    });
    this.ready = this.loadFaces();
    this.resize();
  }

  makeTable() {
    const canvas = document.createElement('canvas'); canvas.width = canvas.height = 256;
    const ctx = canvas.getContext('2d'); ctx.fillStyle = '#285747'; ctx.fillRect(0,0,256,256);
    const felt = new THREE.CanvasTexture(canvas); felt.colorSpace = THREE.SRGBColorSpace;
    felt.wrapS = felt.wrapT = THREE.RepeatWrapping; felt.repeat.set(8,8);
    const board = new THREE.Mesh(new RoundedBoxGeometry(29.5,.45,24,3,.18),
      new THREE.MeshStandardMaterial({color:0xffffff,map:felt,roughness:1}));
    board.position.y=-.25; board.receiveShadow=true; this.scene.add(board);
    const border = new THREE.Mesh(new RoundedBoxGeometry(30.1,.38,24.6,3,.2),
      new THREE.MeshStandardMaterial({color:0x133e31,roughness:.7}));
    border.position.y=-.53; this.scene.add(border);
    const rim = new THREE.Mesh(new THREE.CylinderGeometry(2.08,2.08,.08,96),
      new THREE.MeshStandardMaterial({color:0xd3cbb5,roughness:.5}));
    rim.position.y=.04; rim.castShadow=true; rim.receiveShadow=true; this.scene.add(rim);
    const center = new THREE.Mesh(new THREE.CylinderGeometry(2.04,2.08,.25,96),
      this.ivory);
    center.position.y=.175; center.castShadow=true; center.receiveShadow=true; this.scene.add(center);
    this.indicatorCanvas = document.createElement('canvas');
    this.indicatorCanvas.width = this.indicatorCanvas.height = 1024;
    this.indicatorContext = this.indicatorCanvas.getContext('2d');
    this.indicatorContext.scale(2,2);
    this.indicatorTexture = new THREE.CanvasTexture(this.indicatorCanvas);
    this.indicatorTexture.colorSpace = THREE.SRGBColorSpace;
    this.indicatorTexture.anisotropy = Math.min(16,this.renderer.capabilities.getMaxAnisotropy());
    const display = new THREE.Mesh(new THREE.PlaneGeometry(4.08,4.08),
      new THREE.MeshBasicMaterial({map:this.indicatorTexture,toneMapped:false,transparent:true}));
    display.rotation.x=-Math.PI/2; display.position.y=.302; this.scene.add(display);
    this.updateIndicator(null);
  }

  updateIndicator(state) {
    const ctx = this.indicatorContext;
    const colors = {E:'#efbd62', S:'#ed8690', W:'#76cbd8', N:'#b9a0e6'};
    const labels = {E:'東', S:'南', W:'西', N:'北'};
    ctx.clearRect(0,0,512,512);
    ctx.textAlign='center'; ctx.textBaseline='middle';
    ctx.fillStyle='#f3efdf';
    ctx.beginPath(); ctx.arc(256,256,256,0,Math.PI*2); ctx.fill();
    const order = state?.seating_order || [0,1,2,3];
    const ownSeat = order.indexOf(0);
    const angles = [Math.PI/2,0,-Math.PI/2,Math.PI];
    angles.forEach((angle, seat) => {
      const pid = order[(ownSeat+seat)%4];
      const wind = state?.seat_winds[pid] || ['E','S','W','N'][pid];
      const color = colors[wind];
      const active = state && !state.done && state.actor === pid;
      const start = angle-Math.PI/4+.045, end = angle+Math.PI/4-.045;
      ctx.shadowColor=color; ctx.shadowBlur=active?18:0;
      ctx.fillStyle=active?color:`${color}88`;
      ctx.beginPath();
      ctx.arc(256,256,238,start,end);
      ctx.arc(256,256,132,end,start,true);
      ctx.closePath(); ctx.fill();
      ctx.shadowBlur=0; ctx.strokeStyle='#d1c8b5'; ctx.lineWidth=2; ctx.stroke();
      ctx.font=`${active?'700':'500'} 64px "PingFang TC",sans-serif`;
      ctx.fillStyle=active?'#102d29':'#536960';
      ctx.fillText(labels[wind],256+Math.cos(angle)*184,256+Math.sin(angle)*184);
    });
    ctx.fillStyle='#faf6e8';
    ctx.beginPath(); ctx.arc(256,256,120,0,Math.PI*2); ctx.fill();
    ctx.strokeStyle='#d1c8b5'; ctx.lineWidth=2; ctx.stroke();
    ctx.fillStyle='#153e32'; ctx.font='600 136px ui-monospace,"SFMono-Regular",monospace';
    ctx.fillText(state ? String(state.remaining) : '—',256,256);
    this.indicatorTexture.needsUpdate=true;
  }

  async loadFaces() {
    const loader = new THREE.ImageLoader();
    await Promise.all(Array.from({length:42},async(_,id)=>{
      const image = await loader.loadAsync(`assets/tiles/${id}.svg`);
      const canvas=document.createElement('canvas');canvas.width=384;canvas.height=538;
      const ctx=canvas.getContext('2d');ctx.fillStyle='#f7f6ef';ctx.fillRect(0,0,384,538);
      ctx.drawImage(image,40,52,304,434);
      const texture=new THREE.CanvasTexture(canvas);
      texture.colorSpace=THREE.SRGBColorSpace;
      texture.anisotropy=Math.min(4,this.renderer.capabilities.getMaxAnisotropy());
      const material=new THREE.MeshBasicMaterial({map:texture,toneMapped:false});
      material.polygonOffset=true;material.polygonOffsetFactor=-1;material.polygonOffsetUnits=-1;
      this.faceMaterials.set(id,material);
    }));
    if(this.snapshot)this.update(this.snapshot,this.selection,this.sortOrder);
  }

  makeTile(id, upright=true, action=null, selected=false) {
    const group=new THREE.Group();
    const body=new THREE.Mesh(this.bodyGeometry,this.ivory);body.position.z=.04;
    body.castShadow=true;body.receiveShadow=true;group.add(body);
    if(id!==null && this.faceMaterials.has(id)) {
      const face=new THREE.Mesh(this.faceGeometry,this.faceMaterials.get(id));
      face.position.z=.216;group.add(face);
    }
    const back=new THREE.Mesh(this.backGeometry,this.jade);back.position.z=-.17;
    back.castShadow=true;back.receiveShadow=true;group.add(back);
    if(upright){group.rotation.x=0;group.position.y=.705+(selected?.22:0);}
    else{group.rotation.x=-Math.PI/2;group.position.y=.235;}
    group.userData={id,action,selected};
    if(action)this.handObjects.push(group);
    return group;
  }

  seatGroup(pid) {
    const seat = this.seatPositions[pid];
    const group=new THREE.Group();group.position.set(SEATS[seat][0],0,SEATS[seat][1]);
    group.rotation.y=ANGLES[seat];this.tiles.add(group);return group;
  }

  addMeld(pid, meld, group, x, z) {
    meld.tiles.forEach((id, i) => {
      const top = meld.tiles.length === 4 && i === 3;
      const faceDown = meld.type === 'ANGANG' && (pid !== 0 || !top);
      const tile = this.makeTile(faceDown ? null : id, false);
      if (faceDown) tile.rotation.x = Math.PI / 2;
      tile.position.x = x + (top ? 1 : i) * TILE.pitch;
      tile.position.z = z;
      // The full ivory body and green back span .44; .46 clears either orientation.
      if (top) tile.position.y += .46;
      group.add(tile);
    });
    return x + Math.min(3, meld.tiles.length) * TILE.pitch + .18;
  }

  addConcealed(pid,state,selected,sortOrder) {
    const group=this.seatGroup(pid);
    const hand=pid===0?sortHand(state.hand,sortOrder):
      Array.from({length:state.players[pid].count},()=>null);
    // Own melds occupy space beside the hand, using the same physical scale.
    const ownMeldSlots=pid===0?state.players[0].melds.reduce((n,m)=>n+Math.min(3,m.tiles.length)+.18/TILE.pitch,0):0;
    const drawn=pid===0&&state.drawn!==null&&state.drawn!==undefined;
    const total=hand.length+ownMeldSlots+(drawn?1.7:0);
    let x=-(total-1)*TILE.pitch/2;
    if(pid===0)for(const meld of state.players[0].melds){
      x=this.addMeld(pid,meld,group,x,.1);
    }
    hand.forEach((id,index)=>{
      const action=pid===0?state.legal_actions.find(a=>a.type==='DISCARD'&&a.tile===id&&a.from==='hand'):null;
      const chosen=pid===0&&selected?.tile===id&&selected?.from==='hand'&&(selected.index===undefined||selected.index===index);
      const tile=this.makeTile(id,true,action,chosen);tile.position.x=x;group.add(tile);x+=TILE.pitch;
      tile.userData.index=index;
    });
    if(drawn){x+=.55;const action=state.legal_actions.find(a=>a.type==='DISCARD'&&a.from==='drawn');
      const t=this.makeTile(state.drawn,true,action,selected?.from==='drawn');t.position.x=x;group.add(t);}
    if(pid!==0){
      const melds=state.players[pid].melds;
      const span=melds.reduce((n,m)=>n+Math.min(3,m.tiles.length)*TILE.pitch,0)+Math.max(0,melds.length-1)*.18;
      let offset=-(span-TILE.pitch)/2;
      for(const meld of melds)offset=this.addMeld(pid,meld,group,offset,-1.0);
    }
    // Small flowers stay beside their owner's hand, outside the three-row river area.
    state.players[pid].flowers.forEach((id,i)=>{
      const tile=this.makeTile(id,false);
      tile.scale.setScalar(.55);
      tile.position.y=.13;
      tile.position.x=-4-(i%4)*.62;
      tile.position.z=-2.25-Math.floor(i/4)*.85;
      group.add(tile);
    });
  }

  addRiver(pid,river,last) {
    const seat = this.seatPositions[pid];
    const group=new THREE.Group();group.position.set(RIVERS[seat][0],0,RIVERS[seat][1]);
    group.rotation.y=ANGLES[seat];group.userData.riverPid=pid;this.tiles.add(group);
    river.forEach((id,i)=>{
      const tile=this.makeTile(id,false);tile.position.x=(i%6-2.5)*1.12;
      tile.position.z=Math.floor(i/6)*1.58;
      if(last?.pid===pid&&i===river.length-1){
        this.markLatest(tile);
      }
      tile.userData.riverIndex=i;group.add(tile);
    });
  }

  markLatest(tile) {
    if (!this.latestOutlineGeometry) {
      const shape = new THREE.Shape();
      shape.moveTo(-.555,-.755); shape.lineTo(.555,-.755);
      shape.lineTo(.555,.755); shape.lineTo(-.555,.755); shape.closePath();
      const hole = new THREE.Path();
      hole.moveTo(-.495,-.695); hole.lineTo(-.495,.695);
      hole.lineTo(.495,.695); hole.lineTo(.495,-.695); hole.closePath();
      shape.holes.push(hole);
      this.latestOutlineGeometry = new THREE.ShapeGeometry(shape);
    }
    const outline = new THREE.Mesh(this.latestOutlineGeometry,
      this.latestOutlineMaterial ||= new THREE.MeshBasicMaterial({color:0xb94037,
        side:THREE.DoubleSide, toneMapped:false, depthWrite:false}));
    outline.position.z = -.2;
    tile.add(outline);
    const pointer = new THREE.Group();
    const geometry = this.latestPointerGeometry ||= new THREE.ConeGeometry(.325,.468,3,1,true);
    const material = this.latestPointerMaterial ||= new THREE.MeshStandardMaterial({
      color:0xb94037, roughness:.65, metalness:.08, flatShading:true});
    const upper = new THREE.Mesh(geometry,material);
    upper.position.y = .234;
    upper.castShadow = true;
    const lower = new THREE.Mesh(geometry,material);
    lower.rotation.z = Math.PI;
    lower.position.y = -.234;
    lower.castShadow = true;
    pointer.add(upper,lower);
    pointer.rotation.x = Math.PI / 2;
    pointer.rotation.y = .35;
    pointer.position.z = 1.05;
    tile.add(pointer);
    tile.userData.latestMarkers = [outline,pointer];
    this.latestPointer = pointer;
    this.rotateLatest();
  }

  rotateLatest() {
    if (this.latestAnimation || typeof requestAnimationFrame !== 'function' ||
        (typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches)) return;
    const tick = now => {
      this.latestAnimation = null;
      if (!this.latestPointer) return;
      this.latestPointer.rotation.y = .35 + now * Math.PI / 5000;
      // Only the pointer moves: do not rebuild hand hit targets each animation frame.
      if (this.width && this.height) this.renderer.render(this.scene,this.camera);
      this.latestAnimation = requestAnimationFrame(tick);
    };
    this.latestAnimation = requestAnimationFrame(tick);
  }

  update(state,selection,sortOrder=DEFAULT_ORDER) {
    if (this.discardAnimating) {
      this.pendingUpdate = [state,selection,sortOrder];
      return;
    }
    this.snapshot=state;this.selection=selection;this.sortOrder=sortOrder;
    this.seatPositions = state.players.map((_, pid) =>
      (state.seating_order.indexOf(pid) - state.seating_order.indexOf(0) + 4) % 4);
    this.updateIndicator(state);
    this.latestPointer = null;
    this.tiles.clear();this.handObjects=[];
    const event = state.events?.at(-1);
    const latest = state.last_discard ||
      (event && ['DISCARD','TING'].includes(event.type) ? event : null);
    for(let pid=0;pid<4;pid++){
      this.addConcealed(pid,state,selection,sortOrder);
      this.addRiver(pid,state.rivers[pid],latest);
    }
    this.draw();
  }

  animateDiscard(pid) {
    const river = this.tiles.children.find(group => group.userData.riverPid === pid);
    const tile = river?.children.find(child =>
      child.userData.riverIndex === this.snapshot.rivers[pid].length-1);
    if (!tile) return Promise.resolve();
    const end = tile.position.clone(), seat = this.seatPositions[pid];
    this.scene.updateMatrixWorld(true);
    const start = river.worldToLocal(new THREE.Vector3(SEATS[seat][0],.8,SEATS[seat][1]));
    const markers = tile.userData.latestMarkers || [];
    this.discardAnimating = true;
    for (const marker of markers) marker.visible = false;
    tile.position.copy(start);
    this.draw();
    const began = performance.now();
    return new Promise(resolve => {
      const tick = now => {
        const progress = Math.min(1,(now-began)/250);
        tile.position.lerpVectors(start,end,1-(1-progress)**3);
        if (progress < 1) {
          this.draw();
          requestAnimationFrame(tick);
        } else {
          for (const marker of markers) marker.visible = true;
          this.discardAnimating = false;
          const pending = this.pendingUpdate;
          this.pendingUpdate = null;
          if (pending) this.update(...pending); else this.draw();
          resolve();
        }
      };
      requestAnimationFrame(tick);
    });
  }

  project(point) {
    const v=new THREE.Vector3(...point).project(this.camera);
    return {x:(v.x+1)*this.width/2,y:(1-v.y)*this.height/2};
  }

  hitBoxes() {
    this.scene.updateMatrixWorld(true);
    return this.handObjects.map(group=>{
      const box=new THREE.Box3().setFromObject(group);const points=[];
      for(const x of [box.min.x,box.max.x])for(const y of [box.min.y,box.max.y])
        for(const z of [box.min.z,box.max.z])points.push(this.project([x,y,z]));
      const left=Math.min(...points.map(p=>p.x)),top=Math.min(...points.map(p=>p.y));
      return {...group.userData,left,top,width:Math.max(...points.map(p=>p.x))-left,
        height:Math.max(...points.map(p=>p.y))-top};
    });
  }

  resize() {
    this.width=this.container.clientWidth;this.height=this.container.clientHeight;
    if(!this.width||!this.height)return;
    this.renderer.setSize(this.width,this.height);
    this.camera.aspect=this.width/this.height;
    // Frame a fixed, full 17-tile hand. Every object still uses this one camera.
    // The fit changes on viewport resize, never independently per seat or tile.
    let near=.32,far=1.4;
    for(let i=0;i<18;i++){
      const scale=(near+far)/2;
      this.camera.position.set(0,24*scale,42*scale);
      let low=-6,high=12;
      for(let j=0;j<18;j++){
        const focus=(low+high)/2;this.camera.lookAt(0,0,focus);
        this.camera.updateProjectionMatrix();this.camera.updateMatrixWorld();
        const y=this.project([0,.77,9.1]).y/this.height;
        if(y>.79)low=focus;else high=focus;
      }
      const span=(this.project([9.3,.77,9.1]).x-this.project([-9.3,.77,9.1]).x)/this.width;
      const farY=this.project([0,1.75,-9.1]).y/this.height;
      if(span>.8 || farY<.14)near=scale;else far=scale;
    }
    this.draw();
  }

  draw() {
    if(!this.width||!this.height)return;
    this.renderer.render(this.scene,this.camera);
    this.onProject?.(this);
  }
}
