export const TILE_FONTS = [
  {id:'mahjong-tw', name:'臺灣牌面（預設）'},
  {id:'mahjong-jp', name:'日式牌面'},
];
export const DEFAULT_TILE_FONT = 'mahjong-tw';
export const validTileFont = font => TILE_FONTS.some(item => item.id === font);
export function tileAsset(id, font = DEFAULT_TILE_FONT) {
  return (id >= 0 && id < 9) || font === 'mahjong-jp'
    ? `assets/tiles/fonts/${validTileFont(font) ? font : DEFAULT_TILE_FONT}/${id}.svg${id >= 9 ? '?v=imahjong-jp-1' : ''}`
    : `assets/tiles/${id}.svg?v=imahjong-tw-1`;
}
