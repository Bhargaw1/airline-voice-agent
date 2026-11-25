import React from "react";

export default function ResultsToolbar({
  isOpen,
  count,
  filteredCount,
  truncated,
  widened,
  priceRanges,
  airlines,
  statuses,
  sortBy,
  priceFilter,
  timeFilter,
  airlineFilter,
  statusFilter,
  onSortChange,
  onPriceChange,
  onTimeChange,
  onAirlineChange,
  onStatusChange,
}) {
  return (
    <div className={`toolbar${isOpen ? " is-open" : ""}`} id="toolbar" style={{ width: "100%", maxWidth: "880px", margin: "0 auto 14px" }}>
      <div style={{ flex: 1, minWidth: "200px" }}>
        <h3 style={{ margin: 0 }}>Flight results</h3>
        <p className="results-meta" id="results-meta" style={{ margin: "4px 0 0" }}>
          Showing {filteredCount} of {count} flights{truncated ? " (first 100 shown)" : ""}
        </p>
        {widened && (
          <p style={{ margin: "6px 0 0", color: "var(--delayed)", fontSize: "0.85rem", fontWeight: 600 }}>
            No exact match. Showing the nearest available dates.
          </p>
        )}
      </div>
      <div className="filters">
        <div className="field">
          <label htmlFor="sort">Sort by</label>
          <select id="sort" value={sortBy} onChange={(e) => onSortChange(e.target.value)}>
            <option value="recommended">Recommended</option>
            <option value="cheapest">Cheapest</option>
            <option value="earliest">Earliest</option>
            <option value="shortest">Shortest</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="filter-price">Price</label>
          <select id="filter-price" value={priceFilter} onChange={(e) => onPriceChange(e.target.value)}>
            <option value="all">Any price</option>
            {priceRanges.map((range) => (
              <option key={range.maxVal} value={String(range.maxVal)}>
                {range.label}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="filter-time">Departure</label>
          <select id="filter-time" value={timeFilter} onChange={(e) => onTimeChange(e.target.value)}>
            <option value="all">Any time</option>
            <option value="morning">Morning</option>
            <option value="afternoon">Afternoon</option>
            <option value="evening">Evening</option>
            <option value="night">Night</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="filter-airline">Airline</label>
          <select id="filter-airline" value={airlineFilter} onChange={(e) => onAirlineChange(e.target.value)}>
            <option value="all">All airlines</option>
            {airlines.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="filter-status">Status</label>
          <select id="filter-status" value={statusFilter} onChange={(e) => onStatusChange(e.target.value)}>
            <option value="all">All statuses</option>
            {statuses.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}
