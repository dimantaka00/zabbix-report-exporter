// Uses the running LAN application. Creates one identifiable manual PDF; never edits schedules.
const {chromium}=require("../e2e/node_modules/@playwright/test");
const fs=require("node:fs/promises");
const path=require("node:path");
async function main(){
  const baseURL=process.env.MVP_BASE_URL || "http://localhost:8080";
  const browser=await chromium.launch({channel:process.env.E2E_BROWSER_CHANNEL || "chrome"});
  const context=await browser.newContext({acceptDownloads:true,locale:"id-ID",timezoneId:"Asia/Jakarta"});
  const page=await context.newPage();
  const errors=[];page.on("pageerror",error=>errors.push(error.message));
  try{
    for(const route of ["/","/schedules","/reports"]){
      const response=await page.goto(baseURL+route);
      if(response.status()!==200)throw new Error("HTTP failed: "+route);
      await page.locator("h1").waitFor();
    }
    const statuses=await (await context.request.get(baseURL+"/api/v1/dashboard/status")).json();
    if(Object.values(statuses.data).some(value=>!["connected","running"].includes(value)))
      throw new Error("Layanan belum siap: "+JSON.stringify(statuses.data));
    await page.goto(baseURL);
    await page.getByRole("combobox",{name:"Host",exact:true}).selectOption("16500");
    await page.getByRole("checkbox",{name:/SNMP agent availability/}).check();
    await page.getByRole("checkbox",{name:/Uptime \(network\)/}).check();
    await page.getByRole("button",{name:"Tampilkan grafik"}).click();
    await page.getByRole("img",{name:"Grafik SNMP agent availability"}).waitFor();
    await page.getByLabel("Judul laporan").fill("MVP acceptance smoke");
    const downloadPromise=page.waitForEvent("download");
    await page.getByRole("button",{name:"Ekspor PDF (2 metrik)"}).click();
    const download=await downloadPromise;
    const directory=path.resolve(__dirname,"../backup");
    await fs.mkdir(directory,{recursive:true});
    const filename=download.suggestedFilename();
    const target=path.join(directory,"mvp-live-validation.pdf");
    await download.saveAs(target);
    const pdf=await fs.readFile(target);
    if(pdf.subarray(0,5).toString()!=="%PDF-" || !pdf.toString().includes("%%EOF"))
      throw new Error("PDF tidak lengkap.");
    const pages=(pdf.toString().match(/\/Type\s*\/Page\b/g)||[]).length;
    if(pages!==3)throw new Error("Expected cover and 2 metric pages, got "+pages);
    await page.getByRole("status").filter({hasText:"sebagian data"}).waitFor();
    const history=await (await context.request.get(baseURL+"/api/v1/history?limit=1")).json();
    if(history.data[0].status!=="PARTIAL" || history.data[0].report_filename!==filename ||
       history.data[0].trigger_type!=="manual_report")throw new Error("Riwayat tidak cocok dengan PDF.");
    const archive=await (await context.request.get(baseURL+"/api/v1/reports?limit=1")).json();
    if(archive.data[0].filename!==filename)throw new Error("PDF belum tampil pada arsip.");
    const downloaded=await context.request.get(baseURL+"/api/v1/reports/"+filename);
    if(!downloaded.ok() || !pdf.equals(await downloaded.body()))throw new Error("Unduhan arsip berbeda.");
    if(errors.length)throw new Error("Browser errors: "+errors.join("; "));
    await page.screenshot({path:path.join(directory,"mvp-live-dashboard.png"),fullPage:true});
    const result={checked_at:new Date().toISOString(),services:statuses.data,
      browser_errors:errors,report:{filename,pages,bytes:pdf.length,status:history.data[0].status},
      total_reports:archive.total,total_executions:history.total};
    await fs.writeFile(path.resolve(__dirname,"../docs/mvp-live-validation.json"),JSON.stringify(result,null,2)+"\n");
    console.log(JSON.stringify(result,null,2));
  }finally{await browser.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
