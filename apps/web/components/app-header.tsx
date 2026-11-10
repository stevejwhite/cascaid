import Link from "next/link";

export function AppHeader({ current }: {
  current: "stations" | "blueprint" | "status" | "authoring";
}) {
  return <header className="topbar">
    <Link className="brand" href="/" aria-label="CascAid home"><span className="brand-mark" aria-hidden="true">Ψ</span>CascAid <span className="brand-light">CASC practice</span></Link>
    <nav aria-label="Main navigation" className="main-nav">
      <Link href="/" aria-current={current === "stations" ? "page" : undefined}>Home</Link>
      <Link href="/blueprint" aria-current={current === "blueprint" ? "page" : undefined}>Matrix</Link>
      <Link href="/status" aria-current={current === "status" ? "page" : undefined}>Status</Link>
    </nav>
    <span className="environment-tag">LOCAL ONLY · FICTIONAL CASES · NOT CLINICALLY VALIDATED</span>
  </header>;
}
