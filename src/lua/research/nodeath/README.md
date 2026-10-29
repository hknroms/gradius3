# NO DEATH モード（#36）の確かめ方

`ndlog.lua` は30フレームごとに、状態・MODE・残り時間（`$103e10`）・クレジット・ポーズ・無敵・残機・点数・ハイスコアを出す。
`NDPOKE="f:値"` で f フレームに残り時間（16進）を書く（10分待たずに終わりを見る）。`W32="f:番地:値"` で32ビット書く（ハイスコアを 0 にするなど）。

```bash
L=<リポジトリ>/src/lua; N=$L/research/nodeath; M=<改造のビルド>/mame
B="1400:COIN,1730:START,1870:B1,1950:B1,2030:B1"; P="1700:103f08:1,1700:103f0a:1,1700:103f0b:1"   # 1面A・MODE=1（NO DEATH）
# A: 残り 2000 フレームにして、0 でゲームオーバー（状態 8）になるか
G3RUN=$L/g3run.lua NDPOKE="3000:7d0" SEQ="$B" HOLDK="1495:U:20,1500:START:5" POKE="$P" END=5600 bash $L/run.sh $M $N/ndlog.lua x
# B: 途中でコインを入れて START → クレジットが1減って残りが +36000
G3RUN=$L/g3run.lua NDPOKE="3000:7d0" SEQ="$B,3500:COIN,3600:START" HOLDK="1495:U:20,1500:START:5" POKE="$P" END=4200 bash $L/run.sh $M $N/ndlog.lua x
# C: ポーズ（START 長押し）の間は残りが減らない
G3RUN=$L/g3run.lua SEQ="$B" HOLDK="1495:U:20,1500:START:5,3500:START:70" POKE="$P" END=4500 bash $L/run.sh $M $N/ndlog.lua x
# ハイスコア: MODE を 0（NORMAL・無敵 POKE 1700:103f20:1）と 1 で比べる。W32="2500:40058:0" でハイスコアを 0 にして撃ち続ける
```

MODE の値は v0.5.1 から 0=NORMAL 1=NO DEATH 2=CUBE RUSH 3=BOSS RUSH（以前のスクリプトの `103f0b:1`＝キューブラッシュは `:2` に読み替える）。
