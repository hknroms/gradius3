# エンディングのスキップ（#63）

改造ROMで、純正どおり 10面の途中（進行度 $2341）から無敵で遊んでエンディングまで進め、状態7（$40029）・小状態（$4002B）・段階（$4002D）・サブの印（$103E2E）・音の命令（$E8000）を記録する。
PRESS=n なら、状態7に入って n フレーム後に MB_RUN（$103F07）を立てて 1P START を10フレーム押す（メニューから始めたのと同じ扱いにするため）。

```bash
L=<リポジトリ>/src/lua
OLOG=es.log PRESS=900 SNAPF="12500,12900" NEXT0=$L/research/cov/covplay.lua COVOUT=c.bin STG=10 PROG=2341 LOOP=1 INV=1 MOVE=1 END=13400 bash $L/run.sh <改造>/mame $L/research/ending/skip.lua out
```

## 押したままエンディングに入った場合（2026-10-31・alamone さんの指摘）

`HOLDF=f HOLD=n`：f フレームで MB_RUN を立てて START を押し始め（状態7の少し前。60フレーム以上前だとポーズになる）、状態7に入って n フレーム後に離す。
`covplay.lua` は 900 フレームごと（fr%900==100）に START を6フレーム押すので、それも「押し直し」になる。

```bash
OLOG=A.log HOLDF=11410 HOLD=600 NEXT0=$L/research/cov/covplay.lua COVOUT=a.bin STG=10 PROG=2341 LOOP=1 INV=1 MOVE=1 END=12700 bash $L/run.sh <改造>/mame $L/research/ending/skip.lua out
```
結果：直す前（押しているだけで飛ぶ）は、入って5フレーム目に飛んだ。直した後は、押したままなら飛ばず（その間の covplay の START も押し直しにならない）、
離した後に押し直すと飛んで2周目に入る。PRESS=900（離した状態から押す）も今までどおり飛ぶ。
