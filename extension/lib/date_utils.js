// Date Utility Functions for Weekly & Custom Range Calculations

export function formatDateRangeLabel(startDate, endDate) {
  const sDay = startDate.getDate();
  const eDay = endDate.getDate();
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const sMonth = months[startDate.getMonth()];
  const eMonth = months[endDate.getMonth()];
  const yearShort = String(endDate.getFullYear()).slice(-2);

  if (startDate.getMonth() === endDate.getMonth()) {
    return `${sDay} - ${eDay} ${sMonth}'${yearShort}`;
  } else {
    return `${sDay} ${sMonth} - ${eDay} ${eMonth}'${yearShort}`;
  }
}

export function formatISODate(d) {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

/**
 * Returns Monday-Sunday weekly date ranges for the previous `numWeeks`.
 * In ISO calendar, Monday is day 1, Sunday is day 7.
 */
export function getWeeklyDateRanges(numWeeks = 1) {
  const ranges = [];
  const today = new Date();

  // Calculate most recent completed Sunday
  const currentDayOfWeek = today.getDay(); // 0 = Sun, 1 = Mon, ..., 6 = Sat
  const daysSinceSunday = currentDayOfWeek === 0 ? 7 : currentDayOfWeek;
  const lastSunday = new Date(today);
  lastSunday.setDate(today.getDate() - daysSinceSunday);
  lastSunday.setHours(23, 59, 59, 999);

  for (let i = 0; i < numWeeks; i++) {
    const end = new Date(lastSunday);
    end.setDate(lastSunday.getDate() - (i * 7));

    const start = new Date(end);
    start.setDate(end.getDate() - 6);
    start.setHours(0, 0, 0, 0);

    const label = formatDateRangeLabel(start, end);
    ranges.push({
      startDate: start,
      endDate: end,
      startISO: formatISODate(start),
      endISO: formatISODate(end),
      label: label
    });
  }

  return ranges;
}

export function getCustomDates(startDateStr, endDateStr) {
  const start = new Date(startDateStr);
  const end = new Date(endDateStr);
  start.setHours(0, 0, 0, 0);
  end.setHours(23, 59, 59, 999);
  const label = formatDateRangeLabel(start, end);

  return {
    startDate: start,
    endDate: end,
    startISO: formatISODate(start),
    endISO: formatISODate(end),
    label: label
  };
}
