import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Zabbix Report Exporter',
  description: 'Monitoring dan export laporan Zabbix',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="id">
      <body>{children}</body>
    </html>
  )
}
