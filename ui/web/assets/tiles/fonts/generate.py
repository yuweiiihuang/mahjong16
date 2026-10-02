"""Rebuild outlined wan faces from local, OFL-licensed font sources.

Usage: python generate.py --wenkai /path/LXGWWenKaiTC-Regular.ttf --brush /path/YujiSyuku-Regular.ttf
The serif option copies the accepted A artwork exactly.
"""
import argparse
from pathlib import Path
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.boundsPen import BoundsPen

ROOT = Path(__file__).resolve().parent
CHARS = '一二三四五六七八九萬'

def faces(source, destination):
    font = TTFont(source)
    glyphs = font.getGlyphSet()
    cmap = font.getBestCmap()
    data = {}
    for char in CHARS:
        if ord(char) not in cmap:
            raise ValueError(f'Missing traditional glyph: {char}')
        glyph = glyphs[cmap[ord(char)]]
        path = SVGPathPen(glyphs); glyph.draw(path)
        bounds = BoundsPen(glyphs); glyph.draw(bounds)
        data[char] = (path.getCommands(), bounds.bounds)
    scale = min(58/max(b[2]-b[0] for _,b in data.values()),
                58/max(b[3]-b[1] for _,b in data.values()))
    def outlined(char, top, color):
        path,(x0,y0,x1,y1) = data[char]
        x = 21+(58-(x1-x0)*scale)/2-x0*scale
        y = top+(58-(y1-y0)*scale)/2+y1*scale
        return f'<path d="{path}" transform="matrix({scale:.6f} 0 0 {-scale:.6f} {x:.6f} {y:.6f})" fill="{color}"/>'
    destination.mkdir(exist_ok=True)
    for i,char in enumerate(CHARS[:-1]):
        svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 140">'
        svg += outlined(char,8,'#122e29') + outlined('萬',74,'#ad211f') + '</svg>'
        (destination/f'{i}.svg').write_text(svg)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--wenkai', required=True)
    parser.add_argument('--brush', required=True)
    parser.add_argument('--iansui')
    parser.add_argument('--klee')
    args = parser.parse_args()
    (ROOT/'serif').mkdir(exist_ok=True)
    for i in range(9):
        source = ROOT.parents[2]/'designs'/'wan-options'/'a'/f'{i+1}.svg'
        (ROOT/'serif'/f'{i}.svg').write_bytes(source.read_bytes())
    faces(args.wenkai,ROOT/'wenkai')
    faces(args.brush,ROOT/'brush')
    if args.iansui:
        faces(args.iansui,ROOT/'iansui')
    if args.klee:
        faces(args.klee,ROOT/'klee')
