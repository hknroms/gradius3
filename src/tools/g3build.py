"""Gradius III 313 改造ROMビルダー（capstone不要）
- 純正313メイン(945_313.f15 偶数/945_312.e15 奇数) と サブ(945_m09.r17 偶数/945_m08.n17 奇数, R版共通) を読み込み
- パッチ適用（空き領域か期待バイト列を検証）
- サブROM合計をメイン 0x744/0x748 に反映、メイン合計(0x73c/0x740の期待値)を補正バイトで一致させる
- MAME用ROMセット(ディレクトリ)と 実機用ROMファイルを出力
"""
import os, struct, shutil, zipfile, sys
sys.path.insert(0, os.path.dirname(__file__))
import asm68

BASE = os.environ.get('G3BASE', '/tmp/claude-0/-home-claude/57f28419-36f2-5d63-9dbe-6a3976a5a75b/scratchpad')
F15 = f'{BASE}/rom/genuine/313_main/945_313.f15'
E15 = f'{BASE}/rom/genuine/313_main/945_312.e15'
M09 = f'{BASE}/rw/945_m09.r17'   # sub 偶数
M08 = f'{BASE}/rw/945_m08.n17'   # sub 奇数
MAMEZIP = f'{BASE}/rom/gradius3_313_for_MAME.zip'

def il(even, odd): return bytearray(x for p in zip(even, odd) for x in p)

class Rom:
    def __init__(self):
        self.main = il(open(F15,'rb').read(), open(E15,'rb').read())
        self.sub = il(open(M09,'rb').read(), open(M08,'rb').read())
        self.main0 = bytes(self.main); self.sub0 = bytes(self.sub)
        with zipfile.ZipFile(MAMEZIP) as z: self.snd = bytearray(z.read('945_r05.d9'))   # サウンド(Z80)
        self.snd0 = bytes(self.snd)
        self.used = []   # (cpu, start, end, tag)
        self.fillers = {'main': [], 'sub': []}

    def img(self, cpu): return {'main': self.main, 'sub': self.sub, 'snd': self.snd}[cpu]
    def orig(self, cpu): return {'main': self.main0, 'sub': self.sub0, 'snd': self.snd0}[cpu]

    def put(self, cpu, addr, data, tag='', expect=None, free_ok=False):
        im = self.img(cpu); o = self.orig(cpu)
        assert addr + len(data) <= len(o), f'{cpu}:{addr:x}+{len(data)} ROM の終わりを越えた ({tag})'
        cur = bytes(o[addr:addr+len(data)])
        if expect is not None:
            assert cur == bytes(expect), f'{cpu}:{addr:x} expect mismatch {cur.hex()} != {bytes(expect).hex()} ({tag})'
        elif not free_ok:
            # 未使用領域(全部0x00 or 全部0xff)のみ許可
            assert len(set(cur)) == 1 and cur[0] in (0, 0xff), f'{cpu}:{addr:x} not free ({tag}) {cur[:8].hex()}'
        for (c, s, e, t) in self.used:
            if c == cpu and s < addr+len(data) and addr < e:
                raise AssertionError(f'overlap {cpu}:{addr:x}+{len(data)} with {t} ({tag})')
        self.used.append((cpu, addr, addr+len(data), tag))
        im[addr:addr+len(data)] = data

    def asm(self, cpu, org, src, tag='', labels=None, expect=None, free_ok=False):
        b, lab = asm68.assemble(src, org, labels)
        self.put(cpu, org, b, tag, expect=expect, free_ok=free_ok)
        return lab, len(b)

    def finalize(self, outdir, filler_main=None):
        # 1) サブ合計 → メイン 0x744/0x748
        so, se = sum(self.sub[1::2]), sum(self.sub[0::2])
        self.main[0x744:0x748] = struct.pack('>I', so)
        self.main[0x748:0x74c] = struct.pack('>I', se)
        # 2) メイン合計: 期待値 0x73c(e15=奇数側)/0x740(f15=偶数側) を再計算して一致させる（固定点反復）
        #    期待値自身が合計に含まれるので、反復で収束させ、残差は filler(未使用0xff)で微調整
        m = self.main
        fl = filler_main or [(0x3ffc0, 0x3fff0)]
        orig_free = all(bytes(self.main0[lo:hi]) == b'\xff' * (hi - lo) for lo, hi in fl)
        # 調整用バイトは中間値(0x80)から始める（増減どちら向きにも調整できるように）。
        # ※ 無改造(差分なし)ビルドは純正と完全一致させるため、何も書き換えない
        changed = bytes(m) != bytes(self.main0) or True
        if bytes(m) == bytes(self.main0):
            pass
        else:
            assert orig_free, 'filler領域が使用済み'
            for lo, hi in fl:
                for a2 in range(lo, hi): m[a2] = 0x80
            n1, n2 = sum(m[1::2]), sum(m[0::2])
            m[0x73c:0x740] = struct.pack('>I', n1); m[0x740:0x744] = struct.pack('>I', n2)
            for par, a in ((1, 0x73c), (0, 0x740)):
                want = struct.unpack('>I', bytes(m[a:a+4]))[0]
                diff = want - sum(m[par::2])
                for lo, hi in fl:
                    for a2 in range(lo + ((lo + par) % 2), hi, 2):
                        if diff == 0: break
                        if diff < 0 and m[a2] > 0:
                            k = min(m[a2], -diff); m[a2] -= k; diff += k
                        elif diff > 0 and m[a2] < 0xff:
                            k = min(0xff - m[a2], diff); m[a2] += k; diff -= k
                assert diff == 0, 'filler不足'
        # 3) 出力
        os.makedirs(outdir, exist_ok=True)
        mf, me = bytes(self.main[0::2]), bytes(self.main[1::2])
        sf, so_ = bytes(self.sub[0::2]), bytes(self.sub[1::2])
        out = {'945_313.f15': mf, '945_312.e15': me, '945_m09.r17': sf, '945_m08.n17': so_}
        if bytes(self.snd) != self.snd0: out['945_r05.d9'] = bytes(self.snd)
        for n, b in out.items(): open(f'{outdir}/{n}', 'wb').write(b)
        # MAME romset (gradius3) ディレクトリ
        rs = f'{outdir}/mame/gradius3'
        shutil.rmtree(rs, ignore_errors=True); os.makedirs(rs)
        with zipfile.ZipFile(MAMEZIP) as z: z.extractall(rs)
        open(f'{rs}/945_r13.f15', 'wb').write(mf); open(f'{rs}/945_r12.e15', 'wb').write(me)
        open(f'{rs}/945_m09.r17', 'wb').write(sf); open(f'{rs}/945_m08.n17', 'wb').write(so_)
        if '945_r05.d9' in out: open(f'{rs}/945_r05.d9', 'wb').write(out['945_r05.d9'])
        return out

def selfcheck(rom):
    m, s = rom.main, rom.sub
    ok = True
    for par, a in ((1, 0x73c), (0, 0x740)):
        ok &= sum(m[par::2]) == struct.unpack('>I', bytes(m[a:a+4]))[0]
    ok &= sum(s[1::2]) == struct.unpack('>I', bytes(m[0x744:0x748]))[0]
    ok &= sum(s[0::2]) == struct.unpack('>I', bytes(m[0x748:0x74c]))[0]
    return ok
