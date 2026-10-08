import {test,expect,type Page} from "@playwright/test";
const host={hostid:"1",host:"host",name:"Test host",status:"0"};
const disabledHost={hostid:"2",host:"archived-router",name:"Archived router",status:"1"};
const items=[
  {itemid:"10",hostid:"1",name:"CPU",key_:"cpu",units:"%",value_type:"0",status:"0"},
  {itemid:"11",hostid:"1",name:"Memory",key_:"memory",units:"%",value_type:"0",status:"0"},
  {itemid:"12",hostid:"1",name:"Text log",key_:"log",units:"",value_type:"1",status:"0"},
];
const initial={id:1,name:"Daily test",host_id:"1",host_name:"Test host",item_ids:["10"],
  hour:7,minute:0,timezone:"Asia/Jakarta",enabled:true,last_run_date:null,next_retry_at:null,last_error:null};
const log={id:1,schedule_name:"Daily test",host_name:"Test host",started_at:"2026-10-07T07:00:00+07:00",
  finished_at:"2026-10-07T07:00:02+07:00",status:"PARTIAL",trigger_type:"scheduled",
  error_message:"Memory: Tidak ada data.",report_filename:"test.pdf"};
const sample={item:items[0],source:"history",points:[{timestamp:1,value:1},{timestamp:2,value:1}],
  summary:{minimum:1,maximum:1,average:1,samples:2}};
async function mockAPI(page:Page, disposition='attachment; filename="Test_host_2026-03-18_a1b2c3d4.pdf"'){
  let schedules=[{...initial}],generated:any=null;
  await page.route("**/api/v1/**",async route=>{
    const request=route.request(),url=new URL(request.url()),path=url.pathname.replace("/api/v1","");
    let data:any=[],total:number|undefined;
    if(path==="/zabbix/servers")data=[
      {id:"primary",name:"Zabbix 1",configured:true},
      {id:"secondary",name:"Zabbix 2",configured:true},
    ];
    else if(path==="/zabbix/hosts")data=[host,disabledHost];
    else if(path==="/zabbix/hosts/1/items")data=items;
    else if(path==="/zabbix/hosts/2/items")data=items.map(item=>({...item,hostid:"2"}));
    else if(path==="/zabbix/hosts/2/downtime-triggers")data=[];
    else if(path==="/zabbix/hosts/1/downtime-triggers")data=[
      {triggerid:"10",name:"Unavailable by ICMP ping",value:"0",status:"0",state:"0",recommended:true},
    ];
    else if(path==="/zabbix/hosts/1/downtime")data={host,trigger:{triggerid:"10",name:"Unavailable by ICMP ping"},
      status:"available",current_status:"online",status_at_end:"unknown",events:[],total_downtime_seconds:0,
      time_from:Number(url.searchParams.get("time_from")),time_till:Number(url.searchParams.get("time_till")),as_of:1791331200};
    else if(path==="/zabbix/items/10/data" || path==="/zabbix/items/11/data"){
      const start=Number(url.searchParams.get("time_from")),end=Number(url.searchParams.get("time_till"));
      data={...sample,item:path.includes("/11/") ? items[1] : items[0],time_from:start,time_till:end,
        resolution:url.searchParams.get("resolution"),points:[{timestamp:start+120,value:1,num:1},{timestamp:end-120,value:1,num:1}]};
    }
    else if(path==="/dashboard/summary")data={total_schedules:schedules.length,active_schedules:schedules.filter(s=>s.enabled).length,total_reports:26};
    else if(path==="/dashboard/status")data={backend:"connected",postgresql:"connected",redis:"connected",zabbix:"connected",zabbix_secondary:"connected",scheduler:"running"};
    else if(path==="/history"){data=url.searchParams.get("offset")==="25"?[{...log,id:26,schedule_name:"Older report"}]:[log];total=26;}
    else if(path==="/reports/generate"){
      generated=request.postDataJSON();
      return route.fulfill({status:200,headers:{"Content-Type":"application/pdf","Content-Disposition":disposition,"X-Report-Status":"PARTIAL"},body:"%PDF-1.4\nmock"});
    }
    else if(path==="/reports"){const offset=Number(url.searchParams.get("offset")||0);
      data=Array.from({length:offset===25?1:25},(_,i)=>({filename:`report_${offset+i+1}.pdf`,created:1791327600,size:2520,download_url:"/api/v1/reports/test.pdf"}));total=26;}
    else if(path==="/schedules"&&request.method()==="GET")data=schedules;
    else if(path==="/schedules"&&request.method()==="POST"){data={...initial,...request.postDataJSON(),id:2};schedules.push(data);}
    else if(path==="/schedules/1"&&request.method()==="PUT"){data={...schedules[0],...request.postDataJSON()};schedules[0]=data;}
    else if(path==="/schedules/1/status"){data={...schedules[0],...request.postDataJSON()};schedules[0]=data;}
    else if(path==="/schedules/1/run"){data={status:"SUCCESS"};schedules[0].last_run_date="2026-10-07" as any;}
    else if(path==="/schedules/1"&&request.method()==="DELETE"){schedules=[];}
    else return route.fulfill({status:404,json:{detail:`Unexpected API: ${path}`}});
    await route.fulfill({json:{success:true,data,...(total===undefined?{}:{total})}});
  });
  return {generated:()=>generated,schedules:()=>schedules};
}
test.beforeEach(async({page})=>{
  const errors:string[]=[];page.on("pageerror",e=>errors.push(e.message));
  page.on("console",message=>{
    if(message.type()==="error" && /hydration|hydrating|Minified React error/i.test(message.text()))errors.push(message.text());
  });
  (page as any).__runtimeErrors=errors;
});
test.afterEach(async({page})=>{expect((page as any).__runtimeErrors).toEqual([]);});

test("theme preference persists across pages and reloads with the developer credit",async({page})=>{
  await page.emulateMedia({colorScheme:"light"});
  await mockAPI(page);await page.goto("/");
  const toggle=page.getByRole("switch",{name:"Mode gelap"});
  await expect(toggle).not.toBeChecked();
  await page.getByRole("combobox",{name:"Host",exact:true}).selectOption("1");
  await page.getByRole("checkbox",{name:"CPU"}).check();
  await page.getByRole("button",{name:"Tampilkan grafik"}).click();
  await expect(page.getByRole("img",{name:"Grafik CPU"})).toBeVisible();
  await page.screenshot({path:test.info().outputPath("theme-light-dashboard.png"),fullPage:true});
  await toggle.click();
  await expect(toggle).toBeChecked();
  await expect(page.locator("html")).toHaveAttribute("data-theme","dark");
  await expect(page.locator(".theme-dark-label")).toBeVisible();
  await expect(page.locator(".theme-light-label")).toBeHidden();
  expect(await page.evaluate(()=>getComputedStyle(document.body).backgroundColor)).toBe("rgb(11, 18, 32)");
  await expect(page.getByRole("img",{name:"Grafik CPU"}).locator('path[fill="none"]')).toHaveCSS("stroke","rgb(127, 181, 252)");
  expect(await page.evaluate(()=>localStorage.getItem("zabbix-report-theme"))).toBe("dark");
  await page.screenshot({path:test.info().outputPath("theme-dark-dashboard.png"),fullPage:true});
  for(const label of ["Jadwal","Laporan","Monitoring"]) {
    await page.getByRole("navigation").getByRole("link",{name:label,exact:true}).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme","dark");
    await expect(toggle).toBeChecked();
    await expect(page.locator(".developer-credit")).toHaveText("Developed by Daniel Christoper I.P");
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
    if(label!=="Monitoring")await page.screenshot({path:test.info().outputPath(`theme-dark-${label}.png`),fullPage:true});
  }
  await page.reload();await expect(toggle).toBeChecked();
  await toggle.click();await expect(toggle).not.toBeChecked();
  await expect(page.locator("html")).toHaveAttribute("data-theme","light");
  expect(await page.evaluate(()=>getComputedStyle(document.body).backgroundColor)).toBe("rgb(245, 247, 251)");
  await page.reload();await expect(toggle).not.toBeChecked();
});

test("theme follows the system until the user saves a preference",async({page})=>{
  await page.emulateMedia({colorScheme:"dark"});
  await mockAPI(page);await page.goto("/");
  const toggle=page.getByRole("switch",{name:"Mode gelap"});
  await expect(page.locator("html")).toHaveAttribute("data-theme","dark");
  await expect(toggle).toBeChecked();
  expect(await page.evaluate(()=>localStorage.getItem("zabbix-report-theme"))).toBeNull();
  await page.emulateMedia({colorScheme:"light"});await expect(toggle).not.toBeChecked();
  await page.emulateMedia({colorScheme:"dark"});await expect(toggle).toBeChecked();
  await toggle.click();await expect(toggle).not.toBeChecked();
  await page.emulateMedia({colorScheme:"light"});
  await page.emulateMedia({colorScheme:"dark"});
  await expect(toggle).not.toBeChecked();
  await page.reload();await expect(toggle).not.toBeChecked();
  await expect(page.locator("html")).toHaveAttribute("data-theme","light");
});

test("theme changes synchronize between browser tabs",async({page,context})=>{
  await context.addInitScript(()=>{
    if(!localStorage.getItem("zabbix-report-theme"))localStorage.setItem("zabbix-report-theme","light");
  });
  await mockAPI(page);await page.goto("/");
  const second=await context.newPage(),errors:string[]=[];
  second.on("pageerror",error=>errors.push(error.message));
  second.on("console",message=>{
    if(message.type()==="error" && /hydration|hydrating|Minified React error/i.test(message.text()))errors.push(message.text());
  });
  await mockAPI(second);await second.goto("/reports");
  const firstToggle=page.getByRole("switch",{name:"Mode gelap"});
  const secondToggle=second.getByRole("switch",{name:"Mode gelap"});
  await expect(firstToggle).not.toBeChecked();await expect(secondToggle).not.toBeChecked();
  await firstToggle.click();await expect(secondToggle).toBeChecked();
  await expect(second.locator("html")).toHaveAttribute("data-theme","dark");
  await secondToggle.click();await expect(firstToggle).not.toBeChecked();
  await expect(page.locator("html")).toHaveAttribute("data-theme","light");
  expect(errors).toEqual([]);
  await second.close();
});

test("theme can still be changed when browser storage is unavailable",async({page})=>{
  await page.addInitScript(()=>{
    Storage.prototype.getItem=()=>{throw new DOMException("Storage blocked","SecurityError");};
    Storage.prototype.setItem=()=>{throw new DOMException("Storage blocked","SecurityError");};
  });
  await page.emulateMedia({colorScheme:"light"});
  await mockAPI(page);await page.goto("/");
  const toggle=page.getByRole("switch",{name:"Mode gelap"});
  await expect(toggle).not.toBeChecked();
  await toggle.click();await expect(toggle).toBeChecked();
  await page.emulateMedia({colorScheme:"dark"});
  await page.emulateMedia({colorScheme:"light"});
  await expect(toggle).toBeChecked();
  await page.getByRole("navigation").getByRole("link",{name:"Jadwal",exact:true}).click();
  await expect(toggle).toBeChecked();
  await toggle.click();await expect(toggle).not.toBeChecked();
});

test("host status filters include disabled hosts and retain the selected host for PDF export",async({page})=>{
  const state=await mockAPI(page);await page.goto("/");
  const picker=page.locator(".host-picker");
  const select=page.getByRole("combobox",{name:"Host",exact:true});
  const filter=page.getByRole("combobox",{name:"Status host",exact:true});
  await expect(picker.locator(".host-status-summary")).toContainText("Enabled: 1");
  await expect(picker.locator(".host-status-summary")).toContainText("Disabled: 1");
  await expect(select.locator("option")).toHaveText(["Pilih host","Test host — Enabled","Archived router — Disabled"]);
  await filter.selectOption("1");
  await expect(select.locator("option")).toHaveText(["Pilih host","Archived router — Disabled"]);
  await page.getByLabel("Cari host").fill("archived-router");
  await select.selectOption("2");
  await expect(picker.locator(".host-selection-status .badge")).toHaveText("Disabled");
  await expect(picker).toContainText("data historis yang masih tersedia");
  await page.getByRole("checkbox",{name:"CPU"}).check();
  await filter.selectOption("0");
  await expect(select).toHaveValue("2");
  await expect(picker).toContainText("Host terpilih tetap ditampilkan");
  await page.getByRole("checkbox",{name:"Include downtime in PDF"}).uncheck();
  await page.getByLabel("Judul laporan",{exact:true}).fill("Archived router history");
  const download=page.waitForEvent("download");
  await page.getByRole("button",{name:"Ekspor PDF (1 metrik)"}).click();await download;
  expect(state.generated().host_id).toBe("2");
  expect(state.generated().host_name).toBe("Archived router");
  expect(state.generated().zabbix_server).toBe("primary");
  await filter.selectOption("1");
  await picker.screenshot({path:test.info().outputPath("disabled-host-picker.png")});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
  await page.getByRole("combobox",{name:"Sumber Zabbix",exact:true}).selectOption("secondary");
  await expect(filter).toHaveValue("all");
  await expect(select).toHaveValue("");
  await filter.selectOption("1");
  await select.selectOption("2");
  await expect(picker.locator(".host-selection-status .badge")).toHaveText("Disabled");
});

test("disabled hosts remain selectable when creating a daily schedule",async({page})=>{
  const state=await mockAPI(page);await page.goto("/schedules");
  const picker=page.locator(".host-picker");
  const select=page.getByRole("combobox",{name:"Host",exact:true});
  const filter=page.getByRole("combobox",{name:"Status host",exact:true});
  await expect(picker.locator(".host-status-summary")).toContainText("Disabled: 1");
  await filter.selectOption("0");
  await expect(select.locator("option")).toHaveText(["Pilih host","Test host — Enabled"]);
  await filter.selectOption("1");
  await select.selectOption("2");
  await expect(picker.locator(".host-selection-status .badge")).toHaveText("Disabled");
  await page.getByRole("checkbox",{name:"CPU"}).check();
  await page.getByLabel("Nama laporan").fill("Disabled host history");
  await picker.screenshot({path:test.info().outputPath("disabled-schedule-picker.png")});
  await page.getByRole("button",{name:"Simpan jadwal"}).click();
  await expect(page.getByRole("status")).toContainText("Jadwal berhasil dibuat");
  expect(state.schedules().at(-1)?.host_id).toBe("2");
  expect(state.schedules().at(-1)?.host_name).toBe("Archived router");
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
});

test("dashboard previews constant data and exports several metrics with partial warning",async({page})=>{
  const state=await mockAPI(page);await page.goto("/");
  await expect(page.getByLabel("Judul laporan",{exact:true})).toHaveValue("");
  await page.getByLabel("Cari host").fill("test");
  await page.getByRole("combobox",{name:"Host",exact:true}).selectOption("1");
  await page.getByLabel("Cari metrik").fill("11");
  await page.getByRole("checkbox",{name:"Memory"}).check();
  await page.getByLabel("Cari metrik").fill("");
  await page.getByRole("checkbox",{name:"Memory"}).uncheck();
  await page.getByLabel("Cari metrik").fill("cpu");
  await page.getByRole("checkbox",{name:"CPU"}).check();
  await page.getByLabel("Cari metrik").fill("");
  await page.getByRole("checkbox",{name:"Memory"}).check();
  await expect(page.getByRole("checkbox",{name:"Text log"})).toHaveCount(0);
  await page.getByRole("button",{name:"Tampilkan grafik"}).click();
  await expect(page.getByRole("img",{name:"Grafik CPU"})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
  await expect(page.getByRole("table",{name:"Statistik harian"})).toContainText("Average");
  await page.getByRole("button",{name:"Ekspor PDF (2 metrik)"}).click();
  await expect(page.getByRole("alert").filter({hasText:"Judul laporan wajib diisi."})).toBeVisible();
  expect(state.generated()).toBeNull();
  await page.getByLabel("Judul laporan",{exact:true}).fill("Laporan jaringan PUSDATIN");
  const download=page.waitForEvent("download");
  await page.getByRole("button",{name:"Ekspor PDF (2 metrik)"}).click();
  expect((await download).suggestedFilename()).toBe("Test_host_2026-03-18_a1b2c3d4.pdf");
  expect(state.generated().item_ids).toEqual(["10","11"]);
  expect(state.generated().zabbix_server).toBe("primary");
  expect(state.generated().resolution).toBe("minute");
  expect(state.generated().title).toBe("Laporan jaringan PUSDATIN");
  await expect(page.getByRole("status")).toContainText("sebagian data");
  await expect(page.getByText("Memory: Tidak ada data.",{exact:true})).toBeVisible();
  await page.screenshot({path:test.info().outputPath("dashboard.png"),fullPage:true});
});

test("PDF download preserves Unicode host names from encoded filenames",async({page})=>{
  await mockAPI(page,"attachment; filename*=utf-8''Branch_Caf%C3%A9_2026-03-18_a1b2c3d4.pdf");
  await page.goto("/");
  await page.getByLabel("Judul laporan",{exact:true}).fill("Branch network report");
  await page.getByRole("combobox",{name:"Host",exact:true}).selectOption("1");
  await page.getByRole("checkbox",{name:"CPU"}).check();
  const download=page.waitForEvent("download");
  await page.getByRole("button",{name:"Ekspor PDF (1 metrik)"}).click();
  expect((await download).suggestedFilename()).toBe("Branch_Café_2026-03-18_a1b2c3d4.pdf");
});

test("daily minute chart covers midnight through the final minute and exports one full day",async({page})=>{
  const state=await mockAPI(page);await page.goto("/");
  await page.getByLabel("Judul laporan",{exact:true}).fill("Daily network report");
  await page.getByLabel("Tanggal laporan",{exact:true}).fill("2026-03-18");
  await expect(page.getByLabel("Mulai",{exact:true})).toHaveValue("2026-03-18T00:00");
  await expect(page.getByLabel("Selesai",{exact:true})).toHaveValue("2026-03-18T23:59");
  await expect(page.getByLabel("Rincian waktu")).toHaveValue("minute");
  await page.getByRole("combobox",{name:"Host",exact:true}).selectOption("1");
  await page.getByRole("checkbox",{name:"CPU"}).check();
  const response=page.waitForResponse(r=>r.url().includes("/zabbix/items/10/data"));
  await page.getByRole("button",{name:"Tampilkan grafik"}).click();
  expect(new URL((await response).url()).searchParams.get("resolution")).toBe("minute");
  const chart=page.getByRole("img",{name:"Grafik CPU"});
  await expect(chart).toContainText("00:00");await expect(chart).toContainText("23:59");
  const table=page.getByRole("table",{name:"Statistik harian"});
  await expect(table.getByRole("row")).toHaveCount(2);
  await expect(page.locator(".chart-heading")).toContainText("18/3/2026");
  await expect(table).toContainText("CPU");
  await chart.hover();await expect(page.locator(".chart-detail")).toContainText("1 sampel");
  const download=page.waitForEvent("download");
  await page.getByRole("button",{name:"Ekspor PDF (1 metrik)"}).click();await download;
  expect(state.generated().time_till-state.generated().time_from).toBe(86399);
  expect(new Date(state.generated().time_till*1000).getSeconds()).toBe(59);
});

test("monthly report exports March 18 through 31 in one PDF with daily previews",async({page})=>{
  const state=await mockAPI(page);await page.goto("/");
  await page.getByLabel("Judul laporan",{exact:true}).fill("March network report");
  await page.getByRole("combobox",{name:"Host",exact:true}).selectOption("1");
  await page.getByRole("checkbox",{name:"CPU"}).check();
  await page.getByRole("combobox",{name:"Periode laporan",exact:true}).selectOption("monthly");
  await page.getByLabel("Bulan laporan",{exact:true}).fill("2026-03");
  await page.getByLabel("Tanggal awal",{exact:true}).fill("18");
  await page.getByLabel("Tanggal akhir",{exact:true}).fill("31");
  await expect(page.getByLabel("Mulai",{exact:true})).toHaveValue("2026-03-18T00:00");
  await expect(page.getByLabel("Selesai",{exact:true})).toHaveValue("2026-03-31T23:59");
  await expect(page.getByText("Satu PDF untuk 14 hari",{exact:false})).toBeVisible();
  await page.getByRole("button",{name:"Tampilkan grafik"}).click();
  await expect(page.locator(".daily-chart")).toHaveCount(14);
  await expect(page.locator(".chart-heading").first()).toContainText("18/3/2026");
  await expect(page.locator(".chart-heading").last()).toContainText("31/3/2026");
  await expect(page.getByRole("table",{name:"Statistik harian"})).toHaveCount(14);
  await expect(page.getByText("Tidak ada data pada hari ini",{exact:true})).toHaveCount(12);
  const download=page.waitForEvent("download");
  await page.getByRole("button",{name:"Ekspor PDF (1 metrik)"}).click();await download;
  const payload=state.generated();
  expect(payload.time_till-payload.time_from).toBe(14*86400-1);
  expect(payload.timezone).toBe("Asia/Jakarta");
  expect(payload.resolution).toBe("minute");
  expect(new Date(payload.time_from*1000).getDate()).toBe(18);
  expect(new Date(payload.time_till*1000).getDate()).toBe(31);
  expect(new Date(payload.time_till*1000).getSeconds()).toBe(59);
  await page.getByRole("combobox",{name:"Periode laporan",exact:true}).selectOption("daily");
  await expect(page.getByLabel("Tanggal laporan",{exact:true})).toHaveValue("2026-03-18");
  await expect(page.getByLabel("Selesai",{exact:true})).toHaveValue("2026-03-18T23:59");
});

test("monthly range rejects reversed dates and handles February including leap years",async({page})=>{
  const state=await mockAPI(page);await page.goto("/");
  await page.getByLabel("Judul laporan",{exact:true}).fill("Monthly network report");
  await page.getByRole("combobox",{name:"Host",exact:true}).selectOption("1");
  await page.getByRole("checkbox",{name:"CPU"}).check();
  await page.getByRole("combobox",{name:"Periode laporan",exact:true}).selectOption("monthly");
  await page.getByLabel("Bulan laporan",{exact:true}).fill("2026-03");
  await page.getByLabel("Tanggal awal",{exact:true}).fill("31");
  await page.getByLabel("Tanggal akhir",{exact:true}).fill("18");
  await page.getByRole("button",{name:"Ekspor PDF (1 metrik)"}).click();
  await expect(page.getByRole("alert").filter({hasText:"rentang tanggal yang valid"})).toBeVisible();
  expect(state.generated()).toBeNull();
  await page.getByLabel("Tanggal awal",{exact:true}).fill("18");
  await page.getByLabel("Tanggal akhir",{exact:true}).fill("31");
  await page.getByLabel("Bulan laporan",{exact:true}).fill("2026-02");
  await expect(page.getByLabel("Tanggal akhir",{exact:true})).toHaveValue("28");
  await expect(page.getByLabel("Selesai",{exact:true})).toHaveValue("2026-02-28T23:59");
  await page.getByLabel("Bulan laporan",{exact:true}).fill("2024-02");
  await page.getByLabel("Tanggal akhir",{exact:true}).fill("29");
  await expect(page.getByLabel("Selesai",{exact:true})).toHaveValue("2024-02-29T23:59");
  await page.getByLabel("Tanggal akhir",{exact:true}).fill("31");
  await page.getByRole("button",{name:"Ekspor PDF (1 metrik)"}).click();
  expect(state.generated()).toBeNull();
  await expect(page.getByLabel("Selesai",{exact:true})).toHaveValue("");
});

test("downtime displays start recovery and duration and includes the selected trigger in PDF",async({page})=>{
  const state=await mockAPI(page);
  let requestServer="";
  await page.route("**/api/v1/zabbix/hosts/1/downtime?**",async route=>{
    const url=new URL(route.request().url()),start=Number(url.searchParams.get("time_from")),end=Number(url.searchParams.get("time_till"));
    requestServer=url.searchParams.get("server_id") || "";
    await route.fulfill({json:{success:true,data:{host,trigger:{triggerid:"10",name:"Unavailable by ICMP ping"},
      status:"available",current_status:"offline",status_at_end:"offline",time_from:start,time_till:end,as_of:end+1,total_downtime_seconds:960,
      events:[{event_id:"1",status:"recovered",start_time:start+120,end_time:start+1020,duration_seconds:900,period_duration_seconds:900},
              {event_id:"2",status:"ongoing",start_time:end-59,end_time:null,duration_seconds:60,period_duration_seconds:60}]}}});
  });
  await page.goto("/");
  await page.getByRole("combobox",{name:"Sumber Zabbix",exact:true}).selectOption("secondary");
  await page.getByLabel("Tanggal laporan",{exact:true}).fill("2026-03-18");
  await page.getByRole("combobox",{name:"Host",exact:true}).selectOption("1");
  await page.getByRole("checkbox",{name:"CPU"}).check();
  await page.getByRole("combobox",{name:"Host-down trigger",exact:true}).selectOption("10");
  await page.getByRole("button",{name:"Show Downtime",exact:true}).click();
  const table=page.getByRole("table",{name:"Downtime history"});
  await expect(table.getByRole("columnheader")).toHaveText(["No","Status","Start Time","End Time","Duration"]);
  await expect(table).not.toContainText(host.name);
  await expect(table).not.toContainText("Unavailable by ICMP ping");
  await expect(table.getByRole("row")).toHaveCount(3);
  await expect(table.getByRole("row").nth(1)).toContainText("00:15:00");
  await expect(table.getByRole("row").nth(1)).toContainText("00:17:00");
  await expect(table.getByRole("row").nth(2)).toContainText("Ongoing");
  await expect(table.getByRole("row").nth(1)).toContainText("15 m");
  await expect(table.getByRole("row").nth(1).getByRole("cell").nth(1)).toHaveText("Down");
  await expect(table.getByRole("row").nth(2)).toContainText("00:01:00");
  await expect(page.locator(".downtime-summary")).toContainText("00:16:00");
  expect(requestServer).toBe("secondary");
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
  await page.locator(".downtime-card").screenshot({path:test.info().outputPath("host-downtime.png")});
  await page.getByLabel("Judul laporan",{exact:true}).fill("Host downtime report");
  let download=page.waitForEvent("download");
  await page.getByRole("button",{name:"Ekspor PDF (1 metrik)"}).click();await download;
  expect(state.generated().include_downtime).toBe(true);
  expect(state.generated().downtime_trigger_id).toBe("10");
  await page.getByRole("checkbox",{name:"Include downtime in PDF"}).uncheck();
  download=page.waitForEvent("download");
  await page.getByRole("button",{name:"Ekspor PDF (1 metrik)"}).click();await download;
  expect(state.generated().include_downtime).toBe(false);
  await page.getByRole("combobox",{name:"Host",exact:true}).selectOption("");
  await expect(table).toHaveCount(0);
});

test("downtime API failure shows an error instead of assuming the host is online",async({page})=>{
  await mockAPI(page);
  await page.route("**/api/v1/zabbix/hosts/1/downtime?**",route=>route.fulfill({status:502,json:{detail:"Event read permissions are unavailable"}}));
  await page.goto("/");
  await page.getByRole("combobox",{name:"Host",exact:true}).selectOption("1");
  await page.getByRole("button",{name:"Show Downtime",exact:true}).click();
  await expect(page.locator(".downtime-card .alert.error")).toHaveText("Event read permissions are unavailable");
  await expect(page.locator(".downtime-summary")).toHaveCount(0);
  await expect(page.getByRole("table",{name:"Downtime history"})).toHaveCount(0);
});

test("empty downtime history displays No Downtime without names",async({page})=>{
  await mockAPI(page);await page.goto("/");
  await page.getByRole("combobox",{name:"Host",exact:true}).selectOption("1");
  await page.getByRole("button",{name:"Show Downtime",exact:true}).click();
  const table=page.getByRole("table",{name:"Downtime history"});
  await expect(table.getByRole("row")).toHaveCount(2);
  await expect(table.getByRole("row").nth(1).getByRole("cell")).toHaveText(["1","No Downtime","—","—","—"]);
  await expect(table).not.toContainText(host.name);
  await expect(page.locator(".downtime-summary")).toContainText("Status at period end: Unknown");
});

test("bandwidth chart chooses network units per statistic and preserves the final sample",async({page})=>{
  await mockAPI(page);
  let values={peak:3630648,last:1000000};
  await page.route("**/api/v1/zabbix/items/10/data?**",async route=>{
    const url=new URL(route.request().url()),start=Number(url.searchParams.get("time_from"));
    const points=[{timestamp:start+120,value:8576,min:8576,max:8576,num:1,last:8576},
      {timestamp:start+240,value:(values.peak+values.last)/2,min:values.last,max:values.peak,num:2,last:values.last}];
    await route.fulfill({json:{success:true,data:{...sample,
      item:{...items[0],name:"Interface internal1(): Bits received",units:"bps"},
      points,time_from:start,time_till:Number(url.searchParams.get("time_till")),resolution:"minute"}}});
  });
  await page.goto("/");
  await page.getByRole("combobox",{name:"Host",exact:true}).selectOption("1");
  await page.getByRole("checkbox",{name:"CPU"}).check();
  for (const scenario of [
    {peak:3630648,last:1000000,unit:"Mbps",expected:["1,00 Mbps","8,58 Kbps","1,55 Mbps","3,63 Mbps"]},
    {peak:2500000,last:2500000,unit:"Mbps",expected:["2,50 Mbps","8,58 Kbps","1,67 Mbps","2,50 Mbps"]},
    {peak:363064,last:100000,unit:"Kbps",expected:["100,00 Kbps","8,58 Kbps","157,21 Kbps","363,06 Kbps"]},
    {peak:2000000000,last:500,unit:"Gbps",expected:["500,00 bps","500,00 bps","666,67 Mbps","2,00 Gbps"]},
  ]) {
    values=scenario;
    await page.getByRole("button",{name:"Tampilkan grafik"}).click();
    const chart=page.getByRole("img",{name:"Grafik Interface internal1(): Bits received"});
    await expect(chart).toContainText(scenario.unit);
    const table=page.getByRole("table",{name:"Statistik harian"});
    await expect(table.getByRole("columnheader")).toHaveText(["Interface Parameter","Last","Min","Average","Max"]);
    await expect(table.getByRole("columnheader",{name:"Last",exact:true})).toBeVisible();
    await expect(table.getByRole("columnheader",{name:"Sampel",exact:true})).toHaveCount(0);
    const cells=table.getByRole("row").nth(1).getByRole("cell");
    for (let i=0;i<scenario.expected.length;i++)await expect(cells.nth(i+1)).toHaveText(scenario.expected[i]);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
  }
  await page.screenshot({path:test.info().outputPath("bandwidth-chart.png"),fullPage:true});
});

test("network unit conversion distinguishes Mbps from MBps and data sizes",async({page})=>{
  await mockAPI(page);
  let source={units:"Mbps",values:[.001,1,2.5]};
  await page.route("**/api/v1/zabbix/items/10/data?**",async route=>{
    const url=new URL(route.request().url()),start=Number(url.searchParams.get("time_from"));
    await route.fulfill({json:{success:true,data:{...sample,
      item:{...items[0],name:"Network metric",units:source.units},
      points:source.values.map((value,index)=>({timestamp:start+index*60,value})),
      time_from:start,time_till:Number(url.searchParams.get("time_till")),resolution:"minute"}}});
  });
  await page.goto("/");
  await page.getByRole("combobox",{name:"Host",exact:true}).selectOption("1");
  await page.getByRole("checkbox",{name:"CPU"}).check();
  for(const scenario of [
    {units:"Mbps",values:[.001,1,2.5],expected:["2,50 Mbps","1,00 Kbps","1,17 Mbps","2,50 Mbps"],header:"Interface Parameter"},
    {units:"Bps",values:[1024,1024**2,2*1024**2],expected:["2,00 MBps","1,00 KBps","1,00 MBps","2,00 MBps"],header:"Interface Parameter"},
    {units:"B",values:[1024,1024**2,2*1024**2],expected:["2,00 MB","1,00 KB","1,00 MB","2,00 MB"],header:"Parameter"},
    {units:"kb",values:[1,1000,2500],expected:["2,50 Mb","1,00 Kb","1,17 Mb","2,50 Mb"],header:"Parameter"},
  ]) {
    source=scenario;
    await page.getByRole("button",{name:"Tampilkan grafik"}).click();
    const table=page.getByRole("table",{name:"Statistik harian"});
    await expect(table.getByRole("columnheader")).toHaveText([scenario.header,"Last","Min","Average","Max"]);
    await expect(table.getByRole("row").nth(1).getByRole("cell")).toHaveText(["Network metric",...scenario.expected]);
  }
});

test("schedule can be created, edited, paused, run and deleted",async({page})=>{
  const state=await mockAPI(page);await page.goto("/schedules");
  await page.getByRole("button",{name:"Edit",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Edit jadwal #1"})).toBeVisible();
  await page.getByLabel("Nama laporan").fill("Updated daily");
  await expect(page.getByRole("checkbox",{name:"CPU"})).toBeChecked();
  await page.getByRole("checkbox",{name:"Memory"}).check();
  await page.getByRole("button",{name:"Simpan perubahan"}).click();
  await expect(page.getByRole("status")).toContainText("Perubahan jadwal tersimpan");
  expect(state.schedules()[0].item_ids).toEqual(["10","11"]);
  await page.getByRole("button",{name:"Nonaktifkan",exact:true}).click();
  await expect(page.getByText("Nonaktif",{exact:true})).toBeVisible();
  page.on("dialog",dialog=>dialog.accept());
  await page.getByRole("button",{name:"Jalankan sekarang"}).click();
  await expect(page.getByRole("status")).toContainText("Laporan berhasil dibuat");
  await page.getByRole("button",{name:"Hapus",exact:true}).click();
  await expect(page.getByText("Belum ada jadwal. Buat jadwal pertama di atas.")).toBeVisible();
  await page.getByLabel("Nama laporan").fill("New schedule");
  await page.getByRole("combobox",{name:"Host",exact:true}).selectOption("1");
  await page.getByRole("checkbox",{name:"CPU"}).check();
  await page.getByRole("button",{name:"Simpan jadwal"}).click();
  await expect(page.getByRole("status")).toContainText("Jadwal berhasil dibuat");
  expect(state.schedules()[0].name).toBe("New schedule");
});

test("report archive and history have independent pagination and search",async({page})=>{
  await mockAPI(page);await page.goto("/reports");
  const archive=page.locator("section").filter({has:page.getByRole("heading",{name:"Arsip PDF"})});
  const history=page.locator("section").filter({has:page.getByRole("heading",{name:"Riwayat eksekusi",exact:true})});
  await expect(archive).toContainText("report_25.pdf");
  await archive.getByRole("button",{name:"Berikutnya"}).click();
  await expect(archive).toContainText("report_26.pdf");
  await expect(archive).not.toContainText("report_1.pdf");
  await expect(history).toContainText("Daily test");
  await history.getByRole("button",{name:"Berikutnya"}).click();
  await expect(history).toContainText("Older report");
  await page.getByLabel("Cari PDF pada halaman ini").fill("missing");
  await expect(archive).toContainText("Tidak ada PDF yang cocok");
  await page.getByRole("link",{name:"Jadwal",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Jadwal laporan"})).toBeVisible();
});

test("API failures are shown and schedule conflict leaves form intact",async({page})=>{
  await mockAPI(page);
  await page.route("**/api/v1/schedules",route=>route.request().method()==="POST"?
    route.fulfill({status:409,json:{detail:"Jadwal sedang diproses"}}):route.fallback());
  await page.goto("/schedules");
  await page.getByRole("combobox",{name:"Host",exact:true}).selectOption("1");
  await page.getByRole("checkbox",{name:"CPU"}).check();
  await page.getByRole("button",{name:"Simpan jadwal"}).click();
  await expect(page.locator(".alert.error")).toHaveText("Jadwal sedang diproses");
  await expect(page.getByRole("checkbox",{name:"CPU"})).toBeChecked();
  await page.route("**/api/v1/zabbix/hosts/1/items*",route=>route.fulfill({status:502,json:{detail:"Zabbix tidak terhubung"}}));
  await page.getByRole("combobox",{name:"Host",exact:true}).selectOption("");
  await page.getByRole("combobox",{name:"Host",exact:true}).selectOption("1");
  await expect(page.locator(".alert.error")).toHaveText("Zabbix tidak terhubung");
});

test("switching away from a loading host resets controls",async({page})=>{
  await mockAPI(page);
  await page.route("**/api/v1/zabbix/hosts/1/items*",async route=>{
    await new Promise(resolve=>setTimeout(resolve,500));await route.fulfill({json:{success:true,data:items}});
  });
  await page.goto("/schedules");
  await page.getByRole("combobox",{name:"Host",exact:true}).selectOption("1");
  await expect(page.getByText("Memuat metrik…")).toBeVisible();
  await page.getByRole("combobox",{name:"Host",exact:true}).selectOption("");
  await expect(page.getByText("Memuat metrik…")).toHaveCount(0);
  await expect(page.getByRole("button",{name:"Simpan jadwal"})).toBeEnabled();
});
