"use client";
import {useEffect,useRef,useState,useCallback} from "react";
import HistoryTable from "../../components/HistoryTable";
import {api} from "../../lib/api";
import type {Execution} from "../../lib/api";

type Report={filename:string;size:number;created:number;download_url:string};
const PAGE=25;

export default function ReportsPage(){
  const [reports,setReports]=useState<Report[]>([]),[history,setHistory]=useState<Execution[]>([]);
  const [page,setPage]=useState(0),[total,setTotal]=useState(0),[historyPage,setHistoryPage]=useState(0),[historyTotal,setHistoryTotal]=useState(0);
  const [loading,setLoading]=useState(true),[error,setError]=useState(""),[search,setSearch]=useState("");
  const request=useRef<AbortController|null>(null);
  const refresh=useCallback(async()=>{
    if(request.current)return;
    const controller=new AbortController();request.current=controller;
    setLoading(true);setError("");
    try{
      const [r,h]=await Promise.all([api<Report[]>(`/reports?limit=${PAGE}&offset=${page*PAGE}`,{signal:controller.signal}),api<Execution[]>(`/history?limit=${PAGE}&offset=${historyPage*PAGE}`,{signal:controller.signal})]);
      if(controller.signal.aborted)return;
      setReports(r.data);setTotal(r.total || 0);setHistory(h.data);setHistoryTotal(h.total || 0);
    }catch(e){if(!controller.signal.aborted)setError(e instanceof Error ? e.message : "Laporan gagal dimuat.");}
    finally{if(request.current===controller){request.current=null;setLoading(false);}}
  },[page,historyPage]);
  useEffect(()=>{
    void refresh();
    const update=()=>{if(document.visibilityState==="visible")void refresh();};
    const timer=setInterval(update,5000);
    document.addEventListener("visibilitychange",update);
    return ()=>{clearInterval(timer);document.removeEventListener("visibilitychange",update);request.current?.abort();request.current=null;};
  },[refresh]);
  const filtered=reports.filter(r=>r.filename.toLowerCase().includes(search.toLowerCase()));
  function pager(current:number,count:number,change:(n:number)=>void){
    return <div className="pagination"><small>{count} hasil · halaman {current+1} dari {Math.max(Math.ceil(count/PAGE),1)}</small><div className="actions">
      <button disabled={loading||current===0} onClick={()=>change(current-1)}>Sebelumnya</button><button disabled={loading||(current+1)*PAGE>=count} onClick={()=>change(current+1)}>Berikutnya</button></div></div>;
  }
  return <main><div className="page-heading"><div><p className="eyebrow">Arsip operasional</p><h1>Laporan & riwayat</h1><p className="muted">Daftar diperbarui otomatis setiap 5 detik. Unduh PDF atau ZIP yang selesai dibuat; PDF dalam ZIP tetap dapat diunduh satu per satu melalui riwayat.</p></div><button onClick={()=>refresh()} disabled={loading}>Refresh laporan</button></div>
    {error&&<div className="alert error" role="alert">{error}</div>}
    <section className="card"><div className="card-heading"><h2>Arsip PDF</h2><a href="/">Buat laporan →</a></div>
      <div className="filter-row"><input aria-label="Cari PDF pada halaman ini" placeholder="Cari PDF pada halaman ini…" value={search} onChange={e=>setSearch(e.target.value)} /></div>
      {loading&&!reports.length?<p role="status">Memuat PDF…</p>:!filtered.length?<p className="empty">{reports.length ? "Tidak ada PDF yang cocok pada halaman ini." : "Belum ada laporan PDF."}</p>:
        <div className="table-wrap"><table><thead><tr><th>Nama file</th><th>Dibuat</th><th>Ukuran</th><th>Unduh</th></tr></thead><tbody>
          {filtered.map(r=><tr key={r.filename}><td style={{overflowWrap:"anywhere"}}>{r.filename}</td><td className="nowrap">{new Date(r.created*1000).toLocaleString("id-ID")}</td>
            <td>{(r.size/1024).toFixed(1)} KB</td><td><a href={r.download_url} target="_blank" rel="noreferrer">Unduh {r.filename.toLowerCase().endsWith(".zip")?"ZIP":"PDF"} ↗</a></td></tr>)}
        </tbody></table></div>}
      {pager(page,total,setPage)}
    </section>
    <section className="card"><h2>Riwayat eksekusi</h2><HistoryTable rows={history} loading={loading} />{pager(historyPage,historyTotal,setHistoryPage)}</section>
  </main>;
}
