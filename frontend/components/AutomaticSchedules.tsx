"use client";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { ZabbixServer } from "../lib/api";
import AutomaticHostSelection from "./AutomaticHostSelection";
import type {AutoHostSelection} from "./AutomaticHostSelection";
import AutomaticGroupPicker from "./AutomaticGroupPicker";
import type {AutoHostGroup,HostCategory} from "./AutomaticGroupPicker";

type Policy = {id:number;run_id?:number|null;name:string;zabbix_server:string;host_status:string;hour:number;minute:number;timezone:string;enabled:boolean;
  data_start_time?:string;data_end_time?:string;date_start?:string|null;date_end?:string|null;date_status?:string;host_categories?:HostCategory[];host_groups?:AutoHostGroup[];
  run_status:string;report_date:string|null;total_hosts:number;done_hosts:number;files_completed:number;failed_hosts:number;skipped_hosts:number;partial_hosts:number;pending_periods:number;last_error:string|null;
  selection_mode:"all"|"selected";host_selections:AutoHostSelection[];package_zip:boolean;archive_status:string|null;archive_download_url:string|null;archive_size:number|null;original_size:number|null;archive_error:string|null};
type Task = {id:number;host_name:string;zabbix_server:string;status:string;item_offset:number;total_metrics:number;files_completed:number;last_error:string|null};
type Preview = {hosts:number;servers:{id:string;hosts:number}[];max_metrics_per_pdf:number};
const states:Record<string,string>={WAITING:"Menunggu jadwal",QUEUED:"Dalam antrean",RUNNING:"Memproses",PAUSED:"Dijeda",COMPLETED:"Selesai",SUCCESS:"Selesai",PARTIAL:"Sebagian data",FAILED:"Gagal",SKIPPED:"Tanpa metrik aktif",PENDING:"Dalam antrean"};

export default function AutomaticSchedules({servers}:{servers:ZabbixServer[]}) {
  const [rows,setRows]=useState<Policy[]>([]),[editing,setEditing]=useState<number|null>(null);
  const [name,setName]=useState("Semua host · laporan harian"),[source,setSource]=useState("all"),[hostStatus,setHostStatus]=useState("all");
  const [clock,setClock]=useState("07:00"),[timezone,setTimezone]=useState("Asia/Jakarta"),[enabled,setEnabled]=useState(false);
  const [dataStart,setDataStart]=useState("00:00"),[dataEnd,setDataEnd]=useState("23:59"),[dateStart,setDateStart]=useState(""),[dateEnd,setDateEnd]=useState("");
  const [categories,setCategories]=useState<HostCategory[]>([]),[groups,setGroups]=useState<AutoHostGroup[]>([]);
  const groupKey=Array.from(new Set(groups.map(g=>`${g.zabbix_server}:${g.group_id}`))).sort().join(","),categoryKey=categories.join(",");
  const [selectionMode,setSelectionMode]=useState<"all"|"selected">("all"),[selections,setSelections]=useState<AutoHostSelection[]>([]),[packageZip,setPackageZip]=useState(true);
  const [preview,setPreview]=useState<Preview|null>(null),[previewError,setPreviewError]=useState("");
  const [error,setError]=useState(""),[message,setMessage]=useState(""),[busy,setBusy]=useState(false);
  const [detail,setDetail]=useState<number|null>(null),[offset,setOffset]=useState(0),[tasks,setTasks]=useState<Task[]>([]),[total,setTotal]=useState(0);
  const [detailLoading,setDetailLoading]=useState(false);
  async function refresh(){setRows((await api<Policy[]>("/auto-schedules")).data);}
  useEffect(()=>{
    let active=true;
    const load=async()=>{try{const r=await api<Policy[]>("/auto-schedules");if(active)setRows(r.data);}catch(e){if(active)setError((e as Error).message);}};
    load();const timer=setInterval(load,15000);return()=>{active=false;clearInterval(timer);};
  },[]);
  useEffect(()=>{
    const controller=new AbortController();setPreview(null);setPreviewError("");
    if(categoryKey&&!groupKey){setPreviewError("Pilih group untuk kategori terpilih agar cakupan host dapat diperiksa.");return()=>controller.abort();}
    const params=new URLSearchParams({zabbix_server:source,host_status:hostStatus});
    if(groupKey)groupKey.split(",").forEach(ref=>params.append("group_refs",ref));
    api<Preview>(`/auto-schedules/preview?${params}`,{signal:controller.signal})
      .then(r=>setPreview(r.data)).catch(e=>{if(e.name!=="AbortError")setPreviewError(e.message);});
    return()=>controller.abort();
  },[source,hostStatus,groupKey,categoryKey]);
  useEffect(()=>{
    if(detail===null)return;
    const controller=new AbortController();
    const load=async()=>{setDetailLoading(true);try{
      const r=await api<Task[]>(`/auto-schedules/${detail}/tasks?offset=${offset}&limit=25`,{signal:controller.signal});
      setTasks(r.data);setTotal(r.total||0);
    }catch(e){if((e as Error).name!=="AbortError")setError((e as Error).message);}finally{if(!controller.signal.aborted)setDetailLoading(false);}};
    load();const timer=setInterval(load,15000);return()=>{controller.abort();clearInterval(timer);};
  },[detail,offset]);
  function reset(){setEditing(null);setName("Semua host · laporan harian");setSource("all");setHostStatus("all");setClock("07:00");setTimezone("Asia/Jakarta");setEnabled(false);setSelectionMode("all");setSelections([]);setPackageZip(true);setDataStart("00:00");setDataEnd("23:59");setDateStart("");setDateEnd("");setCategories([]);setGroups([]);}
  async function save(event:React.FormEvent){event.preventDefault();setBusy(true);setError("");setMessage("");try{
    if(!/^([01]\d|2[0-3]):[0-5]\d$/.test(clock))throw new Error("Pilih waktu dari 00:00 sampai 23:59.");
    if(![dataStart,dataEnd].every(t=>/^([01]\d|2[0-3]):[0-5]\d$/.test(t))||dataStart>dataEnd)throw new Error("Jam akhir laporan harus sama atau setelah jam mulai, dalam satu hari.");
    if(dateStart&&dateEnd&&dateStart>dateEnd)throw new Error("Tanggal akhir jadwal harus sama atau setelah tanggal mulai.");
    if(categories.some(c=>!groups.some(g=>g.category===c)))throw new Error("Pilih minimal satu group Zabbix untuk setiap kategori terpilih.");
    if(groups.length>200)throw new Error("Maksimal 200 pilihan group per jadwal.");
    if(selectionMode==="selected"&&(!selections.length||selections.some(h=>h.item_ids!==null&&!h.item_ids.length)))throw new Error("Pilih minimal satu host dan metrik untuk setiap host yang memakai pilihan metrik tertentu.");
    const [hour,minute]=clock.split(":").map(Number);
    await api(editing===null?"/auto-schedules":`/auto-schedules/${editing}`,{method:editing===null?"POST":"PUT",body:JSON.stringify({name,zabbix_server:source,host_status:hostStatus,hour,minute,timezone,enabled,selection_mode:selectionMode,host_selections:selectionMode==="selected"?selections:[],package_zip:packageZip,data_start_time:dataStart,data_end_time:dataEnd,date_start:dateStart||null,date_end:dateEnd||null,host_categories:categories,host_groups:groups})});
    setMessage(enabled?"Jadwal otomatis aktif. Laporan mulai masuk antrean pada waktu terpilih.":"Jadwal otomatis tersimpan dalam keadaan nonaktif.");reset();await refresh();
  }catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  async function action(row:Policy,remove=false){
    if(remove&&!window.confirm(`Hapus jadwal otomatis ${row.name}? PDF dan riwayat tetap tersimpan.`))return;
    setBusy(true);setError("");try{
      await api(`/auto-schedules/${row.id}${remove?"":"/status"}`,{method:remove?"DELETE":"PATCH",...(remove?{}:{body:JSON.stringify({enabled:!row.enabled})})});
      if(remove){if(editing===row.id)reset();if(detail===row.id)setDetail(null);}
      setMessage(remove?"Jadwal otomatis dihapus.":row.enabled?"Antrean dijeda setelah bagian yang sedang diproses selesai.":"Jadwal otomatis diaktifkan.");await refresh();
    }catch(e){setError((e as Error).message);}finally{setBusy(false);}
  }
  function edit(row:Policy){setEditing(row.id);setName(row.name);setSource(row.zabbix_server);setHostStatus(row.host_status);setClock(`${String(row.hour).padStart(2,"0")}:${String(row.minute).padStart(2,"0")}`);setTimezone(row.timezone);setEnabled(row.enabled);setSelectionMode(row.selection_mode||"all");setSelections(row.host_selections||[]);setPackageZip(!!row.package_zip);setDataStart(row.data_start_time||"00:00");setDataEnd(row.data_end_time||"23:59");setDateStart(row.date_start||"");setDateEnd(row.date_end||"");setCategories(row.host_categories||[]);setGroups(row.host_groups||[]);setError("");setMessage("");document.getElementById("automatic-schedules")?.scrollIntoView({behavior:"smooth"});}
  return <section className="card" id="automatic-schedules" aria-label="Jadwal otomatis semua host">
    <h2>Jadwal otomatis host & metrik</h2>
    <p className="muted">Pilih host dan metrik tertentu, atau gunakan semua host dan semua metrik numerik aktif. Dalam mode semua host, host dan metrik baru ikut pada eksekusi berikutnya.</p>
    <p className="muted">Jam eksekusi menentukan kapan antrean dibuat setiap hari. Jam mulai–akhir laporan menentukan rentang data hari sebelumnya sesuai zona waktu; seluruh menit akhir ikut disertakan. Setiap PDF memuat maksimal 20 metrik dan dapat dikemas dalam satu ZIP per jadwal per hari.</p>
    <p className="muted">Tanggal mulai–akhir membatasi tanggal eksekusi harian, termasuk kedua tanggal tersebut. Kosongkan tanggal jika tidak ingin memberi batas. Periode yang sudah masuk antrean tetap diselesaikan.</p>
    {error&&<p className="alert error" role="alert">{error}</p>}{message&&<p className="alert success" role="status">{message}</p>}
    {editing!==null&&<p className="info-note">Perubahan jam laporan, host group, host, metrik, dan opsi ZIP berlaku untuk periode berikutnya. Antrean yang sudah dibuat tetap memakai pilihan awal; mengaktifkan kembali jadwal melanjutkan antrean tersebut.</p>}
    <form onSubmit={save}><div className="form-grid">
      <label><span>Nama jadwal otomatis</span><input required maxLength={200} value={name} onChange={e=>setName(e.target.value)}/></label>
      <label><span>Sumber jadwal otomatis</span><select value={source} onChange={e=>{setSource(e.target.value);setSelections([]);setGroups([]);}}><option value="all">Semua sumber Zabbix</option>{servers.map(s=><option key={s.id} value={s.id} disabled={!s.configured}>{s.name}</option>)}</select></label>
      <label><span>Status host otomatis</span><select value={hostStatus} onChange={e=>{setHostStatus(e.target.value);setSelections([]);}}><option value="all">Semua host</option><option value="enabled">Host aktif</option><option value="disabled">Host nonaktif</option></select></label>
      <label><span>Cakupan laporan otomatis</span><select value={selectionMode} onChange={e=>setSelectionMode(e.target.value==="selected"?"selected":"all")}><option value="all">Semua host dan metrik numerik aktif</option><option value="selected">Pilih host dan metrik</option></select></label>
      <label><span>Jam eksekusi harian</span><input required type="time" min="00:00" max="23:59" step="60" value={clock} onChange={e=>setClock(e.target.value)}/></label>
      <label><span>Jam mulai laporan</span><input required type="time" min="00:00" max="23:59" step="60" value={dataStart} onChange={e=>setDataStart(e.target.value)}/></label>
      <label><span>Jam akhir laporan</span><input required type="time" min="00:00" max="23:59" step="60" value={dataEnd} onChange={e=>setDataEnd(e.target.value)}/></label>
      <label><span>Tanggal mulai jadwal</span><input type="date" value={dateStart} onChange={e=>setDateStart(e.target.value)}/></label>
      <label><span>Tanggal akhir jadwal</span><input type="date" value={dateEnd} onChange={e=>setDateEnd(e.target.value)}/></label>
      <label><span>Zona waktu jadwal otomatis</span><select value={timezone} onChange={e=>setTimezone(e.target.value)}>{Array.from(new Set(["Asia/Jakarta","Asia/Makassar","Asia/Jayapura",timezone])).map(t=><option key={t}>{t}</option>)}</select></label>
      <label className="metric"><input type="checkbox" checked={enabled} onChange={e=>setEnabled(e.target.checked)}/><span>{selectionMode==="selected"?"Aktifkan otomatis host terpilih":"Aktifkan otomatis semua host"}</span></label>
      <label className="metric"><input type="checkbox" checked={packageZip} onChange={e=>setPackageZip(e.target.checked)}/><span>Kemas PDF menjadi satu ZIP</span></label>
    </div>
    <AutomaticGroupPicker source={source} categories={categories} groups={groups} onChange={(nextCategories,nextGroups)=>{setCategories(nextCategories);setGroups(nextGroups);setSelections([]);}}/>
    {selectionMode==="selected"&&<AutomaticHostSelection key={`${source}:${hostStatus}:${groupKey}`} servers={servers} source={source} status={hostStatus} groups={groups} groupFilter={categories.length>0} value={selections} onChange={setSelections}/>}
    {packageZip&&<p className="muted">Satu ZIP disimpan setelah periode selesai. PDF individual dapat diunduh dari riwayat, dan salinan sementara dibersihkan setelah ZIP terverifikasi. Penghematan ukuran mengikuti isi PDF.</p>}
    {preview?<p>{selectionMode==="selected"?`Cakupan laporan: ${selections.length} host terpilih dari ${preview.hosts} host tersedia`:`Cakupan saat ini: ${preview.hosts} host`} ({preview.servers.map(s=>`${s.id==="primary"?"Zabbix Utama":"Zabbix Cadangan"}: ${s.hosts}`).join(", ")}). Daftar metrik diperiksa saat host diproses.</p>:<p className="muted">{previewError||"Memuat cakupan host…"}</p>}
    <div className="actions"><button className="primary" disabled={busy}>{busy?"Menyimpan…":editing===null?"Simpan otomatis":"Perbarui otomatis"}</button>{editing!==null&&<button type="button" onClick={reset}>Batal edit otomatis</button>}</div></form>
    <h3 style={{marginTop:24}}>Progres jadwal otomatis</h3>
    {!rows.length?<p className="empty">Belum ada jadwal otomatis tersimpan.</p>:<div className="table-wrap"><table aria-label="Progres jadwal otomatis"><thead><tr><th>Jadwal</th><th>Waktu</th><th>Progres</th><th>Aksi</th></tr></thead><tbody>{rows.map(row=><tr key={row.id}>
      <td><strong>{row.name}</strong><small>{row.enabled?"Aktif":"Nonaktif"} · {row.zabbix_server==="all"?"Semua sumber":row.zabbix_server} · {row.host_status==="all"?"Semua host":row.host_status==="enabled"?"Host aktif":"Host nonaktif"}</small>{row.last_error&&<small className="warning-text">{row.last_error}</small>}</td>
      <td>{String(row.hour).padStart(2,"0")}:{String(row.minute).padStart(2,"0")}<small>{row.timezone}</small><small>Data {row.data_start_time||"00:00"}–{row.data_end_time||"23:59"}</small><small>{row.date_start||"Tanpa batas mulai"} → {row.date_end||"Tanpa batas akhir"}</small>{row.date_status==="UPCOMING"&&<small>Belum masuk tanggal mulai</small>}{row.date_status==="EXPIRED"&&<small>Masa jadwal berakhir</small>}{!!row.host_categories?.length&&<small>Group {row.host_categories.join(", ")}</small>}</td>
      <td>{states[row.run_status]||row.run_status}<small>{row.done_hosts}/{row.total_hosts} host · {row.files_completed} PDF</small>{row.selection_mode==="selected"&&<small>{row.host_selections.length} host dipilih</small>}{row.report_date&&<small>Periode terbaru: {row.report_date}</small>}<small>{row.pending_periods||0} periode dalam antrean</small><small>{row.partial_hosts} sebagian · {row.failed_hosts} gagal · {row.skipped_hosts} dilewati</small>
        {row.archive_download_url?<><a href={row.archive_download_url} target="_blank" rel="noreferrer">Unduh ZIP ↗</a><small>ZIP {((row.archive_size||0)/1048576).toFixed(2)} MB · PDF sebelum kompresi {((row.original_size||0)/1048576).toFixed(2)} MB</small></>:row.package_zip&&row.run_id!=null&&<small>{row.archive_status==="EMPTY"?"Tidak ada PDF untuk ZIP":row.archive_status==="ERROR"?"Pengemasan ZIP tertunda":row.archive_status==="PACKING"?"Mengemas ZIP…":"ZIP menunggu periode selesai"}</small>}
        {row.archive_error&&<small className="warning-text">{row.archive_error}</small>}</td>
      <td><div className="schedule-actions"><button type="button" className="small-button" disabled={busy} onClick={()=>edit(row)}>Edit otomatis</button><button type="button" className="small-button" disabled={busy} onClick={()=>action(row)}>{row.enabled?"Jeda otomatis":"Aktifkan otomatis"}</button><button type="button" className="small-button" onClick={()=>{setTasks([]);setOffset(0);setDetail(row.id);}}>Detail host</button><button type="button" className="small-button danger" disabled={busy} onClick={()=>action(row,true)}>Hapus otomatis</button></div></td>
    </tr>)}</tbody></table></div>}
    {detail!==null&&<div><div className="card-heading"><h3>Detail antrean host</h3><button type="button" onClick={()=>setDetail(null)}>Tutup detail</button></div><p className="muted">Progres host untuk periode terbaru. Hasil periode sebelumnya tersedia di halaman Laporan.</p>{detailLoading&&<p role="status">Memuat progres…</p>}
      {!tasks.length&&!detailLoading?<p>Belum ada eksekusi.</p>:<div className="table-wrap"><table aria-label="Detail antrean host"><thead><tr><th>Host / sumber</th><th>Status</th><th>Metrik</th><th>PDF</th></tr></thead><tbody>{tasks.map(t=><tr key={t.id}><td>{t.host_name}<small>{t.zabbix_server}</small></td><td>{states[t.status]||t.status}{t.last_error&&<small className="warning-text">{t.last_error}</small>}</td><td>{t.item_offset}/{t.total_metrics}</td><td>{t.files_completed}</td></tr>)}</tbody></table></div>}
      <div className="actions"><button type="button" disabled={offset===0||detailLoading} onClick={()=>setOffset(Math.max(0,offset-25))}>Host sebelumnya</button><span>{total?`${offset+1}–${Math.min(offset+25,total)} dari ${total} host`:"0 host"}</span><button type="button" disabled={offset+25>=total||detailLoading} onClick={()=>setOffset(offset+25)}>Host berikutnya</button></div>
    </div>}
  </section>;
}
