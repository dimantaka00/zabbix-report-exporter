import {useState} from "react";
import {displayUnit,metricNumber,type MetricData,type Point} from "../lib/api";
import {chartUnit,combinedUnit,metricStyles,metricValue,statistics,combinedDays} from "../lib/combined";

type Day=ReturnType<typeof combinedDays>[number];
function DayChart({day}:{day:Day}){
  const [hovered,setHovered]=useState<number|null>(null);
  const styles=metricStyles(day.series.map(metric=>metric.item));
  const unit=combinedUnit(day.series.map(metric=>metric.item));
  const stats=day.series.map(metric=>statistics(metric.points));
  const factors=day.series.map(metric=>chartUnit(metric.item.units).factor);
  const lows=stats.flatMap((value,i)=>value.minimum===null?[]:[value.minimum*factors[i]]);
  const highs=stats.flatMap((value,i)=>value.maximum===null?[]:[value.maximum*factors[i]]);
  const low=Math.min(0,...lows),high=Math.max(0,...highs);
  const pad=low===high?Math.max(Math.abs(low)*.05,1):0;
  const minimum=low-pad,maximum=high+pad,span=Math.max(day.end-day.start,1);
  const scale=displayUnit(unit,Math.max(Math.abs(minimum),Math.abs(maximum)));
  const x=(stamp:number)=>70+(stamp-day.start)/span*650;
  const y=(value:number)=>230-(value-minimum)/(maximum-minimum)*205;
  const stampText=(stamp:number)=>new Date(stamp*1000).toLocaleTimeString("id-ID",{hour:"2-digit",minute:"2-digit",hour12:false}).replace(".",":");
  const nearest=(points:Point[])=>hovered===null || !points.length?null:
    points.reduce((a,b)=>Math.abs(a.timestamp-hovered)<=Math.abs(b.timestamp-hovered)?a:b);
  return <section className="daily-chart combined-chart">
    <div className="chart-heading"><div><h3>Grafik gabungan</h3><p className="muted">{day.label} · 00:00–23:59 · {scale.unit || "Tanpa unit"} · {day.series[0].resolution==="minute"?"Per menit":"Sesuai resolusi terpilih"}</p></div></div>
    <div className="combined-legend" aria-label="Legenda metrik">{day.series.map((metric,i)=><span key={metric.item.itemid} style={{color:styles[i].color}}>
      <svg width="24" height="10" aria-hidden="true"><line x1="0" x2="24" y1="5" y2="5" stroke="currentColor" strokeWidth="2" strokeDasharray={styles[i].dash}/></svg>
      {metric.item.name}{!metric.points.length && <small>Tanpa data pada hari ini</small>}</span>)}</div>
    {day.series.filter(metric=>metric.warning).map(metric=><p className="warning-text" key={metric.item.itemid}>{metric.item.name}: {metric.warning}</p>)}
    <div className="chart-scroll"><svg viewBox="0 0 740 280" role="img" aria-label="Grafik gabungan metrik"
      onPointerLeave={()=>setHovered(null)} onPointerMove={event=>{
        const rect=event.currentTarget.getBoundingClientRect();
        setHovered(Math.min(day.end,Math.max(day.start,day.start+((event.clientX-rect.left)/rect.width*740-70)/650*span)));
      }}>
      <title>Grafik gabungan — {day.label}, 00:00–23:59</title>
      <text x="70" y="16" fontSize="10" fill="var(--chart-label)">{scale.unit || "Nilai"}</text>
      {[0,1,2,3,4].map(tick=><g key={tick}><line x1="70" x2="720" y1={230-tick*51.25} y2={230-tick*51.25} stroke="var(--chart-grid)" strokeDasharray={tick===0?undefined:"4 5"}/>
        <text x="59" y={234-tick*51.25} textAnchor="end" fontSize="11" fill="var(--chart-label)">{metricNumber((minimum+(maximum-minimum)*tick/4)*scale.factor,scale.unit)}</text></g>)}
      {[0,3,6,9,12,15,18,21].map(hour=>{
        const stamp=new Date(day.start*1000);stamp.setHours(hour,0,0,0);const px=x(stamp.getTime()/1000);
        return <g key={hour}><line x1={px} x2={px} y1="25" y2="234" stroke="var(--chart-grid)"/>
          <text x={px} y="252" fontSize="10" textAnchor="middle" fill="var(--chart-label)">{String(hour).padStart(2,"0")}:00</text></g>;
      })}
      {day.series.map((metric,i)=>{
        let points=metric.points;
        if(points.length>2000){
          const reduced=[points[0]],size=Math.max(Math.floor(points.length/700),1);
          for(let n=0;n<points.length;n+=size){const bucket=points.slice(n,n+size);reduced.push(...[
            bucket.reduce((a,b)=>a.value<b.value?a:b),bucket.reduce((a,b)=>a.value>b.value?a:b)].sort((a,b)=>a.timestamp-b.timestamp));}
          reduced.push(points[points.length-1]);points=reduced;
        }
        const coords=points.map(point=>[x(point.timestamp),y(point.value*factors[i])]);
        const path=coords.map(([px,py],n)=>`${n?"L":"M"}${px},${py}`).join(" ");
        const area=coords.length?`${path} L${coords[coords.length-1][0]},230 L${coords[0][0]},230 Z`:"";
        return <g key={metric.item.itemid} data-metric-id={metric.item.itemid}>
          {coords.length>1 && <path d={area} fill={styles[i].color} fillOpacity=".07"/>}
          {points.filter(point=>point.min!==undefined && point.max!==undefined && point.min!==point.max).map((point,n)=><line key={n}
            x1={x(point.timestamp)} x2={x(point.timestamp)} y1={y(point.min!*factors[i])} y2={y(point.max!*factors[i])} stroke={styles[i].color} strokeOpacity=".3"/>)}
          <path d={path} fill="none" stroke={styles[i].color} strokeWidth="2" strokeDasharray={styles[i].dash} strokeLinejoin="round"/>
          {coords.length===1 && <circle cx={coords[0][0]} cy={coords[0][1]} r="4" fill={styles[i].color}/>}
        </g>;
      })}
      {!lows.length && <text x="395" y="130" textAnchor="middle" fontSize="13" fill="var(--chart-label)">Tidak ada data pada hari ini</text>}
      {hovered!==null && <line x1={x(hovered)} x2={x(hovered)} y1="25" y2="230" stroke="var(--chart-label)" strokeDasharray="3 3"/>}
      <text x="720" y="252" textAnchor="end" fontSize="10" fill="var(--chart-label)">23:59</text>
      <text x="395" y="275" textAnchor="middle" fontSize="10" fill="var(--chart-label)">Waktu (HH:MM)</text>
    </svg></div>
    <div className="combined-tooltip" aria-live="polite">{hovered===null?<p className="muted chart-detail">Arahkan kursor ke grafik untuk melihat nilai tiap metrik.</p>:
      day.series.map((metric,i)=>{const point=nearest(metric.points);return <p key={metric.item.itemid} style={{color:styles[i].color}}>
        {metric.item.name}: {point?`${stampText(point.timestamp)} · ${metricValue(point.value,metric.item.units)}`:"Tanpa data"}</p>;})}</div>
    <div className="table-wrap"><table aria-label="Statistik harian gabungan"><thead><tr><th>Parameter</th><th>Last</th><th>Min</th><th>Average</th><th>Max</th></tr></thead>
      <tbody>{day.series.map((metric,i)=><tr key={metric.item.itemid}><td style={{color:styles[i].color}}>{metric.item.name}</td>
        {[stats[i].last,stats[i].minimum,stats[i].average,stats[i].maximum].map((value,n)=><td key={n}>{metricValue(value,metric.item.units)}</td>)}</tr>)}</tbody></table></div>
  </section>;
}
export default function CombinedChart({data}:{data:MetricData[]}){
  return <>{combinedDays(data).map(day=><DayChart key={day.start} day={day}/>)}</>;
}
