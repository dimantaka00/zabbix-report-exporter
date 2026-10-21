import {test,expect} from "@playwright/test";

test("automatic daily schedule supports midnight, last minute, all metrics and queue controls",async({page})=>{
  let rows:any[]=[],saved:any;
  await page.route("**/api/v1/**",async route=>{
    const request=route.request(),url=new URL(request.url()),path=url.pathname.replace("/api/v1","");
    let data:any=[],total:number|undefined;
    if(path==="/auth/me")data={authentication_enabled:false};
    else if(path==="/zabbix/servers")data=[{id:"primary",name:"Zabbix 7",configured:true},{id:"secondary",name:"Zabbix 2",configured:true}];
    else if(path==="/zabbix/hosts"||path==="/schedules"||path==="/auto-schedules/host-groups")data=[];
    else if(path==="/auto-schedules/preview")data={hosts:2,servers:[{id:"primary",hosts:1},{id:"secondary",hosts:1}],max_metrics_per_pdf:20};
    else if(path==="/auto-schedules"&&request.method()==="POST"){
      saved=request.postDataJSON();data={id:1,...saved,run_status:"WAITING",total_hosts:0,done_hosts:0,files_completed:0,failed_hosts:0,partial_hosts:0,skipped_hosts:0};rows=[data];
    }else if(path==="/auto-schedules/1"&&request.method()==="PUT"){
      saved=request.postDataJSON();data={...rows[0],...saved};rows=[data];
    }else if(path==="/auto-schedules/1/status"){
      data={...rows[0],...request.postDataJSON(),run_status:"RUNNING",total_hosts:2,done_hosts:1,files_completed:2,report_date:"2026-10-11"};rows=[data];
    }else if(path==="/auto-schedules/1/tasks"){
      total=26;const offset=Number(url.searchParams.get("offset"));
      data=Array.from({length:offset===25?1:25},(_,i)=>({id:offset+i+1,host_name:`Router ${offset+i+1}`,zabbix_server:"primary",status:"SUCCESS",item_offset:25,total_metrics:25,files_completed:2}));
    }else if(path==="/auto-schedules/1"&&request.method()==="DELETE"){rows=[];}
    else if(path==="/auto-schedules")data=rows;
    else return route.fulfill({status:404,json:{detail:`Unexpected ${path}`}});
    await route.fulfill({json:{success:true,data,...(total===undefined?{}:{total})}});
  });
  await page.goto("/schedules");
  const section=page.getByRole("region",{name:"Jadwal otomatis semua host"});
  await expect(section.getByRole("heading",{name:"Jadwal otomatis host & metrik"})).toBeVisible();
  await expect(section.getByText(/Cakupan saat ini: 2 host/)).toBeVisible();
  await expect(section.getByLabel("Aktifkan otomatis semua host")).not.toBeChecked();
  await section.getByLabel("Jam eksekusi harian").fill("00:00");
  await section.getByRole("button",{name:"Simpan otomatis",exact:true}).click();
  await expect(section.getByText("Jadwal otomatis tersimpan dalam keadaan nonaktif.")).toBeVisible();
  expect(saved).toMatchObject({hour:0,minute:0,zabbix_server:"all",host_status:"all",enabled:false});
  await section.getByRole("button",{name:"Edit otomatis",exact:true}).click();
  await section.getByLabel("Jam eksekusi harian").fill("23:59");
  await section.getByRole("button",{name:"Perbarui otomatis"}).click();
  await expect(section.getByRole("cell",{name:/23:59/})).toBeVisible();
  expect(saved).toMatchObject({hour:23,minute:59});
  await section.getByRole("button",{name:"Aktifkan otomatis",exact:true}).click();
  await expect(section.getByText("1/2 host · 2 PDF")).toBeVisible();
  await section.getByRole("button",{name:"Detail host",exact:true}).click();
  const details=section.getByRole("table",{name:"Detail antrean host"});
  await expect(details.getByRole("cell",{name:"Router 1 primary",exact:true})).toBeVisible();
  await section.getByRole("button",{name:"Host berikutnya"}).click();
  await expect(details.getByRole("cell",{name:"Router 26 primary",exact:true})).toBeVisible();
  await expect(details.getByRole("cell",{name:"25/25",exact:true})).toBeVisible();
  await section.getByRole("button",{name:"Jeda otomatis",exact:true}).click();
  await expect(section.getByText(/Antrean dijeda setelah/)).toBeVisible();
  page.once("dialog",dialog=>dialog.accept());
  await section.getByRole("button",{name:"Hapus otomatis",exact:true}).click();
  await expect(section.getByText("Belum ada jadwal otomatis tersimpan.")).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
});

test("automatic schedules show inventory and save errors",async({page})=>{
  await page.route("**/api/v1/**",async route=>{
    const path=new URL(route.request().url()).pathname;
    if(path.endsWith("/auth/me"))return route.fulfill({json:{success:true,data:{authentication_enabled:false}}});
    if(path.endsWith("/preview"))return route.fulfill({status:502,json:{detail:"Inventaris tidak tersedia"}});
    if(path.endsWith("/auto-schedules")&&route.request().method()==="POST")return route.fulfill({status:400,json:{detail:"Sumber belum dikonfigurasi"}});
    return route.fulfill({json:{success:true,data:[]}});
  });
  await page.goto("/schedules");
  const section=page.getByRole("region",{name:"Jadwal otomatis semua host"});
  await expect(section.getByText("Inventaris tidak tersedia")).toBeVisible();
  await section.getByRole("button",{name:"Simpan otomatis",exact:true}).click();
  await expect(section.getByRole("alert")).toHaveText("Sumber belum dikonfigurasi");
});

test("selected hosts keep per-source metrics, validate empty choices and show ZIP downloads",async({page})=>{
  let saved:any,rows:any[]=[];
  await page.route("**/api/v1/**",async route=>{
    const request=route.request(),url=new URL(request.url()),path=url.pathname.replace("/api/v1","");let data:any=[];
    if(path==="/auth/me")data={authentication_enabled:false};
    else if(path==="/zabbix/servers")data=[{id:"primary",name:"Zabbix 7",configured:true},{id:"secondary",name:"Zabbix 2",configured:true}];
    else if(path==="/zabbix/hosts")data=[{hostid:"1",name:"Router",host:"router",status:"0"},{hostid:"2",name:"Other",host:"other",status:"1"}];
    else if(path==="/zabbix/hosts/1/items")data=[{itemid:"10",name:"CPU",units:"%",key_:"cpu",status:"0",value_type:"0"},{itemid:"11",name:"Memory",units:"%",key_:"mem",status:"0",value_type:"3"},{itemid:"12",name:"Log",units:"",key_:"log",status:"0",value_type:"1"}];
    else if(path==="/auto-schedules/preview")data={hosts:4,servers:[{id:"primary",hosts:2},{id:"secondary",hosts:2}],max_metrics_per_pdf:20};
    else if(path==="/auto-schedules"&&request.method()==="POST"){
      saved=request.postDataJSON();data={...saved,id:1,run_id:1,run_status:"COMPLETED",total_hosts:2,done_hosts:2,files_completed:2,partial_hosts:0,failed_hosts:0,skipped_hosts:0,archive_status:"READY",archive_download_url:"/api/v1/reports/bundle.zip",archive_size:1234,original_size:4321};rows=[data];
    }else if(path==="/auto-schedules")data=rows;
    else if(path==="/schedules"||path==="/auto-schedules/host-groups")data=[];
    else return route.fulfill({status:404,json:{detail:`Unexpected ${path}`}});
    await route.fulfill({json:{success:true,data}});
  });
  await page.goto("/schedules");const section=page.getByRole("region",{name:"Jadwal otomatis semua host"});
  await section.getByLabel("Cakupan laporan otomatis").selectOption("selected");
  await section.getByRole("button",{name:"Simpan otomatis",exact:true}).click();
  await expect(section.getByRole("alert")).toContainText("Pilih minimal satu host");expect(saved).toBeUndefined();
  await section.getByLabel("Pilih host otomatis Router · Zabbix 7",{exact:true}).check();
  await section.getByRole("button",{name:"Atur metrik Router · Zabbix 7",exact:true}).click();
  await section.getByLabel("Cakupan metrik host otomatis").selectOption("selected");
  await section.getByRole("button",{name:"Simpan otomatis",exact:true}).click();
  await expect(section.getByRole("alert")).toContainText("Pilih minimal satu host");expect(saved).toBeUndefined();
  const picker=section.locator(".auto-metric-editor");
  await picker.getByRole("checkbox",{name:"CPU"}).check();
  await expect(picker.getByRole("checkbox",{name:"Log",exact:true})).toHaveCount(0);
  await section.getByLabel("Pilih host otomatis Router · Zabbix 2",{exact:true}).check();
  await expect(section.getByText(/Cakupan laporan: 2 host terpilih dari 4 host tersedia/)).toBeVisible();
  await section.getByLabel("Hanya host yang sudah dipilih").check();
  await expect(section.getByRole("checkbox",{name:/Pilih host otomatis/})).toHaveCount(2);
  await expect(section.getByLabel("Kemas PDF menjadi satu ZIP")).toBeChecked();
  await expect(section.getByLabel("Aktifkan otomatis host terpilih")).not.toBeChecked();
  await section.getByRole("button",{name:"Simpan otomatis",exact:true}).click();
  await expect(section.getByRole("link",{name:"Unduh ZIP"})).toHaveAttribute("href","/api/v1/reports/bundle.zip");
  expect(saved).toMatchObject({selection_mode:"selected",package_zip:true,enabled:false,host_selections:[{zabbix_server:"primary",host_id:"1",item_ids:["10"]},{zabbix_server:"secondary",host_id:"1",item_ids:null}]});
  await section.getByRole("button",{name:"Edit otomatis",exact:true}).click();
  await expect(section.getByLabel("Pilih host otomatis Router · Zabbix 7",{exact:true})).toBeChecked();
  await expect(section.getByLabel("Pilih host otomatis Router · Zabbix 2",{exact:true})).toBeChecked();
  await section.getByRole("button",{name:"Atur metrik Router · Zabbix 7",exact:true}).click();
  await expect(section.getByLabel("Cakupan metrik host otomatis")).toHaveValue("selected");
  await expect(section.locator(".auto-metric-editor").getByRole("checkbox",{name:"CPU"})).toBeChecked();
  await section.getByLabel("Sumber jadwal otomatis").selectOption("primary");
  await expect(section.getByLabel("Pilih host otomatis Router · Zabbix 7",{exact:true})).not.toBeChecked();
  await expect(section.getByLabel("Pilih host otomatis Router · Zabbix 2",{exact:true})).toHaveCount(0);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});
