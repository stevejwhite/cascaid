import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CascAid · CASC interview practice",
  applicationName: "CascAid",
  description: "CascAid is a local educational research prototype for CASC-style simulated psychiatric interviews.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
