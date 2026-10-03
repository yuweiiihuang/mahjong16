import test from 'node:test';
import assert from 'node:assert/strict';
import { createTileImageLoader } from '../../ui/web/tile-images.mjs';

test('previews and table share requests with at most four concurrent downloads', async () => {
  let active = 0, peak = 0, calls = 0;
  const load = createTileImageLoader(async url => {
    active++; calls++; peak = Math.max(peak,active);
    await new Promise(resolve => setTimeout(resolve,1));
    active--;
    return url;
  });
  const urls = Array.from({length:42},(_,id)=>`tile-${id}`);
  await Promise.all([...urls,...urls].map(load));
  assert.equal(calls,42);
  assert.equal(peak,4);
});

test('transient failures retry and exhausted failures can be requested again', async () => {
  let calls = 0, failing = true;
  const load = createTileImageLoader(async () => {
    calls++;
    if (failing) throw new Error('connection reset');
    return 'loaded';
  });
  await assert.rejects(load('tile'),/connection reset/);
  assert.equal(calls,3);
  failing = false;
  assert.equal(await load('tile'),'loaded');
  assert.equal(await load('tile'),'loaded');
  assert.equal(calls,4);
});

test('a successful retry is cached for later previews', async () => {
  let calls = 0;
  const load = createTileImageLoader(async () => {
    if (++calls === 1) throw new Error('temporary failure');
    return 'image';
  });
  assert.equal(await load('tile'),'image');
  assert.equal(await load('tile'),'image');
  assert.equal(calls,2);
});
