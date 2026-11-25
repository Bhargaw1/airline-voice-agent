import React from 'react';
import { getAirlineCode, getStatusClass } from "../utils/flights.js";

export default function FlightTable({ flights, onSelectFlight }) {
  if (!flights || flights.length === 0) return null;

  const formatDate = (dateStr) => {
    if (!dateStr) return "";
    const dateObj = new Date(dateStr.split("T")[0]);
    if (isNaN(dateObj.getTime())) return dateStr;
    return dateObj.toLocaleDateString("en-US", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  };

  const formatTime = (t) => t ? String(t).substring(0, 5) : "";

  const formatDuration = (mins) => {
    if (!mins) return "";
    const minsNum = Number(mins);
    if (isNaN(minsNum)) return String(mins);
    const h = Math.floor(minsNum / 60);
    const m = minsNum % 60;
    return h > 0 ? `${h}h ${m}m` : `${m}m`;
  };

  return (
    <div style={{
      width: "100%",
      maxWidth: "880px",
      margin: "0 auto 22px",
      background: "var(--navy-2)",
      border: "1px solid var(--line)",
      borderRadius: "16px",
      overflow: "hidden",
      boxShadow: "var(--shadow)"
    }}>
      <div style={{ overflowX: "auto" }}>
        <table style={{
          width: "100%",
          borderCollapse: "collapse",
          textAlign: "left",
          fontSize: "0.92rem",
          color: "var(--ink)"
        }}>
          <thead>
            <tr style={{
              background: "rgba(255, 255, 255, 0.02)",
              borderBottom: "1px solid var(--line)"
            }}>
              <th style={{ padding: "14px 16px", color: "var(--muted)", fontWeight: "600", fontSize: "0.75rem", letterSpacing: "0.08em", textTransform: "uppercase" }}>Airline</th>
              <th style={{ padding: "14px 16px", color: "var(--muted)", fontWeight: "600", fontSize: "0.75rem", letterSpacing: "0.08em", textTransform: "uppercase" }}>Route</th>
              <th style={{ padding: "14px 16px", color: "var(--muted)", fontWeight: "600", fontSize: "0.75rem", letterSpacing: "0.08em", textTransform: "uppercase" }}>Date</th>
              <th style={{ padding: "14px 16px", color: "var(--muted)", fontWeight: "600", fontSize: "0.75rem", letterSpacing: "0.08em", textTransform: "uppercase" }}>Timing</th>
              <th style={{ padding: "14px 16px", color: "var(--muted)", fontWeight: "600", fontSize: "0.75rem", letterSpacing: "0.08em", textTransform: "uppercase" }}>Duration</th>
              <th style={{ padding: "14px 16px", color: "var(--muted)", fontWeight: "600", fontSize: "0.75rem", letterSpacing: "0.08em", textTransform: "uppercase" }}>Fare</th>
              <th style={{ padding: "14px 16px", color: "var(--muted)", fontWeight: "600", fontSize: "0.75rem", letterSpacing: "0.08em", textTransform: "uppercase" }}>Status</th>
              <th style={{ padding: "14px 16px", color: "var(--muted)", fontWeight: "600", fontSize: "0.75rem", letterSpacing: "0.08em", textTransform: "uppercase", textAlign: "center" }}>Action</th>
            </tr>
          </thead>
          <tbody>
            {flights.map((flight, idx) => {
              const status = flight.flight_status || flight.status || "On Time";
              const statusClass = getStatusClass(status);
              const airlineCode = getAirlineCode(flight.airline);
              const roundelClass = airlineCode === "6E" ? "indigo" : airlineCode.toLowerCase();
              const fare = flight.total_fare_inr || flight.price_inr || flight.fare || 0;
              const seats = flight.available_seats;

              return (
                <tr key={`${flight.flight_number || idx}-${idx}`} style={{
                  borderBottom: "1px solid var(--line)",
                  transition: "background 0.2s ease"
                }} className="table-row-hover">
                  <td style={{ padding: "16px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                      <div className={`roundel ${roundelClass}`} style={{ width: "32px", height: "32px", borderRadius: "8px", fontSize: "0.68rem" }}>
                        {airlineCode}
                      </div>
                      <div>
                        <div style={{ fontWeight: "700", fontFamily: "monospace", fontSize: "0.95rem" }}>{flight.flight_number || flight.flightNumber}</div>
                        <div style={{ fontSize: "0.75rem", color: "var(--muted)", marginTop: "1px" }}>{flight.airline}</div>
                      </div>
                    </div>
                  </td>
                  <td style={{ padding: "16px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                      <strong style={{ fontSize: "1.05rem" }}>{flight.origin}</strong>
                      <span style={{ color: "var(--muted)", fontSize: "0.85rem" }}>→</span>
                      <strong style={{ fontSize: "1.05rem" }}>{flight.destination}</strong>
                    </div>
                  </td>
                  <td style={{ padding: "16px", color: "var(--muted)", fontSize: "0.85rem", fontWeight: "500" }}>
                    {formatDate(flight.flight_date)}
                  </td>
                  <td style={{ padding: "16px" }}>
                    <div style={{ fontWeight: "600" }}>
                      {formatTime(flight.departure_time)} <span style={{ color: "var(--muted)", fontWeight: "normal", fontSize: "0.8rem" }}>→</span> {formatTime(flight.arrival_time)}
                    </div>
                  </td>
                  <td style={{ padding: "16px" }}>
                    <div style={{ fontWeight: "500" }}>{formatDuration(flight.total_journey_duration_minutes || flight.duration_minutes)}</div>
                    <div style={{ fontSize: "0.72rem", color: "var(--muted)", marginTop: "2px" }}>
                      {flight.stops === 0 || !flight.stops ? "Non-stop" : `${flight.stops} stop(s)`}
                    </div>
                  </td>
                  <td style={{ padding: "16px" }}>
                    <div style={{ color: "var(--gold)", fontWeight: "700", fontSize: "1.1rem" }}>
                      ₹{Number(fare).toLocaleString("en-IN")}
                    </div>
                    {seats !== undefined && seats !== null && (
                      <div style={{ fontSize: "0.7rem", color: "var(--muted)", marginTop: "2px" }}>
                        {seats} seats left
                      </div>
                    )}
                  </td>
                  <td style={{ padding: "16px" }}>
                    <span className={`badge ${statusClass}`} style={{ fontSize: "0.68rem", padding: "4px 8px" }}>
                      {status}
                    </span>
                  </td>
                  <td style={{ padding: "16px", textAlign: "center" }}>
                    <button
                      type="button"
                      onClick={() => onSelectFlight && onSelectFlight(flight)}
                      style={{
                        padding: "8px 14px",
                        background: "var(--gold)",
                        color: "#1a1404",
                        fontSize: "0.8rem",
                        fontWeight: "600",
                        borderRadius: "8px",
                        border: "none",
                        cursor: "pointer",
                        transition: "filter 0.15s ease"
                      }}
                      className="table-btn-hover"
                    >
                      Book
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
