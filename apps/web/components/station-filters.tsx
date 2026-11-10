import type { CaseSummary } from "../lib/api";
import { emptyFilters, type StationFilters as Filters } from "../lib/station-filters";
import { label } from "../lib/station-display";

export function StationFilters({ stations, value, onChange }: {
  stations: CaseSummary[];
  value: Filters;
  onChange: (value: Filters) => void;
}) {
  return <fieldset className="station-filters">
    <legend>Filter stations</legend>
    <label className="station-search">Search stations
      <input type="search" value={value.query} placeholder="e.g. depression, capacity, clozapine"
        onChange={(event) => onChange({ ...value, query: event.target.value })} />
    </label>
    {(["skill", "specialty", "subdivision", "role"] as const).map((field) => {
      const choices = stations.filter((station) => field !== "subdivision" || !value.skill || station.skill === value.skill);
      return <label key={field}>{label(field)}
        <select value={value[field]} onChange={(event) => onChange({ ...value,
          [field]: event.target.value, ...(field === "skill" ? { subdivision: "" } : {}) })}>
          <option value="">All {field === "specialty" ? "specialties" : `${field}s`}</option>
          {[...new Set(choices.map((station) => station[field]))].sort().map((choice) =>
            <option key={choice} value={choice}>{label(choice)}</option>)}
        </select>
      </label>;
    })}
    <button className="refresh" type="button" onClick={() => onChange(emptyFilters)}
      disabled={!Object.values(value).some(Boolean)}>Clear filters</button>
  </fieldset>;
}
