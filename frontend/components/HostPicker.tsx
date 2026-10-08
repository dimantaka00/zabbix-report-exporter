import {useState} from "react";
import type {Host} from "../lib/api";

const statuses=[{value:"0",label:"Enabled",className:"success"},
  {value:"1",label:"Disabled",className:"disabled"}];
function statusOf(host:Host) {
  return statuses.find(status=>status.value===String(host.status)) ||
    {value:String(host.status),label:"Unknown",className:"partial"};
}

export default function HostPicker({hosts,value,onChange,search,onSearchChange,loading,required=false}: {
  hosts:Host[];value:string;onChange:(value:string)=>void;search:string;
  onSearchChange:(value:string)=>void;loading:boolean;required?:boolean;
}) {
  const [filter,setFilter]=useState("all");
  const query=search.trim().toLowerCase();
  const matching=hosts.filter(host=>(filter==="all" || String(host.status)===filter) &&
    `${host.name} ${host.host}`.toLowerCase().includes(query));
  const selected=hosts.find(host=>host.hostid===value);
  const keepSelected=selected && !matching.some(host=>host.hostid===value);
  const selectedStatus=selected && statusOf(selected);
  const groups=[...statuses,{value:"unknown",label:"Unknown",className:"partial"}];
  return <div className="span-two host-picker">
    {!loading && <div className="host-status-summary" aria-label="Ringkasan status host">
      <span className="host-total">Total: {hosts.length.toLocaleString("id-ID")}</span>
      {statuses.map(status=><span key={status.value} className={`badge ${status.className}`}>
        {status.label}: {hosts.filter(host=>String(host.status)===status.value).length.toLocaleString("id-ID")}
      </span>)}
    </div>}
    <div className="form-grid">
      <label><span>Cari host</span><input placeholder="Ketik nama atau kode host…" value={search}
        onChange={event=>onSearchChange(event.target.value)} /></label>
      <label><span>Status host</span><select value={filter} disabled={loading}
        onChange={event=>setFilter(event.target.value)}>
        <option value="all">Semua status</option><option value="0">Enabled</option><option value="1">Disabled</option>
      </select></label>
      <label className="span-two"><span>Host</span><select aria-label="Host" required={required} value={value} disabled={loading}
        onChange={event=>onChange(event.target.value)}>
        <option value="">Pilih host</option>
        {keepSelected && <optgroup label="Host terpilih">
          <option value={selected.hostid}>{selected.name || selected.host} — {selectedStatus?.label}</option>
        </optgroup>}
        {groups.map(group=>{
          const rows=matching.filter(host=>group.value==="unknown"
            ? !statuses.some(status=>status.value===String(host.status)) : String(host.status)===group.value);
          return rows.length ? <optgroup key={group.value} label={`${group.label} (${rows.length})`}>
            {rows.map(host=><option key={host.hostid} value={host.hostid}>
              {host.name || host.host} — {group.label}
            </option>)}
          </optgroup> : null;
        })}
      </select>
        {loading && <small>Memuat host…</small>}
        {!loading && !matching.length && <small>Tidak ada host yang cocok dengan pencarian dan status.</small>}
      </label>
    </div>
    {selected && selectedStatus && <div className="host-selection-status" aria-label="Status host terpilih">
      <span className={`badge ${selectedStatus.className}`}>{selectedStatus.label}</span>
      <span>{selectedStatus.value==="1"
        ? "Monitoring dinonaktifkan di Zabbix. Laporan memakai data historis yang masih tersedia."
        : selectedStatus.value==="0" ? "Monitoring diaktifkan di Zabbix." : "Status monitoring belum diketahui."}</span>
      {keepSelected && <small>Host terpilih tetap ditampilkan meskipun tidak cocok dengan filter.</small>}
    </div>}
  </div>;
}
