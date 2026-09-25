export function getAirlineCode(airline) {
  if (!airline) {
    return "✈";
  }

  const name = airline.toLowerCase();

  if (name.includes("air india")) {
    return "AI";
  }

  if (name.includes("indigo")) {
    return "6E";
  }

  if (name.includes("vistara")) {
    return "UK";
  }

  if (name.includes("spicejet")) {
    return "SG";
  }

  return airline.substring(0, 2).toUpperCase();
}

export function getStatusClass(status) {
  const value = String(status || "On Time");
  const lower = value.toLowerCase();

  if (lower.includes("delay")) {
    return "delayed";
  }

  if (lower.includes("cancel")) {
    return "cancelled";
  }

  return "on-time";
}

export function applySearchResults(data) {
  const results = Array.isArray(data?.results) ? data.results : [];

  if (data?.error) {
    return {
      results: [],
      aiResponse: data.error,
      isError: true,
      showEmpty: true,
      showToolbar: false,
    };
  }

  return {
    results,
    aiResponse: data?.aiResponse || "",
    isError: false,
    showEmpty: results.length === 0,
    showToolbar: results.length > 0,
  };
}
