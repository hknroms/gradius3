local m=manager.machine; local sp=m.devices[":maincpu"].spaces["program"]; local ss=m.devices[":sub"].spaces["program"]; local f=0; local lg=io.open(os.getenv("OLOG"),"w"); local last=""
TAP=sp:install_write_tap(0xe8000,0xe8001,"snd",function(o,d,mk) if (d&0xff)~=0 and (d&0xff)~=1 then lg:write(string.format("f=%d snd=%02x\n",f,d&0xff)) end end)
Y=emu.add_machine_frame_notifier(function() f=f+1
  local s=string.format("unlk=%02x req=%02x 40005=%02x lk=%02x%02x%02x p1=%02x run=%02x",sp:read_u8(0x103f02),sp:read_u8(0x103f03),sp:read_u8(0x40005),ss:read_u8(0x103760),ss:read_u8(0x103761),ss:read_u8(0x103762),sp:read_u8(0x103f00),sp:read_u8(0x103f07))
  if s~=last then last=s; lg:write("f="..f.." "..s.."\n"); lg:flush() end end)
dofile(os.getenv("NEXT0"))
