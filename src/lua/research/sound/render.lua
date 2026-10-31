local m=manager.machine; local sp=m.devices[":maincpu"].spaces["program"]; local f=0
for _,p in pairs(m.ioport.ports) do for n,fl in pairs(p.fields) do if n:find("Demo") then fl.user_value=fl.defvalue==0 and 1 or 0; print("demo field",n) end end end
local codes={}; for c in (os.getenv("CODES") or ""):gmatch("%x+") do table.insert(codes,tonumber(c,16)) end
local T0=tonumber(os.getenv("T0") or "1200"); local GAP=tonumber(os.getenv("GAP") or "150")
local function send(c) local a=sp:read_u32(0x40020); sp:write_u8(a,c); a=a+1; if a>0x403bf then a=0x40380 end; sp:write_u32(0x40020,a) end
local lg=io.open("render.log","w")
TAP=sp:install_write_tap(0xe8000,0xe8001,"snd",function(o,d,mk) lg:write(string.format("f=%d snd=%02x\n",f,d&0xff)) end)
Y=emu.add_machine_frame_notifier(function() f=f+1
  for i,c in ipairs(codes) do if f==T0+(i-1)*GAP then send(c) end end
  if f==T0+#codes*GAP+30 then lg:close(); m:exit() end end)
