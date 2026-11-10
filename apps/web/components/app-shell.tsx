import Link from "next/link";
import type { ReactNode } from "react";
import { AppHeader } from "./app-header";

export function AppShell({ current, children }: {
  current: "stations" | "blueprint" | "status" | "authoring";
  children: ReactNode;
}) {
  return <>
    <AppHeader current={current} />
    <main className="content">
      {current !== "stations" && <Link className="back-home" href="/">← Back to home</Link>}
      {children}
      <footer>CascAid · Educational research prototype. Not clinical decision support. All inference runs on this machine.</footer>
    </main>
  </>;
}
