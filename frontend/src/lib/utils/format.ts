export function displayValue(value: unknown, unit = '') {
  if (value === null || value === undefined || value === '') return 'Unavailable';
  return `${value}${unit ? ` ${unit}` : ''}`;
}

export function displayDate(value: string | null | undefined) {
  if (!value) return 'Never';
  return new Intl.DateTimeFormat('en', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
}
