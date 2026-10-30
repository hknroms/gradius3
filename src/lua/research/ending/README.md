# エンディングのスキップ（#63）

改造ROMで、純正どおり 10面の途中（進行度 $2341）から無敵で遊んでエンディングまで進め、状態7（$40029）・小状態（$4002B）・段階（$4002D）・サブの印（$103E2E）・音の命令（$E8000）を記録する。
PRESS=n なら、状態7に入って n フレーム後に MB_RUN（$103F07）を立てて 1P START を10フレーム押す（メニューから始めたのと同じ扱いにするため）。

```bash
L=<リポジトリ>/src/lua
OLOG=es.log PRESS=900 SNAPF="12500,12900" NEXT0=$L/research/cov/covplay.lua COVOUT=c.bin STG=10 PROG=2341 LOOP=1 INV=1 MOVE=1 END=13400 bash $L/run.sh <改造>/mame $L/research/ending/skip.lua out
```
