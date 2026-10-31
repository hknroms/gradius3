# メインの空きを作る：改造のコードの一部をサブに寄せる（#70）

メニュー確定の後の ND_LEFT（`$103E10`）・ND_TIME（`$103E1C`）・残機（`$101050`）・ND_BONUS（`$103E20`）・FIX31（`$103E21`）と、
キューブの1個目の瞬間のカウンタ（`$103E3A`）を100フレームごとに記録する。`DSWCLR=80` で DSW1 bit7 を ON（0）に、`DSWCLR=10` で SW1:5 を ON にする
（`$D0000-1` の読み取りタップで値を書き換える。MAME の DIP 設定を lua から変えるより確実）。

```bash
L=<リポジトリ>/src/lua
# MODE を変えて（0〜3）、DSW1 bit7 の OFF/ON で比べる
OLOG=m2-d80.log DSWCLR=80 NEXT0=$L/g3run.lua SEQ="1400:COIN,1730:START" HOLDK="1495:U:20,1500:START:5" POKE="1700:103f0b:2" END=2400 bash $L/run.sh <ROM>/mame $L/research/subshift/nd.lua x
# START だけ（メニューなし）で FIX31 を見る
OLOG=st-d10.log DSWCLR=10 NEXT0=$L/g3run.lua SEQ="1400:COIN,1500:START" END=2400 bash $L/run.sh <ROM>/mame $L/research/subshift/nd.lua x
```

結果（2026-10-31）：移す前と後のビルドで、MODE 0〜3 × DSW1 bit7 OFF/ON の16通りとも ND_LEFT・ND_TIME・残機が同じ
（OFF＝36000・キューブラッシュ 3→8、ON＝18000・3→5。**DSW ON 側は今回はじめて確かめられた**）。
キューブラッシュ（H5 S2 T7）で1個目のカウンタも同じ（`$0594`）。FIX31 はメニューから＝1、START だけ＝SW1:5 OFF で 1・ON で 0。
