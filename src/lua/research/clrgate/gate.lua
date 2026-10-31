local m=manager.machine; local sp=m.devices[":maincpu"].spaces["program"]; local f=0; local lg=io.open(os.getenv("OLOG"),"w"); local t5=nil; local last=-1; local on=false
TAP=sp:install_write_tap(0x40082,0x40083,"ev",function(o,d,mk) if on and o==0x40082 and (mk&0xff00)~=0 then lg:write(string.format("f=%d w82=%02x x=%06x\n",f,(d>>8)&0xff,sp:read_u32(0x1038de)>>8)) end end)
Y=emu.add_machine_frame_notifier(function() f=f+1
  local st=sp:read_u8(0x40029)
  if st==2 and f>2040 then on=true end
  if st~=last then last=st; if on then lg:write(string.format("f=%d st=%d x=%06x c0=%08x\n",f,st,sp:read_u32(0x1038de)>>8,sp:read_u32(0x400c0))) end end
  if st==5 and not t5 then t5=f end
  if t5 and f>t5+tonumber(os.getenv("PLAY") or "600") then lg:close(); m:exit() end end)
dofile(os.getenv("NEXT0"))
