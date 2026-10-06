export function displayDate(value: string | null | undefined): string {
  if (!value) return "—";
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  return match ? `${match[3]}.${match[2]}.${match[1]}` : value;
}
export function displayValue(value: unknown, dataType?: string): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Ja" : "Nein";
  if (Array.isArray(value)) return value.length ? value.join(", ") : "—";
  if (dataType === "date" && typeof value === "string")
    return displayDate(value);
  return String(value);
}
