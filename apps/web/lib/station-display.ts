export function label(value: string): string {
  const text = value.replaceAll(/[_-]/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function duration(seconds: number): string {
  return seconds % 60 ? `${seconds} s` : `${seconds / 60} min`;
}
