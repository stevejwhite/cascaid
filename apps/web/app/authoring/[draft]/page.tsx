import type { Metadata } from "next";
import { AppShell } from "../../../components/app-shell";
import { CaseEditor } from "../../../components/case-editor/case-editor";

export const metadata: Metadata = { title: "Case editor · CascAid" };

export default async function DraftPage({ params }: { params: Promise<{ draft: string }> }) {
  const { draft } = await params;
  return <AppShell current="authoring"><CaseEditor draftId={draft} /></AppShell>;
}
