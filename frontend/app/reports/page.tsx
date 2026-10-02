"use client";

import { useEffect, useState } from "react";

type Report = {
  filename: string;
  size: number;
  created: number;
  download_url: string;
};

export default function ReportsPage() {
  const [reports, setReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadReports() {
    try {
      setLoading(true);
      setError("");

      const response = await fetch(
        "/api/v1/reports",
        {
          cache: "no-store",
        }
      );

      const json = await response.json();

      if (!response.ok || !json.success) {
        throw new Error(
          json.detail || "Gagal mengambil laporan."
        );
      }

      setReports(json.data || []);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Gagal mengambil laporan."
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadReports();
  }, []);

  function formatSize(bytes: number) {
    if (bytes < 1024) return `${bytes} B`;

    if (bytes < 1024 * 1024) {
      return `${(bytes / 1024).toFixed(1)} KB`;
    }

    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  }

  function formatDate(timestamp: number) {
    return new Date(
      timestamp * 1000
    ).toLocaleString("id-ID");
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
          maxWidth: "1100px",
          margin: "0 auto",
        }}
      >
        <h1>Report History</h1>

        <p style={{ color: "#666" }}>
          Daftar laporan PDF yang sudah dibuat.
        </p>

        {error && (
          <div
            style={{
              padding: "12px",
              background: "#ffe7e7",
              marginBottom: "20px",
            }}
          >
            {error}
          </div>
        )}

        {loading && <p>Loading...</p>}

        {!loading && reports.length === 0 && (
          <div
            style={{
              background: "#fff",
              padding: "40px",
              borderRadius: "12px",
            }}
          >
            Belum ada laporan.
          </div>
        )}

        {reports.map((report) => (
          <div
            key={report.filename}
            style={{
              background: "#fff",
              padding: "18px",
              marginBottom: "12px",
              borderRadius: "10px",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <div>
              <strong>{report.filename}</strong>

              <div
                style={{
                  color: "#777",
                  marginTop: "6px",
                }}
              >
                {formatDate(report.created)}
                {" · "}
                {formatSize(report.size)}
              </div>
            </div>

            <a
              href={report.download_url}
              target="_blank"
              rel="noreferrer"
              style={{
                padding: "9px 14px",
                borderRadius: "6px",
                border: "1px solid #ccc",
                textDecoration: "none",
              }}
            >
              Download
            </a>

            <a href="/schedules">
                Schedules
            </a>
          </div>
        ))}
      </div>
    </main>
  );
}