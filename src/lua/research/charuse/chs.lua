local m = manager.machine
local sysf = m.ioport.ports[":SYSTEM"].fields
local p1 = m.ioport.ports[":P1"].fields
local F = { COIN=sysf["Coin 1"], START=sysf["1 Player Start"], U=p1["P1 Up"], D=p1["P1 Down"], R=p1["P1 Right"], B1=p1["P1 Button 1"], B2=p1["P1 Button 2"] }
local sp = m.devices[":maincpu"].spaces["program"]
local sub = m.devices[":sub"].spaces["program"]
local ST = tonumber(os.getenv("ST") or "1")
local seq = { {1000,"U",12},{1000,"B1",12},{1040,"D",12},{1040,"B1",12},{1400,"COIN",3},{1495,"U",20},{1500,"START",3} }
local fr = 1700
for i = 1, ST + 1 do table.insert(seq, {fr, "D", 8}); fr = fr + 20 end
table.insert(seq, {fr, "R", 8}); fr = fr + 20
local G = fr + 20
table.insert(seq, {G, "START", 3}); table.insert(seq, {G+140, "B1", 3}); table.insert(seq, {G+220, "B1", 3}); table.insert(seq, {G+300, "B1", 3})
local f = 0; local ref = {}; local nz = {}
local END = tonumber(os.getenv("END") or "12000")
emu.register_frame_done(function()
  f = f + 1
  for _, s in ipairs(seq) do if f == s[1] then F[s[2]]:set_value(1) elseif f == s[1] + s[3] then F[s[2]]:set_value(0) end end
  if f == G - 10 then sp:write_u8(0x103f20, 1) end
  if f > G and f % 15 == 0 then
    for _, base in ipairs({0x24c000, 0x24d000, 0x24e000}) do
      for i = 0, 0x7ff do local a = sub:read_u8(base + 2*i + 1); local lo = sub:read_u8(base + 2*i + 0x4001)
        ref[lo | ((a & 1) << 8) | ((a & 0x1c) << 7)] = true end
    end
  end
  if f > G and f % 120 == 0 then
    for c = 0xc00, 0xfff do if not nz[c] then local b = 0x280000 + c * 32
      for k = 0, 31, 4 do if sub:read_u32(b + k) ~= 0 then nz[c] = true; break end end end end
  end
  if f >= G + END then local o = io.open(os.getenv("OUTLOG"), "w")
    for c = 0, 0xfff do if ref[c] then o:write(string.format("R %03x\n", c)) end end
    for c = 0xc00, 0xfff do if nz[c] then o:write(string.format("N %03x\n", c)) end end
    o:close(); m:exit() end
end)
