local m=manager.machine; local sp=m.devices[":maincpu"].spaces["program"]; local f=0; local lg=io.open(os.getenv("OLOG"),"w")
local X=tonumber(os.getenv("PX"),16); local Yv=tonumber(os.getenv("PY"),16); local A=11418; local B=11445; local die=nil
Y6=emu.add_machine_frame_notifier(function() f=f+1
  if f>=A-3 and sp:read_u8(0x40029)==5 then sp:write_u32(0x101008,sp:read_u32(0x1038de)+((X-0x30)<<8)); sp:write_u32(0x10100c,Yv<<8) end
  if not die and f>A and sp:read_u8(0x101001)==4 then die=f end
  if f==B then lg:write(string.format("%02x %02x %s\n",X,Yv,die and ("DIE "..die) or "ok")); lg:close(); m:exit() end end)
dofile(os.getenv("NEXT0"))
