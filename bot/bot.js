const puppeteer = require("puppeteer");

//sudo apt install nodejs npm -y
//npm install puppeteer
//npx puppeteer browsers install chrome
/*apt-get install -y \
  libnss3 \
  libatk1.0-0 \
  libatk-bridge2.0-0 \
  libcups2 \
  libxcomposite1 \
  libxdamage1 \
  libxrandr2 \
  libgbm1 \
  libgtk-3-0 \
  libasound2 \
  libpangocairo-1.0-0 \
  libxss1 \
  fonts-liberation \
  xdg-utils*/

//start bot with node bot.js

/*(async () => {
  const browser = await puppeteer.launch({
    headless: true,
    args: ["--no-sandbox"]
  });*/
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

  await page.type("#username", "Compliance Bot");
  await page.type("#password", "C0mpl1anceB0t2026");

  await Promise.all([
    page.waitForNavigation({ waitUntil: "domcontentloaded" }),
    page.click("button[type=submit]")
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

while (true) {
  await page.goto("http://localhost:8080/dm");

  const conversationLinks = await page.$$eval(
    "a.dm-item",
    links => links.map(link => link.href)
  );

  console.log("Gefundene DMs:", conversationLinks);

  for (const link of conversationLinks) {
    console.log("Öffne:", link);

    await page.goto(link, {
      waitUntil: "domcontentloaded",
      timeout: 60000
    });
    await page.waitForTimeout(3000);
  }

  await page.waitForTimeout(60000);
}

  await browser.close();
})();