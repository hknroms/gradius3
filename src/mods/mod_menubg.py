"""メニューの背景: 3面ボス(ビッグコアMkIII)が反射レーザーを撃っている瞬間（奥の岩の背景はなし・暗く）
ボス・反射レーザー・自機はすべてスプライト(57個)。スプライト表 1KB と色 0.5KB だけを持つ。
MAME で記録したその瞬間の A面(ボス)・スプライト(レーザー・自機)・色から、メニュー表示用のデータを作る。
"""
import os, struct
D = os.path.join(os.path.dirname(__file__), 'menubg')
F = 7440
DIM = 0.40
COLSHIFT = 10
SHD_X, SHD_Y = int(os.environ.get('SHDX', '333')), int(os.environ.get('SHDY', '217'))   # #75 SHIELD COLOR を一番下の行へ移したので 185 → 209（上の行へはみ出す）→ 217（メニュー全体を1行下げた）
FF_DX, FF_DY = int(os.environ.get('FFDX', '14')), int(os.environ.get('FFDY', '0'))
SHIP, SHIP_OX, SHIP_OY = 71, int(os.environ.get('SHIPX', '184')), int(os.environ.get('SHIPY', '148'))   # 自機のスプライト番号と位置（スプライト座標）          # 記録時の A面スクロール(0x160) → メニュー中(0x1b0) の差 = 80ドット = 10タイル

def _load():
    """pal・spr はリポジトリにある（メニュー背景に使うのはこの2つだけ）。
    vram・chr（A面の岩の背景）は今は使っていないので、無ければ読まない（ROM 由来なのでリポジトリには入れない）"""
    def opt(name):
        f = os.path.join(D, '%s_%d.bin' % (name, F))
        return open(f, 'rb').read() if os.path.exists(f) else None
    v = opt('vram'); K = bytes(v[2*i+1] for i in range(0x4000)) if v else None
    chr_ = opt('chr')
    pal = open(os.path.join(D, 'pal_%d.bin' % F), 'rb').read()
    s = open(os.path.join(D, 'spr_%d.bin' % F), 'rb').read(); spr = bytes(s[i] for i in range(1, len(s), 2))
    return K, chr_, pal, spr

def blobs():
    K, chr_, pal, spr = _load()
    blank = 16
    cells = []; codes = set()
    for r in (range(32) if K is not None and chr_ is not None else ()):
        for c in range(64):
            i = r * 64 + c
            a = K[0x800 + i]; lo = K[0x2800 + i]
            code = lo | ((a & 1) << 8) | ((a & 0x1c) << 7)
            if code == blank: continue
            codes.add(code)
            cells.append((r * 64 + (c + COLSHIFT) % 64, a, lo))
    tiles = b''.join(struct.pack('>H', c) + chr_[c*32:c*32+32] for c in sorted(codes))
    cellb = b''.join(struct.pack('>HBB', i, a, lo) for i, a, lo in cells)
    p = bytearray()
    for o in range(0x200, 0x400, 2):          # スプライトの色（パレット16〜31）
        w = struct.unpack('>H', pal[o:o+2])[0]
        r, g, b = (w >> 10) & 31, (w >> 5) & 31, w & 31
        r, g, b = int(r * DIM + .5), int(g * DIM + .5), int(b * DIM + .5)
        p += struct.pack('>H', (w & 0x8000) | (r << 10) | (g << 5) | b)
    sp = bytearray(1024)
    for i in range(0, 1024, 8):
        if spr[i] & 0x80: sp[i:i+8] = spr[i:i+8]
    # 自機（表の71番）を移す: CUBE HEIGHT の上の空き行、先端が EX STAGE の行の A のあたり
    o = SHIP * 8
    sp[o+4] = (sp[o+4] & 0xfe) | (((256 - SHIP_OY) & 0x1ff) >> 8); sp[o+5] = (256 - SHIP_OY) & 0xff
    sp[o+6] = (sp[o+6] & 0xfe) | ((SHIP_OX & 0x1ff) >> 8); sp[o+7] = SHIP_OX & 0xff
    # シールド色の見本を SHIELD COLOR の右に置く。色3 はメニューで選んだ色を暗くせずに入れる
    x, y = SHD_X, SHD_Y
    # 自機とフォースフィールド（ゲーム中に記録した並び: 自機 コード 0x20ba・色0、フォースフィールド 0x8170・色3 は自機の y+8・x−14）。
    # 自機は暗くしない: 使っていないスプライトの色1 に、自機の色0 を暗くせずに入れて使う（2026-10-28 管理者の指示。フリーシールドの見本はやめた）
    p[32:64] = pal[0x200:0x220]
    def ent(n, b1, code, col, ry, rx): return bytes([0x80 | n, b1, code, col, (ry & 0x1ff) >> 8, ry & 0xff, (rx & 0x1ff) >> 8, rx & 0xff])
    # #75 手前の飾りの色（明るさ100%。ゲーム中の色を記録した値）: 2 = 5面ボスの石（ゲームではパレット12）・6 = 爆発・13 = キューブ（9面）
    for k, h in ((2, '000000000000000000001882290431483dab4e2f5a926b160000000000000000'),
                 (6, '0000000000010000000000ae00120d3621db3a7f4f7f639e4a5339d0294b0000'),
                 (13, '000000000000000000aa00ec04ce115015721db42e3642984efa5f5c7bde0844')):
        p[k * 32:k * 32 + 32] = bytes.fromhex(h)
    ry, rx = (256 - y + FF_DY) & 0x1ff, x + FF_DX
    sp[8:16] = ent(0x3a, 0x81, 0x70, 0x06, ry + 8, rx - 14)
    sp[16:24] = ent(0x3b, 0x20, 0xba, 0x02, ry, rx)
    return {'MBGPAL': (0, bytes(p)), 'MBGSPR': (0, bytes(sp))}   # ボス本体・レーザー・自機はすべてスプライト（A面は奥の岩なので使わない）

if __name__ == '__main__':
    b = blobs()
    for k, (n, d) in b.items(): print(k, n, len(d))
    print('total', sum(len(d) for n, d in b.values()))
