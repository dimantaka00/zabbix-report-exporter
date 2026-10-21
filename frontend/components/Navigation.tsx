"use client";
import {branding} from "../lib/branding";
import Link from "next/link";
import {usePathname} from "next/navigation";
import Icon from "./Icon";
import ThemeToggle from "./ThemeToggle";
import type {IconName} from "./Icon";
import type {AccessUser} from "./AccessShell";

const links: {href:string;label:string;icon:IconName;description:string}[] = [
  {href:"/",label:"Monitoring",icon:"monitor",description:"Dashboard operasional"},
  {href:"/schedules",label:"Jadwal",icon:"calendar",description:"Otomasi laporan"},
  {href:"/reports",label:"Laporan",icon:"file",description:"Arsip & riwayat"},
];

export default function Navigation({user,onLogout}:{user:AccessUser|null;onLogout:()=>void}) {
  const available=user?.role==="admin"?[...links,{href:"/admin",label:"Akses admin",icon:"shield" as IconName,description:"Monitoring akses & akun"}]:links;
  const path=usePathname(),current=available.find(link=>link.href===path);
  return <>
    <header className="site-header"><div className="nav-inner">
      <Link href="/" className="brand" aria-label={branding.product} title={branding.organization}><span className="brand-mark"><img src={branding.logo} alt={branding.product} width="40" height="43"/></span>
        <span className="brand-copy">{branding.product}<small>{branding.organization}</small></span></Link>
      <p className="nav-label">WORKSPACE</p>
      <nav aria-label="Navigasi utama">
        {available.map(({href,label,icon})=><Link key={href} href={href} title={label} aria-label={label} aria-current={path===href?"page":undefined}>
          <Icon name={icon}/><span>{label}</span><span className="nav-active-dot"/></Link>)}
      </nav>
      <div className="nav-footer" title="Workspace internal — Monitoring jaringan & laporan"><span className="environment-icon"><Icon name="shield"/></span>
        <div><strong>Workspace internal</strong><small>Monitoring jaringan & laporan</small></div></div>
    </div></header>
    <div className="workspace-bar"><div className="breadcrumb"><span>Workspace</span><span className="breadcrumb-separator">/</span><strong>{current?.description || "Zabbix Reports"}</strong></div>
      <div className="workspace-tools">{user?<Link className="account-label" href="/password" title="Ganti password">{user.display_name}<small>{user.role}</small></Link>:<span className="workspace-label"><Icon name="shield"/>LAN internal</span>}<ThemeToggle/>{user&&<button className="small-button" onClick={onLogout}>Keluar</button>}</div></div>
  </>;
}
