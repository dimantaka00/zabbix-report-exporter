import type { MetricData } from "../lib/api";
import { number } from "../lib/api";

export default function Chart({data}: {data: MetricData}) {
  if (!data.points.length) return <p className="empty">Tidak ada data pada periode ini. Pilih periode atau metrik lain.</p>;
  const low = data.summary.minimum ?? Math.min(...data.points.map(p => p.value));
  const high = data.summary.maximum ?? Math.max(...data.points.map(p => p.value));
  const pad = low === high ? Math.max(Math.abs(low) * .05, 1) : 0;
  const minimum = low - pad, maximum = high + pad;
  const first = data.points[0].timestamp, last = data.points[data.points.length-1].timestamp;
  const span = Math.max(last-first, 1);
  const points = data.points.filter((_,i) => i % Math.max(Math.floor(data.points.length/1000),1) === 0 || i === data.points.length-1);
  const coords = points.map(p => [70+(p.timestamp-first)/span*810, 250-(p.value-minimum)/(maximum-minimum)*220]);
  const path = coords.map(([x,y],i) => `${i ? "L" : "M"}${x},${y}`).join(" ");
  return <><div className="chart-heading"><div><h3>{data.item.name}</h3><p className="muted">{data.item.units || "Tanpa unit"} · {data.source} · {data.points.length.toLocaleString("id-ID")} titik data</p></div><span className="badge success">Data tersedia</span></div>
    <div className="chart-scroll"><svg viewBox="0 0 920 300" role="img" aria-label={`Grafik ${data.item.name}`}>
      <title>{data.item.name}</title>
      {[0,1,2,3,4].map(tick => <g key={tick}><line x1="70" x2="880" y1={250-tick*55} y2={250-tick*55} stroke="#e2e8f0" />
        <text x="60" y={254-tick*55} textAnchor="end" fontSize="11" fill="#64748b">{number(minimum+(maximum-minimum)*tick/4)}</text></g>)}
      <path d={path} fill="none" stroke="#2563eb" strokeWidth="2" />
      {coords.length === 1 && <circle cx={coords[0][0]} cy={coords[0][1]} r="4" fill="#2563eb" />}
      <text x="70" y="285" fontSize="11" fill="#64748b">{new Date(first*1000).toLocaleString("id-ID")}</text>
      <text x="880" y="285" textAnchor="end" fontSize="11" fill="#64748b">{new Date(last*1000).toLocaleString("id-ID")}</text>
    </svg></div>
    <div className="stat-grid compact">{[["Minimum",data.summary.minimum],["Rata-rata",data.summary.average],["Maksimum",data.summary.maximum],["Sampel",data.summary.samples]].map(([label,value]) =>
      <div key={String(label)}><span>{label}</span><strong>{number(value as number | null)}</strong></div>)}</div>
  </>;
}
