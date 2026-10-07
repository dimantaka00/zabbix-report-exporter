import {test,expect,type Page} from "@playwright/test";
const host={hostid:"1",host:"host",name:"Test host",status:"0"};
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
async function mockAPI(page:Page){
  let schedules=[{...initial}],generated:any=null;
  await page.route("**/api/v1/**",async route=>{
    const request=route.request(),url=new URL(request.url()),path=url.pathname.replace("/api/v1","");
    let data:any=[],total:number|undefined;
    if(path==="/zabbix/hosts")data=[host];
    else if(path==="/zabbix/hosts/1/items")data=items;
    else if(path==="/zabbix/items/10/data")data=sample;
    else if(path==="/dashboard/summary")data={total_schedules:schedules.length,active_schedules:schedules.filter(s=>s.enabled).length,total_reports:26};
    else if(path==="/dashboard/status")data={backend:"connected",postgresql:"connected",redis:"connected",zabbix:"connected",scheduler:"running"};
    else if(path==="/history"){data=url.searchParams.get("offset")==="25"?[{...log,id:26,schedule_name:"Older report"}]:[log];total=26;}
    else if(path==="/reports/generate"){
      generated=request.postDataJSON();
      return route.fulfill({status:200,headers:{"Content-Type":"application/pdf","Content-Disposition":'attachment; filename="generated.pdf"',"X-Report-Status":"PARTIAL"},body:"%PDF-1.4\nmock"});
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
  (page as any).__runtimeErrors=errors;
});
test.afterEach(async({page})=>{expect((page as any).__runtimeErrors).toEqual([]);});

test("dashboard previews constant data and exports several metrics with partial warning",async({page})=>{
  const state=await mockAPI(page);await page.goto("/");
  await page.getByRole("combobox",{name:"Host",exact:true}).selectOption("1");
  await page.getByRole("checkbox",{name:"CPU"}).check();
  await page.getByRole("checkbox",{name:"Memory"}).check();
  await expect(page.getByRole("checkbox",{name:"Text log"})).toHaveCount(0);
  await page.getByRole("button",{name:"Tampilkan grafik"}).click();
  await expect(page.getByRole("img",{name:"Grafik CPU"})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
  await expect(page.locator(".stat-grid.compact")).toContainText("Rata-rata");
  const download=page.waitForEvent("download");
  await page.getByRole("button",{name:"Ekspor PDF (2 metrik)"}).click();
  expect((await download).suggestedFilename()).toBe("generated.pdf");
  expect(state.generated().item_ids).toEqual(["10","11"]);
  await expect(page.getByRole("status")).toContainText("sebagian data");
  await expect(page.getByText("Memory: Tidak ada data.",{exact:true})).toBeVisible();
  await page.screenshot({path:test.info().outputPath("dashboard.png"),fullPage:true});
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
  await page.route("**/api/v1/zabbix/hosts/1/items",route=>route.fulfill({status:502,json:{detail:"Zabbix tidak terhubung"}}));
  await page.getByRole("combobox",{name:"Host",exact:true}).selectOption("");
  await page.getByRole("combobox",{name:"Host",exact:true}).selectOption("1");
  await expect(page.locator(".alert.error")).toHaveText("Zabbix tidak terhubung");
});

test("switching away from a loading host resets controls",async({page})=>{
  await mockAPI(page);
  await page.route("**/api/v1/zabbix/hosts/1/items",async route=>{
    await new Promise(resolve=>setTimeout(resolve,500));await route.fulfill({json:{success:true,data:items}});
  });
  await page.goto("/schedules");
  await page.getByRole("combobox",{name:"Host",exact:true}).selectOption("1");
  await expect(page.getByText("Memuat metrik…")).toBeVisible();
  await page.getByRole("combobox",{name:"Host",exact:true}).selectOption("");
  await expect(page.getByText("Memuat metrik…")).toHaveCount(0);
  await expect(page.getByRole("button",{name:"Simpan jadwal"})).toBeEnabled();
});
