import type { components } from "./api.generated";
import type { DraftCase } from "./case-draft";

type Schemas = components["schemas"];
export type AuthoringOptions = Schemas["AuthoringOptions"];
export type Choice = Schemas["Choice"];
export type CaseChoice = Schemas["CaseChoice"];
export type DraftSummary = Schemas["DraftSummary"];
export type CheckResult = Schemas["CheckResult"];
export type Preview = Schemas["Preview"];
export type PreviewTurn = Schemas["PreviewTurn"];
export type Export = Schemas["Export"];
export type Draft = Omit<Schemas["Draft"], "case"> & { case: DraftCase };

export class AuthoringError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

const BASE = "/backend/api/authoring";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(BASE + path, {
    cache: "no-store", ...init,
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
  });
  if (!response.ok) {
    const detail = await response.json().then((b) => b.detail).catch(() => undefined);
    const message = typeof detail === "string" ? detail
      : response.status === 404 ? "The case editor is not enabled on this server (set AUTHORING_ENABLED=true for local development)."
      : "The request failed. Check the case editor input and try again.";
    throw new AuthoringError(message, response.status);
  }
  return response.json() as Promise<T>;
}

const body = (value: unknown) => ({ method: "POST", body: JSON.stringify(value) });

export const authoring = {
  options: () => call<AuthoringOptions>("/options"),
  cases: () => call<CaseChoice[]>("/cases"),
  drafts: () => call<DraftSummary[]>("/drafts"),
  create: (request: { author: string; kind: "new" | "revision"; title?: string; source_case_id?: string }) =>
    call<Draft>("/drafts", body(request)),
  load: (id: string) => call<Draft>(`/drafts/${id}`),
  save: (id: string, revision: number, draft: Pick<Draft, "case" | "notes" | "objectives">) =>
    call<Draft>(`/drafts/${id}`, { method: "PUT", body: JSON.stringify({ revision, ...draft }) }),
  check: (id: string, draftCase: DraftCase) => call<CheckResult>(`/drafts/${id}/check`, body({ case: draftCase })),
  preview: (id: string, draftCase: DraftCase, turns: PreviewTurn[]) =>
    call<Preview>(`/drafts/${id}/preview`, body({ case: draftCase, turns })),
  export: (id: string, revision: number) => call<Export>(`/drafts/${id}/export`, body({ revision })),
};
