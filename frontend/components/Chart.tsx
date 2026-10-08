import {useId, useState} from "react";
import type {MetricData, Point} from "../lib/api";
import {displayUnit, metricNumber, isBandwidthUnit, conversionCaption} from "../lib/api";

type Day = {start: number; end: number; label: string; points: Point[]};

function dailySeries(data: MetricData): Day[] {
  const start = new Date((data.time_from ?? data.points[0].timestamp)*1000);
  start.setHours(0,0,0,0);
  const end = new Date((data.time_till ?? data.points[data.points.length-1].timestamp)*1000);
  const buckets = new Map<string, Point[]>();
  for (const point of data.points) {
    const key = new Date(point.timestamp*1000).toDateString();
    const bucket = buckets.get(key) || [];
    bucket.push(point); buckets.set(key,bucket);
  }
  const days: Day[] = [];
  while (start <= end) {
    const next = new Date(start); next.setDate(next.getDate()+1);
    days.push({start: start.getTime()/1000, end: next.getTime()/1000-1,
      label: start.toLocaleDateString("id-ID"), points: buckets.get(start.toDateString()) || []});
    start.setDate(start.getDate()+1);
  }
  return days;
}

function DayChart({data,day}: {data: MetricData; day: Day}) {
  const fillId=`metric-fill-${useId().replace(/[^a-zA-Z0-9_-]/g,"")}`;
  const [hovered,setHovered] = useState<Point | null>(null);
  const stats = day.points.reduce((value,point) => {
    const weight = Math.max(point.num ?? 1,1);
    return {minimum: Math.min(value.minimum,point.min ?? point.value),
      maximum: Math.max(value.maximum,point.max ?? point.value),
      total: value.total+point.value*weight, samples: value.samples+weight};
  }, {minimum: Infinity, maximum: -Infinity, total: 0, samples: 0});
  const low=stats.samples ? stats.minimum : 0, high=stats.samples ? stats.maximum : 1;
  const scale=displayUnit(data.item.units,Math.max(Math.abs(low),Math.abs(high)));
  const formatted=(value: number | null)=>{
    if (value === null) return "—";
    const valueScale=displayUnit(data.item.units,value);
    const converted=valueScale.factor<1 ? value/(1/valueScale.factor) : value*valueScale.factor;
    return `${metricNumber(converted,valueScale.unit)}${valueScale.unit ? ` ${valueScale.unit}` : ""}`;
  };
  const lastPoint=day.points[day.points.length-1];
  const last=lastPoint ? (lastPoint.last !== undefined ? lastPoint.last : lastPoint.value) : null;
  const pad=low===high ? Math.max(Math.abs(low)*.05,1) : 0;
  const minimum=low-pad,maximum=high+pad,span=Math.max(day.end-day.start,1);
  let points=day.points;
  if (points.length>2000) {
    const reduced: Point[]=[points[0]],size=Math.max(Math.floor(points.length/700),1);
    for (let i=0;i<points.length;i+=size) {
      const bucket=points.slice(i,i+size);
      reduced.push(...[bucket.reduce((a,b)=>a.value<b.value ? a : b),bucket.reduce((a,b)=>a.value>b.value ? a : b)]
        .sort((a,b)=>a.timestamp-b.timestamp));
    }
    reduced.push(points[points.length-1]); points=reduced;
  }
  const x=(point: Point)=>70+(point.timestamp-day.start)/span*650;
  const y=(value: number)=>230-(value-minimum)/(maximum-minimum)*205;
  const coords=points.map(point=>[x(point),y(point.value)]);
  const path=coords.map(([px,py],i)=>`${i ? "L" : "M"}${px},${py}`).join(" ");
  const area=coords.length ? `${path} L${coords[coords.length-1][0]},230 L${coords[0][0]},230 Z` : "";
  const time=(stamp: number)=>new Date(stamp*1000).toLocaleTimeString("id-ID",{hour:"2-digit",minute:"2-digit",hour12:false}).replace(".",":");
  return <section className="daily-chart">
    <div className="chart-heading"><div><h3>{data.item.name}</h3><p className="muted">{day.label} · 00:00–23:59 · {scale.unit || "Tanpa unit"} · {data.resolution === "minute" ? "Per menit" : data.source} · {day.points.length.toLocaleString("id-ID")} titik data</p></div></div>
    <div className="chart-scroll"><svg viewBox="0 0 740 280" role="img" aria-label={`Grafik ${data.item.name}`}
      onPointerLeave={()=>setHovered(null)} onPointerMove={event=>{
        if (!day.points.length) return;
        const rect=event.currentTarget.getBoundingClientRect();
        const stamp=day.start+((event.clientX-rect.left)/rect.width*740-70)/650*span;
        setHovered(day.points.reduce((a,b)=>Math.abs(a.timestamp-stamp)<Math.abs(b.timestamp-stamp) ? a : b));
      }}>
      <title>{data.item.name} — {day.label}, 00:00–23:59</title>
      <text x="70" y="16" fontSize="10" fill="var(--chart-label)">{scale.unit || "Nilai"}</text>
      <defs><linearGradient id={fillId} x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor="#3b82f6" stopOpacity=".18"/><stop offset="100%" stopColor="#3b82f6" stopOpacity=".01"/>
      </linearGradient></defs>
      {[0,1,2,3,4].map(tick=><g key={tick}><line x1="70" x2="720" y1={230-tick*51.25} y2={230-tick*51.25} stroke="var(--chart-grid)" strokeDasharray={tick===0 ? undefined : "4 5"}/>
        <text x="59" y={234-tick*51.25} textAnchor="end" fontSize="11" fill="var(--chart-label)">{metricNumber((minimum+(maximum-minimum)*tick/4)*scale.factor,scale.unit)}</text></g>)}
      {[0,3,6,9,12,15,18,21].map(hour=>{
        const stamp=new Date(day.start*1000); stamp.setHours(hour,0,0,0);
        const px=70+(stamp.getTime()/1000-day.start)/span*650;
        return <g key={hour}><line x1={px} x2={px} y1="25" y2="234" stroke="var(--chart-grid)"/>
          <text x={px} y="252" fontSize="10" textAnchor="middle" fill="var(--chart-label)">{String(hour).padStart(2,"0")}:00</text></g>;
      })}
      {coords.length>1 && <path d={area} fill={`url(#${fillId})`} stroke="none"/>}
      {points.filter(point=>point.min !== undefined && point.max !== undefined && point.min !== point.max).map((point,i)=>
        <line key={i} x1={x(point)} x2={x(point)} y1={y(point.min!)} y2={y(point.max!)} stroke="#93c5fd" strokeWidth="1"/>)}
      <path d={path} fill="none" stroke="#2563eb" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
      {coords.length===1 && <circle cx={coords[0][0]} cy={coords[0][1]} r="4" fill="#2563eb"/>}
      {!day.points.length && <text x="395" y="130" textAnchor="middle" fontSize="13" fill="var(--chart-label)">Tidak ada data pada hari ini</text>}
      {hovered && <g><line x1={x(hovered)} x2={x(hovered)} y1="25" y2="230" stroke="#2563eb" strokeDasharray="3 3"/>
        <circle cx={x(hovered)} cy={y(hovered.value)} r="4" fill="#2563eb"/></g>}
      <text x="720" y="252" textAnchor="end" fontSize="10" fill="var(--chart-label)">23:59</text>
      <text x="395" y="275" textAnchor="middle" fontSize="10" fill="var(--chart-label)">Waktu (HH:MM)</text>
    </svg></div>
    <p className="muted chart-detail">{hovered ? `${time(hovered.timestamp)} · ${formatted(hovered.value)} · ${hovered.num ?? 1} sampel` : "Arahkan kursor ke grafik untuk melihat waktu dan nilai sampel."}</p>
    <div className="table-wrap"><table aria-label="Statistik harian"><thead><tr><th>{isBandwidthUnit(data.item.units) ? "Interface Parameter" : "Parameter"}</th><th>Last</th><th>Min</th><th>Average</th><th>Max</th></tr></thead>
      <tbody><tr><td>{data.item.name}</td><td>{formatted(last)}</td><td>{formatted(stats.samples ? stats.minimum : null)}</td>
        <td>{formatted(stats.samples ? stats.total/stats.samples : null)}</td><td>{formatted(stats.samples ? stats.maximum : null)}</td></tr></tbody></table></div>
    {conversionCaption(data.item.units) && <p className="muted chart-detail">{conversionCaption(data.item.units)}</p>}
  </section>;
}

export default function Chart({data}: {data:MetricData}) {
  if (!data.points.length) return <p className="empty">{data.warning || "Tidak ada data pada periode ini. Pilih periode atau metrik lain."}</p>;
  return <>{dailySeries(data).map(day=><DayChart key={`${data.item.itemid}-${day.start}`} data={data} day={day}/>)}</>;
}
