# #32: 面クリアで B 面を作り直すとき、どの升目でも「番号は新しい・属性は古い」瞬間があったとして、
# 自機の範囲（X $1000〜$11000・Y $2000〜$E000、8ドットおき）のどこが地形に当たるかを地図で出す
# usage: python3 cells.py <clr.lua の出力フォルダ> [作り直す前のフレーム(既定6)] [後(既定8)]
import sys, os
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'terr.py')).read().split('xs = range')[0].replace("D = sys.argv[1]", "D = None"))
D = sys.argv[1]; a = int(sys.argv[2]) if len(sys.argv) > 2 else 6; b = int(sys.argv[3]) if len(sys.argv) > 3 else 8
rd = lambda k, f: open(f'{D}/{k}_{f}.bin', 'rb').read()
XS = range(0x1000, 0x11001, 0x800); YS = range(0x2000, 0xe001, 0x800)
v0, v1 = rd('vram', a), rd('vram', b)
def run(vr):
    globals()['load'] = lambda k, f: {'vram': vr, 'chr': rd('chr', b), 'shr': rd('shr', b)}[k]
    h, _ = hits(0, XS, YS); return set((p[0], p[1]) for p in h)
base = run(v1); hy = bytearray(v1); hy[0x2000:0x4000] = v0[0x2000:0x4000]; H = run(bytes(hy)) - base
print('map %02x' % rd('shr', b)[0x39c0], '当たる点', len(H), '/', len(XS) * len(YS))
print('Y\\X  ' + ''.join('%x' % ((x >> 12) & 0xf) for x in XS))
for y in YS: print('%04x ' % y + ''.join('#' if (x, y) in H else '.' for x in XS))
