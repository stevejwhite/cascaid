import type { Metadata } from "next";
import { AppShell } from "../../components/app-shell";
import { AuthoringHome } from "../../components/case-editor/authoring-home";

export const metadata: Metadata = { title: "Case drafts · CascAid" };

export default function AuthoringPage() {
  return <AppShell current="authoring"><AuthoringHome /></AppShell>;
}
