import type { Metadata } from "next";
import { BlueprintMatrix } from "../../components/blueprint-matrix";

export const metadata: Metadata = { title: "CASC blueprint matrix · CascAid" };

export default function BlueprintPage() {
  return <BlueprintMatrix />;
}
