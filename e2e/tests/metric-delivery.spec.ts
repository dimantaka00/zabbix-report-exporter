import {test,expect,type Page} from "@playwright/test";

const host={hostid:"1",host:"router",name:"Router",status:"0"};
const item={itemid:"10",hostid:"1",name:"CPU",key_:"cpu",units:"%",value_type:"0",status:"0"};

async function setup(page:Page){
  const state={reads:0,temporaryFailures:0,failRefresh:false,exports:0,exportStatus:200,reportReads:0};
  await page.route("**/api/v1/**",async route=>{
    const url=new URL(route.request().url()),path=url.pathname.replace("/api/v1","");
    let data:any=[];
    if(path==="/auth/me")data={authentication_enabled:false};
    else if(path==="/auth/visit")data={};
    else if(path==="/zabbix/servers")data=[{id:"primary",name:"Zabbix 7",configured:true}];
    else if(path==="/zabbix/hosts")data=[host];
    else if(path==="/zabbix/hosts/1/items")data=[item];
    else if(path==="/zabbix/hosts/1/details")data={...host,description:"",groups:[],templates:[],interfaces:[],proxy:{mode:"server",id:null,name:null,assigned_proxy:null},warnings:[]};
    else if(path==="/zabbix/items/10/data"){
      state.reads++;
      if(state.temporaryFailures>0){state.temporaryFailures--;return route.fulfill({status:502,json:{detail:"Gateway sementara gagal."}});}
      if(state.failRefresh)return route.fulfill({status:403,json:{detail:"Koneksi metrik belum dapat diperbarui."}});
      const start=Number(url.searchParams.get("time_from")),end=Number(url.searchParams.get("time_till"));
      data={item,source:"history",time_from:start,time_till:end,resolution:"minute",
        points:[{timestamp:start+120,value:state.reads},{timestamp:start+180,value:state.reads+1}],
        summary:{minimum:state.reads,maximum:state.reads+1,average:state.reads+.5,last:state.reads+1,samples:2}};
    }else if(path==="/reports/generate"){
      state.exports++;
      if(state.exportStatus!==200)return route.fulfill({status:state.exportStatus,json:{detail:"Data metrik belum tersedia untuk PDF."}});
      return route.fulfill({headers:{"Content-Type":"application/pdf","Content-Disposition":'attachment; filename="Router.pdf"',"X-Report-Status":"SUCCESS"},body:"%PDF-1.4\ncomplete test report\n%%EOF"});
    }else if(path==="/reports"){
      state.reportReads++;
      data=[{filename:`report_${state.reportReads}.pdf`,size:1024,created:1792550000,download_url:"/api/v1/reports/report.pdf"}];
    }else if(path==="/dashboard/summary")data={total_schedules:0,active_schedules:0,total_reports:1};
    else if(path==="/dashboard/status")data={backend:"connected",postgresql:"connected",redis:"connected",zabbix:"connected",scheduler:"running"};
    return route.fulfill({json:{success:true,data,total:Array.isArray(data)?data.length:undefined}});
  });
  return state;
}

async function selectMetric(page:Page){
  await page.goto("/");
  await page.getByRole("combobox",{name:"Host",exact:true}).selectOption("1");
  await page.getByRole("checkbox",{name:/^CPU/}).check();
}

test("first preview recovers from two gateway failures without repeated clicks",async({page})=>{
  const state=await setup(page);state.temporaryFailures=2;
  await selectMetric(page);
  await page.getByRole("button",{name:"Tampilkan grafik",exact:true}).click();
  await expect(page.getByRole("img",{name:"Grafik CPU",exact:true})).toBeVisible();
  expect(state.reads).toBe(3);expect(state.exports).toBe(0);
  await expect(page.getByRole("table",{name:"Statistik harian",exact:true})).toContainText("4 %");
});

test("preview refreshes automatically and keeps its last graph during a failed refresh",async({page})=>{
  await page.clock.install();
  const state=await setup(page);await selectMetric(page);
  await page.getByRole("button",{name:"Tampilkan grafik",exact:true}).click();
  const path=page.getByRole("img",{name:"Grafik CPU",exact:true}).locator('path[fill="none"]');
  await expect(path).toBeVisible();const initial=await path.getAttribute("d");
  await page.clock.fastForward(15000);
  await expect.poll(()=>state.reads).toBe(2);
  await expect(page.getByRole("table",{name:"Statistik harian",exact:true})).toContainText("3 %");
  const fresh=await path.getAttribute("d");
  expect(fresh).not.toBeNull();expect(initial).not.toBeNull();
  state.failRefresh=true;
  await page.clock.fastForward(15000);
  await expect(page.getByRole("main").getByRole("alert")).toContainText("data terakhir tetap ditampilkan");
  await expect(path).toHaveAttribute("d",fresh!);
  state.failRefresh=false;
  await page.clock.fastForward(15000);
  await expect.poll(()=>state.reads).toBe(4);
  await expect(page.getByRole("table",{name:"Statistik harian",exact:true})).toContainText("5 %");
  await expect(page.getByRole("main").getByRole("alert")).toHaveCount(0);
});

test("automatic refresh can be paused",async({page})=>{
  await page.clock.install();const state=await setup(page);await selectMetric(page);
  await page.getByRole("button",{name:"Tampilkan grafik",exact:true}).click();
  await expect(page.getByRole("img",{name:"Grafik CPU",exact:true})).toBeVisible();
  await page.getByRole("checkbox",{name:"Perbarui grafik otomatis setiap 15 detik"}).uncheck();
  await page.clock.fastForward(45000);expect(state.reads).toBe(1);
});

test("first export downloads the complete PDF and keeps its object URL alive",async({page})=>{
  await page.clock.install();const state=await setup(page);
  await page.addInitScript(()=>{
    (window as any).__revoked=[];
    const original=URL.revokeObjectURL.bind(URL);
    URL.revokeObjectURL=url=>{(window as any).__revoked.push(url);original(url);};
  });
  await selectMetric(page);await page.getByLabel("Judul laporan",{exact:true}).fill("Current report");
  const pending=page.waitForEvent("download");
  await page.getByRole("button",{name:/Ekspor PDF/}).click();
  const download=await pending;
  expect(download.suggestedFilename()).toBe("Router.pdf");expect(await download.failure()).toBeNull();
  expect(state.exports).toBe(1);
  expect(await page.evaluate(()=>(window as any).__revoked.length)).toBe(0);
  await page.clock.fastForward(60000);
  expect(await page.evaluate(()=>(window as any).__revoked.length)).toBe(1);
});

test("a failed PDF generation is not automatically submitted multiple times",async({page})=>{
  const state=await setup(page);state.exportStatus=502;await selectMetric(page);
  await page.getByLabel("Judul laporan",{exact:true}).fill("Current report");
  await page.getByRole("button",{name:/Ekspor PDF/}).click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText("Data metrik belum tersedia");
  expect(state.exports).toBe(1);
});

test("finished reports appear automatically without a manual refresh",async({page})=>{
  await page.clock.install();const state=await setup(page);await page.goto("/reports");
  await expect(page.getByRole("cell",{name:"report_1.pdf",exact:true})).toBeVisible();
  await page.clock.fastForward(5000);
  await expect(page.getByRole("cell",{name:"report_2.pdf",exact:true})).toBeVisible();
  expect(state.reportReads).toBe(2);
});
