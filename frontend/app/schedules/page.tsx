"use client";
import { useEffect, useState } from "react";
import MetricPicker from "../../components/MetricPicker";
import { api, numericItems, dateTime } from "../../lib/api";
import type { Host, Item, Schedule } from "../../lib/api";

export default function SchedulesPage() {
  const [hosts,setHosts]=useState<Host[]>([]), [items,setItems]=useState<Item[]>([]);
  const [schedules,setSchedules]=useState<Schedule[]>([]);
  const [editing,setEditing]=useState<number | null>(null), [hostId,setHostId]=useState("");
  const [selected,setSelected]=useState<string[]>([]), [name,setName]=useState("Daily Infrastructure Report");
  const [hour,setHour]=useState("7"), [minute,setMinute]=useState("0"), [timezone,setTimezone]=useState("Asia/Jakarta");
  const [enabled,setEnabled]=useState(true), [loadingItems,setLoadingItems]=useState(false);
  const [loading,setLoading]=useState(true), [saving,setSaving]=useState(false), [busy,setBusy]=useState<number | null>(null);
  const [error,setError]=useState(""), [message,setMessage]=useState("");

  async function refresh() {
    const result=await api<Schedule[]>("/schedules"); setSchedules(result.data);
  }
  useEffect(() => {
    Promise.all([api<Host[]>("/zabbix/hosts"), api<Schedule[]>("/schedules")])
      .then(([h,s]) => {setHosts(h.data);setSchedules(s.data);})
      .catch(e => setError(e.message)).finally(() => setLoading(false));
    const timer=setInterval(() => {refresh().catch(e => setError(e.message));},30000);
    return () => clearInterval(timer);
  },[]);
  useEffect(() => {
    setItems([]);
    if (!hostId) {setLoadingItems(false);return;}
    const controller=new AbortController(); setLoadingItems(true);
    api<Item[]>(`/zabbix/hosts/${hostId}/items`,{signal:controller.signal})
      .then(r => setItems(numericItems(r.data)))
      .catch(e => {if(e.name !== "AbortError")setError(e.message);})
      .finally(() => {if(!controller.signal.aborted)setLoadingItems(false);});
    return () => controller.abort();
  },[hostId]);
  function reset() {
    setEditing(null);setHostId("");setSelected([]);setName("Daily Infrastructure Report");
    setHour("7");setMinute("0");setTimezone("Asia/Jakarta");setEnabled(true);
  }
  function edit(s:Schedule) {
    setEditing(s.id);setHostId(s.host_id);setSelected(s.item_ids);setName(s.name);
    setHour(String(s.hour));setMinute(String(s.minute));setTimezone(s.timezone);setEnabled(s.enabled);
    setError("");setMessage("");window.scrollTo({top:0,behavior:"smooth"});
  }
  async function save(event:React.FormEvent) {
    event.preventDefault();setError("");setMessage("");setSaving(true);
    try {
      const host=hosts.find(h => h.hostid === hostId);
      if(!host || !selected.length)throw new Error("Pilih host dan minimal satu metrik.");
      const h=Number(hour),m=Number(minute);
      if(!Number.isInteger(h)||!Number.isInteger(m)||h<0||h>23||m<0||m>59)throw new Error("Jam dan menit tidak valid.");
      await api<Schedule>(editing === null ? "/schedules" : `/schedules/${editing}`,{
        method:editing === null ? "POST" : "PUT",body:JSON.stringify({
          name,host_id:hostId,host_name:host.name || host.host,item_ids:selected,
          hour:h,minute:m,timezone,enabled,
        }),
      });
      setMessage(editing === null ? "Jadwal berhasil dibuat." : "Perubahan jadwal tersimpan.");
      reset();await refresh();
    }catch(e){setError(e instanceof Error ? e.message : "Jadwal gagal disimpan.");}
    finally{setSaving(false);}
  }
  async function action(s:Schedule, type:"toggle"|"delete"|"run") {
    if(type==="delete"&&!window.confirm(`Hapus jadwal “${s.name}”? PDF dan riwayat tetap tersimpan.`))return;
    if(type==="run"&&!window.confirm("Buat laporan untuk hari kalender sebelumnya sekarang? Eksekusi ini juga menandai jadwal sudah dijalankan hari ini."))return;
    setBusy(s.id);setError("");setMessage("");
    try{
      if(type==="toggle"){
        await api(`/schedules/${s.id}/status`,{method:"PATCH",body:JSON.stringify({enabled:!s.enabled})});
        setMessage(s.enabled ? "Jadwal dinonaktifkan." : "Jadwal diaktifkan.");
      } else if(type==="delete"){
        await api(`/schedules/${s.id}`,{method:"DELETE"});setMessage("Jadwal dihapus.");
        if(editing===s.id)reset();
      } else {
        const result=await api<{status:string}>(`/schedules/${s.id}/run`,{method:"POST"});
        setMessage(result.data.status==="PARTIAL" ? "Laporan dibuat dengan sebagian data. Periksa riwayat." : "Laporan berhasil dibuat. Buka halaman Laporan untuk mengunduh.");
      }
      await refresh();
    }catch(e){setError(e instanceof Error ? e.message : "Aksi gagal.");}
    finally{setBusy(null);}
  }

  return <main><div className="page-heading"><div><p className="eyebrow">Report automation</p><h1>Jadwal laporan</h1><p className="muted">Laporan harian menggunakan data hari kalender sebelumnya.</p></div><button onClick={() => refresh().catch(e => setError(e.message))}>Refresh jadwal</button></div>
    {error&&<div className="alert error" role="alert">{error}</div>}
    {message&&<div className="alert success" role="status">{message}</div>}
    <section className="card"><h2>{editing===null ? "Buat jadwal harian" : `Edit jadwal #${editing}`}</h2>
      <form onSubmit={save}><div className="form-grid">
        <label><span>Nama laporan</span><input required maxLength={200} value={name} onChange={e => setName(e.target.value)} /></label>
        <label><span>Host</span><select required value={hostId} disabled={loading} onChange={e => {setHostId(e.target.value);setSelected([]);}}>
          <option value="">Pilih host</option>{hosts.map(h => <option key={h.hostid} value={h.hostid}>{h.name || h.host}</option>)}</select></label>
        <label><span>Jam</span><input required type="number" min="0" max="23" step="1" value={hour} onChange={e => setHour(e.target.value)} /></label>
        <label><span>Menit</span><input required type="number" min="0" max="59" step="1" value={minute} onChange={e => setMinute(e.target.value)} /></label>
        <label><span>Timezone</span><select value={timezone} onChange={e => setTimezone(e.target.value)}>
          {Array.from(new Set(["Asia/Jakarta","Asia/Makassar","Asia/Jayapura",timezone])).map(t => <option key={t}>{t}</option>)}</select></label>
        <label className="metric"><input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} /><span>Aktifkan jadwal</span></label>
      </div><MetricPicker items={items} selected={selected} onChange={setSelected} loading={loadingItems} />
        <div className="actions"><button className="primary" disabled={saving||loadingItems}>{saving ? "Menyimpan…" : editing===null ? "Simpan jadwal" : "Simpan perubahan"}</button>
          {editing!==null&&<button type="button" onClick={reset}>Batal edit</button>}</div>
      </form></section>
    <section className="card"><div className="card-heading"><h2>Jadwal tersimpan</h2><small>{schedules.length} jadwal</small></div>
      {loading ? <p role="status">Memuat jadwal…</p> : !schedules.length ? <p className="empty">Belum ada jadwal. Buat jadwal pertama di atas.</p> :
      <div className="table-wrap"><table><thead><tr><th>Laporan / host</th><th>Waktu</th><th>Status</th><th>Eksekusi terakhir</th><th>Aksi</th></tr></thead><tbody>
        {schedules.map(s => <tr key={s.id}><td><strong>{s.name}</strong><small>{s.host_name} · {s.item_ids.length} metrik</small></td>
          <td className="nowrap">{String(s.hour).padStart(2,"0")}:{String(s.minute).padStart(2,"0")}<small>{s.timezone}</small></td>
          <td><span className={`badge ${s.enabled ? "success" : "disabled"}`}>{s.enabled ? "Aktif" : "Nonaktif"}</span>
            {s.last_error&&<small className="warning-text">{s.last_error}</small>}{s.next_retry_at&&<small>Retry {dateTime(s.next_retry_at)}</small>}</td>
          <td>{s.last_run_date || "Belum dijalankan"}</td><td><div className="schedule-actions">
            <button className="small-button" disabled={busy!==null} onClick={() => edit(s)}>Edit</button>
            <button className="small-button" disabled={busy!==null} onClick={() => action(s,"toggle")}>{s.enabled ? "Nonaktifkan" : "Aktifkan"}</button>
            <button className="small-button" disabled={busy!==null} onClick={() => action(s,"run")}>{busy===s.id ? "Memproses…" : "Jalankan sekarang"}</button>
            <button className="small-button danger" disabled={busy!==null} onClick={() => action(s,"delete")}>Hapus</button>
          </div></td></tr>)}
      </tbody></table></div>}
    </section></main>;
}
