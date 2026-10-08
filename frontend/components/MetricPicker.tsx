"use client";
import { useState } from "react";
import type { Item } from "../lib/api";

export default function MetricPicker({items, selected, onChange, loading}: {
  items: Item[]; selected: string[]; onChange: (ids: string[]) => void; loading: boolean;
}) {
  const [search, setSearch] = useState("");
  const query = search.trim().toLowerCase();
  const filtered = items.filter(i =>
    `${i.name} ${i.key_} ${i.units} ${i.itemid}`.toLowerCase().includes(query),
  );
  return <fieldset className="metric-picker"><legend>Metrik <span className="muted">({selected.length}/20 dipilih)</span></legend>
    <input aria-label="Cari metrik" placeholder="Cari nama, key, ID, atau unit metrik…" value={search} onChange={e => setSearch(e.target.value)} />
    {loading ? <p role="status">Memuat metrik…</p> : !items.length ? <p className="empty">Pilih host yang memiliki metrik numerik aktif.</p> :
      <div className="metric-list">{filtered.map(i => <label key={i.itemid} className={selected.includes(i.itemid) ? "metric selected" : "metric"}>
        <input type="checkbox" checked={selected.includes(i.itemid)} disabled={!selected.includes(i.itemid) && selected.length >= 20}
          onChange={() => onChange(selected.includes(i.itemid) ? selected.filter(id => id !== i.itemid) : [...selected, i.itemid])} />
        <span>{i.name}<small>{i.units || "Tanpa unit"} · {i.key_}</small></span>
      </label>)}{!filtered.length && <p className="empty">Tidak ada metrik yang cocok.</p>}</div>}
  </fieldset>;
}
