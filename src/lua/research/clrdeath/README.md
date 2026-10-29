# 面クリア後の突然死（面クリピシャン・#32）の再現

純正のバグ。面クリア（状態 `$40029 = 7`）の7フレーム後、サブCPUが次の面のために地形の面（K052109 の B 面）を作り直す（サブ `$72C6`〜：文字RAM を消してから、全部の升目に通し番号の文字を「番号（`$4001(a1)`）→ 属性（`$1(a1)`）」の順に書く）。
1つの升目で「番号は新しい・属性は古い」瞬間に、属性の古いバンクの字（不透明）が出て、メインの地形の当たり判定（`$7BA2` → `$83B0`）に引っかかる。
メインが判定する時にちょうどその升目の属性がまだ書かれていなければ、自機がそこにいると何もない画面で死ぬ。

## 使うもの
- `plain_start.sh`：純正を START で始め、面・進行度を書き込む（`../dig/plain_start.sh` と同じ。`G3RUN_OVR` で別の Lua を先に読む）
- `terr.py` / `scan.py`：SCENEDUMP したフレームから、メインの地形の判定（`$83B0`）を Python で再現して、画面のどこが「当たる」かを数える
- `celltap.lua`：その升目への書き込み（サブ）と、メインの判定の時刻を記録
- `delay.lua`：サブの属性の書き込みを1フレーム遅らせる（実機でサブの割り込みが長くかかった場合の再現）

## 手順（1面ボス、純正の ROM）
```bash
R=<リポジトリ>/src/lua/research/clrdeath; RUN=<リポジトリ>/src/lua/g3run.lua
INV=7bc4:4268001a602a4e71,ae22:4268001a60284e71       # ボスまで死なないように（rompatch.lua で書き換え）
# 1) 面クリアの前後をダンプして、当たる場所を探す（面クリアは 9186 フレーム）
SCENEDUMP=1 MAINPATCH=$INV LUAF=../dig/rompatch.lua NOFIRE=1 $R/plain_start.sh <純正> gd1 1 0a81 0 9260 9180:9250:1
python3 $R/scan.py runs/gd1:9186     # → 9193（+7）だけ x a800-ac00 y 8800-8e00 が当たる
# 2) 自機をそこに置き、属性の書き込みを遅らせる／遅らせない（9188 で無敵を外す）
P=$(for f in $(seq 9150 9260); do printf ',%d:101008:0:w,%d:10100a:ac00:w,%d:10100c:0:w,%d:10100e:8c00:w' $f $f $f $f; done)
DELAY=1 RESTORE_AT=9188 G3RUN_OVR=$R/delay.lua G3RUN2=$RUN MAINPATCH=$INV LUAF=../dig/rompatch.lua NOFIRE=1 XP="$P" WATCH=40029,101001 $R/plain_start.sh <純正> dlyA 1 0a81 0 9300 9190:9200:1
```
- 遅らせる＋その場所 → 9194 で死ぬ（`101001=04`）。遅らせない（`DELAY=0`）／別の場所（x 6000 や y 6000）→ 死なない。

## 直し方の確認（書く順を「属性 → 番号」に）
サブ `$732E`〜`$7345`（24バイト）を `e05c 1a04 0205 000e da04 1345 0001 e04c 1344 4001 4e71 4e71`
（ror.w #8,d4 / move.b d4,d5 / andi.b #$e,d5 / add.b d4,d5 / move.b d5,$1(a1) / lsr.w #8,d4 / move.b d4,$4001(a1) / nop nop）に書き換える。
属性 = 上のバイト + (上のバイト & $E)（上のバイトは 4〜9 なので純正の計算と同じ）。
```bash
FIX=732e:e05c1a040205000eda0413450001e04c134440014e714e71
DELAY=1 DELAYCODE=1 SUBPATCH=$FIX ...   # 後に書くほう（番号）を遅らせても死なない
DELAY=0 SUBPATCH=$FIX ...               # 9190〜9700 の画面は純正と1ピクセルも違わない（52枚）
```

## 面ごとの洗い出し（2026-10-30・純正313）
`clr.lua`：面クリア（`$40029` が 7 になった）フレームを tc として、tc−1〜tc+12 の vram/chr/shr をダンプし、サブの B 面への書き込み（`S <t> <番地> <値>`）を `tap.log` に記録する。`CLRDIR`・`CLRNEXT`（次に読む Lua）。
```bash
L=<リポジトリ>/src/lua; SEQ="1400:COIN,1500:START,1640:B1,1720:B1,1800:B1"; for f in $(seq 1950 6 80000); do SEQ="$SEQ,$f:B2"; done
# 1〜9面: 死なない・撃ちっぱなしで面クリアまで
CLRDIR=$PWD/runs/s2 CLRNEXT=$L/research/escape10/genstart.lua NEXT=$L/g3run.lua INV=1 STG=2 PROG=0000 HOLD=3 SEQ="$SEQ" END=80000 bash $L/run.sh <純正> $R/clr.lua x
# 10面: 自動で動いて撃つ
CLRDIR=$PWD/runs/s10 CLRNEXT=$L/research/cov/covplay.lua COVOUT=/dev/null STG=10 PROG=2341 LOOP=1 INV=1 MOVE=1 END=80000 bash $L/run.sh <純正> $R/clr.lua x
python3 $R/cells.py runs/s2        # 10面は: cells.py runs/s10 1 3
```
`cells.py`：全部の升目が「番号は新しい・属性は古い」だったとして、自機の範囲で地形に当たる点の地図。
`delay2.lua`：指定の升目（`DA`＝サブの属性の番地）の属性の書き込みを1フレーム遅らせ、その間は古い属性のまま（`DELAY=1`）。`RESTORE_AT` で無敵を外す。自機を置く位置は POKE（`10100a`＝X、`10100e`＝Y）。升目の番地は `terr.py` の idx から `0x24e001+idx`。
