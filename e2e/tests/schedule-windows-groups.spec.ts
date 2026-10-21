import {test,expect} from "@playwright/test";

test("daily report window, date bounds and actual CS COMNET groups persist and restrict host choices",async({page})=>{
  let saved:any,rows:any[]=[];const previews:string[][]=[],hostQueries:string[][]=[];
  const catalog=[{zabbix_server:"primary",group_id:"10",name:"Balai Internet Comnet",suggested_categories:["CS"]},
    {zabbix_server:"secondary",group_id:"10",name:"DC-Internet Comnet",suggested_categories:["CS"]},
    {zabbix_server:"primary",group_id:"20",name:"TELKOM",suggested_categories:["TLK"]},
    {zabbix_server:"primary",group_id:"30",name:"ICON-UPS",suggested_categories:["ICON"]},
    {zabbix_server:"primary",group_id:"40",name:"Hypernet",suggested_categories:["HYP"]},
    {zabbix_server:"primary",group_id:"50",name:"MILES",suggested_categories:["MILES"]}];
  await page.route("**/api/v1/**",async route=>{
    const req=route.request(),url=new URL(req.url()),path=url.pathname.replace("/api/v1","");let data:any=[];
    if(path==="/auth/me")data={authentication_enabled:false};
    else if(path==="/zabbix/servers")data=[{id:"primary",name:"Zabbix Utama",configured:true},{id:"secondary",name:"Zabbix Cadangan",configured:true}];
    else if(path==="/auto-schedules/host-groups")data=catalog.filter(g=>url.searchParams.get("zabbix_server")==="all"||g.zabbix_server===url.searchParams.get("zabbix_server"));
    else if(path==="/auto-schedules/preview"){
      const refs=url.searchParams.getAll("group_refs");previews.push(refs);
      data={hosts:refs.length||2,servers:[{id:"primary",hosts:refs.length||2}],max_metrics_per_pdf:20};
    }else if(path==="/zabbix/hosts"){
      const ids=url.searchParams.getAll("group_ids");hostQueries.push([url.searchParams.get("server_id")!,...ids]);
      data=ids.includes("10")?[{hostid:"1",name:"Router A",host:"router-a",status:"0"}]:[{hostid:"99",name:"CS named outside group",host:"CS-outside",status:"0"}];
    }else if(path==="/auto-schedules"&&req.method()==="POST"){
      saved=req.postDataJSON();rows=[{id:1,...saved,run_status:"WAITING",total_hosts:0,done_hosts:0,files_completed:0,failed_hosts:0,partial_hosts:0,skipped_hosts:0}];data=rows[0];
    }else if(path==="/auto-schedules")data=rows;
    await route.fulfill({json:{success:true,data}});
  });
  await page.goto("/schedules");const section=page.getByRole("region",{name:"Jadwal otomatis semua host"});
  await expect(section.getByLabel("Jam mulai laporan")).toHaveValue("00:00");
  await expect(section.getByLabel("Jam akhir laporan")).toHaveValue("23:59");
  for(const category of ["CS","TLK","ICON","HYP","MILES"])await expect(section.getByLabel(`Kategori ${category}`,{exact:true})).toBeVisible();
  await section.getByLabel("Kategori CS",{exact:true}).check();
  await expect.poll(()=>previews.at(-1)).toEqual(["primary:10","secondary:10"]);
  await section.getByRole("button",{name:"Atur group CS",exact:true}).click();
  await section.getByLabel("Group CS DC-Internet Comnet Zabbix Cadangan",{exact:true}).uncheck();
  await expect.poll(()=>previews.at(-1)).toEqual(["primary:10"]);
  await section.getByLabel("Cakupan laporan otomatis").selectOption("selected");
  const choice=section.getByLabel("Pilih host otomatis Router A \u00b7 Zabbix Utama",{exact:true});
  await expect(choice).toBeVisible();await choice.check();
  await expect(section.getByRole("checkbox",{name:/CS named outside group/})).toHaveCount(0);
  expect(hostQueries).toContainEqual(["primary","10"]);
  await section.getByLabel("Jam mulai laporan").fill("08:15");await section.getByLabel("Jam akhir laporan").fill("17:30");
  await section.getByLabel("Tanggal mulai jadwal").fill("2026-10-13");await section.getByLabel("Tanggal akhir jadwal").fill("2026-10-31");
  await section.getByLabel("Jam eksekusi harian").fill("07:00");
  await section.getByRole("button",{name:"Simpan otomatis",exact:true}).click();
  await expect(section.getByRole("status")).toContainText("tersimpan");
  expect(saved).toMatchObject({data_start_time:"08:15",data_end_time:"17:30",date_start:"2026-10-13",date_end:"2026-10-31",hour:7,minute:0,enabled:false,package_zip:true,host_categories:["CS"],host_groups:[{category:"CS",zabbix_server:"primary",group_id:"10"}],host_selections:[{zabbix_server:"primary",host_id:"1",item_ids:null}]});
  await section.getByRole("button",{name:"Edit otomatis",exact:true}).click();
  await expect(section.getByLabel("Jam mulai laporan")).toHaveValue("08:15");
  await expect(section.getByLabel("Jam akhir laporan")).toHaveValue("17:30");
  await expect(section.getByLabel("Tanggal akhir jadwal")).toHaveValue("2026-10-31");
  await expect(section.getByLabel("Kategori CS",{exact:true})).toBeChecked();
  await expect(choice).toBeChecked();
  await section.getByLabel("Sumber jadwal otomatis").selectOption("secondary");
  await expect(section.getByText(/Pilih minimal satu group Zabbix untuk kategori CS/)).toBeVisible();
  await section.getByRole("button",{name:"Perbarui otomatis",exact:true}).click();
  await expect(section.getByRole("alert")).toContainText("setiap kategori terpilih");
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test("invalid same-day windows and reversed dates cannot be saved",async({page})=>{
  let posts=0;
  await page.route("**/api/v1/**",async route=>{
    const path=new URL(route.request().url()).pathname;let data:any=[];
    if(path.endsWith("/auth/me"))data={authentication_enabled:false};
    if(path.endsWith("/preview"))data={hosts:0,servers:[],max_metrics_per_pdf:20};
    if(path.endsWith("/auto-schedules")&&route.request().method()==="POST")posts++;
    await route.fulfill({json:{success:true,data}});
  });
  await page.goto("/schedules");const section=page.getByRole("region",{name:"Jadwal otomatis semua host"});
  await section.getByLabel("Jam mulai laporan").fill("18:00");await section.getByLabel("Jam akhir laporan").fill("08:00");
  await section.getByRole("button",{name:"Simpan otomatis",exact:true}).click();
  await expect(section.getByRole("alert")).toContainText("Jam akhir laporan");
  await section.getByLabel("Jam mulai laporan").fill("00:00");await section.getByLabel("Jam akhir laporan").fill("23:59");
  await section.getByLabel("Tanggal mulai jadwal").fill("2026-10-31");await section.getByLabel("Tanggal akhir jadwal").fill("2026-10-13");
  await section.getByRole("button",{name:"Simpan otomatis",exact:true}).click();
  await expect(section.getByRole("alert")).toContainText("Tanggal akhir jadwal");expect(posts).toBe(0);
});
