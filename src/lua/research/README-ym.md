# ステレオの調べ方（#66）

`ymtap2.lua`：YM2151 の `$20`〜`$27`（RL/FB/CONNECT）への書き込みを、**面ごと・チャンネルごと・RL の値ごと**に数える。

```bash
H=<リポジトリ>/src/lua/research
export ROMDIR=<純正の gradius3.zip を置いたフォルダ> WORK=$PWD
COVPLAY=$H/cov/covplay.lua YMOUT=$WORK/ym_loop1.txt \
  INV=1 MOVE=1 END=200000 \
  bash <リポジトリ>/src/lua/run.sh $ROMDIR $H/ymtap2.lua $WORK/x
```

- 自動プレイは `cov/covplay.lua` に任せる（`COVPLAY` でその場所を渡す）。`INV=1 MOVE=1` で死なずに進む。
- 1周（10面）を通すには `END=200000` くらい要る。
- 出力は `stage ch RL count` の行と、RL ごとの合計。

**大事な前提**：`gradius3 -listxml` の `sound channels = 1`。**MAME のこのドライバはモノラル出力**なので、音を聞いて左右を判定することはできない。ここで分かるのは「どの値が何回書かれたか」まで。どちらが左でどちらが右かは、YM2151 の資料か実機（#14）で決める。

古い `ymtap.lua` は「その組み合わせの最初の1回」しか書かないので、回数を数えるときは `ymtap2.lua` を使う。
