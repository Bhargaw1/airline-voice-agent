import { getAirlineCode, getStatusClass } from "../utils/flights.js";

export default function FlightCard({ flight }) {
  const status = String(flight.status || "On Time");
  const statusClass = getStatusClass(status);
  const airlineCode = getAirlineCode(flight.airline);

  return (
    <div className="flight-card">
      <div className="card-top">
        <div className="airline-row">
          <div className="roundel">{airlineCode}</div>
          <div>
            <div className="flight-no">{flight.flightNumber}</div>
            <div className="airline-name">{flight.airline}</div>
          </div>
        </div>
        <span className={`badge ${statusClass}`}>{status}</span>
      </div>

      <div className="route">
        <div className="city-block">
          <div className="iata">{flight.origin}</div>
          <div className="city">{flight.originCity || flight.origin}</div>
          <div className="clock">{flight.departure}</div>
        </div>

        <div className="path">
          <i />
          <span>{flight.duration || ""}</span>
          <i />
        </div>

        <div className="city-block arr">
          <div className="iata">{flight.destination}</div>
          <div className="city">{flight.destinationCity || flight.destination}</div>
          <div className="clock">{flight.arrival}</div>
        </div>
      </div>

      <div className="card-foot">
        <div className="price">
          ₹{Number(flight.price || 0).toLocaleString("en-IN")}
        </div>
        <div className="seats">{flight.availableSeats ?? 0} seats available</div>
      </div>
    </div>
  );
}
