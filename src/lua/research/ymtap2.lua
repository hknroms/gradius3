-- ステレオ（#66）: YM2151 の $20〜$27（RL/FB/CONNECT）への書き込みを「面ごと・チャンネルごと・RL の値ごと」に数える。
-- 自動プレイは covplay.lua に任せる（env COVPLAY にその場所を入れる）。
-- env: COVPLAY=covplay.lua の場所 / YMOUT=出した表の場所 / ほかは covplay.lua と同じ（INV=1 MOVE=1 END=... など）
-- 注意: MAME の gradius3 はモノラル出力（sound channels = 1）なので、音を聞いて左右は判定できない。ここで数えるのは「書かれた値」だけ。
local cp = os.getenv("COVPLAY"); if cp then dofile(cp) end
local m = manager.machine
local a = m.devices[":audiocpu"].spaces["program"]
local sp = m.devices[":maincpu"].spaces["program"]
local cnt, order, f, reg = {}, {}, 0, 0
local function stage() return (sp:read_u8(0x101051) & 0x0f) + 1 end
G3YT = a:install_write_tap(0xf030, 0xf031, "ym2", function(offset, data, mask)
  if offset == 0xf030 then reg = data & 0xff
  elseif reg >= 0x20 and reg <= 0x27 then
    local st, ch, rl = stage(), reg - 0x20, (data >> 6) & 3
    local k = st .. "," .. ch .. "," .. rl
    if not cnt[k] then cnt[k] = 0; order[#order+1] = { st, ch, rl, k } end
    cnt[k] = cnt[k] + 1
  end
  return data
end)
G3YN = emu.add_machine_frame_notifier(function() f = f + 1 end)
G3YS = emu.add_machine_stop_notifier(function()
  local out = io.open(os.getenv("YMOUT") or "ym2.txt", "w")
  out:write("# YM2151 $20-$27 への書き込み（面ごと・チャンネルごと・RL ごと）\n")
  out:write("# RL: 0=どちらにも出さない 1=片方 2=もう片方 3=両方（どちらが左右かは YM2151 の資料で決める。MAME はモノ出力）\n")
  out:write("#stage ch RL count\n")
  table.sort(order, function(x, y)
    if x[1] ~= y[1] then return x[1] < y[1] end
    if x[2] ~= y[2] then return x[2] < y[2] end
    return x[3] < y[3] end)
  local tot = {}
  for _, e in ipairs(order) do
    out:write(string.format("%d %d %d %d\n", e[1], e[2], e[3], cnt[e[4]]))
    tot[e[3]] = (tot[e[3]] or 0) + cnt[e[4]]
  end
  out:write("#--- RL ごとの合計 ---\n")
  for rl = 0, 3 do out:write(string.format("#RL=%d  %d\n", rl, tot[rl] or 0)) end
  out:write(string.format("#frames %d\n", f))
  out:close()
end)
