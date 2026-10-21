"use client";

import { useEffect, useState, useRef } from "react";
import MetricPicker from "../components/MetricPicker";
import Chart from "../components/Chart";
import CombinedChart from "../components/CombinedChart";
import {combinedUnit} from "../lib/combined";
import HostDowntime from "../components/HostDowntime";
import HostPicker from "../components/HostPicker";
import HostDetails from "../components/HostDetails";
import HistoryTable from "../components/HistoryTable";
import Icon from "../components/Icon";
import type {IconName} from "../components/Icon";
import { api, numericItems, localInput, responseError, downloadFilename, getCsrfToken } from "../lib/api";
import type { Host, Item, MetricData, Execution, ZabbixServer } from "../lib/api";

type Summary = {total_schedules: number; active_schedules: number; total_reports: number};

function monthDays(value:string) {
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(value)) return 0;
  const [year,month]=value.split("-").map(Number);
  return new Date(year,month,0).getDate();
}

function validMonthRange(month:string,first:string,last:string) {
  const start=Number(first),end=Number(last),limit=monthDays(month);
  return limit>0 && Number.isInteger(start) && Number.isInteger(end) && start>=1 && end>=start && end<=limit;
}

export default function Home() {
  const [hosts,setHosts] = useState<Host[]>([]);
  const [servers,setServers] = useState<ZabbixServer[]>([]);
  const [zabbixServer,setZabbixServer] = useState<ZabbixServer["id"]>("primary");
  const [items,setItems] = useState<Item[]>([]);
  const [hostId,setHostId] = useState(""), [hostSearch,setHostSearch] = useState("");
  const [selected,setSelected] = useState<string[]>([]);
  const [metricId,setMetricId] = useState("");
  const [from,setFrom] = useState(""), [to,setTo] = useState("");
  const [reportDate,setReportDate] = useState("");
  const [periodMode,setPeriodMode] = useState<"daily" | "monthly" | "custom">("daily");
  const [reportMonth,setReportMonth] = useState("");
  const [firstDay,setFirstDay] = useState("1"), [lastDay,setLastDay] = useState("31");
  const [resolution,setResolution] = useState<"minute" | "hourly" | "auto">("minute");
  const [title,setTitle] = useState("");
  const [downtimeTriggerId,setDowntimeTriggerId] = useState("");
  const [includeDowntime,setIncludeDowntime] = useState(true);
  const [summary,setSummary] = useState<Summary | null>(null);
  const [services,setServices] = useState<Record<string,string>>({});
  const [updatedAt,setUpdatedAt] = useState<Date | null>(null);
  const [history,setHistory] = useState<Execution[]>([]);
  const [chart,setChart] = useState<MetricData | null>(null);
  const [chartMode,setChartMode] = useState<"separate"|"combined">("separate");
  const [combinedChart,setCombinedChart] = useState<MetricData[]|null>(null);
  const [loading,setLoading] = useState(true), [loadingItems,setLoadingItems] = useState(false);
  const [loadingChart,setLoadingChart] = useState(false), [generating,setGenerating] = useState(false);
  const [error,setError] = useState(""), [dashboardError,setDashboardError] = useState("");
  const [message,setMessage] = useState(""), [partial,setPartial] = useState(false);
  const chartRequest = useRef<AbortController | null>(null);
  const dashboardRequest = useRef<AbortController | null>(null);

  async function refreshDashboard() {
    if (dashboardRequest.current && !dashboardRequest.current.signal.aborted) return;
    const controller = new AbortController();
    dashboardRequest.current = controller;
    try {
      const results = await Promise.allSettled([
        api<Summary>("/dashboard/summary", {signal:controller.signal}),
        api<Record<string,string>>("/dashboard/status", {signal:controller.signal}),
        api<Execution[]>("/history?limit=10", {signal:controller.signal}),
      ]);
      if (controller.signal.aborted) return;
      const [stats,status,logs] = results;
      if (stats.status === "fulfilled") setSummary(stats.value.data);
      if (status.status === "fulfilled") {setServices(status.value.data);setUpdatedAt(new Date());}
      if (logs.status === "fulfilled") setHistory(logs.value.data);
      const failure = results.find(r => r.status === "rejected");
      setDashboardError(failure?.status === "rejected" ? failure.reason.message : "");
    } finally {
      if (dashboardRequest.current === controller) dashboardRequest.current = null;
    }
  }
  useEffect(() => {
    const yesterday = new Date(); yesterday.setDate(yesterday.getDate()-1);
    selectReportDate(localInput(yesterday).slice(0,10));
    api<ZabbixServer[]>("/zabbix/servers").then(result => setServers(result.data))
      .catch(e => setError(e.message));
    refreshDashboard();
    const timer = setInterval(refreshDashboard, 30000);
    return () => {clearInterval(timer); chartRequest.current?.abort(); dashboardRequest.current?.abort();};
  }, []);
  useEffect(() => {
    setHosts([]); setHostId(""); setHostSearch(""); setItems([]); setSelected([]); setMetricId(""); setChart(null);
    const controller = new AbortController();
    setLoading(true);
    api<Host[]>(`/zabbix/hosts?server_id=${zabbixServer}`, {signal:controller.signal})
      .then(result => setHosts(result.data))
      .catch(e => {if (e.name !== "AbortError") setError(e.message);})
      .finally(() => {if (!controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
  }, [zabbixServer]);
  useEffect(() => {
    setItems([]); setSelected([]); setMetricId(""); setChart(null);
    setDowntimeTriggerId("");
    if (!hostId) {setLoadingItems(false);return;}
    const controller = new AbortController();
    setLoadingItems(true);
    api<Item[]>(`/zabbix/hosts/${hostId}/items?server_id=${zabbixServer}`, {signal: controller.signal})
      .then(result => setItems(numericItems(result.data)))
      .catch(e => {if (e.name !== "AbortError") setError(e.message);})
      .finally(() => {if (!controller.signal.aborted) setLoadingItems(false);});
    return () => controller.abort();
  }, [hostId,zabbixServer]);
  useEffect(() => {
    if (!selected.includes(metricId)) setMetricId(selected[0] || "");
  }, [selected,metricId]);
  useEffect(() => {
    chartRequest.current?.abort();setLoadingChart(false);setChart(null);setCombinedChart(null);
  }, [metricId,from,to,zabbixServer,resolution,hostId,chartMode]);
  useEffect(()=>{
    if(chartMode==="combined"){chartRequest.current?.abort();setLoadingChart(false);setCombinedChart(null);}
  },[selected,chartMode]);

  function validateCombined(){
    if(selected.length<2)throw new Error("Pilih minimal dua metrik untuk grafik gabungan.");
    combinedUnit(items.filter(item=>selected.includes(item.itemid)));
  }

  function period() {
    if (periodMode === "monthly" && !validMonthRange(reportMonth,firstDay,lastDay)) {
      throw new Error("Pilih bulan dan rentang tanggal yang valid; tanggal akhir harus sama atau setelah tanggal awal dan berada dalam bulan tersebut.");
    }
    const start = Math.floor(new Date(from).getTime()/1000), end = Math.floor(new Date(to).getTime()/1000)+59;
    if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) throw new Error("Pilih periode yang valid; waktu selesai harus setelah waktu mulai.");
    if (end-start > 90*86400) throw new Error("Periode maksimal 90 hari.");
    return {time_from:start,time_till:end};
  }
  function selectReportDate(value:string) {
    setReportDate(value);
    if (!value) {setFrom("");setTo("");return;}
    setReportMonth(value.slice(0,7));
    const [year,month,day]=value.split("-").map(Number);
    setFrom(localInput(new Date(year,month-1,day,0,0)));
    setTo(localInput(new Date(year,month-1,day,23,59)));
  }
  function selectMonthRange(month:string,first:string,last:string) {
    setReportMonth(month);setFirstDay(first);setLastDay(last);setReportDate("");
    if (!validMonthRange(month,first,last)) {setFrom("");setTo("");return;}
    setFrom(`${month}-${String(Number(first)).padStart(2,"0")}T00:00`);
    setTo(`${month}-${String(Number(last)).padStart(2,"0")}T23:59`);
  }
  function selectPeriodMode(value:"daily" | "monthly" | "custom") {
    setPeriodMode(value);setError("");
    if (value === "monthly") {
      const month=from.slice(0,7) || reportMonth;
      selectMonthRange(month,"1",String(monthDays(month)));
    } else if (value === "daily") {
      selectReportDate(from.slice(0,10) || localInput(new Date()).slice(0,10));
    }
  }
  async function preview() {
    setError(""); setLoadingChart(true);
    const controller = new AbortController(); chartRequest.current?.abort(); chartRequest.current = controller;
    try {
      if (chartMode==="combined")validateCombined();
      else if (!metricId) throw new Error("Pilih minimal satu metrik.");
      const p = period();
      if(chartMode==="combined"){
        const results:MetricData[]=[];
        for(let index=0;index<selected.length;index+=4){
          const batch=await Promise.all(selected.slice(index,index+4).map(async id=>{
            try{return (await api<MetricData>(`/zabbix/items/${id}/data?time_from=${p.time_from}&time_till=${p.time_till}&server_id=${zabbixServer}&resolution=${resolution}`,{signal:controller.signal})).data;}
            catch(e){
              if(controller.signal.aborted)throw e;
              return {item:items.find(item=>item.itemid===id)!,source:"unavailable",points:[],...p,resolution,
                summary:{minimum:null,maximum:null,average:null,last:null,samples:0},warning:e instanceof Error?e.message:"Data metrik tidak tersedia."} as MetricData;
            }
          }));
          results.push(...batch);
        }
        if(!controller.signal.aborted)setCombinedChart(results);
      }else{
        const result = await api<MetricData>(`/zabbix/items/${metricId}/data?time_from=${p.time_from}&time_till=${p.time_till}&server_id=${zabbixServer}&resolution=${resolution}`, {signal:controller.signal});
        if(!controller.signal.aborted)setChart(result.data);
      }
    } catch (e) {if (!controller.signal.aborted && e instanceof Error && e.name !== "AbortError") setError(e.message);}
    finally {if (chartRequest.current === controller) setLoadingChart(false);}
  }
  async function generate() {
    setError(""); setMessage(""); setGenerating(true);
    try {
      const host = hosts.find(h => h.hostid === hostId);
      if (!host || !selected.length) throw new Error("Pilih host dan minimal satu metrik.");
      if (!title.trim()) throw new Error("Judul laporan wajib diisi.");
      if(chartMode==="combined")validateCombined();
      const response = await fetch("/api/v1/reports/generate", {
        method:"POST", headers:{"Content-Type":"application/json","X-CSRF-Token":getCsrfToken()},
        body:JSON.stringify({zabbix_server:zabbixServer,host_id:hostId,host_name:host.name || host.host,item_ids:selected,
          ...period(),resolution,title,chart_mode:chartMode,timezone:Intl.DateTimeFormat().resolvedOptions().timeZone,
          include_downtime:includeDowntime,downtime_trigger_id:downtimeTriggerId || null}),
      });
      if (!response.ok) throw await responseError(response);
      const blob = await response.blob(), url = URL.createObjectURL(blob);
      const disposition = response.headers.get("Content-Disposition") || "";
      const filename = downloadFilename(disposition, `${(host.name || host.host).replace(/[\\/:*?"<>|]/g, "_")}.pdf`);
      const link = document.createElement("a"); link.href=url; link.download=filename;
      document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url);
      const incomplete = response.headers.get("X-Report-Status") === "PARTIAL";
      setPartial(incomplete); setMessage(incomplete ? "PDF dibuat dengan sebagian data. Lihat metrik yang kosong pada PDF dan riwayat." : "PDF berhasil dibuat, disimpan, dan diunduh.");
      await refreshDashboard();
    } catch (e) {setError(e instanceof Error ? e.message : "Ekspor gagal.");}
    finally {setGenerating(false);}
  }

  return <main>
    <div className="page-heading dashboard-heading"><div className="heading-copy"><p className="eyebrow"><span className="eyebrow-dot"/>TIM DATA CENTER PUSDATIN KEMENSOS</p><h1>Monitoring & laporan</h1><p className="muted">Pantau infrastruktur dan siapkan laporan operasional dalam satu workspace.</p></div>
      <div className="heading-tools"><label className="source-control"><span>Sumber Zabbix</span><select value={zabbixServer} onChange={e => {
        setError("");setHostId("");setHostSearch("");setZabbixServer(e.target.value === "secondary" ? "secondary" : "primary");
      }}>
        {servers.map(server => <option key={server.id} value={server.id} disabled={!server.configured}>
          {server.name}{server.configured ? "" : " (belum dikonfigurasi)"}
        </option>)}</select></label>
      <span className="sync-label"><Icon name="clock"/>{updatedAt ? `Diperbarui ${updatedAt.toLocaleTimeString("id-ID",{hour:"2-digit",minute:"2-digit",second:"2-digit"})}` : "Menunggu pembaruan"}</span>
      <button onClick={refreshDashboard}><Icon name="refresh"/>Refresh dashboard</button></div></div>
    {dashboardError && <div className="alert error" role="alert">{dashboardError}</div>}
    <div className="stat-grid">
      {[
        ["Host",loading ? "…" : hosts.length,"server","Terdaftar di Zabbix"],
        ["Laporan PDF / ZIP",summary?.total_reports ?? "…","file","Tersimpan di arsip"],
        ["Jadwal aktif",summary?.active_schedules ?? "…","calendar","Laporan otomatis"],
        ["Total jadwal",summary?.total_schedules ?? "…","layers","Konfigurasi tersimpan"],
      ].map(([label,value,icon,description]) =>
        <div className="kpi-card" key={String(label)}><div className="kpi-header"><span>{label}</span><span className="kpi-icon"><Icon name={icon as IconName}/></span></div>
          <strong>{value}</strong><small>{description}</small></div>)}
    </div>
    <section className="card"><div className="card-heading"><div className="section-title"><span className="section-icon"><Icon name="activity"/></span><div><h2>Status layanan</h2><p>Koneksi dan kesiapan sistem</p></div></div><span className="refresh-meta"><Icon name="refresh"/>Setiap 30 detik</span></div>
      <div className="status-grid">{[["backend","Backend","server"],["postgresql","Database","database"],["redis","Redis","layers"],["zabbix","Zabbix 7","network"],["zabbix_secondary","Zabbix 2","network"],["scheduler","Scheduler","calendar"]].map(([key,label,icon]) => {
        const value=services[key] || "checking",good=["connected","running"].includes(value),failed=["error","stopped"].includes(value);
        const captions:Record<string,string>={connected:"Terhubung",running:"Berjalan",starting:"Memulai",error:"Gangguan",stopped:"Berhenti",unknown:"Belum diketahui",checking:"Memeriksa…",not_configured:"Belum dikonfigurasi"};
        return <div className={`service ${good ? "service-good" : failed ? "service-error" : "service-warning"}`} key={key}><span className="service-icon"><Icon name={icon as IconName}/></span>
          <div className="service-details"><strong>{label}</strong><small>{captions[value] || value}</small></div><span className={`dot ${good ? "ok" : failed ? "error" : ""}`}/></div>;
      })}</div>
    </section>
    {error && <div className="alert error" role="alert">{error}</div>}
    {message && <div className={`alert ${partial ? "warning" : "success"}`} role="status">{message}</div>}
    <div className="grid-two">
      <section className="card report-config"><div className="card-heading"><div className="section-title"><span className="section-icon"><Icon name="sliders"/></span><div><h2>Konfigurasi laporan</h2><p>Host, periode, dan metrik</p></div></div><span className="panel-index">01</span></div><div className="form-grid">
        <label className="span-two"><span>Judul laporan</span><input value={title} maxLength={200} onChange={e => setTitle(e.target.value)} /></label>
        <HostPicker key={zabbixServer} hosts={hosts} value={hostId} search={hostSearch} onSearchChange={setHostSearch}
          loading={loading} onChange={value=>{setError("");setHostId(value);}} />
        {hostId && <HostDetails key={`${zabbixServer}:${hostId}`} hostId={hostId} serverId={zabbixServer}/>}
        <label className="span-two"><span>Periode laporan</span><select value={periodMode} onChange={e => selectPeriodMode(e.target.value as "daily" | "monthly" | "custom")}>
          <option value="daily">Satu hari</option><option value="monthly">Rentang tanggal dalam satu bulan</option><option value="custom">Periode khusus</option>
        </select></label>
        {periodMode === "daily" && <label className="span-two"><span>Tanggal laporan</span><input type="date" value={reportDate} onChange={e => selectReportDate(e.target.value)} /></label>}
        {periodMode === "monthly" && <>
          <label className="span-two"><span>Bulan laporan</span><input type="month" value={reportMonth} onChange={e => {
            const month=e.target.value,limit=monthDays(month);
            selectMonthRange(month,firstDay ? String(Math.min(Number(firstDay),limit)) : "",lastDay ? String(Math.min(Number(lastDay),limit)) : "");
          }} /></label>
          <label><span>Tanggal awal</span><input type="number" min={1} max={monthDays(reportMonth) || 31} step={1} value={firstDay} onChange={e => selectMonthRange(reportMonth,e.target.value,lastDay)} /></label>
          <label><span>Tanggal akhir</span><input type="number" min={1} max={monthDays(reportMonth) || 31} step={1} value={lastDay} onChange={e => selectMonthRange(reportMonth,firstDay,e.target.value)} /></label>
        </>}
        <label><span>Mulai</span><input type="datetime-local" value={from} readOnly={periodMode === "monthly"} onChange={e => {setPeriodMode("custom");setReportDate("");setFrom(e.target.value);}} /></label>
        <label><span>Selesai</span><input type="datetime-local" value={to} readOnly={periodMode === "monthly"} onChange={e => {setPeriodMode("custom");setReportDate("");setTo(e.target.value);}} /></label>
        <label><span>Rincian waktu</span><select value={resolution} onChange={e => setResolution(e.target.value as "minute" | "hourly" | "auto")}>
          <option value="minute">Per menit (history)</option><option value="hourly">Per jam (trend)</option><option value="auto">Otomatis sesuai periode</option>
        </select></label>
      </div>
        {periodMode === "monthly" && validMonthRange(reportMonth,firstDay,lastDay) && <p className="info-note">Satu PDF untuk {Number(lastDay)-Number(firstDay)+1} hari, tanggal {firstDay}–{lastDay} {new Date(`${reportMonth}-01T00:00`).toLocaleDateString("id-ID",{month:"long",year:"numeric"})}. Setiap tanggal diurutkan dengan grafik 00:00–23:59 dan statistiknya sendiri.</p>}
        <p className="info-note">Tanggal laporan mencakup 00:00–23:59 waktu lokal. Grafik per menit dan satu baris statistik per hari disertakan dalam PDF. Detail mengikuti interval sampel Zabbix; menit tanpa data tidak diisi. Periode maksimal 90 hari.</p>
        <MetricPicker items={items} selected={selected} onChange={setSelected} loading={loadingItems} />
        <label className="chart-mode-field"><span>Mode grafik dan PDF</span><select value={chartMode} onChange={e=>{setError("");setChartMode(e.target.value as "separate"|"combined");}}>
          <option value="separate">Grafik terpisah per metrik</option><option value="combined">Grafik gabungan dari metrik terpilih</option></select>
          {chartMode==="combined" && <small>Pilih minimal 2 metrik dengan satuan sejenis. Received hijau, Sent merah; satu grafik per hari dan statistik tiap metrik.</small>}</label>
        <p className="info-note">Nama file PDF otomatis mengikuti nama host dan periode laporan.</p>
        <div className="actions"><button className="primary" onClick={generate} disabled={!selected.length || generating}>
          <Icon name="download"/>{generating ? "Membuat PDF…" : `Ekspor PDF (${selected.length} metrik)`}</button></div>
      </section>
      <section className="card chart-card"><div className="card-heading"><div className="section-title"><span className="section-icon"><Icon name="chart"/></span><div><h2>Pratinjau grafik</h2><p>Data metrik terpilih</p></div></div><span className="panel-index">02</span></div>
        {chartMode==="separate"?<label><span>Metrik grafik</span><select value={metricId} onChange={e => setMetricId(e.target.value)} disabled={!selected.length}>
          <option value="">Pilih metrik</option>{items.filter(i => selected.includes(i.itemid)).map(i => <option key={i.itemid} value={i.itemid}>{i.name}</option>)}</select></label>:
          <p className="muted">{selected.length} metrik terpilih akan ditampilkan bersama.</p>}
        <div className="actions"><button onClick={preview} disabled={loadingChart || (chartMode==="combined"?selected.length<2:!metricId)}><Icon name="activity"/>{loadingChart ? "Memuat grafik…" : "Tampilkan grafik"}</button></div>
        {combinedChart?<CombinedChart data={combinedChart}/>:chart ? <Chart data={chart}/> : <div className="chart-empty"><span><Icon name="chart"/></span><strong>Pratinjau belum tersedia</strong><p>Pilih metrik dan tampilkan grafik untuk melihat data dan statistiknya.</p></div>}
      </section>
    </div>
    <HostDowntime hostId={hostId} serverId={zabbixServer} from={from} to={to} triggerId={downtimeTriggerId}
      onTriggerChange={setDowntimeTriggerId} includeInPdf={includeDowntime} onIncludeChange={setIncludeDowntime}/>
    <section className="card"><div className="card-heading"><div className="section-title"><span className="section-icon"><Icon name="history"/></span><div><h2>Riwayat eksekusi terbaru</h2><p>Aktivitas laporan manual dan terjadwal</p></div></div><a href="/reports" className="history-link">Lihat semua riwayat<Icon name="arrow"/></a></div><HistoryTable rows={history} loading={false}/></section>
  </main>;
}
