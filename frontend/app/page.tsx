"use client";



import { useEffect, useMemo, useState } from "react";



type Host = {

  hostid: string;

  host: string;

  name: string;

  status: string;

};



type Item = {

  itemid: string;

  name: string;

  key_: string;

  value_type: string;

  units: string;

  status: string;

  history: string;

  trends: string;

};



type Point = {

  timestamp: number;

  value: number;

  min?: number;

  max?: number;

};



type ItemDataResponse = {

  success: boolean;

  data: {

    item: Item;

    source: "history" | "trend";

    time_from: number;

    time_till: number;

    points: Point[];

  };

};



type ExecutionHistory = {
  id: number;
  schedule_id: number| null;
  schedule_name: string | null;
  host_name: string | null;
  started_at: string;
  finished_at: string | null;
  status: "RUNNING" | "SUCCESS" | "FAILED";
  report_filename: string | null;
  error_message: string | null;
};


function localDateTimeValue(date: Date): string {

  const pad = (value: number) => String(value).padStart(2, "0");



  return (

    `${date.getFullYear()}-` +

    `${pad(date.getMonth() + 1)}-` +

    `${pad(date.getDate())}T` +

    `${pad(date.getHours())}:` +

    `${pad(date.getMinutes())}`

  );

}



function formatDateTime(
  value: string | null
): string {
  if (!value) {
    return "-";
  }

  return new Date(value).toLocaleString(
    "id-ID",
    {
      dateStyle: "medium",
      timeStyle: "medium",
    }
  );
}

export default function Home() {

  const [hosts, setHosts] = useState<Host[]>([]);

  const [items, setItems] = useState<Item[]>([]);



  const [selectedHostId, setSelectedHostId] = useState("");

  const [selectedItemId, setSelectedItemId] = useState("");



  const [from, setFrom] = useState("");

  const [to, setTo] = useState("");



  const [chartData, setChartData] =

    useState<ItemDataResponse["data"] | null>(null);



  const [loadingHosts, setLoadingHosts] = useState(true);

  const [loadingItems, setLoadingItems] = useState(false);

  const [loadingChart, setLoadingChart] = useState(false);



  const [history, setHistory] = useState<ExecutionHistory[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(true);

  const [error, setError] = useState("");
  
  type DashboardSummary = {

    total_schedules: number;

    active_schedules: number;

    total_reports: number;

  };



  const [dashboard, setDashboard] =

    useState<DashboardSummary | null>(null);



  const [loadingDashboard, setLoadingDashboard] =

    useState(true);






  useEffect(() => {

    const now = new Date();

    const yesterday = new Date(

      now.getTime() - 24 * 60 * 60 * 1000

    );



    setFrom(localDateTimeValue(yesterday));

    setTo(localDateTimeValue(now));



    loadHosts();
    loadDashboard();
    loadHistory();

  }, []);


  async function loadHistory() {
  try {
    setLoadingHistory(true);

    const response = await fetch("/api/v1/history", {
      cache: "no-store",
    });

    const json = await response.json();

    if (!response.ok || !json.success) {
      throw new Error(
        json.detail || "Gagal mengambil execution history."
      );
    }

    setHistory(json.data || []);
  } catch (err) {
    console.error("History error:", err);
  } finally {
    setLoadingHistory(false);
  }
}

  async function loadDashboard() {

  try {

    setLoadingDashboard(true);



    const response = await fetch(

      "/api/v1/dashboard/summary"

    );



    const json = await response.json();



    if (!response.ok || !json.success) {

      throw new Error(

        json.detail ||

          "Gagal mengambil statistik dashboard."

      );

    }



    setDashboard(json.data);

  } catch (err) {

    console.error(

      "Dashboard error:",

      err

    );

  } finally {

    setLoadingDashboard(false);

  }

}async function loadHosts() {

    try {

      setLoadingHosts(true);

      setError("");



      const response = await fetch("/api/v1/zabbix/hosts");



      const json = await response.json();



      if (!response.ok || !json.success) {

        throw new Error(

          json.detail || "Gagal mengambil daftar host."

        );

      }



      setHosts(json.data ?? []);



      if (json.data?.length > 0) {

        setSelectedHostId(json.data[0].hostid);

      }

    } catch (err) {

      setError(

        err instanceof Error

          ? err.message

          : "Gagal mengambil host."

      );

    } finally {

      setLoadingHosts(false);

    }

  }



  useEffect(() => {

    if (!selectedHostId) {

      setItems([]);

      setSelectedItemId("");

      return;

    }



    loadItems(selectedHostId);

  }, [selectedHostId]);



  async function loadItems(hostId: string) {

    try {

      setLoadingItems(true);

      setError("");

      setChartData(null);



      const response = await fetch(

        `/api/v1/zabbix/hosts/${hostId}/items`

      );



      const json = await response.json();



      if (!response.ok || !json.success) {

        throw new Error(

          json.detail || "Gagal mengambil item."

        );

      }



      const numericItems = (json.data ?? []).filter(

        (item: Item) =>

          (item.value_type === "0" ||

            item.value_type === "3") &&

          item.status === "0"

      );



      setItems(numericItems);



      if (numericItems.length > 0) {

        setSelectedItemId(numericItems[0].itemid);

      } else {

        setSelectedItemId("");

      }

    } catch (err) {

      setError(

        err instanceof Error

          ? err.message

          : "Gagal mengambil item."

      );

    } finally {

      setLoadingItems(false);

    }

  }



  async function loadChart() {

    if (!selectedItemId || !from || !to) {

      setError(

        "Pilih host, item, tanggal mulai, dan tanggal akhir."

      );

      return;

    }



    const timeFrom = Math.floor(

      new Date(from).getTime() / 1000

    );



    const timeTill = Math.floor(

      new Date(to).getTime() / 1000

    );



    if (timeTill <= timeFrom) {

      setError(

        "Tanggal akhir harus lebih besar dari tanggal mulai."

      );

      return;

    }



    try {

      setLoadingChart(true);

      setError("");



      const response = await fetch(

        `/api/v1/zabbix/items/${selectedItemId}/data` +

          `?time_from=${timeFrom}` +

          `&time_till=${timeTill}`

      );



      const json = await response.json();



      if (!response.ok || !json.success) {

        throw new Error(

          json.detail || "Gagal mengambil data grafik."

        );

      }



      setChartData(json.data);

    } catch (err) {

      setError(

        err instanceof Error

          ? err.message

          : "Gagal mengambil data grafik."

      );

    } finally {

      setLoadingChart(false);

    }

  }



  const selectedHost = hosts.find(

    (host) => host.hostid === selectedHostId

  );



  const selectedItem = items.find(

    (item) => item.itemid === selectedItemId

  );



  const chartPath = useMemo(() => {

    if (!chartData || chartData.points.length === 0) {

      return "";

    }



    const points = chartData.points;



    const width = 900;

    const height = 330;

    const paddingLeft = 55;

    const paddingRight = 20;

    const paddingTop = 20;

    const paddingBottom = 35;



    const plotWidth =

      width - paddingLeft - paddingRight;



    const plotHeight =

      height - paddingTop - paddingBottom;



    const values = points.map((point) => point.value);



    let minValue = Math.min(...values);

    let maxValue = Math.max(...values);



    if (minValue === maxValue) {

      minValue -= 1;

      maxValue += 1;

    }



    const firstTime = points[0].timestamp;

    const lastTime =

      points[points.length - 1].timestamp;



    const timeRange = Math.max(

      lastTime - firstTime,

      1

    );



    return points

      .map((point, index) => {

        const x =

          paddingLeft +

          ((point.timestamp - firstTime) /

            timeRange) *

            plotWidth;



        const normalized =

          (point.value - minValue) /

          (maxValue - minValue);



        const y =

          paddingTop +

          plotHeight -

          normalized * plotHeight;



        return `${index === 0 ? "M" : "L"} ${x} ${y}`;

      })

      .join(" ");

  }, [chartData]);



  async function generatePdf() {

  if (!selectedItemId || !from || !to) {

    setError("Data laporan belum lengkap.");

    return;

  }



  const timeFrom = Math.floor(

    new Date(from).getTime() / 1000

  );



  const timeTill = Math.floor(

    new Date(to).getTime() / 1000

  );



  if (timeTill <= timeFrom) {

    setError("Waktu selesai harus lebih besar dari waktu mulai.");

    return;

  }



  const hostName =

    selectedHost?.name ||

    selectedHost?.host ||

    "Unknown";



  try {

    setError("");



    const response = await fetch(

      "/api/v1/reports/generate",

      {

        method: "POST",

        headers: {

          "Content-Type": "application/json",

        },

        body: JSON.stringify({

          host_name: hostName,

          item_ids: [String(selectedItemId)],

          time_from: timeFrom,

          time_till: timeTill,

          title: "ZABBIX MONITORING REPORT",

        }),

      }

    );



    if (!response.ok) {

      const errorText = await response.text();



      throw new Error(

        errorText || `HTTP ${response.status}`

      );

    }



    const blob = await response.blob();



    const url = window.URL.createObjectURL(blob);



    const link = document.createElement("a");

    link.href = url;

    link.download = `zabbix_report_${hostName}.pdf`;



    document.body.appendChild(link);

    link.click();

    link.remove();



    window.URL.revokeObjectURL(url);

    await loadHistory();

  } catch (error) {

    console.error("Generate PDF error:", error);



    setError(

      error instanceof Error

        ? error.message

        : "Gagal membuat PDF."

    );

  }

}



  return (

    <main

      style={{

        minHeight: "100vh",

        background: "#f5f7fa",

        padding: "32px",

        fontFamily: "Arial, sans-serif",

      }}

    >

      <div

        style={{

          maxWidth: "1200px",

          margin: "0 auto",

        }}

      >

        <h1

          style={{

            marginBottom: "8px",

          }}

        >

          Zabbix Report Exporter

        </h1>



        <p

          style={{

            marginTop: 0,

            color: "#666",

          }}

        >

          Monitoring dan export laporan Zabbix 7.4.10

        </p>



        <div

          style={{

            display: "grid",

            gridTemplateColumns:

              "repeat(auto-fit, minmax(200px, 1fr))",

            gap: "16px",

            marginBottom: "24px",

          }}

        >

        <div

          style={{

            background: "#fff",

            borderRadius: "12px",

            padding: "20px",

            boxShadow: "0 2px 8px rgba(0,0,0,0.06)",

          }}

        >

          <div style={{ color: "#666" }}>

            Total Host

          </div>



        <div

          style={{

            fontSize: "32px",

            fontWeight: "bold",

            marginTop: "8px",

          }}

        >

          {loadingHosts

            ? "..."

            : hosts.length}

        </div>

  </div>



  <div

    style={{

      background: "#fff",

      borderRadius: "12px",

      padding: "20px",

      boxShadow: "0 2px 8px rgba(0,0,0,0.06)",

    }}

  >

    <div style={{ color: "#666" }}>

      Total Item

    </div>



    <div

      style={{

        fontSize: "32px",

        fontWeight: "bold",

        marginTop: "8px",

      }}

    >

      {loadingItems

        ? "..."

        : items.length}

    </div>

  </div>



  <div

    style={{

      background: "#fff",

      borderRadius: "12px",

      padding: "20px",

      boxShadow: "0 2px 8px rgba(0,0,0,0.06)",

    }}

  >

    <div style={{ color: "#666" }}>

      Total Report

    </div>



        <div

          style={{

            fontSize: "32px",

            fontWeight: "bold",

            marginTop: "8px",

          }}

        >

          {loadingDashboard

            ? "..."

            : dashboard?.total_reports ?? 0}

        </div>

      </div>



      <div

        style={{

          background: "#fff",

          borderRadius: "12px",

          padding: "20px",

          boxShadow: "0 2px 8px rgba(0,0,0,0.06)",

        }}

      >

        <div style={{ color: "#666" }}>

          Active Schedule

        </div>



        <div

          style={{

            fontSize: "32px",

            fontWeight: "bold",

            marginTop: "8px",

          }}

        >

            {loadingDashboard

            ? "..."

            : dashboard?.active_schedules ?? 0}

        </div>

      </div>

    </div>



        {error && (

          <div

            style={{

              background: "#ffe7e7",

              padding: "12px 16px",

              borderRadius: "8px",

              marginBottom: "20px",

              color: "#a00000",

            }}

          >

            {error}

          </div>

        )}



        <section

          style={{

            background: "#fff",

            borderRadius: "12px",

            padding: "24px",

            marginBottom: "24px",

          }}

        >

          <h2>Report Configuration</h2>



          <div

            style={{

              display: "grid",

              gridTemplateColumns:

                "repeat(auto-fit, minmax(240px, 1fr))",

              gap: "16px",

            }}

          >

            <label>

              <div style={{ marginBottom: "6px" }}>

                Host

              </div>



              <select

                value={selectedHostId}

                onChange={(e) =>

                  setSelectedHostId(e.target.value)

                }

                disabled={loadingHosts}

                style={{

                  width: "100%",

                  padding: "10px",

                }}

              >

                <option value="">

                  {loadingHosts

                    ? "Loading hosts..."

                    : "Select host"}

                </option>



                {hosts.map((host) => (

                  <option

                    key={host.hostid}

                    value={host.hostid}

                  >

                    {host.name || host.host}

                  </option>

                ))}

              </select>

            </label>



            <label>

              <div style={{ marginBottom: "6px" }}>

                Metric / Item

              </div>



              <select

                value={selectedItemId}

                onChange={(e) =>

                  setSelectedItemId(e.target.value)

                }

                disabled={

                  !selectedHostId || loadingItems

                }

                style={{

                  width: "100%",

                  padding: "10px",

                }}

              >

                <option value="">

                  {loadingItems

                    ? "Loading items..."

                    : "Select metric"}

                </option>



                {items.map((item) => (

                  <option

                    key={item.itemid}

                    value={item.itemid}

                  >

                    {item.name}

                    {item.units

                      ? ` (${item.units})`

                      : ""}

                  </option>

                ))}

              </select>

            </label>



            <label>

              <div style={{ marginBottom: "6px" }}>

                From

              </div>



              <input

                type="datetime-local"

                value={from}

                onChange={(e) =>

                  setFrom(e.target.value)

                }

                style={{

                  width: "100%",

                  padding: "10px",

                }}

              />

            </label>



            <label>

              <div style={{ marginBottom: "6px" }}>

                To

              </div>



              <input

                type="datetime-local"

                value={to}

                onChange={(e) =>

                  setTo(e.target.value)

                }

                style={{

                  width: "100%",

                  padding: "10px",

                }}

              />

            </label>

          </div>



          <div

            style={{

              display: "flex",

              gap: "10px",

              marginTop: "20px",

            }}

          >

            <button

              onClick={loadChart}

              disabled={loadingChart}

              style={{

                padding: "10px 18px",

                cursor: "pointer",

              }}

            >

              {loadingChart

                ? "Loading..."

                : "Preview Chart"}

            </button>



            <button

              onClick={generatePdf}

              disabled={!selectedItemId}

              style={{

                padding: "10px 18px",

                cursor: "pointer",

              }}

            >

              Generate PDF

            </button>

          </div>

        </section>



        <section

          style={{

            background: "#fff",

            borderRadius: "12px",

            padding: "24px",

          }}

        >

          <div

            style={{

              display: "flex",

              justifyContent: "space-between",

              alignItems: "center",

              marginBottom: "16px",

            }}

          >

            <div>

              <h2

                style={{

                  margin: 0,

                }}

              >

                Chart Preview

              </h2>



              {selectedHost && selectedItem && (

                <p

                  style={{

                    marginBottom: 0,

                    color: "#666",

                  }}

                >

                  {selectedHost.name ||

                    selectedHost.host}

                  {" ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â "}

                  {selectedItem.name}

                </p>

              )}

            </div>



            {chartData && (

              <span

                style={{

                  padding: "6px 10px",

                  borderRadius: "6px",

                  background: "#eef3ff",

                }}

              >

                Source: {chartData.source}

              </span>

            )}

          </div>



          {!chartData && (

            <div

              style={{

                padding: "80px 20px",

                textAlign: "center",

                color: "#777",

              }}

            >

              Pilih host, metric, dan periode kemudian

              klik <b>Preview Chart</b>.

            </div>

          )}



          {chartData &&

            chartData.points.length === 0 && (

              <div

                style={{

                  padding: "80px 20px",

                  textAlign: "center",

                  color: "#777",

                }}

              >

                Tidak ada data pada periode tersebut.

              </div>

            )}



          {chartData &&

            chartData.points.length > 0 && (

              <div

                style={{

                  width: "100%",

                  overflowX: "auto",

                }}

              >

                <svg

                  viewBox="0 0 900 330"

                  style={{

                    width: "100%",

                    minWidth: "800px",

                    height: "360px",

                  }}

                >

                  <line

                    x1="55"

                    y1="20"

                    x2="55"

                    y2="295"

                    stroke="#999"

                  />



                  <line

                    x1="55"

                    y1="295"

                    x2="880"

                    y2="295"

                    stroke="#999"

                  />



                  <path

                    d={chartPath}

                    fill="none"

                    stroke="currentColor"

                    strokeWidth="2"

                  />

                </svg>



                <div

                  style={{

                    marginTop: "8px",

                    color: "#666",

                  }}

                >

                  Data points:{" "}

                  {chartData.points.length}

                </div>

              </div>

            )}

        </section>

        <section
          style={{
            background: "#fff",
            borderRadius: "12px",
            padding: "24px",
            marginTop: "24px",
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "16px",
              gap: "12px",
            }}
          >
            <div>
              <h2 style={{ margin: 0 }}>
                Execution History
              </h2>
              <p
                style={{
                  margin: "6px 0 0",
                  color: "#666",
                }}
              >
                Riwayat eksekusi scheduler dan laporan PDF.
              </p>
            </div>

            <button
              onClick={loadHistory}
              disabled={loadingHistory}
              style={{
                padding: "9px 14px",
                cursor: loadingHistory
                  ? "not-allowed"
                  : "pointer",
              }}
            >
              {loadingHistory ? "Loading..." : "Refresh"}
            </button>
          </div>

          {loadingHistory && history.length === 0 ? (
            <div
              style={{
                padding: "40px 20px",
                textAlign: "center",
                color: "#777",
              }}
            >
              Memuat execution history...
            </div>
          ) : history.length === 0 ? (
            <div
              style={{
                padding: "40px 20px",
                textAlign: "center",
                color: "#777",
              }}
            >
              Belum ada execution history.
            </div>
          ) : (
            <div
              style={{
                width: "100%",
                overflowX: "auto",
              }}
            >
              <table
                style={{
                  width: "100%",
                  borderCollapse: "collapse",
                  minWidth: "900px",
                }}
              >
                <thead>
                  <tr
                    style={{
                      borderBottom: "2px solid #e5e7eb",
                      textAlign: "left",
                    }}
                  >
                    <th style={{ padding: "12px 10px" }}>Schedule</th>
                    <th style={{ padding: "12px 10px" }}>Host</th>
                    <th style={{ padding: "12px 10px" }}>Started</th>
                    <th style={{ padding: "12px 10px" }}>Finished</th>
                    <th style={{ padding: "12px 10px" }}>Status</th>
                    <th style={{ padding: "12px 10px" }}>Report</th>
                  </tr>
                </thead>

                <tbody>
                  {history.map((item) => (
                    <tr
                      key={item.id}
                      style={{
                        borderBottom: "1px solid #eee",
                      }}
                    >
                      <td style={{ padding: "12px 10px" }}>
                        <div style={{ fontWeight: 600 }}>
                          {item.schedule_name ||
                            `Schedule #${item.schedule_id}`}
                        </div>
                        <div
                          style={{
                            fontSize: "12px",
                            color: "#777",
                            marginTop: "3px",
                          }}
                        >
                          ID: {item.schedule_id}
                        </div>
                      </td>

                      <td style={{ padding: "12px 10px" }}>
                        {item.host_name || "-"}
                      </td>

                      <td
                        style={{
                          padding: "12px 10px",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {formatDateTime(item.started_at)}
                      </td>

                      <td
                        style={{
                          padding: "12px 10px",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {formatDateTime(item.finished_at)}
                      </td>

                      <td style={{ padding: "12px 10px" }}>
                        <span
                          style={{
                            display: "inline-block",
                            padding: "5px 9px",
                            borderRadius: "999px",
                            fontSize: "12px",
                            fontWeight: 700,
                            background:
                              item.status === "SUCCESS"
                                ? "#e7f7ed"
                                : item.status === "FAILED"
                                ? "#ffe7e7"
                                : "#fff4d6",
                            color:
                              item.status === "SUCCESS"
                                ? "#087443"
                                : item.status === "FAILED"
                                ? "#a00000"
                                : "#8a5a00",
                          }}
                        >
                          {item.status}
                        </span>

                        {item.error_message && (
                          <div
                            style={{
                              marginTop: "6px",
                              maxWidth: "260px",
                              fontSize: "12px",
                              color: "#a00000",
                            }}
                          >
                            {item.error_message}
                          </div>
                        )}
                      </td>

                      <td style={{ padding: "12px 10px" }}>
                        {item.report_filename ? (
                          <a
                            href={`/api/v1/reports/${encodeURIComponent(
                              item.report_filename
                            )}`}
                            target="_blank"
                            rel="noreferrer"
                            style={{ textDecoration: "none" }}
                          >
                            View PDF
                          </a>
                        ) : (
                          "-"
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section
          style={{
            background: "#fff",
            borderRadius: "12px",
            padding: "24px",
            marginTop: "24px",
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "16px",
            }}
          >
            <div>
              <h2 style={{ margin: 0 }}>
                Execution History
              </h2>

              <p
                style={{
                  marginTop: "6px",
                  marginBottom: 0,
                  color: "#666",
                }}
              >
                Riwayat eksekusi laporan otomatis.
              </p>
            </div>

            <button
              onClick={loadHistory}
              disabled={loadingHistory}
              style={{
                padding: "8px 14px",
                cursor: loadingHistory
                  ? "not-allowed"
                  : "pointer",
              }}
            >
              {loadingHistory ? "Loading..." : "Refresh"}
            </button>
          </div>

          {loadingHistory && history.length === 0 && (
            <div
              style={{
                padding: "40px",
                textAlign: "center",
                color: "#777",
              }}
            >
              Memuat execution history...
            </div>
          )}

          {!loadingHistory && history.length === 0 && (
            <div
              style={{
                padding: "40px",
                textAlign: "center",
                color: "#777",
              }}
            >
              Belum ada riwayat eksekusi.
            </div>
          )}

          {history.length > 0 && (
            <div
              style={{
                overflowX: "auto",
              }}
            >
              <table
                style={{
                  width: "100%",
                  borderCollapse: "collapse",
                  fontSize: "14px",
                }}
              >
                <thead>
                  <tr
                    style={{
                      borderBottom: "1px solid #ddd",
                      textAlign: "left",
                    }}
                  >
                    <th style={{ padding: "12px 8px" }}>
                      Waktu
                    </th>

                    <th style={{ padding: "12px 8px" }}>
                      Schedule
                    </th>

                    <th style={{ padding: "12px 8px" }}>
                      Host
                    </th>

                    <th style={{ padding: "12px 8px" }}>
                      Status
                    </th>

                    <th style={{ padding: "12px 8px" }}>
                      Report
                    </th>
                  </tr>
                </thead>

                <tbody>
                  {history.map((item) => (
                    <tr
                      key={item.id}
                      style={{
                        borderBottom:
                          "1px solid #eee",
                      }}
                    >
                      <td
                        style={{
                          padding: "12px 8px",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {new Date(
                          item.started_at
                        ).toLocaleString("id-ID")}
                      </td>

                      <td
                        style={{
                          padding: "12px 8px",
                        }}
                      >
                        {item.schedule_name ||
                          `Schedule #${item.schedule_id}`}
                      </td>

                      <td
                        style={{
                          padding: "12px 8px",
                        }}
                      >
                        {item.host_name || "-"}
                      </td>

                      <td
                        style={{
                          padding: "12px 8px",
                        }}
                      >
                        {item.status === "SUCCESS" && (
                          <span
                            style={{
                              background: "#e8f7e8",
                              color: "#176b17",
                              padding:
                                "5px 10px",
                              borderRadius: "6px",
                              fontWeight: "bold",
                            }}
                          >
                            ÃƒÂ¢Ã…â€œÃ¢â‚¬Å“ SUCCESS
                          </span>
                        )}

                        {item.status === "FAILED" && (
                          <span
                            style={{
                              background: "#ffe7e7",
                              color: "#a00000",
                              padding:
                                "5px 10px",
                              borderRadius: "6px",
                              fontWeight: "bold",
                            }}
                          >
                            ÃƒÂ¢Ã…â€œÃ¢â‚¬Â¢ FAILED
                          </span>
                        )}

                        {item.status === "RUNNING" && (
                          <span
                            style={{
                              background: "#fff4d6",
                              color: "#8a6200",
                              padding:
                                "5px 10px",
                              borderRadius: "6px",
                              fontWeight: "bold",
                            }}
                          >
                            ÃƒÂ¢Ã¢â‚¬â€Ã‚Â RUNNING
                          </span>
                        )}
                      </td>

                      <td
                        style={{
                          padding: "12px 8px",
                        }}
                      >
                        {item.report_filename ? (
                          <a
                            href={`/api/v1/reports/${encodeURIComponent(
                              item.report_filename
                            )}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{
                              color: "#0066cc",
                              textDecoration:
                                "none",
                              fontWeight: "bold",
                            }}
                          >
                            Download PDF
                          </a>
                        ) : item.error_message ? (
                          <span
                            style={{
                              color: "#a00000",
                            }}
                          >
                            {item.error_message}
                          </span>
                        ) : (
                          "-"
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </main>

  );

}
