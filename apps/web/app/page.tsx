import { Stations } from "../components/stations";

export default async function Home({ searchParams }: {
  searchParams: Promise<{ station?: string | string[] }>;
}) {
  const { station } = await searchParams;
  const initialCaseId = typeof station === "string" ? station : null;
  return <Stations key={initialCaseId ?? "list"} initialCaseId={initialCaseId} />;
}
