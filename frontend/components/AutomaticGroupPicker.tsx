"use client";
import {useEffect,useState} from "react";
import {api} from "../lib/api";

export type HostCategory="CS"|"TLK"|"ICON"|"HYP"|"MILES";
export type AutoHostGroup={category:HostCategory;zabbix_server:"primary"|"secondary";group_id:string};
type Group={zabbix_server:"primary"|"secondary";group_id:string;name:string;suggested_categories:HostCategory[]};
const CATEGORIES:HostCategory[]=["CS","TLK","ICON","HYP","MILES"];
const key=(g:AutoHostGroup)=>`${g.category}:${g.zabbix_server}:${g.group_id}`;

export default function AutomaticGroupPicker({source,categories,groups,onChange}:{source:string;categories:HostCategory[];groups:AutoHostGroup[];onChange:(categories:HostCategory[],groups:AutoHostGroup[])=>void}){
  const [catalog,setCatalog]=useState<Group[]>([]),[error,setError]=useState(""),[loading,setLoading]=useState(true),[open,setOpen]=useState<HostCategory|null>(null),[reload,setReload]=useState(0);
  useEffect(()=>{const controller=new AbortController();setLoading(true);setError("");
    api<Group[]>(`/auto-schedules/host-groups?zabbix_server=${source}`,{signal:controller.signal}).then(r=>setCatalog(r.data))
      .catch(e=>{if(e.name!=="AbortError"){setCatalog([]);setError(e.message);}}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});return()=>controller.abort();
  },[source,reload]);
  function candidates(category:HostCategory){return catalog.filter(g=>g.suggested_categories.includes(category));}
  function all(category:HostCategory){return candidates(category).map(g=>({category,zabbix_server:g.zabbix_server,group_id:g.group_id}));}
  function toggle(category:HostCategory){onChange(categories.includes(category)?categories.filter(c=>c!==category):[...categories,category],categories.includes(category)?groups.filter(g=>g.category!==category):[...groups,...all(category)]);}
  return <fieldset className="metric-picker"><legend>Host group Zabbix</legend>
    <p className="muted">CS memakai COMNET; TLK memakai TLK/TELKOM; HYP memakai HYP/Hypernet. Pilihan mengikuti keanggotaan host group Zabbix.</p>
    {loading?<p className="muted">Memuat host group…</p>:error?<p className="muted">{error} <button type="button" className="small-button" onClick={()=>setReload(reload+1)}>Muat ulang group</button></p>:null}
    <div className="form-grid">{CATEGORIES.map(category=><div key={category}><label className="metric"><input type="checkbox" aria-label={`Kategori ${category}`} checked={categories.includes(category)} disabled={loading} onChange={()=>toggle(category)}/><span>{category==="CS"?"CS (COMNET)":category}<small>{candidates(category).length} group tersedia · {groups.filter(g=>g.category===category).length} dipilih</small></span></label>{categories.includes(category)&&<button type="button" className="small-button" onClick={()=>setOpen(open===category?null:category)}>Atur group {category}</button>}</div>)}</div>
    {categories.filter(c=>!groups.some(g=>g.category===c)).map(c=><p key={c} className="warning-text">Pilih minimal satu group Zabbix untuk kategori {c}. {candidates(c).length?"Gunakan Atur group untuk memilih kembali.":"Group yang cocok belum tersedia pada sumber ini."}</p>)}
    {open&&categories.includes(open)&&<div className="auto-metric-editor"><div className="card-heading"><h3>Group untuk {open}</h3><button type="button" className="small-button" onClick={()=>onChange(categories,[...groups.filter(g=>g.category!==open),...all(open)])} disabled={loading||!candidates(open).length}>Pilih semua group {open}</button></div><div className="metric-list">{candidates(open).map(g=>{
      const entry={category:open,zabbix_server:g.zabbix_server,group_id:g.group_id};const selected=groups.some(s=>key(s)===key(entry));
      return <label className="metric" key={key(entry)}><input type="checkbox" checked={selected} aria-label={`Group ${open} ${g.name} ${g.zabbix_server==="primary"?"Zabbix 7":"Zabbix 2"}`} onChange={()=>onChange(categories,selected?groups.filter(s=>key(s)!==key(entry)):[...groups,entry])}/><span>{g.name}<small>{g.zabbix_server==="primary"?"Zabbix 7":"Zabbix 2"} · ID {g.group_id}</small></span></label>;
    })}{!candidates(open).length&&<p>Group tidak tersedia untuk kategori ini.</p>}</div></div>}
    {!categories.length&&<p className="muted">Tanpa kategori: seluruh host pada sumber dan status terpilih tetap tersedia.</p>}
  </fieldset>;
}
