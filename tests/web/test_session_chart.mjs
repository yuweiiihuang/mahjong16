import test from 'node:test';
import assert from 'node:assert/strict';
import {renderScoreChart} from '../../ui/web/session-chart.mjs';
const node = tag => ({tag,attrs:{},children:[],style:{},dataset:{},animations:[],
  getAnimations(){return this.animations;},
  animate(frames,options){this.animations.push({frames,options,cancel(){this.cancelled=true;}});},
  setAttribute(key,value){this.attrs[key]=value;},append(...children){this.children.push(...children);}});
const doc = {createElement:node,createElementNS:(ns,tag)=>node(tag)};
const all = (node, tag) => node.children.flatMap(child=>
  [...(child.tag === tag ? [child] : []),...all(child,tag)]);

test('score chart keeps every score with bounded flat coordinates and solid wind colors', () => {
  const names = ['A','B','C','D'];
  const chart = renderScoreChart([
    {totals:[1000,1000,1000,1000]}, {round:5,totals:[1100,900,1000,1000]},
  ],names,['W','N','E','S'],()=>{},doc);
  const lines = all(chart,'polyline');
  assert.equal(lines.length,4);
  assert.equal(lines[0].attrs.points,'0,80 525,0');
  assert.equal(lines[1].attrs.points,'0,80 525,160');
  assert.deepEqual(lines.map(line=>line.attrs.stroke),['#76cbd8','#b9a0e6','#efbd62','#ed8690']);
  assert.ok(lines.every(line=>line.attrs['stroke-dasharray'] === undefined));
  assert.deepEqual(lines.map(line=>line.children[0].textContent),names);
  assert.equal(all(chart,'line')[0].attrs.y1,80,'1000-point baseline uses the score scale');
  assert.deepEqual(chart.children.find(el=>el.className==='chart-ticks').children.filter(n=>!n.hidden).map(n=>n.textContent),['0','5']);
  const flat=renderScoreChart([{totals:[1000,1000,1000,1000]}],names,['E','S','W','N'],()=>{},doc);
  assert.ok(all(flat,'polyline').every(line=>line.attrs.points==='0,80'));
});

test('hover shows the selected scores and leaving restores latest with no guide or button', () => {
  const points=[{round:0,totals:[1000,1000,1000,1000]},
    {round:2,totals:[1200,800,1000,1000]}, {round:4,totals:[900,1300,1000,800]}];
  const original=JSON.stringify(points);
  let shown;
  const chart=renderScoreChart(points,['A','B','C','D'],['E','S','W','N'],
    point=>{shown=point.totals;},doc);
  const plot=chart.children.find(el=>el.className==='chart-plot');
  const guide=plot.children.find(el=>el.className==='chart-guide');
  const markers=plot.children.filter(el=>el.className==='chart-point');
  const ticks=chart.children.find(el=>el.className==='chart-ticks');
  const active=ticks.children.find(el=>el.className==='chart-active-tick');
  assert.deepEqual(shown,[900,1300,1000,800]);
  assert.equal(guide.hidden,true);
  assert.ok(markers.every(marker=>marker.hidden));
  assert.equal(plot.onclick,undefined);
  assert.equal(all(chart,'button').length,1,'only the animation replay button is present');
  assert.equal(chart.children.find(el=>el.className==='chart-axis-label').textContent,'局數');
  plot.getBoundingClientRect=()=>({left:20,width:200});
  plot.onpointermove({clientX:120});
  assert.deepEqual(shown,[1200,800,1000,1000]);
  assert.equal(active.textContent,'2');
  assert.equal(guide.style.left,'50%');
  assert.equal(guide.hidden,false);
  assert.ok(markers.every(marker=>marker.style.left==='50%'&&!marker.hidden));
  chart.onpointerleave();
  assert.deepEqual(shown,[900,1300,1000,800]);
  assert.equal(guide.hidden,true);
  assert.equal(active.hidden,true);
  plot.onpointermove({clientX:220});
  assert.equal(guide.hidden,false,'hovering the latest hand still shows its guide');
  assert.equal(guide.style.left,'100%');
  chart.onkeydown({key:'Home',preventDefault(){}});
  assert.equal(active.textContent,'0');
  chart.onblur();
  assert.equal(guide.hidden,true);
  assert.deepEqual(shown,[900,1300,1000,800]);
  assert.equal(JSON.stringify(points),original);
});


test('curves reveal once on creation and replay without changing the displayed scores', () => {
  const points=[{round:0,totals:[1000,1000,1000,1000]},
    {round:1,totals:[1200,800,1000,1000]}];
  let updates=0;
  const chart=renderScoreChart(points,['A','B','C','D'],['E','S','W','N'],()=>updates++,doc);
  const lines=all(chart,'polyline');
  assert.ok(lines.every(line=>line.animations.length===1));
  assert.deepEqual(lines[0].animations[0].frames,[{clipPath:'inset(-4px 100% -4px -4px)'},
    {clipPath:'inset(-4px -4px -4px -4px)'}]);
  assert.equal(lines[0].animations[0].options.duration,900);
  all(chart,'button')[0].onclick();
  assert.ok(lines.every(line=>line.animations.length===2 && line.animations[0].cancelled));
  assert.equal(updates,1,'animation replay must not select historical scores');
  const reduced=renderScoreChart(points,['A','B','C','D'],['E','S','W','N'],()=>{},
    {...doc,defaultView:{matchMedia:()=>({matches:true})}});
  all(reduced,'button')[0].onclick();
  assert.ok(all(reduced,'polyline').every(line=>line.animations.length===0));
});
