import type {Metadata} from "next";
import AccessShell from "../components/AccessShell";
import {THEME_INIT_SCRIPT} from "../lib/theme";
import "./globals.css";

export const metadata: Metadata={title:"Zabbix Report Exporter",description:"Monitoring dan laporan Zabbix untuk tim operasional",icons:{icon:"/brand/kemensos.png"}};
export default function RootLayout({children}:Readonly<{children:React.ReactNode}>){
  return <html lang="id" data-theme="dark" suppressHydrationWarning><head>
    <script id="theme-init" dangerouslySetInnerHTML={{__html:THEME_INIT_SCRIPT}} />
  </head><body><AccessShell>{children}</AccessShell></body></html>;
}
