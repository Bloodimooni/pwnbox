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

(async () => {
  const browser = await puppeteer.launch({
    headless: true,
    args: ["--no-sandbox"]
  });

  const page = await browser.newPage();

  // Login
  await page.goto("http://web:5000/login");

  await page.type("#username", "admin");
  await page.type("#password", "adminpassword");
  await page.click("button[type=submit]");

  await page.waitForNavigation();

  // Öffne DM Chat
  await page.goto("http://web:5000/dm/1");

  // Warte damit XSS Zeit hat auszuführen
  await page.waitForTimeout(60000);

  await browser.close();
})();