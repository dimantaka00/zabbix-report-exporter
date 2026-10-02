"use client";

import { useEffect, useState } from "react";

<nav
  style={{
    display: "flex",
    gap: "16px",
    marginBottom: "20px",
  }}
>
  <a href="/">Monitoring</a>
  <a href="/reports">Reports</a>
  <a href="/schedules">Schedules</a>
</nav>

type Host = {
  hostid: string;
  host: string;
  name: string;
  status: string;
};

type Item = {
  itemid: string;
  name: string;
  units: string;
  value_type: string;
  status: string;
};

type Schedule = {
  id: number;
  name: string;
  host_id?: string | null;
  host_name: string;
  item_ids: string[];
  hour: number;
  minute: number;
  timezone: string;
  enabled: boolean;
  last_run_date?: string | null;
};

export default function SchedulesPage() {
  const [hosts, setHosts] = useState<Host[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [schedules, setSchedules] = useState<Schedule[]>([]);

  const [selectedHostId, setSelectedHostId] = useState("");
  const [selectedItemIds, setSelectedItemIds] =
    useState<string[]>([]);

  const [name, setName] = useState(
    "Daily Infrastructure Report"
  );
  const [hour, setHour] = useState("7");
  const [minute, setMinute] = useState("0");
  const [timezone, setTimezone] =
    useState("Asia/Jakarta");

  const [loading, setLoading] = useState(true);
  const [loadingItems, setLoadingItems] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    loadInitialData();
  }, []);

  async function loadInitialData() {
    try {
      setLoading(true);
      setError("");

      const [hostsResponse, schedulesResponse] =
        await Promise.all([
          fetch("/api/v1/zabbix/hosts"),
          fetch("/api/v1/schedules", {
            cache: "no-store",
          }),
        ]);

      const hostsJson = await hostsResponse.json();
      const schedulesJson =
        await schedulesResponse.json();

      if (
        !hostsResponse.ok ||
        !hostsJson.success
      ) {
        throw new Error(
          hostsJson.detail ||
            "Gagal mengambil host."
        );
      }

      if (
        !schedulesResponse.ok ||
        !schedulesJson.success
      ) {
        throw new Error(
          schedulesJson.detail ||
            "Gagal mengambil schedule."
        );
      }

      setHosts(hostsJson.data || []);
      setSchedules(schedulesJson.data || []);

      if (hostsJson.data?.length > 0) {
        setSelectedHostId(
          hostsJson.data[0].hostid
        );
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Gagal memuat data."
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!selectedHostId) {
      setItems([]);
      setSelectedItemIds([]);
      return;
    }

    loadItems(selectedHostId);
  }, [selectedHostId]);

  async function loadItems(hostId: string) {
    try {
      setLoadingItems(true);
      setError("");
      setSelectedItemIds([]);

      const response = await fetch(
        `/api/v1/zabbix/hosts/${hostId}/items`
      );

      const json = await response.json();

      if (!response.ok || !json.success) {
        throw new Error(
          json.detail ||
            "Gagal mengambil item."
        );
      }

      const numericItems = (
        json.data || []
      ).filter(
        (item: Item) =>
          (item.value_type === "0" ||
            item.value_type === "3") &&
          item.status === "0"
      );

      setItems(numericItems);
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

  function toggleItem(itemId: string) {
    setSelectedItemIds((current) => {
      if (current.includes(itemId)) {
        return current.filter(
          (id) => id !== itemId
        );
      }

      return [...current, itemId];
    });
  }

  async function createSchedule() {
    setMessage("");
    setError("");

    const selectedHost = hosts.find(
      (host) =>
        host.hostid === selectedHostId
    );

    if (!selectedHost) {
      setError("Pilih host.");
      return;
    }

    if (selectedItemIds.length === 0) {
      setError(
        "Pilih minimal satu metric."
      );
      return;
    }

    const hourNumber = Number(hour);
    const minuteNumber = Number(minute);

    if (
      hourNumber < 0 ||
      hourNumber > 23 ||
      minuteNumber < 0 ||
      minuteNumber > 59
    ) {
      setError(
        "Jam harus 00-23 dan menit 00-59."
      );
      return;
    }

    try {
      setSaving(true);

      const response = await fetch(
        "/api/v1/schedules",
        {
          method: "POST",
          headers: {
            "Content-Type":
              "application/json",
          },
          body: JSON.stringify({
            name,
            host_id: selectedHost.hostid,
            host_name:
              selectedHost.name ||
              selectedHost.host,
            item_ids: selectedItemIds,
            hour: hourNumber,
            minute: minuteNumber,
            timezone,
            enabled: true,
          }),
        }
      );

      const json = await response.json();

      if (!response.ok || !json.success) {
        throw new Error(
          json.detail ||
            "Gagal membuat schedule."
        );
      }

      setSchedules((current) => [
        json.data,
        ...current,
      ]);

      setMessage(
        "Schedule berhasil dibuat."
      );

      setSelectedItemIds([]);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Gagal membuat schedule."
      );
    } finally {
      setSaving(false);
    }
  }

  async function deleteSchedule(
    scheduleId: number
  ) {
    const confirmed = window.confirm(
      "Hapus schedule ini?"
    );

    if (!confirmed) {
      return;
    }

    try {
      const response = await fetch(
        `/api/v1/schedules/${scheduleId}`,
        {
          method: "DELETE",
        }
      );

      const json = await response.json();

      if (!response.ok || !json.success) {
        throw new Error(
          json.detail ||
            "Gagal menghapus schedule."
        );
      }

      setSchedules((current) =>
        current.filter(
          (schedule) =>
            schedule.id !== scheduleId
        )
      );

      setMessage(
        "Schedule berhasil dihapus."
      );
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Gagal menghapus schedule."
      );
    }
  }

  async function toggleSchedule(schedule: Schedule) {
    setMessage("");
    setError("");

    try {
        const response = await fetch(
            `/api/v1/schedules/${schedule.id}`,
            {
                method: "PUT",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    name: schedule.name,
                    host_id: schedule.host_id,
                    host_name: schedule.host_name,
                    item_ids: schedule.item_ids,
                    hour: schedule.hour,
                    minute: schedule.minute,
                    timezone: schedule.timezone,
                    enabled: !schedule.enabled,
                }),
            }
        );

        const json = await response.json();

        if (!response.ok || !json.success) {
            throw new Error(
                json.detail ||
                    "Gagal mengubah status schedule."
            );
        }

        setSchedules((current) =>
            current.map((item) =>
                item.id === schedule.id
                    ? json.data
                    : item
            )
        );

        setMessage(
            json.data.enabled
                ? "Schedule berhasil diaktifkan."
                : "Schedule berhasil dinonaktifkan."
        );
    } catch (err) {
        setError(
            err instanceof Error
                ? err.message
                : "Gagal mengubah status schedule."
        );
    }
  }


  return (
    <main
      style={{
        minHeight: "100vh",
        background: "#f5f7fa",
        padding: "32px",
        fontFamily:
          "Arial, sans-serif",
      }}
    >
      <div
        style={{
          maxWidth: "1200px",
          margin: "0 auto",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent:
              "space-between",
            alignItems: "center",
            marginBottom: "24px",
          }}
        >
          <div>
            <h1 style={{ marginBottom: "8px" }}>
              Report Schedules
            </h1>

            <p
              style={{
                marginTop: 0,
                color: "#666",
              }}
            >
              Atur laporan Zabbix otomatis.
            </p>
          </div>

          <a href="/">
            ← Monitoring
          </a>
        </div>

        {error && (
          <div
            style={{
              background: "#ffe7e7",
              color: "#9a0000",
              padding: "12px 16px",
              borderRadius: "8px",
              marginBottom: "16px",
            }}
          >
            {error}
          </div>
        )}

        {message && (
          <div
            style={{
              background: "#e8f7e8",
              color: "#176b17",
              padding: "12px 16px",
              borderRadius: "8px",
              marginBottom: "16px",
            }}
          >
            {message}
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
          <h2>
            Create Daily Report
          </h2>

          <div
            style={{
              display: "grid",
              gridTemplateColumns:
                "repeat(auto-fit, minmax(230px, 1fr))",
              gap: "16px",
            }}
          >
            <label>
              <div>Report Name</div>

              <input
                value={name}
                onChange={(e) =>
                  setName(e.target.value)
                }
                style={{
                  width: "100%",
                  padding: "10px",
                  marginTop: "6px",
                }}
              />
            </label>

            <label>
              <div>Host</div>

              <select
                value={selectedHostId}
                onChange={(e) =>
                  setSelectedHostId(
                    e.target.value
                  )
                }
                disabled={loading}
                style={{
                  width: "100%",
                  padding: "10px",
                  marginTop: "6px",
                }}
              >
                <option value="">
                  Select host
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
              <div>Hour</div>

              <input
                type="number"
                min="0"
                max="23"
                value={hour}
                onChange={(e) =>
                  setHour(e.target.value)
                }
                style={{
                  width: "100%",
                  padding: "10px",
                  marginTop: "6px",
                }}
              />
            </label>

            <label>
              <div>Minute</div>

              <input
                type="number"
                min="0"
                max="59"
                value={minute}
                onChange={(e) =>
                  setMinute(e.target.value)
                }
                style={{
                  width: "100%",
                  padding: "10px",
                  marginTop: "6px",
                }}
              />
            </label>

            <label>
              <div>Timezone</div>

              <select
                value={timezone}
                onChange={(e) =>
                  setTimezone(
                    e.target.value
                  )
                }
                style={{
                  width: "100%",
                  padding: "10px",
                  marginTop: "6px",
                }}
              >
                <option value="Asia/Jakarta">
                  Asia/Jakarta
                </option>

                <option value="Asia/Makassar">
                  Asia/Makassar
                </option>

                <option value="Asia/Jayapura">
                  Asia/Jayapura
                </option>
              </select>
            </label>
          </div>

          <h3
            style={{
              marginTop: "24px",
            }}
          >
            Metrics
          </h3>

          {loadingItems && (
            <p>Loading metrics...</p>
          )}

          {!loadingItems &&
            items.length === 0 && (
              <p style={{ color: "#777" }}>
                Tidak ada metric numerik
                pada host ini.
              </p>
            )}

          <div
            style={{
              display: "grid",
              gridTemplateColumns:
                "repeat(auto-fit, minmax(300px, 1fr))",
              gap: "8px",
              maxHeight: "300px",
              overflowY: "auto",
            }}
          >
            {items.map((item) => (
              <label
                key={item.itemid}
                style={{
                  display: "flex",
                  gap: "10px",
                  padding: "10px",
                  border:
                    "1px solid #ddd",
                  borderRadius: "8px",
                  cursor: "pointer",
                }}
              >
                <input
                  type="checkbox"
                  checked={selectedItemIds.includes(
                    item.itemid
                  )}
                  onChange={() =>
                    toggleItem(
                      item.itemid
                    )
                  }
                />

                <span>
                  {item.name}
                  {item.units
                    ? ` (${item.units})`
                    : ""}
                </span>
              </label>
            ))}
          </div>

          <button
            onClick={createSchedule}
            disabled={saving}
            style={{
              marginTop: "24px",
              padding: "11px 20px",
              cursor: "pointer",
            }}
          >
            {saving
              ? "Saving..."
              : "Create Schedule"}
          </button>
        </section>

                <section
          style={{
            background: "#fff",
            borderRadius: "12px",
            padding: "24px",
          }}
        >
          <h2>
            Existing Schedules
          </h2>

          {schedules.length === 0 && (
            <p style={{ color: "#777" }}>
              Belum ada schedule.
            </p>
          )}

          {schedules.map((schedule) => (
            <div
              key={schedule.id}
              style={{
                border: "1px solid #ddd",
                borderRadius: "10px",
                padding: "16px",
                marginBottom: "12px",
                display: "flex",
                justifyContent: "space-between",
                gap: "20px",
                alignItems: "center",
              }}
            >
              <div>
                <strong>
                  {schedule.name}
                </strong>

                <div
                  style={{
                    marginTop: "6px",
                    color: "#666",
                  }}
                >
                  {schedule.host_name}
                  {" • "}
                  {String(schedule.hour).padStart(2, "0")}
                  :
                  {String(schedule.minute).padStart(2, "0")}
                  {" • "}
                  {schedule.timezone}
                </div>

                <div
                  style={{
                    marginTop: "5px",
                    color: "#777",
                  }}
                >
                  Metrics:{" "}
                  {schedule.item_ids.length}
                  {" • "}
                  Status:{" "}
                  {schedule.enabled
                    ? "Enabled"
                    : "Disabled"}
                </div>

                {schedule.last_run_date && (
                  <div
                    style={{
                      marginTop: "5px",
                      color: "#777",
                    }}
                  >
                    Last run:{" "}
                    {schedule.last_run_date}
                  </div>
                )}
              </div>

              <div
                style={{
                  display: "flex",
                  gap: "8px",
                  flexDirection: "column",
                }}
              >
                <button
                  onClick={() =>
                    toggleSchedule(schedule)
                  }
                  style={{
                    padding: "8px 14px",
                    cursor: "pointer",
                  }}
                >
                  {schedule.enabled
                    ? "Disable"
                    : "Enable"}
                </button>

                <button
                  onClick={() =>
                    deleteSchedule(schedule.id)
                  }
                  style={{
                    padding: "8px 14px",
                    cursor: "pointer",
                  }}
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </section>
      </div>
    </main>
  );
}