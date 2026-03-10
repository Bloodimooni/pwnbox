const puppeteer = require('puppeteer');

const TARGET_URL    = (process.env.TARGET_URL  || 'http://localhost:8080').replace(/\/$/, '');
const BOT_USER      = process.env.BOT_USER    || 'compliancebot';
const BOT_PASS      = process.env.BOT_PASS    || 'C0mpl1anceB0t2026';
const DEBUG_TOKEN   = process.env.DEBUG_TOKEN || 'b3b46de0-86e1-4a98-885d-1a85d2bef561';
const POLL_MS       = parseInt(process.env.POLL_MS || '60000', 10);
const EXEC_PATH     = process.env.CHROMIUM_PATH || '/usr/bin/chromium';

const sleep = ms => new Promise(r => setTimeout(r, ms));

// --- Crypto — Laura ---
// Encrypt the debug token using the same hourly XOR cipher as /api/v1/crypto/encrypt.
// Key = current UTC hour index (single byte, rotates every 60 min).
// Result is wrapped in CORP{...} so players know it is CorpChat-encrypted.
function encryptToken(token) {
  const keyByte = Math.floor(Date.now() / 3_600_000) & 0xFF;
  const buf = Buffer.from(token, 'utf8');
  const enc = Buffer.from(buf.map(b => b ^ keyByte));
  return 'CORP{' + enc.toString('base64') + '}';
}

async function waitForApp() {
  const { get } = TARGET_URL.startsWith('https') ? require('https') : require('http');
  for (;;) {
    try {
      await new Promise((resolve, reject) => {
        get(TARGET_URL + '/login', res => { res.resume(); resolve(); }).on('error', reject);
      });
      console.log('[*] App is up');
      return;
    } catch {
      console.log('[*] Waiting for app to start...');
      await sleep(3000);
    }
  }
}

(async () => {
  await waitForApp();

  const browser = await puppeteer.launch({
    headless: true,
    executablePath: EXEC_PATH,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
  });

  const page = await browser.newPage();

  // Log in
  await page.goto(`${TARGET_URL}/login`, { waitUntil: 'domcontentloaded' });
  await page.type('#username', BOT_USER);
  await page.type('#password', BOT_PASS);
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.click('button[type=submit]'),
  ]);
  console.log('[*] Logged in as', BOT_USER);

  const domain = new URL(TARGET_URL).hostname;

  // Set initial flag cookie so it exists before the first poll cycle.
  await page.setCookie(
    { name: 'flag', value: encryptToken(DEBUG_TOKEN), domain, path: '/', httpOnly: false },
    { name: 'hint', value: 'This looks encrypted. Try POST /api/v1/crypto/encrypt with {"data":"..."} — maybe you can reverse it.', domain, path: '/', httpOnly: false },
  );
  console.log('[*] Flag cookie set (encrypted debug token)');

  // --- XSS — Leon ---
  // Poll all DM conversations every POLL_MS milliseconds
  for (;;) {
    try {
      // Re-encrypt the cookie at the top of every poll cycle so it always reflects
      // the current hour's XOR key — the player's chosen-plaintext attack on
      // /api/v1/crypto/encrypt will always recover the correct key.
      await page.setCookie(
        { name: 'flag', value: encryptToken(DEBUG_TOKEN), domain, path: '/', httpOnly: false },
      );

      await page.goto(`${TARGET_URL}/dm`, { waitUntil: 'domcontentloaded', timeout: 30000 });
      const links = await page.$$eval('a.dm-item', els => els.map(a => a.href));
      console.log(`[*] Found ${links.length} DM conversation(s)`);

      for (const link of links) {
        try {
          console.log('[*] Visiting', link);
          await page.goto(link, { waitUntil: 'domcontentloaded', timeout: 30000 });
          await sleep(2000);
        } catch (err) {
          console.error('[!] Error visiting DM:', err.message);
        }
      }
    } catch (err) {
      console.error('[!] Poll error:', err.message);
    }

    console.log(`[*] Sleeping ${POLL_MS / 1000}s...`);
    await sleep(POLL_MS);
  }
})();
