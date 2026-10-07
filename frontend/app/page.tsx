"use client";

import { useEffect, useState, useRef } from "react";
import MetricPicker from "../components/MetricPicker";
import Chart from "../components/Chart";
import HistoryTable from "../components/HistoryTable";
import Icon from "../components/Icon";
import type {IconName} from "../components/Icon";
import { api, numericItems, localInput, responseError } from "../lib/api";
import type { Host, Item, MetricData, Execution } from "../lib/api";

type Summary = {total_schedules: number; active_schedules: number; total_reports: number};

export default function Home() {
  const [hosts,setHosts] = useState<Host[]>([]);
  const [items,setItems] = useState<Item[]>([]);
  const [hostId,setHostId] = useState("");
  const [selected,setSelected] = useState<string[]>([]);
  const [metricId,setMetricId] = useState("");
  const [from,setFrom] = useState(""), [to,setTo] = useState("");
  const [title,setTitle] = useState("ZABBIX MONITORING REPORT");
  const [summary,setSummary] = useState<Summary | null>(null);
  const [services,setServices] = useState<Record<string,string>>({});
  const [updatedAt,setUpdatedAt] = useState<Date | null>(null);
  const [history,setHistory] = useState<Execution[]>([]);
  const [chart,setChart] = useState<MetricData | null>(null);
  const [loading,setLoading] = useState(true), [loadingItems,setLoadingItems] = useState(false);
  const [loadingChart,setLoadingChart] = useState(false), [generating,setGenerating] = useState(false);
  const [error,setError] = useState(""), [dashboardError,setDashboardError] = useState("");
  const [message,setMessage] = useState(""), [partial,setPartial] = useState(false);
  const chartRequest = useRef<AbortController | null>(null);

  async function refreshDashboard() {
    const results = await Promise.allSettled([
      api<Summary>("/dashboard/summary"), api<Record<string,string>>("/dashboard/status"),
      api<Execution[]>("/history?limit=10"),
    ]);
    const [stats,status,logs] = results;
    if (stats.status === "fulfilled") setSummary(stats.value.data);
    if (status.status === "fulfilled") {setServices(status.value.data);setUpdatedAt(new Date());}
    if (logs.status === "fulfilled") setHistory(logs.value.data);
    const failure = results.find(r => r.status === "rejected");
    setDashboardError(failure?.status === "rejected" ? failure.reason.message : "");
  }
  useEffect(() => {
    const now = new Date();
    setFrom(localInput(new Date(now.getTime()-86400000))); setTo(localInput(now));
    api<Host[]>("/zabbix/hosts").then(result => setHosts(result.data)).catch(e => setError(e.message)).finally(() => setLoading(false));
    refreshDashboard();
    const timer = setInterval(refreshDashboard, 30000);
    return () => {clearInterval(timer); chartRequest.current?.abort();};
  }, []);
  useEffect(() => {
    setItems([]); setSelected([]); setMetricId(""); setChart(null);
    if (!hostId) {setLoadingItems(false);return;}
    const controller = new AbortController();
    setLoadingItems(true);
    api<Item[]>(`/zabbix/hosts/${hostId}/items`, {signal: controller.signal})
      .then(result => setItems(numericItems(result.data)))
      .catch(e => {if (e.name !== "AbortError") setError(e.message);})
      .finally(() => {if (!controller.signal.aborted) setLoadingItems(false);});
    return () => controller.abort();
  }, [hostId]);
  useEffect(() => {
    if (!selected.includes(metricId)) setMetricId(selected[0] || "");
  }, [selected,metricId]);
  useEffect(() => {chartRequest.current?.abort(); setChart(null);}, [metricId,from,to]);

  function period() {
    const start = Math.floor(new Date(from).getTime()/1000), end = Math.floor(new Date(to).getTime()/1000);
    if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) throw new Error("Pilih periode yang valid; waktu selesai harus setelah waktu mulai.");
    if (end-start > 90*86400) throw new Error("Periode maksimal 90 hari.");
    return {time_from:start,time_till:end};
  }
  async function preview() {
    setError(""); setLoadingChart(true);
    const controller = new AbortController(); chartRequest.current?.abort(); chartRequest.current = controller;
    try {
      if (!metricId) throw new Error("Pilih minimal satu metrik.");
      const p = period();
      const result = await api<MetricData>(`/zabbix/items/${metricId}/data?time_from=${p.time_from}&time_till=${p.time_till}`, {signal:controller.signal});
      setChart(result.data);
    } catch (e) {if (e instanceof Error && e.name !== "AbortError") setError(e.message);}
    finally {if (chartRequest.current === controller) setLoadingChart(false);}
  }
  async function generate() {
    setError(""); setMessage(""); setGenerating(true);
    try {
      const host = hosts.find(h => h.hostid === hostId);
      if (!host || !selected.length) throw new Error("Pilih host dan minimal satu metrik.");
      if (!title.trim()) throw new Error("Judul laporan wajib diisi.");
      const response = await fetch("/api/v1/reports/generate", {
        method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({host_id:hostId,host_name:host.name || host.host,item_ids:selected,
          ...period(),title,timezone:Intl.DateTimeFormat().resolvedOptions().timeZone}),
      });
      if (!response.ok) throw await responseError(response);
      const blob = await response.blob(), url = URL.createObjectURL(blob);
      const disposition = response.headers.get("Content-Disposition") || "";
      const filename = /filename="?([^";]+)"?/.exec(disposition)?.[1] || "zabbix_report.pdf";
      const link = document.createElement("a"); link.href=url; link.download=filename;
      document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url);
      const incomplete = response.headers.get("X-Report-Status") === "PARTIAL";
      setPartial(incomplete); setMessage(incomplete ? "PDF dibuat dengan sebagian data. Lihat metrik yang kosong pada PDF dan riwayat." : "PDF berhasil dibuat, disimpan, dan diunduh.");
      await refreshDashboard();
    } catch (e) {setError(e instanceof Error ? e.message : "Ekspor gagal.");}
    finally {setGenerating(false);}
  }

  return <main>
    <div className="page-heading dashboard-heading"><div className="heading-copy"><p className="eyebrow"><span className="eyebrow-dot"/>IT OPERATIONS</p><h1>Monitoring & laporan</h1><p className="muted">Pantau infrastruktur dan siapkan laporan operasional dalam satu workspace.</p></div>
      <div className="heading-tools"><span className="sync-label"><Icon name="clock"/>{updatedAt ? `Diperbarui ${updatedAt.toLocaleTimeString("id-ID",{hour:"2-digit",minute:"2-digit",second:"2-digit"})}` : "Menunggu pembaruan"}</span>
      <button onClick={refreshDashboard}><Icon name="refresh"/>Refresh dashboard</button></div></div>
    {dashboardError && <div className="alert error" role="alert">{dashboardError}</div>}
    <div className="stat-grid">
      {[
        ["Host",loading ? "…" : hosts.length,"server","Terdaftar di Zabbix"],
        ["Laporan PDF",summary?.total_reports ?? "…","file","Tersimpan di arsip"],
        ["Jadwal aktif",summary?.active_schedules ?? "…","calendar","Laporan otomatis"],
        ["Total jadwal",summary?.total_schedules ?? "…","layers","Konfigurasi tersimpan"],
      ].map(([label,value,icon,description]) =>
        <div className="kpi-card" key={String(label)}><div className="kpi-header"><span>{label}</span><span className="kpi-icon"><Icon name={icon as IconName}/></span></div>
          <strong>{value}</strong><small>{description}</small></div>)}
    </div>
    <section className="card"><div className="card-heading"><div className="section-title"><span className="section-icon"><Icon name="activity"/></span><div><h2>Status layanan</h2><p>Koneksi dan kesiapan sistem</p></div></div><span className="refresh-meta"><Icon name="refresh"/>Setiap 30 detik</span></div>
      <div className="status-grid">{[["backend","Backend","server"],["postgresql","Database","database"],["redis","Redis","layers"],["zabbix","Zabbix","network"],["scheduler","Scheduler","calendar"]].map(([key,label,icon]) => {
        const value=services[key] || "checking",good=["connected","running"].includes(value),failed=["error","stopped"].includes(value);
        const captions:Record<string,string>={connected:"Terhubung",running:"Berjalan",starting:"Memulai",error:"Gangguan",stopped:"Berhenti",unknown:"Belum diketahui",checking:"Memeriksa…"};
        return <div className={`service ${good ? "service-good" : failed ? "service-error" : "service-warning"}`} key={key}><span className="service-icon"><Icon name={icon as IconName}/></span>
          <div className="service-details"><strong>{label}</strong><small>{captions[value] || value}</small></div><span className={`dot ${good ? "ok" : failed ? "error" : ""}`}/></div>;
      })}</div>
    </section>
    {error && <div className="alert error" role="alert">{error}</div>}
    {message && <div className={`alert ${partial ? "warning" : "success"}`} role="status">{message}</div>}
    <div className="grid-two">
      <section className="card report-config"><div className="card-heading"><div className="section-title"><span className="section-icon"><Icon name="sliders"/></span><div><h2>Konfigurasi laporan</h2><p>Host, periode, dan metrik</p></div></div><span className="panel-index">01</span></div><div className="form-grid">
        <label className="span-two"><span>Judul laporan</span><input value={title} maxLength={200} onChange={e => setTitle(e.target.value)} /></label>
        <label className="span-two"><span>Host</span><select value={hostId} onChange={e => {setError("");setHostId(e.target.value);}} disabled={loading}>
          <option value="">Pilih host</option>{hosts.map(h => <option key={h.hostid} value={h.hostid}>{h.name || h.host}</option>)}</select></label>
        <label><span>Mulai</span><input type="datetime-local" value={from} onChange={e => setFrom(e.target.value)} /></label>
        <label><span>Selesai</span><input type="datetime-local" value={to} onChange={e => setTo(e.target.value)} /></label>
      </div><p className="info-note">Waktu mengikuti timezone browser. Periode maksimal 90 hari.</p>
        <MetricPicker items={items} selected={selected} onChange={setSelected} loading={loadingItems} />
        <div className="actions"><button className="primary" onClick={generate} disabled={!selected.length || generating}>
          <Icon name="download"/>{generating ? "Membuat PDF…" : `Ekspor PDF (${selected.length} metrik)`}</button></div>
      </section>
      <section className="card chart-card"><div className="card-heading"><div className="section-title"><span className="section-icon"><Icon name="chart"/></span><div><h2>Pratinjau grafik</h2><p>Data metrik terpilih</p></div></div><span className="panel-index">02</span></div>
        <label><span>Metrik grafik</span><select value={metricId} onChange={e => setMetricId(e.target.value)} disabled={!selected.length}>
          <option value="">Pilih metrik</option>{items.filter(i => selected.includes(i.itemid)).map(i => <option key={i.itemid} value={i.itemid}>{i.name}</option>)}</select></label>
        <div className="actions"><button onClick={preview} disabled={!metricId || loadingChart}><Icon name="activity"/>{loadingChart ? "Memuat grafik…" : "Tampilkan grafik"}</button></div>
        {chart ? <Chart data={chart}/> : <div className="chart-empty"><span><Icon name="chart"/></span><strong>Pratinjau belum tersedia</strong><p>Pilih metrik dan tampilkan grafik untuk melihat data dan statistiknya.</p></div>}
      </section>
    </div>
    <section className="card"><div className="card-heading"><div className="section-title"><span className="section-icon"><Icon name="history"/></span><div><h2>Riwayat eksekusi terbaru</h2><p>Aktivitas laporan manual dan terjadwal</p></div></div><a href="/reports" className="history-link">Lihat semua riwayat<Icon name="arrow"/></a></div><HistoryTable rows={history} loading={false}/></section>
  </main>;
}
