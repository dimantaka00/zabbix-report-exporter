import {displayUnit,metricNumber,type Item,type MetricData,type Point} from "./api";

export function chartUnit(units:string):{unit:string;factor:number}{
  const scale=displayUnit(units,0);
  if(scale.unit==="Bps")return {unit:"bps",factor:scale.factor*8};
  if(scale.unit==="B")return {unit:"b",factor:scale.factor*8};
  return scale;
}

export function combinedUnit(items:Item[]):string{
  const units=new Set(items.map(item=>chartUnit(item.units).unit));
  if(units.size>1)throw new Error("Grafik gabungan membutuhkan metrik dengan satuan sejenis. Pisahkan bandwidth, ukuran data, dan persentase.");
  return [...units][0] || "";
}

export function metricStyles(items:Item[]){
  let incoming=0,outgoing=0,other=0;
  return items.map(item=>{
    const label=`${item.key_ || ""} ${item.name}`;
    let color:string,index:number;
    if(/net\.if\.out|bits sent|bytes sent|outgoing|transmit/i.test(label)){
      color="var(--combined-sent)";index=outgoing++;
    }else if(/net\.if\.in|bits received|bytes received|incoming|receive/i.test(label)){
      color="var(--combined-received)";index=incoming++;
    }else{
      color=`var(--combined-color-${other%6})`;index=Math.floor(other++/6);
    }
    return {color,dash:[undefined,"6 3","2 3"][index%3]};
  });
}

export function metricValue(value:number|null,units:string){
  if(value===null)return "—";
  const scale=displayUnit(units,value);
  const converted=scale.factor<1?value/(1/scale.factor):value*scale.factor;
  return `${metricNumber(converted,scale.unit)}${scale.unit?` ${scale.unit}`:""}`;
}

export function statistics(points:Point[]){
  if(!points.length)return {minimum:null,maximum:null,average:null,last:null};
  const weights=points.map(point=>Math.max(point.num ?? 1,1));
  const final=points.reduce((a,b)=>b.timestamp>a.timestamp || (b.timestamp===a.timestamp && (b.ns ?? 0)>=(a.ns ?? 0))?b:a);
  return {minimum:Math.min(...points.map(point=>point.min ?? point.value)),
    maximum:Math.max(...points.map(point=>point.max ?? point.value)),
    average:points.reduce((sum,point,i)=>sum+point.value*weights[i],0)/weights.reduce((a,b)=>a+b,0),
    last:final.last!==undefined?final.last:final.value};
}

export function combinedDays(data:MetricData[]){
  const first=data[0];
  if(!first)return [];
  const start=new Date((first.time_from ?? first.points[0]?.timestamp ?? 0)*1000);start.setHours(0,0,0,0);
  const end=(first.time_till ?? first.points[first.points.length-1]?.timestamp ?? 0)*1000;
  const buckets=data.map(metric=>{
    const map=new Map<string,Point[]>();
    for(const point of metric.points){
      const key=new Date(point.timestamp*1000).toDateString();
      const bucket=map.get(key) || [];bucket.push(point);map.set(key,bucket);
    }
    return map;
  });
  const days=[];
  while(start.getTime()<=end){
    const next=new Date(start);next.setDate(next.getDate()+1);
    days.push({start:start.getTime()/1000,end:next.getTime()/1000-1,label:start.toLocaleDateString("id-ID"),
      series:data.map((metric,i)=>({...metric,points:(buckets[i].get(start.toDateString()) || []).toSorted((a,b)=>a.timestamp-b.timestamp)}))});
    start.setDate(start.getDate()+1);
  }
  return days;
}
