-- 純正サブ: 地形を描く 7cc2 / 7dae の呼び出しを、ROM の空きに置いた記録の差し込みで横取りして記録する
local m=manager.machine; local sub=m.devices[":sub"]; local ss=sub.spaces["program"]; local sp=m.devices[":maincpu"].spaces["program"]
local f=0; local lg=io.open(os.getenv("OLOG"),"w"); local patched=false; local cur={}; local stopf=nil; local hi=nil
local function W(rg,a,hx) for i=0,#hx//4-1 do rg:write_u16(a+i*2,tonumber(hx:sub(i*4+1,i*4+4),16)) end end
local P=0x103400
T=ss:install_write_tap(P,P+3,"rec",function(o,d,mk)
  if o==P then hi=d else local v=((hi or 0)<<16)|d; table.insert(cur,v)
    if #cur==5 then lg:write(string.format("C f=%d t=%x d6=%08x d7=%08x d4=%08x a5=%08x cam=%08x\n",f,cur[1],cur[2],cur[3],cur[4]&0xffff,cur[5],ss:read_u32(0x2038de))); cur={} end end end)
F=emu.add_machine_frame_notifier(function() f=f+1
  if not patched and m.time.seconds>12 then patched=true; local rg=m.memory.regions[":sub"]
    -- サブ ROM はバイト入れ替えの並びかもしれないので、読んで確かめる
    local S=0x3f000
    local stubA="23fccc000001001034002" -- placeholder
    local function stub(base,marker,target)
      local h=string.format("23fc%08x%08x",marker,P)..string.format("23c6%08x",P)..string.format("23c7%08x",P)..string.format("23c4%08x",P)..string.format("23cd%08x",P)..string.format("4ef9%08x",target)
      W(rg,base,h) end
    stub(S,0xcc000001,0x7cc2); stub(S+0x40,0xcc000002,0x7dae)
    W(rg,0xae40,string.format("4eb9%08x",S)); W(rg,0xaf64,string.format("4eb9%08x",S)); W(rg,0xafe6,string.format("4eb9%08x",S+0x40))
    lg:write(string.format("patched check ae40=%04x%04x\n",ss:read_u16(0xae40),ss:read_u16(0xae42)))
  end
  local p=sp:read_u32(0x1038f0)
  if not stopf and p>=0x5a000 and p<0x70000 then stopf=f; lg:write(string.format("STOP f=%d cam=%08x camy=%08x f4=%08x\n",f,sp:read_u32(0x1038de),sp:read_u32(0x1038e2),sp:read_u32(0x1038f4))) end
  if stopf and f==stopf+60 then lg:close(); m:exit() end end)
dofile(os.getenv("NEXT0"))
