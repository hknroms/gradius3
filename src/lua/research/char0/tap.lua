local m=manager.machine; local ss=m.devices[":sub"].spaces["program"]; local sp=m.devices[":maincpu"].spaces["program"]; local cpu=m.devices[":sub"]; local f=0; local lg=io.open(os.getenv("OLOG"),"w"); local seen={}; local b0=nil
T=ss:install_write_tap(0x280000,0x28001f,"c0",function(o,d,mk) local pc=cpu.state["PC"].value; local k=string.format("%x",pc); if not seen[k] then seen[k]=1; lg:write(string.format("f=%d pc=%x addr=%x data=%x st=%02x\n",f,pc,o,d,sp:read_u8(0x40029))); lg:flush() end end)
Y=emu.add_machine_frame_notifier(function() f=f+1
  if f==1000 then b0=ss:read_range(0x280000,0x28001f,8) end
  if b0 and f%500==0 then local c=ss:read_range(0x280000,0x28001f,8); if c~=b0 then lg:write("f=",f," CHAR0 CHANGED\n"); lg:flush(); b0=c end end end)
dofile(os.getenv("NEXT0"))
