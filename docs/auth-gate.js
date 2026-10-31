// Google ログインの扉（Firebase Authentication + Firestore の users/{uid}）
// 使い方: ページの <head> か <body> の最後に <script type="module" src="auth-gate.js"></script>
//   data-gate="admin" を付けると管理者だけ（Firestore の admins/{メールアドレス} がある人。申請の管理画面で登録）:
//   <script type="module" src="auth-gate.js" data-gate="admin"></script>
//   - ログインしていない → 「Google でログイン」
//   - ログインしたが申請が無い → 名前を入れて申請（users/{uid} に status: pending で作る。ルールは dev/firebase/firestore.rules）
//   - 承認待ち・却下 → その旨を表示
//   - 承認済み（status: approved）→ 扉を開けてページを見せる
// 申請の通知・承認・管理画面は tools/notify-gas/（管理者は管理画面の「自動で承認する」一覧に入れておけば、初回ログインで自動承認）。
// ※ GitHub Pages は誰でも見られるファイルしか置けないので、これは「入口の扉」。中身の Issue などは GitHub で公開されている。
import { initializeApp } from 'https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js';
import { getAuth, GoogleAuthProvider, signInWithPopup, signInWithRedirect, getRedirectResult, onAuthStateChanged, signOut } from 'https://www.gstatic.com/firebasejs/10.12.2/firebase-auth.js';
import { getFirestore, doc, getDoc, setDoc, addDoc, collection, serverTimestamp } from 'https://www.gstatic.com/firebasejs/10.12.2/firebase-firestore.js';

const firebaseConfig = {
  apiKey: 'AIzaSyAVuANsHQGEDSEujscNoCXWlixBKAAIw1U',
  authDomain: 'gradius3-login-41798.firebaseapp.com',
  projectId: 'gradius3-login-41798',
  storageBucket: 'gradius3-login-41798.firebasestorage.app',
  messagingSenderId: '570590177142',
  appId: '1:570590177142:web:8db75cac44711a158e7c57',
};

const MODE = (document.querySelector('script[src*="auth-gate.js"]') || { dataset: {} }).dataset.gate || 'approved';
const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const db = getFirestore(app);

// 扉（ページの上にかぶせる）
const css = `
#gate{position:fixed;inset:0;z-index:9999;background:var(--bg,#0d1117);color:var(--text,#e6edf3);display:flex;align-items:center;justify-content:center;padding:16px;font:15px/1.7 system-ui,-apple-system,"Hiragino Sans","Noto Sans JP",sans-serif}
#gate .box{max-width:420px;width:100%;background:var(--panel,#161b22);border:1px solid var(--line,#30363d);border-radius:12px;padding:20px}
#gate h2{font-size:17px;margin:0 0 6px}#gate p{margin:6px 0;font-size:14px}#gate .sub{color:var(--sub,#8b949e);font-size:13px}
#gate input{font:inherit;width:100%;padding:8px 10px;border-radius:8px;border:1px solid var(--line,#30363d);background:var(--bg,#0d1117);color:var(--text,#e6edf3);margin:6px 0}
#gate button{font:inherit;padding:9px 16px;border-radius:8px;border:1px solid var(--acc,#58a6ff);background:var(--acc,#58a6ff);color:#fff;cursor:pointer;margin-top:8px}
#gate button.sub2{background:transparent;color:var(--sub,#8b949e);border-color:var(--line,#30363d)}
#gatebar{font-size:12.5px;color:var(--sub,#8b949e);text-align:right;padding:4px 16px 0;max-width:860px;margin:0 auto}
#gatebar button{font:inherit;font-size:12.5px;background:none;border:none;color:var(--acc,#58a6ff);cursor:pointer;padding:0;margin-left:6px}
html.gate-locked body>*:not(#gate){visibility:hidden}`;
document.head.appendChild(Object.assign(document.createElement('style'), { textContent: css }));
document.documentElement.classList.add('gate-locked');
const gate = document.createElement('div'); gate.id = 'gate';
const mount = () => document.body ? document.body.prepend(gate) : document.addEventListener('DOMContentLoaded', () => document.body.prepend(gate));
mount();
const EN = (document.documentElement.lang || '').startsWith('en');
const t = (ja, en) => EN ? en : ja;
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const show = html => { gate.innerHTML = '<div class="box">' + html + '</div>'; gate.style.display = 'flex'; document.documentElement.classList.add('gate-locked'); };
const title = document.title.replace(/\s*—.*$/, '');

function open(user) {
  gate.style.display = 'none';
  document.documentElement.classList.remove('gate-locked');
  if (!document.getElementById('gatebar')) {
    const bar = document.createElement('div'); bar.id = 'gatebar';
    bar.innerHTML = esc(user.email) + '<button type="button">' + t('ログアウト', 'Sign out') + '</button>';
    bar.querySelector('button').onclick = () => signOut(auth);
    document.body.prepend(bar);
  }
  // 「確かめてほしいこと」のボタン（testplay.html）: 押されたことを Firestore の rechecks に残す。
  // 申請の管理画面の Apps Script（tools/notify-gas の check、5分ごと）が読んで GitHub に「[確認] #番号」の報告を作り、ボットが元の報告に記録する
  window.sendRecheck = (issue, result, version) => addDoc(collection(db, 'rechecks'), {
    uid: user.uid, name: user.displayName || '', email: user.email || '', issue: Number(issue), result: String(result), version: String(version || ''), createdAt: serverTimestamp(),
  });
  window.dispatchEvent(new CustomEvent('gate-open', { detail: { email: user.email } }));
}

async function login() {
  const p = new GoogleAuthProvider();
  try { await signInWithPopup(auth, p); }
  catch (e) {
    if (['auth/popup-blocked', 'auth/operation-not-supported-in-this-environment', 'auth/popup-closed-by-user'].includes(e.code)) await signInWithRedirect(auth, p);
    else show(`<h2>${t('ログインできませんでした', 'Could not sign in')}</h2><p class="sub">${esc(e.code || e.message)}</p><button type="button" id="g_retry">${t('もう一度', 'Try again')}</button>`), gate.querySelector('#g_retry').onclick = login;
  }
}

function askLogin() {
  show(`<h2>${esc(title)}</h2><p>${t('このページは、許可された人だけが見られます。Google アカウントでログインしてください。', 'Only approved people can view this page. Please sign in with your Google account.')}</p>
    <button type="button" id="g_login">${t('Google でログイン', 'Sign in with Google')}</button>
    ${MODE === 'admin' ? '<p class="sub">' + t('管理者だけが見られるページです。', 'This page is for administrators only.') + '</p>' : '<p class="sub">' + t('初めての人は、ログインしたあと申請すると、管理者が確認して許可します（許可されるとメールが届きます）。', 'If this is your first time, sign in and send a request. An administrator will review it (you will get an email when approved).') + '</p>'}`);
  gate.querySelector('#g_login').onclick = login;
}

async function checkAdmin(user) {
  show('<p class="sub">' + t('確認中…', 'Checking…') + '</p>');
  const out = '<button type="button" class="sub2" id="g_out">' + t('ログアウト', 'Sign out') + '</button>';
  try {
    const a = await getDoc(doc(db, 'admins', String(user.email || '').toLowerCase()));
    if (a.exists()) return open(user);
    show(`<h2>管理者だけのページです</h2><p>${esc(user.email)} は管理者として登録されていません。</p>${out}`);
  } catch (e) {
    show(`<h2>管理者だけのページです</h2><p>${esc(user.email)} は管理者として登録されていません。</p><p class="sub">${esc(e.code || '')}</p>${out}`);
  }
  gate.querySelector('#g_out').onclick = () => signOut(auth);
}

async function check(user) {
  if (MODE === 'admin') return checkAdmin(user);
  show('<p class="sub">' + t('確認中…', 'Checking…') + '</p>');
  let snap;
  try { snap = await getDoc(doc(db, 'users', user.uid)); }
  catch (e) { show(`<h2>${t('確認できませんでした', 'Could not check your status')}</h2><p class="sub">${esc(e.code || e.message)}</p><button type="button" class="sub2" id="g_out">${t('ログアウト', 'Sign out')}</button>`); gate.querySelector('#g_out').onclick = () => signOut(auth); return; }
  const st = snap.exists() ? snap.data().status : null;
  if (st === 'approved') return open(user);
  const out = '<button type="button" class="sub2" id="g_out">' + t('ログアウト', 'Sign out') + '</button>';
  if (st === 'pending') {
    show(`<h2>${t('承認待ちです', 'Waiting for approval')}</h2><p>${t(esc(user.email) + ' で申請を受け付けています。管理者が確認して許可すると、メールでお知らせします。', 'Your request from ' + esc(user.email) + ' has been received. You will get an email when an administrator approves it.')}</p>${out}`);
  } else if (st) {
    show(`<h2>${t('このページは見られません', 'You cannot view this page')}</h2><p>${t(esc(user.email) + ' の申請は許可されていません。', 'The request from ' + esc(user.email) + ' was not approved.')}</p>${out}`);
  } else {
    show(`<h2>${t('利用の申請', 'Request access')}</h2><p>${t(esc(user.email) + ' でログインしています。名前（呼び名）を入れて申請してください。', 'Signed in as ' + esc(user.email) + '. Enter your name (or nickname) and send a request.')}</p>
      <input id="g_name" maxlength="200" placeholder="${t('名前・ハンドル名', 'Name or nickname')}" value="${esc(user.displayName || '')}">
      <button type="button" id="g_apply">${t('申請する', 'Send request')}</button> ${out}`);
    gate.querySelector('#g_apply').onclick = async () => {
      const name = gate.querySelector('#g_name').value.trim();
      if (!name) return;
      try {
        await setDoc(doc(db, 'users', user.uid), { uid: user.uid, name, email: user.email, status: 'pending', createdAt: serverTimestamp() });
        check(user);
      } catch (e) { show(`<h2>${t('申請できませんでした', 'Could not send the request')}</h2><p class="sub">${esc(e.code || e.message)}</p>${out}`); gate.querySelector('#g_out').onclick = () => signOut(auth); }
    };
  }
  const o = gate.querySelector('#g_out'); if (o) o.onclick = () => signOut(auth);
}

getRedirectResult(auth).catch(() => {});
onAuthStateChanged(auth, user => user ? check(user) : askLogin());
