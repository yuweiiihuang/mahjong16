import test from 'node:test';
import assert from 'node:assert/strict';
import {renderScoreChart} from '../../ui/web/session-chart.mjs';

const doc = {createElementNS(ns, tag) {
  return {tag, attrs:{}, children:[], classList:{add() {}},
    setAttribute(key, value) {this.attrs[key] = value;},
    append(child) {this.children.push(child);}};
}};

test('score chart keeps every seat and old result, with bounded flat-score coordinates', () => {
  const names = ['A', 'B', 'C', 'D'];
  const chart = renderScoreChart([
    {totals:[1000,1000,1000,1000]}, {totals:[1100,900,1000,1000]},
  ], names, doc);
  const lines = chart.children.filter(node => node.tag === 'polyline');
  assert.equal(lines.length, 4);
  assert.equal(lines[0].attrs.points, '55,100 580,20');
  assert.equal(lines[1].attrs.points, '55,100 580,180');
  assert.equal(lines[2].attrs.points, '55,100 580,100');
  assert.deepEqual(lines.map(line => line.children[0].textContent), names);
  assert.equal(chart.attrs.role, 'img');
  const flat = renderScoreChart([{totals:[1000,1000,1000,1000]}], names, doc);
  for (const line of flat.children.filter(node => node.tag === 'polyline')) {
    assert.equal(line.attrs.points, '55,100');
  }
});
