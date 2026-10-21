"use client";
import {branding} from "../../lib/branding";
import {useState} from "react";
import {useRouter} from "next/navigation";
import ThemeToggle from "../../components/ThemeToggle";
import Icon from "../../components/Icon";
import {responseError,setCsrfToken} from "../../lib/api";

export default function LoginPage(){
  const router=useRouter();
  const [username,setUsername]=useState(""),[password,setPassword]=useState(""),[show,setShow]=useState(false);
  const [busy,setBusy]=useState(false),[error,setError]=useState("");
  async function login(event:React.FormEvent){
    event.preventDefault();setBusy(true);setError("");
    try{
      const response=await fetch("/api/v1/auth/login",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({username,password})});
      if(!response.ok)throw await responseError(response);
      const result=await response.json();setCsrfToken(result.data.csrf_token);setPassword("");
      router.replace(result.data.must_change_password?"/password":result.data.role==="admin"?"/admin":"/");
    }catch(e){setError(e instanceof Error?e.message:"Login gagal.");}
    finally{setBusy(false);}
  }
  return <main className="login-page"><div className="login-theme"><ThemeToggle/></div>
    <section className="login-intro"><div className="login-brand"><img src={branding.logo} alt={branding.product} width="56" height="60"/>
      <div><strong>{branding.product}</strong><small>{branding.organization}</small></div></div>
      <p className="eyebrow">OPERATIONS TEAM</p><h1>Satu workspace.<br/>Akses yang terpantau.</h1>
      <p>Pantau infrastruktur, siapkan laporan, dan kelola aktivitas tim dalam satu tempat.</p>
      <div className="login-features"><span><Icon name="monitor"/>Monitoring jaringan</span><span><Icon name="file"/>Laporan operasional</span><span><Icon name="shield"/>Kontrol akses admin</span></div>
    </section>
    <section className="card login-card"><div className="login-lock"><Icon name="shield"/></div><p className="eyebrow">AKSES WORKSPACE</p>
      <h2>Selamat datang kembali</h2><p className="muted">Masuk menggunakan akun yang diberikan administrator.</p>
      <form onSubmit={login}><label><span>Username</span><input name="username" autoComplete="username" autoCapitalize="none" spellCheck={false} required maxLength={64} value={username} onChange={e=>setUsername(e.target.value)}/></label>
        <label><span>Password</span><input name="password" type={show?"text":"password"} autoComplete="current-password" required maxLength={128} value={password} onChange={e=>setPassword(e.target.value)}/></label>
        <label className="login-show"><input type="checkbox" checked={show} onChange={e=>setShow(e.target.checked)}/><span>Tampilkan password</span></label>
        {error&&<p className="alert error" role="alert">{error}</p>}
        <button className="primary" disabled={busy}>{busy?"Memeriksa akun…":"Masuk ke workspace"}<Icon name="arrow"/></button>
      </form><p className="login-notice">Aktivitas akses dicatat untuk keamanan: akun, waktu, alamat IP, perangkat, dan perkiraan negara IP publik.</p>
      <small>Lupa password? Hubungi administrator.</small>
    </section><p className="login-credit">Developed by Daniel Christoper I.P</p>
  </main>;
}
