"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

export default function Navigation() {
  const path = usePathname();
  return <header className="site-header"><div className="nav-inner">
    <Link href="/" className="brand"><span className="brand-mark">Z</span><span>Zabbix Reports<small>Monitoring & reporting</small></span></Link>
    <nav aria-label="Navigasi utama">
      {[["/", "Monitoring"], ["/schedules", "Jadwal"], ["/reports", "Laporan"]].map(([href,label]) =>
        <Link key={href} href={href} aria-current={path === href ? "page" : undefined}>{label}</Link>
      )}
    </nav>
    <span className="internal-tag">Internal workspace</span>
  </div></header>;
}
