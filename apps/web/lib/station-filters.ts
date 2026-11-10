import type { CaseSummary } from "./api";

export interface StationFilters {
  query: string;
  skill: string;
  specialty: string;
  subdivision: string;
  role: string;
}

export const emptyFilters: StationFilters = { query: "", skill: "", specialty: "", subdivision: "", role: "" };

export function filterStations(stations: CaseSummary[], filters: StationFilters): CaseSummary[] {
  const words = filters.query.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
  return stations.filter((station) => {
    if (["skill", "specialty", "subdivision", "role"].some((key) => {
      const field = key as Exclude<keyof StationFilters, "query">;
      return filters[field] && station[field] !== filters[field];
    })) return false;
    const text = [station.title, station.id, station.candidate_instructions, station.skill,
      station.specialty, station.subdivision, station.role].join(" ").replaceAll(/[_-]/g, " ").toLocaleLowerCase();
    return words.every((word) => text.includes(word));
  });
}
