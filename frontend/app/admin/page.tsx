"use client";
import {useEffect,useState,useCallback} from "react";
import {api,dateTime} from "../../lib/api";
import Icon from "../../components/Icon";

type Summary={unique_users:number;unique_ips:number;successful_logins:number;failed_logins:number;online_sessions:number;total_events:number;geoip_available:boolean;countries:{country_name:string;country_code:string|null;total:number}[]};
type Event={id:number;occurred_at:string;username:string|null;event_type:string;ip:string;country_name:string;country_code:string|null;ip_kind:string;user_agent:string;method:string;path:string;status_code:number};
type Session={id:number;username:string;display_name:string;ip:string;country_name:string;user_agent:string;last_seen:string;expires_at:string;online:boolean};
type User={id:number;username:string;display_name:string;role:string;active:boolean;must_change_password:boolean};
const labels:Record<string,string>={login_success:"Login berhasil",login_failed:"Login gagal",logout:"Logout",page_view:"Halaman dibuka",access_denied:"Akses ditolak",csrf_denied:"Permintaan ditolak",request:"Aktivitas API",account_created:"Akun dibuat",account_status_changed:"Status akun diubah",password_changed:"Password diubah",password_reset:"Password direset",session_revoked:"Sesi dicabut"};
function device(agent:string){
  const browser=/Edg\//.test(agent)?"Edge":/Firefox\//.test(agent)?"Firefox":/Chrome\//.test(agent)?"Chrome":/Safari\//.test(agent)?"Safari":"Browser / klien lain";
  const os=/Android/.test(agent)?"Android":/iPhone|iPad/.test(agent)?"iOS":/Windows/.test(agent)?"Windows":/Macintosh/.test(agent)?"macOS":/Linux/.test(agent)?"Linux":"";
  return agent?`${browser}${os?` · ${os}`:""}`:"Tidak tersedia";
}

export default function AdminPage(){
  const [summary,setSummary]=useState<Summary|null>(null),[events,setEvents]=useState<Event[]>([]),[sessions,setSessions]=useState<Session[]>([]),[users,setUsers]=useState<User[]>([]);
  const [tab,setTab]=useState<"events"|"sessions"|"users">("events"),[search,setSearch]=useState(""),[query,setQuery]=useState("");
  const [kind,setKind]=useState(""),[days,setDays]=useState("7"),[page,setPage]=useState(0),[total,setTotal]=useState(0);
  const [loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState(""),[message,setMessage]=useState(""),[updated,setUpdated]=useState<Date|null>(null);
  const [username,setUsername]=useState(""),[name,setName]=useState(""),[password,setPassword]=useState(""),[role,setRole]=useState("operator");
  const [resetId,setResetId]=useState(""),[resetPassword,setResetPassword]=useState("");
  const refresh=useCallback(async(signal?:AbortSignal)=>{
    try{
      const params=new URLSearchParams({q:query,event_type:kind,days,limit:"25",offset:String(page*25)});
      const [s,e,a,u]=await Promise.all([api<Summary>("/admin/summary",{signal}),api<Event[]>(`/admin/events?${params}`,{signal}),api<Session[]>("/admin/sessions",{signal}),api<User[]>("/admin/users",{signal})]);
      if(signal?.aborted)return;
      setSummary(s.data);setEvents(e.data);setTotal(e.total||0);setSessions(a.data);setUsers(u.data);setUpdated(new Date());setError("");
    }catch(e){if(!signal?.aborted)setError(e instanceof Error?e.message:"Data akses belum tersedia.");}
    finally{if(!signal?.aborted)setLoading(false);}
  },[query,kind,days,page]);
  useEffect(()=>{
    const controller=new AbortController();let running=false;
    async function poll(){if(running)return;running=true;try{await refresh(controller.signal);}finally{running=false;}}
    poll();const timer=setInterval(poll,15000);
    return()=>{controller.abort();clearInterval(timer);};
  },[refresh]);
  async function action(path:string,method:string,body?:object){
    setBusy(true);setMessage("");setError("");
    try{await api(path,{method,...(body?{body:JSON.stringify(body)}:{})});setMessage("Perubahan tersimpan.");await refresh();return true;}
    catch(e){setError(e instanceof Error?e.message:"Perubahan gagal.");return false;}finally{setBusy(false);}
  }
  async function create(event:React.FormEvent){event.preventDefault();if(await action("/admin/users","POST",{username,display_name:name,password,role})){setUsername("");setName("");setPassword("");}}
  async function reset(event:React.FormEvent){event.preventDefault();if(await action(`/admin/users/${resetId}/password`,"POST",{password:resetPassword})){setResetId("");setResetPassword("");}}
  return <main><div className="page-heading dashboard-heading"><div><p className="eyebrow"><Icon name="shield"/>ADMINISTRATOR</p><h1>Monitoring akses</h1><p className="muted">Lihat siapa yang mengakses workspace dan dari jaringan mana.</p></div>
    <div className="heading-tools"><span className="sync-label">{updated?`Diperbarui ${updated.toLocaleTimeString("id-ID")}`:"Memuat aktivitas…"}</span><button disabled={loading} onClick={()=>refresh()}><Icon name="refresh"/>Refresh</button></div></div>
    {error&&<p className="alert error" role="alert">{error}</p>}{message&&<p className="alert success" role="status">{message}</p>}
    <div className="stat-grid access-stats">{[
      ["Akun aktif hari ini",summary?.unique_users,"Akun dengan aktivitas tercatat"],
      ["IP unik hari ini",summary?.unique_ips,"Alamat yang terlihat oleh server"],
      ["Sesi online",summary?.online_sessions,"Aktif dalam 5 menit terakhir"],
      ["Login gagal hari ini",summary?.failed_logins,"Percobaan username/password salah"],
    ].map(([title,value,note])=><div className="kpi-card" key={String(title)}><div className="kpi-header"><span>{title}</span><Icon name="shield"/></div><strong>{value??"—"}</strong><small>{note}</small></div>)}</div>
    <div className="access-overview"><section className="card"><div className="card-heading"><h2>Asal akses · 24 jam terakhir</h2><span className="badge success">{summary?.successful_logins??0} login berhasil hari ini</span></div>
      <div className="country-list">{summary?.countries.map(country=><div key={`${country.country_code}-${country.country_name}`}><span>{country.country_code&&<b>{country.country_code}</b>}{country.country_name}</span><strong>{country.total.toLocaleString("id-ID")} aktivitas</strong></div>)}{!summary?.countries.length&&<p className="empty">Belum ada aktivitas tercatat.</p>}</div>
    </section><section className="card access-location-note"><Icon name="network"/><h2>Memahami lokasi akses</h2><p>IP privat atau localhost ditandai sebagai jaringan internal. Negara IP publik adalah perkiraan lokasi jaringan, termasuk VPN atau proxy, dan bukan identitas atau lokasi pasti pengguna.</p>
      <p className="muted">{summary?.geoip_available?"Basis negara IP tersedia secara lokal.":"Basis negara IP belum tersedia; IP publik ditampilkan sebagai tidak diketahui."} Aktivitas disimpan selama 90 hari.</p>
      <a href="https://db-ip.com" target="_blank" rel="noreferrer">IP Geolocation by DB-IP</a>
    </section></div>
    <section className="card"><div className="access-tabs" role="tablist" aria-label="Monitoring akses">{[["events","Aktivitas akses"],["sessions","Sesi pengguna"],["users","Kelola akun"]].map(([value,label])=><button key={value} role="tab" aria-selected={tab===value} className={tab===value?"primary":""} onClick={()=>setTab(value as typeof tab)}>{label}</button>)}</div>
      {tab==="events"&&<><form className="access-filters" onSubmit={e=>{e.preventDefault();setQuery(search);setPage(0);}}>
        <label><span>Cari akun, IP, atau negara</span><input maxLength={100} placeholder="Contoh: admin atau 192.168…" value={search} onChange={e=>setSearch(e.target.value)}/></label>
        <label><span>Jenis aktivitas</span><select value={kind} onChange={e=>{setKind(e.target.value);setPage(0);}}><option value="">Semua aktivitas</option>{Object.entries(labels).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
        <label><span>Periode</span><select value={days} onChange={e=>{setDays(e.target.value);setPage(0);}}>{[1,7,30,90].map(day=><option key={day} value={day}>{day} hari terakhir</option>)}</select></label><button type="submit">Cari</button>
      </form><div className="table-wrap"><table className="access-table"><thead><tr><th>Waktu</th><th>Akun</th><th>IP / negara</th><th>Aktivitas</th><th>Perangkat</th><th>Hasil</th></tr></thead><tbody>
        {events.map(event=><tr key={event.id}><td className="nowrap">{dateTime(event.occurred_at)}</td><td><strong>{event.username||"Belum login"}</strong>{event.event_type==="login_failed"&&<small>Username yang dicoba</small>}</td>
          <td><code>{event.ip}</code><small>{event.country_name||"Tidak diketahui"}{event.country_code?` (${event.country_code})`:""}</small></td><td>{labels[event.event_type]||event.event_type}<small className="access-path">{event.method} {event.path}</small></td>
          <td title={event.user_agent}>{device(event.user_agent)}</td><td><span className={`badge ${event.status_code>=400?"failed":"success"}`}>HTTP {event.status_code}</span></td></tr>)}
        {!events.length&&<tr><td colSpan={6} className="empty">{loading?"Memuat aktivitas…":"Tidak ada aktivitas untuk filter ini."}</td></tr>}
      </tbody></table></div><div className="pagination"><small>{total.toLocaleString("id-ID")} aktivitas · halaman {page+1} dari {Math.max(1,Math.ceil(total/25))}</small><div className="actions"><button disabled={page===0} onClick={()=>setPage(page-1)}>Sebelumnya</button><button disabled={(page+1)*25>=total} onClick={()=>setPage(page+1)}>Berikutnya</button></div></div></>}
      {tab==="sessions"&&<><p className="muted">Sesi dapat dicabut untuk mengeluarkan pengguna dari workspace. Sesi kedaluwarsa setelah 8 jam.</p><div className="table-wrap"><table><thead><tr><th>Akun</th><th>IP / negara</th><th>Perangkat</th><th>Aktivitas terakhir</th><th>Status / aksi</th></tr></thead><tbody>
        {sessions.map(session=><tr key={session.id}><td><strong>{session.display_name}</strong><small>{session.username}</small></td><td><code>{session.ip}</code><small>{session.country_name}</small></td><td title={session.user_agent}>{device(session.user_agent)}</td><td>{dateTime(session.last_seen)}<small>Berlaku hingga {dateTime(session.expires_at)}</small></td>
          <td><span className={`badge ${session.online?"success":"disabled"}`}>{session.online?"Online":"Tidak aktif"}</span><button className="small-button danger" disabled={busy} onClick={()=>{if(window.confirm(`Cabut sesi ${session.username}?`))action(`/admin/sessions/${session.id}`,"DELETE");}}>Cabut sesi</button></td></tr>)}
        {!sessions.length&&<tr><td colSpan={5} className="empty">Tidak ada sesi aktif.</td></tr>}
      </tbody></table></div></>}
      {tab==="users"&&<><div className="access-user-forms"><form onSubmit={create}><h2>Buat akun</h2><div className="form-grid">
        <label><span>Username</span><input required pattern="[a-z0-9][a-z0-9._-]{2,63}" maxLength={64} autoComplete="off" value={username} onChange={e=>setUsername(e.target.value)} placeholder="huruf kecil, angka, titik, _ atau -"/></label>
        <label><span>Nama pengguna</span><input required maxLength={100} value={name} onChange={e=>setName(e.target.value)}/></label>
        <label><span>Password sementara</span><input type="password" required minLength={12} maxLength={128} autoComplete="new-password" value={password} onChange={e=>setPassword(e.target.value)}/></label>
        <label><span>Peran</span><select value={role} onChange={e=>setRole(e.target.value)}><option value="operator">Operator</option><option value="admin">Admin</option></select></label></div><small>Pengguna wajib mengganti password saat pertama masuk. Operator dapat mengakses monitoring, laporan, dan jadwal.</small><button className="primary" disabled={busy}>Buat akun</button></form>
        <form onSubmit={reset}><h2>Reset password</h2><label><span>Akun</span><select required value={resetId} onChange={e=>setResetId(e.target.value)}><option value="">Pilih akun</option>{users.map(user=><option key={user.id} value={user.id}>{user.display_name} ({user.username})</option>)}</select></label>
          <label><span>Password sementara baru</span><input type="password" required minLength={12} maxLength={128} autoComplete="new-password" value={resetPassword} onChange={e=>setResetPassword(e.target.value)}/></label><small>Semua sesi akun ini dicabut. Pengguna harus mengganti password sementara saat masuk kembali.</small><button disabled={busy}>Reset password</button></form>
      </div><div className="table-wrap"><table><thead><tr><th>Akun</th><th>Peran</th><th>Status</th><th>Aksi</th></tr></thead><tbody>{users.map(user=><tr key={user.id}><td><strong>{user.display_name}</strong><small>{user.username}</small></td><td>{user.role}</td><td><span className={`badge ${user.active?"success":"disabled"}`}>{user.active?"Aktif":"Nonaktif"}</span>{user.must_change_password&&<small>Wajib ganti password</small>}</td><td><button className="small-button" disabled={busy} onClick={()=>action(`/admin/users/${user.id}/status`,"PATCH",{active:!user.active})}>{user.active?"Nonaktifkan":"Aktifkan"}</button></td></tr>)}</tbody></table></div></>}
    </section></main>;
}
