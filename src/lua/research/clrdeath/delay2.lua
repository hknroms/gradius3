-- #32 検証: 面クリア中、指定の升目（サブのアドレス DA）の属性の書き込みを1フレーム遅らせ、その間は古い属性を残す
local m = manager.machine
local sub = m.devices[":sub"].spaces["program"]
local main = m.devices[":maincpu"].spaces["program"]
local rg = m.memory.regions[":maincpu"]
local fr = 0
local RA = tonumber(os.getenv("RESTORE_AT") or "0")
local DL = os.getenv("DELAY") == "1"
local DA = tonumber(os.getenv("DA"), 16); local A0 = DA & ~1
local pend, used = nil, false
local lf = io.open(os.getenv("DLOG"), "w")
D2_N = emu.add_machine_frame_notifier(function()
  fr = fr + 1
  if fr == RA then rg:write_u16(0x7bc4, 0x13fc); rg:write_u16(0x7bc6, 0x0001); rg:write_u16(0x7bc8, 0x0004); rg:write_u16(0x7bca, 0x00a2)
    rg:write_u16(0xae22, 0x13fc); rg:write_u16(0xae24, 0x0001); rg:write_u16(0xae26, 0x0004); rg:write_u16(0xae28, 0x00a2) end
  if pend and fr == pend[1] then sub:write_u8(DA, pend[2]); lf:write(string.format("frame %d: wrote delayed %02x\n", fr, pend[2])); pend = nil end
  if fr >= RA - 4 and fr <= RA + 30 then lf:write(string.format("%d st=%02x ship=%02x x=%04x y=%04x\n", fr, main:read_u8(0x40029), main:read_u8(0x101001), main:read_u16(0x10100a), main:read_u16(0x10100e))) end
  if fr == RA + 30 then lf:close() end
end)
D2_T = sub:install_write_tap(A0, A0 + 1, "dl2", function(o, d, mask)
  if DL and not used and main:read_u8(0x40029) == 7 and fr >= RA then
    used = true
    local old = sub:read_u16(A0)
    local newv = (DA & 1 == 1) and (d & 0xff) or ((d >> 8) & 0xff)
    pend = {fr + 2, newv}
    lf:write(string.format("frame %d: delay write %x=%x (old %04x) mask %x\n", fr + 1, o, d, old, mask))
    return old
  end
end)
dofile(os.getenv("G3RUN2"))
