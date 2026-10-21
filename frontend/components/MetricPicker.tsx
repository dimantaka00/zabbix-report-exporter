"use client";
import { useState } from "react";
import type { Item } from "../lib/api";

export default function MetricPicker({items, selected, onChange, loading, maxItems=20,searchLabel="Cari metrik",legendLabel="Metrik"}: {
  items: Item[]; selected: string[]; onChange: (ids: string[]) => void; loading: boolean;maxItems?:number;searchLabel?:string;legendLabel?:string;
}) {
  const [search, setSearch] = useState("");
  const query = search.trim().toLowerCase();
  const filtered = items.filter(i =>
    `${i.name} ${i.key_} ${i.units} ${i.itemid}`.toLowerCase().includes(query),
  );
  return <fieldset className="metric-picker"><legend>{legendLabel} <span className="muted">({selected.length}/{maxItems} dipilih)</span></legend>
    <input aria-label={searchLabel} placeholder="Cari nama, key, ID, atau unit metrik…" value={search} onChange={e => setSearch(e.target.value)} />
    {loading ? <p role="status">Memuat metrik…</p> : !items.length ? <p className="empty">Pilih host yang memiliki metrik numerik aktif.</p> :
      <div className="metric-list">{filtered.map(i => <label key={i.itemid} className={selected.includes(i.itemid) ? "metric selected" : "metric"}>
        <input type="checkbox" checked={selected.includes(i.itemid)} disabled={!selected.includes(i.itemid) && selected.length >= maxItems}
          onChange={() => onChange(selected.includes(i.itemid) ? selected.filter(id => id !== i.itemid) : [...selected, i.itemid])} />
        <span>{i.name}<small>{i.units || "Tanpa unit"} · {i.key_}</small></span>
      </label>)}{!filtered.length && <p className="empty">Tidak ada metrik yang cocok.</p>}</div>}
  </fieldset>;
}
