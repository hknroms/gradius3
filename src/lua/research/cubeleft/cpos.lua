-- キューブの出る高さを決まった並びにし、くっついた位置（画面の座標）を記録する（#2 の検証と同じやり方）
local m=manager.machine; local mc=m.devices[":maincpu"]; local sp=mc.spaces["program"]; local sub=m.devices[":sub"]; local ss=sub.spaces["program"]
local SEQ={3,9,12,1,6,14,4,10,7,0,13,2,11,5,15,8}; local n=0; local f=0; local on=false; local lg=io.open(os.getenv("OLOG"),"w"); local k=0
RT=sp:install_read_tap(0x40032,0x40033,"cr",function(o,d,mk)
  if not on then return end
  local pc=mc.state["CURPC"].value
  if (pc>=0x26238 and pc<0x26244) or (pc>=0x103a00 and pc<0x103c00) then
    local idx=SEQ[(n%16)+1]
    local r=d
    if mk&0xff00~=0 then r=(r&0x00ff)|((idx*4)<<8) end
    if mk&0x00ff~=0 then r=r&0xff00; if pc>=0x2623e and pc<0x26244 then n=n+1; lg:write(string.format('SP n=%d f=%d\n',n,f)) end end
    return r
  end end)
WT=ss:install_write_tap(0x202320,0x2037ff,"cs",function(o,d,mk)
  if not on then return end
  local r=(o-0x202320)%0x50; if r~=0x26 then return end
  local a=o-0x26; if ss:read_u16(a+0x28)~=0x3301 then return end
  if (mk&0xff00~=0 and (d>>8)&0xff==1) then k=k+1
    lg:write(string.format("K %d f=%d x=%d y=%d\n",k,f,(ss:read_u32(a+8)-ss:read_u32(0x2038de))>>8,(ss:read_u32(a+12)-ss:read_u32(0x2038e2))>>8)); lg:flush() end end)
F=emu.add_machine_frame_notifier(function() f=f+1
  local p=sp:read_u32(0x1038f0); if p>=0x58000 and p<0x70000 then on=true end
  if k>=60 then lg:close(); m:exit() end end)
dofile(os.getenv("NEXT0"))
