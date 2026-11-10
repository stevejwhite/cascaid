"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { readApi, type BlueprintMatrix as Matrix, type MatrixStation } from "../lib/api";
import { duration, label } from "../lib/station-display";
import { AppShell } from "./app-shell";
import { StationTitle } from "./station-title";

function StationEntry({ station }: { station: MatrixStation }) {
  return <div className={station.case_id ? "matrix-station" : "matrix-station unavailable"}>
    {station.case_id
      ? <Link href={`/?station=${encodeURIComponent(station.case_id)}`} prefetch={false} aria-label={`${station.code} ${station.title}`}>
        <strong className="matrix-code">{station.code}</strong>{" "}<StationTitle title={station.title} />
      </Link>
      : <span><strong className="matrix-code">{station.code}</strong>{" "}<StationTitle title={station.title} /></span>}
    <span className={`matrix-session session-${station.session}`}>{label(station.session)}</span>
    {station.unavailable_reason && <span className="matrix-unavailable">Unavailable: {station.unavailable_reason}</span>}
    {!station.clinically_validated && <span className="matrix-validation">Not clinically validated</span>}
  </div>;
}

export function BlueprintMatrix() {
  const [data, setData] = useState<Matrix | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [order, setOrder] = useState("");
  const active = useRef<AbortController | null>(null);
  const refresh = useCallback(() => {
    active.current?.abort();
    const controller = new AbortController();
    active.current = controller;
    return readApi<Matrix>("/api/blueprint", controller.signal).then((result) => {
      if (!controller.signal.aborted) setData(result);
    }).catch(() => {
      if (!controller.signal.aborted) { setError(true); setData(null); }
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
  }, []);
  useEffect(() => {
    void refresh();
    return () => active.current?.abort();
  }, [refresh]);

  const stations = data?.stations.filter((station) => !order || station.running_order === order) ?? [];
  const specialties = Object.entries(data?.minimum_specialty ?? {});
  return <AppShell current="blueprint">
      <div className="page-heading">
        <div>
          <p className="eyebrow">CascAid · Practice</p>
          <h1>CASC blueprint matrix</h1>
          <p className="intro">Browse the mock-exam stations by skill, subdivision and specialty.
            Select a linked station to start its reading time. Cases are original fiction and
            not clinically validated; availability does not establish teaching or exam coverage.</p>
        </div>
        <button type="button" className="refresh" onClick={() => {
          setLoading(true); setError(false); void refresh();
        }} disabled={loading}>Refresh</button>
      </div>
      {loading && <p className="empty" role="status">Loading blueprint…</p>}
      {error && <p className="error" role="alert">The blueprint could not be loaded. Check that the local API
        is running and up to date, then refresh. <Link href="/">Return to stations</Link>.</p>}
      {data && !loading && <>
        <section className="blueprint-summary" aria-label="Pinned blueprint">
          <p><strong>Pinned blueprint:</strong> {data.version.split(" | ")[0]}.</p>
          <p>Each mock exam: {Object.entries(data.stations_per_running_order).map(([skill, count]) =>
            `${count} ${label(skill).toLowerCase()}`).join(" · ")} stations.
            {" "}Reading: {Object.entries(data.reading_seconds).map(([session, seconds]) =>
              `${label(session).toLowerCase()} ${duration(seconds)}`).join(" · ")}.</p>
          <details><summary>Blueprint source and version</summary><p>{data.source_id} · {data.version}</p></details>
        </section>
        <div className="matrix-controls">
          <label>Mock exam<select value={order} onChange={(event) => setOrder(event.target.value)}>
            <option value="">All mock exams</option>
            {[...new Set(data.stations.map((station) => station.running_order))].sort().map((code) =>
              <option key={code} value={code}>Mock exam {code}</option>)}
          </select></label>
          <p role="status">{stations.filter((station) => station.case_id).length} runnable / {stations.length} planned stations</p>
        </div>
        <p id="matrix-help" className="matrix-help">The minimum percentage is the proportion of mock exams
          that should include each subdivision, not a percentage of stations. Specialty minimums apply
          within each mock exam. A dash means no station is mapped in this selection.</p>
        <div className="matrix-scroll" role="region" aria-label="Station matrix" tabIndex={0}>
          <table className="blueprint-matrix" aria-describedby="matrix-help">
            <caption>Blueprint subdivisions × specialties{order ? ` · Mock exam ${order}` : " · Mock exams A–D"}</caption>
            <thead><tr><th scope="col">Skill<br />Subdivision</th><th scope="col">Minimum exams</th>
              {specialties.map(([specialty, minimum]) => <th scope="col" key={specialty}>
                <span className="matrix-specialty">{label(specialty)}</span><span className="matrix-minimum">At least {minimum} per exam</span>
              </th>)}
            </tr></thead>
            <tbody>{data.subdivisions.map((subdivision, index) => <tr key={subdivision.id}
              className={index > 0 && data.subdivisions[index - 1].skill !== subdivision.skill ? "skill-group-start" : undefined}>
              <th scope="row"><span className={`matrix-skill skill-${subdivision.skill}`}>{label(subdivision.skill)}</span><br />
                <span className="matrix-subdivision">{subdivision.label}</span></th>
              <td>{subdivision.minimum_percentage}%</td>
              {specialties.map(([specialty]) => {
                const entries = stations.filter((station) => station.subdivision === subdivision.id && station.specialty === specialty);
                return <td key={specialty}>{entries.length
                  ? <div className="matrix-entries">{entries.map((station) => <StationEntry key={station.code} station={station} />)}</div>
                  : <span aria-label="No mapped station">—</span>}</td>;
              })}
            </tr>)}</tbody>
          </table>
        </div>
      </>}
  </AppShell>;
}
