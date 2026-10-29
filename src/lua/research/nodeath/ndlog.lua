-- NO DEATH（#36）の確認: 30フレームごとに 状態・残り時間($103e10)・クレジット($40034)・ポーズ(MB+6)・無敵(MB+$20)・残機・ハイスコア
-- NDPOKE="f:val" で f フレームに残り時間を書く（16進）。ほかは G3RUN（g3run.lua）に渡す
local m=manager.machine; local sp=m.devices[":maincpu"].spaces["program"]; local f=0
local pk={}
local w32={}   -- W32="f:addr:val,..." で f フレームに32ビット書く（16進。例 ハイスコアを 0 に: 2500:40058:0）
for a,b,c in (os.getenv("W32") or ""):gmatch("(%d+):(%x+):(%x+)") do w32[tonumber(a)]={tonumber(b,16),tonumber(c,16)} end
for a,b in (os.getenv("NDPOKE") or ""):gmatch("(%d+):(%x+)") do pk[tonumber(a)]=tonumber(b,16) end
ND=emu.add_machine_frame_notifier(function() f=f+1
  if w32[f] then sp:write_u32(w32[f][1], w32[f][2]) end
  if pk[f] then sp:write_u32(0x103e10, pk[f]) end
  if f%30==0 then print(string.format("ND %d st=%x/%x mode=%x left=%d cred=%x paus=%x inv=%x lives=%x score=%08x hi=%08x x=%04x",
    f, sp:read_u8(0x40029), sp:read_u8(0x4002b), sp:read_u8(0x103f0b), sp:read_u32(0x103e10), sp:read_u8(0x40034), sp:read_u8(0x103f06),
    sp:read_u8(0x103f20), sp:read_u8(0x101050), sp:read_u32(0x101054), sp:read_u32(0x40058), sp:read_u32(0x1038de)>>16)) end end)
dofile(os.getenv("G3RUN"))
