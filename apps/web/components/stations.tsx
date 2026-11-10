"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { readApi, type CaseSummary, type Readiness } from "../lib/api";
import { StationRunner } from "./station";
import { AppShell } from "./app-shell";
import { StationFilters } from "./station-filters";
import { emptyFilters, filterStations } from "../lib/station-filters";
import { duration, label } from "../lib/station-display";
import { StationTitle } from "./station-title";

export { duration, label } from "../lib/station-display";

function StationCard({ station, onStart }: { station: CaseSummary; onStart: () => void }) {
  return <article className="station-card" aria-labelledby={`station-${station.id}`}>
    <div>
      <p className="station-descriptors"><span className={`descriptor-skill skill-${station.skill}`}>{label(station.skill)}</span>{" "}
        <span className="descriptor-specialty">{label(station.specialty)}</span></p>
      <h2 id={`station-${station.id}`} aria-label={station.title}><StationTitle title={station.title} /></h2>
    </div>
    <div className="station-meta">
      <span className="tag">{label(station.subdivision)}</span>
      <span className="tag">{label(station.role)}</span>
      <span className="tag"><span className="descriptor-line">Reading {duration(station.reading_seconds)}</span>{" "}<span className="descriptor-line">Station {duration(station.interview_seconds)}</span></span>
      {!station.clinically_validated && <span className="tag warning">Not clinically validated</span>}
    </div>
    <details>
      <summary>Candidate instructions</summary>
      <p>{station.candidate_instructions}</p>
    </details>
    <button className="start" type="button" onClick={onStart}>Start station</button>
  </article>;
}

export function Stations({ initialCaseId = null }: { initialCaseId?: string | null }) {
  const [status, setStatus] = useState<Readiness | null>(null);
  const [stations, setStations] = useState<CaseSummary[] | null>(null);
  const [error, setError] = useState(false);
  const [running, setRunning] = useState<string | null>(initialCaseId);
  const [filters, setFilters] = useState(emptyFilters);
  const active = useRef<AbortController | null>(null);

  const refresh = useCallback(() => {
    active.current?.abort();
    const controller = new AbortController();
    active.current = controller;
    return Promise.allSettled([
      // Readiness enables speech in the runner; it must not delay browsing cases.
      readApi<Readiness>("/api/status", controller.signal).then((health) => {
        if (!controller.signal.aborted) setStatus(health);
      }).catch(() => { if (!controller.signal.aborted) setStatus(null); }),
      readApi<CaseSummary[]>("/api/cases", controller.signal).then((cases) => {
        if (!controller.signal.aborted) { setStations(cases); setError(false); }
      }).catch(() => {
        if (!controller.signal.aborted) { setStations(null); setError(true); }
      }),
    ]);
  }, []);

  useEffect(() => {
    void refresh();
    return () => active.current?.abort();
  }, [refresh]);

  const activeStation = stations?.find((station) => station.id === running);
  const filtered = filterStations(stations ?? [], filters);
  const exitStation = () => {
    setRunning(null);
    const url = new URL(window.location.href);
    url.searchParams.delete("station");
    window.history.replaceState(null, "", url);
    void refresh();
  };
  return <AppShell current="stations">
      {activeStation ? <StationRunner key={activeStation.id} caseId={activeStation.id} speech={status?.speech?.status === "ready" && status.speech_backend !== "off"}
        neural={status?.voice?.status === "ready" && status.tts_backend !== "off"} onExit={exitStation} /> : <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">CascAid · Practice</p>
          <h1>CASC stations</h1>
          <p className="intro">Practise CASC-style stations with a simulated patient, relative or colleague.
            Cases are original fiction written to the March 2023 CASC blueprint; they are not
            clinician-reviewed, and feedback will not be a CASC mark.</p>
        </div>
        <button className="refresh" type="button" onClick={() => void refresh()}>Refresh</button>
      </div>
      {error && <p className="error" role="alert">The local API is unavailable or returned an error. Start it with npm run dev.</p>}
      {running && stations !== null && !activeStation && <p className="error" role="alert">
        The selected station is unavailable. Choose another station from the list or blueprint matrix.
      </p>}
      <section aria-labelledby="stations-heading">
        <h2 id="stations-heading">Stations</h2>
        {stations !== null && stations.length > 0 && <>
          <StationFilters stations={stations} value={filters} onChange={setFilters} />
          <p className="results-count" role="status">Showing {filtered.length} of {stations.length} stations</p>
        </>}
        {stations === null ? <p className="empty">Loading stations…</p>
          : stations.length === 0 ? <p className="empty">No station cases found in data/cases.</p>
            : filtered.length === 0 ? <p className="empty">No stations match these filters. Try a different search or clear the filters.</p>
              : <div className="station-list">{filtered.map((station) => <StationCard key={station.id} station={station} onStart={() => setRunning(station.id)} />)}</div>}
      </section>
      </>}
  </AppShell>;
}
