"""Build SVG-only wan tile proposals; glyphs are outlined, never rasterized."""
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.boundsPen import BoundsPen

ET.register_namespace('', 'http://www.w3.org/2000/svg')
ROOT = Path(__file__).resolve().parent
FONTS = {key: TTFont('/usr/share/fonts/opentype/noto/'+name+'.ttc', fontNumber=3)
         for key, name in [('serif','NotoSerifCJK-Bold'), ('light','NotoSerifCJK-Regular'),
                           ('sans','NotoSansCJK-Bold')]}
INK, RED, PAPER = '#122e29', '#ad211f', '#f7f6ef'
OPTIONS = [
 ('a','A · 典雅宋體','推薦 · 最接近青和的典雅氣質','serif',(21,8,58,58),(21,74,58,58),49,68,6),
 ('b','B · 放大粗宋','字面更飽滿 · 小尺寸容易辨認','serif',(18,3,64,64),(18,73,64,64),53,68,8),
 ('c','C · 圓潤黑體','粗細均勻 · 筆畫俐落、辨識直接','sans',(20,6,60,60),(20,74,60,60),49,68,11),
 ('d','D · 修長細宋','留白較多 · 安靜、偏文雅','light',(24,11,52,52),(24,77,52,52),46,72,4),
]

def glyph(char, font, box, color):
    f=FONTS[font]; gs=f.getGlyphSet(); g=gs[f.getBestCmap()[ord(char)]]
    p=SVGPathPen(gs); g.draw(p)
    b=BoundsPen(gs); g.draw(b); x0,y0,x1,y1=b.bounds
    x,y,w,h=box
    # All numerals and 萬 share a single font scale and equal character boxes.
    # Preserve each glyph's native aspect ratio, including the thin 一 / 二.
    bounds=[]
    for ref in '一二三四五六七八九萬':
        pen=BoundsPen(gs); gs[f.getBestCmap()[ord(ref)]].draw(pen)
        bounds.append(pen.bounds)
    scale=min(w/max(b[2]-b[0] for b in bounds), h/max(b[3]-b[1] for b in bounds))
    sx=sy=scale
    x+=(w-(x1-x0)*scale)/2
    y+=(h-(y1-y0)*scale)/2
    return f'<path d="{p.getCommands()}" transform="matrix({sx:.6f} 0 0 {-sy:.6f} {x-x0*sx:.6f} {y+y1*sy:.6f})" fill="{color}"/>'

def label(text,x,y,size,color=INK,font='sans'):
    chunks=[]
    for ch in text:
        if ch==' ': x+=size*.35; continue
        f=FONTS[font]; gs=f.getGlyphSet(); g=gs[f.getBestCmap()[ord(ch)]]
        p=SVGPathPen(gs); g.draw(p)
        s=size/f['head'].unitsPerEm
        chunks.append(f'<path d="{p.getCommands()}" fill="{color}" transform="translate({x:.3f} {y}) scale({s:.6f} {-s:.6f})"/>')
        x+=g.width*s
    return ''.join(chunks)

def art(key, n):
    return ET.tostring(ET.parse(ROOT/key/f'{n}.svg').getroot(),encoding='unicode')

def tile(key,n,x,y,w,h,r):
    # Same face inset as loadFaces(): 40/384 horizontally and 52/538 vertically.
    face=art(key,n)
    inner=face[face.index('>')+1:face.rindex('</')]
    return (f'<rect x="{x}" y="{y+4}" width="{w}" height="{h}" rx="{r}" fill="#196241"/>'
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{PAPER}" stroke="#d8d8c8"/>'
            f'<g transform="translate({x+w*40/384:.3f} {y+h*52/538:.3f}) scale({w*304/384/100:.6f} {h*434/538/140:.6f})">{inner}</g>')

for key,title,desc,font,number_box,wan_box,w,h,r in OPTIONS:
    (ROOT/key).mkdir(exist_ok=True)
    for i,ch in enumerate('一二三四五六七八九'):
        svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 140">'+glyph(ch,font,number_box,INK)+glyph('萬',font,wan_box,RED)+'</svg>'
        (ROOT/key/f'{i+1}.svg').write_text(svg)
(ROOT/'current').mkdir(exist_ok=True)
for i in range(9): shutil.copyfile(ROOT.parent.parent/'assets'/'tiles'/f'{i}.svg',ROOT/'current'/f'{i+1}.svg')
shutil.copyfile(ROOT.parent.parent/'assets'/'tiles'/'FONT-LICENSE.txt',ROOT/'FONT-LICENSE.txt')

board=['<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="1320" viewBox="0 0 1440 1320">',
 '<rect width="1440" height="1320" fill="#eef0e5"/>',label('青和 · 萬字牌樣式提案',48,61,30),
 label('SVG 向量字形 ／ 深綠數字 × 朱紅萬字 × 米白牌身',48,97,15,'#647767'),
 label('數字與萬字同字級、同字框；牌身比例與圓角是示意。',48,124,14,'#647767')]
# Baseline across the top.
board+=['<rect x="40" y="153" width="1360" height="178" rx="16" fill="#285747"/>',label('目前版本',65,193,20,'#eef0df'),label('現有字形與比例',65,225,13,'#bccdad')]
for n in range(1,10): board.append(tile('current',n,410+(n-1)*83,186,65,91,6))
for idx,(key,title,desc,font,number_box,wan_box,w,h,r) in enumerate(OPTIONS):
    x=40+(idx%2)*690; y=355+(idx//2)*462
    board += [f'<rect x="{x}" y="{y}" width="670" height="440" rx="16" fill="#f8f8f0" stroke="#d4dacb"/>',
              label(title,x+25,y+42,23),label(desc,x+25,y+70,14,'#647767'),
              f'<rect x="{x+20}" y="{y+92}" width="630" height="200" rx="12" fill="#285747"/>']
    for j,n in enumerate([1,5,9]): board.append(tile(key,n,x+110+j*160,y+111,w*2,h*2,r*2))
    board.append(label('一至九萬 · 手牌尺寸比較',x+25,y+324,13,'#647767'))
    for n in range(1,10): board.append(tile(key,n,x+25+(n-1)*69,y+342,w,h,r))
board += [label('A 標準圓角 49×68  ｜  B 稍寬 53×68  ｜  C 大圓角 49×68  ｜  D 修長 46×72',48,1300,14,'#647767'),'</svg>']
(ROOT/'comparison.svg').write_text(''.join(board))

cards=[]
for key,title,desc,font,number_box,wan_box,w,h,r in OPTIONS:
    cards.append(f'<button data-option="{key}" style="--tw:{w}px;--th:{h}px;--tr:{r}px"><strong>{title}</strong><span>{desc}</span><div class="samples">'+''.join(f'<i class="tile"><img src="{key}/{n}.svg" alt="{n}萬"></i>' for n in [1,5,9])+'</div></button>')
html='''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>青和 · 萬字牌樣式提案</title><style>
*{box-sizing:border-box}body{margin:0;background:#eef0e5;color:#122e29;font-family:system-ui,sans-serif}main{max-width:1440px;margin:auto;padding:30px}h1{font-size:28px;margin:0 0 12px}p{color:#647767;line-height:1.7}a{color:#285747}.board{width:100%;display:block;margin-top:24px}.controls{display:flex;gap:14px;align-items:center;flex-wrap:wrap;margin:22px 0}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}button{color:inherit;text-align:left;background:#f8f8f0;border:1px solid #ccd3c4;border-radius:12px;padding:18px;cursor:pointer}button[aria-pressed=true]{outline:2px solid #285747}strong,span{display:block}span{font-size:12px;color:#647767;margin-top:8px}.samples{display:flex;gap:12px;background:#285747;padding:18px 12px;margin-top:16px;border-radius:8px;justify-content:center}.tile{display:inline-flex;flex:none;width:var(--tw,49px);height:var(--th,68px);border-radius:var(--tr,6px);background:#f7f6ef;border:1px solid #d8d8c8;box-shadow:0 4px #196241}.tile img{width:100%;height:100%;padding:9.665% 10.417%;object-fit:fill}.hand{display:flex;gap:6px;flex-wrap:wrap;padding:25px;background:#285747;border-radius:12px;min-height:145px;align-items:center}.hand .tile{width:calc(var(--tw)*var(--zoom));height:calc(var(--th)*var(--zoom));border-radius:calc(var(--tr)*var(--zoom))}label{font-size:14px}#selection{font-weight:600}.note{font-size:13px}@media(max-width:850px){.cards{grid-template-columns:repeat(2,1fr)}main{padding:16px}}@media(max-width:480px){.cards{grid-template-columns:1fr}}
</style><main><h1>青和 · 萬字牌樣式提案</h1><p>保留米白牌身、玉綠牌背、深綠數字與朱紅「萬」。四組皆為 SVG 路徑字形，數字與「萬」使用相同字級與字框。點選方案，可比較一至九萬的手牌尺寸。</p><div class="cards">'''+''.join(cards)+'''</div><div class="controls"><b id="selection"></b><label>預覽倍率 <input id="zoom" type="range" min="0.65" max="2" step="0.05" value="1"></label><label><input id="body" type="checkbox" checked> 套用提案牌身比例與圓角</label><a href="comparison.svg" download>下載 SVG 比較圖</a></div><div class="hand" id="hand"></div><p class="note">關閉牌身選項，可在現有 49×68 比例下比較純牌面。牌身形狀是示意，正式採用時需同步調整 Three.js 幾何；目前遊戲仍使用原版素材。字形：Noto Serif / Sans CJK TC（SIL OFL），已轉路徑，不依賴裝置字體。</p><img class="board" src="comparison.svg" alt="目前版本與四組 SVG 萬字牌樣式比較"><script>
const options='''+str({k:{'title':t,'w':w,'h':h,'r':r} for k,t,d,f,nb,wb,w,h,r in OPTIONS}).replace("'",'"')+''';let key='a';function render(){const o=options[key],body=document.querySelector('#body').checked,hand=document.querySelector('#hand');hand.style.cssText=`--tw:${body?o.w:49}px;--th:${body?o.h:68}px;--tr:${body?o.r:6}px;--zoom:${document.querySelector('#zoom').value}`;hand.innerHTML=Array.from({length:9},(_,i)=>`<i class="tile"><img src="${key}/${i+1}.svg" alt="${i+1}萬"></i>`).join('');document.querySelector('#selection').textContent=o.title;document.querySelectorAll('[data-option]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.option===key)))}document.querySelectorAll('[data-option]').forEach(b=>b.onclick=()=>{key=b.dataset.option;render()});document.querySelector('#zoom').oninput=render;document.querySelector('#body').onchange=render;render();
</script></main></html>'''
(ROOT/'index.html').write_text(html)
print('Generated 36 proposal tiles, baseline copies, comparison.svg and index.html')
