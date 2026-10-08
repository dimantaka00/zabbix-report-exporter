"use client";

import {useEffect,useRef,useState} from "react";
import {api,durationText,durationDetail} from "../lib/api";
import type {DowntimeTrigger,HostDowntimeData,ZabbixServer} from "../lib/api";
import Icon from "./Icon";

type Props={hostId:string; serverId:ZabbixServer["id"]; from:string; to:string;
  triggerId:string; onTriggerChange:(id:string)=>void; includeInPdf:boolean; onIncludeChange:(include:boolean)=>void};
const labels={online:"Up",offline:"Down",unknown:"Unknown"};
function stamp(value:number | null) {
  return value === null ? "—" : new Date(value*1000).toLocaleString("en-GB",{
    year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",second:"2-digit",hour12:false,
  }).replace(/\./g,":");
}

export default function HostDowntime({hostId,serverId,from,to,triggerId,onTriggerChange,includeInPdf,onIncludeChange}:Props) {
  const [triggers,setTriggers]=useState<DowntimeTrigger[]>([]),[data,setData]=useState<HostDowntimeData | null>(null);
  const [loadingTriggers,setLoadingTriggers]=useState(false),[loading,setLoading]=useState(false),[error,setError]=useState("");
  const request=useRef<AbortController | null>(null);
  useEffect(()=>{
    setTriggers([]);setData(null);setError("");
    if (!hostId) {setLoadingTriggers(false);return;}
    const controller=new AbortController();setLoadingTriggers(true);
    api<DowntimeTrigger[]>(`/zabbix/hosts/${hostId}/downtime-triggers?server_id=${serverId}`,{signal:controller.signal})
      .then(result=>setTriggers(result.data)).catch(e=>{if(e.name!=="AbortError")setError(e.message);})
      .finally(()=>{if(!controller.signal.aborted)setLoadingTriggers(false);});
    return ()=>controller.abort();
  },[hostId,serverId]);
  useEffect(()=>{request.current?.abort();setLoading(false);setData(null);},[hostId,serverId,from,to,triggerId]);
  useEffect(()=>()=>request.current?.abort(),[]);
  async function load() {
    setError("");setLoading(true);
    const controller=new AbortController();request.current?.abort();request.current=controller;
    try {
      const start=Math.floor(new Date(from).getTime()/1000),end=Math.floor(new Date(to).getTime()/1000)+59;
      if (!Number.isFinite(start) || !Number.isFinite(end) || end<=start || end-start>90*86400) throw new Error("Select a valid period of up to 90 days.");
      const result=await api<HostDowntimeData>(`/zabbix/hosts/${hostId}/downtime?server_id=${serverId}&time_from=${start}&time_till=${end}${triggerId ? `&trigger_id=${triggerId}` : ""}`,{signal:controller.signal});
      if (!controller.signal.aborted)setData(result.data);
    } catch(e) {if(e instanceof Error && e.name!=="AbortError")setError(e.message);}
    finally {if(request.current===controller)setLoading(false);}
  }
  return <section className="card downtime-card">
    <div className="card-heading"><div className="section-title"><span className="section-icon"><Icon name="activity"/></span><div><h2>Downtime Report</h2><p>Outage start time, recovery time, and duration</p></div></div></div>
    {!hostId ? <p className="empty">Select a host to view its downtime history.</p> : <>
      <div className="form-grid"><label className="span-two"><span>Host-down trigger</span><select value={triggerId} onChange={e=>onTriggerChange(e.target.value)} disabled={loadingTriggers}>
        <option value="">Automatic (host-down trigger)</option>
        {triggers.map(trigger=><option key={trigger.triggerid} value={trigger.triggerid}>{trigger.name}{trigger.recommended ? " (host-down)" : ""}{trigger.status!=="0" ? " (disabled)" : ""}</option>)}
      </select></label></div>
      <label className="downtime-pdf-option"><input type="checkbox" checked={includeInPdf} onChange={e=>onIncludeChange(e.target.checked)}/> Include downtime in PDF</label>
      <div className="actions"><button onClick={load} disabled={loading || loadingTriggers}><Icon name="refresh"/>{loading ? "Loading downtime…" : "Show Downtime"}</button></div>
      {error && <p className="alert error" role="alert">{error}</p>}
      {data && <>
        {data.warning && <p className="alert warning">{data.warning}</p>}
        {data.status==="available" && <>
          <div className="downtime-summary"><p>Current status: <strong>{labels[data.current_status]}</strong></p><p>Status at period end: <strong>{labels[data.status_at_end]}</strong></p>
            <p>Downtime in period: <strong>{durationText(data.total_downtime_seconds)}</strong></p><p>Recorded events: <strong>{data.events.length}</strong></p></div>
          <p className="muted">Period: {stamp(data.time_from)} – {stamp(data.time_till)}</p>
          <div className="table-wrap"><table className="downtime-table" aria-label="Downtime history"><thead><tr><th>No</th><th>Status</th><th>Start Time</th><th>End Time</th><th>Duration</th></tr></thead>
            <tbody>{data.events.length ? data.events.map((event,index)=><tr key={event.event_id}><td>{index+1}</td><td>Down</td>
              <td className="nowrap">{stamp(event.start_time)}</td><td className="nowrap">{event.end_time!==null ? stamp(event.end_time) : event.status==="ongoing" ? "Ongoing" : "Unknown"}</td>
              <td className="nowrap"><span>{durationDetail(event.duration_seconds)}</span><small>{durationText(event.duration_seconds)}</small></td></tr>) :
              <tr><td>1</td><td>No Downtime</td><td>—</td><td>—</td><td>—</td></tr>}</tbody></table></div>
          {data.as_of && <p className="info-note">Updated: {stamp(data.as_of)}</p>}
          <p className="info-note">Times follow Zabbix problem and recovery events. Ongoing durations are calculated up to the update time. The total counts only the selected period, with overlaps counted once. No events means no recorded downtime; availability depends on event retention and read permissions.</p>
        </>}
      </>}
    </>}
  </section>;
}
