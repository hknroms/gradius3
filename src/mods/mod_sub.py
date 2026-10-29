"""サブCPU側: ロック/解除コンボ + 60秒自動ロック + メニュー起動
サブROM空き: 0x37d78〜0x3ffff（サブ連結イメージ上）。メールボックス: 共有RAM 0x103f00 → サブから 0x203f00
サブ専用変数: 0x103400〜0x1039cf（サブ私有RAM。元のプログラムは起動時のRAMチェックの後は書かない。2026-10-28 に 0x100f00〜0x1014cf から移した:
  0x100e00〜0x101bff はゲームの地形ブロックの読み込み表で、改造の変数が重なって地形が欠けていた #1）。
  ゲームが面の開始・再開のたびに 0x100e00〜0x101fff を消す（$0B9C）ので、同じときにこの範囲も消す（ClrHook）
"""
SUB_FREE = 0x37d78
MBS = 0x203f00

CONSTS = """
MBS_P1   = $203f00
MBS_SYS  = $203f01
MBS_UNLK = $203f02
MBS_REQ  = $203f03
MBS_DONE = $203f04
MBS_KIND = $203f05
MBS_PAUS = $203f06
MBS_RUN  = $203f07
TOPSTATE = $2037c5
SV       = $103400
V_LAST   = $103400
V_PUD    = $103402
V_PDU    = $103403
V_TUD    = $103404
V_TDU    = $103406
V_IDLE   = $103408
V_LTBL   = $103720          ; 最後に写したエリア表の元
V_CCS    = $103724          ; キューブの色パレットの写しの中身（0=なし 1=色付き 2=元の色）
FRAMECNT = $203950          ; メインのVBLANKが共有RAMへ写すフレームカウンタ(サブの$100022は途中で止まるため)
"""

SRC = CONSTS + """
        org $37d78
; サブ IRQ1(垂直同期, 毎フレーム) の前に割り込ませる。元のハンドラ 0x5c8 へ続ける
; 面の開始・再開でゲームが 0x100e00〜0x101fff を消す処理（$0B9C の後半 $0BB6 の lea $101c00,a0 から飛んでくる）:
; 元の処理の続き＋改造の変数（0x103400〜0x1039cf）も消す（以前は消える範囲に置いていたので、同じ動きにする）
ClrHook:
        lea     $101c00.l,a0
        move.w  #$ff,d0
        jsr     $bc4.w
        lea     $103400.l,a0
        move.w  #$173,d0        ; 0x5d0 バイト = 0x174 ロング
        jmp     $bc4.w

; ---- メインの改造のコードの一部を RAM へ写す（#34。mod_main の先頭の説明） ----
; 印 RMAGIC（共有RAM）: 偶数 2k = k 番目のメインRAM用の中身を受け渡し場所に置いて 2k+1 にする（メインが写して 2k+2 にする）。
; 全部（RMCNT 個）渡したら、共有RAMの R1〜R3 にコードを置いて最後に RMVAL。RMVAL なら何もしない
RamCopy:
        move.w  RMAGIC.l,d0
        cmpi.w  #RMVAL,d0
        beq.s   rc_x
        btst    #0,d0
        bne.s   rc_x                    ; メインが写している最中
        lsr.w   #1,d0
        cmpi.w  #RMCNT,d0
        bcc.s   rc_fin
        mulu    #10,d0
        lea     RMTBL.l,a0              ; [写す先.l, ロング数-1.w, 中身のサブROMの番地.l] × RMCNT
        adda.l  d0,a0
        lea     RSTAGE.l,a1
        move.l  (a0)+,(a1)+
        move.w  (a0)+,d1
        move.w  d1,(a1)+
        movea.l (a0),a0
rc_c:   move.l  (a0)+,(a1)+
        dbf     d1,rc_c
        addq.w  #1,RMAGIC.l
rc_x:   rts
rc_fin: lea     RSTBL.l,a2              ; [写す先(サブの番地).l, 中身.l, 語数-1.w] … 写す先 0 で終わり
rc_l:   move.l  (a2)+,d0
        beq.s   rc_e
        movea.l d0,a1
        movea.l (a2)+,a0
        move.w  (a2)+,d1
rc_w:   move.w  (a0)+,(a1)+
        dbf     d1,rc_w
        bra.s   rc_l
rc_e:   move.w  #RMVAL,RMAGIC.l
        rts

IrqHook:
        TESTNOIRQ
        movem.l d0-d7/a0-a6,-(a7)
        bsr.w   RamCopy                 ; 起動直後: メインの改造のコードを RAM へ（#34。済んでいれば何もしない）
        moveq   #0,d0                   ; 独自エリア表を共有RAMへ: 今の面(0〜9)の分 (ボスラッシュ時は専用表)
        move.b  $201051.l,d0
        btst    #2,$203f1a.l            ; メニューから始めた直後（面・エリアをまだ反映していない）はメニューで選んだ面
        beq.s   sb_sc
        move.b  $203f08.l,d0
        subq.b  #1,d0
sb_sc:  cmpi.b  #9,d0
        bls.s   sb_s9
        moveq   #9,d0
sb_s9:  mulu    #192,d0
        lea     AREABLOB.l,a0
        adda.l  d0,a0
        cmpi.b  #3,$203f0b.l
        bne.s   sb_a0
        lea     BOSSBLOB.l,a0
sb_a0:
        ; 表の写しは毎フレームだと重い（サブの処理が遅れて、くっついたキューブの描き込みが間に合わなくなる）。
        ; メニュー中・表が変わったとき・8フレームに1回だけ写す
        cmpi.b  #2,TOPSTATE.l
        bne.s   sb_cpy
        cmpa.l  V_LTBL.l,a0
        bne.s   sb_cpy
        move.w  FRAMECNT.l,d1
        andi.w  #7,d1
        bne.w   sb_skip
sb_cpy: move.l  a0,V_LTBL.l
        lea     $203f40.l,a1
        move.w  #AREACNT,d7
sb_cp:  move.l  (a0)+,(a1)+
        dbf     d7,sb_cp
        lea     EDGEN.l,a0              ; エディット画面の表 → $103b40 (改造プレイ時は拡張版)
        tst.b   MBS_RUN.l
        beq.s   sb_d0
        lea     EDEXT.l,a0
sb_d0:  move.b  (a0),d0                 ; 先頭(MISSILE列の数)が違うときだけ書き直す(毎フレームの負担を減らす)
        cmp.b   $203b40.l,d0
        beq.s   sb_d2
        lea     $203b40.l,a1
        moveq   #EDCNT,d7
sb_d1:  move.l  (a0)+,(a1)+
        dbf     d7,sb_d1
sb_d2:
        lea     EXTN.l,a0               ; 10面の独自エリア表 → $103e40 (ボスラッシュ時はボス1直前から)
        cmpi.b  #3,$203f0b.l
        bne.s   sb_e0
        lea     EXTB.l,a0
sb_e0:  lea     $203e40.l,a1
        moveq   #33,d7
sb_e1:  move.l  (a0)+,(a1)+
        dbf     d7,sb_e1
        moveq   #0,d0                   ; シールド色(選択中の7色)を共有RAM $103e00 へ
        move.b  $203f16.l,d0
        subq.b  #1,d0
        cmpi.b  #9,d0
        bls.s   sb_c1
        moveq   #0,d0
sb_c1:  mulu    #14,d0
        lea     SHCOL.l,a0
        adda.w  d0,a0
        lea     $203e00.l,a1
        moveq   #6,d7
sb_c2:  move.w  (a0)+,(a1)+
        dbf     d7,sb_c2
        ; （$103e10〜 は以前ボスの表を写していたが、どこも読まないのでやめた。いまは NO DEATH の残り時間 #36）
sb_skip:
        jsr     Frame.l
        movem.l (a7)+,d0-d7/a0-a6
        jmp     $5c8.l          ; 元の処理へ

; ---- 毎フレーム ----  (解除/ロック/自動ロックはメインCPU側で処理)
Frame:
        lea     LNPAL.l,a0      ; パレット6 の 6〜15番（CUBE LINE の色と見出しの色）→ 共有RAM $103dec（メインが毎フレーム写す）
        lea     $203dec.l,a1
        moveq   #4,d0
fr_lp:  move.l  (a0)+,(a1)+
        dbf     d0,fr_lp
        move.w  $203e32.l,d0    ; キューブの RANDOM 用の乱数: 電源投入から毎フレーム進める（デモ・メニュー中も）
        mulu    #25173,d0
        addi.w  #13849,d0
        move.w  d0,$203e32.l
        moveq   #0,d1               ; CUBE INFO が有効か → $203ed1（メインはこれを見て HI・2P を描かない）
        cmpi.b  #2,TOPSTATE.l
        bne.s   fe_set
        tst.b   MBS_RUN.l
        beq.s   fe_set
        tst.l   $2038de.l
        beq.s   fe_set
        cmpi.b  #2,$203f0b.l
        bne.s   fe_set
        tst.b   $203f0c.l
        beq.s   fe_off
        moveq   #1,d1
        bra.s   fe_set
fe_off: tst.b   $203ed1.l           ; 表示中に OFF にされた → 最上段を消して、メインにスコアの描き直しを頼む
        beq.s   fe_set
        move.w  #26,d0
        move.w  #2,d1
        moveq   #24,d7
        jsr     ClrFld.l
        move.b  #1,$203ed0.l
        moveq   #0,d1
fe_set: move.b  d1,$203ed1.l
        jsr     BrSkip.l
        tst.b   MBS_RUN.l           ; キューブラッシュでは残機が増えない（次に増える点数を 0 = もう増えない にしておく）
        beq.s   fe_x
        cmpi.b  #2,$203f0b.l
        bne.s   fe_x
        clr.l   $201058.l
        jsr     CrEnd.l
        jsr     HuntCtl.l
        cmpi.b  #2,TOPSTATE.l   ; キューブラッシュ: カプセルゲージは SPEED UP に固定（使ってもまた SPEED UP。5速まで）
        bne.s   fe_g
        tst.l   $2038de.l
        beq.s   fe_g
        move.b  #1,$20106a.l
fe_g:
fe_x:   moveq   #0,d1               ; CUBE COLOR が有効か → $203ed4（メインはこれを見てキューブの色を写す）
        cmpi.b  #2,TOPSTATE.l
        bne.s   fc_s
        tst.b   MBS_RUN.l
        beq.s   fc_s
        tst.l   $2038de.l
        beq.s   fc_s
        cmpi.b  #2,$203f0b.l
        bne.s   fc_s
        move.b  $203f34.l,d1
fc_s:   move.b  d1,V_CCW.l
        jsr     CubeCol.l
        cmpi.b  #2,TOPSTATE.l
        beq.w   fr_ingame
        tst.b   MBS_REQ.l
        bne.w   fr_menu
        clr.b   V_INIT.l
fr_chk: rts
fr_menu:
        tst.b   MBS_DONE.l
        bne.w   fr_chk
        jmp     MenuFrame.l
fr_ingame:
        tst.b   MBS_RUN.l
        beq.w   fr_nr
        jsr     CmdCalc.l
        jsr     CubeCalc.l
        jsr     EditOv.l
        move.w  $20101e.l,d0    ; 面が始まってから（武器選択などの画面では出さない）: 自機の絵の番号（1P/2P）が入っている
        or.w    $20109e.l,d0    ; （以前は画面の位置 $2038de で見ていたが、4面は位置が 0 のままで出なかった #4）
        beq.w   fr_nr
        jsr     CubeHud.l
        jsr     CubeLine.l
        tst.b   $203f0e.l       ; RANK DISP（ポーズで切り替え。OFF にしたら消す）
        bne.s   fr_rk
        tst.b   V_RKL.l
        beq.w   fr_nr
        clr.b   V_RKL.l
        move.w  #43,d0
        move.w  #3,d1
        moveq   #7,d7
        jsr     ClrFld.l
        bra.w   fr_nr
fr_rk:  move.b  #1,V_RKL.l
        jsr     RankDisp.l
fr_nr:  jsr     StChk.l
        jsr     PosChk.l
        jsr     NdDisp.l
        cmpi.b  #1,MBS_PAUS.l
        bne.w   fr_np
        jmp     PauseFrame.l
fr_np:  clr.b   $103450.l
        rts


; ---- キューブラッシュの並び: 毎フレーム、選ばれた H/S/T（R は毎フレーム乱数で選び直す）から
;      1個目が出る瞬間に入れるフレームカウンタの値を表から引いて $203e30 に置く（メインの CubeSeed が使う）
V_CRNG  = $203e32
; ---- キューブラッシュ: キューブの区間が終わったら（壁が崩れて画面が進み、ボスの場所 0x5b0 に着いたら）
; ボスには行かずに自機を1機減らす → キューブラッシュの頭（0x58000）から始め直し。残機が無ければゲームオーバー
; 当たり判定は使わず、自機（$201000）を「死亡の動きが終わった」状態にして、ゲームの再開の流れに乗せる（爆発・死ぬ音・曲の止めは出ない）
CrEnd:  cmpi.b  #2,TOPSTATE.l
        bne.s   ce_clr
        move.b  $201051.l,d0
        andi.b  #$0f,d0
        cmpi.b  #8,d0
        bne.s   ce_clr
        cmpi.w  #$5b0,$201052.l
        bcs.s   ce_clr
        tst.b   $203ed3.l       ; もう死んだ
        bne.s   ce_off
        cmpi.b  #4,$201001.l    ; 死亡中になった → 済み
        beq.s   ce_done
        move.w  FRAMECNT.l,d0   ; 画面が止まってから約2秒（崩れた壁の破片が消えきるまで）待つ。ボスは約3.7秒後に見え始める
        tst.w   V_CEW.l
        bne.s   ce_w
        addq.w  #1,d0           ; 着いたフレーム+1 を覚える（0 = まだ）
        move.w  d0,V_CEW.l
        rts
ce_w:   sub.w   V_CEW.l,d0
        cmpi.w  #119,d0
        bcs.s   ce_r
        ; 当たり判定は使わず、自機を「死亡の動きが終わった」状態にする（爆発・死ぬ音・曲の止めを出さない）
        move.b  #4,$201001.l
        move.b  #1,$201027.l
        rts
ce_done: move.b #1,$203ed3.l
        move.b  #1,$201027.l    ; 爆発の演出を飛ばす（死亡の動きの「終わり」の印 → すぐ再開へ）
ce_off: clr.b   $203ed2.l
ce_r:   rts
ce_clr: clr.w   V_CEW.l
        clr.b   $203ed3.l
        clr.b   $203ed2.l
        rts

; ---- ボスラッシュ: ボスを倒して画面が動き出したら、面の終わりまで一気に進める（倒した後のスクロールを飛ばして次のボスへ）
; BRSKIP: 面(0〜9)ごとに [最後のボスの停止位置.l, 面の終わりの位置.l]（0=しない）
BrSkip: cmpi.b  #2,TOPSTATE.l
        bne.s   bk_r
        tst.b   MBS_RUN.l
        beq.s   bk_r
        cmpi.b  #3,$203f0b.l
        bne.s   bk_r
        moveq   #0,d0
        move.b  $201051.l,d0
        andi.b  #$0f,d0
        cmpi.b  #9,d0
        bhi.s   bk_r
        lsl.w   #3,d0
        lea     BRSKIP.l,a0
        move.l  0(a0,d0.w),d1   ; ボスの停止位置
        beq.s   bk_r
        move.l  4(a0,d0.w),d2   ; 面の終わり
        move.l  $2038de.l,d0
        addi.l  #$100,d1
        cmp.l   d1,d0
        bls.s   bk_r
        cmp.l   d2,d0
        bcc.s   bk_r
        move.l  d2,$2038de.l
bk_r:   rts

; ---- キューブラッシュのオプションハンター（ポーズの CUBE HUNTER）: OFF = 出さない / ON = キューブラッシュ1回につき最初の1体だけ
; ハンター = 種類($28) $4200 のオブジェクト。出させないものは出た瞬間に消す
V_CEW   = $203ed6               ; キューブラッシュの終わり: 画面が止まったフレーム+1（共有RAMの空き。サブの私有RAMは途中で消されることがある）
V_HUSED = $103728               ; このキューブラッシュで1体出した
V_HALLOW = $10372c              ; 出してよいハンターの場所
HuntCtl: cmpi.b #2,TOPSTATE.l
        bne.w   hu_r
        move.w  FRAMECNT.l,d0   ; 4フレームに1回（ハンターは出てから15フレームはこの種類のまま）
        andi.w  #3,d0
        cmpi.w  #1,d0
        bne.w   hu_r
        tst.l   $2038de.l
        beq.w   hu_r
        tst.w   $203e36.l       ; まだ1個目のキューブが出ていない（始め直し）→ 数え直す
        bne.s   hu_1
        clr.b   V_HUSED.l
hu_1:   move.l  V_HALLOW.l,d1
        beq.s   hu_2
        movea.l d1,a1
        tst.b   (a1)
        beq.s   hu_c
        cmpi.w  #$4200,$28(a1)
        beq.s   hu_2
hu_c:   clr.l   V_HALLOW.l
hu_2:   lea     $202320.l,a0
        moveq   #31,d6
hu_l:   tst.b   (a0)
        beq.s   hu_n
        cmpi.w  #$4200,$28(a0)
        bne.s   hu_n
        cmpa.l  V_HALLOW.l,a0
        beq.s   hu_n
        tst.b   $203f33.l
        beq.s   hu_d
        tst.b   V_HUSED.l
        bne.s   hu_d
        move.b  #1,V_HUSED.l
        move.l  a0,V_HALLOW.l
        bra.s   hu_n
hu_d:   clr.b   (a0)
hu_n:   lea     $50(a0),a0
        dbf     d6,hu_l
hu_r:   rts

CubeCalc:
        move.w  V_CRNG.l,d0
        moveq   #0,d1
        move.b  $203f35.l,d1    ; H: 0=R, 1..16
        bne.s   cu_h
        move.w  d0,d1
        lsr.w   #8,d1
        andi.w  #15,d1
        addq.w  #1,d1
cu_h:   subq.w  #1,d1
        lsl.w   #2,d1           ; (h*4 + s)
        moveq   #0,d2
        move.b  $203f36.l,d2    ; S: 0=R, 1..4
        bne.s   cu_s
        move.w  d0,d2
        lsr.w   #4,d2
        andi.w  #3,d2
        addq.w  #1,d2
cu_s:   subq.w  #1,d2
        add.w   d2,d1
        mulu    #45,d1
        moveq   #0,d2
        move.b  $203f37.l,d2    ; T: 0=R, 1..45
        bne.s   cu_t
        moveq   #0,d2
        move.w  d0,d2
        divu    #45,d2
        swap    d2
        andi.l  #$ffff,d2
        addq.w  #1,d2
cu_t:   subq.w  #1,d2
        add.w   d2,d1
        add.w   d1,d1
        lea     CUBETBL.l,a0
        move.w  0(a0,d1.w),$203e30.l
        rts
"""

DATA_BASE = 0x39c00   # 0x39800 → 0x39c00（#30 でサブのコードが増えた。データの終わりは 0x3e2xx、0x3ffff まで空き）
WTYPE_BYTES = bytes([1,3,1, 3,1,4, 4,2,2, 2,4,3])   # TYPE A..D -> (missile, double, laser)

def apply(rom):
    import asm68, mod_menu, os
    import mod_main
    data, dl = mod_menu.build_data(DATA_BASE)
    abs_ = [mod_main.area_table_blob(st) for st in range(10)]
    ab = abs_[0]
    if len(data) & 1: data += b'\0'
    dl['BRSKIP'] = DATA_BASE + len(data); data += mod_main.brskip_blob()
    if len(data) & 1: data += b'\0'
    dl['AREABLOB'] = DATA_BASE + len(data); dl['AREACNT'] = len(ab) // 4 - 1
    data += b''.join(abs_)
    bb = mod_main.boss_area_blob(); assert len(bb) == len(ab)
    dl['BOSSBLOB'] = DATA_BASE + len(data); data += bb
    import mod_edit
    import mod_main; main = mod_main._main313()
    cells = open(os.path.join(os.path.dirname(__file__), 'edit_cells.bin'), 'rb').read()
    if len(data) & 1: data += b'\0'
    eb, el = mod_edit.sub_blob(DATA_BASE + len(data), cells[:6], cells[8:], cells[6:8], mod_edit.tables(main, False), mod_edit.tables(main, True))
    data += eb; dl.update(el); dl['EDCNT'] = mod_edit.SIZE // 4 - 1
    if len(data) & 1: data += b'\0'
    dl['EXTN'] = DATA_BASE + len(data); data += mod_main.ext10_blob(False)
    dl['EXTB'] = DATA_BASE + len(data); data += mod_main.ext10_blob(True)
    import struct
    pt, bt = mod_main.progress_tables()
    import mod_cube
    if len(data) & 1: data += b'\0'
    dl['CUBETBL'] = DATA_BASE + len(data); data += b''.join(struct.pack('>H', x) for x in mod_cube.table())
    dl['CUBEDLT'] = DATA_BASE + len(data); data += b''.join(struct.pack('>H', x) for x in mod_cube.DELTAS)
    import mod_menubg
    for k, (n, blob) in mod_menubg.blobs().items():
        if len(data) & 1: data += b'\0'
        dl[k] = DATA_BASE + len(data); data += blob
    dl['PROGTBL'] = DATA_BASE + len(data); data += b''.join(struct.pack('>H', x) for x in pt)
    dl['BOSSTBL'] = DATA_BASE + len(data); data += b''.join(struct.pack('>H', x) for x in bt)
    dl['SHCOL'] = DATA_BASE + len(data)
    data += open(os.path.join(os.path.dirname(__file__), 'shield_colors.bin'), 'rb').read()
    rb = mod_main.RAMBLOB                                 # メインの改造のコードのうち RAM で動かす分（#34）
    if len(data) & 1: data += b'\0'
    mt = b''; mblobs = []
    for dst, b in rb['main']: mblobs.append((dst, b))
    sblobs = list(rb['shr'])
    tbl_m = DATA_BASE + len(data); data += bytes(10 * len(mblobs))
    tbl_s = DATA_BASE + len(data); data += bytes(10 * len(sblobs) + 4)
    mtab, stab = b'', b''
    for dst, b in mblobs:
        assert len(b) % 4 == 0 and len(b) <= mod_main.STAGEMAX
        mtab += struct.pack('>IHI', dst, len(b) // 4 - 1, DATA_BASE + len(data)); data += b
    for dst, b in sblobs:
        if len(b) & 1: b += b'\0'
        stab += struct.pack('>IIH', dst + 0x100000, DATA_BASE + len(data), len(b) // 2 - 1); data += b
    stab += bytes(4)
    data = data[:tbl_m - DATA_BASE] + mtab + stab + data[tbl_s - DATA_BASE + len(stab):]
    dl['RMTBL'] = tbl_m; dl['RSTBL'] = tbl_s; dl['RMCNT'] = len(mblobs)
    dl['RMAGIC'] = rb['magic'] + 0x100000; dl['RMVAL'] = rb['magicval']; dl['RSTAGE'] = rb['stage'] + 0x100000
    wt = DATA_BASE + len(data) + (len(data) & 1)
    data = data + (b'\0' if len(data) & 1 else b'') + WTYPE_BYTES
    consts = ''.join('%s = $%x\n' % (k, v) for k, v in dl.items()) + 'WTYPE = $%x\n' % wt
    src = CONSTS + consts + SRC.replace(CONSTS, '', 1) + mod_menu.source(dl) + mod_edit.src()
    src = src.replace('V_INIT', 'V_INIT') 
    src = src.replace('TESTNOIRQ', 'cmpi.b  #2,TOPSTATE.l\n        bne.s   ih_go\n        jmp     $5c8.l\nih_go:' if os.environ.get('TESTNOIRQ') else '')
    b, lab = asm68.assemble('V_INIT = $103412\n' + src if 'V_INIT   =' not in src else src, SUB_FREE)
    assert SUB_FREE + len(b) <= DATA_BASE, hex(SUB_FREE + len(b))
    rom.put('sub', SUB_FREE, b, 'subcore')
    rom.put('sub', 0xbb6, bytes.fromhex('4ef9') + lab['ClrHook'].to_bytes(4, 'big'), 'clr-vars', expect=bytes.fromhex('41f900101c00'))
    rom.put('sub', 0xafc4, bytes.fromhex('4eb9') + lab['CubeStick'].to_bytes(4, 'big'), 'cube-stick', expect=bytes.fromhex('117c00010026'))
    rom.put('sub', 0x877c, bytes.fromhex('4eb9') + lab['SprHook'].to_bytes(4, 'big') + bytes.fromhex('4e714e714e71'), 'menubg-spr', expect=bytes.fromhex('610000d213fc000000203936'))
    rom.put('sub', DATA_BASE, data, 'menudata')
    # IRQ1 ハンドラ(0xc6e)内の jsr $5c8 (0xc88) → jsr IrqHook
    rom.put('sub', 0xc88, bytes.fromhex('4eb9') + lab['IrqHook'].to_bytes(4, 'big'), 'irq1hook', expect=bytes.fromhex('4eb9000005c8'))
    return lab, len(b)
