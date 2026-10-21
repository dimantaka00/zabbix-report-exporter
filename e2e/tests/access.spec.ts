import {test,expect,type Page} from "@playwright/test";
const admin={id:1,username:"admin",display_name:"Administrator",role:"admin",must_change_password:false,csrf_token:"fixture-csrf"};
async function mockAccess(page:Page,initial:typeof admin|null){
  let account=initial;
  const created:unknown[]=[];
  const sessions=[{id:1,username:"admin",display_name:"Administrator",ip:"192.168.1.20",country_name:"Jaringan internal / lokal",user_agent:"Mozilla/5.0 Chrome/123 Windows",last_seen:new Date().toISOString(),expires_at:new Date(Date.now()+3600000).toISOString(),online:true}];
  const users=[{...admin,active:true}];
  await page.route("**/api/v1/**",async route=>{
    const request=route.request(),path=new URL(request.url()).pathname.replace("/api/v1","");
    let data:any={};
    if(path==="/auth/me"){
      if(!account)return route.fulfill({status:401,json:{detail:"Silakan login."}});
      data=account;
    }else if(path==="/auth/login"){
      const payload=request.postDataJSON();
      if(payload.password!=="fixture-password-long")return route.fulfill({status:401,json:{detail:"Username atau password salah."}});
      account={...admin,must_change_password:true};data=account;
    }else if(path==="/auth/password"){
      expect(request.headers()["x-csrf-token"]).toBe("fixture-csrf");
      account={...admin,must_change_password:false};data=account;
    }else if(path==="/auth/logout"){account=null;}
    else if(path==="/auth/visit"){expect(request.headers()["x-csrf-token"]).toBe("fixture-csrf");}
    else if(path==="/admin/summary")data={unique_users:2,unique_ips:3,successful_logins:4,failed_logins:2,online_sessions:sessions.length,total_events:8,geoip_available:true,countries:[{country_name:"Indonesia",country_code:"ID",total:4},{country_name:"Jaringan internal / lokal",country_code:null,total:4}]};
    else if(path==="/admin/events")return route.fulfill({json:{success:true,total:1,data:[{id:1,occurred_at:new Date().toISOString(),username:"admin",event_type:"login_success",ip:"203.0.113.10",country_name:"Indonesia",country_code:"ID",ip_kind:"public",user_agent:"Chrome/123 Windows",method:"POST",path:"/api/v1/auth/login",status_code:200}]}});
    else if(path==="/admin/sessions")data=sessions;
    else if(path==="/admin/sessions/1"&&request.method()==="DELETE")sessions.splice(0);
    else if(path==="/admin/users"&&request.method()==="GET")data=users;
    else if(path==="/admin/users"&&request.method()==="POST"){
      expect(request.headers()["x-csrf-token"]).toBe("fixture-csrf");
      created.push(request.postDataJSON());users.push({...request.postDataJSON(),id:2,active:true,must_change_password:true});data={id:2};
    }else if(path==="/admin/users/2/status"){users[1].active=request.postDataJSON().active;}
    else return route.fulfill({status:404,json:{detail:"Unexpected fixture route"}});
    return route.fulfill({json:{success:true,data}});
  });
  return {created};
}
test("login errors and mandatory password change",async({page})=>{
  await mockAccess(page,null);await page.goto("/login");
  await page.getByLabel("Username",{exact:true}).fill("admin");await page.getByLabel("Password",{exact:true}).fill("wrong-password");
  await page.getByRole("button",{name:"Masuk ke workspace"}).click();await expect(page.locator(".login-card").getByRole("alert")).toContainText("Username atau password salah");
  await page.getByLabel("Password",{exact:true}).fill("fixture-password-long");await page.getByRole("button",{name:"Masuk ke workspace"}).click();
  await expect(page).toHaveURL(/\/password$/);await page.getByLabel("Password saat ini").fill("fixture-password-long");
  await page.getByLabel(/^Password baru/).fill("changed-password-long");await page.getByLabel("Konfirmasi password baru").fill("changed-password-long");
  await page.getByRole("button",{name:"Simpan password"}).click();await expect(page).toHaveURL(/\/admin$/);await expect(page.getByRole("heading",{name:"Monitoring akses"})).toBeVisible();
});
test("anonymous users are redirected to login",async({page})=>{
  await mockAccess(page,null);await page.goto("/admin");await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading",{name:"Monitoring akses"})).toHaveCount(0);
});
test("admin sees account IP country and can revoke a session",async({page})=>{
  await mockAccess(page,admin);await page.goto("/admin");await expect(page.getByRole("heading",{name:"Monitoring akses"})).toBeVisible();
  await expect(page.locator(".access-table")).toContainText("203.0.113.10");await expect(page.locator(".access-table")).toContainText("Indonesia (ID)");
  await page.screenshot({path:test.info().outputPath("access-dashboard.png"),fullPage:true});
  await page.getByRole("tab",{name:"Sesi pengguna"}).click();await expect(page.getByText("192.168.1.20",{exact:true})).toBeVisible();
  page.once("dialog",d=>d.accept());await page.getByRole("button",{name:"Cabut sesi"}).click();await expect(page.getByText("Tidak ada sesi aktif.")).toBeVisible();
  await page.getByRole("button",{name:"Keluar",exact:true}).click();await expect(page).toHaveURL(/\/login$/);
});
test("admin creates and disables a named operator account",async({page})=>{
  const state=await mockAccess(page,admin);await page.goto("/admin");await page.getByRole("tab",{name:"Kelola akun"}).click();
  await page.getByLabel("Username",{exact:true}).fill("operator1");await page.getByLabel("Nama pengguna").fill("Operator Satu");
  await page.getByLabel("Password sementara",{exact:true}).fill("temporary-password-long");await page.getByRole("button",{name:"Buat akun",exact:true}).click();
  const row=page.getByRole("row").filter({hasText:"Operator Satu"});await expect(row).toContainText("Wajib ganti password");
  await row.getByRole("button",{name:"Nonaktifkan"}).click();await expect(row).toContainText("Nonaktif");expect(state.created).toHaveLength(1);
});
