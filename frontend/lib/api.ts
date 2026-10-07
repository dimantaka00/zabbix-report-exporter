export type Host = { hostid: string; host: string; name: string; status: string };
export type Item = { itemid: string; hostid?: string; name: string; key_: string; units: string; value_type: string; status: string };
export type Schedule = {
  id: number; name: string; host_id: string; host_name: string; item_ids: string[];
  hour: number; minute: number; timezone: string; enabled: boolean;
  last_run_date: string | null; next_retry_at: string | null; last_error: string | null;
};
export type Execution = {
  id: number; schedule_id: number | null; schedule_name: string | null; host_name: string | null;
  started_at: string; finished_at: string | null; status: "RUNNING" | "SUCCESS" | "PARTIAL" | "FAILED";
  report_filename: string | null; error_message: string | null; trigger_type: string;
};
export type Point = { timestamp: number; value: number; min?: number; max?: number; num?: number };
export type MetricData = {
  item: Item; source: string; points: Point[];
  summary: { minimum: number | null; maximum: number | null; average: number | null; samples: number };
};

export async function responseError(response: Response): Promise<Error> {
  let message = `Permintaan gagal (HTTP ${response.status}).`;
  try {
    const body = await response.json();
    if (typeof body.detail === "string") message = body.detail;
    else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg: string }) => d.msg.replace(/^Value error, /, "")).join(" ");
  } catch { /* HTTP errors may have a non-JSON body. */ }
  return new Error(message);
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<{data: T; total?: number}> {
  const response = await fetch(`/api/v1${path}`, {
    cache: "no-store", ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  if (!response.ok) throw await responseError(response);
  const result = await response.json();
  if (!result.success) throw new Error("Respons layanan tidak valid.");
  return result;
}

export function numericItems(items: Item[]) {
  return items.filter(i => i.status === "0" && ["0", "3"].includes(i.value_type));
}
export function dateTime(value: string | null) {
  return value ? new Date(value).toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" }) : "—";
}
export function localInput(date: Date) {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}
export function number(value: number | null) {
  return value === null ? "—" : value.toLocaleString("id-ID", {maximumFractionDigits: 3});
}
