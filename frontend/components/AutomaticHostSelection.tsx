"use client";
import {useEffect,useState} from "react";
import {api,numericItems} from "../lib/api";
import type {Host,Item,ZabbixServer} from "../lib/api";
import MetricPicker from "./MetricPicker";
import type {AutoHostGroup} from "./AutomaticGroupPicker";

export type AutoHostSelection={zabbix_server:ZabbixServer["id"];host_id:string;item_ids:string[]|null};
type CatalogHost=Host&{source:ZabbixServer["id"]};
const key=(host:AutoHostSelection)=>`${host.zabbix_server}:${host.host_id}`;

export default function AutomaticHostSelection({servers,source,status,value,onChange,groups=[],groupFilter=false}:{servers:ZabbixServer[];source:string;status:string;value:AutoHostSelection[];onChange:(value:AutoHostSelection[])=>void;groups?:AutoHostGroup[];groupFilter?:boolean}){
  const [hosts,setHosts]=useState<CatalogHost[]>([]),[loading,setLoading]=useState(false),[error,setError]=useState("");
  const [query,setQuery]=useState(""),[offset,setOffset]=useState(0),[expanded,setExpanded]=useState<string|null>(null);
  const [onlySelected,setOnlySelected]=useState(false);
  const [items,setItems]=useState<Item[]>([]),[itemsLoading,setItemsLoading]=useState(false);
  const groupKey=groups.map(g=>`${g.zabbix_server}:${g.group_id}`).sort().join(",");
  const configured=servers.filter(s=>s.configured&&(source==="all"||s.id===source)&&(!groupFilter||groups.some(g=>g.zabbix_server===s.id))).map(s=>s.id).join(",");
  useEffect(()=>{
    const controller=new AbortController();setHosts([]);setLoading(true);setError("");setOffset(0);
    const ids=configured.split(",").filter(Boolean) as ZabbixServer["id"][];
    Promise.all(ids.map(async id=>{const params=new URLSearchParams({server_id:id});if(groupFilter)Array.from(new Set(groups.filter(g=>g.zabbix_server===id).map(g=>g.group_id))).forEach(g=>params.append("group_ids",g));return (await api<Host[]>(`/zabbix/hosts?${params}`,{signal:controller.signal})).data.map(h=>({...h,source:id}));}))
      .then(r=>setHosts(r.flat().filter(h=>status==="all"||h.status===(status==="enabled"?"0":"1"))))
      .catch(e=>{if(e.name!=="AbortError")setError(e.message);}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    return()=>controller.abort();
  },[configured,status,groupKey,groupFilter]);
  useEffect(()=>{
    setItems([]);setError("");
    if(!expanded){setItemsLoading(false);return;}
    const [id,host]=expanded.split(":");const controller=new AbortController();setItemsLoading(true);
    api<Item[]>(`/zabbix/hosts/${host}/items?server_id=${id}`,{signal:controller.signal})
      .then(r=>setItems(numericItems(r.data))).catch(e=>{if(e.name!=="AbortError")setError(e.message);})
      .finally(()=>{if(!controller.signal.aborted)setItemsLoading(false);});
    return()=>controller.abort();
  },[expanded]);
  const chosen=new Set(value.map(key));
  const filtered=hosts.filter(h=>(!onlySelected||chosen.has(`${h.source}:${h.hostid}`))&&`${h.name} ${h.host} ${h.hostid} ${h.source}`.toLowerCase().includes(query.trim().toLowerCase()));
  const missing=!loading?value.filter(v=>!hosts.some(h=>`${h.source}:${h.hostid}`===key(v))):[];
  const selected=value.find(h=>key(h)===expanded);
  function changeItems(ids:string[]|null){if(selected)onChange(value.map(h=>key(h)===expanded?{...h,item_ids:ids}:h));}
  function toggle(h:CatalogHost){
    const entry={zabbix_server:h.source,host_id:h.hostid,item_ids:null};
    if(value.some(v=>key(v)===key(entry))){onChange(value.filter(v=>key(v)!==key(entry)));if(expanded===key(entry))setExpanded(null);}
    else onChange([...value,entry]);
  }
  return <fieldset className="metric-picker"><legend>Host & metrik otomatis <span className="muted">({value.length}/200 host dipilih)</span></legend>
    <input aria-label="Cari host otomatis" placeholder="Cari nama host, kode, atau ID…" value={query} onChange={e=>{setQuery(e.target.value);setOffset(0);}}/>
    <label className="metric"><input type="checkbox" checked={onlySelected} onChange={e=>{setOnlySelected(e.target.checked);setOffset(0);}}/><span>Hanya host yang sudah dipilih</span></label>
    {!!missing.length&&<p className="warning-text">{missing.length} host terpilih tidak tersedia pada cakupan ini. <button type="button" className="small-button" onClick={()=>{onChange(value.filter(v=>!missing.includes(v)));setExpanded(null);}}>Hapus pilihan host tidak tersedia</button></p>}
    {error&&<p className="alert error" role="alert">{error}</p>}
    {loading?<p role="status">Memuat pilihan host otomatis…</p>:<div className="metric-list">{filtered.slice(offset,offset+50).map(h=>{
      const selection=value.find(v=>v.zabbix_server===h.source&&v.host_id===h.hostid);
      const label=`${h.name||h.host} · ${h.source==="primary"?"Zabbix 7":"Zabbix 2"}`;
      return <div key={`${h.source}:${h.hostid}`} className="auto-host-row"><label className="metric"><input type="checkbox" aria-label={`Pilih host otomatis ${label}`} checked={!!selection} disabled={!selection&&value.length>=200} onChange={()=>toggle(h)}/><span>{label}<small>{h.status==="0"?"Aktif":"Nonaktif"} · {selection?.item_ids?`${selection.item_ids.length} metrik terpilih`:"Semua metrik numerik aktif"}</small></span></label>
        {selection&&<button type="button" className="small-button" onClick={()=>setExpanded(key(selection))}>Atur metrik {label}</button>}
      </div>;
    })}{!filtered.length&&<p className="empty">Tidak ada host yang cocok.</p>}</div>}
    <div className="actions"><button type="button" disabled={loading||offset===0} onClick={()=>setOffset(Math.max(0,offset-50))}>Pilihan host sebelumnya</button><small>{filtered.length} host tersedia</small><button type="button" disabled={loading||offset+50>=filtered.length} onClick={()=>setOffset(offset+50)}>Pilihan host berikutnya</button></div>
    {selected&&<div className="auto-metric-editor"><div className="card-heading"><h3>Metrik untuk {hosts.find(h=>`${h.source}:${h.hostid}`===expanded)?.name||selected.host_id}</h3><button type="button" onClick={()=>setExpanded(null)}>Tutup pilihan metrik</button></div>
      <label><span>Cakupan metrik host otomatis</span><select value={selected.item_ids===null?"all":"selected"} onChange={e=>changeItems(e.target.value==="all"?null:[])}><option value="all">Semua metrik numerik aktif</option><option value="selected">Pilih metrik tertentu</option></select></label>
      {selected.item_ids!==null?<><MetricPicker items={items} selected={selected.item_ids} onChange={changeItems} loading={itemsLoading} maxItems={5000} searchLabel="Cari metrik otomatis" legendLabel="Metrik otomatis"/>{!selected.item_ids.length&&<p className="warning-text">Pilih minimal satu metrik untuk host ini sebelum menyimpan.</p>}</>:<p className="muted">Seluruh metrik numerik aktif host ini dibaca setiap hari saat pemrosesan dimulai.</p>}
    </div>}
    <p className="muted">Atur metrik per host. Host dari Zabbix 7 dan Zabbix 2 tetap dibedakan walaupun ID-nya sama.</p>
  </fieldset>;
}
