const puppeteer = require('puppeteer');
const fs        = require('fs');

// --- Config ---
// Multi-instance mode: TARGETS_FILE points to a JSON array of target objects.
// Single-instance fallback (dev compose): TARGET_URL + individual env vars.
const TARGETS_FILE   = process.env.TARGETS_FILE   || '';
const TARGET_URL     = (process.env.TARGET_URL    || 'http://localhost:8080').replace(/\/$/, '');
const BOT_USER       = process.env.BOT_USER       || 'compliancebot';
const BOT_PASS       = process.env.BOT_PASS       || 'ufoundit';
const DEBUG_TOKEN    = process.env.DEBUG_TOKEN    || 'b3b46de0-86e1-4a98-885d-1a85d2bef561';
const POLL_MS        = parseInt(process.env.POLL_MS || '60000', 10);
const EXEC_PATH      = process.env.CHROMIUM_PATH  || '/usr/bin/chromium';

const sleep = ms => new Promise(r => setTimeout(r, ms));

// --- Crypto — Laura ---
// Encrypt the debug token using the same hourly XOR cipher as /api/v1/crypto/encrypt.
function encryptToken(token) {
  const keyByte = Math.floor(Date.now() / 3_600_000) & 0xFF;
  const buf = Buffer.from(token, 'utf8');
  const enc = Buffer.from(buf.map(b => b ^ keyByte));
  return 'CORP{' + enc.toString('base64') + '}';
}

// --- Target list ---
// Returns array of { url, botUser, botPass, debugToken }
function loadTargets() {
  if (TARGETS_FILE && fs.existsSync(TARGETS_FILE)) {
    try {
      const raw = fs.readFileSync(TARGETS_FILE, 'utf8');
      const targets = JSON.parse(raw);
      if (Array.isArray(targets) && targets.length > 0) return targets;
    } catch (e) {
      console.error('[!] Failed to parse targets file:', e.message);
    }
  }
  // Fallback: single target from environment
  return [{ url: TARGET_URL, botUser: BOT_USER, botPass: BOT_PASS, debugToken: DEBUG_TOKEN }];
}

// --- Wait for app ---
// Returns true when reachable, false if maxWaitMs elapses (default 5 min).
async function waitForUrl(url, maxWaitMs = 300_000) {
  const { get } = url.startsWith('https') ? require('https') : require('http');
  const deadline = Date.now() + maxWaitMs;
  for (;;) {
    try {
      await new Promise((resolve, reject) => {
        get(url + '/login', res => { res.resume(); resolve(); }).on('error', reject);
      });
      console.log(`[*] App ready: ${url}`);
      return true;
    } catch {
      if (Date.now() >= deadline) {
        console.error(`[!] Timed out waiting for ${url} after ${maxWaitMs / 1000}s — skipping`);
        return false;
      }
      console.log(`[*] Waiting for ${url}...`);
      await sleep(3000);
    }
  }
}

// --- Per-target session ---
// sessions: Map<url, { page, botUser, botPass, debugToken }>
const sessions = new Map();

async function openSession(browser, target) {
  const { url, botUser, botPass, debugToken } = target;
  const ready = await waitForUrl(url);
  if (!ready) throw new Error(`App never became reachable: ${url}`);

  const page = await browser.newPage();
  await page.goto(`${url}/login`, { waitUntil: 'domcontentloaded' });
  await page.type('#username', botUser);
  await page.type('#password', botPass);
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.click('button[type=submit]'),
  ]);
  const finalUrl = page.url();
  if (finalUrl.includes('/login') || finalUrl.includes('/force-change-password')) {
    throw new Error(`Login failed for ${botUser} @ ${url} — redirected to ${finalUrl}`);
  }
  console.log(`[*] Logged in as ${botUser} @ ${url}`);

  const domain = new URL(url).hostname;
  await page.setCookie(
    { name: 'flag', value: encryptToken(debugToken), domain, path: '/', httpOnly: false },
    { name: 'hint', value: 'This looks encrypted. Try POST /api/v1/crypto/encrypt with {"data":"..."} — maybe you can reverse it.', domain, path: '/', httpOnly: false },
  );

  sessions.set(url, { page, botUser, botPass, debugToken, domain });
  console.log(`[*] Session ready for ${url}`);
}

async function pollSession(url) {
  const sess = sessions.get(url);
  if (!sess) return;
  const { page, debugToken, domain } = sess;

  // Re-encrypt flag cookie so it always uses the current hour's key
  await page.setCookie({ name: 'flag', value: encryptToken(debugToken), domain, path: '/', httpOnly: false });

  try {
    await page.goto(`${url}/dm`, { waitUntil: 'domcontentloaded', timeout: 30000 });
    const links = await page.$$eval('a.dm-item', els => els.map(a => a.href));
    console.log(`[*] ${url}: ${links.length} DM conversation(s)`);

    for (const link of links) {
      try {
        await page.goto(link, { waitUntil: 'domcontentloaded', timeout: 30000 });
        await sleep(2000);
      } catch (err) {
        console.error(`[!] Error visiting DM ${link}:`, err.message);
      }
    }
  } catch (err) {
    console.error(`[!] Poll error for ${url}:`, err.message);
  }
}

// --- Main ---
(async () => {
  const browser = await puppeteer.launch({
    headless: true,
    executablePath: EXEC_PATH,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu'],
  });

  console.log('[*] Browser launched');

  // Open initial sessions
  let lastTargets = loadTargets();
  for (const t of lastTargets) {
    await openSession(browser, t);
  }

  // --- XSS — Leon ---
  // Poll all active sessions every POLL_MS, re-reading targets file each cycle.
  for (;;) {
    // Check for added/removed targets
    const currentTargets = loadTargets();
    const currentUrls = new Set(currentTargets.map(t => t.url));

    // Close sessions for removed targets
    for (const [url, sess] of sessions) {
      if (!currentUrls.has(url)) {
        console.log(`[*] Target removed: ${url} — closing session`);
        await sess.page.close().catch(() => {});
        sessions.delete(url);
      }
    }

    // Open sessions for new targets
    for (const t of currentTargets) {
      if (!sessions.has(t.url)) {
        console.log(`[*] New target: ${t.url}`);
        await openSession(browser, t).catch(err => {
          console.error(`[!] Failed to open session for ${t.url}:`, err.message);
        });
      }
    }

    // Poll all active sessions
    for (const url of sessions.keys()) {
      await pollSession(url);
    }

    console.log(`[*] Sleeping ${POLL_MS / 1000}s... (${sessions.size} active session(s))`);
    await sleep(POLL_MS);
  }
})();
