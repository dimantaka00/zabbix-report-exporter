"use client";
import {useEffect,useState} from "react";
import {api,type HostDetailsData} from "../lib/api";
import Icon from "./Icon";

const interfaceTypes:Record<string,string>={"1":"Agent","2":"SNMP","3":"IPMI","4":"JMX"};
const snmpVersions:Record<string,string>={"1":"SNMPv1","2":"SNMPv2c","3":"SNMPv3"};
const securityLevels:Record<string,string>={"0":"noAuthNoPriv","1":"authNoPriv","2":"authPriv"};

export default function HostDetails({hostId,serverId}:{hostId:string;serverId:string}){
  const [data,setData]=useState<HostDetailsData|null>(null);
  const [loading,setLoading]=useState(true),[error,setError]=useState("");
  const [retry,setRetry]=useState(0);
  useEffect(()=>{
    const controller=new AbortController();setData(null);setLoading(true);setError("");
    api<HostDetailsData>(`/zabbix/hosts/${hostId}/details?server_id=${serverId}`,{signal:controller.signal})
      .then(result=>{if(!controller.signal.aborted)setData(result.data);})
      .catch(e=>{if(!controller.signal.aborted)setError(e.message);})
      .finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    return ()=>controller.abort();
  },[hostId,serverId,retry]);
  const proxy=data?.proxy;
  const proxyLabel=!proxy?"":proxy.mode==="server"?"Zabbix server (tanpa proxy)":
    proxy.mode==="unknown"?"Tidak diketahui":`${proxy.mode==="proxy_group"?"Proxy group: ":""}${proxy.name || (proxy.id?`ID ${proxy.id}`:"Tidak tersedia")}`;
  return <details className="host-details span-two" open>
    <summary><Icon name="server"/><span>Detail host</span><span className="host-details-chevron">⌄</span></summary>
    <div className="host-details-content" role="region" aria-label="Detail host">
      {loading && <p className="muted" role="status">Memuat detail host…</p>}
      {error && <div className="alert error" role="alert">Detail host tidak dapat dimuat: {error}
        <button type="button" className="small-button" onClick={()=>setRetry(value=>value+1)}>Coba lagi</button></div>}
      {data && <>
        <p className="host-details-name"><strong>{data.name || data.host}</strong><small>{data.host}</small></p>
        <dl className="host-details-grid">
          <div><dt>Groups</dt><dd>{data.groups.length?<div className="host-detail-tags">{data.groups.map(group=><span key={group.groupid}>{group.name || `ID ${group.groupid}`}</span>)}</div>:"Tidak ada group"}</dd></div>
          <div><dt>Templates</dt><dd>{data.templates.length?<div className="host-detail-tags">{data.templates.map(template=><span key={template.templateid}>{template.name || `ID ${template.templateid}`}</span>)}</div>:"Tidak ada template tertaut"}</dd></div>
          <div className="span-two"><dt>Proxy</dt><dd>{proxyLabel}{proxy?.assigned_proxy && <small>Assigned proxy: {proxy.assigned_proxy.name || `ID ${proxy.assigned_proxy.id}`}</small>}</dd></div>
          <div className="span-two"><dt>Description</dt><dd className="host-description">{data.description || "Belum diisi di Zabbix"}</dd></div>
        </dl>
        <div className="table-wrap"><table aria-label="Interface host"><thead><tr><th>Type</th><th>IP address</th><th>DNS</th><th>Port</th><th>SNMP</th></tr></thead>
          <tbody>{data.interfaces.map(row=><tr key={row.interfaceid}>
            <td>{interfaceTypes[row.type] || `Type ${row.type}`}{row.main==="1" && <small>Default</small>}</td>
            <td>{row.ip || "—"}{row.useip==="1" && <small>Alamat polling</small>}</td>
            <td>{row.dns || "—"}{row.useip==="0" && <small>Alamat polling</small>}</td>
            <td>{row.port || "—"}</td>
            <td>{row.snmp?<>{snmpVersions[row.snmp.version] || "Versi tidak tersedia"}
              {row.snmp.bulk!=="" && <small>Bulk: {row.snmp.bulk==="1"?"Enabled":"Disabled"}</small>}
              {row.snmp.version==="3" && <small>{securityLevels[row.snmp.securitylevel] || "Security level tidak tersedia"}</small>}</>:"—"}</td>
          </tr>)}</tbody></table></div>
        {data.interfaces.length>0 && <p className="host-details-table-hint">Pada layar kecil, geser tabel untuk melihat semua kolom.</p>}
        {!data.interfaces.length && <p className="muted">Tidak ada interface yang dikonfigurasi pada host ini.</p>}
        {data.warnings.map(warning=><p className="warning-text" key={warning}>{warning}</p>)}
      </>}
    </div>
  </details>;
}
