"use client";
import {branding} from "../lib/branding";
import {useEffect,useState} from "react";
import {usePathname,useRouter} from "next/navigation";
import Navigation from "./Navigation";
import {api,setCsrfToken} from "../lib/api";

export type AccessUser={id:number;username:string;display_name:string;role:"admin"|"operator";must_change_password:boolean;csrf_token:string};

export default function AccessShell({children}:{children:React.ReactNode}){
  const path=usePathname(),router=useRouter();
  const [user,setUser]=useState<AccessUser|null>(null),[ready,setReady]=useState(false),[error,setError]=useState("");
  const [disabled,setDisabled]=useState(false);
  useEffect(()=>{
    let live=true;setReady(false);setError("");
    async function load(){
      try{
        const response=await fetch("/api/v1/auth/me",{cache:"no-store"});
        if(!live)return;
        if(response.status===401){setUser(null);setCsrfToken("");if(path!=="/login")router.replace("/login");setReady(true);return;}
        if(!response.ok)throw new Error("Status sesi tidak dapat diperiksa. Muat ulang halaman.");
        const result=await response.json(),account=result.data as AccessUser & {authentication_enabled?:boolean};
        if(!live)return;
        if(account.authentication_enabled===false){
          setDisabled(true);setUser(null);setCsrfToken("");
          if(["/login","/admin","/password"].includes(path)){router.replace("/");return;}
          setReady(true);return;
        }
        setDisabled(false);
        setUser(account);setCsrfToken(account.csrf_token);
        if(account.must_change_password&&path!=="/password"){router.replace("/password");return;}
        if(path==="/login"){router.replace("/");return;}
        if(path==="/admin"&&account.role!=="admin"){router.replace("/");return;}
        setReady(true);
        if(["/","/reports","/schedules","/admin","/password"].includes(path)){
          await api("/auth/visit",{method:"POST",body:JSON.stringify({path})});
        }
      }catch(e){if(live){setError(e instanceof Error?e.message:"Koneksi gagal.");setReady(true);}}
    }
    load();
    const heartbeat=setInterval(()=>{if(path!=="/login")fetch("/api/v1/auth/me",{cache:"no-store"}).then(r=>{if(r.status===401)router.replace("/login");}).catch(()=>{});},60000);
    return()=>{live=false;clearInterval(heartbeat);};
  },[path,router]);
  async function logout(){
    try{await api("/auth/logout",{method:"POST"});setUser(null);setCsrfToken("");router.replace("/login");}
    catch(e){setError(e instanceof Error?e.message:"Logout gagal.");}
  }
  if(disabled&&["/login","/admin","/password"].includes(path))return <main className="access-loading" role="status">Membuka monitoring…</main>;
  if(path==="/login")return <>{children}</>;
  if(!user&&!disabled)return <main className="access-loading" role="status">{error||"Memeriksa sesi…"}</main>;
  return <><Navigation user={user} onLogout={logout}/><div className="workspace-content">{branding.demo && <p className="alert warning">DEMO — Data sintetis untuk contoh implementasi. Tidak terhubung ke server client.</p>}
    {error&&<p className="alert error" role="alert">{error}</p>}{ready?children:<main className="access-loading" role="status">Memeriksa sesi…</main>}
    <footer className="site-footer"><span>Zabbix Report Exporter</span><span>Monitoring & laporan operasional IT</span>
      <span className="developer-credit">Developed by <strong>Daniel Christoper I.P</strong></span></footer>
  </div></>;
}
