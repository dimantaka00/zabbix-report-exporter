export type Host = { hostid: string; host: string; name: string; status: string };
export type HostDetailsData = Host & {
  description:string;
  groups:{groupid:string;name:string}[];
  templates:{templateid:string;name:string}[];
  interfaces:{interfaceid:string;type:string;main:string;ip:string;dns:string;useip:string;port:string;available:string;
    snmp:{version:string;bulk:string;securitylevel:string} | null}[];
  proxy:{mode:"server"|"proxy"|"proxy_group"|"unknown";id:string|null;name:string|null;assigned_proxy:{id:string;name:string|null}|null};
  warnings:string[];
};
export type ZabbixServer = { id: "primary" | "secondary"; name: string; configured: boolean };
export type Item = { itemid: string; hostid?: string; name: string; key_: string; units: string; value_type: string; status: string };
export type Schedule = {
  id: number; name: string; zabbix_server: "primary" | "secondary"; host_id: string; host_name: string; item_ids: string[];
  hour: number; minute: number; timezone: string; enabled: boolean;
  last_run_date: string | null; next_retry_at: string | null; last_error: string | null;
};
export type Execution = {
  id: number; schedule_id: number | null; schedule_name: string | null; host_name: string | null;
  started_at: string; finished_at: string | null; status: "RUNNING" | "SUCCESS" | "PARTIAL" | "FAILED";
  report_filename: string | null; error_message: string | null; trigger_type: string;
};
export type Point = { timestamp: number; value: number; min?: number; max?: number; num?: number; last?: number | null; ns?: number };
export type MetricData = {
  item: Item; source: string; points: Point[];
  time_from?: number; time_till?: number; resolution?: "minute" | "hourly" | "auto"; warning?: string;
  summary: { minimum: number | null; maximum: number | null; average: number | null; samples: number; last?: number | null };
};

export type DowntimeTrigger = {triggerid:string; name:string; value:string; status:string; state:string; recommended:boolean};
export type HostDowntimeData = {
  host:Host; trigger:DowntimeTrigger | null; status:"available" | "unconfigured" | "unavailable";
  current_status:"online" | "offline" | "unknown"; status_at_end:"online" | "offline" | "unknown";
  time_from:number; time_till:number; as_of?:number; warning?:string | null; total_downtime_seconds:number | null;
  events:{event_id:string; status:"recovered" | "ongoing" | "unknown"; start_time:number; end_time:number | null;
    duration_seconds:number | null; period_duration_seconds:number | null}[];
};

export function durationText(value:number | null):string {
  if (value === null) return "—";
  const total=Math.max(Math.floor(value),0),days=Math.floor(total/86400);
  const clock=[Math.floor(total%86400/3600),Math.floor(total%3600/60),total%60].map(n=>String(n).padStart(2,"0")).join(":");
  return `${days ? `${days} d ` : ""}${clock}`;
}

export function durationDetail(value:number | null):string {
  if(value===null)return "—";
  const total=Math.max(Math.floor(value),0);
  const parts:[[number,string],[number,string],[number,string],[number,string]]=[
    [Math.floor(total/86400),"d"],[Math.floor(total%86400/3600),"h"],[Math.floor(total%3600/60),"m"],[total%60,"s"]];
  return parts.filter(([amount])=>amount>0).map(([amount,unit])=>`${amount} ${unit}`).join(" ") || "0 s";
}

export function downloadFilename(disposition: string, fallback: string): string {
  // Unicode names are sent by FileResponse using the encoded filename* parameter.
  const encoded = /filename\*\s*=\s*UTF-8'[^']*'([^;]+)/i.exec(disposition)?.[1];
  if (encoded) {
    try { return decodeURIComponent(encoded.trim()); } catch { /* Use the plain filename or fallback. */ }
  }
  return /filename\s*=\s*(?:"([^"]+)"|([^;]+))/i.exec(disposition)?.slice(1).find(Boolean)?.trim() || fallback;
}

export async function responseError(response: Response): Promise<Error> {
  let message = `Permintaan gagal (HTTP ${response.status}).`;
  try {
    const body = await response.json();
    if (typeof body.detail === "string") message = body.detail;
    else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg: string }) => d.msg.replace(/^Value error, /, "")).join(" ");
  } catch { /* HTTP errors may have a non-JSON body. */ }
  return new Error(message);
}

let csrfToken="";
export function setCsrfToken(value:string){csrfToken=value;}
export function getCsrfToken(){return csrfToken;}

export async function api<T>(path: string, options: RequestInit = {}): Promise<{data: T; total?: number}> {
  const response = await fetch(`/api/v1${path}`, {
    cache: "no-store", ...options,
    headers: { "Content-Type": "application/json", "X-CSRF-Token":csrfToken, ...options.headers },
  });
  if (!response.ok) {
    if(response.status===401&&typeof window!=="undefined"&&window.location.pathname!=="/login")window.location.assign("/login");
    throw await responseError(response);
  }
  const result = await response.json();
  if (!result.success) throw new Error("Respons layanan tidak valid.");
  return result;
}

export function numericItems(items: Item[]) {
  return items.filter(i => i.status === "0" && ["0", "3"].includes(i.value_type));
}
export function dateTime(value: string | null) {
  return value ? new Date(value).toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" }) : "—";
}
export function localInput(date: Date) {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}
export function number(value: number | null) {
  return value === null ? "—" : value.toLocaleString("id-ID", {maximumFractionDigits: 3});
}

const bitRates: Record<string,number> = {
    bps:1, "b/s":1, "bit/s":1, "bits/s":1, kbps:1000, Kbps:1000,
    mbps:1000000, Mbps:1000000, gbps:1000000000, Gbps:1000000000, tbps:1000000000000, Tbps:1000000000000,
    "kb/s":1000, "Kb/s":1000, "kbit/s":1000, "Mb/s":1000000, "Mbit/s":1000000,
    "Gb/s":1000000000, "Gbit/s":1000000000, "Tb/s":1000000000000, "Tbit/s":1000000000000,
};
const byteRates: Record<string,number> = Object.fromEntries([
  ...["Bps","KBps","MBps","GBps","TBps"].map((label,power)=>[label,1024**power]),
  ...["B/s","KB/s","MB/s","GB/s","TB/s"].map((label,power)=>[label,1024**power]),
]);
const bitSizes: Record<string,number> = {b:1,Kb:1000,kb:1000,Mb:1e6,mb:1e6,Gb:1e9,gb:1e9,Tb:1e12,tb:1e12};
const byteSizes: Record<string,number> = {B:1,KB:1024,kB:1024,MB:1024**2,GB:1024**3,TB:1024**4};
const unitGroups = [
  {sources:bitRates,step:1000,labels:["bps","Kbps","Mbps","Gbps","Tbps"]},
  {sources:byteRates,step:1024,labels:["Bps","KBps","MBps","GBps","TBps"]},
  {sources:bitSizes,step:1000,labels:["b","Kb","Mb","Gb","Tb"]},
  {sources:byteSizes,step:1024,labels:["B","KB","MB","GB","TB"]},
];
function unitGroup(units:string) {
  return unitGroups.find(group=>Object.hasOwn(group.sources,units.trim()));
}
export function isBandwidthUnit(units:string):boolean {
  return Object.hasOwn(bitRates,units.trim()) || Object.hasOwn(byteRates,units.trim());
}
export function conversionCaption(units:string):string {
  const first=unitGroup(units)?.labels[0];
  if(first==="bps")return "Bandwidth: 1 Kbps = 1,000 bps; 1 Mbps = 1,000 Kbps. Lowercase b denotes bits.";
  if(first==="Bps")return "Byte rate: 1 KBps = 1,024 Bps; 1 MBps = 1,024 KBps, following Zabbix. Uppercase B denotes bytes.";
  if(first==="b")return "Data size: 1 Kb = 1,000 bits; 1 Mb = 1,000 Kb. This unit measures size, not bits per second.";
  if(first==="B")return "Data size: 1 KB = 1,024 bytes; 1 MB = 1,024 KB, following Zabbix. Uppercase B denotes bytes.";
  return "";
}
export function displayUnit(units: string, peak: number): {factor: number; unit: string} {
  const source=units.trim(),group=unitGroup(source);
  if(!group)return {factor:1,unit:source};
  const base=group.sources[source];
  const bps=Math.abs(peak)*base;
  for(let power=group.labels.length-1;power>=0;power--) {
    const target=group.step**power,unit=group.labels[power];
    if (bps>=target || target===1) return {factor:base/target,unit};
  }
  return {factor:1,unit:source};
}

export function metricNumber(value: number | null, unit=""): string {
  const options = unitGroup(unit)
    ? {minimumFractionDigits:2,maximumFractionDigits:2} : {maximumFractionDigits:6};
  return value === null ? "—" : value.toLocaleString("id-ID",options);
}
