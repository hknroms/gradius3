local m=manager.machine; local sp=m.devices[":maincpu"].spaces["program"]; local f=0; local lg=io.open(os.getenv("OLOG"),"w"); local last=""; local t7=nil
local ST1=m.ioport.ports[":SYSTEM"].fields["1 Player Start"]
HOLDF=tonumber(os.getenv("HOLDF") or "0")   -- 押し始めるフレーム（状態7の少し前）
local SN={}; for x in (os.getenv("SNAPF") or ""):gmatch("%d+") do SN[tonumber(x)]=true end
TAP=sp:install_write_tap(0xe8000,0xe8001,"snd",function(o,d,mk) lg:write(string.format("f=%d snd=%02x\n",f,d&0xff)) end)
local PRESS=tonumber(os.getenv("PRESS") or "0")
local HOLD=tonumber(os.getenv("HOLD") or "0")   -- HOLD=n: 状態7に入る前（START 表示の前の面の途中）から START を押したままにして、状態7に入って n フレーム後に離す（押したままエンディングに入った場合。#63 alamone さんの指摘）
Y=emu.add_machine_frame_notifier(function() f=f+1
  local st=sp:read_u8(0x40029)
  if st==7 and not t7 then t7=f end
  if t7 and PRESS>0 then
    if f==t7+PRESS-5 then sp:write_u8(0x103f07,1) end
    if f>=t7+PRESS and f<t7+PRESS+10 then ST1:set_value(1) elseif f==t7+PRESS+10 then ST1:clear_value() end
  end
  if HOLD>0 then
    if f==HOLDF then sp:write_u8(0x103f07,1); ST1:set_value(1) end
    if t7 and f==t7+HOLD then ST1:clear_value() end
  end
  if SN[f] then m.video:snapshot() end
  local s=string.format("29=%02x 2b=%02x 2d=%02x map=%02x es=%02x",st,sp:read_u8(0x4002b),sp:read_u8(0x4002d),sp:read_u8(0x1039c0),sp:read_u8(0x103e2e))
  if s~=last then last=s; lg:write("f="..f.." "..s.."\n"); lg:flush() end end)
dofile(os.getenv("NEXT0"))
