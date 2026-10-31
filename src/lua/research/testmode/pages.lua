local m=manager.machine; local sp=m.devices[":maincpu"].spaces["program"]; local f=0
for _,p in pairs(m.ioport.ports) do for n,fl in pairs(p.fields) do if n:find("Service Mode") then fl.user_value=0; print("svc",n) end end end
local ST1=m.ioport.ports[":SYSTEM"].fields["1 Player Start"]
local cov={}; local cpu=m.devices[":maincpu"]; local pcs={}
T=sp:install_read_tap(0x76c,0x10cd,"a",function(o) local pg=sp:read_u8(0x40001); cov[pg]=cov[pg] or {}; local pc=cpu.state["PC"].value; cov[pg][(o&~1)..":"..pc]=true end)
T2=sp:install_read_tap(0x625e,0x686f,"b",function(o) local pg=sp:read_u8(0x40001); cov[pg]=cov[pg] or {}; local pc=cpu.state["PC"].value; cov[pg][(o&~1)..":"..pc]=true end)
Y=emu.add_machine_frame_notifier(function() f=f+1
  local k=(f-600)%400
  if f>600 and k==0 then ST1:set_value(1) elseif f>600 and k==6 then ST1:clear_value() end
  if f>600 and k==300 then m.video:snapshot() end
  if f==600+400*16 then
    local o=io.open("cov.txt","w")
    for pg,t in pairs(cov) do for a,_ in pairs(t) do o:write(pg," ",a,"\n") end end
    o:close(); m:exit() end end)
