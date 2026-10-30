local m=manager.machine; local sp=m.devices[":maincpu"].spaces["program"]; local f=0; local lg=io.open(os.getenv("OLOG"),"w"); local lx=-1
Y=emu.add_machine_frame_notifier(function() f=f+1
  if sp:read_u8(0x1039c0)~=13 then return end
  local x=sp:read_u32(0x1038de)>>8
  if x//32~=lx then lx=x//32; lg:write(string.format("%04x camY=%05x mode=%02x plY=%05x st=%d\n",x,sp:read_u32(0x1038e2),sp:read_u8(0x40082),sp:read_u32(0x10100c),sp:read_u8(0x101001))) lg:flush() end
  if x>=0x1c00 then lg:close(); m:exit() end end)
dofile(os.getenv("NEXT0"))
