"use client";
import Link from "next/link";
import {usePathname} from "next/navigation";
import Icon from "./Icon";
import ThemeToggle from "./ThemeToggle";
import type {IconName} from "./Icon";

const links: {href:string;label:string;icon:IconName;description:string}[] = [
  {href:"/",label:"Monitoring",icon:"monitor",description:"Dashboard operasional"},
  {href:"/schedules",label:"Jadwal",icon:"calendar",description:"Otomasi laporan"},
  {href:"/reports",label:"Laporan",icon:"file",description:"Arsip & riwayat"},
];

export default function Navigation() {
  const path=usePathname(),current=links.find(link=>link.href===path);
  return <>
    <header className="site-header"><div className="nav-inner">
      <Link href="/" className="brand"><span className="brand-mark"><img src="/brand/kemensos.png" alt="Logo Kementerian Sosial Republik Indonesia" width="40" height="43"/></span>
        <span>Zabbix Reports<small>PUSDATIN KEMENSOS</small></span></Link>
      <p className="nav-label">WORKSPACE</p>
      <nav aria-label="Navigasi utama">
        {links.map(({href,label,icon})=><Link key={href} href={href} aria-current={path===href?"page":undefined}>
          <Icon name={icon}/><span>{label}</span><span className="nav-active-dot"/></Link>)}
      </nav>
      <div className="nav-footer"><span className="environment-icon"><Icon name="shield"/></span>
        <div><strong>Workspace internal</strong><small>Monitoring jaringan & laporan</small></div></div>
    </div></header>
    <div className="workspace-bar"><div className="breadcrumb"><span>Workspace</span><span className="breadcrumb-separator">/</span><strong>{current?.description || "Zabbix Reports"}</strong></div>
      <div className="workspace-tools"><span className="workspace-label"><Icon name="shield"/>LAN internal</span><ThemeToggle/></div></div>
  </>;
}
