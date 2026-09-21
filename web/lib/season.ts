/** Formats a season-start year as the "2024-25" style label used across nba_api exports. */
export function formatSeason(startYear: number): string {
  const endYear = (startYear + 1) % 100;
  return `${startYear}-${endYear.toString().padStart(2, "0")}`;
}
