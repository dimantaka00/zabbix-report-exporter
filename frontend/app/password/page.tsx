"use client";
import {useEffect,useState} from "react";
import {useRouter} from "next/navigation";
import {api,setCsrfToken} from "../../lib/api";
import type {AccessUser} from "../../components/AccessShell";

export default function PasswordPage(){
  const router=useRouter();
  const [current,setCurrent]=useState(""),[password,setPassword]=useState(""),[confirm,setConfirm]=useState("");
  const [required,setRequired]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState("");
  useEffect(()=>{api<AccessUser>("/auth/me").then(r=>setRequired(r.data.must_change_password)).catch(e=>setError(e.message));},[]);
  async function save(event:React.FormEvent){
    event.preventDefault();setError("");
    if(password!==confirm){setError("Konfirmasi password belum sama.");return;}
    setBusy(true);
    try{const result=await api<AccessUser>("/auth/password",{method:"POST",body:JSON.stringify({current_password:current,password})});
      setCsrfToken(result.data.csrf_token);setCurrent("");setPassword("");setConfirm("");router.replace(result.data.role==="admin"?"/admin":"/");
    }catch(e){setError(e instanceof Error?e.message:"Password gagal diubah.");}finally{setBusy(false);}
  }
  return <main><div className="page-heading"><div><p className="eyebrow">Keamanan akun</p><h1>Ganti password</h1><p className="muted">{required?"Ganti password sementara sebelum membuka workspace.":"Semua sesi lama akan dicabut setelah password berubah."}</p></div></div>
    <section className="card password-card"><form onSubmit={save}><label><span>Password saat ini</span><input type="password" autoComplete="current-password" required maxLength={128} value={current} onChange={e=>setCurrent(e.target.value)}/></label>
      <label><span>Password baru</span><input type="password" autoComplete="new-password" required minLength={12} maxLength={128} value={password} onChange={e=>setPassword(e.target.value)}/><small>Gunakan minimal 12 karakter. Kalimat panjang mudah diingat.</small></label>
      <label><span>Konfirmasi password baru</span><input type="password" autoComplete="new-password" required minLength={12} maxLength={128} value={confirm} onChange={e=>setConfirm(e.target.value)}/></label>
      {error&&<p className="alert error" role="alert">{error}</p>}<button className="primary" disabled={busy}>{busy?"Menyimpan…":"Simpan password"}</button>
    </form></section></main>;
}
