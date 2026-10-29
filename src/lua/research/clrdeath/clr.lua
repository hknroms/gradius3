-- #32: 面クリア（$40029=7）を見つけたら tc..tc+N の vram/chr/shr をダンプ、サブの B 面への書き込みとメインの判定時刻を記録
local m = manager.machine
local main = m.devices[":maincpu"].spaces["program"]
local sub = m.devices[":sub"].spaces["program"]
local D = os.getenv("CLRDIR"); local N = tonumber(os.getenv("CLRN") or "12")
local fr, last, tc, cnt = 0, 0, nil, 0
local lf = io.open(D .. "/tap.log", "w")
local function on() return tc and fr + 1 >= tc and fr + 1 <= tc + N end
local function dump(k)
  for _, r in ipairs({{"vram", 0x14c000, 0x153fff}, {"chr", 0x180000, 0x19ffff}, {"shr", 0x100000, 0x103fff}}) do
    local o = io.open(string.format("%s/%s_%d.bin", D, r[1], k), "wb"); o:write(main:read_range(r[2], r[3], 8)); o:close() end
end
CL_N = emu.add_machine_frame_notifier(function()
  fr = fr + 1
  local st = main:read_u8(0x40029)
  if st == 7 and last ~= 7 and not tc then tc = fr
    lf:write(string.format("CLEAR frame %d stage=%d loop=%d prog=%04x map=%02x\n", fr, main:read_u8(0x101051) + 1, main:read_u8(0x101063), main:read_u16(0x101052), main:read_u8(0x1039c0))) end
  if fr % 600 == 0 then lf:write(string.format("f %d st=%x stage=%d prog=%04x\n", fr, st, main:read_u8(0x101051)+1, main:read_u16(0x101052))); lf:flush() end
  if tc and fr >= tc - 1 and fr <= tc + N then dump(fr - tc); lf:write(string.format("---- end t=%+d time=%s\n", fr - tc, tostring(m.time))) end
  if tc and fr == tc + N then lf:close(); m:exit() end
  last = st
end)
CL_T1 = sub:install_write_tap(0x24c000, 0x253fff, "clv", function(o, d, mk)
  if on() then lf:write(string.format("S %d %x %x %x %s\n", fr + 1 - tc, o, d, mk, tostring(m.time))) end end)
CL_T2 = main:install_write_tap(0x1039d0, 0x1039d1, "clk", function(o, d) if on() then lf:write(string.format("CHK %d %s\n", fr + 1 - tc, tostring(m.time))) end end)
dofile(os.getenv("CLRNEXT"))
