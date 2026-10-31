"""サブCPU側: ロック/解除コンボ + 60秒自動ロック + メニュー起動
サブROM空き: 0x37d78〜0x3ffff（サブ連結イメージ上）。メールボックス: 共有RAM 0x103f00 → サブから 0x203f00
サブ専用変数: 0x103400〜0x1039cf（サブ私有RAM。元のプログラムは起動時のRAMチェックの後は書かない。2026-10-28 に 0x100f00〜0x1014cf から移した:
  0x100e00〜0x101bff はゲームの地形ブロックの読み込み表で、改造の変数が重なって地形が欠けていた #1）。
  ゲームが面の開始・再開のたびに 0x100e00〜0x101fff を消す（$0B9C）ので、同じときにこの範囲も消す（ClrHook）
"""
SUB_FREE = 0x37d78
# #2 キューブラッシュの左端の地形（B2'）: 純正で9面を最初から進めたとき、画面が止まる（0x5a000）までに地形を描いた呼び出し
# （サブ $7CC2: d6=X d7=Y d4=1 a5=絵の場所）のうち、止まったときの左端（X 0x580〜）にかかる22件。
# 測り方: src/lua/research/cubeleft/rec.lua（純正のサブの $AE40・$AF64 の jsr $7CC2 を記録の差し込みに替えて引数を書き出す）。
# 数字は位置と、サブ ROM の中の絵の番地だけ（絵そのものは入れない）。キューブラッシュの開始・再開のときにゲーム自身の $7CC2 で描く
CR9 = [(0x58140, 0xf000, 0x4a000), (0x58140, 0x2000, 0x4a000), (0x59140, 0xf000, 0x4a000), (0x59140, 0x2000, 0x4a000),
       (0x5a140, 0xf000, 0x4a000), (0x5a140, 0x2000, 0x4a000), (0x58700, 0x3000, 0x4a000), (0x59700, 0x3000, 0x4a000),
       (0x58740, 0xd000, 0x4a200), (0x58740, 0xc000, 0x4a280), (0x59640, 0xc000, 0x4a000), (0x59640, 0xb000, 0x4a000),
       (0x59640, 0xa000, 0x4a000), (0x59640, 0x9000, 0x4a000), (0x58700, 0x6000, 0x4a400), (0x58700, 0x5000, 0x4a600),
       (0x58700, 0x4000, 0x4a200), (0x59700, 0x4000, 0x4a480), (0x5a780, 0xa000, 0x4a400), (0x5a780, 0x9000, 0x4a600),
       (0x5a780, 0x8000, 0x4a200), (0x5b780, 0x8000, 0x4a480)]
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
SE_REQ   = $203e24          ; 効果音の依頼（メインの StubIn が鳴らす。#60・#62）
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
        cmpi.w  #1536,d0                ; 9面（8×192）: キューブラッシュ以外は純正どおり面の最初だけ（#45。キューブ地帯の手前 0x58000・
        bne.s   sb_n9                   ;   ボスの手前 0x5c000 はキューブラッシュの開始・復活用。NORMAL で死ぬとキューブ地帯から再開していた）
        cmpi.b  #2,$203f0b.l
        beq.s   sb_n9
        lea     AREA9N.l,a0
sb_n9:
        cmpi.b  #4,$203f0b.l   ; BOSS RUSH（BOSSRUSH=1。CUBE NO DEATH #39 のため 3→4 に）
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
        cmpi.b  #4,$203f0b.l           ; BOSS RUSH（BOSSRUSH=1。CUBE NO DEATH #39 のため 3→4 に）
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

; ---- #32 面クリアの後の即死（面クリピシャン）の修正 ----
; 純正のサブ $72C6〜 は、次の面のために B 面（地形）を作り直すとき、升目ごとに「番号 → 属性」の順に書く（$732E・$7342）。
; 番号だけ新しく属性が古い瞬間は古いバンクの不透明な字になり、メインの地形の判定に当たって死ぬ。
; 修正: 「属性 → 番号」の順に書く（途中の字は消したばかりの文字RAM＝透明）。
; 効かせるのは、メニューから始めたとき（いつも）と、START だけのときは SW1:5 が OFF（初期状態）のとき。
; SW1:5 を ON にすると純正どおり（#31 と同じスイッチ。2026-10-29 管理者決定）。DSW1 はメインが共有RAM $103814 に写す
; 入口: d4 = 番号（下位）と属性の元（上位）、a1 = 升目。出口: d4 = 属性（純正と同じ）。d5 を壊す（純正と同じ）
ClrFix:
        tst.b   MBS_RUN.l
        bne.s   cx_fix
        btst    #4,$203814.l    ; SW1:5（負論理: 1 = OFF = 修正する）
        bne.s   cx_fix
        move.b  d4,$4001(a1)    ; 純正どおり: 番号 → 属性
        lsr.w   #8,d4
        move.b  d4,d5
        andi.b  #$e,d4
        andi.b  #$e1,d5
        lsl.b   #1,d4
        add.b   d5,d4
        move.b  d4,1(a1)
        rts
cx_fix: move.b  d4,-(a7)        ; 番号を取っておく
        lsr.w   #8,d4
        move.b  d4,d5
        andi.b  #$e,d4
        andi.b  #$e1,d5
        lsl.b   #1,d4
        add.b   d5,d4
        move.b  d4,1(a1)        ; 属性が先
        move.b  (a7)+,$4001(a1) ; 番号が後
        rts

; ---- #2 キューブラッシュの左端の地形（B2'）----
; 開始・再開（面の初期化で ClrHook が V_CRP を 0 に戻す）のあと、画面の位置が 0x58000〜0x5a000 の間に、
; 純正で記録した22件をゲーム自身の地形の描き込み（$7CC2）で描く。初期化で地形が消されるのを待つため CRWAIT フレーム待ち、
; 1フレームに4件ずつ（START 表示の間。地形の色はまだ 0 なので見えない）。当たり判定の印もゲームが付ける
V_CRP   = $103710          ; 描いた件数（CRN 以上 = 済み）
V_CRW   = $103711          ; 待ったフレーム
CRWAIT  = 8
CrPaint:
        move.b  $201051.l,d0
        andi.b  #$0f,d0
        cmpi.b  #8,d0
        bne.s   cp_x
        move.l  $2038f0.l,d0
        cmpi.l  #$58000,d0
        bcs.s   cp_x
        cmpi.l  #$5a000,d0
        bhi.s   cp_x
        moveq   #0,d1
        move.b  V_CRP.l,d1
        cmpi.b  #CRN,d1
        bcc.s   cp_x
        cmpi.b  #CRWAIT,V_CRW.l
        bcc.s   cp_go
        addq.b  #1,V_CRW.l
cp_x:   rts
cp_go:  moveq   #3,d2           ; 4件ずつ
cp_l:   move.w  d1,d0
        mulu    #12,d0
        lea     CRTBL.l,a1
        adda.l  d0,a1
        movem.l d1-d2,-(a7)
        move.l  (a1)+,d6
        move.l  (a1)+,d7
        movea.l (a1),a5
        moveq   #1,d4
        jsr     $7cc2.l
        movem.l (a7)+,d1-d2
        addq.b  #1,d1
        cmpi.b  #CRN,d1
        bcc.s   cp_e
        dbf     d2,cp_l
cp_e:   move.b  d1,V_CRP.l
        rts

; ---- #53 NO DEATH: 10面の下へ降りる区間（X $800〜$9C0）で、自機を上に行き過ぎないように押さえる ----
; この区間は画面が自機を追って上下し（$40082 = 8）、X $9C0 で画面の高さが固定される（= 0）。普通は壁に押されて下へ降りるので
; 画面は一番下（上下 $80）で固定されるが、無敵で上にいると上のまま固定に入り、中ボス（X $1C00）まで化けた画面になる。
; NO DEATH（ND_FLAG）のときだけ、自機の Y（下から上へ増える）を「目標の画面の高さ + $8000（画面の真ん中）」以下にする。
; #59（2026-10-31 MAME で測った）: X $800〜$940 は画面が自機を追う（上へは自機−$8F00、下へは自機−$6200）。X $940〜$9C0 は
; 自機に関係なく画面が自分で降り（16ドットで約 $2A80、0 で止まる）、$9C0 でその高さに固定。$940 で $14000 以下なら 0 まで降りる。
; なので押さえるのは X $7F0〜$940 だけ、目標は $20000 → $10000（余裕を見て）。降りた後（$940 から先）は自由に上へ行ける。
NdDown:
        tst.b   MBS_RUN.l               ; 改造プレイだけ
        beq.s   nd_x
        tst.b   $203e1a.l               ; ND_FLAG
        beq.s   nd_x
        cmpi.b  #13,$2039c0.l           ; 10面（地図 13）
        bne.s   nd_x
        move.l  $2038de.l,d0
        lsr.l   #8,d0                   ; X（ドット）
        cmpi.l  #$7f0,d0
        bcs.s   nd_x
        cmpi.l  #$940,d0                ; #59: X $940 から先は画面が自分で一番下まで降りる（$40082=$28、16ドットで約 $2A80）ので押さえない
        bcc.s   nd_x
        move.l  #$940,d1                ; 目標の画面の高さ = ($940 − X) × $C0 + $10000（X $7F0 で約 $20000 → $940 で $10000）
        sub.l   d0,d1
        mulu    #$c0,d1
        addi.l  #$10000,d1
nd_t:   addi.l  #$8000,d1               ; 自機の Y の上限
        lea     $201000.l,a0            ; 1P・2P
        moveq   #1,d2
nd_p:   tst.b   (a0)
        bpl.s   nd_n
        cmp.l   $c(a0),d1
        bcc.s   nd_n
        move.l  d1,$c(a0)
nd_n:   lea     $80(a0),a0
        dbf     d2,nd_p
nd_x:   rts

; ---- #35 その場復活 ----
; 毎フレーム、「その場復活してよいか」を $203816 に置く（メインの Rsp が爆発の終わりで見る）:
;   改造プレイ・その場復活の印（MB+$3E。メニューの MODE が RESPAWN / RESPAWN NO DEATH のとき mf_go が立てる）・
;   動いているときの MODE が 0 か 1（キューブ・ボスラッシュでは使わない）・1人（2P の残機 $1010D0 が 0）・残機（BCD）が 2 以上。
;   最後の1機・4面（3D は別の自機の処理で Rsp を通らない）は純正どおり復活地点から。
;   RESPAWN NO DEATH は無敵なので、死ぬのはポーズの MISS など（残機は MISS が先に1つ足すので減らない）。
; 復活の後の無敵 $203817（メインが 180 を置く。メインの InvChk が見る）を、自機を動かせる間（状態 3）だけ減らし、点滅させる
; （自機の先頭 $201000 を 0 / $80。隠したかを $203818 に覚えておき、登場中（状態 1）以外の状態になったらやめて戻す）。
RspSub:
        moveq   #0,d0
        tst.b   MBS_RUN.l
        beq.s   rs_set
        tst.b   $203f3e.l       ; その場復活の印
        beq.s   rs_set
        cmpi.b  #1,$203f0b.l    ; 動いているときの MODE 0（普通）か 1（NO DEATH）
        bhi.s   rs_set
        tst.b   $2010d0.l       ; 2P の残機（1人プレイでは 0）
        bne.s   rs_set
        cmpi.b  #1,$201050.l    ; 残機 2 以上
        bls.s   rs_set
        moveq   #1,d0
rs_set: move.b  d0,$203816.l
        tst.b   $203817.l
        beq.s   rs_x
        cmpi.b  #1,MBS_PAUS.l   ; ポーズ中は減らさない
        beq.s   rs_x
        move.b  $201001.l,d0    ; 自機の状態
        cmpi.b  #1,d0           ; 登場中は待つ
        beq.s   rs_x
        cmpi.b  #3,d0
        bne.s   rs_end
        subq.b  #1,$203817.l
        beq.s   rs_vis
        btst    #2,$203817.l
        beq.s   rs_vis
        clr.b   $201000.l       ; 隠す
        move.b  #1,$203818.l
rs_x:   rts
rs_end: clr.b   $203817.l
rs_vis: tst.b   $203818.l       ; 自分で隠したときだけ戻す
        beq.s   rs_x
        clr.b   $203818.l
        move.b  #$80,$201000.l
        rts

; ---- キューブが反応する瞬間の効果音（#60）: ポーズの CUBE SE（$103E23 = 0:OFF / 1〜:音の番号の表 CSE_TBL）----
;   メインはキューブが反応したフレームで $2A を 0→1 にする（$262A2）。サブは枠ごとに前のフレームの $2A を控えておき、
;   0→0以外 に変わった枠があれば音の依頼を置く（遅れは最大1フレーム。反応の直前の $3A=0 を見る方法は、
;   メインとサブのフレームのずれで約4%取りこぼしたのでやめた）
V_SEA   = $103768          ; 枠ごとの前のフレームの「反応した」（32バイト。$103768〜$103787）
CubeSe: moveq   #0,d2
        moveq   #0,d3
        cmpi.b  #2,TOPSTATE.l
        bne.s   cse_0
        tst.b   MBS_RUN.l
        beq.s   cse_0
        cmpi.b  #2,$203f0b.l
        bne.s   cse_0
        move.b  $203e23.l,d3    ; CUBE SE（0 = OFF でも控えは更新する）
        bra.s   cse_1
cse_0:  rts                     ; キューブラッシュの外では何もしない（サブの処理を増やさない。純正どおりの START のプレイを変えないため）
cse_1:  lea     $202320.l,a0
        lea     V_SEA.l,a1
        moveq   #31,d6
cse_l:  moveq   #0,d0
        tst.b   (a0)
        beq.s   cse_n
        cmpi.w  #$3301,$28(a0)
        bne.s   cse_n
        move.b  $2a(a0),d0
        beq.s   cse_n
        tst.b   (a1)
        bne.s   cse_n
        moveq   #1,d2           ; この枠がいま反応した
cse_n:  move.b  d0,(a1)+
        lea     $50(a0),a0
        dbf     d6,cse_l
        tst.b   d2
        beq.s   cse_x
        tst.b   d3
        beq.s   cse_x
        ext.w   d3
        lea     CSE_TBL-1.l,a1
        move.b  0(a1,d3.w),SE_REQ.l
cse_x:  rts
CSE_TBL: CSEDATA
        even

; ---- #90 くっついたキューブの絵を地形の字に描くとき（純正 $7DAE の 32×32 ドットのループ）、その升目の字が 0 番だと
;      字の0番（数字の「0」）に描いてしまい、スコアなどの 0 が化けていた（キューブラッシュの開始位置では、くっつく所に
;      専用の字が用意されていない升目がある）。字の0番に当たるドットは描かない。
StickPix:
        jsr     $7dfc.l         ; 純正: そのドットのある字の絵の場所 → a6
        cmpa.l  #$280020,a6     ; 字の0番（$280000〜$28001F）
        bcs.s   sp_x
        jmp     $7ed2.l         ; 純正: ドットを描く
sp_x:   rts

; ---- 毎フレーム ----
Frame:
        jsr     CubeSe.l        ; #60
        moveq   #0,d0           ; #63 エンディングのスキップ: 改造プレイ・10面（$101051=9）・1P START を押している → $103E2E=1（メインの EndSkip が状態7で見る）
        tst.b   MBS_RUN.l
        beq.s   fr_es
        cmpi.b  #9,$201051.l
        bne.s   fr_es
        btst    #3,MBS_SYS.l
        beq.s   fr_ar
        tst.b   $203e22.l       ; 押し直し: START を離したのを見てから（$103E22=1）押されたときだけ。メインがエンディングの段階 0 で $103E22 を 0 に戻す
        beq.s   fr_es           ;   → START を押したままエンディングに入ってきたら、いったん離すまで飛ばさない（#63）
        moveq   #1,d0
        bra.s   fr_es
fr_ar:  move.b  #1,$203e22.l    ; START を離している
fr_es:  move.b  d0,$203e2e.l
        moveq   #1,d0           ; #31 高次周のリセットの修正を効かせるか（メインのガードが見る。1=効かせる 0=純正のバグを残す）:
        tst.b   MBS_RUN.l       ;   メニューから始めたら必ず効かせる。START だけのときは SW1:5（DSW1 bit4・負論理。1=OFF=初期値）が OFF なら効かせる
        bne.s   fr_31
        btst    #4,$203814.l
        bne.s   fr_31
        moveq   #0,d0
fr_31:  move.b  d0,$203e21.l    ; FIX31（共有RAM $103E21。ゲームが消さない所）
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
        jsr     CrPaint.l       ; #2 左端の地形
        jsr     HuntCtl.l
        cmpi.b  #2,TOPSTATE.l   ; キューブラッシュ: カプセルゲージは SPEED UP に固定（使ってもまた SPEED UP。5速まで）
        bne.s   fe_g
        tst.l   $2038de.l
        beq.s   fe_g
        move.b  #1,$20106a.l
fe_g:
fe_x:   moveq   #0,d1               ; CUBE COLOR が有効か → $203ed4（メインはこれを見てキューブの色を写す）
        moveq   #0,d2               ; CUBE FLASH（#48）が有効か
        cmpi.b  #2,TOPSTATE.l
        bne.s   fc_s
        tst.b   MBS_RUN.l
        beq.s   fc_s
        tst.l   $2038de.l
        beq.s   fc_s
        cmpi.b  #2,$203f0b.l
        bne.s   fc_s
        move.b  $203f34.l,d1
        move.b  $203e2a.l,d2        ; CF_FLAG（#57・#73）
fc_s:   move.b  d1,V_CCW.l
        move.b  d2,$103758.l        ; V_CFW（mod_menu）
        jsr     CubeCol.l
        tst.b   $203ed2.l           ; ポーズの MISS（キューブラッシュ以外）: 死んだら「無敵でも死ぬ」印を下ろす
        beq.s   fr_mx
        cmpi.b  #2,$203f0b.l
        beq.s   fr_mx
        cmpi.b  #4,$201001.l
        bne.s   fr_mx
        clr.b   $203ed2.l
fr_mx:
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
fr_nr:  jsr     NdDown.l        ; #53 NO DEATH の10面の下へ降りる区間
        jsr     RspSub.l        ; #35 その場復活
        jsr     HitDisp.l       ; #38 当たり判定の表示
        jsr     StChk.l
        jsr     PosChk.l
        jsr     NdDisp.l
        jsr     NdMsg.l
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
        bne.w   ce_clr          ; .w: CUBE NO DEATH の +1 残機で ce_clr が遠くなった (#39)
        move.b  $201051.l,d0
        andi.b  #$0f,d0
        cmpi.b  #8,d0
        bne.w   ce_clr
        cmpi.w  #$5b0,$201052.l
        bcs.w   ce_clr
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
        tst.b   $203e1a.l       ; CUBE NO DEATH（#39）: 残機を減らさない（先に +1。MISS と同じやり方）
        beq.s   ce_s4
        move.b  $201050.l,d0
        moveq   #1,d1
        dc.w    $44fc,$0000     ; move #0,ccr
        dc.w    $c101           ; abcd d1,d0
        cmpi.b  #$99,d0
        bcc.s   ce_s4
        move.b  d0,$201050.l
ce_s4:  move.b  #4,$201001.l
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
        cmpi.b  #4,$203f0b.l   ; BOSS RUSH（BOSSRUSH=1。CUBE NO DEATH #39 のため 3→4 に）
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
HuntCtl: cmpi.b #2,TOPSTATE.l   ; #74: 毎フレーム見る（以前は4フレームに1回で、出てから消すまでの2〜3フレーム、画面の左端に映っていた）
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

DATA_BASE = 0x3ac00   # 0x3a800 → 0x3ac00（#92・#93 でサブのコードが増えた）。0x3a400 → 0x3a800（#60・#62）。0x39800 → 0x39c00（#30）→ 0x3a000（#36 でサブのコードが増えた）→ 0x3a400（#38・#48・#49）。データの終わりは 0x3e2xx、0x3ffff まで空き）
WTYPE_BYTES = bytes([1,3,1, 3,1,4, 4,2,2, 2,4,3])   # TYPE A..D -> (missile, double, laser)

def apply(rom):
    import asm68, mod_menu, os, re
    import mod_main
    data, dl = mod_menu.build_data(DATA_BASE)
    abs_ = [mod_main.area_table_blob(st) for st in range(10)]
    ab = abs_[0]
    if len(data) & 1: data += b'\0'
    dl['BRSKIP'] = DATA_BASE + len(data); data += mod_main.brskip_blob()
    if len(data) & 1: data += b'\0'
    dl['AREABLOB'] = DATA_BASE + len(data); dl['AREACNT'] = len(ab) // 4 - 1
    data += b''.join(abs_)
    dl['AREA9N'] = DATA_BASE + len(data); data += mod_main.area_table_blob(8, areas=[(0, 0)])   # #45 9面・キューブラッシュ以外
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
    if len(data) & 1: data += b'\0'
    dl['CRTBL'] = DATA_BASE + len(data); dl['CRN'] = len(CR9)
    data += b''.join(struct.pack('>III', x, y, a) for x, y, a in CR9)
    wt = DATA_BASE + len(data) + (len(data) & 1)
    data = data + (b'\0' if len(data) & 1 else b'') + WTYPE_BYTES
    consts = ''.join('%s = $%x\n' % (k, v) for k, v in dl.items()) + 'WTYPE = $%x\n' % wt
    src = CONSTS + consts + SRC.replace(CONSTS, '', 1) + mod_menu.source(dl) + mod_edit.src()
    src = src.replace('CSEDATA', 'dc.b    ' + ','.join('$%02x' % c for t, c in mod_menu.CUBE_SE))
    src = src.replace('V_INIT', 'V_INIT') 
    src = src.replace('TESTNOIRQ', 'cmpi.b  #2,TOPSTATE.l\n        bne.s   ih_go\n        jmp     $5c8.l\nih_go:' if os.environ.get('TESTNOIRQ') else '')
    b, lab = asm68.assemble('V_INIT = $103412\n' + src if 'V_INIT   =' not in src else src, SUB_FREE)
    assert SUB_FREE + len(b) <= DATA_BASE, hex(SUB_FREE + len(b))
    rom.put('sub', SUB_FREE, b, 'subcore')
    rom.put('sub', 0xbb6, bytes.fromhex('4ef9') + lab['ClrHook'].to_bytes(4, 'big'), 'clr-vars', expect=bytes.fromhex('41f900101c00'))
    rom.put('sub', 0x732e, bytes.fromhex('4eb9') + lab['ClrFix'].to_bytes(4, 'big') + bytes.fromhex('4e71') * 9, 'clrfix-32',
            expect=bytes.fromhex('13444001e04c1a040204000e020500e1e30cd80513440001'))   # #32 $732E〜$7345（24バイト）
    rom.put('sub', 0x7dce, bytes.fromhex('4eb9') + lab['StickPix'].to_bytes(4, 'big'), 'stickpix-90', expect=bytes.fromhex('612c61000100'))   # bsr.s $7dfc / bsr.w $7ed2
    rom.put('sub', 0xafc4, bytes.fromhex('4eb9') + lab['CubeStick'].to_bytes(4, 'big'), 'cube-stick', expect=bytes.fromhex('117c00010026'))
    rom.put('sub', 0x877c, bytes.fromhex('4eb9') + lab['SprHook'].to_bytes(4, 'big') + bytes.fromhex('4e714e714e71'), 'menubg-spr', expect=bytes.fromhex('610000d213fc000000203936'))
    rom.put('sub', DATA_BASE, data, 'menudata')
    # IRQ1 ハンドラ(0xc6e)内の jsr $5c8 (0xc88) → jsr IrqHook
    rom.put('sub', 0xc88, bytes.fromhex('4eb9') + lab['IrqHook'].to_bytes(4, 'big'), 'irq1hook', expect=bytes.fromhex('4eb9000005c8'))
    return lab, len(b)
