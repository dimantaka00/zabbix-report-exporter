import type {Metadata} from "next";
import Navigation from "../components/Navigation";
import {THEME_INIT_SCRIPT} from "../lib/theme";
import "./globals.css";

export const metadata: Metadata={title:"Zabbix Report Exporter",description:"Monitoring dan laporan Zabbix untuk tim operasional"};
export default function RootLayout({children}:Readonly<{children:React.ReactNode}>){
  return <html lang="id" data-theme="light" suppressHydrationWarning><head>
    <script id="theme-init" dangerouslySetInnerHTML={{__html:THEME_INIT_SCRIPT}} />
  </head><body><Navigation/><div className="workspace-content">{children}
    <footer className="site-footer"><span>Zabbix Report Exporter</span><span>Monitoring & laporan operasional IT</span>
      <span className="developer-credit">Developed by <strong>Daniel Christoper I.P</strong></span></footer>
  </div></body></html>;
}
