"""Compose an SVG comparison and font picker from the shipped vector faces."""
from pathlib import Path
import xml.etree.ElementTree as ET
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
ET.register_namespace('', 'http://www.w3.org/2000/svg')
ROOT=Path(__file__).resolve().parent
ASSETS=ROOT.parents[1]/'assets'/'tiles'/'fonts'
f=TTFont('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',fontNumber=3)
gs=f.getGlyphSet(); cmap=f.getBestCmap()
OPTIONS=[('serif','A · 典雅宋體','保留方案 A，作為預設'),('wenkai','霞鶩文楷','手寫楷書，溫和而清楚'),('brush','Yuji Syuku','毛筆書法，筆勢較鮮明'),('iansui','芫荽 Iansui','手寫楷書，筆畫圓潤自然'),('klee','Klee One','鋼筆手寫，細緻而有頓筆')]
def label(text,x,y,size,color='#122e29'):
    parts=[]; scale=size/f['head'].unitsPerEm
    for c in text:
        g=gs[cmap[ord(c)]]; pen=SVGPathPen(gs);g.draw(pen)
        parts.append(f'<path d="{pen.getCommands()}" fill="{color}" transform="translate({x:.2f} {y}) scale({scale} {-scale})"/>')
        x+=g.width*scale
    return ''.join(parts)
def tile(font,n,x,y,w,h):
    source=ET.tostring(ET.parse(ASSETS/font/f'{n}.svg').getroot(),encoding='unicode')
    source=source[source.index('>')+1:source.rindex('</')]
    return (f'<rect x="{x}" y="{y+4}" width="{w}" height="{h}" rx="6" fill="#196241"/>'
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="#f7f6ef" stroke="#d8d8c8"/>'
            f'<g transform="translate({x+w*40/384} {y+h*52/538}) scale({w*304/384/100} {h*434/538/140})">{source}</g>')
board=['<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="1290" viewBox="0 0 1440 1290">','<rect width="1440" height="1290" fill="#eef0e5"/>',label('青禾 · 萬字牌字體選擇',40,64,30),label('保留 A，加上手寫楷書與毛筆書法；全部為 SVG 路徑。',40,103,16,'#647767'),label('數字與萬字使用同字級、同字框；五組使用相同牌身。',40,131,14,'#647767')]
for col,(font,title,desc) in enumerate(OPTIONS):
    offset=(col//3)*550
    x=(40 if col<3 else 270)+(col%3)*460
    board += [f'<rect x="{x}" y="{166+offset}" width="440" height="516" rx="16" fill="#f8f8f0" stroke="#d4dacb"/>',label(title,x+24,212+offset,24),label(desc,x+24,243+offset,15,'#647767'),f'<rect x="{x+16}" y="{270+offset}" width="408" height="228" rx="12" fill="#285747"/>']
    for j,n in enumerate([0,4,8]): board.append(tile(font,n,x+33+j*132,302+offset,108,151))
    board.append(label('一至九萬 · 同一尺寸',x+24,539+offset,14,'#647767'))
    for n in range(9): board.append(tile(font,n,x+24+n*44,569+offset,37,52))
board += [label('牌桌設定 → 萬字牌字體 → 預覽 → 儲存。下次開啟保留選擇。',40,1268,15,'#647767'),'</svg>']
(ROOT/'comparison.svg').write_text(''.join(board))
html='''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>青禾 · 萬字牌字體選擇</title><style>*{box-sizing:border-box}body{margin:0;background:#eef0e5;color:#122e29;font-family:system-ui,sans-serif}main{max-width:1440px;padding:30px;margin:auto}h1{font-size:28px}p{color:#647767;line-height:1.7}select{font:inherit;padding:10px;border:1px solid #c8d0bf;background:#f8f8f0;color:#122e29;border-radius:8px}.controls{display:flex;gap:20px;align-items:center;flex-wrap:wrap}.hand{display:flex;gap:10px;flex-wrap:wrap;background:#285747;border-radius:12px;padding:24px;margin:20px 0}.tile{display:block;width:calc(49px * var(--zoom));height:calc(68px * var(--zoom));border:1px solid #d8d8c8;background:#f7f6ef;border-radius:6px;box-shadow:0 4px #196241}.tile img{width:100%;height:100%;padding:9.665% 10.417%;object-fit:fill}.board{width:100%}a{color:#285747}</style><main><h1>青禾 · 萬字牌字體選擇</h1><p>A 保留為預設。新增手寫楷書、毛筆書法與鋼筆手寫，字形皆已轉為 SVG 路徑，數字與「萬」同字級。</p><div class="controls"><label>字體 <select id="font">'''+''.join(f'<option value="{key}">{title}</option>' for key,title,desc in OPTIONS)+'''</select></label><label>預覽倍率 <input id="zoom" type="range" min="0.65" max="2" step="0.05" value="1"></label><a href="comparison.svg">SVG 比較圖</a><a href="/">回牌桌</a></div><div class="hand" id="hand"></div><p>在牌桌右上角「設定 → 萬字牌字體」也能預覽、儲存並套用到 3D 牌桌。Yuji Syuku 為日式毛筆字形，使用繁體「萬」。</p><img class="board" src="comparison.svg" alt="宋體、文楷與毛筆書法比較"><script>function render(){const font=document.querySelector('#font').value,hand=document.querySelector('#hand');hand.style.setProperty('--zoom',document.querySelector('#zoom').value);hand.innerHTML=Array.from({length:9},(_,id)=>`<span class="tile"><img src="../../assets/tiles/fonts/${font}/${id}.svg" alt="${id+1}萬"></span>`).join('')}document.querySelector('#font').onchange=render;document.querySelector('#zoom').oninput=render;render()</script></main></html>'''
(ROOT/'index.html').write_text(html)
