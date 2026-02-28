const puppeteer = require("puppeteer");

(async () => {
  const browser = await puppeteer.launch({
    headless: true,
    executablePath: "/home/leon/.cache/puppeteer/chrome/linux-121.0.6167.85/chrome-linux64/chrome",
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox"
    ]
  });

  const page = await browser.newPage();

  // === Login als Opfer/Admin ===
  await page.goto("http://localhost:8080/login");

  await page.type("#username", "test_leon");
  await page.type("#password", "test_leon123");

  await Promise.all([
    page.click("button[type=submit]"),
    page.waitForNavigation()
  ]);

  // === Flag nur im Opfer-Cookie setzen ===
  await page.setCookie({
    name: "flag",
    value: "CTF{clickhereforepsteinfiles}",
    domain: "localhost",
    path: "/",
    httpOnly: false
  });

  // === DM öffnen (Stored XSS liegt dort bereits) ===
  const conversationId = 1;
  await page.goto(`http://localhost:8080/dm/${conversationId}`, {
  waitUntil: "domcontentloaded",
  timeout: 0
});

  // Zeit geben damit XSS ausführt
  await page.waitForTimeout(15000);

  console.log("Bot hat DM geöffnet.");

  // Optional: Browser offen lassen
  // await page.waitForTimeout(60000);

})();