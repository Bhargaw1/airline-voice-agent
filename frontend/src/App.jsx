import React, { useState, useCallback, useEffect, useRef } from "react";
import { TRY_QUERIES } from "./constants.js";
import { useRealtimeAgent } from "./hooks/useRealtimeAgent.js";

import Header from "./components/Header.jsx";
import Hero from "./components/Hero.jsx";
import SearchCard from "./components/SearchCard.jsx";
import Suggestions from "./components/Suggestions.jsx";
import EmptyState from "./components/EmptyState.jsx";
import ResultsToolbar from "./components/ResultsToolbar.jsx";
import FlightTable from "./components/FlightTable.jsx";

export default function App() {
  const [query, setQuery] = useState("");
  const [statusMessage, setStatusMessage] = useState("Agent Offline");
  const [statusActive, setStatusActive] = useState(false);
  const [realtimeConfigured, setRealtimeConfigured] = useState(false);

  const [flightData, setFlightData] = useState(null);
  const [, setBookingHandoff] = useState(null);

  const [sortBy, setSortBy] = useState("recommended");
  const [priceFilter, setPriceFilter] = useState("all");
  const [timeFilter, setTimeFilter] = useState("all");
  const [airlineFilter, setAirlineFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");

  const setStatus = useCallback((message, active = false) => {
    setStatusMessage(message);
    setStatusActive(active);
  }, []);

  const isNewTurnRef = useRef(true);

  const handleTurnComplete = useCallback(() => {
    isNewTurnRef.current = true;
  }, []);

  const handleInterrupted = useCallback(() => {
    isNewTurnRef.current = true;
  }, []);

  const handleInputTranscription = useCallback(() => {
    isNewTurnRef.current = true;
  }, []);

  const clearFlightResults = useCallback(() => {
    setFlightData(null);
    setSortBy("recommended");
    setPriceFilter("all");
    setTimeFilter("all");
    setAirlineFilter("all");
    setStatusFilter("all");
  }, []);

  const handleFlightResults = useCallback((rows, meta = {}) => {
    if (!Array.isArray(rows) || rows.length === 0) return;
    setFlightData({
      flight_results: rows,
      count: meta.count ?? rows.length,
      truncated: !!meta.truncated,
      widened: !!meta.widened,
    });
    setSortBy("recommended");
    setPriceFilter("all");
    setTimeFilter("all");
    setAirlineFilter("all");
    setStatusFilter("all");
  }, []);

  const {
    isCalling,
    realtimeConnected,
    isListening,
    stopAgentCall,
    handleMicClick,
  } = useRealtimeAgent({
    onFlightResults: handleFlightResults,
    onSessionEnd: clearFlightResults,
    onTurnComplete: handleTurnComplete,
    onInterrupted: handleInterrupted,
    onInputTranscription: handleInputTranscription,
    setStatus,
    isConfigured: realtimeConfigured,
  });

  const handleChipSelect = useCallback((nextQuery) => {
    setQuery(nextQuery);
  }, []);

  const handleTextSubmit = useCallback(() => {
    // Voice-first: use the mic to ask your question.
  }, []);

  useEffect(() => {
    const backendUrl = import.meta.env.VITE_BACKEND_URL || "http://127.0.0.1:8000";
    fetch(`${backendUrl}/health`)
      .then((res) => res.json())
      .then((data) => setRealtimeConfigured(data?.services?.gemini_live === "configured"))
      .catch(() => setRealtimeConfigured(false));
  }, []);

  const flightsList = flightData?.flight_results || [];

  const generatePriceRanges = (flights) => {
    const fares = flights.map((f) => Number(f.total_fare_inr || f.price_inr || f.fare || 0)).filter((f) => f > 0);
    if (fares.length === 0) return [];
    const min = Math.min(...fares);
    const max = Math.max(...fares);
    if (max - min < 500) {
      return [{ label: `Under ₹${Math.ceil(max).toLocaleString("en-IN")}`, maxVal: Math.ceil(max) }];
    }
    const step = (max - min) / 3;
    const r1 = min + step;
    const r2 = min + 2 * step;
    return [
      { label: `Under ₹${Math.ceil(r1).toLocaleString("en-IN")}`, maxVal: Math.ceil(r1) },
      { label: `Under ₹${Math.ceil(r2).toLocaleString("en-IN")}`, maxVal: Math.ceil(r2) },
      { label: `Under ₹${Math.ceil(max).toLocaleString("en-IN")}`, maxVal: Math.ceil(max) },
    ];
  };

  const priceRanges = generatePriceRanges(flightsList);
  const airlines = Array.from(new Set(flightsList.map((f) => f.airline).filter(Boolean)));
  const statuses = Array.from(new Set(flightsList.map((f) => f.flight_status || f.status).filter(Boolean)));

  const checkDepartureTime = (timeStr, filter) => {
    if (filter === "all") return true;
    if (!timeStr) return false;
    const hour = parseInt(timeStr.split(":")[0], 10);
    if (isNaN(hour)) return false;
    switch (filter) {
      case "morning":
        return hour >= 5 && hour < 12;
      case "afternoon":
        return hour >= 12 && hour < 17;
      case "evening":
        return hour >= 17 && hour < 21;
      case "night":
        return hour >= 21 || hour < 5;
      default:
        return true;
    }
  };

  const sortFlights = (a, b, criterion) => {
    if (criterion === "recommended") return 0;
    if (criterion === "cheapest") {
      const priceA = Number(a.total_fare_inr || a.price_inr || a.fare || 0);
      const priceB = Number(b.total_fare_inr || b.price_inr || b.fare || 0);
      return priceA - priceB;
    }
    if (criterion === "earliest") {
      const depA = a.departure_time || "23:59:59";
      const depB = b.departure_time || "23:59:59";
      return depA.localeCompare(depB);
    }
    if (criterion === "shortest") {
      const durA = Number(a.total_journey_duration_minutes || a.duration_minutes || 0);
      const durB = Number(b.total_journey_duration_minutes || b.duration_minutes || 0);
      return durA - durB;
    }
    return 0;
  };

  const filteredFlights = flightsList.filter((f) => {
    if (priceFilter !== "all") {
      const priceVal = Number(f.total_fare_inr || f.price_inr || f.fare || 0);
      const limit = Number(priceFilter);
      if (priceVal > limit) return false;
    }
    if (!checkDepartureTime(f.departure_time, timeFilter)) return false;
    if (airlineFilter !== "all" && f.airline !== airlineFilter) return false;
    if (statusFilter !== "all" && (f.flight_status || f.status) !== statusFilter) return false;
    return true;
  });

  const processedFlights = [...filteredFlights].sort((a, b) => sortFlights(a, b, sortBy));

  const uniqueDates = Array.from(new Set(processedFlights.map((f) => f.flight_date).filter(Boolean)));
  const spanMultipleDates = uniqueDates.length > 1;

  const formatDateHeader = (dateStr) => {
    if (!dateStr) return "";
    const dateObj = new Date(dateStr.split("T")[0]);
    if (isNaN(dateObj.getTime())) return dateStr;
    return dateObj.toLocaleDateString("en-US", {
      weekday: "short",
      day: "numeric",
      month: "short",
      year: "numeric",
    }).toUpperCase();
  };

  const showToolbar = flightsList.length > 0;

  const handleSelectFlight = useCallback((flight) => {
    setBookingHandoff({
      status: "transferring",
      message: `Connecting you to a ticketing specialist for flight ${flight.flight_number || flight.flightNumber || ""}...`,
    });
  }, []);

  const renderFlightSection = () => {
    if (!flightData || flightsList.length === 0) return null;

    if (processedFlights.length === 0) {
      return (
        <div style={{ padding: "20px", background: "var(--navy-2)", border: "1px dashed var(--line)", borderRadius: "16px", textAlign: "center", color: "var(--muted)", marginBottom: "22px", maxWidth: "880px", margin: "0 auto 22px" }}>
          No flights matched your filters.
        </div>
      );
    }

    if (spanMultipleDates) {
      const grouped = {};
      processedFlights.forEach((f) => {
        const d = f.flight_date || "Unknown Date";
        if (!grouped[d]) grouped[d] = [];
        grouped[d].push(f);
      });

      const sortedDates = Object.keys(grouped).sort();

      return (
        <div style={{ marginBottom: "22px" }}>
          {sortedDates.map((dateStr) => (
            <div key={dateStr} style={{ marginBottom: "20px" }}>
              <h4 style={{
                fontSize: "0.85rem",
                color: "var(--gold)",
                letterSpacing: "0.12em",
                textTransform: "uppercase",
                marginBottom: "12px",
                borderBottom: "1px dashed var(--line)",
                paddingBottom: "6px",
                maxWidth: "880px",
                margin: "0 auto 12px",
              }}>
                {formatDateHeader(dateStr)}
              </h4>
              <FlightTable flights={grouped[dateStr]} onSelectFlight={handleSelectFlight} />
            </div>
          ))}
        </div>
      );
    }

    return (
      <FlightTable flights={processedFlights} onSelectFlight={handleSelectFlight} />
    );
  };

  const showEmptyState = !realtimeConnected && !isCalling && flightsList.length === 0;

  return (
    <div className="app">
      <Header
        statusMessage={statusMessage}
        statusActive={statusActive}
        isCalling={isCalling}
        realtimeConnected={realtimeConnected}
        onStartCall={handleMicClick}
        isRealtimeConfigured={realtimeConfigured}
      />

      <Hero />

      <SearchCard
        query={query}
        onQueryChange={setQuery}
        onSubmit={handleTextSubmit}
        onMicClick={handleMicClick}
        onStopCall={stopAgentCall}
        isListening={isListening}
        listenPanelOpen={realtimeConnected}
        isRealtimeConfigured={realtimeConfigured}
      />

      <Suggestions queries={TRY_QUERIES} onSelect={handleChipSelect} />

      <section className="stage" aria-live="polite">
        <EmptyState isOpen={showEmptyState} />

        <ResultsToolbar
          isOpen={showToolbar}
          count={flightData?.count || 0}
          filteredCount={processedFlights.length}
          truncated={!!flightData?.truncated}
          widened={!!flightData?.widened}
          priceRanges={priceRanges}
          airlines={airlines}
          statuses={statuses}
          sortBy={sortBy}
          priceFilter={priceFilter}
          timeFilter={timeFilter}
          airlineFilter={airlineFilter}
          statusFilter={statusFilter}
          onSortChange={setSortBy}
          onPriceChange={setPriceFilter}
          onTimeChange={setTimeFilter}
          onAirlineChange={setAirlineFilter}
          onStatusChange={setStatusFilter}
        />

        {renderFlightSection()}
      </section>
    </div>
  );
}
