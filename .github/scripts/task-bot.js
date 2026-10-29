// 共同作業ボット: Issue コメントのコマンドで、作業タスクの状態・確認項目・提出物を記録する。
// .github/workflows/task-bot.yml から actions/github-script で呼ばれる。
//
// 作業の種類（ラベル）: 検証 / 調査 / 実装 / 素材 / 資料
// 状態（ラベル）      : 未着手 → 担当中 → 確認待ち → 完了（人の確認が必要なものは 要人間確認）
//
// コマンド（コメントの行頭に書く。1つのコメントに複数行書いてよい）
//   /claim [ai|人]           担当する（ai = AI が作業する／人 = 人が作業する。まとめページに出る。claude も ai と同じ）
//                            AI 用に予約された担当（/claim ai）は、別のアカウントの AI が /claim ai で引き継げる
//   /check 番号 ok|ng|hold   確認項目に結果を付ける（hold = 人の目で確認が必要）
//   /submit URL [ひとこと]   成果物を提出する（自分のフォークの枝・コミット・PR などの GitHub の URL）
//   /done [ひとこと]         終わり。検証は ok だけなら完了、ng/hold/未チェックがあれば要人間確認。
//                            検証以外は「確認待ち」（管理者が /accept すると完了）
//   /human [ひとこと]        人の判断が必要なので「要人間確認」にする
//   /release                 担当をやめて「未着手」に戻す
//   ── 管理者のみ ──
//   /items                   次の行からの箇条書きを確認項目として追加し、タスクにする
//   /type 種類               作業の種類を変える（検証・調査・実装・素材・資料）
//   /accept [ひとこと]       提出物を取り込んだ／確認できた → 完了
//   /reject ひとこと         直してほしい点を伝えて「担当中」に戻す
//   /fixed 版 [ひとこと]     （どの Issue でも）その版で直した → 閉じる。配布ページの「報告の状況」に「v0.4.17 で直しました」と出る
//   /wontfix 理由            （どの Issue でも）見送る → 閉じる。配布ページには「見送り」と出る
//   /later [理由]            （どの Issue でも）後の版でやる → ラベル「後の版」。まとめページで「後の版（今はやらなくてよい）」に分ける。配布ページには出さない
//   /now                     「後の版」をやめて、元の状態に戻す
//
// 直ったかの確認（コマンドではなく、テストプレイ報告のフォームから）:
//   配布ページの「確かめてほしいこと」（/fixed した報告）のボタンから報告を送ると、「確認した元の報告」「確認の結果」が入っている。
//   直っていた → 元の報告に「確認済み」を記録 / まだおかしい → 元の報告を開き直して「未着手」に戻す。どちらも確認の報告自体は閉じる。

const TYPES = ['検証', '調査', '実装', '素材', '資料'];
const REQUEST = '要望';
const LATER = '後の版';
const REQUEST_ITEMS = [
  '書かれている現象・要望について、今の版での動きを確かめる（再現手順も書く）',
  '純正（改造なし）ではどうなるかと比べる',
  '直し方・変え方の案と、影響しそうなところをまとめる',
];

const L = { todo: '未着手', doing: '担当中', review: '確認待ち', human: '要人間確認', done: '完了' };
const STATUS = [L.todo, L.doing, L.review, L.human, L.done];
const LABEL_DEFS = [
  { name: '検証', color: '1f6feb', description: '作業: テストプレイ・動作の検証' },
  { name: '調査', color: '8250df', description: '作業: ROMの解析・原因調査' },
  { name: '実装', color: '0e8a16', description: '作業: 改造・修正のコードを書く' },
  { name: '素材', color: 'e16f24', description: '作業: 画像・パレット・タイル・文字など' },
  { name: '資料', color: '0969da', description: '作業: 説明書・翻訳・ページ' },
  { name: REQUEST, color: 'fbca04', description: '改善したいこと（協力者の声・人から聞いた話）。自動で検証タスクになる' },
  { name: L.todo, color: 'bfbfbf', description: 'まだ誰も担当していない' },
  { name: L.doing, color: 'd29922', description: '担当者が作業中' },
  { name: L.review, color: '1d76db', description: '提出済み・管理者の確認待ち' },
  { name: L.human, color: 'f85149', description: '人の目・判断が必要' },
  { name: L.done, color: '3fb950', description: '完了' },
  { name: LATER, color: 'c5c5c5', description: '後の版でやる（今はやらなくてよい）' },
];
const RENAMES = [['検証済み', L.done]];
const STALE_DAYS = 3;
const MARK = /<!-- (?:verify|task)-state (\{[^]*?\}) -->/;
const ITEM = /^(\s*)- \[( |x|X)\] (.*)$/;
const MARKS = { ok: '✅', ng: '❌', hold: '⚠️' };
const MARK_PREFIX = /^(✅|❌|⚠️) /;
const HIST_MAX = 40;

function getState(body) {
  const m = (body || '').match(MARK);
  if (!m) return {};
  try { return JSON.parse(m[1]); } catch { return {}; }
}
function cleanStr(v) { return String(v).replace(/--/g, '—').replace(/[<>]/g, '').slice(0, 300); }
function setState(body, st) {
  const clean = JSON.parse(JSON.stringify(st, (k, v) => (typeof v === 'string' ? cleanStr(v) : v)));
  const s = `<!-- task-state ${JSON.stringify(clean)} -->`;
  body = body || '';
  return MARK.test(body) ? body.replace(MARK, s) : body.replace(/\s*$/, '') + '\n\n' + s + '\n';
}
function items(body) {
  const out = [];
  (body || '').split('\n').forEach((line, i) => {
    const m = line.match(ITEM);
    if (m) {
      const text = m[3];
      const mk = (text.match(MARK_PREFIX) || [])[1] || '';
      out.push({ line: i, checked: m[2] !== ' ', mark: mk, text: text.replace(MARK_PREFIX, '') });
    }
  });
  return out;
}
function checkItem(body, n, result) {
  const lines = body.split('\n');
  const it = items(body)[n - 1];
  if (!it) return null;
  const indent = lines[it.line].match(ITEM)[1];
  lines[it.line] = `${indent}- [${result === 'hold' ? ' ' : 'x'}] ${MARKS[result]} ${it.text}`;
  return lines.join('\n');
}
function summary(body) {
  const list = items(body);
  return {
    total: list.length,
    ok: list.filter(i => i.mark === '✅' || (i.checked && !i.mark)).length,
    ng: list.filter(i => i.mark === '❌').length,
    hold: list.filter(i => i.mark === '⚠️').length,
    open: list.filter(i => !i.checked && i.mark !== '⚠️').length,
  };
}
function section(body, name) {
  const m = (body || '').match(new RegExp('^### ' + name + '\\s*\\n+([^]*?)(?=\\n### |\\n<!--|$)', 'm'));
  const v = m ? m[1].trim() : '';
  return v === '_No response_' ? '' : v;
}
function parseCommands(text) {
  const lines = (text || '').split('\n');
  const cmds = [];
  lines.forEach((raw, i) => {
    // Windows の Git Bash（MSYS）から送ると「/claim」が「C:/Program Files/Git/claim」に化ける → 元に戻す
    const line = raw.trim().replace(/^[A-Za-z]:\/Program Files(?: \(x86\))?\/Git\//i, '/');
    const m = line.match(/^\/(claim|check|submit|done|human|release|items|type|accept|reject|fixed|wontfix|later|now)\b\s*(.*)$/i);
    if (!m) return;
    const c = { name: m[1].toLowerCase(), arg: m[2].trim() };
    if (c.name === 'items') {
      const rest = [];
      for (let j = i + 1; j < lines.length; j++) {
        const t = lines[j].trim();
        if (t.startsWith('/') || /^(-{3,}|\*{3,}|_{3,})$/.test(t)) break;
        const im = t.match(/^(?:[-*]\s+|・\s*|\d+[.)]\s+)(?:\[[ xX]\]\s*)?(.+)$/);
        if (im) rest.push(im[1].trim());
      }
      c.items = rest;
    }
    cmds.push(c);
  });
  return cmds;
}
function typeOf(labels) { return TYPES.find(t => labels.includes(t)) || null; }

module.exports = async ({ github, context, core }) => {
  const { owner, repo } = context.repo;
  const now = new Date().toISOString();

  async function ensureLabels() {
    for (const [from, to] of RENAMES) {
      try { await github.rest.issues.updateLabel({ owner, repo, name: from, new_name: to }); core.info(`renamed ${from} -> ${to}`); } catch {}
    }
    for (const d of LABEL_DEFS) {
      try { await github.rest.issues.createLabel({ owner, repo, ...d }); }
      catch (e) { if (e.status === 422) { try { await github.rest.issues.updateLabel({ owner, repo, ...d }); } catch {} } else throw e; }
    }
  }
  async function setLabels(num, labels, { status, type }) {
    const drop = [];
    if (status) drop.push(...STATUS.filter(l => l !== status));
    if (type) drop.push(...TYPES.filter(t => t !== type));
    for (const l of drop) if (labels.includes(l)) {
      try { await github.rest.issues.removeLabel({ owner, repo, issue_number: num, name: l }); } catch {}
    }
    const add = [status, type].filter(Boolean).filter(l => !labels.includes(l));
    if (add.length) await github.rest.issues.addLabels({ owner, repo, issue_number: num, labels: add });
  }
  const reply = (num, body) => github.rest.issues.createComment({ owner, repo, issue_number: num, body });
  const react = (id, content) => github.rest.reactions.createForIssueComment({ owner, repo, comment_id: id, content }).catch(() => {});
  const push = (st, who, what, extra) => {
    st.history = (st.history || []).concat([{ who, what, at: now, ...(extra || {}) }]).slice(-HIST_MAX);
  };

  const ev = context.eventName;

  if (ev === 'workflow_dispatch') { await ensureLabels(); core.info('labels ok'); }

  if (ev === 'schedule' || ev === 'workflow_dispatch') {
    const list = await github.paginate(github.rest.issues.listForRepo, { owner, repo, state: 'open', labels: L.doing, per_page: 100 });
    for (const is of list) {
      const st = getState(is.body);
      const last = Date.parse(st.updated_at || st.claimed_at || is.updated_at);
      if (Date.now() - last > STALE_DAYS * 86400e3) {
        const who = st.claimer;
        delete st.claimer; delete st.claimed_at; delete st.worker; st.updated_at = now;
        push(st, 'bot', 'timeout', { prev: who });
        await github.rest.issues.update({ owner, repo, issue_number: is.number, body: setState(is.body, st) });
        await setLabels(is.number, is.labels.map(l => l.name), { status: L.todo });
        await reply(is.number, `${STALE_DAYS}日間報告がなかったので「未着手」に戻しました${who ? `（前の担当: @${who}）` : ''}。続ける場合はもう一度 \`/claim\` してください。`);
      }
    }
    return;
  }

  const issue = context.payload.issue;
  if (!issue || issue.pull_request) return;
  const num = issue.number;
  const labels = issue.labels.map(l => l.name);
  let body = issue.body || '';

  // 報告フォームの「版」（最新版／1つ前の版／それ以外）を、実際の版の番号に置き換える（docs/versions.json）
  if (ev === 'issues' && context.payload.action === 'opened' && /^### (版|Version)\s*$/m.test(body) && /^### (版（|Version \()/m.test(body)) {
    let vs = [];
    try { vs = JSON.parse(require('fs').readFileSync((process.env.GITHUB_WORKSPACE || '.') + '/docs/versions.json', 'utf8')).versions.map(v => 'v' + v.version); } catch {}
    const pick = section(body, '版') || section(body, 'Version');
    const typed = section(body, '版（「それ以外」のとき・わかれば）') || section(body, 'Version (if "Other", if you know)');
    let ver = typed;
    if (!ver && /^(最新|Latest)/.test(pick) && vs[0]) ver = vs[0] + '（最新版）';
    else if (!ver && /^(1つ前|Previous)/.test(pick) && vs[1]) ver = vs[1] + '（1つ前の版）';
    if (ver) {
      body = body.replace(/^(### (?:版|Version)\s*\n+)([^\n]*)/m, (m, h) => h + ver);
      await github.rest.issues.update({ owner, repo, issue_number: num, body });
    }
  }

  if (ev === 'issues' && context.payload.action === 'opened') {
    const om = (section(body, '確認した元の報告') || section(body, 'Original report checked')).match(/#?(\d+)/);
    const res = section(body, '確認の結果') || section(body, 'Re-check result');
    const bad = /まだ|おかしい|直って(い)?な|治って(い)?な|still|broken|not/i.test(res);
    const ok = !bad && /直っ|治っ|fixed|ok/i.test(res);
    if (om && +om[1] !== num && (ok || bad)) {
      const on = +om[1];
      const who = issue.user.login;
      const ver = section(body, '版') || section(body, 'Version');
      let o;
      try { o = (await github.rest.issues.get({ owner, repo, issue_number: on })).data; } catch { o = null; }
      if (o && !o.pull_request) {
        const ost = getState(o.body);
        const olabels = o.labels.map(l => typeof l === 'string' ? l : l.name);
        if (ok) {
          ost.confirmed = (ost.confirmed || []).concat([{ by: who, at: now, ver, issue: num }]).slice(-10);
          ost.updated_at = now; push(ost, who, 'confirm');
          await github.rest.issues.update({ owner, repo, issue_number: on, body: setState(o.body, ost) });
          await reply(on, `✅ ${ver || ''} で直っていたと確認がありました（#${num}、@${who} さん）。`);
          await reply(num, `ありがとうございます。#${on} に「確認済み」として記録しました。`);
        } else {
          const was = ost.fixed_in;
          delete ost.fixed_in; delete ost.wontfix; delete ost.claimer; delete ost.claimed_at; delete ost.worker;
          ost.still = { by: who, at: now, ver, issue: num, was: was || '' };
          ost.note = `まだおかしい（${ver || '版不明'}・#${num}）`;
          ost.updated_at = now; push(ost, who, 'still');
          await github.rest.issues.update({ owner, repo, issue_number: on, body: setState(o.body, ost), state: 'open', state_reason: 'reopened' });
          if (typeOf(olabels) || STATUS.some(x => olabels.includes(x))) await setLabels(on, olabels, { status: L.todo, type: null });
          await reply(on, `⚠️ ${ver || ''} でもまだおかしいと報告がありました（#${num}、@${who} さん）。開き直して「未着手」に戻しました。詳しくは #${num} を見てください。`);
          await reply(num, `ありがとうございます。#${on} を開き直して、もう一度直す対象にしました。`);
        }
        await github.rest.issues.update({ owner, repo, issue_number: num, state: 'closed', state_reason: 'completed' });
        return;
      }
    }
  }

  if (ev === 'issues') {
    // テンプレートから作られた・種類ラベルが付いた → 種類と「未着手」を整え、状態欄を用意
    let type = typeOf(labels);
    const picked = section(body, '作業の種類');
    const fromForm = TYPES.find(t => picked.startsWith(t));
    if (fromForm) type = fromForm;
    // 「要望」（改善したいこと）は自動で検証タスクにし、確認項目が無ければ基本の3項目を付ける
    if (labels.includes(REQUEST) && !type) {
      type = '検証';
      if (!items(body).length) {
        body = body.replace(MARK, '').replace(/\s*$/, '') + '\n\n### 確認項目\n' + REQUEST_ITEMS.map(t => '- [ ] ' + t).join('\n') + '\n';
        await github.rest.issues.update({ owner, repo, issue_number: num, body });
      }
    }
    if (!type) return;
    const status = STATUS.find(s => labels.includes(s)) ? null : L.todo;
    await setLabels(num, labels, { status, type });
    if (!MARK.test(body)) await github.rest.issues.update({ owner, repo, issue_number: num, body: setState(body, { created_at: now, history: [{ who: issue.user.login, what: 'open', at: now }] }) });
    return;
  }

  if (ev !== 'issue_comment') return;
  const c = context.payload.comment;
  const actor = c.user.login;
  if (c.user.type === 'Bot') return;
  // 管理者 = リポジトリの共同編集者、または docs/collaborators.json の admins_github に名前がある人（まとめページに入れる人）
  let extraAdmins = [];
  try { extraAdmins = (JSON.parse(require('fs').readFileSync((process.env.GITHUB_WORKSPACE || '.') + '/docs/collaborators.json', 'utf8')).admins_github || []).map(x => String(x).toLowerCase()); } catch {}
  const isAdmin = ['OWNER', 'MEMBER', 'COLLABORATOR'].includes(c.author_association) || extraAdmins.includes(String(actor).toLowerCase());
  const cmds = parseCommands(c.body);
  if (!cmds.length) return;

  const st = getState(body);
  const errors = [];
  let status = STATUS.find(s => labels.includes(s)) || null;
  let type = typeOf(labels);
  let changed = false;
  const canEdit = () => isAdmin || st.claimer === actor;
  const isTask = () => !!type || status !== null;
  const did = new Set();

  let close = null;   // 'completed' | 'not_planned'
  for (const cmd of cmds) {
    const n = cmd.name;
    if (n === 'fixed' || n === 'wontfix') {
      if (!isAdmin) { errors.push(`\`/${n}\` は管理者だけが使えます`); continue; }
      if (n === 'fixed') {
        const m = cmd.arg.match(/^v?(\d+(?:\.\d+)+)\s*(.*)$/i);
        if (!m) { errors.push('`/fixed` の後に版を書いてください（例: `/fixed v0.4.17`）'); continue; }
        st.fixed_in = 'v' + m[1]; delete st.wontfix; delete st.confirmed; delete st.still; if (m[2]) st.note = m[2];
        close = 'completed';
      } else {
        if (!cmd.arg) { errors.push('`/wontfix` の後に理由を書いてください'); continue; }
        st.wontfix = cmd.arg; delete st.fixed_in; close = 'not_planned';
      }
      if (isTask()) status = L.done;
      changed = true; did.add(n);
      continue;
    }
    if (n === 'later' || n === 'now') {
      if (!isAdmin) { errors.push(`\`/${n}\` は管理者だけが使えます`); continue; }
      if (n === 'later') {
        st.later = cmd.arg || true;
        if (!labels.includes(LATER)) await github.rest.issues.addLabels({ owner, repo, issue_number: num, labels: [LATER] });
      } else {
        delete st.later;
        if (labels.includes(LATER)) { try { await github.rest.issues.removeLabel({ owner, repo, issue_number: num, name: LATER }); } catch {} }
      }
      changed = true; did.add(n);
      continue;
    }
    if (n === 'items' || n === 'type') {
      if (!isAdmin) { errors.push(`\`/${n}\` は管理者だけが使えます`); continue; }
      if (n === 'type') {
        const t = TYPES.find(x => cmd.arg.startsWith(x));
        if (!t) { errors.push(`種類は ${TYPES.join('・')} のどれかです（例: \`/type 調査\`）`); continue; }
        type = t; if (!status) status = L.todo; changed = true; continue;
      }
      if (!cmd.items.length) { errors.push('`/items` の次の行に「- やること」の形で項目を書いてください'); continue; }
      const block = cmd.items.map(t => `- [ ] ${t}`).join('\n');
      if (/^### 確認項目\s*$/m.test(body)) {
        const ls = body.split('\n');
        let at = ls.findIndex(l => /^### 確認項目\s*$/.test(l)) + 1;
        while (at < ls.length && (ITEM.test(ls[at]) || ls[at].trim() === '')) at++;
        while (at > 0 && ls[at - 1].trim() === '') at--;
        ls.splice(at, 0, block);
        body = ls.join('\n');
      } else {
        body = body.replace(MARK, '').replace(/\s*$/, '') + `\n\n### 確認項目\n${block}\n`;
      }
      if (!type) type = '検証';
      if (!status) status = L.todo;
      changed = true;
      continue;
    }
    if (!isTask()) { errors.push('このIssueはまだ作業タスクではありません（管理者が `/items` か `/type` で始められます）'); break; }

    if (n === 'claim') {
      const w = /^(claude|ai|クロード)/i.test(cmd.arg) ? 'ai' : /^(人|human|ひと)/i.test(cmd.arg) ? 'human' : '';
      const takeover = w === 'ai' && (st.worker === 'ai' || st.worker === 'claude');
      if (status === L.doing && st.claimer && st.claimer !== actor && !takeover) { errors.push(`すでに @${st.claimer} さんが担当中です。別の「未着手」を選んでください`); continue; }
      if (status === L.done) { errors.push('このタスクは「完了」しています'); continue; }
      if (!(takeover && status === L.doing)) st.claimed_at = now;
      st.claimer = actor; if (w) st.worker = w; else delete st.worker; status = L.doing; changed = true; did.add('claim');
    } else if (n === 'check') {
      if (!canEdit()) { errors.push('`/check` は担当者（先に `/claim`）か管理者だけが使えます'); continue; }
      const m = cmd.arg.match(/^(\d+)\s+(ok|ng|hold)\b/i);
      if (!m) { errors.push(`\`/check ${cmd.arg}\` が読めません。例: \`/check 2 ok\``); continue; }
      const nb = checkItem(body, Number(m[1]), m[2].toLowerCase());
      if (nb === null) { errors.push(`確認項目 ${m[1]} 番はありません（全${items(body).length}件）`); continue; }
      body = nb; changed = true; did.add('check');
    } else if (n === 'submit') {
      if (!canEdit()) { errors.push('`/submit` は担当者（先に `/claim`）か管理者だけが使えます'); continue; }
      const m = cmd.arg.match(/^(https:\/\/github\.com\/\S+)\s*(.*)$/);
      if (!m) { errors.push('`/submit` の後に GitHub の URL を書いてください（例: `/submit https://github.com/あなた/gradius3/tree/task-7 解析メモ`）'); continue; }
      st.submissions = (st.submissions || []).concat([{ url: m[1], by: actor, at: now, note: m[2] || '' }]).slice(-10);
      if (m[2]) st.note = m[2];
      status = L.review; changed = true; did.add('submit');
    } else if (n === 'done') {
      if (!canEdit()) { errors.push('`/done` は担当者か管理者だけが使えます'); continue; }
      if (type === '検証') { const s = summary(body); status = (s.ng || s.hold || s.open) ? L.human : L.done; }
      else status = L.review;
      st.done_at = now; st.done_by = actor; if (cmd.arg) st.note = cmd.arg; changed = true; did.add('done');
    } else if (n === 'human') {
      if (!canEdit()) { errors.push('`/human` は担当者か管理者だけが使えます'); continue; }
      status = L.human; if (cmd.arg) st.note = cmd.arg; changed = true; did.add('human');
    } else if (n === 'release') {
      if (!canEdit()) { errors.push('`/release` は担当者か管理者だけが使えます'); continue; }
      delete st.claimer; delete st.claimed_at; delete st.worker; status = L.todo; changed = true; did.add('release');
    } else if (n === 'accept') {
      if (!isAdmin) { errors.push('`/accept` は管理者だけが使えます'); continue; }
      status = L.done; st.accepted_at = now; st.accepted_by = actor; if (cmd.arg) st.note = cmd.arg; changed = true; did.add('accept');
    } else if (n === 'reject') {
      if (!isAdmin) { errors.push('`/reject` は管理者だけが使えます'); continue; }
      if (!cmd.arg) { errors.push('`/reject` の後に直してほしい点を書いてください'); continue; }
      status = st.claimer ? L.doing : L.todo; st.note = '差し戻し: ' + cmd.arg; changed = true; did.add('reject');
    }
  }

  if (changed) {
    st.updated_at = now;
    st.last_by = actor;
    st.last_comment = c.html_url;
    for (const what of did) push(st, actor, what);
    await github.rest.issues.update({ owner, repo, issue_number: num, body: setState(body, st), ...(close ? { state: 'closed', state_reason: close } : {}) });
    if (status || type) await setLabels(num, labels, { status, type });
  }
  if (errors.length) { await react(c.id, 'confused'); await reply(num, (c.synthetic ? "" : `@${actor} `) + errors.map(e => `- ${e}`).join('\n')); }
  else if (changed) await react(c.id, '+1');
};

module.exports._test = { getState, setState, items, checkItem, summary, parseCommands, section, TYPES, L };
