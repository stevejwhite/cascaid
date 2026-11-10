import type { Metadata } from "next";
import { ServiceStatus } from "../../components/service-status";

export const metadata: Metadata = { title: "Service status · CascAid" };

export default function StatusPage() {
  return <ServiceStatus />;
}
