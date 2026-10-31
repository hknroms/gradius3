"""メインCPU側スタブ（純正313へのパッチ）

置き場所（#34、2026-10-28〜）: メインROMには本当の空きがほとんど無いので、次の空きに「かたまり」ごとに詰めて置く（mainpack.py）。
  1. C = 0x3fd9a〜0x3ffbf（ROM の最後の空き。0x3ffc0〜 は起動画面の文字列、0x3fff0〜 は ROM 合計の微調整）
  2. 地形を掘る跡のマスク（$D4AC〜$DA7D。掘る処理 $D31A が読む）の中の、一度も読まれないバイト（隙間の列）:
     32バイトの行ごとの後ろ14バイト（$D4BE+32n〜$D4CB+32n、n=0〜45）と、最後の行の後ろ $DA7E〜$DB09。
     命令を詰めて隙間の終わりで bra.s で次の隙間へつなぐ。マスクとして読まれるバイトは純正のまま（#6）。
     以前（〜v0.4.17）はマスクの上にコードを置いていた
  3. 共有RAMの空き R1〜R3（$103860〜$1038D3・$103966〜$1039BF・$1039C6〜$103ABD。どちらの ROM からも参照が無く、
     記録でも使われなかった所）。
  4. メインRAM M1 = $40500〜$405DF（スタックの上。起動の途中だけ SSP=$40600 で使い（$405F4 まで）、
     $155E で SSP=$40500 にした後は使われない）・M2 = $42E78〜$42FFF（$42E00〜$42E75 の変数の後ろ。参照なし）・
     M3 = $43F70〜$43FFF（ハイスコア表 $43F00〜$43F63 と並べ替えの作業場所 〜$43F6D の後ろ。参照なし）。
     どれも起動時の消去のほかは書かれない（記録で確認）。
  3・4 はサブが起動時に ROM から写す（mod_sub の RamCopy）。メインRAMにはサブが書けないので、R3 を受け渡し場所にして
     240B ずつ渡す。印 RAMMAGIC（共有RAM）で順番を合わせる: 偶数 2k → サブが k 番目を R3 に置いて 2k+1 →
     メインが写して 2k+2 → …全部渡したら、サブが R1〜R3 の中身を置いて MAGICVAL。
     メインは毎フレーム StubIn（フレームの処理の最初のフック）の最後で印を見て、MAGICVAL でなければ LoadStep で
     1回分ずつ写す（その間は RAM のコードを呼ばない。起動直後の数フレームで、RAM のコードを呼ぶ場面＝ゲームの開始・
     デモ・START などはまだ来ない）。120 フレームたっても終わらなければ LoadW で終わるまで待つ。
     起動直後のフレームの進み方は純正と同じ（待たない）。
     起動時（$119A・$11E4・$1202）にゲームがメインRAM・共有RAMを消すので、リセットのたびに最初からやり直しになる
"""
import os
BOSSRUSH = os.environ.get('BOSSRUSH') == '1'          # BOSS RUSH モード（v0.5.0 から外した。後の版で戻す）。mod_menu と同じ
EXTRA_AREAS = os.environ.get('EXTRA_AREAS') == '1'
ND_FRAMES = 36000        # NO DEATH（#36）の1クレジットの時間（フレーム。10分）
ND_LEFT = 0x103e10       # NO DEATH の残りフレーム.l（共有RAM。以前ボスラッシュの表を置いていた所）
ND_FLAG = 0x103e1a       # NO DEATH の印（共有RAM。MODE 1=NO DEATH と MODE 3=CUBE NO DEATH で立つ。#39）
SE_REQ = 0x103e24        # 効果音の依頼（サブが音の番号を置き、メインの StubIn が鳴らして 0 に戻す。#60・#62）
ND_BONUS = 0x103e20      # CUBE RUSH の残機ボーナス（+5 か +2。サブがメニュー確定時に置く。#40・#70）
ND_TIME = 0x103e1c       # NO DEATH の時間（.l フレーム。ディップスイッチ #40 で 36000 か 18000）
MB = 0x103f00           # メールボックス（共有RAM。サブ側は 0x203f00）
# オフセット
O_P1, O_SYS, O_UNLOCK, O_REQ, O_DONE, O_KIND, O_PAUSE, O_MODRUN = 0, 1, 2, 3, 4, 5, 6, 7
O_STAGE, O_LOOP, O_AREA, O_MODE, O_BEGIN = 8, 9, 10, 11, 12

RAMMAGIC = 0x103abe     # 共有RAMのコードを写し終えた印（サブが最後に書く。起動時にゲームが共有RAMを消すと 0 に戻る）
MAGICVAL = 0x4d4f
LCNT = 0x103abc          # 写している間のフレーム数（R3 の最後の語。写し終えたら使わない）
REGIONS = [('C', 0x3fd6a, 0x3ffc0, 'rom'),   # 2026-10-30 拡張: $3fd6a〜$3fd99 の 48B はデモ入力の後ろのゼロ・参照なし（TECH.md「ROM の空き」の候補を使用）
           ('R1', 0x103860, 0x1038d4, 'shr'), ('R2', 0x103966, 0x1039c0, 'shr'),
           # R3（$1039C6〜$103ABB）は受け渡し場所 STAGE だけに使う。コードを置くと起動時の ROM CHECK でサブ（N17・R17）が BAD になった（#101、2026-11-01）
           ('M1', 0x40500, 0x405e0, 'mrm'), ('M2', 0x42e78, 0x43000, 'mrm'), ('M3', 0x43f70, 0x44000, 'mrm')]
# #41 テストモードの小機能のうち消すもの（2026-10-31 管理者：CHARACTER ROM CHECK・COLOR TEST・COIN COUNTER TEST）。
# 小機能の表 $808（7つ）の消す番号を「次の小機能へ進むだけ」の短い処理（TM_SKIP、0 番の場所の先頭 10B）に向け、残りを改造のコードの置き場所にする。
# 戻すときはこの一覧から外す（後で SCREEN CHECK(1) なども、ここに足すだけで消せる。場所は TM_BLOCKS に足す）。調べ方：src/lua/research/testmode/
TM_BLOCKS = {0: (0x824, 0x9ae), 2: (0x9ec, 0xafa), 4: (0xb82, 0xcb4)}   # 小機能の番号: そのコードの範囲（次の小機能の入口まで。表の外から呼ばれない）
TM_REMOVE = [0, 2, 4]
TM_SKIP = 0x824          # 消した小機能の代わり: addq.b #1,$40001.l / rts（10B）。0 番を消す前提（0 番の場所の先頭に置く）
assert 0 in TM_REMOVE
for _n in TM_REMOVE:
    _lo, _hi = TM_BLOCKS[_n]
    REGIONS.append(('X%d' % _n, _lo + (10 if _lo == TM_SKIP else 0), _hi, 'rom'))
STAGE = 0x1039c6        # メインRAMへ写す中身の受け渡し場所（R3 を借りる。先頭 6バイト = 写す先.l・ロング数-1.w）
STAGEMAX = 240          # 1回に渡す大きさ（R3 248B − 見出し6B 以下の4の倍数）
STREAM = [('S%02d' % n, 0xd4be + 32 * n, 0xd4cc + 32 * n) for n in range(46)] + [('T', 0xda7e, 0xdb0a)]
FILLER = (0x3fff0, 0x40000)   # ROM 合計の微調整（ROM の最後の16バイト。どこからも読まれない）

CONSTS = f"""
MB      = ${MB:x}
MB_P1   = ${MB+O_P1:x}
MB_SYS  = ${MB+O_SYS:x}
MB_UNLK = ${MB+O_UNLOCK:x}
MB_REQ  = ${MB+O_REQ:x}
MB_DONE = ${MB+O_DONE:x}
MB_KIND = ${MB+O_KIND:x}
MB_PAUS = ${MB+O_PAUSE:x}
MB_RUN  = ${MB+O_MODRUN:x}
MB_STG  = ${MB+O_STAGE:x}
MB_LOOP = ${MB+O_LOOP:x}
MB_AREA = ${MB+O_AREA:x}
MB_MODE = ${MB+O_MODE:x}
MB_BEG  = ${MB+O_BEGIN:x}
MB_LIVES = $103f0d
MB_TYPE  = $103f0f
MB_SPD   = $103f10
MB_EMIS  = $103f11
MB_EDBL  = $103f12
MB_ELSR  = $103f13
MB_OPT   = $103f14
MB_SHD   = $103f15
MB_PMIS  = $103f17
MB_PSHOT = $103f18
MB_PSHON = $103f19
MB_PEND  = $103f1a
MB_INV   = $103f20
ND_LEFT  = ${ND_LEFT:x}
ND_FLAG  = ${ND_FLAG:x}
ND_TIME  = ${ND_TIME:x}
ND_BONUS = ${ND_BONUS:x}
SE_REQ   = ${SE_REQ:x}
ND_FRAMES = {ND_FRAMES}
RAMMAGIC = ${RAMMAGIC:x}
MAGICVAL = ${MAGICVAL:x}
LCNT    = ${LCNT:x}
STAGE   = $1039c6
"""

# ---- かたまり（名前, ソース, 'rom'=ROM に置く / 'any'=どこでも） ----
CHUNKS = []
ANY = {'rom', 'shr', 'mrm'}
# 'rom' = ROM のひと続きの空き（C）だけ / 'any' = どこでも（隙間の列を除く。毎フレーム通る処理など）
# 隙間の列（つなぎの bra.s で少し遅くなる）には、めったに通らない処理だけを置く（COLD の順に入るだけ）
def chunk(name, src, where='any'):
    CHUNKS.append((name, src, {'rom'} if where == 'rom' else set(ANY) if where == 'any' else where))
COLD = ['LoadW', 'EdLR', 'TypeBeg', 'TypeGrey', 'ApplyStart', 'ApplyStage', 'NextStg', 'NextPos', 'BossSet', 'PendB',
        'CmdCnt', 'Command', 'AreaTbl', 'EvPtr', 'Die', 'ShPal', 'StageHook', 'ModState', 'EndSkip', 'PalCopy']

# 毎フレーム（フレームの処理の最初。0x1d1e の jsr $33b8 を置き換え）: 入力の写し・スコアの描き直し・見出しの色
chunk('StubIn', """
StubIn: jsr     $33b8.w
        move.b  $c8003.l,d0
        not.b   d0
        move.b  d0,MB_P1.l
        addq.w  #1,$103e0e.l    ; #100 ゲームの処理の回数（サブの処理落ちメーターが画面の描き直しの回数と比べる）
        jsr     Lock.l          ; #62 解除のコマンド（d0 = P1 正論理）
        move.b  $c8001.l,d0
        not.b   d0
        move.b  d0,MB_SYS.l
        move.b  $d0001.l,$103814.l  ; DSW1 をそのまま共有RAMへ（サブはディップスイッチを読めない。#32・#31 で使う。負論理: OFF=1）
        cmpi.b  #1,MB_PAUS.l    ; ポーズ中はフレームカウンタを進めない（キューブの並びがポーズでずれないように）
        bne.s   si_np
        subq.w  #1,$40032.l
si_np:  move.b  SE_REQ.l,d7     ; 効果音の依頼（サブが置く。#60 キューブが反応する瞬間・#62 解除/ロックの成立）→ 音の命令の列へ（$2b0c）
        beq.s   si_ns
        clr.b   SE_REQ.l
        jsr     $2b0c.w
si_ns:  tst.b   $103ed0.l       ; サブからスコアの描き直しの依頼（CUBE INFO を OFF にした／キューブがくっついて点が入った）
        beq.s   ms_nr
        clr.b   $103ed0.l
        movem.l d0-d7/a0-a6,-(a7)
        jsr     ScoreHk.l
        movem.l (a7)+,d0-d7/a0-a6
ms_nr:  tst.b   MB_RUN.l        ; 改造プレイ中（= RAM のコードは写し終えている）→ 見出しの色
        bne.s   si_hp
        cmpi.w  #MAGICVAL,RAMMAGIC.l ; RAM の改造のコードがまだ無い（起動直後）→ 1回分ずつ写す
        bne.s   si_ld
        rts
si_hp:  jmp     HudPal2.l
si_ld:  jmp     LoadStep.l
""", 'rom')
# RAM のコードを待つ（ウォッチドッグを叩きながら。約8秒たっても終わらなければ叩くのをやめてリセットさせる）
chunk('LoadW', """
LoadStep:                       ; 起動直後の毎フレーム（StubIn から）: サブが置いた1回分を写す。2秒たっても終わらなければ LoadW で待つ
        addq.w  #1,LCNT.l
        cmpi.w  #120,LCNT.l
        bcc.s   LoadW
        move.w  RAMMAGIC.l,d1
        bsr.s   lw_cp
        rts
LoadW:  move.l  #$140000,d0     ; 終わるまで待つ（ウォッチドッグを叩きながら。約8秒で叩くのをやめてリセットさせる）
lw_l:   move.b  #1,$e0000.l
        move.w  RAMMAGIC.l,d1
        cmpi.w  #MAGICVAL,d1
        beq.s   lw_r
        bsr.s   lw_cp
        subq.l  #1,d0
        bne.s   lw_l
lw_h:   bra.s   lw_h
lw_cp:  btst    #0,d1           ; 奇数: サブが受け渡し場所に1回分を置いた → 写して次の番号（偶数）を返す
        beq.s   lw_r
        lea     STAGE.l,a0
        movea.l (a0)+,a1
        move.w  (a0)+,d2
lw_c:   move.l  (a0)+,(a1)+
        dbf     d2,lw_c
        addq.w  #1,d1
        move.w  d1,RAMMAGIC.l
lw_r:   rts
""", {'rom'})

# 残機の絵（純正 $1a72。表 $15ce と $17fe の jsr から）: STAGE DISP 表示中（#30）はサブが数字で描くので描かない
chunk('LivHk', """
LivHk:  tst.b   $1039c5.l
        bne.s   lh_r
        jmp     $1a72.w
lh_r:   rts
""", 'rom')

chunk('HookStart', """
HookStart:
        clr.b   MB_RUN.l        ; アトラクト中は改造プレイ中フラグを落とす
        tst.b   MB_UNLK.l
        beq.s   hs_norm
        move.w  $40042.l,d0
        not.w   d0
        and.w   $40040.l,d0
        andi.w  #$18,d0
        beq.s   hs_norm
        tst.b   $4004a.l
        bne.s   hs_cred
        move.b  $40034.l,d1
        beq.s   hs_norm
hs_cred:
        moveq   #1,d2
        btst    #3,d0
        bne.s   hs_k
        moveq   #2,d2
        tst.b   $4004a.l
        bne.s   hs_k
        cmpi.b  #2,$40034.l
        bcs.s   hs_norm
hs_k:
        move.b  $c8003.l,d1
        moveq   #1,d3
        btst    #2,d1
        beq.s   hs_go
        moveq   #2,d3
        btst    #3,d1
        bne.s   hs_norm
hs_go:
        moveq   #-$5f,d7        ; メニューの曲: 未使用曲 A1 を鳴らす（音量はサウンドROM側で半分に）
        jsr     $2b0c.w
        move.b  d3,MB_REQ.l
        move.b  d2,MB_KIND.l
        clr.b   MB_DONE.l
        move.b  #3,$40005.l
        ori     #1,ccr
        rts
hs_norm:
        jmp     $2968.w
""", 'rom')

# 新トップ状態3: メニュー実行中（サブCPUが描画・操作）。確定/キャンセルを待つ
chunk('ModState', """
ModState:
        jsr     PalCopy.l       ; メニューの背景の色（サブが用意したら写す）
        move.l  #$6000,$1038e8.l ; スクロール位置 0 に固定（レジスタ値 = 変数-0x6000 を毎フレーム反映する処理がある）
        move.l  #$6000,$1038f0.l
        clr.l   $1038ec.l
        clr.l   $1038f4.l
        clr.w   $10393c.l
        clr.w   $10393e.l
        move.b  MB_DONE.l,d0
        beq.s   ms_rts
        cmpi.b  #2,d0
        beq.s   ms_cancel
        move.b  $40034.l,d1
        cmpi.b  #2,MB_KIND.l
        beq.s   ms_p2
        moveq   #1,d7
        jsr     $2a76.w
        clr.b   $40080.l
        bra.s   ms_begin
ms_p2:  moveq   #2,d7
        jsr     $2a76.w
        move.b  #1,$40080.l
ms_begin:
        jsr     $29c0.w
        jsr     ApplyStart.l
        clr.b   MB_REQ.l
        clr.b   MB_DONE.l
ms_rts: rts
ms_cancel:
        clr.b   $40005.l
        clr.b   MB_REQ.l
        clr.b   MB_DONE.l
        rts
""")
# 新状態表（0x1e58の代わり）
chunk('StateTbl', """
StateTbl:
        dc.l    $1e6c, $1e64, $28ce, ModState
""", 'rom')          # 毎フレーム読まれる（RAM のコードを写し終える前から）ので ROM

# メニュー確定後（0x29c0 で通常のゲーム開始処理を済ませた直後）に呼ばれる
chunk('ApplyStart', """
ApplyStart:                     ; メニュー確定直後: 改造プレイ開始の印だけ付ける（面・周回は ApplyStage で後から）
        move.b  #1,MB_RUN.l
        move.b  #7,MB_PEND.l
                                ; $103f38・START 押下時間 $103f21・装備コマンドの残り回数 $103f22 はサブがメニュー確定時に置く（#70・#63）
as_1:   move.b  ND_BONUS.l,d1   ; d1 = CUBE RUSH 残機ボーナス（sk_set で使う）。ND_LEFT・ND_TIME と一緒にサブがメニュー確定時に DSW1 bit7 から作る（#40。メインの空きを作るためサブに移した #70）
        lea     $101000.l,a0
        bsr.s   sk_set
        lea     $101080.l,a0
sk_set: cmpi.b  #2,MB_MODE.l    ; 残機はディップスイッチどおり。キューブラッシュはそれに +5(10分) か +2(5分) (#40)
        bne.s   sk_sr
        tst.b   $50(a0)
        beq.s   sk_sr
        move.b  $50(a0),d0      ; 残機は BCD（d1 は呼び出し元から渡される）
        dc.w    $44fc,$0000     ; move #0,ccr
        dc.w    $c101           ; abcd d1,d0
        move.b  d0,$50(a0)
sk_sr:  rts
""")

# 面・周回・エリアの反映。装備選択画面が終わり、面の準備(状態2)に入る瞬間に1回だけ呼ばれる
# （先に書くと、周回≠0 のときゲームが選択画面を飛ばしてしまうため）
chunk('ApplyStage', """
ApplyStage:
        move.b  MB_STG.l,d0
        subq.b  #1,d0           ; 面1..10 → 内部 0..9 (11,12=隠し面 → 戻り先は10面)
        cmpi.b  #9,d0
        bls.s   as_nb
        moveq   #9,d0
as_nb:  move.b  d0,$101051.l
        move.b  d0,$1010d1.l
        move.b  MB_LOOP.l,d0
        subq.b  #1,d0
        add.b   d0,d0
        move.b  d0,$101063.l
        move.b  d0,$1010e3.l
; エリア(復活地点)指定: 0x4ce8 は「$101063 bit0≠0 のとき $101052(進行度)以下で最後のエリア開始点」を使う
                                ; 進行度はサブCPUがビルド時の表から計算して MB+$1e に置く
        ori.b   #1,$101063.l    ; 「再開」扱い: 1周目の新規開始で面が1面に戻される処理(0x37c6)を避ける
        ori.b   #1,$1010e3.l
        move.w  $103f1e.l,d6
        beq.s   sa_ret
        move.w  d6,$101052.l
        move.w  d6,$1010d2.l
sa_ret: rts
""")

# ---- 改造モードのポーズ(プレイ中 START)。戻り d0≠0 ならこのフレームのゲーム処理を止める ----
# MB_PAUS: 0=通常 1=ポーズ中(サブがメニュー表示) 2=再開 3=ゲームオーバー
chunk('PauseChk', """
PauseChk:                       ; 戻り d0: 0=通常 1=止める 2=装備コマンド実行
        move.b  MB_PAUS.l,d0
        beq.s   pc_chk
        cmpi.b  #2,d0
        bcs.w   pc_frz
        beq.s   pc_res
        clr.b   MB_PAUS.l       ; 3: GAME OVER（ポーズの GAME OVER・NO DEATH の時間切れ）。いきなり状態8にすると、物体が残り・GAME OVER の表示や
        clr.b   $101050.l       ;   ネーム入れの準備が飛ばされていた（#84）。→ 残機を最後の1機にして、無敵でもやられるようにして続ける。
        clr.b   $1010d0.l       ;   やられた後は純正どおりのゲームオーバー（爆発・GAME OVER・ネーム入れ）になる
        lea     $101000.l,a0
        tst.b   $4007f.l        ; いま遊んでいる側（0=1P 1=2P）
        beq.s   pc_g1
        lea     $101080.l,a0
pc_g1:  move.b  #1,$50(a0)
        move.b  #1,$103ed2.l    ; InvChk: 無敵でもやられる（ポーズの MISS と同じ）
        ori.b   #$80,$1a(a0)    ; 自機の当たりの印
        moveq   #0,d0
        rts
pc_res: clr.b   MB_PAUS.l
        jsr     EqApply.l       ; ポーズで装備を変えていたら、やり直す
        jsr     HtApply.l       ; #92 ポーズの HUNTER TIME
        moveq   #0,d0
        rts
pc_chk: lea     $103f21.l,a0    ; 1P START: 短く押す=装備コマンド / 約1秒押し続ける=ポーズ
        btst    #3,MB_SYS.l
        beq.s   pc_up
        addq.b  #1,(a0)
        cmpi.b  #60,(a0)
        bne.s   pc_no
        move.b  #1,MB_PAUS.l
pc_frz: moveq   #1,d0
        rts
pc_up:  move.b  (a0),d1
        clr.b   (a0)
        tst.b   d1
        beq.s   pc_no
        cmpi.b  #60,d1
        bcc.s   pc_no
        moveq   #2,d0
        rts
pc_no:  moveq   #0,d0
        rts
""")

# ---- #92 ポーズの HUNTER TIME（サブが $103E2B に 0=OFF / 1〜100=0〜99秒 を置く）: 閉じてから何秒後にオプションハンターを出すか ----
# 純正（$12696〜）は $42E70 からオプションの数だけ毎フレーム引き、借りが出たら出す（$42E72≠0 なら引かずにすぐ出す）。
# n 秒 → $42E70 = n×60×オプションの数（オプションなしは1つ分＝付けたら数え始める）。0 秒 → $42E72=1。1周目の最初の面など純正が出さない所では出ない
chunk('HtApply', """
HtApply: moveq  #0,d0
        move.b  $103e2b.l,d0
        beq.s   ht_r
        clr.b   $103e2b.l
        subq.w  #1,d0
        bne.s   ht_t
        move.b  #1,$42e72.l     ; 0 秒: すぐ出す。次の時間は純正が出したときと同じ $FFFF から
        move.w  #$ffff,$42e70.l
        rts
ht_t:   mulu    #60,d0
        moveq   #7,d1
        and.b   $101068.l,d1
        bne.s   ht_m
        moveq   #1,d1
ht_m:   mulu    d1,d0
        move.w  d0,$42e70.l
ht_r:   rts
""")

# ---- ポーズで装備を変えた（無敵のとき。サブが EQ_REQ $103e14 を立て、+1〜+5 に SPEED MISSILE DOUBLE/LASER OPTION SHIELD を置く）----
# いったん何もない状態（死んで出直したときと同じ）にしてから、装備コマンドと同じ Use で付け直す（減らすこともできる）
chunk('EqApply', """
EqApply: tst.b  $103e14.l
        beq.w   ea_r
        clr.b   $103e14.l
        movem.l d0-d7/a0-a6,-(a7)
        lea     $101100.l,a0    ; オプション（$50 ずつ4つ）を消す
        moveq   #$4f,d0
ea_c1:  clr.l   (a0)+
        dbf     d0,ea_c1
        lea     $101f60.l,a0    ; シールドを消す
        moveq   #$f,d0
ea_c2:  clr.l   (a0)+
        dbf     d0,ea_c2
        lea     $101000.l,a0
        clr.w   $68(a0)         ; 武器・スピード（出直したときと同じ。$7732）
        clr.b   $6b(a0)
        clr.w   $6c(a0)
        move.w  #$100,$2c(a0)
        jsr     $89b0.l         ; パワーアップの枠をタイプの初期値に（$896c の途中から。エディットの表は書かない）
        lea     $101000.l,a2
        lea     $101f60.l,a3
        lea     $103e15.l,a4
        moveq   #1,d3           ; SPEED
        move.b  (a4)+,d4
        jsr     Use.l
        moveq   #2,d3           ; MISSILE
        move.b  (a4)+,d4
        jsr     Use.l
        moveq   #2,d3           ; DOUBLE(1→枠3) / LASER(2→枠4)
        move.b  (a4)+,d4
        beq.s   ea_o
        add.b   d4,d3
        moveq   #1,d4
        jsr     Use.l
ea_o:   moveq   #5,d3           ; OPTION
        move.b  (a4)+,d4
        jsr     Use.l
        moveq   #6,d3           ; SHIELD
        move.b  (a4)+,d4
        jsr     Use.l
        movem.l (a7)+,d0-d7/a0-a6
ea_r:   rts
""")

# ---- 隠しメニューの解除/ロック (毎フレーム, d0=P1 正論理) ---- （LOCK_SUSPEND の間は入れない）
# 解除: 上+A → 全部離す → 下+A   ロック: 下+A → 離す → 上+A   (各3秒以内, プレイ中以外)。放置300秒で自動ロック
# MB+$3a 段階 / +$3b 種類(1=解除,0=ロック) / +$3c 残り時間 / +$3e 最後の操作時刻
SRC_LOCK = """
Lock:   lea     $103f3a.l,a0
        cmpi.b  #2,$40005.l
        bcc.w   lk_act
; 解除/ロックのコマンド (各段階3秒以内):
;   段階0: レバー上(下)＋A がそろう → 1: 全部離す → 2: レバー下(上)＋A がそろう → 3: 全部離す → 成立
;   レバーとボタンを押す順番・同時押しは問わない。上から始めると解除、下から始めるとロック
        andi.b  #$1f,d0
        move.b  (a0),d1
        beq.s   lk_0
        subq.b  #1,2(a0)
        beq.s   lk_clr
        btst    #0,d1           ; 段階1・3 = 離すのを待つ
        beq.s   lk_2
        tst.b   d0
        bne.s   lk_idle
        cmpi.b  #3,d1
        bne.s   lk_nx
        move.b  1(a0),MB_UNLK.l
        clr.w   4(a0)           ; 放置カウンタ
        bra.s   lk_clr
lk_2:   moveq   #$18,d3         ; 段階2: 最初と逆の方向＋A
        tst.b   1(a0)
        bne.s   lk_t
        moveq   #$14,d3
lk_t:   cmp.b   d3,d0
        bne.s   lk_idle
lk_nx:  addq.b  #1,(a0)
        move.b  #180,2(a0)
        bra.s   lk_idle
lk_0:   moveq   #1,d2
        cmpi.b  #$14,d0
        beq.s   lk_s
        moveq   #0,d2
        cmpi.b  #$18,d0
        bne.s   lk_idle
lk_s:   move.b  d2,1(a0)
        bra.s   lk_nx
lk_clr: clr.b   (a0)
lk_idle:                        ; 300秒自動ロック(遊んでいない間)
        tst.b   MB_UNLK.l
        beq.s   lk_r
        addq.w  #1,4(a0)        ; 放置フレーム数(ゲームのフレームカウンタはアトラクト一巡で0に戻るため自前で数える)
        cmpi.w  #18000,4(a0)    ; 300秒
        bcs.s   lk_r
        clr.b   MB_UNLK.l
lk_r:   rts
lk_act: clr.b   (a0)
        clr.w   4(a0)
        rts
"""

# スコア表示(0x180a: 2P→HI→1P の順に3つ描く)の入口: キューブラッシュで CUBE INFO を ON にしている間は 1P だけ描く（HI・2P の場所にキューブの情報）。STAGE DISP 中は 2P の場所だけ描かない
chunk('ScoreHk', """
ScoreHk: moveq  #2,d0           ; 描く数−1（2=2P・HI・1P、純正の $180a と同じ）
        sub.b   $1039c5.l,d0    ; STAGE DISP 表示中（#30。サブが 0/1 を置く）: 1 = HI と 1P だけ（2P の場所に出すので）
        tst.b   $103ed1.l       ; サブが「CUBE INFO 表示中」としたとき: 1P だけ
        beq.s   sk_go
        moveq   #0,d0
sk_go:  jmp     $180e.w
""", 'rom')
# ---- 開始時のハンターの設定（PlayHook から） ----
chunk('PendB', """
PendB:  move.b  $103f1b.l,d0    ; HUNTER NEXT (0=そのまま, 1..3 → $42e73=0..2)
        beq.s   pb_h1
        subq.b  #1,d0
        move.b  d0,$42e73.l
pb_h1:  rts                     ; （HUNTER TIME は廃止。装備コマンドの後の1回目を出さない方式に）
""")
# ---- キューブラッシュ（改造プレイ）の点数はハイスコア・ランキングに入れない ----
chunk('HiRank', """
CkCR:   tst.b   MB_RUN.l        ; 戻り: eq = ハイスコアに入れない改造プレイ（#35 2026-10-31 管理者：入るのはメニューの MODE が NORMAL のときだけ。
        beq.s   ck_n            ;   NO DEATH の3つ・RESPAWN・キューブの2つ・ボスラッシュは入れない。START だけのプレイは今までどおり入る）
        tst.b   MB_MODE.l       ; 動いているときの MODE（0 普通・1 NO DEATH・2 キューブ・4 ボスラッシュ）
        bne.s   ck_e
        cmpi.b  #1,$103f3e.l    ; その場復活（RESPAWN）: 1 なら eq
        rts
ck_e:   cmp.b   d0,d0           ; Z=1
        rts
ck_n:   cmpi.b  #1,MB_RUN.l
        rts
; 0x197e の cmp.l $40058.l,d7 の置き換え（点数加算後のハイスコア更新）: キューブラッシュなら更新しない（C=1）
HiHk:   bsr.s   CkCR
        bne.s   hh_n
        ori     #1,ccr
        rts
hh_n:   cmp.l   $40058.l,d7
        rts
; 0x226c4 の move.l $101054.l,d0 の置き換え（ゲームオーバー後のランキング判定）: キューブラッシュなら 0点として扱う
RankHk: move.l  $101054.l,d0
        bsr.s   CkCR
        bne.s   rh_r
        moveq   #0,d0
rh_r:   rts
""")
# 見出しの暗めの色（F面パレット6・ゲームでは未使用）: 改造プレイ中は毎フレーム入れる
chunk('HudPal', """
HudPal: tst.b   MB_RUN.l
        beq.s   hp_r
HudPal2: lea    $103dec.l,a0    ; パレット6 の 6〜15番（見出しの灰色・CUBE LINE の色。サブが共有RAMに置く）
        lea     $800cc.l,a1
        moveq   #9,d1
hp_6:   move.w  (a0)+,(a1)+
        dbf     d1,hp_6
        tst.b   $103ed4.l       ; CUBE COLOR 有効: 飛んでくるキューブの色（サブが共有RAMに置いた5色分のパレット）を写す
        beq.s   hp_r
        lea     $103cf0.l,a0    ; 共有RAMの未使用域（0x103cf0〜0x103deb: パレット9つ分の 4〜15番の色。0x103cb0〜 は死んだときにゲームが使う）
        moveq   #8,d2
hp_p:   movea.l (a0)+,a1
        moveq   #11,d1
hp_w:   move.w  (a0)+,(a1)+
        dbf     d1,hp_w
        dbf     d2,hp_p
hp_r:   rts
""")
# ---- 敵出現表ポインタ ($42e00) の補正 (0x154aa の move.l a6,$42e00 を置換) ----
# 改造プレイ・10面(マップ13)・X<0x780(ボスラッシュ区間) か X≥0x2500（脱出 ❹）のときだけ「X 以上の最初のイベント」から始める
# (ゲーム本来の X/0x300 刻みの索引だと、ボス直前から始めたときにボスの出現イベントを取りこぼす/前のボスが出る)
chunk('EvPtr', """
EvPtr:  tst.b   MB_RUN.l
        beq.s   ev_st
        cmpi.b  #13,$1039c0.l
        bne.s   ev_st
        move.l  $1038de.l,d0
        lsr.l   #8,d0
        cmpi.w  #$780,d0
EVESC
ev_sc:  movea.l #$252d4,a6
ev_lp:  cmp.w   (a6),d0
        bls.s   ev_st
        lea     10(a6),a6
        bra.s   ev_lp
ev_st:  move.l  a6,$42e00.l
        rts
""")
CHUNKS[-1] = (CHUNKS[-1][0], CHUNKS[-1][1].replace('EVESC', """        bcs.s   ev_sc
        cmpi.w  #$2500,d0       ; 脱出（❹）から: ゲームの索引は $2600 から先が無く、表の外を指して止まる（#21）
        bcs.s   ev_st""" if EXTRA_AREAS else """        bcc.s   ev_st"""), CHUNKS[-1][2])

# 改造プレイの START 表示（状態2の2フレーム目から）: 元の処理の後で、パレットの出来事の処理（$E318。純正はプレイ中だけ）も回す。
# 面の途中から始めると、開始位置までのパレットの出来事がプレイの最初のフレームでまとめて実行されるので、START 表示の間は
# 前の画面のパレットが残って地形などの色が化けていた（#20）。通常プレイ（メニューを出さない）は純正どおり
# その後で、地形・背景のパレット（$20〜$27・$30〜$37）を 0 にする（$414E。純正が死んで再開するとき $3B74 で呼ぶのと同じ処理）。
# 純正の「死んで再開」は START 表示の間これらが 0 のままなので、描きかけの地形が見えず真っ黒。プレイに入ると（状態4で
# $400a0 を 0 に戻すので）開始位置までのパレットの出来事がプレイの2フレーム目（$E428）にまとめて入り直す（#20 の続き）。
# ただし最初の START（MB_PEND のその人の bit がまだ立っている）で面の最初（進行度 0）のときは今までどおり（純正の
# メニューを出さない START と同じく星が見える）。死んで再開は面の最初でも 0 にする（ShPal の $E318 が埋め直すので）
chunk('ShPal', """
ShPal:  jsr     $3790.w
        jsr     $e318.l
        move.b  $4007f.l,d0     ; 0=1P 1=2P
        btst    d0,MB_PEND.l    ; 開始時の設定がまだ（= その人の最初の START）
        beq.s   sp_z
        tst.w   $103f1e.l       ; メニューで選んだ開始位置（0 = 面の最初）
        beq.s   sp_r
sp_z:   jmp     $414e.w
sp_r:   rts
""")
# Z=0 なら無敵（改造プレイ中かつ INVINCIBLE=ON）
chunk('Die', """
InvChk: tst.b   $103ed2.l       ; キューブラッシュの区間が終わった → 無敵でも1機減らす（サブが立てる）
        bne.s   ic_f
        tst.b   MB_RUN.l
        beq.s   ic_r
        tst.b   $103817.l       ; #35 その場復活の後の無敵（サブが減らす）
        bne.s   ic_r
        tst.b   MB_INV.l
ic_r:   rts
ic_f:   cmp.b   d0,d0           ; Z=1（無敵ではない）
        rts
; 0x7bc4 / 0xae22 の move.b #1,$400a2.l を置き換え（ここから先が死亡処理）
DieA:   bsr.s   InvChk
        bne.s   da_inv
        move.b  #1,$400a2.l
        rts
da_inv: addq.l  #4,sp
        clr.w   $1a(a0)
        jmp     $7bf4.w
DieB:   bsr.s   InvChk
        bne.s   db_inv
        move.b  #1,$400a2.l
        rts
db_inv: addq.l  #4,sp
        clr.w   $1a(a0)
        jmp     $ae52.l
""")
# #35 その場復活: 0x7c88 の move.b #2,$400a2.l（爆発が終わった → やり直しの流れへ）を置き換え。
# サブが毎フレーム $103816 に「その場復活してよいか」を置く（改造プレイ・MODE が RESPAWN か RESPAWN NO DEATH・1人・残機2以上）。
# よいときは、やり直しに入らず、残機を1つ減らして（純正の $3B00 と同じ）自機だけ出し直す（$7732 で左から登場。
# 装備は #101 の決まりで1つだけ失って付け直す）。状態5（プレイ中）のまま続くので、スクロール・地形・敵はそのまま。4面（3D）は $AE8E を通るので対象外
chunk('Rsp', """
Rsp:    tst.b   $103816.l
        bne.s   rp_go
        move.b  #2,$400a2.l
        rts
rp_go:  move.b  $50(a0),d7
        moveq   #1,d6
        andi.b  #0,ccr
        dc.w    $8f06           ; sbcd d6,d7
        move.b  d7,$50(a0)
        ori.b   #1,$63(a0)
        ; #101 死ぬ前の装備から1つだけ失う（上から最初に当てはまるもの）:
        ;   オプション−1 / ダブル・レーザー→ノーマル / ミサイルなし / ゼロ速＋ゲージを SPEED（保険）。シールドは毎回なくなる
        moveq   #0,d0
        move.b  $68(a0),d2      ; d2 = オプションの数
        andi.b  #7,d2
        move.b  $69(a0),d3      ; d3 = スピードの段階
        andi.b  #$1f,d3
        moveq   #0,d4           ; d4 = ショット（0=ノーマル 3=ダブル 4=レーザー）: ゲージの「取った」印（$76・$78 = $08xx）で見る
        cmpi.b  #8,$76(a0)      ;   （$6C の値はウェポンの型で違うので、純正の $8A5C と同じ結果になる印を使う）
        bne.s   rp_l
        moveq   #3,d4
rp_l:   cmpi.b  #8,$78(a0)
        bne.s   rp_m
        moveq   #4,d4
rp_m:   moveq   #0,d5           ; d5 = ミサイル（$6D≠0 なら1）
        tst.b   $6d(a0)
        beq.s   rp_n
        moveq   #1,d5
rp_n:
        move.b  $6a(a0),d6      ; d6 = カプセルゲージの位置
        tst.b   d2
        beq.s   rp_1
        subq.b  #1,d2
        bra.s   rp_k
rp_1:   tst.b   d4
        beq.s   rp_2
        moveq   #0,d4
        bra.s   rp_k
rp_2:   tst.b   d5
        beq.s   rp_3
        moveq   #0,d5
        bra.s   rp_k
rp_3:   moveq   #0,d3
        moveq   #1,d6
rp_k:   lea     -8(a7),a7       ; 装備コマンドと同じ並び [SPEED,MISSILE,DOUBLE,LASER,OPTION,SHIELD,下げる印] ＋ゲージ
        clr.l   (a7)
        clr.l   4(a7)
        move.b  d3,(a7)
        move.b  d5,1(a7)
        cmpi.b  #4,d4
        bne.s   rp_d
        move.b  #1,3(a7)
        bra.s   rp_o
rp_d:   tst.b   d4
        beq.s   rp_o
        move.b  #1,2(a7)
rp_o:   move.b  d2,4(a7)
        move.b  d6,7(a7)
        move.l  a0,-(a7)
        jsr     $7732.w
        movem.l d0-d7/a0-a6,-(a7)
        movea.l 60(a7),a2       ; 自機
        lea     64(a7),a4       ; 付け直す装備
        movea.l a2,a0           ; ゲージの表を始めの状態に戻す（純正の $89B0〜。やり直しの流れで通る所。$7732 は戻さないので、
        jsr     $89b0.l         ;   以前は取った印が残り、復活の後にカプセルでミサイルなどが取れなかった）
        jsr     CmdUse.l
        move.b  7(a4),$6a(a2)
        movem.l (a7)+,d0-d7/a0-a6
        lea     12(a7),a7
        move.w  #$b00,d7        ; 残機の表示を描き直す（表示の依頼 11 = $1A72。純正はやり直しの流れで描く）
        jsr     $1622.w
        move.b  #180,$103817.l  ; 復活の後の無敵（約3秒。サブが自機を動かせる間だけ減らす）
        clr.b   $400a2.l
        rts
""")
# ---- テクニカル/ビギナー選択（改造プレイ）: ビギナーは選べない・灰色 ----
# 0x6b16 の andi.b #2,d6 / beq.s を置き換え（右でビギナーへ移る処理）
chunk('TypeBeg', """
TypeBeg: tst.b  MB_RUN.l
        bne.s   tb_no
        andi.b  #2,d6
        beq.s   tb_no
        rts
tb_no:  addq.l  #4,sp
        rts
""")
# 0x6a90 の jsr $e824（ビギナーの枠 = パレット $80600 を「選ばれていない色」にする）を置き換え
chunk('TypeGrey', """
TypeGrey: tst.b MB_RUN.l
        beq.s   tg_n
        lea     GREYPAL.l,a0
        lea     $80600.l,a1
        moveq   #15,d1
tg_lp:  move.w  (a0)+,(a1)+
        dbf     d1,tg_lp
        rts
tg_n:   jmp     $e824.l
""")
chunk('GreyPal', """
GREYPAL: GREYDATA
""")
# ボスラッシュ: 面が変わるたび、その面のボス手前を「再開位置」にする（d0 = 面 0..9）
chunk('BossSet', """
BossSet: move.b d0,$103f38.l
        move.l  a0,-(sp)
        move.w  d0,-(sp)
        add.w   d0,d0
        lea     BOSSPROG.l,a0
        move.w  0(a0,d0.w),d0
        beq.s   bs_x
        move.w  d0,$101052.l
        move.w  d0,$1010d2.l
        ori.b   #1,$101063.l
        ori.b   #1,$1010e3.l
bs_x:   move.w  (sp)+,d0
        move.l  (sp)+,a0
        rts
""")
chunk('BossProg', """
BOSSPROG: BOSSDATA
""")

# ---- #62 解除のコマンド（2026-10-31 に戻した。管理者決定：解除だけ・音つき・ロックは自動だけ 120秒）----
# 毎フレーム StubIn から（起動直後から呼ぶので ROM に置く）。d0 = P1（正論理）。
#   段階0: レバー上＋A → 1: 全部離す → 2: レバー下＋A → 3: 全部離す → 解除（各段階3秒以内。押す順番・同時押しは問わない）
#   解除したら音（SE_REQ にサブと同じ形で置き、StubIn が鳴らす）。遊んでいる間・スタートメニューの間（$40005 ≥ 2）は受け付けない。
#   解除のまま遊ばずに 120秒たったら自動でロック。変数は共有RAM $103E26（段階）・$103E27（残りフレーム）・$103E28.w（放置フレーム数）
SE_UNLOCK = 0x45
UNLOCK_IDLE = 7200      # 120秒
chunk('Lock', f"""
Lock:   lea     $103e26.l,a0
        cmpi.b  #2,$40005.l
        bcc.s   lk_act
        andi.b  #$1f,d0
        move.b  (a0),d1
        beq.s   lk_0
        subq.b  #1,1(a0)
        beq.s   lk_clr
        btst    #0,d1           ; 段階1・3 = 全部離すのを待つ
        beq.s   lk_2
        tst.b   d0
        bne.s   lk_idle
        cmpi.b  #3,d1
        bne.s   lk_nx
        move.b  #1,MB_UNLK.l    ; 解除
        move.b  #${SE_UNLOCK:x},SE_REQ.l
        clr.w   2(a0)
        bra.s   lk_clr
lk_2:   cmpi.b  #$18,d0         ; 段階2: レバー下＋A
        bne.s   lk_idle
        bra.s   lk_nx
lk_0:   cmpi.b  #$14,d0         ; 段階0: レバー上＋A
        bne.s   lk_idle
lk_nx:  addq.b  #1,(a0)
        move.b  #180,1(a0)
        bra.s   lk_idle
lk_clr: clr.b   (a0)
lk_idle:
        tst.b   MB_UNLK.l       ; 自動ロック（遊んでいない間）
        beq.s   lk_r
        addq.w  #1,2(a0)
        cmpi.w  #{UNLOCK_IDLE},2(a0)
        bcs.s   lk_r
        clr.b   MB_UNLK.l
lk_r:   rts
lk_act: clr.b   (a0)
        clr.w   2(a0)
        rts
""", 'rom')
# ---- キューブの出現の瞬間（0x26238 の move.b $40032.l,d5 の置き換え）----
# キューブの出現の高さは「その瞬間の $40032 xor $40033」で16通りから決まる。
# 改造プレイ中で CUBE HEIGHT/SHIFT/TYPE のどれかが R 以外のとき、1個目が出る瞬間だけ
# フレームカウンタを「その並びになる値」(サブが毎フレーム $103e30 に用意)にする。2個目以降は純正どおり
chunk('CubeSeed', """
CubeSeed:
        tst.b   MB_RUN.l
        beq.s   cs_x
        cmpi.w  #1,$48(a3)
        bne.s   cs_rec
        move.b  $103f35.l,d5
        or.b    $103f36.l,d5
        or.b    $103f37.l,d5
        beq.s   cs_r
CUBESEEDBODY
cs_r:   move.w  $40032.l,$103e3a.l   ; 1個目の瞬間のカウンタ（サブが H/S/T を割り出してプレイ中に表示）
cs_rec: move.w  $48(a3),$103e36.l    ; 何個目か と その瞬間のカウンタ（サブが予想と比べて処理落ちのずれを見る）
        move.w  $40032.l,$103e38.l
cs_x:   move.b  $40032.l,d5
        rts
""")
# メニューの背景: サブが共有RAM $102000 に置いたスプライトの色(256語)をパレット $80200〜 へ（$103e34 が合図）
# #63 エンディングのスキップ（alamone さんの申し出⑤）: 改造プレイ（メニューから始めた）だけ、エンディング中に 1P START で飛ばす。
# 状態7（$3C28）の入り口。エンディングは状態7の小状態0（$4002B=0）・10面（$101051=9）で $2FF80 が回し、その中の段階 $4002D（0〜$12）で進む。
# 段階 1 から先で START が押されたら、最後の段階 $12（$3085C: オプション等を戻し・物体と文字の面を消して次の周へ）へ飛ばす。
# 段階 0（オプションなどを $43900 に控える）は飛ばさない。状態7はめったに通らないので隙間の列に置く
chunk('EndSkip', """
EndSkip: lea    $4002d.l,a6     ; a6 は $3C28 が使い直す
        tst.b   (a6)            ; 段階 0 は飛ばさない（段階は 0〜$12 だけ。$12 に $12 を書いても同じ）
        beq.s   es_0
        tst.b   $103e2e.l      ; サブが立てる: 改造プレイ・10面・1P START を「押し直した」（場所が足りないので条件はサブで作る）
        beq.s   es_x
        move.b  #$12,(a6)
        bra.s   es_x
es_0:   clr.b   $103e22.l      ; 段階 0（エンディングの入り口）で「押し直し待ち」に戻す（START を押したまま入ってきたら、離すまで飛ばさない。#63 alamone さんの指摘）
es_x:   jmp     $3c28.l
""")
chunk('PalCopy', """
PalCopy: tst.b  $103e34.l
        beq.s   pc_r
        clr.b   $103e34.l
        lea     $102000.l,a0
        lea     $80200.l,a1
        move.w  #255,d0
pc_l:   move.w  (a0)+,(a1)+
        dbf     d0,pc_l
        lea     $80060.l,a1     ; #75 文字の面のパレット3（キューブの並びの見本の色。サブが $102200 に置く）
        moveq   #15,d0
pc_d:   move.w  (a0)+,(a1)+
        dbf     d0,pc_d
pc_r:   rts
""")
# 0x1d24 の jsr $326e（CREDIT の表示）を置き換え: 隠しメニュー表示中（トップ状態3）は出さない
chunk('CredHook', """
CredHook: cmpi.b #3,$40005.l
        beq.s   ch_r
        jmp     $326e.w
ch_r:   rts
""", 'rom')
# 面クリア → 次の面（状態7 の 0x3c7a: clr.w $101052 を置き換え）。ボスラッシュなら次の面もボス手前から
chunk('NextStg', """
NextStg: tst.b  MB_RUN.l
        beq.s   ns_n
        cmpi.b  #4,MB_MODE.l    ; BOSS RUSH（BOSSRUSH=1。CUBE NO DEATH #39 のため 3→4 に）
        bne.s   ns_n
        move.l  d0,-(sp)
        moveq   #0,d0
        move.b  $101051.l,d0
        andi.b  #$0f,d0
        addq.b  #1,d0
        cmpi.b  #10,d0
        bcs.s   ns1
        moveq   #0,d0
ns1:    cmpi.b  #3,d0           ; 4面(ボスなし)は飛ばす: ここで1つ進めておくと 0x68d4 で5面になる
        bne.s   ns2
        addq.b  #1,$101051.l
        moveq   #4,d0
ns2:    addq.b  #1,$103f39.l    ; 一巡したらゲームオーバー（StageHook と同じ数え方）
        cmpi.b  #10,$103f39.l
        bcs.s   ns3
        move.b  #3,$103f06.l
ns3:    jsr     BossSet.l       ; = move.b d0,$103f38 ＋ その面のボス手前を再開位置に（面 0〜9 の表は全部 0 以外）
        move.l  (sp)+,d0
        rts
ns_n:   clr.w   $101052.l
        rts
""")
# 0x68d4（次の面へ）の中の jsr $695c（位置を0に戻す）を置き換え: ボスラッシュなら 0x4ce8 でボス手前の位置を入れ直す
chunk('NextPos', """
NextPos: jsr    $695c.w
        tst.b   MB_RUN.l
        beq.s   np_r
        cmpi.b  #4,MB_MODE.l    ; BOSS RUSH（BOSSRUSH=1。CUBE NO DEATH #39 のため 3→4 に）
        bne.s   np_r
        jmp     $4ce8.w
np_r:   rts
""")
# 装備コマンドの残り回数（無敵中は無制限 $ff として返す）
chunk('CmdCnt', """
CmdCnt: tst.b   ND_FLAG.l       ; NO DEATH（#36・CUBE NO DEATH #39）: 残り30秒の表示が出ている間は、START は延長（+10分）
        beq.s   cc_i
        cmpi.l  #1800,ND_LEFT.l
        bhi.s   cc_i            ; 表示が出る前は、いつもの装備コマンド
        tst.b   $4004a.l        ; フリープレイ: クレジットなしで延長
        bne.s   cc_x
        move.b  $40034.l,d1
        beq.s   cc_i            ; クレジットが無ければ、いつもの装備コマンド
        moveq   #1,d7
        jsr     $2a76.w         ; クレジット −1（純正の START と同じ処理）
cc_x:   move.l  ND_TIME.l,d1    ; +ND_TIME（#40 のディップスイッチで 10分 or 5分）
        add.l   d1,ND_LEFT.l
        moveq   #0,d1           ; 装備コマンドは使わない
        rts
cc_i:   tst.b   MB_INV.l        ; d1 = 残り回数（$ff=無制限。無敵中も無制限）。0 でなければ装備コマンドを使う
        beq.s   cc_n
        moveq   #-1,d1
        bra.s   cc_s
cc_n:   move.b  $103f22.l,d1
        beq.s   cc_r
cc_s:   move.w  #$ffff,$42e70.l  ; オプションハンター: 装備コマンドで付けた後の1回目は出さない。純正は1回目が出ると時間を $FFFF にするので、同じにする（以前の 7200＝初期値 3600 の2回分だと、2回目が早すぎた #83）。出ないので種類（$42E73）は進まない
cc_r:   rts
""")

# ゲーム状態5(プレイ中)の代わり: シールド色・ポーズ/装備コマンド・開始時のハンター設定
chunk('PlayHook', """
PlayHook:
        tst.b   MB_RUN.l
        beq.w   ph_go
        move.w  $42e70.l,$103e2c.l  ; #96 HUNTER DISP 用にハンターの時間を毎フレーム写す（サブはメインのRAMを読めない）
        cmpi.b  #1,$103f16.l    ; SHD COLOR (1=純正の青)
        beq.s   ph_nc
        lea     $103e00.l,a0    ; サブが用意した7色 → シールドのパレット(0x131-0x136,0x13e)
        lea     $80262.l,a1
        moveq   #5,d7
ph_cl:  move.w  (a0)+,(a1)+
        dbf     d7,ph_cl
        move.w  (a0),$8027c.l
ph_nc:  jsr     PauseChk.l
        subq.b  #1,d0
        beq.w   ph_rts          ; 1: ポーズ中
        bcs.s   ph_np
        jsr     Command.l       ; 2: 装備コマンド（NO DEATH でクレジットがあれば延長）
ph_np:  tst.b   ND_FLAG.l       ; NO DEATH（#36・CUBE NO DEATH #39）: 自機を動かせる間だけ数える（ポーズ・START 表示・面クリア・エンディングなどは数えない）。0 でその場でゲームオーバー
        beq.s   ph_nd
        lea     $101001.l,a0    ; 自機の状態（3 = 動かせる）。いま遊んでいる側
        tst.b   $4007f.l
        beq.s   ph_n1
        lea     $101081.l,a0
ph_n1:  cmpi.b  #3,(a0)
        bne.s   ph_nd
        subq.l  #1,ND_LEFT.l
        bhi.s   ph_nd
        clr.l   ND_LEFT.l
        move.b  #3,MB_PAUS.l    ; ポーズの GAME OVER と同じ（次のフレームの PauseChk）
ph_nd:
        tst.b   MB_PEND.l
        beq.s   ph_go
        movem.l d0-d7/a0-a6,-(a7)
        lea     $101000.l,a2
        moveq   #0,d0           ; bit0=1P 未適用 / bit1=2P 未適用
        tst.b   $4007f.l
        beq.s   ph_p
        lea     $101080.l,a2
        moveq   #1,d0
ph_p:   bclr    d0,MB_PEND.l
        beq.s   ph_x
        jsr     PendB.l         ; ハンターの設定
        move.b  $103f3d.l,d4    ; 開始時のスピード（サブがメニュー確定時に用意。いまはいつも 0）
        beq.s   ph_g
        moveq   #1,d3
        jsr     Use.l
ph_g:   move.b  $103f3c.l,d0    ; 開始時のゲージ（1周目1面A は 0=純正どおり、ほかは 1=SPEED UP）
        beq.s   ph_x
        move.b  d0,$6a(a2)
ph_x:   movem.l (a7)+,d0-d7/a0-a6
ESCPAL
ph_go:  jmp     $3a24.w
ph_rts: rts
""")

ESCPAL_SRC = """        move.b  MB_PEND.l,d0    ; 10面の脱出から始めた（StageHook）: ゲームの処理の後で、ラスボスを倒したときと同じ色（$E926:
        andi.b  #$38,d0         ; パレット $31 ← $33740。純正は $1FFBA）を入れる。開始位置までのパレットの出来事が
        beq.s   ph_go           ; プレイの2フレーム目にまとめて入る（$E428）ので、プレイの最初の7フレームのあいだ入れ直す（#21）
        subi.b  #8,MB_PEND.l
        jsr     $3a24.w
        jmp     $e926.l""" if EXTRA_AREAS else ''
CHUNKS[-1] = (CHUNKS[-1][0], CHUNKS[-1][1].replace('ESCPAL', ESCPAL_SRC), CHUNKS[-1][2])

# ---- 装備コマンド: サブCPUが「目標の装備にそろえるのに各枠を何回使うか」を計算済み(MB+$24〜 / 2P は +$2c〜) ----
# 枠 1=SPEED 2=MISSILE 3=DOUBLE 4=LASER 5=OPTION 6=SHIELD、+6 = スピードを2段階へ下げる印
chunk('Command', """
Command:
        jsr     CmdCnt.l        ; d1 = 残り回数 ($ff=無制限。無敵中も無制限)
        beq.s   cm_r
        addq.b  #1,d1
        beq.s   cm_go
        subq.b  #1,$103f22.l
cm_go:  movem.l d0-d7/a0-a6,-(a7)
        lea     $101000.l,a2
        lea     $103f24.l,a4
        tst.b   $4007f.l
        beq.s   cm_p
        lea     $101080.l,a2
        lea     $103f2c.l,a4
cm_p:   bsr.s   CmdUse
        move.b  $103f23.l,$6a(a2) ; カプセルゲージの位置 = メニューの CAPSULE（#5）
        movem.l (a7)+,d0-d7/a0-a6
cm_r:   rts
; a2=自機 a4=[SPEED,MISSILE,DOUBLE,LASER,OPTION,SHIELD の回数, スピードを下げる印]（#101 その場復活の付け直しも使う）
CmdUse: lea     $101f60.l,a3    ; 取得処理(0x8b0e)と同じ: シールド等のオブジェクト枠
        moveq   #0,d0
        move.b  6(a4),d0        ; スピードを下げる印（目標+1）
        beq.s   cm_s
        subq.b  #1,d0
        andi.b  #$e0,$69(a2)
        or.b    d0,$69(a2)
        mulu    #$c0,d0         ; 速さ = 0x100+0xc0*段階（自機の絵の番号 $1e は書かない: 4面で化けるため #4）
        addi.w  #$100,d0
        move.w  d0,$2c(a2)
        move.w  #$0101,$72(a2)  ; ゲージの SPEED UP の枠を戻す（5速で「取り切り」$0800 になって字が消えていた。遅くしたので取れるようにする #3）
cm_s:   moveq   #1,d3
cm_lp:  move.b  -1(a4,d3.w),d4
        bsr.s   Use
        addq.w  #1,d3
        cmpi.w  #7,d3
        bne.s   cm_lp
        rts
; d3=枠番号 d4=回数
Use:    andi.w  #$ff,d4
        subq.w  #1,d4
        bmi.s   us_r
us_lp:  movem.l d3-d4/a2-a4,-(a7)
        lea     $70(a2),a1
        add.w   d3,d3
        adda.w  d3,a1
        moveq   #0,d7
        move.b  1(a1),d7
        lsl.w   #2,d7
        lea     $8ce6.l,a6
        movea.l 0(a6,d7.w),a6
        jsr     (a6)
        movem.l (a7)+,d3-d4/a2-a4
        dbf     d4,us_lp
us_r:   rts
""")

# ---- ゲーム状態2(面の準備)の入口フック: モード別の面設定 ----
# MODE: 0=通常 1=キューブラッシュ 2=ボスラッシュ
chunk('StageHook', """
sh_pl:  jmp     ShPal.l         ; 改造プレイの START 表示の2フレーム目から: パレットの出来事も回す（#20）
StageHook:
        tst.b   MB_RUN.l
        beq.w   sh_go
        tst.b   $4002b.l
        bne.s   sh_pl
        bclr    #2,MB_PEND.l    ; 開始時1回だけ: 面・周回・エリアを反映
        beq.s   sh_m
        jsr     ApplyStage.l
        move.b  $103f08.l,d0    ; STAGE 11=グラディウス隠し面 12=サラマンダ隠し面
        subi.b  #10,d0
        bls.s   sh_m
        ; 隠し面: 0x3bba と同じ手順（戻り先 = 10面のラスボス手前の復活地点）
        move.b  d0,$103957.l
        move.w  #$ffff,$103cc0.l
        move.w  $101052.l,$103cc2.l
        move.b  $101051.l,$103cc4.l
        addi.b  #10,d0
        move.b  d0,$101051.l
        move.w  #$310,$101052.l
        ori.b   #1,$101063.l
        bra.s   sh_go
sh_m:
SHESC
SHBOSS
sh_go:  jmp     $3790.w
""")
SHESC_SRC = """        cmpi.b  #9,$101051.l    ; 10面のラスボスの後（脱出 ❹）から始める・再開する: ラスボスを倒したときに入る色（#21）を
        bne.s   sh_nx           ; プレイの最初のフレームで入れる（PlayHook。パレットの出来事の処理より後に）
        cmpi.w  #$2500,$101052.l
        bcs.s   sh_nx
        ori.b   #$38,MB_PEND.l  ; bit3〜5 = 残りフレーム数×8（7フレーム）
sh_nx:""" if EXTRA_AREAS else ''
SHBOSS_SRC = """        cmpi.b  #4,MB_MODE.l    ; BOSS RUSH（BOSSRUSH=1。CUBE NO DEATH #39 のため 3→4 に）
        bne.s   sh_go
sh_boss:                        ; ボスラッシュ (開始位置はサブが用意するボスラッシュ用エリア表で決まる)
        moveq   #0,d0
        move.b  $101051.l,d0
        andi.b  #$0f,d0
        cmpi.b  #3,d0           ; 4面(高速面・ボスなし)は飛ばす
        bne.s   sh_b1
        addq.b  #1,$101051.l
        addq.b  #1,d0
sh_b1:  cmp.b   $103f38.l,d0    ; 面が変わった回数を数え、一巡したらゲームオーバー
        beq.s   sh_go
        jsr     BossSet.l       ; = move.b d0,$103f38.l ＋ 次の面もボス手前から始める
        addq.b  #1,$103f39.l
        cmpi.b  #10,$103f39.l   ; 開始面 + 8面 → 開始面に戻った(10回目)
        bcs.s   sh_go
        move.b  #3,$103f06.l    ; 一巡した → ポーズの「GAME OVER」と同じ処理をプレイ開始時に行わせる""" if BOSSRUSH else ''
CHUNKS[-1] = (CHUNKS[-1][0], CHUNKS[-1][1].replace('SHESC', SHESC_SRC).replace('SHBOSS', SHBOSS_SRC), CHUNKS[-1][2])
if not (SHESC_SRC or SHBOSS_SRC): CHUNKS[-1] = (CHUNKS[-1][0], CHUNKS[-1][1].replace('        bra.s   sh_go\nsh_m:', 'sh_m:'), CHUNKS[-1][2])

# ---- エリア開始表の差し替え (0x4cfc の lea $54fe,a6 を置換) : 改造プレイ時のみ独自表 ----
chunk('AreaTbl', """
AreaTbl:
        lea     $54fe.w,a6
        tst.b   MB_RUN.l
        beq.s   at_r
        lea     $103f40.l,a6    ; サブCPUが共有RAMに置く独自エリア表(ポインタ16個+表)
at_r:   rts
""")

import os
def _main313():
    """純正313メイン（偶数 945_313.f15・奇数 945_312.e15 を交互に並べた1本）。G3BASE/work/main313.bin があればそれを使う"""
    import g3build
    p = os.path.join(g3build.BASE, 'work', 'main313.bin')
    if os.path.exists(p): return open(p, 'rb').read()
    return bytes(g3build.il(open(g3build.F15, 'rb').read(), open(g3build.E15, 'rb').read()))
CUBEX = int(os.environ.get('CUBEX', '54000'), 16); CUBEY = int(os.environ.get('CUBEY', '0'), 16)
# 10面(マップ13)の独自エリア表。
# ボスラッシュの各ボス = 敵出現表(0x252d4)のボス出現イベントの約0xc4手前。ボス1 = 0x11c00、
#   ボス2〜6 = 0x21c02/0x35bdd/0x49c21/0x5dc03/0x71bde（端数を不規則に数単位ずらす）
# ボスラッシュ後 = EvPtr の補正区間(X<0x780)を抜けた直後の 0x7a000 / ❹ 脱出 = ST10_C4（ラスボスの後）
ST10_C2 = int(os.environ.get('C2X', '1ca000'), 16)   # ❷ 中ボス（0x1bc840 で止まる壁の砲台）を過ぎて（0x1c0000 だとまだ中ボスが出る）、クラブに入るところ
ST10_C3 = int(os.environ.get('C3X', '234000'), 16)   # ❸ ラスボスの手前（肉団子の区間 0x200000〜0x230000 の後。ラスボスは 0x24xxxx）
ST10_C4 = int(os.environ.get('C4X', '260000'), 16)   # ❹ 脱出: ラスボスの脳の壁が画面から出た所（要塞のすぐ手前。#21）。
# スクロールが再開する $24D000 から始めると、ボスを倒したときの地形の書き換え（メイン $203FA・サブ $7900〜）が無いので、
# 壊れていない壁が残って自機が重なる。$25C000 でも最初の1秒ほど左端に壁が残っていた
ST10 = [(0, 0x20000), (0x11c00, 0x20000), (0x21c02, 0x20000), (0x35bdd, 0x20000), (0x49c21, 0x20000),
        (0x5dc03, 0x20000), (0x71bde, 0x20000), (0x7a000, 0x20000), (0xc0000, 0), (0xf0000, 0), (0x120000, 0),
        (0x148000, 0), (0x180000, 0), (0x1b0000, 0), (ST10_C2, 0), (0x200000, 0), (ST10_C3, 0), (ST10_C4, 0)]
# メニューの構成:
#   STAGE 10 = A 開始 / ❶ ボスラッシュ直後 / B〜G 本来の復活地点1〜6 / ❷ / H 本来の7番目 / ❸ / ❹ 脱出(ST10_C4)
#   BOSS RUSH = ボス2〜6の手前
for _kv in os.environ.get('ST10X', '').split(','):      # テスト用: ST10X="2=24000,3=38000"
    if _kv: _i, _v = _kv.split('='); ST10[int(_i)] = (int(_v, 16), ST10[int(_i)][1])
ST10_ROW = [0, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17] if EXTRA_AREAS else [0, 7, 8, 9, 10, 11, 12, 13, 15]
BR_ROW = [2, 3, 4, 5, 6]
# 9面 = 開始 / 0x58000(キューブ地帯の手前。キューブラッシュもここから) / 0x5c000(ボス手前)
ST9 = [(0, 0), (0x58000, 0), (0x5c000, 0)]
# ※ 9面の表は次の版でもそのまま（エリア2 0x58000 はキューブラッシュの開始・復活地点。メニューの 9面は A だけ出す）
if os.environ.get('ST9X'): ST9 = [(0, 0)] + [(int(v, 16), 0) for v in os.environ['ST9X'].split(',')]
# 3面 = 本来の8地点 + ビッグコアMkIII手前 0x1ca000 (Y は8番目と同じ)
MK3 = (int(os.environ.get("MK3X", "1ca000"), 16), 0x30000)
EXT10 = 0x103e40                                  # 10面の表を置く共有RAM (0x103e40〜0x103ec7, 起動後は未使用)
PTCOLS = 12                                       # PROGTBL の1行の語数（10面が12か所）

MID5 = int(os.environ.get('MID5X', 'e0000'), 16)   # 5面 ❶ 中ボス（大きなモアイ。0xe7xxx で出て 0xf0000 で止まる）の手前
BOSS5 = int(os.environ.get('BOSS5X', 'f6000'), 16)  # 5面 ❷ ボスの手前（中ボスの停止位置 0xf0000 を過ぎたところ。ボスは 0x102000 で止まる）

def stage_areas(st):
    """面 st(0..8) のエリア表 [(x, y), ...]。本来の復活地点に「ボスの手前」などを足したもの（x の順）
    1・6・7・8面 = ❶ボスの手前 / 3面 = ❶ビッグコアMkIIIの手前(MK3) / 5面 = ❶中ボスの手前・❷ボスの手前 / 9面 = 独自"""
    import struct
    d = _main313()
    L = lambda a: struct.unpack('>I', d[a:a+4])[0]
    smap = d[0x69ce:0x69de]
    if st == 8: return list(ST9)
    m = smap[st]; a = L(0x54fe + 4*m); r = []
    while L(a) != 0x0fffffff and len(r) < 16: r.append((L(a), L(a+4))); a += 8
    add = []
    if not EXTRA_AREAS: pass
    elif st == 2: add = [MK3]
    elif st in (0, 4, 5, 6, 7):
        bt = boss_progress()
        bx = (bt[st] << 8) - BRDELTA
        # 曲の表(0xe052)の「ボスの曲」の地点より手前から始める（過ぎた所から始めるとボスの曲が鳴らない）
        mt = L(0xe052 + 4*m)
        bx = min(bx, (L(mt + 16) << 8) - BXPRE)
        if st == 4: add += [MID5, BOSS5]       # 5面はボスラッシュの位置(0xf0000)だと中ボスになるので、中ボスの後から
        else: add.append(bx)
    for x in add:
        if isinstance(x, tuple): r.append(x); continue
        y = 0
        for ex, ey in r:
            if ex <= x: y = ey
        r.append((x, y))
    r.sort(key=lambda e: e[0])
    return r

def boss_progress():
    import struct
    d = _main313()
    L = lambda a: struct.unpack('>I', d[a:a+4])[0]
    smap = d[0x69ce:0x69de]; bt = []
    for st in range(16):
        m = smap[st]; v = 0
        if m != 0xff:
            a = L(0x4f06 + 4*m)
            while L(a) != 0xffffffff:
                if d[a+5] & 0x80: v = L(a) >> 8; break
                a += 6
        bt.append(v)
    return bt

def _prog(x):
    return ((x >> 8) + 1) if x else 0

def progress_tables():
    """(PROGTBL: 行1..13 x エリア1..10 の開始進行度, 面idx0..15 のボス接近進行度) をメインROMから算出
    行11/12(隠し面)は未使用、行13 = 10面ボスラッシュ"""
    import struct
    d = _main313()
    L = lambda a: struct.unpack('>I', d[a:a+4])[0]
    smap = d[0x69ce:0x69de]
    def areas(m):
        st = list(smap).index(m)
        return stage_areas(st)
    def row(xs):
        xs = list(xs) + [xs[-1]] * (PTCOLS - len(xs))
        return [_prog(x) for x in xs[:PTCOLS]]
    pt = []
    for st in range(9):
        ar = []
        for x, y in areas(smap[st]):            # 同じ位置の重複エントリは1つにまとめる(メニューの表と一致)
            if x not in ar: ar.append(x)
        pt += row(ar)
    pt += row([ST10[i][0] for i in ST10_ROW])
    pt += [0] * (2 * PTCOLS)
    pt += row([ST10[i][0] for i in BR_ROW])
    bt = []
    for st in range(16):
        m = smap[st]; v = 0
        if m != 0xff:
            a = L(0x4f06 + 4*m)
            while L(a) != 0xffffffff:
                if d[a+5] & 0x80: v = L(a) >> 8; break
                a += 6
        bt.append(v)
    return pt, bt

def ext10_blob(boss=False):
    """共有RAM EXT10 に置く10面の表。通常 = ボスラッシュ区間の地点を除いたもの（そこで死ぬと面の最初から＝純正どおり）
    ボスラッシュ時 = ボス1直前から（❷❸ は除く）"""
    import struct
    if boss: t = [e for e in ST10[1:] if e[0] not in (ST10_C2, ST10_C3)]
    elif EXTRA_AREAS: t = [ST10[i] for i in ST10_ROW]
    else: t = [ST10[i] for i in sorted(ST10_ROW + BR_ROW)]   # 次の版: BOSS RUSH の行（ボス2〜6の手前）は通常のモードで選ぶので、表にも入れる
    #   （表に無い地点を選ぶと面の最初から始まってしまう。そのかわり、ボスラッシュの区間で死ぬとその手前の地点から再開する）
    b = b''.join(struct.pack('>II', x, y) for x, y in t + [(0x0fffffff, 0)])
    assert len(b) <= 0x88, len(b)
    return b + bytes(0x88 - len(b))

def area_table_blob(st, base=0x103f40, areas=None):
    """面 st(0..9) をプレイ中に共有RAM base に置く独自エリア表（ポインタ16個 + その面の表 128バイト）。
    サブが今の面に合わせて毎フレーム書き直す（表は今の面の分だけ置けばよい）"""
    import struct
    d = _main313()
    L = lambda a: struct.unpack('>I', d[a:a+4])[0]
    smap = d[0x69ce:0x69de]
    ptr = [L(0x54fe + 4*m) for m in range(16)]
    ptr[13] = EXT10
    body = b''
    if st <= 8:
        ptr[smap[st]] = base + 64
        body = b''.join(struct.pack('>II', x, y) for x, y in (areas if areas is not None else stage_areas(st)) + [(0x0fffffff, 0)])
    assert len(body) <= 0x80, (st, len(body))
    b = b''.join(struct.pack('>I', x) for x in ptr) + body
    return b + bytes(0xc0 - len(b))

BRDELTA = int(os.environ.get('BRDELTA', '14000'), 16)   # ボスラッシュ: ボス接近位置のこれだけ手前から（全面で検証済み。0x10000 だと着いた瞬間に面クリアになる面がある）
BXPRE = int(os.environ.get('BXPRE', '1000'), 16)    # メニューの ❶ボスの手前: ボスの曲が始まる地点よりこれだけ手前

def boss_area_blob(base=0x103f40):
    """ボスラッシュ用エリア表: 各面(4面・10面を除く)の表を「ボス接近位置-BRDELTA」の1件だけにする。
    死んだときも必ずボス直前から再開する。"""
    import struct
    d = _main313()
    L = lambda a: struct.unpack('>I', d[a:a+4])[0]
    smap = d[0x69ce:0x69de]
    pt, bt = progress_tables()
    ptr = [L(0x54fe + 4*m) for m in range(16)]
    ptr[13] = EXT10
    body = b''
    for st in (0, 1, 2, 4, 5, 6, 7, 8):
        m = smap[st]; bx = (bt[st] << 8) - BRDELTA
        a = ptr[m]; y = 0
        while L(a) != 0x0fffffff and L(a) <= bx: y = L(a+4); a += 8
        ptr[m] = base + 64 + len(body)
        body += struct.pack('>IIII', bx, y, 0x0fffffff, 0)
    b = b''.join(struct.pack('>I', x) for x in ptr) + body
    assert len(b) <= 0xc0, len(b)
    return b + bytes(0xc0 - len(b))

BR_CHUNKS = ('BossSet', 'BossProg', 'NextStg', 'NextPos')   # BOSS RUSH モードだけで使う
if not BOSSRUSH: CHUNKS[:] = [c for c in CHUNKS if c[0] not in BR_CHUNKS]

# 解除・ロックのコマンド：#62（2026-10-31）で解除だけをメインの Lock（chunk）に戻した。SRC_LOCK は前の版（解除・ロックの両方。参考に残す）
RAMBLOB = None             # 共有RAMに置くコード [(メインの番地, bytes)]。apply() が作り、mod_sub がサブROMに入れて起動時に写す

def apply(rom):
    import asm68, struct, mainpack, mod_edit
    d313 = _main313()
    gw = []
    for i in range(16):                                   # ビギナーの枠の色(0x328c0)を灰色・やや暗く
        v = struct.unpack('>H', d313[0x328c0 + 2*i:0x328c2 + 2*i])[0]
        r, g, b_ = (v >> 10) & 31, (v >> 5) & 31, v & 31
        y = int((r * 0.3 + g * 0.59 + b_ * 0.11) * 1.4 + 3.5)
        gw.append(((y << 10) | (y << 5) | y) if (v and 2 <= i <= 6) else v)   # 2〜6 = ビギナーの枠の線の色だけ（8〜10 などはテクニカルの文字と共用）
    pt_, bt_ = progress_tables()
    bp = []
    for st in range(10):                                  # ボスラッシュ用: 面ごとのボス手前の進行度（boss_area_blob と同じ位置）
        if st == 9: bp.append(_prog(ST10[1][0]))
        elif st == 3 or not bt_[st]: bp.append(0)
        else: bp.append(_prog((bt_[st] << 8) - BRDELTA))
    assert all(bp[i] for i in range(10) if i != 3), bp     # NextStg は「0 なら書かない」BossSet を使う（4面以外は全部 0 以外）
    chunks = []
    for n, s, w in CHUNKS:
        s = s.replace('GREYDATA', 'dc.w    ' + ','.join('$%x' % x for x in gw)).replace('BOSSDATA', 'dc.w    ' + ','.join('$%x' % x for x in bp))
        s = s.replace('CUBESEEDBODY', ('        move.w  #$%x,$40032.l' % ((int(os.environ['CUBESLOT']) << 2) << 8)) if os.environ.get('CUBESLOT') else '        move.w  $103e30.l,$40032.l')
        chunks.append((n, s, w))
    lr = '\n'.join(l for l in (mod_edit.SRC_LR % (0, mod_edit.EB + mod_edit.O_MAX)).splitlines() if not l.strip().startswith('org'))
    chunks.append(('EdLR', lr, {'rom', 'shr', 'mrm'}))
    byname = {c[0]: c for c in chunks}
    chunks = [(n, s, w | {'stream'}) for n, s, w in (byname[k] for k in COLD if k in byname)] + [c for c in chunks if c[0] not in COLD]
    place, out, lab, size, left = mainpack.layout(chunks, REGIONS, STREAM, CONSTS, data=('StateTbl', 'GreyPal', 'BossProg'))
    if os.environ.get("PLACE"): print({k: (v, size[k]) for k, v in place.items() if v and v[0][0] in "RMXC"})
    global RAMBLOB
    kinds = {r[0]: r[3] for r in REGIONS}
    shr, mrm = {}, {}
    for rn, org, b in out:
        k = kinds.get(rn, 'rom')
        if k == 'rom': rom.put('main', org, b, 'mod:' + rn, free_ok=rn.startswith('X') or rn == 'C')   # C は 0 と FF の境目をまたぐことがある。X* = 消したテストモードの小機能（#41。中身は残っているが使われない）
        else: (shr if k == 'shr' else mrm).setdefault(rn, []).append((org, b))
    def joined(d):
        res = []
        for rn in sorted(d):
            lo = [r for r in REGIONS if r[0] == rn][0][1]
            blob = bytearray()
            for org, b in sorted(d[rn]):
                assert org == lo + len(blob); blob += b
            res.append((lo, bytes(blob)))
        return res
    mparts = []
    for lo, blob in joined(mrm):                          # メインRAMへは受け渡し場所の大きさごとに分ける
        blob += bytes(-len(blob) % 4)
        for i in range(0, len(blob), STAGEMAX): mparts.append((lo + i, blob[i:i + STAGEMAX]))
    RAMBLOB = {'main': mparts, 'shr': joined(shr), 'magic': RAMMAGIC, 'magicval': MAGICVAL, 'stage': STAGE}
    J = lambda a: bytes.fromhex('4eb9') + lab[a].to_bytes(4, 'big')
    rom.put('main', 0x154aa, J('EvPtr'), 'evptr', expect=bytes.fromhex('23ce00042e00'))
    rom.put('main', 0x4cfc, J('AreaTbl'), 'areatbl', expect=bytes.fromhex('4df9000054fe'))
    rom.put('main', 0x28ec + 2*4, lab['StageHook'].to_bytes(4, 'big'), 'stagehook', expect=bytes.fromhex('00003790'))
    rom.put('main', 0x28ec + 7*4, lab['EndSkip'].to_bytes(4, 'big'), 'endskip', expect=bytes.fromhex('00003c28'))   # #63
    rom.put('main', 0x28ec + 5*4, lab['PlayHook'].to_bytes(4, 'big'), 'playhook', expect=bytes.fromhex('00003a24'))
    rom.put('main', 0x15ce, lab['LivHk'].to_bytes(4, 'big'), 'lives-tbl', expect=bytes.fromhex('00001a72'))
    rom.put('main', 0x17fe, J('LivHk'), 'lives-1p', expect=bytes.fromhex('4eb900001a72'))
    rom.put('main', 0x1d1e, J('StubIn'), 'hook-in', expect=bytes.fromhex('4eb9000033b8'))
    rom.put('main', 0x1e82, J('HookStart'), 'hook-start', expect=bytes.fromhex('4eb900002968'))
    rom.put('main', 0x26238, J('CubeSeed'), 'cubeseed', expect=bytes.fromhex('1a3900040032'))
    rom.put('main', 0x1e44, lab['StateTbl'].to_bytes(4, 'big'), 'state-table-ptr', expect=bytes.fromhex('00001e58'))
    mod_edit.apply_main(rom, d313)
    rom.put('main', 0x7288, J('EdLR'), 'ed_lrhook', expect=bytes.fromhex('1e060207000c'))
    # 無敵（改造プレイのみ・メニューの INVINCIBLE）: 自機が死亡に入る2か所の直前で、無敵なら当たりを消して通常の続きへ
    rom.put('main', 0x7bc4, J('DieA') + bytes.fromhex('4e71'), 'inv-a', expect=bytes.fromhex('13fc0001000400a2'))
    rom.put('main', 0xae22, J('DieB') + bytes.fromhex('4e71'), 'inv-b', expect=bytes.fromhex('13fc0001000400a2'))
    rom.put('main', 0x7c88, J('Rsp') + bytes.fromhex('4e71'), 'respawn', expect=bytes.fromhex('13fc0002000400a2'))   # #35
    rom.put('main', 0x6b16, J('TypeBeg'), 'type-beg', expect=bytes.fromhex('0206000267' + '1a'))
    rom.put('main', 0x6a90, J('TypeGrey'), 'type-grey', expect=bytes.fromhex('4eb90000e824'))
    rom.put('main', 0x197e, J('HiHk'), 'hi-cube', expect=bytes.fromhex('beb900040058'))
    rom.put('main', 0x226c4, J('RankHk'), 'rank-cube', expect=bytes.fromhex('203900101054'))
    rom.put('main', 0x15b6, lab['ScoreHk'].to_bytes(4, 'big'), 'score-tbl', expect=bytes.fromhex('0000180a'))
    rom.put('main', 0x1932, lab['ScoreHk'].to_bytes(4, 'big'), 'score-1p', expect=bytes.fromhex('0000180a'))
    rom.put('main', 0x1954, lab['ScoreHk'].to_bytes(4, 'big'), 'score-2p', expect=bytes.fromhex('0000180a'))
    rom.put('main', 0x1d24, J('CredHook'), 'credit-hide', expect=bytes.fromhex('4eb90000326e'))
    if BOSSRUSH:
        rom.put('main', 0x692a, J('NextPos'), 'bossrush-pos', expect=bytes.fromhex('4eb90000695c'))
    if BOSSRUSH:
        rom.put('main', 0x3c7a, J('NextStg'), 'bossrush-next', expect=bytes.fromhex('427900101052'))
    # RAM のコードは、メインが呼ぶ前に必ず写してあること（StubIn・LoadW は ROM）
    for k in ('StubIn', 'LoadW'): assert all(kinds.get(r, 'rom') == 'rom' for r in place[k]), k
    rom.put('main', TM_SKIP, bytes.fromhex('523900040001' '4e75'), 'tm-skip', expect=bytes.fromhex('4247' '4df90000083a'))   # #41
    for _n in TM_REMOVE:
        rom.put('main', 0x808 + 4 * _n, TM_SKIP.to_bytes(4, 'big'), 'tm-tbl%d' % _n, expect=TM_BLOCKS[_n][0].to_bytes(4, 'big'))
    rom.free_main = [FILLER]                              # ROM 合計の微調整（起動画面の文字列の後ろと、ROM の最後の16バイト）
    rom.main_layout = (place, size, left)
    tot = sum(size.values())
    print('main mod code %d bytes. left: %s' % (tot, ', '.join('%s %d' % kv for kv in left.items())))
    return lab, place




def brskip_blob():
    """ボスラッシュ用: 面(0〜9)ごとに [最後のボスの停止位置, 面の終わりの位置]（画面の位置 = 表の位置 − 0x14000）。10面は 0（飛ばさない）"""
    import struct
    d = _main313()
    L = lambda a: struct.unpack('>I', d[a:a+4])[0]
    smap = d[0x69ce:0x69de]; out = b''
    for st in range(10):
        stop = end = 0
        if st != 9:
            a = L(0x4f06 + 4*smap[st])
            while L(a) != 0xffffffff:
                c = struct.unpack('>H', d[a+4:a+6])[0]
                if c & 0x80: stop = L(a) - 0x14000
                elif c & 0x40 and stop: end = L(a) - 0x14000; break
                a += 6
        if not (stop and end): stop = end = 0
        out += struct.pack('>II', stop, end)
    return out
