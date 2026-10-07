// Read-only checks against the running LAN application; no reports or schedules are written.
const assert = require("node:assert/strict");
const {chromium} = require("../e2e/node_modules/@playwright/test");
const fs = require("node:fs/promises");
const path = require("node:path");

async function main() {
  const baseURL = process.env.MVP_BASE_URL || "http://localhost:8080";
  const browser = await chromium.launch({channel:process.env.E2E_BROWSER_CHANNEL || "chrome"});
  const errors = [], views = [];
  const directory = path.resolve(__dirname, "../backup");
  await fs.mkdir(directory, {recursive:true});
  try {
    for (const [name,width,height] of [["desktop",1440,900],["tablet",768,1024],["mobile",393,851]]) {
      const context = await browser.newContext({viewport:{width,height},locale:"id-ID",timezoneId:"Asia/Jakarta"});
      try {
        const page = await context.newPage();
        page.on("pageerror", error => errors.push(name+": "+error.message));
        const routes = [];
        for (const route of ["/","/schedules","/reports"]) {
          const response = await page.goto(baseURL+route);
          assert.equal(response.status(),200,route);
          await page.locator("h1").waitFor();
          const active = await page.locator("nav a[aria-current=page]").getAttribute("href");
          assert.equal(active,route);
          const dimensions = await page.evaluate(() => ({page:document.documentElement.scrollWidth,viewport:innerWidth}));
          assert.ok(dimensions.page<=dimensions.viewport+1, name+" overflow on "+route);
          routes.push({route,status:response.status(),...dimensions});
        }
        await page.goto(baseURL);
        await page.getByRole("combobox",{name:"Host",exact:true}).selectOption(process.env.MVP_HOST_ID || "16500");
        await page.getByRole("checkbox",{name:/SNMP agent availability/}).check();
        await page.getByRole("button",{name:"Tampilkan grafik"}).click();
        await page.getByRole("img",{name:"Grafik SNMP agent availability"}).waitFor({timeout:60000});
        const statusResponse = await context.request.get(baseURL+"/api/v1/dashboard/status");
        assert.equal(statusResponse.status(),200);
        const {data:services} = await statusResponse.json();
        assert.ok(Object.values(services).every(value=>["connected","running"].includes(value)),JSON.stringify(services));
        await page.evaluate(()=>window.scrollTo(0,0));
        await page.waitForFunction(()=>window.scrollY===0);
        const layout = await page.evaluate(()=>{
          const header=document.querySelector(".site-header"),r=header.getBoundingClientRect();
          return {page:document.documentElement.scrollWidth,viewport:innerWidth,sidebar_top:r.top,sidebar_left:r.left,sidebar_position:getComputedStyle(header).position};
        });
        assert.ok(layout.page<=layout.viewport+1,name+" overflow after chart");
        assert.equal(layout.sidebar_top,0);
        if (width>820) assert.equal(layout.sidebar_position,"fixed");
        else assert.equal(layout.sidebar_position,"static");
        if(name!=="tablet") await page.screenshot({path:path.join(directory,"light-enterprise-"+name+".png"),fullPage:true});
        views.push({name,routes,chart:"SNMP agent availability",layout,services});
      } finally { await context.close(); }
    }
    assert.deepEqual(errors,[]);
    const result={checked_at:new Date().toISOString(),theme:"Light enterprise",browser_errors:errors,views};
    await fs.writeFile(path.resolve(__dirname,"../docs/dashboard-theme-validation.json"),JSON.stringify(result,null,2)+"\n");
    console.log(JSON.stringify(result,null,2));
  } finally { await browser.close(); }
}
main().catch(error=>{console.error(error);process.exitCode=1;});
