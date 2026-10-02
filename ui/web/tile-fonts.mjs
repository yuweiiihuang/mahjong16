export const TILE_FONTS = [
  {id:'serif', name:'典雅宋體 A（預設）'},
  {id:'wenkai', name:'霞鶩文楷 · 手寫楷書'},
  {id:'brush', name:'Yuji Syuku · 毛筆書法'},
  {id:'iansui', name:'芫荽 · 手寫楷書'},
  {id:'klee', name:'Klee One · 鋼筆手寫'},
];
export const DEFAULT_TILE_FONT = 'serif';
export const validTileFont = font => TILE_FONTS.some(item => item.id === font);
export function tileAsset(id, font = DEFAULT_TILE_FONT) {
  return id >= 0 && id < 9
    ? `assets/tiles/fonts/${validTileFont(font) ? font : DEFAULT_TILE_FONT}/${id}.svg`
    : `assets/tiles/${id}.svg`;
}
