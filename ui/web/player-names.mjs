export const RANDOM_NAMES = [
  '槓上開花椰菜', '海底撈月餅', '清一色番茄', '碰碰胡椒粉',
  '一條龍蝦', '白板擦不掉', '東風破水餃', '七索吊烤雞',
];

export function randomPlayerName(previous = '') {
  const choices = RANDOM_NAMES.filter(name => name !== previous);
  return choices[Math.floor(Math.random() * choices.length)];
}
