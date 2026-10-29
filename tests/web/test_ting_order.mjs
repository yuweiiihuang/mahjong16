import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const source=readFileSync(new URL('../../ui/web/app.js',import.meta.url),'utf8');
test('ting options and their waits have a stable numeric tile order without mutating state',()=>{
  const context=vm.createContext({});
  vm.runInContext(source.slice(source.indexOf('function uniqueTingOptions('),
    source.indexOf('function renderTing(')),context);
  const options=[{tile:28,waits:[{tile:11,unseen:2},{tile:2,unseen:1}]},
    {tile:0,waits:[{tile:20,unseen:3}]},
    {tile:28,waits:[{tile:2,unseen:1},{tile:11,unseen:2}]}];
  const original=JSON.stringify(options);
  const result=JSON.parse(JSON.stringify(context.uniqueTingOptions(options)));
  assert.deepEqual(result.map(option=>option.tile),[0,28]);
  assert.deepEqual(result[1].waits.map(wait=>wait.tile),[2,11]);
  assert.equal(JSON.stringify(options),original);
});
