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

  await page.goto("http://localhost:8080/login");

  await page.type("#username", "test_leon");
  await page.type("#password", "test_leon123");

  await Promise.all([
    page.click("button[type=submit]"),
    page.waitForNavigation()
  ]);

  await page.setCookie({
    name: "flag",
    value: "CTF{clickhereforepsteinfiles}",
    domain: "localhost",
    path: "/",
    httpOnly: false
  });

  await page.setCookie({
  name: "hint",
  value: "Check_your_DMs_for_HTML_execution",
  domain: "localhost",
  path: "/",
  httpOnly: false
});

  const conversationId = 1;
  await page.goto(`http://localhost:8080/dm/${conversationId}`, {
  waitUntil: "domcontentloaded",
  timeout: 0
});

  await page.waitForTimeout(15000);

  console.log("Bot hat DM geöffnet.");

})();