-- #35 その場復活の確認: メニューから始めて（面・エリア・RESPAWN を書き込み）、何も操作せずに死ぬのを待つ。
-- env: ST=面(1..10) AR=エリア(1..) RSP=0/1 END=終了フレーム SHOTS="f,f,..." SHOTDIR=dir OUTLOG=file
local m = manager.machine
local sysf = m.ioport.ports[":SYSTEM"].fields
local p1 = m.ioport.ports[":P1"].fields
local F = { COIN=sysf["Coin 1"], START=sysf["1 Player Start"], U=p1["P1 Up"], D=p1["P1 Down"], B1=p1["P1 Button 1"], B2=p1["P1 Button 2"] }
local main = m.devices[":maincpu"].spaces["program"]
local ST = tonumber(os.getenv("ST") or "1"); local AR = tonumber(os.getenv("AR") or "1")
local RSP = tonumber(os.getenv("RSP") or "1"); local END = tonumber(os.getenv("END") or "6000")
local logf = io.open(os.getenv("OUTLOG") or "rsp.log", "w")
local shots = {}; for f in (os.getenv("SHOTS") or ""):gmatch("%d+") do shots[tonumber(f)] = true end
local SD = os.getenv("SHOTDIR") or "."
-- 入力: menu_start.sh と同じ（上+B1・下+B1 でメニュー、COIN、START、START、B1×3）
local seq = { {1000,"U",12},{1000,"B1",12},{1040,"D",12},{1040,"B1",12},{1400,"COIN",3},{1495,"U",20},{1500,"START",3},
  {1730,"START",3},{1870,"B1",3},{1950,"B1",3},{2030,"B1",3} }
local frame, last = 0, ""
local function key(k, on) F[k]:set_value(on and 1 or 0) end
emu.register_frame_done(function()
  frame = frame + 1
  for _, s in ipairs(seq) do
    if frame == s[1] then key(s[2], true) elseif frame == s[1] + s[3] then key(s[2], false) end
  end
  if frame == 1700 then main:write_u8(0x103f08, ST); main:write_u8(0x103f0a, AR); main:write_u8(0x103f3e, RSP) end
  local st = string.format("mode=%d pst=%d dead=%d lives=%x ok=%d inv=%d stg=%d b0=%02x",
    main:read_u8(0x40029), main:read_u8(0x101001), main:read_u8(0x400a2), main:read_u8(0x101050),
    main:read_u8(0x103816), main:read_u8(0x103817) > 0 and 1 or 0, main:read_u8(0x101051), main:read_u8(0x101000))
  if frame > 1700 and st ~= last then logf:write(frame, " ", st, string.format(" X=%x", main:read_u32(0x1038de)), "\n"); last = st end
  if shots[frame] then m.video:snapshot() ; logf:write(frame, " snap\n") end
  if frame >= END then logf:close(); m:exit() end
end)
