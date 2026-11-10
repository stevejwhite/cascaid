/** Keep the full accessible title while giving its descriptors their own lines. */
export function StationTitle({ title }: { title: string }) {
  const parts = title.split(/( [—–] |: )/);
  return <span className="station-title">{parts.map((part, index) => index % 2
    ? <span className="sr-only" key={index}>{part}</span>
    : <span className={index === 0 ? "station-title-main" : "station-title-detail"} key={index}>{part}</span>)}</span>;
}
