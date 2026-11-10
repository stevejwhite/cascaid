"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { readApi, type Readiness, type ServiceCheck } from "../lib/api";
import { AppShell } from "./app-shell";

const statusLabels: Record<ServiceCheck["status"], string> = {
  ready: "Ready", unavailable: "Unavailable", empty: "Empty", invalid: "Needs attention", disabled: "Off",
};

/** A response without a check means the API predates this page. */
function StatusCard({ title, check, answered }: { title: string; check: ServiceCheck | undefined; answered: boolean }) {
  const outdated = answered && !check;
  return <article className="service-card">
    <div className="card-heading"><h2>{title}</h2><span aria-hidden="true" className={`status-dot ${check?.status === "ready" ? "good" : "pending"}`} /></div>
    <p className="service-state">{check ? statusLabels[check.status] : outdated ? "Restart needed" : "Not checked"}</p>
    <p className="muted">{check?.detail ?? (outdated
      ? "The running API is older than this page. Restart npm run dev."
      : "No current status available.")}</p>
  </article>;
}

export function ServiceStatus() {
  const [status, setStatus] = useState<Readiness | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  const active = useRef<AbortController | null>(null);
  const refresh = useCallback(() => {
    active.current?.abort();
    const controller = new AbortController();
    active.current = controller;
    return readApi<Readiness>("/api/status", controller.signal).then((result) => {
      if (!controller.signal.aborted) { setStatus(result); setError(false); }
    }).catch(() => {
      if (!controller.signal.aborted) { setStatus(null); setError(true); }
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
  }, []);
  useEffect(() => {
    void refresh();
    return () => active.current?.abort();
  }, [refresh]);

  const backend = status?.model_backend === "local" ? "Local Qwen model" : "Deterministic fake model";
  return <AppShell current="status">
    <div className="page-heading">
      <div>
        <p className="eyebrow">CascAid · System status</p>
        <h1>Service status</h1>
        <p className="intro">Check station availability, source configuration and the local services
          used for generation, speech recognition and character voices.</p>
      </div>
      <button className="refresh" type="button" disabled={loading} onClick={() => {
        setLoading(true); setError(false); void refresh();
      }}>Refresh</button>
    </div>
    {loading && <p className="empty" role="status">Checking local services…</p>}
    {error && <p className="error" role="alert">The local API is unavailable or returned an error. Check that it is running, then refresh.</p>}
    {!loading && <section aria-label="Service status" className="service-grid">
      <StatusCard title="Station cases" check={status?.cases} answered={!!status} />
      <StatusCard title="Source registry" check={status?.registry} answered={!!status} />
      <StatusCard title={`Generation · ${status ? backend : "model"}`} check={status?.generation} answered={!!status} />
      <StatusCard title="Speech recognition" check={status?.speech} answered={!!status} />
      <StatusCard title="Character voice" check={status?.voice} answered={!!status} />
    </section>}
  </AppShell>;
}
