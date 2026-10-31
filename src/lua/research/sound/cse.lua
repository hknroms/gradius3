local m=manager.machine; local sp=m.devices[":maincpu"].spaces["program"]; local f=0; local lg=io.open(os.getenv("OLOG"),"w"); local prev={}
TAP=sp:install_write_tap(0xe8000,0xe8001,"snd",function(o,d,mk) if (d&0xff)==0x0e then lg:write(string.format("f=%d SE\n",f)) end end)
Y=emu.add_machine_frame_notifier(function() f=f+1
  for i=0,31 do local a=0x102320+i*0x50; local r=sp:read_u8(a+0x2a); local live=sp:read_u8(a)~=0 and sp:read_u16(a+0x28)==0x3301
    local x=((sp:read_u32(a+8)-sp:read_u32(0x1038de))>>8)&0xffff; if x>=0x8000 then x=x-0x10000 end
    if live and r==1 and prev[i]==0 then lg:write(string.format("f=%d react slot%d x=%d\n",f,i,x)) end
    prev[i]=live and r or nil end end)
dofile(os.getenv("NEXT0"))
