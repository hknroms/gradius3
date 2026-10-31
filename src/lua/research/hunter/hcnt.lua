local m = manager.machine
local sysf = m.ioport.ports[":SYSTEM"].fields
local p1 = m.ioport.ports[":P1"].fields
local F = { COIN=sysf["Coin 1"], START=sysf["1 Player Start"], U=p1["P1 Up"], D=p1["P1 Down"], R=p1["P1 Right"], B1=p1["P1 Button 1"], B2=p1["P1 Button 2"] }
local sp = m.devices[":maincpu"].spaces["program"]
local ST = tonumber(os.getenv("ST"))
local seq = { {1000,"U",12},{1000,"B1",12},{1040,"D",12},{1040,"B1",12},{1400,"COIN",3},{1495,"U",20},{1500,"START",3} }
local fr = 1700
for i = 1, ST + 1 do table.insert(seq, {fr, "D", 8}); fr = fr + 20 end
for i = 1, tonumber(os.getenv("RI") or "1") do table.insert(seq, {fr, "R", 8}); fr = fr + 20 end
local G = fr + 20
table.insert(seq, {G, "START", 3}); table.insert(seq, {G+140, "B1", 3}); table.insert(seq, {G+220, "B1", 3}); table.insert(seq, {G+300, "B1", 3})
local f, cnt, tot, started, bossf = 0, 0, 0, false, nil
local lg = io.open(os.getenv("OUTLOG"), "w")
local XEND = tonumber(os.getenv("XEND") or "0", 16)
emu.register_frame_done(function()
  f = f + 1
  for _, s in ipairs(seq) do
    if f == s[1] then F[s[2]]:set_value(1) elseif f == s[1] + s[3] then F[s[2]]:set_value(0) end
  end
  if f == G - 10 then sp:write_u8(0x103f20, 1) end
  local opt = sp:read_u8(0x101068) & 7
  if not started and f > G + 320 and sp:read_u16(0x10101e) ~= 0 then started = true; stg0 = sp:read_u8(0x101051); lg:write(string.format("start f=%d stage=%d e5b=%d\n", f, stg0, sp:read_u8(0x42e5b))) ; eqf = f + 60 end
  if eqf and f == eqf then F.START:set_value(1) elseif eqf and f == eqf + 4 then F.START:set_value(0) end
  if f % 6 < 3 then F.B2:set_value(1) else F.B2:set_value(0) end
  if started then
    tot = tot + 1
    local ok = sp:read_u8(0x42e53) == 0 and (sp:read_u8(0x1039c3) ~= 0 or sp:read_u8(0x42e5b) >= 3) and sp:read_u8(0x103f06) == 0
    if ok then cnt = cnt + 1 end
    local x = sp:read_u32(0x1038de)
    if tot % 600 == 0 then lg:write(string.format("f=%d tot=%d cnt=%d opt=%d x=%x e53=%d e70=%04x st=%d\n", f, tot, cnt, opt, x, sp:read_u8(0x42e53), sp:read_u16(0x42e70), sp:read_u8(0x40029))) end
    local e = sp:read_u8(0x42e53)
    if e ~= (pe or 0) then lg:write(string.format("E53 %d->%d f=%d tot=%d cnt=%d x=%x stg=%d\n", pe or 0, e, f, tot, cnt, x, sp:read_u8(0x101051))); pe = e; es = f end
    if e ~= 0 and es and f - es > 4000 then lg:write("STUCK\n"); lg:close(); m:exit() end
    if sp:read_u8(0x101051) ~= stg0 then lg:write(string.format("NEXTSTAGE f=%d tot=%d cnt=%d\n", f, tot, cnt)); lg:close(); m:exit() end
    if XEND > 0 and x >= XEND then lg:write(string.format("XEND f=%d tot=%d cnt=%d x=%x\n", f, tot, cnt, x)); lg:close(); m:exit() end
  end
  if f > 80000 then lg:close(); m:exit() end
end)
