/**
 * 配布ページのログイン申請: メール通知・ワンタップ承認・自動承認・管理画面（Google Apps Script・無料）
 *
 * Firestore
 *   users/{uid}        … 申請（本人が pending で作る。ルールは dev/firebase/firestore.rules）
 *   admin_notes/{uid}  … 管理者だけのメモ（Twitter・コメント・決めた日時と方法・履歴）。ルールに無いのでページからは読めない
 *   admins/{email}     … 管理者（共同作業のまとめページを見られる人）。本人が自分の分だけ読める。管理画面で登録
 *
 * 動き
 *   - 5分ごとに users を見る（check）
 *       新しい pending → 自動承認の一覧にあれば即承認、なければ管理者に「承認する／却下する」リンク付きのメール
 *       approved になった → 本人に「見られるようになりました」
 *   - Web アプリ（自分だけが開ける）: 管理画面（申請者の一覧・承認・却下・Twitter・コメント・自動承認の一覧）と、メールのリンクの受け口
 *
 * Firebase は Spark（無料）のままでよい。使い方は tools/notify-gas/README.md。
 */

// ── 設定 ──────────────────────────────────────────
const PROJECT_ID = 'gradius3-login-41798';
const PAGE_URL = 'https://hknroms.github.io/gradius3/';      // 承認された人に知らせるページ
const SITE_NAME = 'グラディウスIII 改造ROM';
const ADMIN_EMAIL = '';            // 空なら、このスクリプトを動かしている Google アカウントのアドレスに送る
const CHECK_MINUTES = 5;           // 何分ごとに見るか（1, 5, 10, 15, 30 のどれか）
const NOTIFY_REJECTED = false;     // 却下したときに本人へ知らせるか
// ────────────────────────────────────────────────

const ST = { pending: '承認待ち', approved: '承認', rejected: '却下' };
const CONSOLE_URL = 'https://console.firebase.google.com/project/' + PROJECT_ID + '/firestore/databases/-default-/data/~2Fusers';
const DOCS = 'https://firestore.googleapis.com/v1/projects/' + PROJECT_ID + '/databases/(default)/documents/';

// ═══ 最初に1回 ═══

/** 定期実行を設定し、今の状態を覚える（今ある承認待ちは管理者に1通でまとめて知らせる） */
function setup() {
  ScriptApp.getProjectTriggers().forEach(t => { if (t.getHandlerFunction() === 'check') ScriptApp.deleteTrigger(t); });
  ScriptApp.newTrigger('check').timeBased().everyMinutes(CHECK_MINUTES).create();
  const p = PropertiesService.getScriptProperties();
  p.deleteProperty('seen'); p.deleteProperty('initialized');
  check();
  Logger.log('設定しました。' + CHECK_MINUTES + '分ごとに確認します。通知先: ' + adminEmail_() + ' / 管理画面: ' + (appUrl_() || '（まだデプロイしていない）'));
}

/** 試しに管理者へテストメールを送る */
function testMail() {
  MailApp.sendEmail({ to: adminEmail_(), subject: '【' + SITE_NAME + '】通知のテスト', name: SITE_NAME,
    body: '通知の設定ができています。\n\n管理画面: ' + (appUrl_() || '（Web アプリとしてデプロイすると、ここに URL が出ます）') });
  Logger.log('送りました: ' + adminEmail_());
}

// ═══ テストプレイの報告フォーム（Google フォーム）═══
// 関数 createReportForm を1回実行すると、日本語と英語の両方で書いた報告フォームを作り、URL をログに出す。
// もう一度実行しても作り直さない（作り直すときは「プロジェクトの設定」→ スクリプト プロパティの REPORT_FORM_ID を消す）。
// 写真のアップロードの質問は、Google フォームの画面で手で足せる（「ファイルのアップロード」。回答者は Google ログインが要る）。
function createReportForm() {
  const props = PropertiesService.getScriptProperties();
  const old = props.getProperty('REPORT_FORM_ID');
  if (old) {
    try { const f = FormApp.openById(old); Logger.log('もう作ってあります。\n回答する URL: ' + f.getPublishedUrl() + '\n編集する URL: ' + f.getEditUrl()); return; } catch (e) {}
  }
  const form = FormApp.create(SITE_NAME + ' ご意見・ご要望・不具合報告 / Feedback and bug reports');
  form.setDescription([
    'ご意見・ご要望・不具合の報告、テストプレイの報告など、どんなことでも受け付けています。わかる範囲で書いてください（全部埋めなくても大丈夫です）。',
    '内容は GitHub の報告として公開することがあります（お名前は公開しません）。ROM のファイルや中身は送らないでください。',
    '',
    'Feedback, requests, bug reports and test play reports are all welcome. Fill in what you can (English or Japanese). Your report may be published on GitHub (your name is not). Please do not send ROM files.'
  ].join('\n'));
  form.setCollectEmail(false);
  form.setAllowResponseEdits(false);
  form.setShowLinkToRespondAgain(true);
  form.setConfirmationMessage('送信しました。ありがとうございます！ / Thank you! Your report has been sent.');

  const choice = (title, help, opts, req) => { const q = form.addMultipleChoiceItem().setTitle(title).setChoiceValues(opts).setRequired(!!req); if (help) q.setHelpText(help); return q; };
  const text = (title, help, req) => { const q = form.addTextItem().setTitle(title).setRequired(!!req); if (help) q.setHelpText(help); return q; };
  const para = (title, help, req) => { const q = form.addParagraphTextItem().setTitle(title).setRequired(!!req); if (help) q.setHelpText(help); return q; };

  choice('報告の種類 / Type of report', '', KINDS_, true);
  versionItem_(form);
  text('起動画面の数字 / Boot screen numbers', '電源を入れた直後の「RAM ROM CHECK」の下の数字（わかれば。例 0 4 17  26 10 26 10:12） / The numbers under RAM ROM CHECK right after power-on (if you know them)');
  choice('遊んだ環境 / Where you played', '', ['MAMEUI（Windows）', 'MAME（その他 / other）', 'MAME4droid（Android）', '実機（基板） / Real hardware', 'その他 / Other'], true);
  text('環境の詳しいこと / Details of your setup', '例）MAMEUI 0.289 / Windows 11 / PS5 コントローラー');
  choice('モード / Mode', '', MODES_, false);
  text('面・エリア・位置 / Stage, area, position', '例）5面 ❷ X:1CA0 Y:0000（ポーズメニューの POS DISP を ON にすると右上に出ます） / e.g. Stage 5 area 2, X:1CA0 Y:0000 (turn on POS DISP in the pause menu)');
  para('何が起きたか / What happened', WHAT_HELP_, true);
  para('起こし方 / How to make it happen', 'どうすると起きるか。毎回か、たまにか / Steps, and whether it happens every time');
  para('写真・動画のリンク / Links to photos or videos', 'Google ドライブや Google フォトなどで共有したリンク（あれば） / Shared links from Google Drive, Google Photos, etc. (if any)');
  text('確認した元の報告 / Original report checked', '「直ったかの確認」のときだけ。配布ページの「確かめてほしいこと」の報告の番号（例 #23）と、直っていたか / Only for re-checks: the report number (e.g. #23) and whether it was fixed');
  text('お名前（任意・公開しません） / Your name (optional, not published)', '');

  props.setProperty('REPORT_FORM_ID', form.getId());
  Logger.log('作りました。\n回答する URL（案内ページに載せる）: ' + form.getPublishedUrl() + '\n編集する URL: ' + form.getEditUrl());
}

const WHAT_HELP_ = 'プレイ中のメモをそのまま貼り付けて大丈夫です。本当はどうなってほしいかも。「いろいろまとめて」のときは、メモを丸ごと貼ってください（ほかの欄は空でも大丈夫です） / Paste your notes as they are. For "Several things at once", paste all your notes here (other fields can be blank)';
const MODES_ = ['NORMAL（メニューから開始 / from the menu）', 'CUBE RUSH（キューブラッシュ）', 'BOSS RUSH（ボスラッシュ）', '純正どおりの開始 / Original start (no menu)', 'メニュー・ポーズ画面 / Menu or pause screen', 'わからない・その他 / Not sure / Other'];
const KINDS_ = ['不具合 / Bug', '気づいたこと・感想 / Finding', '要望 / Request', 'いろいろまとめて（音声メモなど） / Several things at once (voice notes, etc.)', '直ったかの確認 / Re-check of a fix'];
// 「版」の質問：選ぶ形（最新版／1つ前の版／その他に書く）。空なら最新版として扱う
function versionItem_(form) {
  return form.addMultipleChoiceItem().setTitle('版 / Version').setHelpText('ふつうは「最新版」。空のままなら最新版として扱います / Usually "Latest". Blank means the latest')
    .setChoiceValues(['最新版 / Latest', '1つ前の版 / Previous']).showOtherOption(true).setRequired(false);
}
// 作ってあるフォームを新しい形に直す（題名・説明・「版」の質問）。1回実行すればよい
function updateReportForm() {
  const form = FormApp.openById(PropertiesService.getScriptProperties().getProperty('REPORT_FORM_ID'));
  form.setTitle(SITE_NAME + ' ご意見・ご要望・不具合報告 / Feedback and bug reports');
  form.setDescription(form.getDescription().replace(/^テストプレイにご協力いただき、ありがとうございます。/, 'ご意見・ご要望・不具合の報告、テストプレイの報告など、どんなことでも受け付けています。').replace(/Thank you for test playing! /, 'Feedback, requests, bug reports and test play reports are all welcome. '));
  const kindItem = form.getItems().find(it => it.getTitle().indexOf('報告の種類') === 0);
  if (kindItem) kindItem.asMultipleChoiceItem().setChoiceValues(KINDS_);
  const modeItem = form.getItems().find(it => it.getTitle().indexOf('モード') === 0);
  if (modeItem) modeItem.asMultipleChoiceItem().setChoiceValues(MODES_);
  const whatItem = form.getItems().find(it => it.getTitle().indexOf('何が起きたか') === 0);
  if (whatItem) whatItem.setHelpText(WHAT_HELP_);
  const old = form.getItems().find(it => it.getTitle().indexOf('版 / Version') === 0);
  if (old) {
    const idx = old.getIndex();
    if (old.getType() !== FormApp.ItemType.MULTIPLE_CHOICE) { form.deleteItem(old); const q = versionItem_(form); form.moveItem(q.getIndex(), idx); }
  }
  Logger.log('直しました: ' + form.getPublishedUrl());
}
// 版を番号にする（最新版・1つ前の版・空 → 配布ページの versions.json の番号）
function resolveVersion_(v) {
  v = String(v || '').trim();
  let vs = [];
  try { vs = JSON.parse(UrlFetchApp.fetch(PAGE_URL + 'versions.json', { muteHttpExceptions: true }).getContentText()).versions.map(x => 'v' + x.version); } catch (e) {}
  if ((!v || /^最新|Latest/.test(v)) && vs[0]) return vs[0] + '（最新版）';
  if (/^1つ前|Previous/.test(v) && vs[1]) return vs[1] + '（1つ前の版）';
  return v;
}

// ═══ 報告フォーム → GitHub の報告（Issue）═══
// 準備: 「プロジェクトの設定」→ スクリプト プロパティに GITHUB_TOKEN（hknroms で作ったトークン。gradius3 の Issues: Read and write）を足す
//       → 関数 setupFormToGitHub を1回実行（フォームに送信の合図を付ける。それまでの回答は送らない）
// 送られた報告は「[テスト] …」の Issue になる（配布ページの「これまでの報告」に出る）。お名前は Issue に書かず、管理者へのメールにだけ書く。
// それまでの回答も送りたいときは forwardExisting を実行する。
const GH_REPO = 'hknroms/gradius3';
function setupFormToGitHub() {
  const props = PropertiesService.getScriptProperties();
  const id = props.getProperty('REPORT_FORM_ID');
  if (!id) throw new Error('先に createReportForm を実行してください');
  if (!props.getProperty('GITHUB_TOKEN')) throw new Error('スクリプト プロパティに GITHUB_TOKEN を足してください');
  ScriptApp.getProjectTriggers().filter(t => t.getHandlerFunction() === 'onReportSubmit').forEach(t => ScriptApp.deleteTrigger(t));
  const form = FormApp.openById(id);
  ScriptApp.newTrigger('onReportSubmit').forForm(form).onFormSubmit().create();
  const done = form.getResponses().map(r => r.getId());
  props.setProperty('FORWARDED', JSON.stringify(done));
  Logger.log('設定しました。これから送られた報告は GitHub に載ります（今までの ' + done.length + ' 件は送っていません。送るなら forwardExisting）。');
}
function onReportSubmit(e) { forwardResponse_(e.response); }
function forwardExisting() {
  const props = PropertiesService.getScriptProperties();
  const form = FormApp.openById(props.getProperty('REPORT_FORM_ID'));
  props.setProperty('FORWARDED', '[]');
  let n = 0; form.getResponses().forEach(r => { if (forwardResponse_(r)) n++; });
  Logger.log(n + ' 件を GitHub に送りました');
}
function forwardResponse_(r) {
  const props = PropertiesService.getScriptProperties();
  const done = JSON.parse(props.getProperty('FORWARDED') || '[]');
  if (done.indexOf(r.getId()) >= 0) return false;
  const A = {};
  r.getItemResponses().forEach(it => { const t = it.getItem().getTitle().split(' / ')[0].trim(); const v = it.getResponse(); A[t] = Array.isArray(v) ? v.join(', ') : String(v || '').trim(); });
  const ja = v => String(v || '').split(' / ')[0].trim();
  const kind = ja(A['報告の種類']) || '不具合';
  const what = A['何が起きたか'] || '';
  const name = A['お名前（任意・公開しません）'] || '';
  const sec = (h, v) => '### ' + h + '\n\n' + (v ? v : '_No response_') + '\n\n';
  let title, body = '';
  const origin = (A['確認した元の報告'] || '').match(/#?(\d+)/);
  if (kind === '直ったかの確認' && origin) {
    const res = A['確認した元の報告'].replace(/#?\d+/, '').trim() + ' ' + what;
    const bad = /まだ|おかしい|直って(い)?な|still|broken|not/i.test(res);
    title = '[確認] #' + origin[1] + ' ' + (bad ? 'まだおかしい' : '直っていた');
    body += sec('報告の種類', '直ったかの確認') + sec('版', resolveVersion_(A['版'])) + sec('確認した元の報告', '#' + origin[1]) + sec('確認の結果', bad ? 'まだおかしい' : '直っていた');
  } else {
    title = '[テスト] ' + (/^いろいろまとめて/.test(kind) ? 'まとめての報告：' : '') + (what.split('\n')[0].slice(0, 40) || '（題名なし）');
    body += sec('報告の種類', kind) + sec('版', resolveVersion_(A['版']));
  }
  body += sec('起動画面の数字（版・ビルド日時）', A['起動画面の数字']) + sec('遊んだ環境', A['遊んだ環境']) + sec('環境の詳しいこと（わかれば）', A['環境の詳しいこと']) +
    sec('モード', A['モード']) + sec('面・エリア', A['面・エリア・位置']) + sec('何が起きたか', what) + sec('起こし方（再現手順）', A['起こし方']) +
    sec('スクリーンショット・動画', A['写真・動画のリンク']) + '---\n_Google フォームから届いた報告です（' + Utilities.formatDate(r.getTimestamp(), 'Asia/Tokyo', 'yyyy-MM-dd HH:mm') + '）。_\n';
  const res = UrlFetchApp.fetch('https://api.github.com/repos/' + GH_REPO + '/issues', { method: 'post', contentType: 'application/json', muteHttpExceptions: true,
    headers: { Authorization: 'Bearer ' + props.getProperty('GITHUB_TOKEN'), Accept: 'application/vnd.github+json' }, payload: JSON.stringify({ title: title, body: body }) });
  const code = res.getResponseCode();
  if (code !== 201) {
    MailApp.sendEmail({ to: adminEmail_(), subject: '【' + SITE_NAME + '】フォームの報告を GitHub に載せられませんでした', name: SITE_NAME, body: 'GitHub ' + code + ': ' + res.getContentText().slice(0, 500) + '\n\n' + title + '\n\n' + body });
    return false;
  }
  const url = JSON.parse(res.getContentText()).html_url;
  done.push(r.getId()); props.setProperty('FORWARDED', JSON.stringify(done.slice(-500)));
  MailApp.sendEmail({ to: adminEmail_(), subject: '【' + SITE_NAME + '】フォームに報告が届きました', name: SITE_NAME,
    body: title + '\n' + url + '\n\nお名前: ' + (name || '（なし）') + '\n\n' + what.slice(0, 1000) });
  return true;
}

// ═══ 「確かめてほしいこと」のボタン（docs/testplay.html）═══
// 押されると、ページが Firestore の rechecks に1件作る（ルールは dev/firebase/firestore.rules）。
// ここで GitHub に「[確認] #番号 直っていた／まだおかしい」の報告を作り（フォームの「直ったかの確認」と同じ形）、ボットが元の報告に記録する。載せたら消す。
function forwardRechecks_() {
  const props = PropertiesService.getScriptProperties();
  const token = props.getProperty('GITHUB_TOKEN'); if (!token) return;
  const failed = JSON.parse(props.getProperty('RC_FAILED') || '[]');
  listDocs_('rechecks').forEach(d => {
    const n = Number(d.issue);
    if (!n) { req_('delete', DOCS + 'rechecks/' + d._id); return; }
    const bad = d.result === 'まだおかしい';
    const sec = (h, v) => '### ' + h + '\n\n' + (v ? v : '_No response_') + '\n\n';
    const when = d.createdAt ? Utilities.formatDate(new Date(d.createdAt), 'Asia/Tokyo', 'yyyy-MM-dd HH:mm') : '';
    const title = '[確認] #' + n + ' ' + (bad ? 'まだおかしい' : '直っていた');
    const body = sec('報告の種類', '直ったかの確認') + sec('版', d.version || '') + sec('確認した元の報告', '#' + n) + sec('確認の結果', bad ? 'まだおかしい' : '直っていた') +
      '---\n_配布ページの「確かめてほしいこと」のボタンから届いた確認です（' + when + '）。_\n';
    const res = UrlFetchApp.fetch('https://api.github.com/repos/' + GH_REPO + '/issues', { method: 'post', contentType: 'application/json', muteHttpExceptions: true,
      headers: { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json' }, payload: JSON.stringify({ title: title, body: body }) });
    if (res.getResponseCode() === 201) { req_('delete', DOCS + 'rechecks/' + d._id); return; }
    if (failed.indexOf(d._id) < 0) {   // 失敗は1件につき1回だけ知らせる（次の check でまた試す）
      failed.push(d._id); props.setProperty('RC_FAILED', JSON.stringify(failed.slice(-100)));
      MailApp.sendEmail({ to: adminEmail_(), subject: '【' + SITE_NAME + '】確認のボタンを GitHub に載せられませんでした', name: SITE_NAME,
        body: 'GitHub ' + res.getResponseCode() + ': ' + res.getContentText().slice(0, 500) + '\n\n' + title + '\n' + (d.name || '') + ' ' + (d.email || '') });
    }
  });
}

// ═══ 定期実行 ═══

function check() {
  const lock = LockService.getScriptLock(); if (!lock.tryLock(20000)) return;
  try { forwardRechecks_(); } catch (e) { Logger.log('rechecks: ' + e); }
  try {
    const props = PropertiesService.getScriptProperties();
    const first = !props.getProperty('initialized');
    const seen = JSON.parse(props.getProperty('seen') || '{}');
    const allow = allowlist_();
    const newPending = [];
    listUsers_().forEach(u => {
      if (seen[u.uid] === u.status) return;
      const prev = seen[u.uid];
      seen[u.uid] = u.status;
      if (u.status === 'pending') {
        if (u.email && allow.indexOf(u.email.toLowerCase()) >= 0) { decide_(u, 'approved', '自動（一覧）'); seen[u.uid] = 'approved'; }
        else newPending.push(u);
      } else if (!first && prev !== undefined) {
        // 管理画面以外（Firebase の管理画面など）で変えられたもの
        noteDecision_(u.uid, u.status, '管理画面（Firebase）');
        if (u.status === 'approved') mailApproved_(u);
        if (u.status === 'rejected' && NOTIFY_REJECTED) mailRejected_(u);
      } else if (!first && prev === undefined && u.status === 'approved') {
        mailApproved_(u);
      }
    });
    if (newPending.length) mailPending_(newPending, first);
    props.setProperty('seen', JSON.stringify(seen));
    props.setProperty('initialized', '1');
  } finally { lock.releaseLock(); }
}

// ═══ Web アプリ（管理画面・メールのリンク） ═══

function doGet(e) {
  const p = (e && e.parameter) || {};
  if (p.a === 'approve' || p.a === 'reject') {
    // メールのリンクは「確かめる画面」を出すだけ（メールのリンク先を自動で開く仕組みで勝手に決まらないように、ボタンで決める）
    const u = getUser_(p.uid);
    if (!u) return page_('<div class="done">申請が見つかりませんでした。</div>');
    const verb = p.a === 'approve' ? '承認' : '却下', st = p.a === 'approve' ? 'approved' : 'rejected';
    if (u.status !== 'pending') return page_('<div class="done">' + esc_(u.name || u.email) + ' さんは、すでに「' + esc_(ST[u.status] || u.status) + '」です。</div><p><a href="' + appUrl_() + '">管理画面を開く</a></p>');
    return page_('<div class="done" id="box"><b>' + esc_(u.name || '(名前なし)') + '</b><br><span class="sub">' + esc_(u.email) + '<br>申請 ' + esc_(u.createdAt ? fmt_(u.createdAt) : '') + '</span>' +
      '<div class="row"><button class="' + (st === 'approved' ? 'ok' : 'ng') + '" id="go">' + verb + 'する</button></div></div>' +
      '<p><a href="' + appUrl_() + '">管理画面を開く</a></p>' +
      '<script>document.getElementById("go").onclick=function(){this.disabled=true;this.textContent="処理中…";' +
      'google.script.run.withSuccessHandler(function(){document.getElementById("box").innerHTML="' + verb + 'しました。' + (st === 'approved' ? '本人にメールを送りました。' : '') + '";})' +
      '.withFailureHandler(function(e){document.getElementById("box").textContent="エラー: "+e.message;}).apiDecide(' + JSON.stringify(u.uid) + ',"' + st + '");};</script>');
  }
  return page_(ADMIN_HTML);
}

/** 管理画面が読むデータ */
function apiData() {
  const users = listUsers_();
  const notes = listNotes_();
  const auth = authInfo_(users.map(u => u.uid));
  return {
    users: users.map(u => Object.assign({}, u, notes[u.uid] || {}, auth[u.uid] || {})),
    allowlist: autoList_().join('\n'),
    admins: adminList_().join('\n'),
    me: adminEmail_(), consoleUrl: CONSOLE_URL, pageUrl: PAGE_URL,
  };
}

// ステレオの聞き比べの記録（stereo_results）。data は記録の JSON（文字列）
function apiStereo() {
  return listDocs_('stereo_results').map(d => ({ uid: d._id, name: d.name || '', email: d.email || '', count: d.count || 0, favs: d.favs || 0, updatedAt: d.updatedAt || '', data: d.data || '' }))
    .sort((a, b) => String(b.updatedAt).localeCompare(String(a.updatedAt)));
}

function apiDecide(uid, status) {
  if (['approved', 'rejected', 'pending'].indexOf(status) < 0) throw new Error('status が違う');
  const u = getUser_(uid); if (!u) throw new Error('申請が見つかりません');
  if (u.status === status) return apiData();
  decide_(u, status, '管理画面（このページ）');
  return apiData();
}

function apiSaveNote(uid, twitter, comment) {
  twitter = String(twitter || '').trim().replace(/^https?:\/\/(www\.)?(twitter|x)\.com\//, '').replace(/^@/, '').replace(/[/?#].*$/, '');
  patchDoc_('admin_notes/' + uid, { twitter: twitter, comment: String(comment || '').slice(0, 5000), noteUpdatedAt: new Date() });
  return apiData();
}

function parseEmails_(text) { return Array.from(new Set(String(text || '').split(/[\s,;]+/).map(s => s.trim().toLowerCase()).filter(s => /^[^@\s]+@[^@\s]+$/.test(s)))); }

/** 管理者（まとめページを見られる人）を保存。Firestore の admins/{email} を作り直す。管理者は配布ページも自動で承認する */
function apiSaveAdmins(text) {
  const want = parseEmails_(text);
  const have = listDocs_('admins').map(d => d._id);
  want.filter(e => have.indexOf(e) < 0).forEach(e => patchDoc_('admins/' + e, { email: e, addedAt: new Date() }));
  have.filter(e => want.indexOf(e) < 0).forEach(e => req_('delete', DOCS + 'admins/' + encodeURIComponent(e)));
  PropertiesService.getScriptProperties().setProperty('admins', JSON.stringify(want));
  check();
  return apiData();
}

function apiSaveAllowlist(text) {
  const list = parseEmails_(text);
  PropertiesService.getScriptProperties().setProperty('allowlist', JSON.stringify(list));
  check();   // 一覧に入った承認待ちをすぐ通す
  return apiData();
}

// ═══ 決める・記録する・メール ═══

function decide_(u, status, method) {
  patchDoc_('users/' + u.uid, { status: status });
  noteDecision_(u.uid, status, method);
  const p = PropertiesService.getScriptProperties();
  const seen = JSON.parse(p.getProperty('seen') || '{}'); seen[u.uid] = status; p.setProperty('seen', JSON.stringify(seen));
  if (status === 'approved') mailApproved_(u);
  if (status === 'rejected' && NOTIFY_REJECTED) mailRejected_(u);
}

function noteDecision_(uid, status, method) {
  const old = getDoc_('admin_notes/' + uid) || {};
  const who = method.indexOf('自動') === 0 ? '自動' : (method.indexOf('Firebase') >= 0 ? '（Firebase の管理画面）' : adminEmail_());
  const line = fmt_(new Date()) + ' ' + (ST[status] || status) + '（' + method + '）';
  patchDoc_('admin_notes/' + uid, { decidedStatus: status, decidedAt: new Date(), decidedBy: who, decidedMethod: method,
    history: ((old.history ? old.history + '\n' : '') + line).slice(-4000) });
}

function adminEmail_() { return ADMIN_EMAIL || Session.getEffectiveUser().getEmail(); }
function appUrl_() { try { return ScriptApp.getService().getUrl() || ''; } catch (e) { return ''; } }

function mailPending_(list, first) {
  const url = appUrl_();
  const lines = list.map(u => '・' + (u.name || '(名前なし)') + ' <' + (u.email || '?') + '>' + (u.createdAt ? '  ' + fmt_(u.createdAt) : '') +
    (url ? '\n   承認する: ' + url + '?a=approve&uid=' + encodeURIComponent(u.uid) + '\n   却下する: ' + url + '?a=reject&uid=' + encodeURIComponent(u.uid) : ''));
  MailApp.sendEmail({
    to: adminEmail_(), name: SITE_NAME,
    subject: '【' + SITE_NAME + '】' + (first ? '承認待ちの申請が ' : '新しい申請が ') + list.length + ' 件あります',
    body: (first ? '通知を設定した時点で承認待ちの申請です。\n\n' : 'ログインの許可の申請がありました。\n\n') + lines.join('\n\n') +
      '\n\nリンクを開いて「承認する」（または「却下する」）を押すと決まります。承認すると本人にメールが届きます。\n' +
      (url ? '\n管理画面（一覧・Twitter・コメント）: ' + url : '\nFirebase の管理画面: ' + CONSOLE_URL)
  });
}

function mailApproved_(u) {
  if (!u.email) return;
  MailApp.sendEmail({ to: u.email, name: SITE_NAME, subject: '【' + SITE_NAME + '】ページを見られるようになりました',
    body: (u.name ? u.name + ' さん\n\n' : '') + '申請していただいたページへのログインを許可しました。\n次のページを開き、申請したときと同じ Google アカウントでログインしてください。\n\n' + PAGE_URL + '\n\n※ このメールは自動で送っています。' });
}

function mailRejected_(u) {
  if (!u.email) return;
  MailApp.sendEmail({ to: u.email, name: SITE_NAME, subject: '【' + SITE_NAME + '】申請について',
    body: (u.name ? u.name + ' さん\n\n' : '') + '申請していただいたページへのログインは、今回は見送らせていただきました。\n\n※ このメールは自動で送っています。' });
}

function autoList_() { return JSON.parse(PropertiesService.getScriptProperties().getProperty('allowlist') || '[]'); }
function adminList_() { return JSON.parse(PropertiesService.getScriptProperties().getProperty('admins') || '[]'); }
/** 自動で承認する人 = 自動承認の一覧 ＋ 管理者 */
function allowlist_() { return Array.from(new Set(autoList_().concat(adminList_()))); }

// ═══ Firestore（REST・持ち主の権限なのでルールに関係なく読み書きできる） ═══

function req_(method, url, body) {
  const o = { method: method, headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken(), 'x-goog-user-project': PROJECT_ID }, muteHttpExceptions: true, contentType: 'application/json' };
  if (body) o.payload = JSON.stringify(body);
  const r = UrlFetchApp.fetch(url, o);
  const c = r.getResponseCode();
  if (c === 404) return null;
  if (c >= 300) throw new Error('Firestore（' + c + '）: ' + r.getContentText().slice(0, 500));
  return JSON.parse(r.getContentText() || '{}');
}
function enc_(v) {
  if (v instanceof Date) return { timestampValue: v.toISOString() };
  if (typeof v === 'boolean') return { booleanValue: v };
  if (typeof v === 'number') return { integerValue: String(Math.round(v)) };
  return { stringValue: String(v == null ? '' : v) };
}
function dec_(f) {
  const o = {};
  Object.keys(f || {}).forEach(k => { const v = f[k]; o[k] = v.stringValue != null ? v.stringValue : v.timestampValue != null ? v.timestampValue : v.booleanValue != null ? v.booleanValue : v.integerValue != null ? Number(v.integerValue) : ''; });
  return o;
}
function patchDoc_(path, obj) {
  const fields = {}; Object.keys(obj).forEach(k => fields[k] = enc_(obj[k]));
  const mask = Object.keys(obj).map(k => 'updateMask.fieldPaths=' + encodeURIComponent(k)).join('&');
  return req_('patch', DOCS + path + '?' + mask, { fields: fields });
}
function getDoc_(path) { const d = req_('get', DOCS + path); return d ? dec_(d.fields) : null; }
function listDocs_(coll) {
  const out = []; let token = '';
  do {
    const d = req_('get', DOCS + coll + '?pageSize=300' + (token ? '&pageToken=' + encodeURIComponent(token) : '')) || {};
    (d.documents || []).forEach(x => out.push(Object.assign({ _id: x.name.split('/').pop() }, dec_(x.fields))));
    token = d.nextPageToken || '';
  } while (token);
  return out;
}
function listUsers_() { return listDocs_('users').map(u => ({ uid: u.uid || u._id, name: u.name || '', email: u.email || '', status: u.status || '', createdAt: u.createdAt || '' })); }
function getUser_(uid) { if (!uid) return null; const u = getDoc_('users/' + uid); return u ? { uid: u.uid || uid, name: u.name || '', email: u.email || '', status: u.status || '', createdAt: u.createdAt || '' } : null; }
function listNotes_() { const m = {}; listDocs_('admin_notes').forEach(n => { m[n._id] = n; delete n._id; }); return m; }

/** Firebase Authentication の情報（最後にログインした日時など）。読めなければ空 */
function authInfo_(uids) {
  const m = {};
  try {
    for (let i = 0; i < uids.length; i += 100) {
      const r = UrlFetchApp.fetch('https://identitytoolkit.googleapis.com/v1/projects/' + PROJECT_ID + '/accounts:lookup', {
        method: 'post', contentType: 'application/json', muteHttpExceptions: true,
        headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken(), 'x-goog-user-project': PROJECT_ID }, payload: JSON.stringify({ localId: uids.slice(i, i + 100) }) });
      if (r.getResponseCode() !== 200) break;
      (JSON.parse(r.getContentText()).users || []).forEach(a => {
        m[a.localId] = { lastLoginAt: a.lastLoginAt ? new Date(Number(a.lastLoginAt)).toISOString() : '', signedUpAt: a.createdAt ? new Date(Number(a.createdAt)).toISOString() : '',
          photoUrl: a.photoUrl || '', providers: (a.providerUserInfo || []).map(p => p.providerId).join(','), disabled: !!a.disabled };
      });
    }
  } catch (e) { /* 読めなくても管理画面は出す */ }
  return m;
}

function fmt_(iso) { return Utilities.formatDate(new Date(iso), 'Asia/Tokyo', 'yyyy-MM-dd HH:mm'); }
function esc_(s) { return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }

function page_(body) {
  return HtmlService.createHtmlOutput('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' +
    '<style>' + CSS + '</style></head><body><main><h1>' + esc_(SITE_NAME) + ' — 申請の管理</h1>' + body + '</main></body></html>')
    .setTitle('申請の管理 — ' + SITE_NAME).addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

const CSS = `
:root{--bg:#0d1117;--panel:#161b22;--line:#30363d;--text:#e6edf3;--sub:#8b949e;--acc:#58a6ff;--ok:#3fb950;--ng:#f85149;--warn:#d29922}
@media (prefers-color-scheme: light){:root{--bg:#f6f8fa;--panel:#fff;--line:#d0d7de;--text:#1f2328;--sub:#59636e;--acc:#0969da;--ok:#1a7f37;--ng:#cf222e;--warn:#9a6700}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.6 system-ui,-apple-system,"Hiragino Sans","Noto Sans JP",sans-serif}
main{max-width:860px;margin:0 auto;padding:20px 16px 60px}h1{font-size:19px;margin:0 0 10px}h2{font-size:16px;margin:22px 0 8px}
a{color:var(--acc)}.sub{color:var(--sub);font-size:13px}
.done{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px;font-size:16px}
.tabs{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0}.tabs button{font:inherit;font-size:13.5px;padding:6px 12px;border-radius:99px;border:1px solid var(--line);background:var(--panel);color:var(--text)}
.tabs button.on{border-color:var(--acc);color:var(--acc);font-weight:600}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:10px 0}
.hd{display:flex;gap:10px;align-items:center}.hd img{width:36px;height:36px;border-radius:50%;flex:none;background:var(--line)}
.nm{font-weight:600;overflow-wrap:anywhere}.em{font-size:13px;color:var(--sub);overflow-wrap:anywhere}
.badge{display:inline-block;font-size:12px;padding:0 8px;border-radius:99px;border:1px solid currentColor;margin-left:6px}
.s-pending{color:var(--warn)}.s-approved{color:var(--ok)}.s-rejected{color:var(--ng)}
dl{display:grid;grid-template-columns:auto 1fr;gap:2px 12px;font-size:13px;margin:8px 0}dt{color:var(--sub)}dd{margin:0;overflow-wrap:anywhere}
label{display:block;font-size:12.5px;color:var(--sub);margin-top:8px}
input,textarea{font:inherit;font-size:15px;width:100%;padding:7px 9px;border-radius:8px;border:1px solid var(--line);background:var(--bg);color:var(--text)}
textarea{min-height:70px;resize:vertical}
.row{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}.row button{font:inherit;font-size:14px;padding:7px 14px;border-radius:8px;border:1px solid var(--line);background:var(--panel);color:var(--text)}
.ok{border-color:var(--ok)!important;color:var(--ok)!important}.ng{border-color:var(--ng)!important;color:var(--ng)!important}.pri{background:var(--acc)!important;border-color:var(--acc)!important;color:#fff!important}
.hist{white-space:pre-wrap;font-size:12px;color:var(--sub);margin-top:6px}
#msg{position:sticky;top:0;background:var(--acc);color:#fff;border-radius:8px;padding:6px 10px;font-size:13px;display:none}
`;

const ADMIN_HTML = `
<div id="msg"></div>
<div class="sub" id="top">読み込み中…</div>
<div class="tabs" id="tabs"></div>
<div id="list"></div>
<h2>ステレオの結果</h2>
<div class="card"><div class="sub">聞き比べのページで「記録を管理者に送る」を押した人の記録です（1人1件・最新のもの）。</div>
<div class="row"><button class="pri" onclick="loadStereo()">読み込む</button><button id="stdl" onclick="dlStereo()" style="display:none">全員分をダウンロード（JSON）</button></div>
<div id="stereo"></div></div>
<h2>管理者（共同作業のまとめページを見られる人）</h2>
<div class="card"><div class="sub">ここに入れた Google アカウントの人だけが「共同作業のまとめ」を開けます（1行に1つ）。管理者は配布ページも自動で承認されます。</div>
<textarea id="admins" style="min-height:90px" placeholder="example@gmail.com"></textarea>
<div class="row"><button class="pri" onclick="saveAdmins()">保存</button></div></div>
<h2>自動で承認する Google アカウント</h2>
<div class="card"><div class="sub">ここにあるアドレスの人が申請したら、すぐ承認して本人にメールします（1行に1つ）。</div>
<textarea id="allow" style="min-height:110px" placeholder="example@gmail.com"></textarea>
<div class="row"><button class="pri" onclick="saveAllow()">保存</button></div></div>
<p class="sub" id="links"></p>
<script>
const ST = {pending:'承認待ち', approved:'承認', rejected:'却下'};
let D = null, tab = 'pending';
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = s => { if (!s) return ''; const d = new Date(s); return isNaN(d) ? s : d.toLocaleString('ja-JP', {year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}); };
function msg(t){ const m=document.getElementById('msg'); m.textContent=t; m.style.display=t?'block':'none'; }
function call(fn, ...args){ msg('保存中…'); google.script.run.withSuccessHandler(d=>{ D=d; render(); msg('保存しました'); setTimeout(()=>msg(''),1500); }).withFailureHandler(e=>msg('エラー: '+e.message))[fn](...args); }
function load(){ google.script.run.withSuccessHandler(d=>{ D=d; render(); }).withFailureHandler(e=>{ document.getElementById('top').textContent='エラー: '+e.message; }).apiData(); }
function render(){
  const us = D.users.slice().sort((a,b)=>String(b.createdAt).localeCompare(String(a.createdAt)));
  const n = k => us.filter(u => k==='all' || u.status===k).length;
  document.getElementById('top').textContent = '申請 ' + us.length + ' 件（承認待ち ' + n('pending') + '）・通知先 ' + D.me;
  document.getElementById('tabs').innerHTML = [['pending','承認待ち'],['approved','承認'],['rejected','却下'],['all','すべて']].map(([k,l]) => '<button class="'+(k===tab?'on':'')+'" onclick="tab=\\''+k+'\\';render()">'+l+' '+n(k)+'</button>').join('');
  const list = us.filter(u => tab==='all' || u.status===tab);
  document.getElementById('list').innerHTML = list.length ? list.map(u => {
    const tw = u.twitter ? '<a href="https://x.com/'+encodeURIComponent(u.twitter)+'" target="_blank">@'+esc(u.twitter)+'</a>' : '';
    return '<div class="card"><div class="hd">'+(u.photoUrl?'<img src="'+esc(u.photoUrl)+'" referrerpolicy="no-referrer">':'')+
      '<div><div class="nm">'+esc(u.name||'(名前なし)')+'<span class="badge s-'+esc(u.status)+'">'+esc(ST[u.status]||u.status)+'</span></div><div class="em">'+esc(u.email)+'</div></div></div>'+
      '<dl><dt>申請</dt><dd>'+fmt(u.createdAt)+'</dd>'+
      (u.decidedAt?'<dt>決定</dt><dd>'+fmt(u.decidedAt)+'　'+esc(ST[u.decidedStatus]||u.decidedStatus||'')+'（'+esc(u.decidedMethod||'')+'・'+esc(u.decidedBy||'')+'）</dd>':'')+
      (u.lastLoginAt?'<dt>最後のログイン</dt><dd>'+fmt(u.lastLoginAt)+'</dd>':'')+
      (u.signedUpAt?'<dt>初めてのログイン</dt><dd>'+fmt(u.signedUpAt)+'</dd>':'')+
      (tw?'<dt>Twitter</dt><dd>'+tw+'</dd>':'')+
      '<dt>ID</dt><dd class="sub">'+esc(u.uid)+(u.disabled?'（無効）':'')+'</dd></dl>'+
      '<label>Twitter（X）のアカウント</label><input id="tw_'+esc(u.uid)+'" value="'+esc(u.twitter||'')+'" placeholder="@なし／URL でも可">'+
      '<label>コメント（自分だけが見られるメモ）</label><textarea id="cm_'+esc(u.uid)+'">'+esc(u.comment||'')+'</textarea>'+
      '<div class="row"><button class="pri" onclick="saveNote(\\''+esc(u.uid)+'\\')">メモを保存</button>'+
      (u.status!=='approved'?'<button class="ok" onclick="decide(\\''+esc(u.uid)+'\\',\\'approved\\')">承認する</button>':'')+
      (u.status!=='rejected'?'<button class="ng" onclick="decide(\\''+esc(u.uid)+'\\',\\'rejected\\')">却下する</button>':'')+
      (u.status!=='pending'?'<button onclick="decide(\\''+esc(u.uid)+'\\',\\'pending\\')">承認待ちに戻す</button>':'')+'</div>'+
      (u.history?'<div class="hist">'+esc(u.history)+'</div>':'')+'</div>';
  }).join('') : '<div class="sub">ありません</div>';
  const a = document.getElementById('allow'); if (document.activeElement !== a) a.value = D.allowlist;
  const ad = document.getElementById('admins'); if (document.activeElement !== ad) ad.value = D.admins;
  document.getElementById('links').innerHTML = '<a href="'+esc(D.pageUrl)+'" target="_blank">配布ページ</a>　<a href="'+esc(D.consoleUrl)+'" target="_blank">Firebase の管理画面</a>';
}
function saveNote(uid){ call('apiSaveNote', uid, document.getElementById('tw_'+uid).value, document.getElementById('cm_'+uid).value); }
function decide(uid, st){ if (st!=='pending' && !confirm((st==='approved'?'承認':'却下')+'しますか？'+(st==='approved'?'（本人にメールが届きます）':''))) return; call('apiDecide', uid, st); }
function saveAllow(){ call('apiSaveAllowlist', document.getElementById('allow').value); }
function saveAdmins(){ call('apiSaveAdmins', document.getElementById('admins').value); }
let SR = [];
function loadStereo(){ document.getElementById('stereo').textContent='読み込み中…'; google.script.run.withSuccessHandler(r=>{ SR=r; renderStereo(); }).withFailureHandler(e=>{ document.getElementById('stereo').textContent='エラー: '+e.message; }).apiStereo(); }
function renderStereo(){
  document.getElementById('stdl').style.display = SR.length ? '' : 'none';
  document.getElementById('stereo').innerHTML = SR.length ? '<table style="width:100%;font-size:13px;border-collapse:collapse">'+SR.map((r,i)=>'<tr style="border-top:1px solid #ddd"><td>'+esc(r.name||'(名前なし)')+'<div class="sub">'+esc(r.email)+'</div></td><td>記録 '+r.count+'・合うパターン '+r.favs+' 曲</td><td class="sub">'+fmt(r.updatedAt)+'</td><td><button onclick="dlOne('+i+')">ダウンロード</button></td></tr>').join('')+'</table>' : '<div class="sub">まだ届いていません</div>';
}
function save(name, text){ try { const a=document.createElement('a'); a.href=URL.createObjectURL(new Blob([text],{type:'application/json'})); a.download=name; document.body.appendChild(a); a.click(); a.remove(); } catch(e) {} let t=document.getElementById('stout'); if(!t){ t=document.createElement('textarea'); t.id='stout'; t.style.minHeight='120px'; document.getElementById('stereo').after(t); } t.value=text; msg('ダウンロードされないときは、下の欄の文字を全部コピーしてください（'+name+'）'); setTimeout(()=>msg(''),4000); }
function dlOne(i){ const r=SR[i]; save('stereo_'+(r.name||r.uid).replace(/[^\w\-]+/g,'_')+'.json', r.data); }
function dlStereo(){ save('stereo_all.json', JSON.stringify(SR.map(r=>{ let d=null; try{ d=JSON.parse(r.data); }catch(e){} return {name:r.name, email:r.email, updatedAt:r.updatedAt, count:r.count, favs:r.favs, data:d}; }), null, 1)); }
load();
</script>`;
