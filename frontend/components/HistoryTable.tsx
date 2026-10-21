import type { Execution } from "../lib/api";
import { dateTime } from "../lib/api";

export default function HistoryTable({rows, loading}: {rows: Execution[]; loading: boolean}) {
  if (loading && !rows.length) return <p role="status">Memuat riwayat…</p>;
  if (!rows.length) return <p className="empty">Belum ada eksekusi laporan.</p>;
  return <div className="table-wrap"><table><thead><tr><th>Waktu</th><th>Laporan / host</th><th>Asal</th><th>Status</th><th>PDF</th></tr></thead>
    <tbody>{rows.map(row => <tr key={row.id}>
      <td className="nowrap">{dateTime(row.started_at)}<small>{row.finished_at ? `Selesai ${dateTime(row.finished_at)}` : "Sedang diproses"}</small></td>
      <td>{row.schedule_name || "Laporan manual"}<small>{row.host_name || "—"}</small></td>
      <td>{row.trigger_type === "scheduled" ? "Terjadwal" : "Manual"}</td>
      <td><span className={`badge ${row.status.toLowerCase()}`}>{row.status}</span>
        {row.error_message && <small className="warning-text">{row.error_message}</small>}</td>
      <td>{row.report_filename ? <a href={`/api/v1/reports/${encodeURIComponent(row.report_filename)}`} target="_blank" rel="noreferrer">Unduh PDF ↗</a> : "—"}</td>
    </tr>)}</tbody></table></div>;
}
