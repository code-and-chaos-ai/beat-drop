#!/usr/bin/env node
// login.mjs — connect Beat Drop to YouTube Music by signing in, no DevTools, no copying.
//
// It opens YOUR OWN Chrome or Edge in a separate, private profile just for Beat Drop.
// You sign in with your own hands and close the window. The sign-in window is completely
// ordinary: nothing is attached to it and nothing is automated (Google refuses sign-in from a
// browser that has a debugging connection open, so there isn't one). Only AFTER you close it
// does the script reopen that profile invisibly, read the saved YouTube session, store it in
// one private file, and close it again. Your password never touches this script.
//
//   node login.mjs             first time: a window opens, you sign in, then close the window
//   node login.mjs --refresh   later: no window, quietly refreshes the saved session
//
// Needs Node 22+ and Chrome or Edge. No packages to install.
// Exit 0 = connected. 1 = not signed in. 2 = error.
//
// The session is never printed, logged, or sent anywhere except into the private file.
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync, chmodSync, copyFileSync, rmSync } from 'node:fs';
import { homedir, platform } from 'node:os';
import { dirname, join } from 'node:path';

const HOME = join(homedir(), '.beat-drop');
const AUTH = process.env.BEAT_DROP_AUTH || join(HOME, 'auth.json');
const PROFILE = process.env.BEAT_DROP_PROFILE || join(HOME, 'browser-profile');
const WAIT_MIN = Number(process.env.BEAT_DROP_LOGIN_MINUTES || 10);
const URL = 'https://music.youtube.com/';
const refresh = process.argv.includes('--refresh');
const posix = platform() !== 'win32';

function findBrowser() {
  if (process.env.BEAT_DROP_BROWSER) return process.env.BEAT_DROP_BROWSER;
  const pf = process.env.PROGRAMFILES || 'C:\\Program Files';
  const pf86 = process.env['PROGRAMFILES(X86)'] || 'C:\\Program Files (x86)';
  const local = process.env.LOCALAPPDATA || '';
  const candidates = {
    win32: [
      `${pf}\\Google\\Chrome\\Application\\chrome.exe`, `${pf86}\\Google\\Chrome\\Application\\chrome.exe`,
      `${local}\\Google\\Chrome\\Application\\chrome.exe`,
      `${pf86}\\Microsoft\\Edge\\Application\\msedge.exe`, `${pf}\\Microsoft\\Edge\\Application\\msedge.exe`,
    ],
    darwin: [
      '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
      '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
      '/Applications/Chromium.app/Contents/MacOS/Chromium',
    ],
    linux: ['/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/usr/bin/chromium',
      '/usr/bin/chromium-browser', '/usr/bin/microsoft-edge', '/snap/bin/chromium'],
  }[platform()] || [];
  return candidates.find((p) => p && existsSync(p));
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const baseArgs = () => [`--user-data-dir=${PROFILE}`, '--no-first-run', '--no-default-browser-check'];

// If an earlier run was interrupted, the profile is marked "crashed" and the browser would reopen
// every old tab. Mark it as cleanly closed before each launch, so the window opens on one page.
function markCleanExit() {
  const prefs = join(PROFILE, 'Default', 'Preferences');
  if (!existsSync(prefs)) return;
  try {
    const p = JSON.parse(readFileSync(prefs, 'utf8'));
    p.profile = { ...(p.profile || {}), exit_type: 'Normal', exited_cleanly: true };
    writeFileSync(prefs, JSON.stringify(p));
  } catch { /* unreadable prefs: the browser repairs its own file */ }
}

// One small DevTools client over Node's built-in WebSocket, talking to the browser itself.
async function connect(portFile) {
  for (let i = 0; i < 60 && !existsSync(portFile); i++) await sleep(250);
  if (!existsSync(portFile)) throw new Error('the browser did not open its local debugging port');
  const [port, path] = readFileSync(portFile, 'utf8').trim().split('\n');
  const ws = new WebSocket(`ws://127.0.0.1:${port}${path}`);
  await new Promise((ok, fail) => { ws.onopen = ok; ws.onerror = () => fail(new Error('could not reach the browser')); });
  let id = 0;
  const waiting = new Map();
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && waiting.has(msg.id)) { waiting.get(msg.id)(msg); waiting.delete(msg.id); }
  };
  const send = (method, params = {}) => new Promise((ok) => {
    const n = ++id; waiting.set(n, ok); ws.send(JSON.stringify({ id: n, method, params }));
  });
  return { send, close: () => ws.close() };
}

// Reopen the profile INVISIBLY, with a debugging port on 127.0.0.1 only, let YouTube Music load
// (that also rotates the session), read its cookies, and close. No sign-in ever happens here.
async function readSession(browser) {
  const portFile = join(PROFILE, 'DevToolsActivePort');
  rmSync(portFile, { force: true }); // a stale one from a crash would point at a dead port
  markCleanExit();
  const child = spawn(browser, [...baseArgs(), '--headless=new', '--remote-debugging-port=0', URL], { stdio: 'ignore' });
  let cdp;
  try {
    cdp = await connect(portFile);
    await sleep(5000);
    return ((await cdp.send('Storage.getCookies')).result?.cookies || []).filter((c) => c.domain.endsWith('youtube.com'));
  } finally {
    try { await cdp?.send('Browser.close'); } catch { /* already closing */ }
    cdp?.close();
    await sleep(1500);
    if (child.exitCode === null) child.kill();
  }
}

// The sign-in window: a plain browser, nothing attached. Resolves when the person closes it.
function signInWindow(browser) {
  markCleanExit();
  return new Promise((resolve) => {
    const child = spawn(browser, [...baseArgs(), URL], { stdio: 'ignore' });
    const timer = setTimeout(() => { child.kill(); resolve('timeout'); }, WAIT_MIN * 60_000);
    child.on('exit', () => { clearTimeout(timer); resolve('closed'); });
    child.on('error', () => { clearTimeout(timer); resolve('error'); });
  });
}

const isSignedIn = (cs) => cs.some((c) => c.name === 'SAPISID') && cs.some((c) => c.name === '__Secure-3PAPISID');

function savePrivately(cookies) {
  mkdirSync(dirname(AUTH), { recursive: true });
  if (posix) chmodSync(dirname(AUTH), 0o700);
  let prev = {};
  if (existsSync(AUTH)) {
    try { prev = JSON.parse(readFileSync(AUTH, 'utf8')); } catch { prev = {}; }
    copyFileSync(AUTH, `${AUTH}.bak`); // exactly one backup
    if (posix) chmodSync(`${AUTH}.bak`, 0o600);
  }
  const data = {
    ...prev,
    cookie: cookies.map((c) => `${c.name}=${c.value}`).join('; '),
    origin: 'https://music.youtube.com',
    'x-goog-authuser': prev['x-goog-authuser'] ?? '0',
  };
  delete data.authorization; // the server rebuilds it from the cookie on every call
  writeFileSync(AUTH, JSON.stringify(data, null, 2), { mode: 0o600 });
  if (posix) chmodSync(AUTH, 0o600);
}

const browser = findBrowser();
if (!browser) {
  console.log('No Chrome or Edge found. Install one, or set BEAT_DROP_BROWSER to its path.');
  process.exit(2);
}
mkdirSync(PROFILE, { recursive: true });
if (posix) chmodSync(PROFILE, 0o700);

try {
  if (!refresh) {
    console.log('A browser window is opening. In it:');
    console.log('  1. Sign in to YouTube Music (top right, "Sign in").');
    console.log('  2. When you see your account, CLOSE the window. That tells me you are done.');
    console.log(`Waiting up to ${WAIT_MIN} minutes.`);
    const how = await signInWindow(browser);
    if (how !== 'closed') console.log(how === 'timeout' ? 'Time ran out; checking what was saved anyway.' : 'The browser could not start.');
    await sleep(1500); // let the profile finish writing and release its lock
  }

  const cs = await readSession(browser);
  if (!isSignedIn(cs)) {
    console.log(refresh
      ? 'NOT SIGNED IN: run `node login.mjs` (without --refresh) and sign in once.'
      : 'No signed-in session found. Nothing was saved. Run it again and sign in before closing the window.');
    process.exitCode = 1;
  } else {
    savePrivately(cs);
    console.log(`Connected. Session saved privately at ${AUTH} (${cs.length} cookies, values not shown).`);
    console.log('Check it from your AI with ytmusic_status.');
    process.exitCode = 0;
  }
} catch (e) {
  console.log(`ERROR: ${e.message}`);
  process.exitCode = 2;
}
