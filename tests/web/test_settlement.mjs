import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import {sortHand} from '../../ui/web/hand-sort.mjs';
const source = readFileSync(new URL('../../ui/web/app.js', import.meta.url), 'utf8');

function settlementView(winSource = 'TSUMO', flowerWin = null) {
  const node = tag => {
    const element = {tag, children:[], attrs:{}, className:'', append(...children) {
      this.children.push(...children);
    }, setAttribute(key,value) { this.attrs[key] = value; }};
    element.classList = {add: name => { element.className += ` ${name}`; }};
    return element;
  };
  const elements = Object.fromEntries(['result-players','score-breakdown','result-new']
    .map(id => [id,node('div')]));
  const hands = Array.from({length:4}, () => ({hand:[0,9,18,27],drawn:null,
    melds:[],flowers:[],sort_order:[0,1,2,3]}));
  Object.assign(hands[2], {hand:[2,9,1,18,27], drawn:winSource === 'TSUMO' ? 9 : null,
    flowers:[35,34],sort_order:[1,0,2,3],
    melds:[{type:'ANGANG',tiles:[6,6,6,6]}, {type:'CHI',tiles:[3,4,5]},
      {type:'PON',tiles:[14,14,14]}]});
  hands[0].sort_order = [2,1,0,3];
  hands[1].drawn = 32;
  const state = {winner:2,round:3,win_source:winSource,win_tile:9,dealer:1,
    seating_order:[0,2,1,3],seat_winds:['N','E','S','W'],totals:[1000,900,1100,1000],final_hands:hands,
    settlement:{flower_win_type:flowerWin,payer:winSource === 'RON' ? 1 : null,
      tai:2,base_points:100,tai_points:20,payments:[-40,-60,140,-40],breakdown:[]}};
  let content;
  const ctx = vm.createContext({state,names:['本人','放槍<玩家>','贏家','第四家'],sortOrder:[0,1,2,3],
    $:id=>elements[id],document:{createElement:node},sortHand,winds:['東','南','西','北'],
    escapeHtml:value=>String(value).replaceAll('<','&lt;').replaceAll('>','&gt;'),
    labels:{CHI:'吃',ANGANG:'暗槓'},tile:id=>Object.assign(node('tile'),{id}),
    modal:(title,html)=>{content = html;}, newGame() {}});
  vm.runInContext(source.slice(source.indexOf('function showResult(){'),source.indexOf("$('close-modal').onclick")),ctx);
  ctx.showResult();
  return {elements,state,ctx,content};
}

test('settlement shows winner first and keeps melds, flowers, sorted hands and last tiles distinct', () => {
  const {elements,content,state} = settlementView();
  const cards = elements['result-players'].children;
  assert.deepEqual(cards.map(c=>c.children[0].innerHTML.match(/<strong[^>]*>(.*?)<\/strong>/)[1]),
    ['贏家','放槍&lt;玩家&gt;','第四家','本人']);
  const groups = cards[0].children[1].children;
  assert.deepEqual(groups.map(g=>g.children.map(t=>t.id)),
    [[34,35],[3,4,5],[6,6,6,6],[14,14,14],[1,2,9,18,27],[9]]);
  assert.deepEqual(state.final_hands[2].melds.map(m=>m.tiles),
    [[6,6,6,6],[3,4,5],[14,14,14]]);
  assert.deepEqual(state.final_hands[2].flowers,[35,34]);
  assert.match(groups.at(-1).className,/result-winning/);
  assert.deepEqual(cards[1].children[1].children.at(-1).children.map(t=>t.id),[32]);
  assert.deepEqual(cards[3].children[1].children[0].children.map(t=>t.id),[0,9,18,27]);
  assert.match(cards[1].children[0].innerHTML,/class="dealer">莊/);
  assert.deepEqual(cards.map(c=>c.children[0].innerHTML.match(/class="result-wind" aria-label="(.*?)"/)[1]),
    ['南家','東家','西家','北家']);
  assert.equal(cards.filter(c=>c.children[0].innerHTML.includes('class="dealer"')).length,1);
  assert.deepEqual(cards[0].children[0].children[0].children.map(amount=>
    amount.children.map(child=>child.textContent)), [['本局','+140'],['累積','1100']]);
  assert.deepEqual(cards[1].children[0].children[0].children.map(amount=>
    amount.children.map(child=>child.textContent)), [['本局','-60'],['累積','900']]);
  assert.doesNotMatch(content,/score-players|settlement-table/);
  assert.doesNotMatch(content,/莊家付款/);
});

test('every settlement hand and meld uses the viewer order rather than its owner preference', () => {
  const {elements,ctx} = settlementView();
  ctx.sortOrder = [2,1,0,3];
  elements['result-players'].children = [];
  ctx.showResult();
  const cards = elements['result-players'].children;
  const concealed = cards.map(card=>card.children[1].children
    .find(group=>group.attrs['aria-label']==='手牌').children.map(tile=>tile.id));
  assert.deepEqual(concealed,[[18,9,1,2,27],[18,9,0,27],[18,9,0,27],[18,9,0,27]]);
  assert.deepEqual(cards[0].children[1].children.slice(0,4).map(g=>g.children.map(t=>t.id)),
    [[34,35],[14,14,14],[3,4,5],[6,6,6,6]]);
});

test('ron tile is separate and a flower already in its flower group is never duplicated', () => {
  const ron = settlementView('RON');
  assert.match(ron.elements['result-players'].children[1].children[0].innerHTML,/放槍/);
  assert.deepEqual(ron.elements['result-players'].children[0].children[1].children.at(-1).children.map(t=>t.id),[9]);
  const flower = settlementView('TSUMO','ba_xian');
  flower.state.final_hands[2].drawn = null;
  flower.state.win_tile = 34;
  flower.elements['result-players'].children = [];
  flower.ctx.showResult();
  const groups = flower.elements['result-players'].children[0].children[1].children;
  assert.equal(groups.filter(g=>g.className.includes('result-winning')).length,0);
  const flowers = groups.find(g=>g.attrs['aria-label'] === '花牌');
  assert.deepEqual(flowers.children.map(t=>t.id),[34,35]);
  assert.match(flowers.children[0].className,/result-winning-tile/);
});

test('player details explain dealer payments without adding dealer tai twice', () => {
  const {elements,state,ctx} = settlementView('RON');
  const render = () => {
    elements['result-players'].children = [];
    ctx.showResult();
    return elements['result-players'].children;
  };
  state.dealer_streak = 2;
  state.settlement.tai = 1;
  state.settlement.breakdown = [{label:'三元牌',points:1}];
  state.settlement.payments = [0,-220,220,0];
  let cards = render();
  assert.equal(cards[0].children[2].children[0].textContent,'胡牌 1 台');
  assert.equal(cards[0].children[2].open,true);
  const dealer = cards[1].children[2];
  assert.equal(dealer.tag,'details');
  assert.equal(dealer.attrs.open,undefined);
  assert.notEqual(dealer.open,true);
  assert.equal(dealer.children[0].textContent,'莊・連 2　加 5 台');
  assert.deepEqual(dealer.children.slice(1).map(row=>row.children.map(n=>n.textContent)),
    [['基本收付','120'],['莊家加台　5 × 20','100'],['付給 贏家','220']]);
  state.settlement.payments = [-120,-220,460,-120];
  cards = render();
  assert.equal(cards[1].children[2].children.at(-1).children[1].textContent,'220');
  state.settlement.payments = [-120,0,120,0];
  cards = render();
  assert.equal(cards[1].children[2].children[0].textContent,'莊・連 2　本局未收付');
  assert.equal(cards[1].children[2].tag,'div');
  assert.equal(cards[1].children[2].children.length,1);
  state.dealer = state.winner;
  state.settlement.tai = 6;
  state.settlement.breakdown = [{label:'三元牌',points:1},{label:'莊家',points:5}];
  cards = render();
  assert.equal(cards.filter(c=>c.children[2]?.tag==='details').length,1);
  assert.deepEqual(cards[0].children[2].children.slice(1).map(r=>r.children[1].textContent),['1 台','5 台']);
  state.winner = null;
  state.settlement.breakdown = [];
  cards = render();
  assert.equal(cards.filter(c=>c.children[2]?.tag==='details').length,0);
});

test('zero-tai winner has a plain label instead of an empty expandable detail', () => {
  const {elements,state,ctx} = settlementView('RON');
  state.settlement.tai = 0;
  state.settlement.breakdown = [];
  state.settlement.payments = [0,-120,120,0];
  elements['result-players'].children = [];
  ctx.showResult();
  const cards = elements['result-players'].children;
  const winner = cards[0].children[2];
  assert.equal(winner.tag,'div');
  assert.equal(winner.children.length,1);
  assert.equal(winner.children[0].tag,'span');
  assert.equal(winner.children[0].textContent,'胡牌 0 台');
  assert.equal(cards[1].children[2].tag,'details');
});
