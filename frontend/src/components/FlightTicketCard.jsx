import React from 'react';
import './FlightTicketCard.css';

const FlightTicketCard = ({
  airline,
  origin,
  destination,
  price,
  flightNumber,
  departureTime,
  date
}) => {
  return (
    <div className="ticket-wrapper">
      <div className="ticket-main">
        <div className="ticket-header">
          <div className="ticket-title">
            <span>Airline Ticket</span>
            <svg className="ticket-plane" viewBox="0 0 24 24">
              <path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" />
            </svg>
          </div>
          <span className="ticket-class">{airline}</span>
        </div>

        <div className="ticket-content">
          <div className="ticket-barcode-side">
            <div className="ticket-barcode-vertical"></div>
          </div>

          <div className="ticket-details">
            <div className="ticket-top-row">
              <div className="ticket-summary">
                <div>
                  <p className="ticket-label">Flight</p>
                  <p className="ticket-value">{flightNumber}</p>
                </div>
                <div>
                  <p className="ticket-label">Date</p>
                  <p className="ticket-value ticket-value-uppercase">{date}</p>
                </div>
              </div>
            </div>

            <div className="ticket-route-row">
              <div className="ticket-route-details">
                <div className="ticket-route-item">
                  <p className="ticket-label ticket-route-label">From:</p>
                  <p className="ticket-value ticket-value-large">{origin}</p>
                </div>
                <div className="ticket-route-item">
                  <p className="ticket-label ticket-route-label">To:</p>
                  <p className="ticket-value ticket-value-large">{destination}</p>
                </div>
              </div>

              <div className="ticket-route-meta">
                <div>
                  <p className="ticket-label">Time</p>
                  <p className="ticket-value ticket-value-large">{departureTime}</p>
                </div>
              </div>
            </div>

            <div className="ticket-boarding-row">
              <div className="ticket-boarding-info">
                <p className="ticket-label">Departure</p>
                <p className="ticket-boarding-time">{departureTime}</p>
              </div>
              <div className="ticket-barcode-horizontal"></div>
            </div>
          </div>
        </div>

        <div className="ticket-perforation ticket-perforation-top"></div>
        <div className="ticket-perforation ticket-perforation-bottom"></div>
      </div>

      <div className="ticket-stub">
        <div className="ticket-header">
          <span className="ticket-class">Boarding Pass</span>
          <svg className="ticket-plane ticket-plane-small" viewBox="0 0 24 24">
            <path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" />
          </svg>
        </div>

        <div className="ticket-stub-content">
          <div>
            <p className="ticket-label">From:</p>
            <p className="ticket-value ticket-value-uppercase ticket-value-small ticket-stub-route">{origin}</p>

            <p className="ticket-label">To:</p>
            <p className="ticket-value ticket-value-uppercase ticket-value-small">{destination}</p>
          </div>

          <div className="ticket-stub-grid">
            <div>
              <p className="ticket-label">Flight</p>
              <p className="ticket-value ticket-value-small">{flightNumber}</p>
            </div>
            <div>
              <p className="ticket-label">Date</p>
              <p className="ticket-value ticket-value-small ticket-value-uppercase">{date}</p>
            </div>
          </div>

          <div className="ticket-price-row">
            <p className="ticket-label">Total Price</p>
            <p className="ticket-price">₹{price}</p>
          </div>

          <div className="ticket-stub-barcode"></div>
        </div>
      </div>
    </div>
  );
};

export default FlightTicketCard;