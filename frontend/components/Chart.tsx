import {useId} from "react";
import type {MetricData} from "../lib/api";
import {number} from "../lib/api";

export default function Chart({data}: {data:MetricData}) {
  const fillId=`metric-fill-${useId().replace(/[^a-zA-Z0-9_-]/g,"")}`;
  if (!data.points.length) return <p className="empty">Tidak ada data pada periode ini. Pilih periode atau metrik lain.</p>;
  const low=data.summary.minimum ?? Math.min(...data.points.map(p=>p.value));
  const high=data.summary.maximum ?? Math.max(...data.points.map(p=>p.value));
  const pad=low===high ? Math.max(Math.abs(low)*.05,1) : 0;
  const minimum=low-pad,maximum=high+pad;
  const first=data.points[0].timestamp,last=data.points[data.points.length-1].timestamp;
  const span=Math.max(last-first,1);
  const points=data.points.filter((_,i)=>i%Math.max(Math.floor(data.points.length/1000),1)===0 || i===data.points.length-1);
  const coords=points.map(p=>[70+(p.timestamp-first)/span*650,230-(p.value-minimum)/(maximum-minimum)*205]);
  const path=coords.map(([x,y],i)=>`${i ? "L" : "M"}${x},${y}`).join(" ");
  const area=`${path} L${coords[coords.length-1][0]},230 L${coords[0][0]},230 Z`;
  return <><div className="chart-heading"><div><h3>{data.item.name}</h3><p className="muted">{data.item.units || "Tanpa unit"} · {data.source} · {data.points.length.toLocaleString("id-ID")} titik data</p></div><span className="badge success">Data tersedia</span></div>
    <div className="chart-scroll"><svg viewBox="0 0 740 280" role="img" aria-label={`Grafik ${data.item.name}`}>
      <title>{data.item.name}</title>
      <defs><linearGradient id={fillId} x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor="#3b82f6" stopOpacity=".18"/><stop offset="100%" stopColor="#3b82f6" stopOpacity=".01"/>
      </linearGradient></defs>
      {[0,1,2,3,4].map(tick=><g key={tick}><line x1="70" x2="720" y1={230-tick*51.25} y2={230-tick*51.25} stroke="var(--chart-grid)" strokeDasharray={tick===0 ? undefined : "4 5"}/>
        <text x="59" y={234-tick*51.25} textAnchor="end" fontSize="12" fill="var(--chart-label)">{number(minimum+(maximum-minimum)*tick/4)}</text></g>)}
      {coords.length>1 && <path d={area} fill={`url(#${fillId})`} stroke="none"/>}
      <path d={path} fill="none" stroke="#2563eb" strokeWidth="2.3" strokeLinecap="round" strokeLinejoin="round"/>
      {coords.length===1 && <circle cx={coords[0][0]} cy={coords[0][1]} r="4" fill="#2563eb"/>}
      <text x="70" y="261" fontSize="11" fill="var(--chart-label)">{new Date(first*1000).toLocaleString("id-ID")}</text>
      <text x="720" y="261" textAnchor="end" fontSize="11" fill="var(--chart-label)">{new Date(last*1000).toLocaleString("id-ID")}</text>
    </svg></div>
    <div className="stat-grid compact">{[["Minimum",data.summary.minimum],["Rata-rata",data.summary.average],["Maksimum",data.summary.maximum],["Sampel",data.summary.samples]].map(([label,value])=>
      <div key={String(label)}><span>{label}</span><strong>{number(value as number | null)}</strong></div>)}</div>
  </>;
}
