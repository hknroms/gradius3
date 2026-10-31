-- #70 確認: メニュー確定後の ND_LEFT・ND_TIME・残機・ND_BONUS・FIX31 を記録。DSWCLR=80 などで DSW1 のビットを 0(=ON) にする
local m = manager.machine
local main = m.devices[":maincpu"].spaces["program"]
local clr = tonumber(os.getenv("DSWCLR") or "0", 16)
if clr ~= 0 then
  tap = main:install_read_tap(0xd0000, 0xd0001, "dsw", function(o, d, mk)
    if o == 0xd0000 and (mk & 0xff) ~= 0 then return d & ~clr end end)
end
local f = 0
local OUT = io.open(os.getenv("OLOG"), "w")
emu.register_frame_done(function()
  f = f + 1
  if f % 100 == 0 or f == 1760 or f == 1800 then
    OUT:write(string.format("f%d run=%02x mode=%02x ndl=%08x ndt=%08x lives=%02x bonus=%02x fix31=%02x dsw=%02x st=%02x e3a=%04x e36=%04x\n", f,
      main:read_u8(0x103f07), main:read_u8(0x103f0b), main:read_u32(0x103e10), main:read_u32(0x103e1c),
      main:read_u8(0x101050), main:read_u8(0x103e20), main:read_u8(0x103e21), main:read_u8(0x103814), main:read_u8(0x40029), main:read_u16(0x103e3a), main:read_u16(0x103e36)))
    OUT:flush()
  end
end)
dofile(os.getenv("NEXT0"))
