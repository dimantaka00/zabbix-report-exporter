const {chromium}=require("../e2e/node_modules/@playwright/test");
const assert=require("node:assert/strict");
const fs=require("node:fs/promises");
const path=require("node:path");

async function main(){
  const browser=await chromium.launch({channel:"chrome"});
  const errors=[],views=[];
  const baseURL=(process.env.MVP_BASE_URL || "http://127.0.0.1:8080").replace(/\/$/,"");
  const directory=path.resolve(__dirname,"../.cache");
  await fs.mkdir(directory,{recursive:true});
  try{
    for(const [name,width,height] of [["desktop",1440,1100],["tablet",820,1100],["mobile",393,851]]){
      const context=await browser.newContext({viewport:{width,height},timezoneId:"Asia/Jakarta"});
      try{
        const page=await context.newPage();
        page.on("pageerror",error=>errors.push(error.message));
        page.on("console",message=>{
          if(message.type()==="error" && /hydration|hydrating|Minified React error/i.test(message.text()))errors.push(message.text());
        });
        const response=await page.goto(baseURL);
        assert.equal(response.status(),200);
        await page.getByRole("combobox",{name:"Host",exact:true}).selectOption(process.env.MVP_HOST_ID || "16500");
        await page.locator('.metric-list input[type="checkbox"]').first().waitFor({timeout:30000});
        const incoming=page.getByRole("checkbox",{name:/bits received/i});
        const availability=page.getByRole("checkbox",{name:/SNMP agent availability/i});
        const metric=await availability.count()?availability.first():await incoming.count()?incoming.first():page.locator('.metric-list input[type="checkbox"]').first();
        await metric.check();
        await page.getByRole("button",{name:"Tampilkan grafik"}).click();
        try{await page.locator(".daily-chart svg").first().waitFor({timeout:30000});}
        catch(error){
          await page.screenshot({path:path.join(directory,`reference-live-error-${name}.png`),fullPage:true});
          console.log("UI errors:",await page.locator('[role="alert"],.chart-card .empty').allTextContents());
          throw error;
        }
        const dark=await page.evaluate(()=>({theme:document.documentElement.dataset.theme,
          background:getComputedStyle(document.body).backgroundColor,
          text:getComputedStyle(document.querySelector("h1")).color,
          stroke:getComputedStyle(document.querySelector('.daily-chart path[fill="none"]')).stroke,
          page:document.documentElement.scrollWidth,viewport:innerWidth,
          sidebar:getComputedStyle(document.querySelector(".site-header")).position}));
        assert.equal(dark.theme,"dark");
        assert.equal(dark.background,"rgb(23, 23, 35)");
        assert.equal(dark.text,"rgb(241, 241, 250)");
        assert.equal(dark.stroke,"rgb(56, 189, 248)");
        assert.ok(dark.page<=dark.viewport+1);
        assert.equal(dark.sidebar,width>820?"fixed":"static");
        await page.evaluate(()=>scrollTo(0,0));
        await page.screenshot({path:path.join(directory,`reference-live-${name}.png`),fullPage:true});
        await page.getByRole("switch",{name:"Mode gelap"}).click();
        assert.equal(await page.locator("html").getAttribute("data-theme"),"light");
        await page.reload();
        assert.equal(await page.locator("html").getAttribute("data-theme"),"light");
        for(const [href,label] of [["/schedules","Jadwal"],["/reports","Laporan"]]){
          await page.getByRole("navigation").getByRole("link",{name:label,exact:true}).click();
          await page.waitForURL(`**${href}`);
          assert.equal(await page.locator("html").getAttribute("data-theme"),"light");
          assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
        }
        views.push({name,...dark,light_preference_persisted:true,routes:["/","/schedules","/reports"]});
      }finally{await context.close();}
    }
    assert.deepEqual(errors,[]);
    const result={checked_at:new Date().toISOString(),theme:"Dark purple with cyan and mint accents",views,browser_errors:errors};
    await fs.writeFile(path.join(__dirname,"../docs/dashboard-reference-theme-validation.json"),JSON.stringify(result,null,2)+"\n");
    console.log(JSON.stringify(result,null,2));
  }finally{await browser.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
