import type { Metadata } from "next";
import Navigation from "../components/Navigation";
import "./globals.css";

export const metadata: Metadata = {title: "Zabbix Report Exporter", description: "Monitoring dan laporan Zabbix untuk tim operasional"};
export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) {
  return <html lang="id"><body><Navigation />{children}<footer className="site-footer">Zabbix Report Exporter · Internal monitoring workspace</footer></body></html>;
}
