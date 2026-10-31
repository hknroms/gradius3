# テストモードの小機能ごとの大きさ（#41、2026-10-31）

純正ROMを、テストモード（DIP の Service Mode を ON）で起動し、1P START で小機能を順に切り替えながら（400フレームごと・16回）、
テストモードの範囲（`$0076C`〜`$010CD`・`$0625E`〜`$0686F`）の読み出しを「そのときの小機能（`$40001`）」ごとに記録する。
起動時の ROM チェック（PC=`$3A2`）の読み出しは除く。小機能の表は `$808`（7つ）。

```bash
# 純正の gradius3.zip を置いたフォルダで
$G3 gradius3 -rompath <純正> -video none -sound none -nothrottle -autoboot_script pages.lua -snapshot_directory snap   # cov.txt（小機能 番地:PC）
```

| `$40001` | 小機能 | 表の入口 | その小機能だけが読んだ |
|---|---|---|---|
| 0 | CHARACTER ROM CHECK | `$824` | 248B |
| 1 | SCREEN CHECK（格子） | `$9AE` | 86B |
| 2 | COLOR TEST | `$9EC` | 444B |
| 3 | IO TEST（入力・DIP の表示） | `$AFA` | 482B |
| 4 | COIN COUNTER TEST | `$B82` | 242B |
| 5 | SOUND TEST | `$CB4` | 286B |
| 6 | DIP SW SELECT（設定の文字での表示） | `$DBA` | 880B |
| — | 2つ以上の小機能が読んだ | | 172B |
| — | この記録では読まれなかった（ほかの設定の文字・使われない分岐など。大半は DIP SW SELECT の文字と思われる） | | 1116B |
