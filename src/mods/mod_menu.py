"""サブCPU側: 隠しメニュー（描画・操作）— テーブル駆動
値は共有RAMメールボックス設定領域 MB+8〜 に保持（メインが開始時に参照）。
前回値は サブ私有RAM(V_LASTBUF)に保存。
※ タイル座標/属性は MAME実測後に TILE_* / ATTR_* を調整する。
"""
import struct

# (ラベル, 種別, 最小, 最大, MBオフセット, 値文字列 or None, 既定値)   種別 0=数値 1=列挙 2=アクション
# 種別 3 = 面/エリアの表の1行（最小値=面番号 1..12、最大値=その面のエリア数）
# 1面V・7面IV・8面V はボス戦中の復活地点で、そこから開始すると即面クリアになるため出さない
# 次の版で外すもの（2026-10-29 管理者決定）: MODE の BOSS RUSH と、場所を調整して足した復活地点（❶〜❹。10面 ❶ は残す）。
# 後の版で戻すときは EXTRA_AREAS=1 BOSSRUSH=1 でビルドする（mod_main も同じ変数を見る）
import os
EXTRA_AREAS = os.environ.get('EXTRA_AREAS') == '1'
BOSSRUSH = os.environ.get('BOSSRUSH') == '1'
NOINV = os.environ.get('NO_INV') == '1'   # スタートメニュー・ポーズの INVINCIBLE を外す（一般公開のとき。NO_INV=1。2026-10-30 管理者：今は残す）
# 各行の表示（英字は普通の文字、数字は白抜き ❶〜❹）
_W = lambda n: '#%d' % n
AREA_LABELS_LESS = [
    ['A', 'B', 'C', 'D'],                                         # 1面
    ['A', 'B', 'C', 'D', 'E'],                                    # 2面
    ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'],                     # 3面
    ['A'],                                                        # 4面
    ['A', 'B', 'C', 'D', 'E'],                                    # 5面
    ['A', 'B', 'C', 'D'],                                         # 6面
    ['A', 'B', 'C'],                                              # 7面
    ['A', 'B', 'C', 'D'],                                         # 8面
    ['A'],                                                        # 9面
    ['A', _W(1), 'B', 'C', 'D', 'E', 'F', 'G', 'H'],              # 10面: ❶ボスラッシュ直後
    ['A', 'B'],                                                   # EX STAGE
    [],
    ['A', 'B', 'C', 'D', 'E'],                                    # BOSS RUSH（10面のボス2〜6の手前）
]
AREA_LABELS = [
    ['A', 'B', 'C', 'D', _W(1)],                                  # 1面: ❶ボスの手前
    ['A', 'B', 'C', 'D', 'E'],                                    # 2面
    ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', _W(1)],              # 3面: ❶ビッグコアMkIIIの手前
    ['A'],                                                        # 4面
    ['A', 'B', 'C', 'D', 'E', _W(1), _W(2)],                      # 5面: ❶中ボスの手前 ❷ボスの手前
    ['A', 'B', 'C', 'D', _W(1)],                                  # 6面
    ['A', 'B', 'C', _W(1)],                                       # 7面
    ['A', 'B', 'C', 'D', _W(1)],                                  # 8面
    ['A', _W(1), _W(2)],                                          # 9面: ❶キューブ地帯の手前 ❷ボスの手前
    ['A', _W(1), 'B', 'C', 'D', 'E', 'F', 'G', _W(2), 'H', _W(3), _W(4)],   # 10面: ❶ボスラッシュ直後 ❷クラブ ❸ラスボスの手前 ❹脱出
    ['A', 'B'],                                                   # EX STAGE
    [],
    ['A', 'B', 'C', 'D', 'E'],                                    # BOSS RUSH
]
if not EXTRA_AREAS: AREA_LABELS = AREA_LABELS_LESS
AREAS = [len(x) for x in AREA_LABELS]   # 選べるエリア数
STAGE_LABELS = ['STAGE   %d' % i for i in range(1, 10)] + ['STAGE  10', 'EX STAGE', '', 'BOSS RUSH']   # 数字の右端を BOSS RUSH の H にそろえる
# 行の並び: 面1〜10, BOSS RUSH(内部の面番号13), EX STAGE(11。A=グラディウス B=サラマンダ → 開始時に 11/12)
ROW_ORDER = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 12, 10]
# MODE（メニューの番号。2026-10-31 管理者決定）: 0 NORMAL / 1 NORMAL NO DEATH / 2 RESPAWN（その場復活 #35）/ 3 RESPAWN NO DEATH /
# 4 CUBE RUSH / 5 CUBE NO DEATH / 6 BOSS RUSH（BOSSRUSH=1）。奇数 1・3・5 が NO DEATH（無敵・時間制）。
# 始めるとき（mf_go）に MODECV で「動いているときの MODE（0 普通・1 NO DEATH・2 キューブラッシュ・4 ボスラッシュ）・ND_FLAG・
# その場復活の印（MB+$3E）」に変換する。ゲーム中の処理は動いているときの MODE を見る（メニューの番号は控えの値だけ）
MODE_NAMES = ['NORMAL', 'NORMAL NO DEATH', 'RESPAWN', 'RESPAWN NO DEATH', 'CUBE RUSH', 'CUBE NO DEATH', 'BOSS RUSH']
MODECV = [(0, 0, 0), (1, 1, 0), (0, 0, 1), (1, 1, 1), (2, 0, 0), (2, 1, 0), (4, 0, 0)]
ITEMS = [
    ('INVINCIBLE', 1, 0, 1, 0x20, ['OFF', 'ON'], 0),   # 一時的な項目（無敵）
    ('MODE',      1, 0, 6 if BOSSRUSH else 5, 0x0b, MODE_NAMES[:7 if BOSSRUSH else 6], 0),   # 番号は MODE_NAMES の順（2026-10-31 管理者決定）。始めるときに mf_go が MODECV で変換する   # 0=NORMAL 1=NO DEATH(#36) 2=CUBE RUSH 3=CUBE NO DEATH(#39。mf_go で 2 に変換して ND_FLAG=1) 4=BOSS RUSH
    ('LOOP',      0, 1, 99, 0x09, None, 1),
] + [(STAGE_LABELS[i], 3, i + 1, AREAS[i], 0x08, None, 0) for i in ROW_ORDER] + [
    ('CUBE HEIGHT', 1, 0, 16, 0x35, ['RANDOM'] + [str(i) for i in range(1, 17)], 0),   # キューブラッシュの並び: 3つとも RANDOM = 純正のまま
    ('      SHIFT', 1, 0, 4, 0x36, ['RANDOM', 'A', 'B', 'C', 'D'], 0),
    ('       TYPE', 1, 0, 45, 0x37, ['RANDOM'] + ['%02d' % i for i in range(1, 46)], 0),
    ('FULL POWER   SPEED', 0, 0, 5, 0x0d, None, 3),       # フル装備コマンドのスピード（スピードアップを使った回数）
    ('FULL POWER CAPSULE', 1, 0, 7, 0x23, ['OFF', 'SPEEDUP', 'MISSILE', 'DOUBLE', 'LASER', 'OPTION', '_', '\x8c'], 6),   # フル装備コマンドの後のカプセルゲージの位置。'_'=? / 0x8c=!（描き足した字）
    ('HUNTER NEXT', 1, 0, 3, 0x1b, ['DEFAULT', 'TYPE 1', 'TYPE 2', 'TYPE 3'], 0),
    ('SHIELD COLOR', 1, 1, 10, 0x16, ['?', 'BLUE', 'RED', 'GREEN', 'GOLD', 'PURPLE', 'CYAN', 'ORANGE', 'PINK', 'SILVER', 'BLACK'], 1),   # #75 SHIELD COLOR を一番下に（見本の絵は上にはみ出す）
]
# 各項目の画面の行（可視は行2〜29）。面の表の後・CUBE の後に1行ずつ空ける
ROWS = [2, 3, 5] + list(range(7, 19)) + [20, 21, 22] + [24, 25, 26, 27]   # INVINCIBLE が一番上、最下段は PUSH START
assert len(ROWS) == len(ITEMS)
PLUS_ROWS = ['........', '...f....', '...f9...', '.ffffff.', '..9f9999', '...f9...', '....9...', '........']   # ゲームの文字と同じ傾き・影
PLUS_GFX = bytes(int(r[i] if r[i] != '.' else '0', 16) << 4 | int(r[i+1] if r[i+1] != '.' else '0', 16) for r in PLUS_ROWS for i in range(0, 8, 2))
BANG_ROWS = ['...ff...', '...ff9..', '...ff9..', '...f9...', '....9...', '...ff...', '...ff9..', '....99..']
BANG_GFX = bytes(int(r[i] if r[i] != '.' else '0', 16) << 4 | int(r[i+1] if r[i+1] != '.' else '0', 16) for r in BANG_ROWS for i in range(0, 8, 2))
# ---- 飛んでくるキューブの色分け（CUBE INFO 表示中）: 反応する位置が左寄りの5か所だけ色を付ける ----
# 反応する位置 x=158 緑 / 126 黄緑 / 94 黄 / 62 橙 / 30 赤。使うスプライトのパレットは 9面で使われていない 21,22,24,26,30
CC_PALS = [21, 22, 28, 26, 30, 23, 25, 27, 31]   # 21,22,26,28,30 は9面で未使用（24 はオプションハンターが使う）。23,25,27,31 はボス戦だけで使う → ラッシュの間だけ借りて、終わったら元に戻す
CC_X    = [254, 222, 190, 158, 126, 94, 62, 30]   # 反応する位置（右から3〜10番目）。右から1・2番目（318・286）は元の色のまま
CC_TINT = [(0.05, 0.55, 1.0), (0.0, 0.85, 0.95), (0.0, 0.95, 0.55), (0.15, 1.0, 0.2), (0.6, 1.0, 0.1), (1.0, 0.95, 0.1), (1.0, 0.5, 0.05), (1.0, 0.05, 0.08),
           None]                                  # 最後 = 反応しない: 灰色
def _stage9_pal():
    import os
    pal = open(os.path.join(os.path.dirname(__file__), 'cubecol', 'pal_stage9.bin'), 'rb').read()
    return [(pal[i*2] << 8) | pal[i*2+1] for i in range(0x200)]
# ---- #75 スタートメニューのキューブの並びの見本（点）: キューブの3行にカーソルがある間だけ、右下（桁36〜51・段17〜24）に32個を点で出す ----
# 文字の面に、借りた字 0xC00〜0xC7F（128字。メニューの間だけ。ゲームが始まると START 表示で上書きされるのを確認）にドットで描く。
# 色は文字の面のパレット3（ゲームも改造も使っていないのを確認）: 1〜8 = 反応する位置の色（CUBE COLOR と同じ順）・9 = 反応しない（灰）・
# 10 = 右寄りの2か所（元の氷の色）・11 = 枠・12 = 目盛りの線・13 = 黒（不透明）。メインの PalCopy が $102200 から写す
DOT_W = [64, 176, 32, 224, 80, 208, 160, 112, 48, 128, 80, 96, 144, 192, 64, 16]   # 何個目か>>1 で引く待ち時間（解析ページの W と同じ）
DOT_CATX = [254, 222, 190, 158, 126, 94, 62, 30]
DOT_HY = [208, 192, 176, 160, 144, 144, 128, 128, 112, 112, 96, 96, 80, 64, 48, 32]
def _rgb15(h):
    r, g, b = (int(h[i:i + 2], 16) for i in (1, 3, 5))
    return ((r * 31 + 127) // 255 << 10) | ((g * 31 + 127) // 255 << 5) | ((b * 31 + 127) // 255)
def dot_palette():
    cols = ['#1e8cff', '#00c8e6', '#00d98c', '#2ecc40', '#9be22d', '#ffd400', '#ff8a00', '#ff1a1a', '#8a8f98', '#9fd4ff', '#5a5aaa', '#232346', '#000000']
    return struct.pack('>16H', 0, *[_rgb15(c) for c in cols], 0, 0)
def dot_cat():
    out = []
    for n in range(1, 33):
        w = DOT_W[(n >> 1) & 15]
        x = 350 - 2 * w
        out.append(9 if w >= 171 else (DOT_CATX.index(x) + 1 if x in DOT_CATX else 10))
    return bytes(out)
def dot_level():
    lv = {y: i + 1 for i, y in enumerate(sorted(set(DOT_HY), reverse=True))}
    return bytes(lv[y] for y in DOT_HY)
def cube_tint_palettes():
    P = _stage9_pal()
    src = P[29*16:29*16+16]                       # キューブの色（パレット29）
    out = bytearray()
    for pl, t in zip(CC_PALS, CC_TINT):
        out += struct.pack('>I', 0x80000 + pl * 32 + 8)      # 0〜3番の色は変えないので 4番から（バッファを小さくするため）
        for i, w in enumerate(src):
            if i < 4: continue
            if w == 0: out += struct.pack('>H', w); continue
            r, g, b = (w >> 10) & 31, (w >> 5) & 31, w & 31   # 色は xRRRRRGGGGGBBBBB
            L = min(31.0, (r * 0.3 + g * 0.59 + b * 0.11) * 1.25)
            if t is None: nr = ng = nb = min(31, int(L * 0.85 + 0.5))
            else: nr, ng, nb = (min(31, int(L * tc * 0.85 + c * 0.15 + 0.5)) for tc, c in zip(t, (r, g, b)))
            out += struct.pack('>H', (w & 0x8000) | (nr << 10) | (ng << 5) | nb)
    return bytes(out)
# ---- CUBE LINE: 反応する位置の縦の点線と、高さの印（文字の面 = 一番手前。色はパレット6の空き番号）----
LN_X    = [254, 222, 190, 158, 126, 94, 62, 30, 286]   # 反応する位置（キューブの x）: 色1〜8 と、右から2番目（286。右端の318は画面の外）
LN_IDX  = [6, 7, 8, 10, 11, 12, 13, 14, 15]           # パレット6の色番号（9 と 15 は見出しの灰色。286 の線は 15 の灰色）
LN_HY   = [208, 192, 176, 160, 144, 128, 112, 96, 80, 64, 48, 32]   # キューブの高さ（12通り）
LN_TILE = 0xf00                                       # 使う文字の番号（9面では使われていない 0xf00〜0xf09）
LN_ROWS = range(5, 28)                                # 縦線の段（スコア・ランク・位置の表示とパワーアップゲージの段は避ける）
def _ln_col(x): return (x + 5 + 96) >> 3              # 画面の x = キューブの x + 5、文字の面の桁 = (画面の x + 96) / 8
def _tile(pix):
    """pix: 8x8 の色番号 → 4bpp の32バイト"""
    return bytes((pix[r][i] << 4) | pix[r][i + 1] for r in range(8) for i in range(0, 8, 2))
def _vpix(kind, idx):
    """縦線の形: kind 1=粗い点線(4段に1つ) 2=細かい点線(1段おき) 3=実線（上下の端の印用）"""
    p = [[0] * 8 for _ in range(8)]
    for r in range(8):
        if kind == 3 or (kind == 2 and r % 2 == 0) or (kind == 1 and r % 4 == 0): p[r][3] = idx
    return p
def _hpix(kind):
    """横線の形（いちばん上の段・色15の灰色）: 1=粗い点線(4ドットに1つ) 2=つながった線（暗い色9で薄く） 3=左端の印 4=右端の印"""
    p = [[0] * 8 for _ in range(8)]
    for i in range(8):
        if (kind == 1 and i % 4 == 0) or (kind == 3 and i <= 5) or (kind == 4 and i >= 2): p[0][i] = 15
        if kind == 2: p[0][i] = 9                     # 線: つながった線を暗い灰色（色9）で薄く
    return p
# ---- #38 HIT DISP: 当たり判定の表示（サブだけで描く。メインのコードは使わない）----
# 当たりの表はメインが毎フレーム、共有RAMのオブジェクト（$101000・$101240〜×54・$102320〜×66、$50 ずつ）から作る（$222AC）:
#   X = (+8.l >> 8) + +$36.w、Y = (+$C.l >> 8) + +$38.w、半分の幅 +$14.w、半分の高さ +$16.w。先頭の bit7 = 動いている
# サブも同じ所を読んで描く。自機（$101000）はドット単位の枠（文字 HB_PL〜+5 の 3×2 字に描く）、ほかは升目に印（文字 HB_MARK）
HB_FLAG = 0x203e1b     # ON/OFF（共有RAM $103E1B。ゲームが消さない所。#57 で $103812 から移した。メニューから始めるたびに OFF）
HB_PL   = 0xe80        # 使う文字: 1〜10面で一度も使われなかった 0xE80〜0xE86（TECH.md「文字の空き」）
HB_MARK = 0xe86
HB_PCOL = 14           # パレット6 の色: 14 = 赤（自機の枠）
HB_MCOL = 12           # 12 = 黄（升目の印）
def hb_mark_tile():
    p = [[HB_MCOL if (r % 2 == 0 and i % 2 == 0) else 0 for i in range(8)] for r in range(8)]
    return _tile(p)
def line_tiles():
    """文字 0xf00〜0xf42: 縦 (V-1)*9+k / 横 27〜30 / 縦と横の交わり 31+((V-1)*2+(H-1))*9+k"""
    out = bytearray()
    for v in (1, 2, 3):
        for k in range(9): out += _tile(_vpix(v, LN_IDX[k]))
    for hk in (1, 2, 3, 4): out += _tile(_hpix(hk))
    for v in (1, 2):
        for hh in (1, 2):
            for k in range(9):
                a, b = _vpix(v, LN_IDX[k]), _hpix(hh)
                out += _tile([[a[r][i] or b[r][i] for i in range(8)] for r in range(8)])
    out += bytes(32)   # 0xf43 = 透明（描いたかの目印）
    assert len(out) == 68 * 32
    return bytes(out)
def line_cols():
    return bytes(_ln_col(x) for x in LN_X) + b'\0'
def line_pal():
    # パレット6 の 6〜15番（メインが毎フレーム写す）: 6,7,8 = 色1〜3 / 9 = 見出しの暗い色 / 10〜14 = 色4〜8 / 15 = 見出しの灰色
    cols = []
    for t in CC_TINT[:8]:
        r, g, b = (min(31, int(c * 31 + 0.5)) for c in t)
        cols.append((r << 10) | (g << 5) | b)
    w = cols[0:3] + [0x10a9] + cols[3:8] + [0x5252]
    return b''.join(struct.pack('>H', v) for v in w)

# ---- CUBE FLASH（#48）: 反応する少し前から反応するまで、そのキューブを白っぽく光らせる。
# 色は CUBE COLOR の9つ目（灰色＝反応しない）の枠を白に替えて使う（CUBE FLASH が ON の間、反応しないキューブは元の色のまま）
CS_FLAG = 0x203e23     # CUBE SE（#60。0=OFF / 1〜=CUBE_SE の何番目の音。共有RAM $103E23。メニューから始めるたびに OFF）
# キューブが反応する瞬間の音（#60）: (表示, 音の番号)。表示は6文字まで。サブの CSE_TBL もここから作る
CUBE_SE = [('SE 0E ', 0x0e), ('SE 29 ', 0x29), ('SE 01 ', 0x01), ('SE 1E ', 0x1e)]
CF_FLAG = 0x203e2a     # ON/OFF（共有RAM $103E2A。#57 で $103813 → $103ED7 に移したが、$103ED7 は V_CEW（$103ED6.w）の下半分で毎フレーム消されていた → #73 で $103E2A へ。メニューから始めるたびに OFF）
CF_N    = 12           # 反応の何フレーム前から光らせるか
def _white_pal():
    P = _stage9_pal()
    src = P[29*16:29*16+16]
    out = struct.pack('>I', 0x80000 + CC_PALS[8] * 32 + 8)
    for i, w in enumerate(src):
        if i < 4: continue
        if w == 0: out += struct.pack('>H', 0); continue
        r, g, b = (w >> 10) & 31, (w >> 5) & 31, w & 31
        L = r * 0.3 + g * 0.59 + b * 0.11
        v = min(31, int(14 + L * 0.75 + 0.5))
        out += struct.pack('>H', (w & 0x8000) | (v << 10) | (v << 5) | v)
    return out
def cube_flash_palettes(tint):
    """tint=True: CUBE COLOR の8色＋白 / False: 元の8色＋白"""
    base = cube_tint_palettes() if tint else cube_orig_palettes()
    return base[:28 * 8] + _white_pal()
def cube_orig_palettes():
    P = _stage9_pal()
    out = bytearray()
    for pl in CC_PALS:
        out += struct.pack('>I', 0x80000 + pl * 32 + 8) + b''.join(struct.pack('>H', P[pl*16+i]) for i in range(4, 16))
    return bytes(out)
ROMAN = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J']   # エリア名(英字)
# エリアの英字を「白抜き」（塗った四角から文字を抜く）で、すき間なしに並べる。
# 文字はメニューの間だけ、メニューで使わない文字の場所（KONAMI ロゴの 0x31〜0x3a）を借りて描き、メニューを出るときに元に戻す
AREA_TILE0 = 0x31
# 色番号（メニューの文字のパレット）: 普段 = 四角 4番(青)／数字 1番(白) パレット4、選択中 = 四角 10番(赤)／数字 1番(白) パレット4、
#   使えない = 四角 10番(青)／数字 15番(使えない英字と同じ色) パレット5
AREA_COLS = [(0x4, 0x1), (0xa, 0x1), (0xa, 0xf)]   # [普段, 選択中, 使えない] の (四角, 数字)
AREA_FONT = {   # 白抜きの数字（四角の中に 5x6 で抜く）
 '1':["..#..",".##..","..#..","..#..","..#..",".###."], '2':[".###.","#...#","...#.","..#..",".#...","#####"],
 '3':["####.","....#",".###.","....#","....#","####."], '4':["...#.","..##.",".#.#.","#..#.","#####","...#."]}
AREA_NUMS = ['1', '2', '3', '4']
def area_tiles():
    out = bytearray()
    for box, dig in AREA_COLS:
        for ch in AREA_NUMS:
            px = [[0]*8 for _ in range(8)]
            for y in range(7):
                for x in range(7): px[y][x] = box
            for y, r in enumerate(AREA_FONT[ch]):
                for x, c in enumerate(r):
                    if c == '#': px[1+y][1+x] = dig
            for y in range(8):
                for x in range(0, 8, 2): out.append((px[y][x] << 4) | px[y][x+1])
    return bytes(out)
GRID_COL = 26
ROMAN_OFS = [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22]   # 1文字ずつ空ける
ATTR_SELGRID = 0x80      # 選択中のマスの色（パレット4: アトラクト後はオレンジ）
ATTR_DIS = 0xa0          # MODE で使われないマスの色（パレット5: 暗い青紫）
NITEM = len(ITEMS)
STG0 = [it[0] for it in ITEMS].index('STAGE   1')   # 面の表の最初の行（12行。#72）
STGEX = [it[0] for it in ITEMS].index('EX STAGE')
CAPI = [it[0] for it in ITEMS].index('FULL POWER CAPSULE')
CUBE0 = [it[0] for it in ITEMS].index('CUBE HEIGHT')   # CUBE HEIGHT/SHIFT/TYPE の最初の項目番号
# 可視領域は タイル列12〜51 / 行2〜29 (320x224)。それに合わせて配置
ROW0, COL_LABEL, COL_VAL, COL_CUR = 4, 14, 35, 12   # 値の列（2026-10-28 に 29→35）
TILE_A = 0x24c000
ATTR_TXT = 0x00          # 属性（パレット番号<<5）。実測で調整
ATTR_SEL = 0x20          # 選択行

def build_data(base):
    """文字列・項目表を base から並べて (bytes, labels) を返す"""
    blob = bytearray(); lab = {}
    def al():
        if len(blob) % 2: blob.append(0)
    def put(name, data):
        al(); lab[name] = base + len(blob); blob.extend(data)
    # 文字列
    for i, it in enumerate(ITEMS):
        put(f'L{i}', it[0].encode() + b'\0')
    for i, it in enumerate(ITEMS):
        if it[5]:
            ptrs = []
            for j, s in enumerate(it[5]):
                put(f'V{i}_{j}', s.encode('latin-1') + b'\0'); ptrs.append(lab[f'V{i}_{j}'])
            al(); lab[f'VT{i}'] = base + len(blob)
            for p in ptrs: blob.extend(struct.pack('>I', p))
    put('ROWMAP', bytes(ROWS))
    put('HELP1', b'UP DOWN SELECT  LEFT RIGHT CHANGE\0')
    put('HELP2', b'PUSH START\0')
    put('DOTPAL', dot_palette())      # #75
    put('DOTCAT', dot_cat())
    put('DOTLV', dot_level())
    put('MODECV', bytes(x for t in MODECV for x in t + (0,)))   # メニューの MODE → (動いているときの MODE, ND_FLAG, その場復活, 0)
    put('PS_T', b'PAUSE\0')
    put('RK_T', b'RANK>\0')
    put('PO_X', b'X>\0')
    put('ND_T', b'TIME\0')   # NO DEATH の残り時間（#36）
    put('ND_M1', b'PUSH START       > FULL POWER\0')   # NO DEATH の最初の START 表示の案内（'>' は ':'）
    put('ND_M2', b'HOLD START 1 SEC > PAUSE MENU\0')
    put('PO_Y', b'Y>\0')
    put('LG_T', b'LAG>\0')
    put('CH_C', b'CUBE>\0')
    put('CH_H', b'H>\0')
    put('CH_S', b'S>\0')
    put('CH_T', b'T>\0')
    put('CH_P', b':\0')          # 0x0a の文字 = 「+」（PlusChr が描き込む）
    put('CH_Q2', b'__\0')        # '_' の位置が「?」
    for i, t in enumerate([b'_', b'A', b'B', b'C', b'D']): put('CH_S%d' % i, t + b'\0')
    al(); lab['CH_STAB'] = base + len(blob)
    for i in range(5): blob.extend(struct.pack('>I', lab['CH_S%d' % i]))
    al(); lab['CS_PTS'] = base + len(blob)
    blob.extend(bytes([0x00, 0x00, 0x10, 0x00]))   # キューブ1個 = 1000点（BCD）
    al(); lab['CCPAL'] = base + len(blob)
    blob.extend(cube_tint_palettes())
    al(); lab['CCORG'] = base + len(blob)
    blob.extend(cube_orig_palettes())
    lab['CCCOL'] = base + len(blob)
    blob.extend(bytes([(p - 16) << 1 for p in CC_PALS]))
    al(); lab['CFTNT'] = base + len(blob); blob.extend(cube_flash_palettes(True))    # #48 CUBE COLOR と CUBE FLASH の両方
    al(); lab['CFORG'] = base + len(blob); blob.extend(cube_flash_palettes(False))   # #48 CUBE FLASH だけ
    al(); lab['LNGFX'] = base + len(blob); blob.extend(line_tiles())
    al(); lab['LNCOL'] = base + len(blob); blob.extend(line_cols())
    al(); lab['LNPAL'] = base + len(blob); blob.extend(line_pal())
    al(); lab['PLUSGFX'] = base + len(blob)
    blob.extend(PLUS_GFX)
    al(); lab['BANGGFX'] = base + len(blob)
    blob.extend(BANG_GFX)
    al(); lab['HBGFX'] = base + len(blob); blob.extend(hb_mark_tile())   # #38 敵・弾の当たりの升目の印（文字 HB_MARK）
    put('PS_C0', b'>CONTINUE\0')
    put('PS_C1', b' CONTINUE\0')
    put('PS_G0', b'>GAME OVER\0')
    put('PS_G1', b' GAME OVER\0')
    put('PS_I0', b'>INVINCIBLE\0')
    put('PS_I1', b' INVINCIBLE\0')
    put('PS_R0', b'>RANK DISP\0')
    put('PS_R1', b' RANK DISP\0')
    put('PS_Q0', b'>CUBE INFO\0')
    put('PS_Q1', b' CUBE INFO\0')
    put('PS_K0', b'>CUBE COLOR\0')
    put('PS_K1', b' CUBE COLOR\0')
    put('PS_S0', b'>STAGE DISP\0')   # #30 周回・面・エリア・スピード（2P のスコアの場所）
    put('PS_S1', b' STAGE DISP\0')
    put('PS_P0', b'>POS DISP\0')
    put('PS_P1', b' POS DISP\0')
    put('PS_U0', b'>CUBE HUNTER\0')
    put('PS_U1', b' CUBE HUNTER\0')
    put('PS_ON', b'ON \0')
    put('PS_CF0', b'>CUBE FLASH\0')   # #48
    put('PS_CF1', b' CUBE FLASH\0')
    put('PS_HB0', b'>HIT DISP\0')   # #38 当たり判定の表示
    put('PS_HB1', b' HIT DISP\0')
    put('PS_CS0', b'>CUBE SE\0')     # #60 キューブが反応する瞬間の音
    put('PS_CS1', b' CUBE SE\0')
    put('PS_TM0', b'>TIME\0')       # #55 NO DEATH の残り時間（読むだけ）
    put('PS_TM1', b' TIME\0')
    # NO DEATH のときだけ出す: 装備（#36 の続き。再開のときにメインがやり直す）と MISS（自分で死ぬ）
    for k, t in [('ES', 'SPEED'), ('EM', 'MISSILE'), ('ED', 'DOUBLE/LASER'), ('EO', 'OPTION'), ('EH', 'SHIELD'), ('X', 'MISS')]:
        put('PS_%s0' % k, b'>' + t.encode() + b'\0'); put('PS_%s1' % k, b' ' + t.encode() + b'\0')
    for i in range(6): put('EN_%d' % i, b'%d     \0' % i)
    put('ED_1', b'DOUBLE\0'); put('ED_2', b'LASER \0'); put('ED_0', b'OFF   \0')
    put('PS_OFF', b'OFF\0')
    # ポーズの項目: 選択中の文字列.l 通常の文字列.l ON/OFF の場所.l(0=なし)
    put('PS_V0', b'>CUBE LINE\0')     # #49 縦と横をまとめた（値は縦の値。横はこれに合わせる）
    put('PS_V1', b' CUBE LINE\0')
    put('PS_H0', b'>CUBE LINE H\0')
    put('PS_H1', b' CUBE LINE H\0')
    put('CF_0', b'OFF   \0'); put('CF_1', b'SHORT \0'); put('CF_2', b'NORMAL\0'); put('CF_3', b'LONG  \0')   # #49 CUBE FLASH
    put('LV_0', b'OFF  \0'); put('LV_1', b'ROUGH\0'); put('LV_2', b'FINE \0'); put('LV_3', b'EDGE \0'); put('LH_2', b'LINE \0')
    al(); lab['LVTAB'] = base + len(blob); blob.extend(struct.pack('>IIIII', 4, lab['LV_0'], lab['LV_1'], lab['LV_2'], lab['LV_3']))
    for i, (t, c) in enumerate(CUBE_SE): put('CS_%d' % i, t.encode() + b'\0')
    al(); lab['CSTAB'] = base + len(blob); blob.extend(struct.pack('>I', len(CUBE_SE) + 1) + struct.pack('>I', lab['CF_0']) + b''.join(struct.pack('>I', lab['CS_%d' % i]) for i in range(len(CUBE_SE))))
    al(); lab['CFTAB'] = base + len(blob); blob.extend(struct.pack('>IIIII', 4, lab['CF_0'], lab['CF_1'], lab['CF_2'], lab['CF_3']))
    al(); lab['LHTAB'] = base + len(blob); blob.extend(struct.pack('>IIIII', 4, lab['LV_0'], lab['LV_1'], lab['LH_2'], lab['LV_3']))
    al(); lab['EQSPD'] = base + len(blob); blob.extend(struct.pack('>I', 6) + b''.join(struct.pack('>I', lab['EN_%d' % i]) for i in range(6)))
    al(); lab['EQOPT'] = base + len(blob); blob.extend(struct.pack('>I', 5) + b''.join(struct.pack('>I', lab['EN_%d' % i]) for i in range(5)))
    al(); lab['EQDL'] = base + len(blob); blob.extend(struct.pack('>IIII', 3, lab['ED_0'], lab['ED_1'], lab['ED_2']))
    al(); lab['PTAB'] = base + len(blob)
    # ポーズの項目 16B: 選択中の文字列.l 通常の文字列.l 値の場所.l(0=なし) 値の表.l(0=ON/OFF, それ以外=[数.l, 文字列.l...])
    for a, b, f, vt in [('PS_C0', 'PS_C1', 0, 0), ('PS_G0', 'PS_G1', 0, 0), ('PS_I0', 'PS_I1', 0x203f20, 0), ('PS_R0', 'PS_R1', 0x203f0e, 0), ('PS_S0', 'PS_S1', 0x2039c4, 0), ('PS_P0', 'PS_P1', 0x203f2b, 0),
                         ('PS_ES0', 'PS_ES1', 0x203e15, 'EQSPD'), ('PS_EM0', 'PS_EM1', 0x203e16, 0), ('PS_ED0', 'PS_ED1', 0x203e17, 'EQDL'),
                         ('PS_EO0', 'PS_EO1', 0x203e18, 'EQOPT'), ('PS_EH0', 'PS_EH1', 0x203e19, 0), ('PS_X0', 'PS_X1', 0, 0), ('PS_Q0', 'PS_Q1', 0x203f0c, 0), ('PS_K0', 'PS_K1', 0x203f34, 0), ('PS_V0', 'PS_V1', 0x203f1c, 'LVTAB'), ('PS_H0', 'PS_H1', 0x203f3b, 'LHTAB'), ('PS_U0', 'PS_U1', 0x203f33, 0),
                         ('PS_HB0', 'PS_HB1', HB_FLAG, 0),
                         ('PS_CF0', 'PS_CF1', CF_FLAG, 'CFTAB'),
                         ('PS_TM0', 'PS_TM1', 0, 0),
                         ('PS_CS0', 'PS_CS1', CS_FLAG, 'CSTAB')]:   # 20 = CUBE SE（#60。キューブラッシュだけ。CUBE FLASH の下）   # 19 = TIME（#55。NO DEATH のときだけ。値は PDraw が $203E10 から作る）   # 18 = CUBE FLASH（#48。キューブラッシュだけ）   # 17 = HIT DISP（#38。いつも出す）
        blob.extend(struct.pack('>IIII', lab[a], lab[b], f, lab[vt] if vt else 0))
    # STAGE DISP のエリア: 面1〜10 × 12。本来のエリア（英字）だけ（❶〜❹ は使わない＝手前の英字のまま。2026-10-28 管理者）
    #   STLAB = 英字（残りは 0）、STPRG = その開始進行度（メニューの表 PROGTBL と同じ値）
    import mod_main
    pt_, _ = mod_main.progress_tables()
    lb, pg = b'', b''
    for i in range(10):
        e = [(ord(l), pt_[i * 12 + j]) for j, l in enumerate(AREA_LABELS[i]) if not l.startswith('#')]
        lb += bytes([c for c, _ in e] + [0] * (12 - len(e)))
        pg += b''.join(struct.pack('>H', v) for _, v in e) + bytes(2 * (12 - len(e)))
    put('STLAB', lb)
    put('STPRG', pg)
    # 項目記述子 12B: labelptr.l type.b min.b max.b mboff.b pad.b strtab.l
    al(); lab['ITM'] = base + len(blob)
    for i, it in enumerate(ITEMS):
        blob.extend(struct.pack('>IBBBBI', lab[f'L{i}'], it[1], it[2], it[3], it[4], lab.get(f'VT{i}', 0)))
    # 既定値表（MB+8からの順序に依存せず、(mboff,既定値)ペア）
    al(); lab['DEF'] = base + len(blob)
    for it in ITEMS:
        if it[1] not in (2, 3): blob.extend(bytes([it[4], it[6]]))
    blob.extend(bytes([0x08, 1, 0x0a, 1]))     # 面1・エリアI
    blob.extend(b'\xff\xff')
    # ローマ数字(エリア)
    for i, r in enumerate(ROMAN): put(f'RM{i}', r.encode() + b'\0')
    for i in range(4): put(f'RW{i+1}', bytes([AREA_TILE0 + i + 0x30, 0, AREA_TILE0 + 4 + i + 0x30, 0, AREA_TILE0 + 8 + i + 0x30, 0]))   # 借りた文字（白抜きの 1〜4）: 普段, 選択中, 使えない
    al(); lab['AREAGFX'] = base + len(blob); blob.extend(area_tiles())
    al(); lab['ROWLAB'] = base + len(blob)                 # 行(面番号1〜13) × 12 の文字列ポインタ
    for labs in AREA_LABELS:
        labs = list(labs) + ['A'] * (12 - len(labs))
        for t in labs:
            blob.extend(struct.pack('>I', lab['RW' + t[1:]] if t.startswith('#') else lab['RM%d' % ROMAN.index(t)]))
    al(); lab['ROMAN'] = base + len(blob)
    for i in range(len(ROMAN)): blob.extend(struct.pack('>I', lab[f'RM{i}']))
    lab['ROMOFS'] = base + len(blob); blob.extend(bytes(ROMAN_OFS))
    return bytes(blob), lab

ENGINE = """
SV2     = $103400
V_CUR   = $103410
V_DIRTY = $103411
V_INIT  = $103412
V_REPC  = $103413
V_PIN   = $103414
V_SIN   = $103415
V_HAVE  = $203ed5          ; 前回値あり（サブの私有RAMは面が始まるときにゲームが消すので、共有RAMの空きに置く）
V_LBUF  = $203ed8          ; 前回値 MB+8..MB+$2f の写し 40バイト → 0x203ed8-0x203eff
V_LBUF2 = $203ec8          ; 前回値 MB+$30..MB+$37 の写し 8バイト → 0x203ec8-0x203ecf
NITEM   = %(nitem)d
TILEA   = $24c000

; ---- PutStr: a0=文字列, d0.w=x, d1.w=y, d2.b=属性 ----
PutStr:
        move.w  d1,d3
        lsl.w   #6,d3
        add.w   d0,d3
        add.w   d3,d3
        lea     TILEA.l,a1
        adda.w  d3,a1
ps_lp:  move.b  (a0)+,d4
        beq.s   ps_end
        cmpi.b  #$20,d4
        bne.s   ps_ok
        move.b  #$40,d4
ps_ok:  subi.b  #$30,d4
        move.b  d4,$4001(a1)
        move.b  d2,1(a1)
        addq.w  #2,a1
        bra.s   ps_lp
ps_end: rts

; ---- PutDec: d5.b=0..99, d0=x,d1=y,d2=属性 ----
PutDec:
        moveq   #0,d6
        move.b  d5,d6
        divu    #10,d6
        move.w  d1,d3
        lsl.w   #6,d3
        add.w   d0,d3
        add.w   d3,d3
        lea     TILEA.l,a1
        adda.w  d3,a1
        move.b  d6,d4
        bne.s   pd_w1
        move.b  #$10,d4
pd_w1:  move.b  d4,$4001(a1)
        move.b  d2,1(a1)
        addq.w  #2,a1
        swap    d6
        move.b  d6,$4001(a1)
        move.b  d2,1(a1)
        rts

; ---- ClearField: x=d0,y=d1,len=d7 (スペース) ----
ClrFld:
        move.w  d1,d3
        lsl.w   #6,d3
        add.w   d0,d3
        add.w   d3,d3
        lea     TILEA.l,a1
        adda.w  d3,a1
cf_lp:  move.b  #$10,$4001(a1)
        move.b  #0,1(a1)
        addq.w  #2,a1
        dbf     d7,cf_lp
        rts

; ---- ClearAll: 3レイヤーのタイルを空に ----
ClrAll:
        lea     $24c000.l,a1
        move.w  #$17ff,d7
ca_lp:  move.b  #$10,$4001(a1)   ; 空白タイル=0x10(ゲーム本体の画面クリアと同じ)
        move.b  #0,1(a1)
        addq.w  #2,a1
        dbf     d7,ca_lp
        rts
"""

ENGINE2 = """
V_I     = $103417
V_Y     = $103418
V_TMP   = $10341a
V_SINP  = $10341c
V_RA    = $10341e          ; この行の文字の色（CUBE の3行はキューブラッシュ以外で暗く）

; ---- 現在行の記述子 a5 を求める ----
CurDesc:
        moveq   #0,d7
        move.b  V_CUR.l,d7
        move.w  d7,d3
        mulu    #12,d3
        lea     ITM.l,a5
        adda.l  d3,a5
        rts

; ---- 全行描画 ----
DrawAll:
        clr.b   V_I.l
da_row:
        moveq   #0,d7
        move.b  V_I.l,d7
        move.w  d7,d3
        mulu    #12,d3
        lea     ITM.l,a5
        adda.l  d3,a5
        move.b  #%(attr)d,V_RA.l
        jsr     CubeSkip.l
        beq.s   da_ra
NOINV_DRAW
        move.b  #ATTRDIS,V_RA.l
da_ra:  lea     ROWMAP.l,a1
        moveq   #0,d1
        move.b  0(a1,d7.w),d1
        move.w  d1,V_Y.l
        lea     V_TMP.l,a0
        move.b  #$20,(a0)
        clr.b   1(a0)
        cmp.b   V_CUR.l,d7
        bne.s   da_nc
        move.b  #$3e,(a0)
da_nc:  move.w  #%(colcur)d,d0
        move.b  #%(attr)d,d2
        jsr     PutStr.l
        movea.l (a5),a0
        move.w  #%(collab)d,d0
        move.w  V_Y.l,d1
        move.b  V_RA.l,d2
        jsr     PutStr.l
        cmpi.b  #2,4(a5)
        beq.w   da_next
        cmpi.b  #3,4(a5)
        bne.s   da_val
        jsr     DrawGrid.l
        bra.w   da_next
da_val: jsr     ValCol.l
        move.w  V_Y.l,d1
        moveq   #15,d7          ; 16桁（RESPAWN NO DEATH が16文字。#58 で13桁にしていた）
        jsr     ClrFld.l
        moveq   #0,d0
        move.b  7(a5),d0
        lea     $203f00.l,a0
        move.b  0(a0,d0.w),d5
        cmpi.b  #1,4(a5)
        beq.s   da_str
        jsr     ValCol.l
        cmpi.b  #10,d5          ; 1桁の数は左にそろえる（2桁目の空白を1つ左に）
        bcc.s   da_d2
        subq.w  #1,d0
da_d2:  move.w  V_Y.l,d1
        move.b  V_RA.l,d2
        jsr     PutDec.l
        bra.w   da_next
da_str: moveq   #0,d0
        move.b  d5,d0
        lsl.w   #2,d0
        movea.l 8(a5),a2
        movea.l 0(a2,d0.w),a0
        jsr     ValCol.l
        move.w  V_Y.l,d1
        move.b  V_RA.l,d2
        jsr     PutStr.l
da_next:
        addq.b  #1,V_I.l
        cmpi.b  #NITEM,V_I.l
        bcs.w   da_row
        rts

; ---- 値の桁: 上の3行（INVINCIBLE・MODE・LOOP）は面の表の A の桁、キューブの3行は B の桁（#75。RANDOM の R を EX STAGE の B に合わせる）、ほかは COL_VAL ----
ValCol:
        move.w  #%(colval)d,d0
        cmpi.b  #3,V_I.l
        bcc.s   vc_c
        move.w  #GRIDCOL,d0
vc_r:   rts
vc_c:   cmpi.b  #CUBE0,V_I.l
        bcs.s   vc_r
        cmpi.b  #CUBE0+2,V_I.l
        bhi.s   vc_r
        move.w  #GRIDCOL+2,d0
        rts

; ---- CUBE HEIGHT/SHIFT/TYPE の行（d7=項目番号）をキューブラッシュ以外で飛ばす: ne=飛ばす（d3 を使う）----
; メニュー表示時なので $203f0b は未変換（1=NO DEATH 2=CUBE RUSH 3=CUBE NO DEATH）。CUBE NO DEATH は NO DEATH と CUBE RUSH の両方の性質を持つ
CubeSkip:
        moveq   #0,d3
        tst.b   d7              ; INVINCIBLE の行: NO DEATH の3つ（MODE 1・3・5）では選べない（いつも無敵）
        bne.s   ck_c
NOINV_SKIP
        move.b  $203f0b.l,d0
        cmpi.b  #6,d0
        bcc.s   ck_x
        btst    #0,d0
        beq.s   ck_x
ck_sk:  moveq   #1,d3
        bra.s   ck_x
ck_c:
        move.b  $203f0b.l,d0    ; MODE
        cmpi.b  #4,d0           ; CUBE RUSH(4) または CUBE NO DEATH(5): キューブの3行は選べる。面の表（9面に決まる）と
        beq.s   ck_cr           ;   FULL POWER CAPSULE（ゲージは SPEED UP に固定）は意味がないので飛ばす（#72）
        cmpi.b  #5,d0
        beq.s   ck_cr
        cmpi.b  #6,d0           ; BOSS RUSH（BOSSRUSH=1）: EX STAGE の行は使えない（#72）
        bne.s   ck_cb
        cmpi.b  #STGEX,d7
        beq.s   ck_sk
ck_cb:  cmpi.b  #CUBE0,d7
        bcs.s   ck_x
        cmpi.b  #CUBE0+2,d7
        bhi.s   ck_x
        moveq   #1,d3
ck_x:   tst.b   d3
        rts
ck_cr:  cmpi.b  #CAPI,d7
        beq.s   ck_s2
        cmpi.b  #STG0,d7
        bcs.s   ck_x
        cmpi.b  #STG0+11,d7
        bhi.s   ck_x
ck_s2:  moveq   #1,d3
        bra.s   ck_x

; ---- 値変更 d6=+1/-1 ----
ChangeVal:
        jsr     CurDesc.l
        cmpi.b  #2,4(a5)
        beq.s   cv_ret
        cmpi.b  #3,4(a5)
        beq.w   cv_grid
        moveq   #0,d0
        move.b  7(a5),d0
        lea     $203f00.l,a0
        move.b  0(a0,d0.w),d1
        add.b   d6,d1
        cmp.b   5(a5),d1
        bge.s   cv_hi
        move.b  6(a5),d1
        bra.s   cv_st
cv_hi:  cmp.b   6(a5),d1
        ble.s   cv_st
        move.b  5(a5),d1
cv_st:  move.b  d1,0(a0,d0.w)
cv_ret: rts
; 面/エリアの表: 別の面の行で左右 → その面のエリアIを選ぶ。同じ面なら左右でエリアを移動(端で一周)
cv_grid:
        move.b  5(a5),d0
        cmp.b   $203f08.l,d0
        beq.s   cg_same
        move.b  d0,$203f08.l
        move.b  #1,$203f0a.l
        rts
cg_same:
        move.b  $203f0a.l,d1
        add.b   d6,d1
        bne.s   cg_1
        move.b  6(a5),d1
cg_1:   cmp.b   6(a5),d1
        bls.s   cg_2
        moveq   #1,d1
cg_2:   move.b  d1,$203f0a.l
        rts

; ---- 面/エリアの表の1行を描く (a5=記述子, V_Y=行) ----
DrawGrid:
        move.w  #GRIDCOL,d0
        move.w  V_Y.l,d1
        moveq   #22,d7
        jsr     ClrFld.l
        moveq   #1,d6
dg_lp:  cmp.b   6(a5),d6
        bhi.w   dg_r
; MODE によって使われないマスは暗い色(ATTRDIS):
;   CUBE RUSH / CUBE NO DEATH = 全部 / BOSS RUSH = EX STAGE の行全部と、面1〜10の行の B 以降(BOSS RUSH の行はそのまま)
        move.b  5(a5),d0        ; この行の面番号(1〜10, 11=EX, 13=BOSS RUSH)
        move.b  $203f0a.l,d4    ; 選択中のエリア
        move.b  $203f0b.l,d5    ; MODE（メニューの番号: 4=CUBE RUSH 5=CUBE NO DEATH 6=BOSS RUSH。MODE_NAMES）
        cmpi.b  #4,d5
        beq.s   dg_dis
        cmpi.b  #5,d5           ; CUBE NO DEATH も CUBE RUSH と同じ扱い
        beq.s   dg_dis
        cmpi.b  #6,d5           ; BOSS RUSH（BOSSRUSH=1）
        bne.s   dg_en
        cmpi.b  #11,d0
        beq.s   dg_dis
        cmpi.b  #10,d0
        bhi.s   dg_en
        moveq   #1,d4           ; ボスラッシュでは面1〜10の開始は常に A
        cmpi.b  #1,d6
        bne.s   dg_dis
dg_en:  moveq   #%(attr)d,d2
        cmp.b   $203f08.l,d0
        bne.s   dg_n
        cmp.b   d4,d6
        bne.s   dg_n
        move.b  #ATTRSELGRID,d2
        bra.s   dg_n
dg_dis: move.b  #ATTRDIS,d2
dg_n:   moveq   #0,d3
        move.b  d6,d3
        subq.w  #1,d3
        lea     ROMOFS.l,a0
        moveq   #0,d0
        move.b  0(a0,d3.w),d0
        addi.w  #GRIDCOL,d0
        lsl.w   #2,d3
        moveq   #0,d7           ; この行（面番号 1〜13）の表示: ROWLAB[(面-1)*12 + 列]
        move.b  5(a5),d7
        subq.w  #1,d7
        mulu    #48,d7
        add.w   d7,d3
        lea     ROWLAB.l,a0
        movea.l 0(a0,d3.w),a0
        cmpi.b  #$61,(a0)       ; 白抜きの数字: 普段・選択中=パレット4（選択中は選択中用の文字）/ 使えない=パレット5 で使えない用の文字
        bcs.s   dg_p
        cmpi.b  #ATTRDIS,d2
        bne.s   dg_q1
        addq.l  #4,a0
        bra.s   dg_p
dg_q1:  cmpi.b  #ATTRSELGRID,d2
        bne.s   dg_q2
        addq.l  #2,a0
dg_q2:  move.b  #$80,d2
dg_p:
        move.w  V_Y.l,d1
        movem.l d6/a5,-(a7)
        jsr     PutStr.l
        movem.l (a7)+,d6/a5
        addq.b  #1,d6
        bra.w   dg_lp
dg_r:   rts

; ---- メニュー初期化 ----
MenuInit:
        clr.b   $203ed4.l       ; キューブの色のパレットを写さない（バッファはメニューの借りた文字の控えと重なる）
        clr.b   V_CCS.l         ; 次に使うときはバッファを書き直す
        cmpi.b  #2,MBS_REQ.l
        bne.s   mi_def
        tst.b   V_HAVE.l
        beq.s   mi_def
        lea     V_LBUF.l,a0
        lea     $203f08.l,a1
        moveq   #$27,d7
mi_cp:  move.b  (a0)+,(a1)+
        dbf     d7,mi_cp
        lea     V_LBUF2.l,a0
        moveq   #7,d7
mi_cp2: move.b  (a0)+,(a1)+
        dbf     d7,mi_cp2
        bra.s   mi_scr
mi_def: lea     DEF.l,a0
        lea     $203f00.l,a1
mi_dl:  moveq   #0,d0
        move.b  (a0)+,d0
        cmpi.b  #$ff,d0
        beq.s   mi_scr
        move.b  (a0)+,0(a1,d0.w)
        bra.s   mi_dl
mi_scr: lea     $280620.l,a0     ; 白抜きの A〜J: 借りる文字を共有RAMの空き(0x203cb0〜)に控えてから描く
        lea     $203cb0.l,a1
        lea     AREAGFX.l,a2
        move.w  #255,d0
mi_ag:  move.b  (a0),(a1)+
        move.b  (a2)+,(a0)+
        dbf     d0,mi_ag
        lea     $103600.l,a1        ; 残り4文字分はポーズ窓の退避場所に（メニュー中は使わない）
        moveq   #127,d0
mi_ah:  move.b  (a0),(a1)+
        move.b  (a2)+,(a0)+
        dbf     d0,mi_ah
        clr.b   $203f0e.l       ; RANK DISP・CUBE INFO はポーズで切り替える（始めは OFF）
        clr.b   $203f2b.l       ; POS DISP
        clr.b   HB_FLAG.l       ; HIT DISP（#38）
        clr.b   V_SIF.l         ; STAGE DISP（#30）
        clr.b   $203f1c.l       ; CUBE LINE V
        clr.b   $203f3b.l       ; CUBE LINE H
        clr.b   $203f0c.l
        clr.b   $203f34.l       ; CUBE COLOR
        clr.b   $203e2a.l       ; CUBE FLASH（#48・#57・#73）
        clr.b   $203e23.l       ; CUBE SE（#60）
        clr.b   $203f33.l       ; CUBE HUNTER（始めは OFF = 出さない）
        jsr     ClrAll.l
        jsr     MbgInit.l
NOINV_CUR
        move.b  MBS_P1.l,V_PIN.l
        move.b  MBS_SYS.l,V_SIN.l
        move.b  #1,V_DIRTY.l
        clr.b   V_REPC.l
        rts

; ---- メニュー 1フレーム ----
; ---- キューブラッシュ中の表示: 右上 行3 に「H nn S x T nn」（実際に出ている並び）----
; メインが1個目の瞬間のカウンタを $203e3a に置く。それを H/S/T に割り出す（$203e3c = 割り出し済みの値）
CubeHud:
        cmpi.b  #2,$203f0b.l    ; MODE = CUBE RUSH のときだけ
        bne.w   ch_rts
        move.w  $203e3a.l,d0
        cmp.w   $203e3c.l,d0
        beq.w   ch_draw
        move.w  d0,$203e3c.l
        cmpi.w  #$ffff,d0
        beq.w   ch_draw
        move.b  d0,d1           ; H = 高さの番号 (下位 xor 上位 の bit2-5)
        move.w  d0,d2
        lsr.w   #8,d2
        eor.b   d2,d1
        andi.w  #$3c,d1
        lsr.w   #2,d1
        move.b  d1,$203e3e.l
        move.w  d0,d2           ; S = bit2-3
        lsr.w   #2,d2
        andi.w  #3,d2
        move.b  d2,$203e3f.l
        lsl.w   #2,d1
        add.w   d2,d1
        mulu    #90,d1          ; (h*4+s)*45 語
        lea     CUBETBL.l,a2
        adda.l  d1,a2
        moveq   #0,d4           ; t
ch_t:   move.w  (a2)+,d5        ; 候補の c0
        lea     CUBEDLT.l,a3
        moveq   #98,d6
ch_k:   move.w  (a3)+,d7
        move.w  d5,d1
        add.w   d7,d1
        move.w  d1,d2
        lsr.w   #8,d2
        eor.b   d2,d1
        add.w   d0,d7
        move.w  d7,d2
        lsr.w   #8,d2
        eor.b   d2,d7
        eor.b   d7,d1
        andi.b  #$3c,d1
        bne.s   ch_nx
        dbf     d6,ch_k
        move.b  d4,$203e35.l    ; 一致した
        bra.s   ch_draw
ch_nx:  addq.w  #1,d4
        cmpi.w  #45,d4
        bcs.s   ch_t
        move.b  #$ff,$203e35.l  ; 見つからない（処理落ち等）
ch_draw:
        jsr     LagChk.l
        tst.b   $203ed1.l       ; CUBE INFO が有効なときだけ描く
        beq.w   ch_rts
        move.w  FRAMECNT.l,d0   ; 描くのは4フレームに1回（毎フレームだとサブの処理が遅れ、くっついたキューブの描き込みが化ける）
        andi.w  #3,d0
        bne.w   ch_rts
        jsr     PlusChr.l
        move.w  #26,d0          ; 最上段 col 26〜50 を消す（HI・2P の跡も）
        move.w  #HROW,d1
        moveq   #24,d7
        jsr     ClrFld.l
        ; CUBE:nn（今何個目。1個目が出る前は 00）
        lea     CH_C.l,a0
        move.w  #30,d0
        bsr.w   HLab
        moveq   #0,d5
        cmpi.w  #$ffff,$203e3c.l
        beq.s   ch_c0
        move.w  $203e36.l,d5
ch_c0:  move.w  #35,d0
        moveq   #2,d6
        bsr.w   HNum
        lea     CH_H.l,a0
        move.w  #38,d0
        bsr.w   HLab
        lea     CH_S.l,a0
        move.w  #43,d0
        bsr.w   HLab
        lea     CH_T.l,a0
        move.w  #47,d0
        bsr.w   HLab
        cmpi.w  #$ffff,$203e3c.l
        bne.s   ch_d1
        ; まだ1個目が出ていない: メニューの設定（0 = RANDOM → ?）
        move.b  $203f35.l,d5
        move.b  $203f36.l,d3
        move.b  $203f37.l,d4
        bra.s   ch_d2
ch_d1:  move.b  $203e3e.l,d5
        addq.b  #1,d5
        move.b  $203e3f.l,d3
        addq.b  #1,d3
        move.b  $203e35.l,d4
        addq.b  #1,d4
        cmpi.b  #46,d4          ; 見つからない($ff+1=0)
        bcs.s   ch_d2
        moveq   #0,d4
ch_d2:  movem.l d3-d4,-(a7)
        andi.w  #$ff,d5
        move.w  #40,d0
        moveq   #2,d6
        bsr.w   HNumR           ; H:nn / H:??
        movem.l (a7)+,d3-d4
        move.l  d4,-(a7)
        moveq   #0,d0
        move.b  d3,d0
        lsl.w   #2,d0
        lea     CH_STAB.l,a0
        movea.l 0(a0,d0.w),a0
        move.w  #45,d0
        move.w  #HROW,d1
        moveq   #0,d2
        jsr     PutStr.l        ; S の値
        move.l  (a7)+,d5
        andi.w  #$ff,d5
        move.w  #49,d0
        moveq   #2,d6
        bsr.w   HNumR           ; T:nn / T:??
        bra.w   ch_rts
; 見出し（暗め: パレット6）: a0=文字列 d0=桁
HLab:   move.w  #HROW,d1
        move.b  #ATTRLAB,d2
        jmp     PutStr.l
; 数字（明るめ）: d5=値 d6=桁数 d0=桁。0 なら「?」（HNumR）
HNumR:  tst.w   d5
        bne.s   HNum
        lea     CH_Q2.l,a0
        move.w  #HROW,d1
        moveq   #0,d2
        jmp     PutStr.l
HNum:   move.w  #HROW,d1
        moveq   #0,d2
; ゼロ付きの数字: d5.w=値 d6=桁数 d0,d1,d2
PutZ:   lea     V_TMP.l,a0
        adda.w  d6,a0
        clr.b   (a0)
        andi.l  #$ffff,d5
pz_l:   divu    #10,d5
        swap    d5
        addi.b  #$30,d5
        move.b  d5,-(a0)
        clr.w   d5
        swap    d5
        subq.w  #1,d6
        bne.s   pz_l
        jmp     PutStr.l
; 「+」の字を空き文字(0x0a)に入れる（ゲームの文字には + がない。0x0a は画面で使われていない空白の文字）
PlusChr:
        lea     PLUSGFX.l,a0
        lea     $280140.l,a1
        moveq   #31,d0
pc_c:   move.b  (a0)+,(a1)+
        dbf     d0,pc_c
        rts
ch_rts: rts

; ---- 処理落ちのずれ: 出現のたびに「その瞬間のカウンタ」と「1個目のカウンタ＋決まった間隔」を比べる。
;      最初にずれたキューブの番号を V_LAG に残し、"LAG nn" を H の左に表示する
HROW    = 2                ; キューブの表示の段（最上段）
ATTRLAB = $c0              ; 見出しの色: パレット6（メインがプレイ中に暗めの灰色を入れる。ゲームでは未使用）
V_LAGI  = $1036e0          ; 最後に調べた出現番号
V_LAG   = $1036e2          ; 最初にずれたキューブの番号 (0 = ずれなし)
V_LAGF  = $1036e4          ; ずれの累計（フレーム）
V_SHL   = $1036e6
V_RKL   = $1036e8          ; RANK の表示を出しているか（OFF にしたら消す）          ; メニューのシールド色の見本: 最後に入れた色
LagChk:
        cmpi.w  #$ffff,$203e3c.l
        bne.s   lc_go
        clr.w   V_LAGI.l        ; まだ1個目が出ていない（やり直し含む）: リセット
        clr.b   V_LAG.l
        clr.w   V_LAGF.l
        bra.w   lc_draw
lc_go:  move.w  $203e36.l,d0    ; 何個目
        cmp.w   V_LAGI.l,d0
        beq.w   lc_draw
        move.w  d0,V_LAGI.l
        cmpi.w  #1,d0
        bne.s   lc_n1
        clr.b   V_LAG.l         ; 1個目 = 新しいラッシュ
        clr.w   V_LAGF.l
lc_n1:  subq.w  #1,d0
        cmpi.w  #99,d0
        bcc.w   lc_draw
        add.w   d0,d0
        lea     CUBEDLT.l,a0
        move.w  0(a0,d0.w),d1
        add.w   $203e3a.l,d1    ; d1 = 計算どおりならこの瞬間のカウンタ
        move.w  $203e38.l,d2    ; d2 = 実際のカウンタ
        move.w  d2,d3
        sub.w   d1,d3
        move.w  d3,V_LAGF.l     ; ずれの累計（フレーム）
        tst.b   V_LAG.l
        bne.s   lc_draw
        move.w  d1,d3           ; 高さの番号（下位 xor 上位 の bit2-5）が変わったときだけ「並びが変わった」
        move.w  d1,d4
        lsr.w   #8,d4
        eor.b   d4,d3
        andi.b  #$3c,d3
        move.w  d2,d4
        move.w  d2,d5
        lsr.w   #8,d5
        eor.b   d5,d4
        andi.b  #$3c,d4
        cmp.b   d3,d4
        beq.s   lc_draw
        lsr.w   #1,d0
        addq.w  #1,d0
        move.b  d0,V_LAG.l
lc_draw:
        tst.b   $203ed1.l
        beq.w   lc_r
        move.w  #31,d0          ; 2段目 col 31〜41: 「LAG:12+0005」
        move.w  #3,d1
        moveq   #10,d7
        jsr     ClrFld.l
        moveq   #0,d5
        move.b  V_LAG.l,d5
        beq.w   lc_r
        move.w  #35,d0
        move.w  #3,d1
        moveq   #0,d2
        moveq   #2,d6
        jsr     PutZ.l
        move.w  V_LAGF.l,d5
        cmpi.w  #9999,d5
        bls.s   lc_f
        move.w  #9999,d5
lc_f:   move.w  #38,d0
        move.w  #3,d1
        moveq   #0,d2
        moveq   #4,d6
        jsr     PutZ.l
        lea     LG_T.l,a0
        move.w  #31,d0
        move.w  #3,d1
        move.b  #ATTRLAB,d2
        jsr     PutStr.l
        lea     CH_P.l,a0
        move.w  #37,d0
        move.w  #3,d1
        move.b  #ATTRLAB,d2
        jmp     PutStr.l
lc_r:   rts

; ---- メニューの背景（スプライトと色）: スプライト表をそのまま書き、暗くした色を共有RAMに置いてメインに写してもらう ----
; スプライト表の書き込み: ゲームのスプライト処理の 0x877c（使っていない枠を消す bsr $8850 と move.b #0,$203936）を置き換え。
; メニュー表示中だけ、消す代わりに背景のスプライト表を丸ごと書く
SprHook:
        tst.b   MBS_REQ.l
        beq.s   sh_n
        tst.b   MBS_DONE.l
        bne.s   sh_n
        moveq   #0,d0               ; シールド色の見本: 選んだ色が変わったら色3(0x131-0x136,0x13e)を入れ替える
        move.b  $203f16.l,d0
        cmp.b   V_SHL.l,d0
        beq.s   sh_sp
        move.b  d0,V_SHL.l
        subq.b  #1,d0
        cmpi.b  #9,d0
        bls.s   sh_c1
        moveq   #0,d0
sh_c1:  mulu    #14,d0
        lea     SHCOL.l,a0
        adda.w  d0,a0
        lea     $202062.l,a1
        moveq   #5,d0
sh_c2:  move.w  (a0)+,(a1)+
        dbf     d0,sh_c2
        move.w  (a0),$20207c.l
        move.b  #1,$203e34.l
sh_sp:  lea     MBGSPR.l,a0
        lea     $2c0801.l,a1
        move.w  #1023,d0
mb_sp:  move.b  (a0)+,(a1)
        addq.l  #2,a1
        dbf     d0,mb_sp
        bra.s   sh_x
sh_n:   jsr     $8850.l
sh_x:   move.b  #0,$203936.l
        rts
MbgInit:
        move.w  #$ffff,$203e3a.l  ; キューブの表示: まだ1個目が出ていない
        move.w  #$ffff,$203e3c.l
        lea     MBGPAL.l,a0
        lea     $202000.l,a1
        move.w  #255,d0
mb_pl:  move.w  (a0)+,(a1)+
        dbf     d0,mb_pl
        lea     DOTPAL.l,a0     ; #75 キューブの並びの見本の色（文字の面のパレット3。メインの PalCopy が $102200 から写す）
        lea     $202200.l,a1
        moveq   #15,d0
mb_dp:  move.w  (a0)+,(a1)+
        dbf     d0,mb_dp
        move.b  #1,$203e34.l
        move.b  #$ff,V_SHL.l
        clr.b   V_DOTV.l
        rts

MenuFrame:
        lea     BANGGFX.l,a0    ; 「!」の字を空き文字(0x5c)に入れる（CAPSULE の値用。ゲームの文字には ! がない）
        lea     $280b80.l,a1
        moveq   #31,d0
mf_bg:  move.b  (a0)+,(a1)+
        dbf     d0,mf_bg
        tst.b   V_INIT.l
        bne.w   mf_run
        jsr     MenuInit.l
        move.b  #1,V_INIT.l
mf_run:
        move.w  #42,d0          ; PUSH START: 右上の一番上（行2・桁42〜51）で点滅（約0.5秒ごと。2026-10-31 管理者）
        move.w  #2,d1
        btst    #5,$203951.l    ; FRAMECNT の下位
        beq.s   mf_pc
        lea     HELP2.l,a0
        move.b  #%(attr)d,d2
        jsr     PutStr.l
        bra.s   mf_pd
mf_pc:  moveq   #9,d7
        jsr     ClrFld.l
mf_pd:  move.b  MBS_P1.l,d0
        move.b  V_PIN.l,d1
        move.b  d0,V_PIN.l
        move.b  d1,d2
        not.b   d2
        and.b   d0,d2             ; 新規押下
        ; 押しっぱなしの連射（方向キー）
        move.b  d0,d3
        andi.b  #$0f,d3
        beq.w   mf_norep
        cmp.b   d1,d0
        bne.w   mf_norep
        addq.b  #1,V_REPC.l
        cmpi.b  #18,V_REPC.l
        bcs.w   mf_dorep
        move.b  #14,V_REPC.l
        or.b    d3,d2
        bra.w   mf_dorep
mf_norep:
        tst.b   d3
        bne.w   mf_dorep
        clr.b   V_REPC.l
mf_dorep:
        move.b  MBS_SYS.l,d4
        move.b  V_SIN.l,d5
        move.b  d4,V_SIN.l
        not.b   d5
        and.b   d4,d5             ; SYSTEM新規押下
        btst    #2,d2
        beq.w   mf_nu
        move.b  V_CUR.l,d7
mf_u0:  tst.b   d7
        bne.s   mf_u1
        move.b  #NITEM,d7
mf_u1:  subq.b  #1,d7
        jsr     CubeSkip.l
        bne.s   mf_u0
        move.b  d7,V_CUR.l
        move.b  #1,V_DIRTY.l
mf_nu:  btst    #3,d2
        beq.w   mf_nd
        move.b  V_CUR.l,d7
mf_d0:  addq.b  #1,d7
        cmpi.b  #NITEM,d7
        bcs.s   mf_d1
        moveq   #0,d7
mf_d1:  jsr     CubeSkip.l
        bne.s   mf_d0
        move.b  d7,V_CUR.l
        move.b  #1,V_DIRTY.l
mf_nd:  btst    #0,d2
        beq.w   mf_nl
        movem.l d2/d4-d5,-(a7)
        moveq   #-1,d6
        jsr     ChangeVal.l
        movem.l (a7)+,d2/d4-d5
        move.b  #1,V_DIRTY.l
mf_nl:  btst    #1,d2
        beq.w   mf_nr
        movem.l d2/d4-d5,-(a7)
        moveq   #1,d6
        jsr     ChangeVal.l
        movem.l (a7)+,d2/d4-d5
        move.b  #1,V_DIRTY.l
mf_nr:  ; 決定: SYSTEMスタート or (B1 かつ START行)
        move.b  d5,d3
        andi.b  #$18,d3
        bne.w   mf_go
        btst    #4,d2
        beq.w   mf_nb1
        jsr     CurDesc.l
        cmpi.b  #2,4(a5)
        bne.w   mf_nb1
        bra.w   mf_go
mf_nb1: tst.b   V_DIRTY.l
        beq.w   mf_ret
        clr.b   V_DIRTY.l
        jsr     DrawAll.l
mf_ret: jmp     DotPanel.l      ; #75 キューブの並びの見本（DrawAll の後で毎フレーム置き直す）
mf_go:  lea     $203f08.l,a0     ; 前回値として控える（モードで面・エリアを書き換える前に）
        lea     V_LBUF.l,a1
        moveq   #$27,d7
mf_sv:  move.b  (a0)+,(a1)+
        dbf     d7,mf_sv
        lea     V_LBUF2.l,a1
        moveq   #7,d7
mf_sv2: move.b  (a0)+,(a1)+
        dbf     d7,mf_sv2
; ---- MODE の変換（2026-10-31）: メニューの番号 → 動いているときの MODE・ND_FLAG・その場復活の印（MB+$3E。#35）----
        moveq   #0,d0
        move.b  $203f0b.l,d0
        lsl.w   #2,d0
        lea     MODECV.l,a0
        adda.w  d0,a0
        move.b  (a0)+,$203f0b.l  ; 0=普通 1=NO DEATH 2=キューブラッシュ 4=ボスラッシュ
        move.b  (a0)+,$203e1a.l  ; ND_FLAG（NO DEATH の3つ）
        move.b  (a0),$203f3e.l   ; その場復活（RESPAWN・RESPAWN NO DEATH）。サブの RspSub が見る
        cmpi.b  #2,$203f0b.l     ; CUBE HEIGHT/SHIFT/TYPE はキューブラッシュだけ（ほかは RANDOM = 純正のまま。控えた値はそのまま）
        beq.s   mf_cr
        clr.b   $203f35.l
        clr.w   $203f36.l
mf_cr:
NOINV_GO
        tst.b   $203e1a.l        ; ND_FLAG が立っていれば いつも無敵（控えた INVINCIBLE はそのまま）
        beq.s   mf_ndz
        move.b  #1,$203f20.l
mf_ndz:
        cmpi.b  #4,$203f0b.l     ; ボスラッシュ(BOSSRUSH=1。番号を 3→4 に変更): 面1〜10は常にエリアA、EX STAGE は使えないので面1
        bne.s   mf_gb
        cmpi.b  #11,$203f08.l
        bne.s   mf_gb1
        move.b  #1,$203f08.l
mf_gb1: cmpi.b  #10,$203f08.l
        bhi.s   mf_gb
        move.b  #1,$203f0a.l
mf_gb:  cmpi.b  #2,$203f0b.l     ; キューブラッシュ = 9面 エリア2(独自開始点)
        bne.w   mf_g1
        move.b  #9,$203f08.l
        move.b  #2,$203f0a.l
mf_g1:  move.w  #$2001,$203f1e.l    ; 隠し面(STAGE 11/12): 戻り先 = 10面のラスボス手前(X=0x200000)
        cmpi.b  #13,$203f08.l       ; 10面ボスラッシュの行(13)も表から
        beq.s   mf_g0
        cmpi.b  #10,$203f08.l
        bhi.w   mf_g2
mf_g0:
        moveq   #0,d0               ; 開始進行度 = PROGTBL[(面-1)*8 + (エリア-1)] → MB+$1e
        move.b  $203f08.l,d0
        subq.w  #1,d0
        mulu    #12,d0
        moveq   #0,d1
        move.b  $203f0a.l,d1
        subq.w  #1,d1
        add.w   d1,d0
        add.w   d0,d0
        lea     PROGTBL.l,a0
        move.w  0(a0,d0.w),$203f1e.l
mf_g2:  cmpi.b  #13,$203f08.l       ; 保存後に 10面ボスラッシュ(13) → 面10 として渡す
        bne.s   mf_g3
        move.b  #10,$203f08.l
mf_g3:  cmpi.b  #11,$203f08.l       ; EX STAGE の B → サラマンダ隠し面(12)
        bne.s   mf_g4
        cmpi.b  #2,$203f0a.l
        bne.s   mf_g4
        move.b  #12,$203f08.l
mf_g4:  clr.w   $203f3c.l       ; 開始時のゲージ（MB+$3c: 0=純正どおり 1=SPEED UP）・開始時のスピード（MB+$3d: いつも 0。メニューの SPEED は装備コマンドだけ・2026-10-28 管理者決定）
mf_sp:  cmpi.w  #$0101,$203f08.l   ; 1周目の1面 A（進み具合 0）だけ純正どおり。それ以外はゲージを SPEED UP に（保険あり・#5）
        bne.s   mf_gs
        tst.w   $203f1e.l
        beq.s   mf_gz
mf_gs:  move.b  #1,$203f3c.l
mf_gz:  move.b  #1,V_HAVE.l
        lea     $280620.l,a0     ; 借りた文字を元に戻す
        lea     $203cb0.l,a1
        move.w  #255,d0
mf_ag:  move.b  (a1)+,(a0)+
        dbf     d0,mf_ag
        lea     $103600.l,a1
        moveq   #127,d0
mf_ah:  move.b  (a1)+,(a0)+
        dbf     d0,mf_ah
; ---- NO DEATH の時間・キューブラッシュの残機ボーナス（#40）: DSW1 bit7（負論理。1=OFF＝10分・+5 / 0=ON＝5分・+2）。
;      以前はメインの ApplyStart で決めていた（メインの空きを作るためサブに移した #70）。DSW1 はメインが毎フレーム $103814 に写す
        moveq   #5,d1
        move.l  #36000,d0
        btst    #7,$203814.l
        bne.s   mf_dt
        moveq   #2,d1
        move.l  #18000,d0
mf_dt:  move.l  d0,$203e10.l     ; ND_LEFT
        move.l  d0,$203e1c.l     ; ND_TIME（CmdCnt の延長で使う）
        move.b  d1,$203e20.l     ; ND_BONUS（メインの ApplyStart の sk_set で使う）
        move.w  #$ff00,$203f38.l ; 以下、以前はメインの ApplyStart で書いていた（メインの空きを作るためサブに移した #70・#63）
        clr.b   $203f21.l        ; START 押下時間
        move.b  #1,$203f22.l     ; 装備コマンドの残り回数: 通常1回 / キューブ・ボスラッシュは無制限($ff)
        tst.b   $203f0b.l        ; MODE（CUBE NO DEATH は上で 2 にしてある）
        beq.s   mf_c1
        st      $203f22.l
mf_c1:
        jsr     DotOff.l        ; #75 見本を消してから抜ける（借りた字はゲームが上書きする）
        move.b  #1,MBS_DONE.l
        rts
mf_cancel:
        jsr     DotOff.l
        move.b  #2,MBS_DONE.l
        rts

; ---- #75 キューブの並びの見本（点） ----
; キューブの3行（CUBE HEIGHT/SHIFT/TYPE）にカーソルがある間だけ、桁36〜51・段17〜24（16×8字）に借りた字 0xC00〜0xC7F を並べる。
; H・S・T が変わったときだけ字の絵を描き直す（DotPix）。字の並べ直しは毎フレーム（DrawAll の値の消去が桁43まで届くので）。
; 字の番号 0xC00+n → 属性 $78（パレット3・番号の上位 $C）、番号の下位 = n
V_DOTK  = $1036c0               ; 描いてある H・S・T（.l の下位3バイト）
V_DOTV  = $1036c4               ; 出しているか
DOTBASE = $298000               ; 字 0xC00 の絵（サブの $280000 + 0xC00*32）
DOTCELL2 = 2248                 ; 左上の升目（段17・桁36）の文字の面の中の位置×2 = (17*64+36)*2
DotPanel:
        move.b  V_CUR.l,d0
        cmpi.b  #CUBE0,d0
        bcs.s   DotOff
        cmpi.b  #CUBE0+2,d0
        bhi.s   DotOff
        move.l  $203f34.l,d1    ; $203f35〜37 = H・S・T
        andi.l  #$ffffff,d1
        tst.b   V_DOTV.l
        beq.s   dp_new
        cmp.l   V_DOTK.l,d1
        beq.s   dp_map
dp_new: move.l  d1,V_DOTK.l
        move.b  #1,V_DOTV.l
        bsr.w   DotPix
dp_map: lea     TILEA.l,a1
        adda.w  #DOTCELL2,a1
        moveq   #0,d4
        moveq   #7,d6
dp_r1:  moveq   #15,d7
        movea.l a1,a2
dp_c1:  move.b  #$78,1(a2)
        move.b  d4,$4001(a2)
        addq.w  #2,a2
        addq.b  #1,d4
        dbf     d7,dp_c1
        adda.w  #128,a1
        dbf     d6,dp_r1
        rts
DotOff: tst.b   V_DOTV.l
        beq.s   do_r
        clr.b   V_DOTV.l
        lea     TILEA.l,a1
        adda.w  #DOTCELL2,a1
        moveq   #7,d6
do_r1:  moveq   #15,d7
        movea.l a1,a2
do_c1:  move.b  #0,1(a2)
        move.b  #$10,$4001(a2)
        addq.w  #2,a2
        dbf     d7,do_c1
        adda.w  #128,a1
        dbf     d6,do_r1
do_r:   rts

; 1ドット: d0 = x(0〜127) d1 = y(0〜63) d2 = 色。d3・d4・a0 を壊す
DotSet: move.w  d1,d3
        lsr.w   #3,d3
        lsl.w   #4,d3
        move.w  d0,d4
        lsr.w   #3,d4
        add.w   d4,d3
        lsl.w   #5,d3
        move.w  d1,d4
        andi.w  #7,d4
        lsl.w   #2,d4
        add.w   d4,d3
        move.w  d0,d4
        andi.w  #7,d4
        lsr.w   #1,d4
        add.w   d4,d3
        lea     DOTBASE.l,a0
        adda.w  d3,a0
        btst    #0,d0
        bne.s   ds_lo
        andi.b  #$0f,(a0)
        move.b  d2,d4
        lsl.b   #4,d4
        or.b    d4,(a0)
        rts
ds_lo:  andi.b  #$f0,(a0)
        or.b    d2,(a0)
        rts
; 2×2 の点: d0 = x d1 = y(下の段) d2 = 色
DotBig: bsr.s   DotSet
        addq.w  #1,d0
        bsr.s   DotSet
        subq.w  #1,d1
        bsr.s   DotSet
        subq.w  #1,d0
        bsr.s   DotSet
        addq.w  #1,d1
        rts

; 字の絵を描く: 黒で塗る → 枠（色11）→ 目盛り（色12、段1・4・8・12）→ 32個（縦 = 高さ 12段、5ドットおき。下が1段目）
DotPix: lea     DOTBASE.l,a0
        move.l  #$dddddddd,d0
        move.w  #1023,d1
dx_f:   move.l  d0,(a0)+
        dbf     d1,dx_f
        moveq   #11,d2          ; 枠: 上下
        moveq   #0,d0
dx_h:   moveq   #0,d1
        bsr.w   DotSet
        moveq   #63,d1
        bsr.w   DotSet
        addq.w  #1,d0
        cmpi.w  #128,d0
        bcs.s   dx_h
        moveq   #0,d1           ; 枠: 左右
dx_v:   moveq   #0,d0
        bsr.w   DotSet
        moveq   #127,d0
        bsr.w   DotSet
        addq.w  #1,d1
        cmpi.w  #64,d1
        bcs.s   dx_v
        moveq   #12,d2          ; 目盛り
        lea     DOTGY.l,a1
        moveq   #3,d6
dx_g:   move.w  (a1)+,d1
        moveq   #2,d0
dx_g2:  bsr.w   DotSet
        addq.w  #1,d0
        cmpi.w  #126,d0
        bcs.s   dx_g2
        dbf     d6,dx_g
; 高さ: 3つとも決めた → c0 = CUBETBL[((H-1)*4+(S-1))*45+(T-1)]、それ以外は d5 = -1（H だけなら1個目だけ）
        moveq   #-1,d5
        moveq   #0,d1
        move.b  $203f35.l,d1    ; H
        beq.s   dx_nc
        tst.b   $203f36.l
        beq.s   dx_nc
        tst.b   $203f37.l
        beq.s   dx_nc
        subq.w  #1,d1
        lsl.w   #2,d1
        moveq   #0,d0
        move.b  $203f36.l,d0
        subq.w  #1,d0
        add.w   d0,d1
        mulu    #45,d1
        moveq   #0,d0
        move.b  $203f37.l,d0
        subq.w  #1,d0
        add.w   d0,d1
        add.w   d1,d1
        lea     CUBETBL.l,a1
        moveq   #0,d5
        move.w  0(a1,d1.w),d5   ; c0（0〜$fffc）
dx_nc:  moveq   #0,d6           ; i = 0〜31
dx_k:   move.w  d6,d0           ; x = 4 + (i*15)/4
        mulu    #15,d0
        lsr.w   #2,d0
        addq.w  #4,d0
        lea     DOTCAT.l,a1
        move.b  0(a1,d6.w),d2
        tst.l   d5
        bmi.s   dx_unk
        lea     CUBEDLT.l,a1    ; v = c0 + 間隔、高さの番号 = ((v の下位) xor (v の上位)) の bit2-5
        move.w  d6,d1
        add.w   d1,d1
        move.w  0(a1,d1.w),d1
        add.w   d5,d1
        move.w  d1,d3
        lsr.w   #8,d3
        eor.b   d3,d1
        andi.w  #$3c,d1
        lsr.w   #2,d1
        bra.s   dx_lv
dx_unk: tst.w   d6              ; 1個目で H だけ決まっている → H の高さ
        bne.s   dx_line
        moveq   #0,d1
        move.b  $203f35.l,d1
        beq.s   dx_line
        subq.w  #1,d1
dx_lv:  lea     DOTLV.l,a1      ; 段 1〜12 → y = 59 − (段−1)*5
        moveq   #0,d3
        move.b  0(a1,d1.w),d3
        subq.w  #1,d3
        mulu    #5,d3
        moveq   #59,d1
        sub.w   d3,d1
        bsr.w   DotBig
        bra.s   dx_nx
dx_line: moveq  #4,d1           ; 高さが分からない: その色の縦の点線（1段おき）
dx_l2:  bsr.w   DotSet
        addq.w  #2,d1
        cmpi.w  #60,d1
        bcs.s   dx_l2
dx_nx:  addq.w  #1,d6
        cmpi.w  #32,d6
        bcs.w   dx_k
        rts
DOTGY:  dc.w    59,44,24,4
"""

PAUSE = """
; ---- 装備コマンドの回数計算 (改造プレイ中、毎フレーム) ----
; 目標: START=ミサイル・レーザー・オプション4・バリア / SHOT+START=レーザーの代わりにダブル
;       MISSILE+START=レーザー・ダブルなし（ノーマルショット）のフル装備 / SHOT+MISSILE+START=ミサイル・オプション2
;       スピードはどれもメニューの SPEED（MB+$0d）にそろえる（#5）
; ボタン: P1 の bit4=ボタン1（パワーアップ）bit5=ボタン2（ショット）bit6=ボタン3（ミサイル）（#3: 以前は1つずれて読んでいた）
; 結果: MB+$24(1P) / +$2c(2P) に [SPEED,MISSILE,DOUBLE,LASER,OPTION,SHIELD の使用回数, スピードを下げる印（0=下げない / 目標+1）]
CmdCalc:
        lea     $201000.l,a0
        lea     $203f24.l,a1
        bsr.s   cc_one
        lea     $201080.l,a0
        lea     $203f2c.l,a1
cc_one: move.b  MBS_P1.l,d2
        move.b  $69(a0),d0
        andi.b  #$1f,d0
        move.b  $203f0d.l,d1    ; 目標のスピード = メニューの SPEED
        move.b  d1,d3
        sub.b   d0,d1
        bpl.s   cc1
        moveq   #0,d1
cc1:    move.b  d1,(a1)
        clr.b   6(a1)
        cmp.b   d3,d0
        bls.s   cc1b
        addq.b  #1,d3
        move.b  d3,6(a1)        ; 今のほうが速い → 目標まで下げる（メインの Command）
cc1b:
        moveq   #0,d1
        tst.b   $6d(a0)
        bne.s   cc2
        moveq   #1,d1
cc2:    move.b  d1,1(a1)
        clr.b   2(a1)
        clr.b   3(a1)
        clr.b   5(a1)
        moveq   #2,d3
        move.b  d2,d4
        andi.b  #$60,d4
        cmpi.b  #$60,d4         ; ショット＋ミサイル＋START: ミサイル・オプション2
        beq.s   cc_op
        moveq   #4,d3
        cmpi.b  #$40,d4         ; ミサイル＋START: ノーマルショットのフル装備（レーザー・ダブルなし）
        beq.s   cc_sh
        btst    #5,d2
        beq.s   cc_l
        move.b  #1,2(a1)        ; ショット＋START: レーザーの代わりにダブル
        bra.s   cc_sh
cc_l:   move.b  #1,3(a1)
cc_sh:  tst.b   $2b(a0)
        bne.s   cc_op
        move.b  #1,5(a1)
cc_op:  move.b  $68(a0),d0
        andi.b  #7,d0
        sub.b   d0,d3
        bpl.s   cc3
        moveq   #0,d3
cc3:    move.b  d3,4(a1)
        rts

; ---- ランク表示 (改造プレイ中・RANK DISP=ON): 画面左上 行3（残機の右）に "RANK nn" ----
; ---- キューブが壁・ほかのキューブにくっついた瞬間（サブ 0xafc4 の move.b #1,$26(a0) の置き換え）----
;      キューブラッシュ（改造プレイ）なら 1P の点数に 1000点を足す。点数はゲームの加算処理を通さないので、
;      ハイスコア・残機の増加には関わらない（メインの HiHk / RankHk / 次の増加点 0 でも止めてある）
CubeStick:                      ; くっついた印($26)は最後に立てる（立てた瞬間からメインがオブジェクトを片付け始めるので、
        tst.b   (a0)            ;  その前に絵の番号を読む）。メインがもう片付けたオブジェクトなら何もしない（描くと化ける）
        beq.s   cst_x
        cmpi.w  #$3301,$28(a0)
        bne.s   cst_x
        tst.b   MBS_RUN.l
        beq.s   cst_r
        cmpi.b  #2,$203f0b.l
        bne.s   cst_r
        movem.l d0/a1-a2,-(a7)
        lea     CS_PTS.l,a1
        addq.l  #4,a1
        lea     $201058.l,a2
        dc.w    $44fc,$0000     ; move #0,ccr（X=0）
        moveq   #3,d0
cst_l:  dc.w    $c509           ; abcd -(a1),-(a2)
        dbf     d0,cst_l
        movem.l (a7)+,d0/a1-a2
        move.b  #1,$203ed0.l    ; メインに点数の描き直しを頼む
cst_r:  move.l  d2,d6           ; 元の 0xafca〜0xafe4 をここで先にやる: 絵の番号を読んでから「くっついた」印を立てる
        move.l  d3,d7           ;  （印を立てた瞬間からメインがオブジェクトを片付け始めるので、読む前に消されないように）
        move.w  #1,d4
        moveq   #0,d5
        move.w  2(a0),d5
        andi.w  #$1fff,d5
        beq.s   cst_x           ; 絵の番号が 0 = 読む直前にメインが片付けた → 描かない（描くと化ける）
        lsl.l   #7,d5
        ori.l   #$400000,d5
        movea.l d5,a5
        move.b  #1,$26(a0)
        addi.l  #$1c,(a7)       ; 戻り先を 0xafe6（jsr $7dae）へ
        rts
cst_x:  addi.l  #$22,(a7)       ; 戻り先を 0xafec（rts）へ: 描かない
        rts

; ---- 飛んでくるキューブの色分け（CUBE INFO 表示中・毎フレーム）----
; 反応前（$2a=0）は「今の x − 残り待ち時間×2」= 反応する x から色を決めて覚える。反応後は覚えた色のまま。
; 色はスプライトの色番号（オブジェクト $4 の bit1-4）を差し替える。パレット本体は共有RAM $202000〜 に置き、メインが写す
V_CCAT  = $1036f0          ; スロットごとの色の種類（-1=そのまま, 0〜8）32バイト
V_CCW   = $1036ea          ; CUBE COLOR を使いたい（サブの Frame が毎フレーム決める）
V_CCR   = $1036eb          ; 元の色に戻す残りフレーム
V_CCS   = $103724          ; パレットの写しの中身（0=なし 1=色付き 2=元の色 3=元の色＋白 4=色付き＋白 #48）
V_CFW   = $103758          ; CUBE FLASH を使いたい（サブの Frame が毎フレーム決める。#48）
CF_N    = 12               ; 反応の何フレーム前から光らせるか（Python の CF_N と同じ）
CCN     = 9                ; 借りるパレットの数
CubeCol:
        moveq   #0,d5           ; 生きているキューブの数
        lea     $202320.l,a0
        lea     V_CCAT.l,a2
        lea     CCCOL.l,a3
        moveq   #31,d6
kc_l:   tst.b   (a0)
        beq.w   kc_n
        cmpi.w  #$3301,$28(a0)
        bne.w   kc_n
        addq.w  #1,d5
        tst.b   V_CFW.l         ; CUBE FLASH（#48）: 反応する CF_N フレーム前から反応するまで、9つ目（白）の色に
        beq.s   kc_nf
        tst.b   $2a(a0)
        bne.s   kc_nf
        moveq   #0,d0           ; #49 光らせ始める時間（SHORT / NORMAL / LONG）
        move.b  V_CFW.l,d0
        add.w   d0,d0
        lea     CF_NT.l,a4
        move.w  0(a4,d0.w),d0
        cmp.w   $3a(a0),d0
        bcs.s   kc_nf
        btst    #1,$203951.l    ; 点滅（FRAMECNT の下位）: 2フレーム白・2フレーム元の色
        bne.s   kc_nf
        move.l  8(a0),d0        ; 画面の中で反応するキューブだけ（反応する x が 8 以上）
        sub.l   $2038de.l,d0
        asr.l   #8,d0
        move.w  $3a(a0),d1
        add.w   d1,d1
        sub.w   d1,d0
        cmpi.w  #8,d0
        blt.s   kc_nf
        move.b  8(a3),d3
        bra.w   kc_put
kc_nf:  tst.b   V_CCW.l
        bne.s   kc_cc
        tst.b   V_CFW.l         ; CUBE FLASH だけのとき: 光らせ終わったら元の色（パレット29）に戻す
        beq.w   kc_n
        move.b  4(a0),d4
        andi.b  #$1e,d4
        cmp.b   8(a3),d4
        bne.w   kc_n
        moveq   #$1a,d3
        bra.s   kc_put
kc_cc:  tst.b   $2a(a0)
        bne.s   kc_set
        move.l  8(a0),d0
        sub.l   $2038de.l,d0
        asr.l   #8,d0
        move.w  $3a(a0),d1
        add.w   d1,d1
        sub.w   d1,d0           ; 反応する x（8 未満 = 反応しない）
        moveq   #8,d2
        cmpi.w  #8,d0
        blt.s   kc_k
        lea     KC_TH.l,a4      ; 区切り: 46,78,110,142,174,206,238,270 → 7〜0、それ以上は色なし
        moveq   #7,d2
kc_t:   cmp.w   (a4)+,d0
        blt.s   kc_k
        subq.w  #1,d2
        bpl.s   kc_t
kc_k:   cmpi.b  #8,d2           ; CUBE FLASH が ON の間は、9つ目（灰色の枠）は白に使うので、反応しないキューブは元の色
        bne.s   kc_k2
        tst.b   V_CFW.l
        beq.s   kc_k2
        moveq   #-1,d2
kc_k2:  move.b  d2,(a2)
kc_set: move.b  (a2),d2
        bmi.s   kc_n
        ext.w   d2
        move.b  0(a3,d2.w),d3
kc_put: move.b  4(a0),d4
        andi.b  #$e1,d4
        or.b    d3,d4
        move.b  d4,4(a0)
kc_n:   lea     $50(a0),a0
        addq.l  #1,a2
        dbf     d6,kc_l
        ; パレット: 使う間は色付きの9つ、やめたら数フレームだけ元の色を置く（メインが $103cb0〜 を写す）
        tst.w   d5
        beq.s   kc_off
        tst.b   V_CFW.l         ; #48: CUBE FLASH が ON なら、9つ目が白の組
        beq.s   kc_p1
        lea     CFORG.l,a0
        moveq   #3,d1
        tst.b   V_CCW.l
        beq.s   kc_p2
        lea     CFTNT.l,a0
        moveq   #4,d1
        bra.s   kc_p2
kc_p1:  tst.b   V_CCW.l
        beq.s   kc_off
        lea     CCPAL.l,a0
        moveq   #1,d1
kc_p2:  move.b  #3,V_CCR.l
        bra.s   kc_cp
kc_off: tst.b   V_CCR.l
        beq.s   kc_none
        subq.b  #1,V_CCR.l
        lea     CCORG.l,a0
        moveq   #2,d1
kc_cp:  cmp.b   V_CCS.l,d1      ; 写しの中身が同じなら写さない（毎フレーム写すとサブの処理が遅れる）
        beq.s   kc_cs
        move.b  d1,V_CCS.l
        lea     $203cf0.l,a1    ; （0x203cb0〜 は死んだ・始め直すときにゲームが使うので使わない）
        move.w  #125,d0         ; 9パレット × (2+12)語 − 1
kc_c:   move.w  (a0)+,(a1)+
        dbf     d0,kc_c
kc_cs:  move.b  #1,$203ed4.l
        rts
kc_none:
        clr.b   V_CCS.l
        clr.b   $203ed4.l
        rts
KC_TH:  dc.w    46,78,110,142,174,206,238,270
CF_NT:  dc.w    0,8,16,30       ; #49 CUBE FLASH の値（OFF/SHORT/NORMAL/LONG）→ 反応の何フレーム前から点滅させるか

RankDisp:                       ; 2段目の右寄せ「RANK:10」（右端 col 50 = T の数字の右端）
        move.w  FRAMECNT.l,d0   ; 4フレームに1回
        andi.w  #3,d0
        cmpi.w  #2,d0
        bne.s   rd_x
        jsr     PlusChr.l
        move.w  #44,d0
        move.w  #3,d1
        moveq   #6,d7
        jsr     ClrFld.l
        moveq   #0,d5
        move.b  $2039c1.l,d5
        cmpi.w  #99,d5
        bls.s   rd_v
        moveq   #99,d5
rd_v:   move.w  #49,d0
        move.w  #3,d1
        moveq   #0,d2
        moveq   #2,d6
        jsr     PutZ.l
        lea     RK_T.l,a0
        move.w  #44,d0
        move.w  #3,d1
        move.b  #ATTRLAB,d2
        jmp     PutStr.l
rd_x:   rts

;---- STAGE DISP（#30・ポーズで切り替え）: 2P のスコアの場所（段2）に 周回-面エリア とスピード 「01-03H  SP2」を出す（2P の字の位置 = 桁39 から・SP はスコアの数字の右端 = 桁49 にそろえる）。
;      残機は「自機の字 : 03」の数字にする（純正の絵は下の桁しか見ないので9機までしか出ない。残機は BCD・最大99＝表示は98）。
;      表示中は V_SIA を立て、メインのスコア表示（ScoreHk）は 2P だけ描かず、残機の絵（LivHk）も描かない。OFF にしたら消して元に戻す
V_SIF   = $2039c4          ; STAGE DISP の設定（ポーズの項目。共有RAM の空き）
V_SIA   = $2039c5          ; 表示中（メインはこれを見て 2P のスコア・残機の絵を描かない）
V_SBUF  = $103a00          ; 文字列を作る場所（サブ私有RAM・元のプログラムは書かない範囲）
LVADR   = $24c1a0          ; 1P の残機の欄（段3・桁16〜25 の10文字。純正 $1a72 と同じ場所）
StChk:  tst.b   MBS_RUN.l
        beq.w   sc_q
        cmpi.b  #2,TOPSTATE.l
        bne.w   sc_q
        move.w  $20101e.l,d0    ; 面が始まってから（fr と同じ判定。4面でも出る #4）
        or.w    $20109e.l,d0
        beq.w   sc_x
        tst.b   V_SIF.l
        bne.s   sc_on
        tst.b   V_SIA.l
        beq.w   sc_x
        clr.b   V_SIA.l         ; OFF にした → 残機を絵に戻し、上の段を消して、メインに 2P のスコアを描き直してもらう
        bsr.w   StPl
        bsr.w   LvIcon
        tst.b   $203ed1.l       ; CUBE INFO 表示中なら上の段はそのまま
        bne.w   sc_x
        move.w  #37,d0
        move.w  #2,d1
        moveq   #14,d7
        jsr     ClrFld.l
        move.b  #1,$203ed0.l
        rts
sc_q:   clr.b   V_SIA.l         ; 改造プレイの外（タイトル・通常プレイなど）: 描かない・2P も純正どおり
        rts
sc_on:  move.b  #1,V_SIA.l
        move.w  FRAMECNT.l,d0   ; 4フレームに1回（RANK=2・POS=3 とずらす）
        andi.w  #3,d0
        cmpi.w  #1,d0
        bne.w   sc_x
        bsr.w   StPl
        bsr.w   LvNum
        tst.b   $203ed1.l       ; キューブラッシュの CUBE INFO が HI・2P の場所を使っている間は上の段は描かない
        bne.w   sc_x
        move.w  #37,d0          ; 段2 の 桁37〜51 を消す
        move.w  #2,d1
        moveq   #14,d7
        jsr     ClrFld.l
        lea     V_SBUF.l,a0     ; 「周回-面エリア」 例 01-03H（2P の字の位置 = 桁39 から）
        moveq   #0,d5
        move.b  $63(a2),d5      ; 周回 = ($63 >> 1) + 1（2桁）
        lsr.b   #1,d5
        addq.w  #1,d5
        bsr.w   AppD2
        move.b  #$5b,(a0)+      ; '-'（ゲームの字 $2b）
        moveq   #0,d4
        move.b  $51(a2),d4
        andi.b  #$0f,d4
        cmpi.b  #9,d4
        bhi.s   sc_ex
        moveq   #0,d5           ; 面（2桁）
        move.b  d4,d5
        addq.w  #1,d5
        bsr.w   AppD2
        move.w  d4,d0           ; エリア = 進行度 $52 以下で最後の本来のエリア（英字）の開始点
        mulu    #12,d0
        lea     STLAB.l,a3
        adda.w  d0,a3
        add.w   d0,d0
        lea     STPRG.l,a4
        adda.w  d0,a4
        move.w  $52(a2),d1
        move.b  (a3)+,d2
        moveq   #10,d3
sc_al:  addq.w  #2,a4
        tst.b   (a3)
        beq.s   sc_ad
        cmp.w   (a4),d1
        bcs.s   sc_ad
        move.b  (a3)+,d2
        dbf     d3,sc_al
sc_ad:  move.b  d2,(a0)+
        bra.s   sc_sp
sc_ex:  move.b  #$45,(a0)+      ; 隠し面 = EX
        move.b  #$58,(a0)+
sc_sp:  clr.b   (a0)
        moveq   #39,d0
        bsr.s   ScPut
        lea     V_SBUF.l,a0     ; 「SP2」をスコアの数字の右端（桁49）にそろえる
        move.b  #$d3,(a0)+
        move.b  #$d0,(a0)+
        moveq   #0,d5
        move.b  $69(a2),d5      ; スピード = $69 の下位5ビット
        andi.b  #$1f,d5
        bsr.w   AppDec
        clr.b   (a0)
        lea     V_SBUF.l,a1
        suba.l  a1,a0
        moveq   #50,d0
        sub.w   a0,d0
; V_SBUF の文字列を 段2・桁 d0 から描く（bit7 = 見出しの色）
ScPut:  add.w   #128,d0         ; (段2*64+桁)*2
        add.w   d0,d0
        lea     TILEA.l,a1
        adda.w  d0,a1
        lea     V_SBUF.l,a0
sc_pl:  move.b  (a0)+,d4
        beq.s   sc_x
        moveq   #0,d2
        bclr    #7,d4
        beq.s   sc_c
        move.b  #ATTRLAB,d2
sc_c:   cmpi.b  #$20,d4
        bne.s   sc_d
        move.b  #$40,d4
sc_d:   subi.b  #$30,d4
        move.b  d4,$4001(a1)
        move.b  d2,1(a1)
        addq.w  #2,a1
        bra.s   sc_pl
sc_x:   rts
; a2 = 表示する自機（1P。1P の絵が無ければ 2P）
StPl:   lea     $201000.l,a2
        tst.w   $20101e.l
        bne.s   sp_r
        lea     $201080.l,a2
sp_r:   rts
; 残機を数字で: 自機の字($3f) ':' 2桁（= 純正の絵の数 = BCD の $50 − 1）、残りの欄は空白
LvNum:  moveq   #0,d5
        move.b  $50(a2),d5
        move.w  d5,d0
        lsr.w   #4,d0
        mulu    #10,d0
        andi.w  #$0f,d5
        add.w   d0,d5
        subq.w  #1,d5
        bpl.s   ln_p
        moveq   #0,d5
ln_p:   lea     LVADR.l,a1
        move.b  #$3f,$4001(a1)
        clr.b   1(a1)
        move.b  #$0e,$4003(a1)  ; ':'
        clr.b   3(a1)
        divu    #10,d5
        move.b  d5,$4005(a1)
        clr.b   5(a1)
        swap    d5
        move.b  d5,$4007(a1)
        clr.b   7(a1)
        addq.w  #8,a1
        moveq   #5,d7
        bra.s   lv_bl
; 残機を純正どおりの絵に戻す（$1a72 と同じ: 下の桁 − 1 個の自機の字、残りは空白。10文字）
LvIcon: moveq   #0,d5
        move.b  $50(a2),d5
        andi.w  #$0f,d5
        lea     LVADR.l,a1
        moveq   #9,d7
li_l:   subq.w  #1,d5
        ble.s   lv_bl
        move.b  #$3f,$4001(a1)
        clr.b   1(a1)
        addq.w  #2,a1
        dbf     d7,li_l
        rts
lv_bl:  move.b  #$10,$4001(a1)
        clr.b   1(a1)
        addq.w  #2,a1
        dbf     d7,lv_bl
        rts
; d5.w を2桁以上で（10未満は頭に0）
AppD2:  cmpi.w  #10,d5
        bcc.s   AppDec
        move.b  #$30,(a0)+
; d5.w の10進数を（先頭の0なしで）a0 に足す
AppDec: andi.l  #$ffff,d5
        divu    #10,d5
        swap    d5
        move.w  d5,-(a7)
        clr.w   d5
        swap    d5
        tst.w   d5
        beq.s   ad_o
        bsr.s   AppDec
ad_o:   move.w  (a7)+,d5
        addi.b  #$30,d5
        move.b  d5,(a0)+
        rts

; ---- POS DISP（ポーズで切り替え）: RANK の下の段に画面の位置 「X:1CA0 Y:0200」（ゲームの進み具合の値 = 画面の位置÷0x100）
V_PSL   = $103731          ; 位置を表示しているか（OFF にしたら消す）
PosChk: tst.b   MBS_RUN.l
        beq.w   po_x
        cmpi.b  #2,TOPSTATE.l
        bne.w   po_x
        move.w  $20101e.l,d0    ; 面が始まってから（fr と同じ判定。#4）
        or.w    $20109e.l,d0
        beq.w   po_x
        tst.b   $203f2b.l
        bne.s   po_on
        tst.b   V_PSL.l
        beq.w   po_x
        clr.b   V_PSL.l
        move.w  #38,d0
        move.w  #4,d1
        moveq   #13,d7
        jmp     ClrFld.l
po_on:  move.b  #1,V_PSL.l
        move.w  FRAMECNT.l,d0   ; 4フレームに1回
        andi.w  #3,d0
        cmpi.w  #3,d0
        bne.w   po_x
        jsr     PlusChr.l
        lea     PO_X.l,a0
        move.w  #38,d0
        move.w  #4,d1
        move.b  #ATTRLAB,d2
        jsr     PutStr.l
        lea     PO_Y.l,a0
        move.w  #45,d0
        move.w  #4,d1
        move.b  #ATTRLAB,d2
        jsr     PutStr.l
        move.l  $2038de.l,d5     ; X÷0x100
        lsr.l   #8,d5
        move.w  #40,d0
        bsr.s   PoHex
        move.l  $2038e2.l,d5
        lsr.l   #8,d5
        move.w  #47,d0
PoHex:  lea     V_TMP.l,a0      ; d5.w を16進4桁で (d0=桁)
        moveq   #3,d6
ph_l:   rol.w   #4,d5
        move.b  d5,d7
        andi.b  #$0f,d7
        addi.b  #$30,d7
        cmpi.b  #$3a,d7
        bcs.s   ph_d
        addq.b  #7,d7           ; A〜F
ph_d:   move.b  d7,(a0)+
        dbf     d6,ph_l
        clr.b   (a0)
        lea     V_TMP.l,a0
        move.w  #4,d1
        moveq   #0,d2
        jmp     PutStr.l
po_x:   rts

; ---- NO DEATH（#36・CUBE NO DEATH #39）: 残り30秒から、段4・桁27〜33 に「TIME 29」を出してカウントダウン（残りはメインが ND_LEFT $103e10 で数える）
V_NDL   = $103733          ; 表示しているか（30秒より多くなったら消す）
NdDisp: tst.b   MBS_RUN.l
        beq.w   nd_q
        tst.b   $203e1a.l       ; ND_FLAG（NO DEATH または CUBE NO DEATH）
        beq.w   nd_q
        cmpi.b  #2,TOPSTATE.l
        bne.w   nd_q
        move.w  $20101e.l,d0    ; 面が始まってから（fr と同じ判定）
        or.w    $20109e.l,d0
        beq.w   nd_q
        move.l  $203e10.l,d5
        cmpi.l  #1800,d5
        bhi.s   nd_off
        move.w  FRAMECNT.l,d0   ; 4フレームに1回（STAGE=1・RANK=2・POS=3 とずらす）
        andi.w  #3,d0
        bne.w   nd_q
        move.b  #1,V_NDL.l
        lea     ND_T.l,a0
        move.w  #27,d0
        move.w  #4,d1
        move.b  #ATTRLAB,d2
        jsr     PutStr.l
        addi.l  #59,d5          ; 秒（切り上げ。0 になった瞬間にゲームオーバー）
        divu    #60,d5
        move.w  #32,d0
        move.w  #4,d1
        moveq   #0,d2
        jmp     PutDec.l
nd_off: tst.b   V_NDL.l
        beq.s   nd_q
        clr.b   V_NDL.l
        move.w  #27,d0
        move.w  #4,d1
        moveq   #6,d7
        jmp     ClrFld.l
nd_q:   rts

; ---- NO DEATH（#36・CUBE NO DEATH #39）: メニューから始めた最初の START 表示の間だけ、操作の案内を2行出す（この間は地形・背景が黒いので読みやすい #20）
V_NDM   = $103734          ; 案内を出しているか
NDMROW  = 19
NdMsg:  tst.b   MBS_RUN.l
        beq.s   nm_off
        tst.b   $203e1a.l       ; ND_FLAG（NO DEATH または CUBE NO DEATH）
        beq.s   nm_off
        cmpi.b  #2,TOPSTATE.l
        bne.s   nm_off
        move.b  $203f1a.l,d0    ; 最初の START 表示: 面・エリアは反映済み（bit2 が下りた）で、その人の開始時の設定がまだ（bit0/1）
        btst    #2,d0
        bne.s   nm_off
        move.b  $203f05.l,d1    ; 1P で始めた = bit0 / 2P = bit1（MB_KIND）
        subq.b  #1,d1
        btst    d1,d0
        beq.s   nm_off
        move.b  #1,V_NDM.l      ; 毎フレーム描く（START 表示の始めにゲームが文字の面を消すので）
        lea     ND_M1.l,a0
        move.w  #17,d0
        move.w  #NDMROW,d1
        moveq   #0,d2
        jsr     PutStr.l
        lea     ND_M2.l,a0
        move.w  #17,d0
        move.w  #NDMROW+2,d1
        moveq   #0,d2
        jmp     PutStr.l
nm_off: tst.b   V_NDM.l
        beq.s   nm_r
        clr.b   V_NDM.l
        move.w  #17,d0
        move.w  #NDMROW,d1
        moveq   #29,d7
        jsr     ClrFld.l
        move.w  #17,d0
        move.w  #NDMROW+2,d1
        moveq   #29,d7
        jmp     ClrFld.l
nm_r:   rts

; ---- CUBE LINE（キューブラッシュ・ポーズで切り替え）: V = 縦（反応する位置）/ H = 横（高さ）
;      値 0=OFF 1=粗い点線 2=細かい点線(縦)・線(横) 3=端だけ（縦は上下の端、横は左右の端）
;      描いた組み合わせを覚えておき、変わったとき・ゲームに消されたときだけ描き直す（毎回描くとサブの処理が重くなる）
V_LNL   = $103732               ; 描いてある組み合わせ+1（0 = 何も描いていない）
LNROW0  = 5                     ; 縦線の段 5〜27（スコア・ランク・位置の段とゲージの段は避ける）
LNROW1  = 27
CubeLine:
        move.b  $203f1c.l,$203f3b.l     ; #49 横はいつも縦と同じ（OFF / ROUGH / FINE=LINE / EDGE）
        cmpi.b  #2,$203f0b.l
        bne.w   ln_r
        cmpi.b  #1,MBS_PAUS.l   ; ポーズ中は描かない（ポーズの窓と重なるので）
        beq.w   ln_r
        moveq   #0,d3
        move.b  $203f1c.l,d3    ; V
        lsl.b   #4,d3
        or.b    $203f3b.l,d3    ; H
        addq.b  #1,d3           ; 組み合わせ+1
        cmp.b   V_LNL.l,d3
        bne.s   ln_new
        cmpi.b  #1,d3           ; 両方 OFF で消してある
        beq.w   ln_r
        cmpi.b  #$43,$250de7.l  ; 消されていないか: 右下（段27・桁51）の目印の文字（透明な 0xf43）
        bne.s   ln_new
        cmpi.b  #$ff,$29e3a0.l  ; 文字の形も残っているか（左端の印の文字 0xf1d の1バイト目）
        beq.w   ln_r
ln_new: move.b  d3,V_LNL.l
        lea     LNGFX.l,a0      ; 文字の形 0xf00〜0xf42
        lea     $29e000.l,a1
        move.w  #543,d0       ; 68文字 x 8ロング
ln_g:   move.l  (a0)+,(a1)+
        dbf     d0,ln_g
        ; 場所をいったん空白に（段 5〜28, 桁 12〜51）
        lea     $24c298.l,a1     ; 段5・桁12
        moveq   #23,d0          ; 24段
ln_cr:  moveq   #39,d1          ; 40桁
        movea.l a1,a2
ln_cc:  clr.b   1(a2)
        move.b  #$10,$4001(a2)
        addq.l  #2,a2
        dbf     d1,ln_cc
        lea     128(a1),a1
        dbf     d0,ln_cr
        ; 横（高さ12通り = 段 6,8,..,28）
        move.b  $203f3b.l,d4
        beq.s   ln_v
        moveq   #6,d0
ln_hr:  cmpi.b  #3,d4
        bne.s   ln_hf
        moveq   #12,d1
        moveq   #29,d2
        bsr.w   LnPut
        moveq   #51,d1
        moveq   #30,d2
        bsr.w   LnPut
        bra.s   ln_hn
ln_hf:  moveq   #26,d2          ; 27=粗い 28=線
        add.b   d4,d2
        moveq   #12,d1
ln_hc:  bsr.w   LnPut
        addq.w  #1,d1
        cmpi.w  #52,d1
        bcs.s   ln_hc
ln_hn:  addq.w  #2,d0
        cmpi.w  #30,d0
        bcs.s   ln_hr
        ; 縦（9か所）
ln_v:   move.b  $203f1c.l,d5
        beq.w   ln_mk
        lea     LNCOL.l,a3
        moveq   #0,d6           ; k
ln_vk:  moveq   #0,d1
        move.b  0(a3,d6.w),d1
        beq.w   ln_mk
        cmpi.b  #3,d5
        bne.s   ln_vf
        moveq   #18,d2          ; 端だけ: 実線を上下の段に
        add.w   d6,d2
        moveq   #5,d0
        bsr.w   LnPut
        moveq   #27,d0
        bsr.w   LnPut
        bra.s   ln_vn
ln_vf:  moveq   #5,d0
ln_vr:  moveq   #0,d2
        move.b  d5,d2           ; 縦だけ: (V-1)*9+k
        subq.w  #1,d2
        mulu    #9,d2
        add.w   d6,d2
        btst    #0,d0           ; 横の段（偶数の段 6〜28）と交わる → 交わりの文字
        bne.s   ln_vp
        cmpi.w  #6,d0
        bcs.s   ln_vp
        tst.b   d4
        beq.s   ln_vp
        cmpi.b  #3,d4
        beq.s   ln_vp
        moveq   #0,d2           ; 31+((V-1)*2+(H-1))*9+k
        move.b  d5,d2
        subq.w  #1,d2
        add.w   d2,d2
        add.b   d4,d2
        subq.w  #1,d2
        mulu    #9,d2
        add.w   d6,d2
        addi.w  #31,d2
ln_vp:  bsr.w   LnPut
        addq.w  #1,d0
        cmpi.w  #28,d0
        bcs.s   ln_vr
ln_vn:  addq.w  #1,d6
        bra.s   ln_vk
ln_mk:  cmpi.b  #1,d3           ; 確認の目印（何か描いたときだけ）: 右下（段27・桁51）に透明な文字 0xf43
        beq.s   ln_r
        moveq   #27,d0
        moveq   #51,d1
        moveq   #$43,d2
        bsr.w   LnPut
        bra.s   ln_r
; d0=段 d1=桁 d2=文字(0xf00+) を描く
LnPut:  bsr.s   LnAdr
        move.b  #$dd,1(a1)      ; パレット6 + 番号の上位 0xf
        move.b  d2,$4001(a1)
        rts
LnAdr:  move.w  d0,d7
        lsl.w   #6,d7
        add.w   d1,d7
        add.w   d7,d7
        lea     TILEA.l,a1
        adda.w  d7,a1
        rts
ln_r:   rts

; ---- #38 HIT DISP: 当たり判定の表示（毎フレーム。ポーズ中は何もしない）----
; 前のフレームに置いた升目を消してから、今の当たりを描く。消すのは、まだ自分の文字が残っている升目だけ
; 置くのは段 HB_R0〜HB_R1（スコア・残機・ゲージの段は避ける）で、空白の升目だけ（ゲームの文字は消さない）
HB_FLAG = $203e1b       ; ON/OFF（共有RAM $103E1B。#57）
HB_R0   = 4
HB_R1   = 27
HB_ATTR = $dc           ; パレット6・文字の上位 $e00（$E80〜 の下位は $80〜）
HB_GFX  = $29d000       ; 文字 $E80 の絵（$280000 + $E80*32）
HB_OX   = 96            ; 画面の x → 文字の面の x（桁 = (x + 96) / 8）
HB_YC   = 254           ; 文字の面の y = HB_YC − 当たりの Y（画面の y = 238 − Y、段 = (y + 16) / 8）
HB_MAX  = 150
V_HBN   = $1034d0       ; 置いた升目の数.w（$1034c0〜$1034c4 はエディット画面の変数）
V_HBL   = $1034d2       ; 置いた升目（TILEA からの位置.w）× HB_MAX（〜$1035fd。$103600〜 はメニュー中に使う）
HitDisp:
        cmpi.b  #1,MBS_PAUS.l
        beq.w   hd_r
        lea     TILEA.l,a2
        lea     $250000.l,a6    ; 文字の番号の側（TILEA + $4000）
        lea     V_HBL.l,a0
        move.w  V_HBN.l,d0
        clr.w   V_HBN.l
        cmpi.w  #HB_MAX,d0      ; 電源を入れた直後（面の開始で消すまで）は不定値なので、多すぎたら消さない
        bls.s   hd_e2
        moveq   #0,d0
        bra.s   hd_e2
hd_e1:  move.w  (a0)+,d1
        cmpi.b  #HB_ATTR,1(a2,d1.w)
        bne.s   hd_e2
        move.b  1(a6,d1.w),d2
        subi.b  #$80,d2
        cmpi.b  #6,d2
        bhi.s   hd_e2
        clr.b   1(a2,d1.w)
        move.b  #$10,1(a6,d1.w)
hd_e2:  dbf     d0,hd_e1
        tst.b   MBS_RUN.l
        beq.w   hd_r
        tst.b   HB_FLAG.l
        beq.w   hd_r
        lea     HB_GFX.l,a1     ; 自機の6字を消し、印の字を入れる
        moveq   #47,d0
hd_c:   clr.l   (a1)+
        dbf     d0,hd_c
        lea     HBGFX.l,a0
        moveq   #7,d0
hd_m:   move.l  (a0)+,(a1)+
        dbf     d0,hd_m
        move.l  $2038de.l,d4    ; 画面の位置（ドット）
        lsr.l   #8,d4
        move.l  $2038e2.l,d5
        lsr.l   #8,d5
        lea     $202320.l,a3    ; 敵・弾など
        moveq   #$41,d6
        bsr.w   hd_lst
        lea     $201240.l,a3    ; 自機の側（オプション・自機の弾など）
        moveq   #$35,d6
        bsr.w   hd_lst
        lea     $201000.l,a3    ; 自機: ドット単位の枠
        tst.b   (a3)
        bpl.w   hd_r
        bsr.w   hd_box          ; d0=左 d1=右 d2=上 d3=下（文字の面のドット）
        move.w  d0,d6           ; 3×2 字の左上の桁・段
        asr.w   #3,d6
        move.w  d2,d7
        asr.w   #3,d7
        movea.w d6,a4
        movea.w d7,a5
        lsl.w   #3,d6
        lsl.w   #3,d7
        sub.w   d6,d0
        sub.w   d6,d1
        sub.w   d7,d2
        sub.w   d7,d3
        movem.w d0-d3,-(a7)     ; (a7)=左 2=右 4=上 6=下
        move.w  (a7),d6
hd_h:   move.w  d6,d0
        move.w  4(a7),d1
        bsr.w   hd_pix
        move.w  d6,d0
        move.w  6(a7),d1
        bsr.w   hd_pix
        addq.w  #1,d6
        cmp.w   2(a7),d6
        ble.s   hd_h
        move.w  4(a7),d6
hd_v:   move.w  (a7),d0
        move.w  d6,d1
        bsr.w   hd_pix
        move.w  2(a7),d0
        move.w  d6,d1
        bsr.w   hd_pix
        addq.w  #1,d6
        cmp.w   6(a7),d6
        ble.s   hd_v
        addq.l  #8,a7
        moveq   #-128,d7        ; 文字 $E80〜$E85 を 3×2 に置く
        moveq   #0,d6
hd_pr:  moveq   #0,d5
hd_pc:  move.w  a4,d0
        add.w   d5,d0
        move.w  a5,d1
        add.w   d6,d1
        bsr.w   hd_put
        addq.b  #1,d7
        addq.w  #1,d5
        cmpi.w  #3,d5
        bcs.s   hd_pc
        addq.w  #1,d6
        cmpi.w  #2,d6
        bcs.s   hd_pr
hd_r:   rts

; a3 のオブジェクトの当たりの箱 → d0=左 d1=右 d2=上 d3=下（文字の面のドット。d4/d5 = 画面の位置）
hd_box: move.l  8(a3),d0
        lsr.l   #8,d0
        add.w   $36(a3),d0
        sub.w   d4,d0
        addi.w  #HB_OX,d0
        move.l  $c(a3),d2
        lsr.l   #8,d2
        add.w   $38(a3),d2
        sub.w   d5,d2
        neg.w   d2              ; 当たりの Y は下から上へ増える → 文字の面の y = HB_YC − Y
        addi.w  #HB_YC,d2
        move.w  d0,d1
        sub.w   $14(a3),d0
        add.w   $14(a3),d1
        move.w  d2,d3
        sub.w   $16(a3),d2
        add.w   $16(a3),d3
        rts

; 表（a3 から d6+1 個、$50 ずつ）の当たりの升目に印を置く
hd_lst: tst.b   (a3)
        bpl.w   hl_n
        movem.l d4-d6,-(a7)
        bsr.s   hd_box
        asr.w   #3,d0
        asr.w   #3,d1
        asr.w   #3,d2
        asr.w   #3,d3
        cmpi.w  #12,d0
        bge.s   hl_1
        moveq   #12,d0
hl_1:   cmpi.w  #51,d1
        ble.s   hl_2
        moveq   #51,d1
hl_2:   cmpi.w  #HB_R0,d2
        bge.s   hl_3
        moveq   #HB_R0,d2
hl_3:   cmpi.w  #HB_R1,d3
        ble.s   hl_4
        moveq   #HB_R1,d3
hl_4:   movea.w d0,a4
        movea.w d1,a5
        moveq   #-122,d7        ; 文字 $E86（印）
hl_r:   cmp.w   d3,d2
        bgt.s   hl_x
        move.w  a4,d4
hl_c:   cmp.w   a5,d4
        bgt.s   hl_rn
        move.w  d4,d0
        move.w  d2,d1
        bsr.s   hd_put
        addq.w  #1,d4
        bra.s   hl_c
hl_rn:  addq.w  #1,d2
        bra.s   hl_r
hl_x:   movem.l (a7)+,d4-d6
hl_n:   lea     $50(a3),a3
        dbf     d6,hd_lst
        rts

; 升目（d0=桁 d1=段）に文字（下位 d7）を置く。空白の升目だけ。置いた所を V_HBL に覚える。a1 を壊す
hd_put: cmpi.w  #HB_R0,d1
        blt.s   hp_x
        cmpi.w  #HB_R1,d1
        bgt.s   hp_x
        cmpi.w  #12,d0
        blt.s   hp_x
        cmpi.w  #51,d0
        bgt.s   hp_x
        cmpi.w  #HB_MAX,V_HBN.l
        bcc.s   hp_x
        move.w  d1,-(a7)
        lsl.w   #6,d1
        add.w   d0,d1
        add.w   d1,d1
        tst.b   1(a2,d1.w)
        bne.s   hp_y
        cmpi.b  #$10,1(a6,d1.w)
        bne.s   hp_y
        move.b  #HB_ATTR,1(a2,d1.w)
        move.b  d7,1(a6,d1.w)
        movea.w V_HBN.l,a1
        adda.w  a1,a1
        adda.l  #V_HBL,a1
        move.w  d1,(a1)
        addq.w  #1,V_HBN.l
hp_y:   move.w  (a7)+,d1
hp_x:   rts

; 自機の枠の1ドット（d0=x 0〜23, d1=y 0〜15。3×2 字の中）を赤に。a1 を壊す
hd_pix: cmpi.w  #23,d0
        bhi.s   hx_x
        cmpi.w  #15,d1
        bhi.s   hx_x
        movem.w d0-d2,-(a7)
        move.w  d1,d2           ; 字の番号 = (y/8)*3 + x/8
        lsr.w   #3,d2
        mulu    #3,d2
        move.w  d0,-(a7)
        lsr.w   #3,d0
        add.w   d0,d2
        lsl.w   #5,d2           ; ×32
        andi.w  #7,d1
        lsl.w   #2,d1
        add.w   d1,d2
        move.w  (a7)+,d0
        move.w  d0,d1
        andi.w  #7,d0
        lsr.w   #1,d0
        add.w   d0,d2
        lea     HB_GFX.l,a1
        btst    #0,d1
        bne.s   hx_lo
        ori.b   #$e0,0(a1,d2.w)
        bra.s   hx_e
hx_lo:  ori.b   #$0e,0(a1,d2.w)
hx_e:   movem.w (a7)+,d0-d2
hx_x:   rts

V_PST   = $103450
V_PSEL  = $103451
V_PPIN  = $103452
V_PSIN  = $103453
V_PSAV  = $103800          ; 12行x21桁x2バイト = 504（〜0x1039f7）（ポーズの間だけ使う。プレイ中は元のプログラムが使っていない範囲）。13行目からは保存せず、閉じるときに消す
V_PMAP  = $103740          ; いま出している項目の PTAB の番号（最大20）
V_PCNT  = $103754          ; 出している項目の数
V_PY    = $103755          ; 窓の一番上の段（項目の数で上下に動かす）
MBS_INV = $203f20          ; 無敵（メインの MB+$20）
V_LINV  = $203ef0          ; スタートメニューの前回値の写し（MB+$20 に対応）
EQ_REQ  = $203e14          ; 装備を変えた（再開のときにメインが装備をやり直す）。値は +1〜+5（SPEED MISSILE DOUBLE/LASER OPTION SHIELD）
PX      = 26
PW      = 21
PI_EQ   = 6                ; PTAB の装備の項目の始め（6〜10 = 装備、11 = MISS）。12〜16 = キューブラッシュの項目
PI_MISS = 11
PI_CUBE = 12
PI_HIT  = 17
PI_CF   = 18
PI_CS   = 20               ; #60 CUBE SE
PI_TIME = 19               ; #55 NO DEATH の残り時間（読むだけ。値は PDraw が作る）
; ---- 出す項目の表を作る: いつもの6つ ＋ NO DEATH なら装備と MISS ＋ キューブラッシュならキューブの5つ。d6 = 数 ----
PMap:   lea     V_PMAP.l,a0
        moveq   #0,d0
pm_b:
NOINV_PM
        move.b  d0,(a0)+
pm_b2:  addq.b  #1,d0
        cmpi.b  #PI_EQ,d0
        bcs.s   pm_b
        tst.b   $203e1a.l       ; TIME（#55）: NO DEATH・CUBE NO DEATH のときだけ、残り時間を読めるように出す
        beq.s   pm_nt
        move.b  #PI_TIME,(a0)+
pm_nt:
        cmpi.b  #2,$203f0b.l    ; HIT DISP（#38）はキューブラッシュ（CUBE NO DEATH も始めると 2）のほかで出す（2026-10-30 管理者）
        beq.s   pm_nh
        move.b  #PI_HIT,(a0)+
pm_nh:
        cmpi.b  #1,$203f0b.l    ; 装備と MISS は NO DEATH のときだけ（2026-10-29 管理者。INVINCIBLE はリリースで外すので）
        bne.s   pm_c
pm_e:   move.b  d0,(a0)+
        addq.b  #1,d0
        cmpi.b  #PI_CUBE,d0
        bcs.s   pm_e
pm_c:   cmpi.b  #2,$203f0b.l
        bne.s   pm_x
        moveq   #PI_CUBE,d0
pm_k:   cmpi.b  #PI_CUBE+3,d0   ; CUBE LINE H は出さない（#49。CUBE LINE にまとめた）
        beq.s   pm_k2
        move.b  d0,(a0)+
        cmpi.b  #PI_CUBE+1,d0   ; CUBE FLASH（#48）は CUBE COLOR の下・CUBE LINE の上（#57）
        bne.s   pm_k2
        move.b  #PI_CF,(a0)+
        move.b  #PI_CS,(a0)+    ; CUBE SE（#60）は CUBE FLASH の下
pm_k2:  addq.b  #1,d0
        cmpi.b  #PI_CUBE+5,d0
        bcs.s   pm_k
pm_x:   move.l  a0,d6
        subi.l  #V_PMAP,d6
        move.b  d6,V_PCNT.l
        moveq   #17,d0          ; 窓の位置: 項目が多いときは上へ（17 − (数+1)/2）
        move.w  d6,d1
        addq.w  #1,d1
        lsr.w   #1,d1
        sub.w   d1,d0
        move.b  d0,V_PY.l
        rts
; d6 = 出している項目の数
PCnt6:  moveq   #0,d6
        move.b  V_PCNT.l,d6
        rts
; d0 = 選んでいる項目の PTAB の番号
PSelIx: moveq   #0,d0
        move.b  V_PSEL.l,d0
        lea     V_PMAP.l,a0
        move.b  0(a0,d0.w),d0
        rts
; d1 = 窓の一番上の段
PYd1:   moveq   #0,d1
        move.b  V_PY.l,d1
        rts

; ---- ポーズ窓: 保存/復元 (layer A, 段 V_PY〜, 桁PX..PX+PW-1) ----
PSave:  lea     V_PSAV.l,a0
        moveq   #0,d0
        bra.s   ps_go
PRest:  lea     V_PSAV.l,a0
        moveq   #1,d0
ps_go:  bsr.w   PCnt6           ; 段の数−1 = 項目の数
        bsr.w   PYd1
        moveq   #0,d5           ; 何段目か（12段目まで保存する）
pr_row: move.w  d1,d3
        lsl.w   #6,d3
        addi.w  #PX,d3
        add.w   d3,d3
        lea     TILEA.l,a1
        adda.w  d3,a1
        moveq   #PW-1,d7
pr_col: cmpi.w  #12,d5
        bcc.s   pr_x
        tst.b   d0
        bne.s   pr_r
        move.b  1(a1),(a0)+
        move.b  $4001(a1),(a0)+
        bra.s   pr_n
pr_r:   move.b  (a0)+,1(a1)
        move.b  (a0)+,$4001(a1)
        bra.s   pr_n
pr_x:   tst.b   d0              ; 13段目から: 閉じるときは消す
        beq.s   pr_n
        move.b  #$10,$4001(a1)
        clr.b   1(a1)
pr_n:   addq.w  #2,a1
        dbf     d7,pr_col
        addq.w  #1,d1
        addq.w  #1,d5
        dbf     d6,pr_row
        rts

; 1行描く: a0=文字列(選択中なら '>' 付き), d4=何番目か → 段 V_PY+1+d4
PLine:  move.w  #PX+1,d0
        bsr.w   PYd1
        add.w   d4,d1
        addq.w  #1,d1
        moveq   #0,d2
        jmp     PutStr.l

PDraw:  bsr.w   PMap
        bsr.w   PYd1
pd_cl:  move.w  #PX,d0
        moveq   #PW-1,d7
        movem.l d1/d6,-(a7)
        jsr     ClrFld.l
        movem.l (a7)+,d1/d6
        addq.w  #1,d1
        dbf     d6,pd_cl
        lea     PS_T.l,a0
        move.w  #PX+6,d0
        bsr.w   PYd1
        moveq   #0,d2
        jsr     PutStr.l
        moveq   #0,d4
pd_lp:  lea     V_PMAP.l,a2
        moveq   #0,d0
        move.b  0(a2,d4.w),d0
        lsl.w   #4,d0
        lea     PTAB.l,a2
        adda.w  d0,a2
        movea.l 4(a2),a0
        cmp.b   V_PSEL.l,d4
        bne.s   pd_u
        movea.l (a2),a0
pd_u:   movem.l d4/a2,-(a7)
        bsr.w   PLine
        movem.l (a7)+,d4/a2
        lea     V_PMAP.l,a3     ; TIME（#55）は値の場所を持たないので、ここで作って描く
        cmpi.b  #PI_TIME,0(a3,d4.w)
        beq.w   pd_tm
        move.l  8(a2),d0
        beq.s   pd_nx
        movea.l d0,a3
        move.l  12(a2),d0       ; 値の表があれば、その文字列
        beq.s   pd_oo
        movea.l d0,a0
        moveq   #0,d0
        move.b  (a3),d0
        lsl.w   #2,d0
        movea.l 4(a0,d0.w),a0
        bra.s   pd_v
pd_oo:  lea     PS_OFF.l,a0
        tst.b   (a3)
        beq.s   pd_v
        lea     PS_ON.l,a0
pd_v:   movem.l d4/a2,-(a7)
        move.w  #PX+15,d0
        bsr.w   PYd1
        add.w   d4,d1
        addq.w  #1,d1
        moveq   #0,d2
        jsr     PutStr.l
        movem.l (a7)+,d4/a2
pd_nx:  addq.w  #1,d4
        bsr.w   PCnt6
        cmp.w   d6,d4
        bcs.w   pd_lp
        rts
; ---- TIME（#55）: NO DEATH の残りフレーム（$203E10）を 分:秒 にして V_TMP に作る（'>' が ':' として出る）----
pd_tm:  move.l  $203e10.l,d5
        addi.l  #59,d5          ; 秒に切り上げ（NdDisp と同じ数え方）
        cmpi.l  #359999,d5      ; 99:59 で頭打ち（divu があふれないように）
        bcs.s   pt_ok
        move.l  #359999,d5
pt_ok:  divu    #60,d5          ; 下位 = 秒
        andi.l  #$ffff,d5
        divu    #60,d5          ; 下位 = 分、上位 = 秒
        lea     V_TMP.l,a0
        move.w  d5,d6
        divu    #10,d6
        move.b  d6,d7
        addi.b  #$30,d7
        move.b  d7,(a0)+        ; 分の十の位
        swap    d6
        move.b  d6,d7
        addi.b  #$30,d7
        move.b  d7,(a0)+        ; 分の一の位
        move.b  #$3e,(a0)+      ; '>' = 画面では ':'
        swap    d5
        move.w  d5,d6
        divu    #10,d6
        move.b  d6,d7
        addi.b  #$30,d7
        move.b  d7,(a0)+        ; 秒の十の位
        swap    d6
        move.b  d6,d7
        addi.b  #$30,d7
        move.b  d7,(a0)+        ; 秒の一の位
        clr.b   (a0)
        lea     V_TMP.l,a0
        bra.w   pd_v

; ---- ポーズを開いたとき: 装備の項目に、いまの装備を入れる（1P の自機 $201000） ----
EqRead: lea     $201000.l,a0
        lea     EQ_REQ.l,a1
        clr.b   (a1)+
        move.b  $69(a0),d0      ; SPEED = $69 の下位5ビット（5まで）
        andi.b  #$1f,d0
        cmpi.b  #5,d0
        bls.s   er_s
        moveq   #5,d0
er_s:   move.b  d0,(a1)+
        tst.b   $6d(a0)         ; MISSILE
        sne     d0
        andi.b  #1,d0
        move.b  d0,(a1)+
        moveq   #0,d0           ; DOUBLE/LASER: $6c = 0 なし / 1〜3 ダブル / 4〜 レーザー
        move.b  $6c(a0),d1
        beq.s   er_d
        moveq   #1,d0
        cmpi.b  #4,d1
        bcs.s   er_d
        moveq   #2,d0
er_d:   move.b  d0,(a1)+
        moveq   #0,d0           ; OPTION = 動いているオプション（$201100 から $50 ごと4つ。先頭の bit7）
        lea     $201100.l,a2
        moveq   #3,d1
er_o:   tst.b   (a2)
        bpl.s   er_o2
        addq.b  #1,d0
er_o2:  lea     $50(a2),a2
        dbf     d1,er_o
        move.b  d0,(a1)+
        tst.b   $201f60.l       ; SHIELD = $201f60 の先頭の bit7
        smi     d0
        andi.b  #1,d0
        move.b  d0,(a1)+
        rts

; ---- ポーズ 1フレーム (MBS_PAUS==1 の間) ----
; 上下で選ぶ。ON/OFF・値のある行では 左右・ショットで切り替え。START か ショットで決定（CONTINUE などの行）
PauseFrame:
        tst.b   V_PST.l
        bne.s   pf_run
        move.b  #1,V_PST.l
        clr.b   V_PSEL.l
        move.b  MBS_P1.l,V_PPIN.l
        move.b  MBS_SYS.l,V_PSIN.l
        bsr.w   EqRead
        bsr.w   PMap
        jsr     PSave.l
        jmp     PDraw.l
pf_run: move.b  MBS_P1.l,d0
        move.b  V_PPIN.l,d1
        move.b  d0,V_PPIN.l
        not.b   d1
        and.b   d0,d1
        move.b  MBS_SYS.l,d4
        move.b  V_PSIN.l,d5
        move.b  d4,V_PSIN.l
        not.b   d5
        and.b   d4,d5
        btst    #2,d1           ; 上
        beq.s   pf_dn
        subq.b  #1,V_PSEL.l
        bpl.w   pf_rd
        bsr.w   PCnt6
        subq.b  #1,d6
        move.b  d6,V_PSEL.l
        bra.w   pf_rd
pf_dn:  btst    #3,d1           ; 下
        beq.s   pf_lr
        addq.b  #1,V_PSEL.l
        bsr.w   PCnt6
        cmp.b   V_PSEL.l,d6
        bhi.w   pf_rd
        clr.b   V_PSEL.l
        bra.w   pf_rd
pf_lr:  bsr.w   PSelIx          ; ON/OFF・値のある行: 左右・ショットで切り替え
        cmpi.b  #2,d0           ; INVINCIBLE の行は NO DEATH / CUBE NO DEATH では変えられない（いつも無敵）
        bne.s   pf_l2
        tst.b   $203e1a.l       ; ND_FLAG (#36/#39)
        bne.w   pf_nm
pf_l2:  move.w  d0,d6           ; d6 = PTAB の番号
        mulu    #16,d0
        lea     PTAB.l,a0
        move.l  12(a0,d0.w),d3  ; 値の表
        move.l  8(a0,d0.w),d0
        beq.w   pf_nm
        move.b  d1,d2
        andi.b  #$13,d2
        beq.w   pf_nm
        movea.l d0,a0
        tst.l   d3
        bne.s   pf_mv
        eori.b  #1,(a0)
        bra.s   pf_sv
pf_mv:  movea.l d3,a1           ; いくつかの値: 右・ショット = 次、左 = 前（端で一周）
        move.b  (a0),d2
        btst    #0,d1
        beq.s   pf_up
        subq.b  #1,d2
        bpl.s   pf_st
        move.b  3(a1),d2
        subq.b  #1,d2
        bra.s   pf_st
pf_up:  addq.b  #1,d2
        cmp.b   3(a1),d2
        bcs.s   pf_st
        moveq   #0,d2
pf_st:  move.b  d2,(a0)
pf_sv:  cmpi.b  #PI_EQ,d6       ; 装備の行: 再開のときに装備をやり直す
        bcs.s   pf_s2
        cmpi.b  #PI_MISS,d6
        bcc.s   pf_s2
        move.b  #1,EQ_REQ.l
pf_s2:  tst.b   $203e1a.l       ; NO DEATH / CUBE NO DEATH の無敵はスタートメニューの前回値に残さない
        bne.s   pf_rd
        move.b  MBS_INV.l,V_LINV.l
pf_rd:  movem.l d1/d5,-(a7)
        jsr     PRest.l         ; 項目の数が変わる（INVINCIBLE の ON/OFF）と窓の大きさ・位置も変わるので、いったん戻して描き直す
        bsr.w   PMap
        cmp.b   V_PSEL.l,d6     ; 項目が減ったときに、選んでいる行が外に出ないように
        bhi.s   pf_r2
        clr.b   V_PSEL.l
pf_r2:  jsr     PSave.l
        jsr     PDraw.l
        movem.l (a7)+,d1/d5
        rts
pf_nm:  andi.b  #$18,d5
        bne.s   pf_ok
        btst    #4,d1
        beq.s   pf_ret
pf_ok:  bsr.w   PSelIx
        move.w  d0,d2           ; d2 = 決めた項目（PRest は d2 を使わない）
        jsr     PRest.l
        clr.b   V_PST.l
        clr.b   V_LNL.l         ; CUBE LINE を描き直させる（窓の13段目からは保存していないので）
        cmpi.b  #PI_MISS,d2     ; MISS: 自分で死ぬ（無敵でも。保険は純正どおり）
        bne.s   pf_o2
        clr.b   EQ_REQ.l
        cmpi.b  #1,$203f0b.l    ; NO DEATH では残機を減らさない（先に1つ足しておく）
        bne.s   pf_mi
        move.b  $201050.l,d0
        moveq   #1,d1
        dc.w    $44fc,$0000     ; move #0,ccr
        dc.w    $c101           ; abcd d1,d0
        cmpi.b  #$99,d0
        bcc.s   pf_mi
        move.b  d0,$201050.l
pf_mi:  move.b  #1,$203ed2.l    ; メインの InvChk: 無敵でも死ぬ
        ori.b   #$80,$20101a.l  ; 自機の当たりの印
        moveq   #2,d0
        bra.s   pf_go
pf_o2:  moveq   #2,d0           ; CONTINUE / INVINCIBLE などの行 → 再開
        cmpi.b  #1,d2
        bne.s   pf_go
        moveq   #3,d0           ; GAME OVER
pf_go:  move.b  d0,MBS_PAUS.l
pf_ret: rts
"""

def _noinv(t):
    if NOINV:
        t = t.replace('NOINV_SKIP\n', '        bra.s   ck_sk           ; リリース: INVINCIBLE の行はいつも飛ばす\n')
        t = t.replace('NOINV_DRAW\n', '        tst.b   d7              ; リリース: INVINCIBLE の行は描かない\n        beq.w   da_next\n')
        t = t.replace('NOINV_CUR\n', '        move.b  #1,V_CUR.l      ; リリース: カーソルは MODE から\n')
        t = t.replace('NOINV_GO\n', '        clr.b   $203f20.l        ; リリース: INVINCIBLE は無い（NO DEATH の無敵は下で立てる）\n')
        t = t.replace('NOINV_PM\n', '        cmpi.b  #2,d0           ; リリース: ポーズの INVINCIBLE（PTAB 2）は出さない\n        beq.s   pm_b2\n')
    else:
        t = t.replace('NOINV_SKIP\n', '').replace('NOINV_DRAW\n', '').replace('NOINV_GO\n', '').replace('NOINV_PM\n', '')
        t = t.replace('NOINV_CUR\n', '        clr.b   V_CUR.l\n')
    return t
def source(lab):
    return _noinv(('GRIDCOL = %d\nATTRSELGRID = %d\nATTRDIS = %d\nCUBE0 = %d\nSTG0 = %d\nSTGEX = %d\nCAPI = %d\n' % (GRID_COL, ATTR_SELGRID, ATTR_DIS, CUBE0, STG0, STGEX, CAPI)) + (ENGINE + ENGINE2 + PAUSE.replace('%', '%%')) % {'nitem': NITEM, 'row0': ROW0, 'colcur': COL_CUR, 'collab': COL_LABEL, 'colval': COL_VAL, 'attr': ATTR_TXT, 'attrsel': ATTR_SEL})
