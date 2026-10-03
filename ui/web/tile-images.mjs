// Share successful images between settings previews and the 3D table.
export function createTileImageLoader(load, concurrency = 4) {
  const cache = new Map(), queue = [];
  let active = 0;
  function drain() {
    while (active < concurrency && queue.length) {
      const {url, resolve, reject} = queue.shift();
      active++;
      (async () => {
        for (let attempt = 0; attempt < 3; attempt++) {
          try { return await load(url); }
          catch (error) {
            if (attempt === 2) throw error;
          }
        }
      })().then(resolve, error => {
        cache.delete(url);
        reject(error);
      }).finally(() => { active--; drain(); });
    }
  }
  return url => {
    if (!cache.has(url)) {
      const pending = new Promise((resolve, reject) => queue.push({url, resolve, reject}));
      cache.set(url, pending);
      drain();
    }
    return cache.get(url);
  };
}

export const loadTileImage = createTileImageLoader(async url => {
  const response = await fetch(url, {signal:AbortSignal.timeout(15000)});
  if (!response.ok) throw new Error(`牌面載入失敗：${response.status}`);
  const src = URL.createObjectURL(await response.blob());
  const image = new Image();
  try {
    await new Promise((resolve, reject) => {
      image.onload = resolve;
      image.onerror = () => reject(new Error('牌面圖片無法顯示'));
      image.src = src;
    });
    return image;
  } catch (error) {
    URL.revokeObjectURL(src);
    throw error;
  }
});
