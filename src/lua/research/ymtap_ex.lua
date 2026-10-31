-- ステレオ（#66）: 隠し面（EX STAGE）での YM2151 $20〜$27 の書き込みを数える。
-- 改造ROM（MODDIR）のメニューから面を選んで無敵で遊ぶ。env: EXSTG=面番号(11=グラディウス 12=サラマンダ) YMOUT=出力 END=終了フレーム
local STG = tonumber(os.getenv("EXSTG") or "12")
local END = tonumber(os.getenv("END") or "40000")
local m = manager.machine
local a = m.devices[":audiocpu"].spaces["program"]
local sp = m.devices[":maincpu"].spaces["program"]
local sysf = m.ioport.ports[":SYSTEM"].fields
local p1 = m.ioport.ports[":P1"].fields
local F = { COIN=sysf["Coin 1"], START=sysf["1 Player Start"],
  U=p1["P1 Up"], D=p1["P1 Down"], B1=p1["P1 Button 1"], B2=p1["P1 Button 2"] }
local press, release = {}, {}
local function hold(f,k,l) press[f]=press[f] or {}; table.insert(press[f],k)
  release[f+l]=release[f+l] or {}; table.insert(release[f+l],k) end
hold(1200,"U",10); hold(1200,"B1",10); hold(1240,"D",10); hold(1240,"B1",10)
hold(1400,"COIN",8); hold(1500,"U",30); hold(1500,"START",8); hold(1730,"START",8)
local cnt, order, f, reg = {}, {}, 0, 0
local patched, seen = false, {}
G3YT = a:install_write_tap(0xf030, 0xf031, "ymex", function(offset, data, mask)
  if offset == 0xf030 then reg = data & 0xff
  elseif reg >= 0x20 and reg <= 0x27 then
    local ch, rl = reg - 0x20, (data >> 6) & 3
    local k = ch .. "," .. rl
    if not cnt[k] then cnt[k] = 0; order[#order+1] = { ch, rl, k } end
    cnt[k] = cnt[k] + 1
  end
  return data
end)
emu.register_frame_done(function()
  f = f + 1
  if press[f] then for _,k in ipairs(press[f]) do F[k]:set_value(1) end end
  if release[f] then for _,k in ipairs(release[f]) do F[k]:set_value(0) end end
  if f == 700 and not patched then            -- 無敵: 死ぬ処理を潰す（covplay.lua と同じ）
    patched = true
    local rg = m.memory.regions[":maincpu"]
    for a, hx in ("7bc4:4268001a602a4e71,ae22:4268001a60284e71"):gmatch("(%x+):(%x+)") do
      a = tonumber(a, 16)
      for i = 0, #hx // 4 - 1 do rg:write_u16(a + i*2, tonumber(hx:sub(i*4+1, i*4+4), 16)) end
    end
  end
  if f == 1700 then sp:write_u8(0x103f08, STG); sp:write_u8(0x103f20, 1) end   -- 面と無敵
  if f % 4000 == 0 and f >= 2000 then         -- どの面にいるか記録（デモに落ちていないか確かめる）
    seen[#seen+1] = string.format("F%d 面%d 地図%02x 状態%d", f, (sp:read_u8(0x101051) & 0x0f)+1,
      sp:read_u8(0x1039c0), sp:read_u8(0x40029))
  end
  if f > 2000 then                      -- 撃ちながら上下に動く
    F.B2:set_value((f % 6 < 3) and 1 or 0)
    local p = f % 600
    F.U:set_value(p < 150 and 1 or 0); F.D:set_value((p >= 300 and p < 450) and 1 or 0)
  end
  if f >= END then m:exit() end
end)
G3YS = emu.add_machine_stop_notifier(function()   -- 変数に入れないと回収されて呼ばれない
  local out = io.open(os.getenv("YMOUT") or "ymex.txt", "w")
  out:write(string.format("# 隠し面 %d（11=グラディウス 12=サラマンダ）の YM2151 $20-$27\n", STG))
  out:write("#ch RL count\n")
  table.sort(order, function(x,y) if x[1]~=y[1] then return x[1]<y[1] end return x[2]<y[2] end)
  local tot = {}
  for _, e in ipairs(order) do
    out:write(string.format("%d %d %d\n", e[1], e[2], cnt[e[3]]))
    tot[e[2]] = (tot[e[2]] or 0) + cnt[e[3]]
  end
  out:write("#--- RL ごとの合計 ---\n")
  for rl = 0, 3 do out:write(string.format("#RL=%d  %d\n", rl, tot[rl] or 0)) end
  out:write(string.format("#frames %d\n", f))
  out:write("#--- どの面にいたか ---\n")
  for _, l in ipairs(seen) do out:write("#" .. l .. "\n") end
  out:close()
end)
