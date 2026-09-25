// import { useState, useCallback, useEffect } from "react";
// import { executeTool } from "./api.js";
// import { TRY_QUERIES } from "./constants.js";
// import { useRealtimeAgent } from "./hooks/useRealtimeAgent.js";

// // UI Components
// import Header from "./components/Header.jsx";
// import Hero from "./components/Hero.jsx";
// import SearchCard from "./components/SearchCard.jsx";
// import Suggestions from "./components/Suggestions.jsx";
// import EmptyState from "./components/EmptyState.jsx";
// import Processing from "./components/Processing.jsx";
// import AiCard from "./components/AiCard.jsx";
// import ResultsToolbar from "./components/ResultsToolbar.jsx";
// import FlightCard from "./components/FlightCard.jsx";
// import FlightTicketCard from "./components/FlightTicketCard.jsx";

// export default function App() {
//   const [query, setQuery] = useState("");
//   const [statusMessage, setStatusMessage] = useState("Agent Offline");
//   const [statusActive, setStatusActive] = useState(false);
//   const [processing, setProcessing] = useState(false);
//   const [results, setResults] = useState([]);
//   const [showEmpty, setShowEmpty] = useState(true);
//   const [showToolbar, setShowToolbar] = useState(false);
//   const [aiOpen, setAiOpen] = useState(false);
//   const [aiError, setAiError] = useState(false);
//   const [aiText, setAiText] = useState("");
//   const [realtimeConfigured, setRealtimeConfigured] = useState(false);
//   const [currentFlight, setCurrentFlight] = useState(null);

//   const setStatus = useCallback((message, active = false) => {
//     setStatusMessage(message);
//     setStatusActive(active);
//   }, []);

//   const applyFlightResults = useCallback((data, toolName) => {
//     setProcessing(false);

//     if (toolName === "search_flights") {
//       setCurrentFlight(Array.isArray(data?.flights) ? data.flights[0] || null : null);
//     }

//     if (data?.error) {
//       setStatus("Agent Error", false);
//       setAiOpen(true);
//       setAiError(true);
//       setAiText(data.error);
//       return;
//     }

//     if (data?.low_confidence) {
//       setAiOpen(true);
//       setAiError(false);
//       setAiText(`${data.aiResponse || ""} I want to make sure this is accurate for your specific case. Let me connect you to a specialist to verify.`.trim());
//     }

//     const hasTicketFlight = toolName === "search_flights" && Array.isArray(data?.flights) && data.flights.length > 0;
//     const nextResults = Array.isArray(data?.results)
//       ? data.results
//       : data?.flight_number
//         ? [{
//             flightNumber: data.flight_number,
//             airline: data.airline,
//             status: data.status,
//             origin: data.origin,
//             destination: data.destination,
//             departure: data.departure_time,
//             arrival: data.arrival_time,
//             availableSeats: data.available_seats,
//           }]
//         : [];

//     if (data?.aiResponse && !data?.low_confidence) {
//       setAiOpen(true);
//       setAiError(false);
//       setAiText(data.aiResponse);
//     }

//     setResults(nextResults);
//     setShowEmpty(!nextResults.length && !hasTicketFlight);
//     setShowToolbar(nextResults.length > 0 || hasTicketFlight);
//   }, [setStatus]);

//   const {
//     isCalling,
//     realtimeConnected,
//     isListening,
//     startAgentCall,
//     stopAgentCall,
//     handleMicClick,
//   } = useRealtimeAgent({
//     onFlightResults: applyFlightResults,
//     setStatus,
//     isConfigured: realtimeConfigured,
//   });

//   const performTextSearch = useCallback(
//     async (nextQuery) => {
//       if (!nextQuery.trim()) return;

//       setStatus("Searching...", true);
//       setProcessing(true);

//       try {
//         const result = await executeTool("search_policy", {
//           query: nextQuery,
//           category: null,
//         });
//         applyFlightResults(result);
//         setStatus(realtimeConnected ? "Agent Online" : "Agent Offline", realtimeConnected);
//       } catch (error) {
//         setProcessing(false);
//         setStatus("Agent Error", false);
//         setAiOpen(true);
//         setAiError(true);
//         setAiText(error.message || "Search failed");
//       }
//     },
//     [applyFlightResults, realtimeConnected, setStatus]
//   );

//   const handleChipSelect = useCallback(
//     (nextQuery) => {
//       setQuery(nextQuery);
//       performTextSearch(nextQuery);
//     },
//     [performTextSearch]
//   );

//   useEffect(() => {
//     const backendUrl = import.meta.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000';
//     fetch(`${backendUrl}/health`)
//       .then((res) => res.json())
//       .then((data) => setRealtimeConfigured(data?.services?.gemini_live === 'configured'))
//       .catch(() => setRealtimeConfigured(false));
//   }, []);

//   return (
//     <div className="app">
//       <Header
//         statusMessage={statusMessage}
//         statusActive={statusActive}
//         isCalling={isCalling}
//         realtimeConnected={realtimeConnected}
//         onStartCall={handleMicClick}
//         isRealtimeConfigured={realtimeConfigured}
//       />

//       <Hero />

//       <SearchCard
//         query={query}
//         onQueryChange={setQuery}
//         onSubmit={performTextSearch}
//         onMicClick={handleMicClick}
//         onStopCall={stopAgentCall}
//         isListening={isListening}
//         listenPanelOpen={realtimeConnected}
//         isRealtimeConfigured={realtimeConfigured}
//       />

//       <Suggestions queries={TRY_QUERIES} onSelect={handleChipSelect} />

//       <section className="stage" aria-live="polite">
//         <EmptyState isOpen={showEmpty} />
//         <Processing isOpen={processing} />
//         <AiCard isOpen={aiOpen} isError={aiError} text={aiText} />
//         <ResultsToolbar isOpen={showToolbar} />
//         <div className="cards" id="cards">
//           {currentFlight && (
//             <FlightTicketCard
//               airline={currentFlight.airline}
//               origin={currentFlight.origin}
//               destination={currentFlight.destination}
//               price={currentFlight.price_inr}
//               flightNumber={currentFlight.flight_number}
//               departureTime={currentFlight.departure_time}
//               date={currentFlight.flight_date}
//             />
//           )}
//           {results.map((flight, index) => (
//             <FlightCard
//               key={`${flight.flightNumber || 'policy'}-${index}`}
//               flight={flight}
//             />
//           ))}
//         </div>
//       </section>
//     </div>
//   );
// }


import { useState, useCallback, useEffect } from "react";
import { executeTool } from "./api.js";
import { TRY_QUERIES } from "./constants.js";
import { useRealtimeAgent } from "./hooks/useRealtimeAgent.js";

// UI Components
import Header from "./components/Header.jsx";
import Hero from "./components/Hero.jsx";
import SearchCard from "./components/SearchCard.jsx";
import Suggestions from "./components/Suggestions.jsx";
import EmptyState from "./components/EmptyState.jsx";
import Processing from "./components/Processing.jsx";
import AiCard from "./components/AiCard.jsx";
import ResultsToolbar from "./components/ResultsToolbar.jsx";
import FlightCard from "./components/FlightCard.jsx";
import FlightTicketCard from "./components/FlightTicketCard.jsx";

export default function App() {
  const [query, setQuery] = useState("");
  const [statusMessage, setStatusMessage] = useState("Agent Offline");
  const [statusActive, setStatusActive] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [results, setResults] = useState([]);
  const [showEmpty, setShowEmpty] = useState(true);
  const [showToolbar, setShowToolbar] = useState(false);
  const [aiOpen, setAiOpen] = useState(false);
  const [aiError, setAiError] = useState(false);
  const [aiText, setAiText] = useState("");
  const [realtimeConfigured, setRealtimeConfigured] = useState(false);
  const [currentFlight, setCurrentFlight] = useState(null);

  const setStatus = useCallback((message, active = false) => {
    setStatusMessage(message);
    setStatusActive(active);
  }, []);

  const applyFlightResults = useCallback((data, toolName) => {
    setProcessing(false);

    let nextResults = [];
    let hasTicketFlight = false;

    // FIX: Safely separate flights from policy searches
    if (toolName === "search_flights" || data?.flights) {
      const flights = data.flights || [];
      if (flights.length > 0) {
        setCurrentFlight(flights[0]);
        hasTicketFlight = true;
        // The remaining flights go into the list below the ticket
        nextResults = flights.slice(1).map(f => ({
          flightNumber: f.flight_number,
          airline: f.airline,
          status: f.flight_status || f.status || 'On Time',
          origin: f.origin,
          destination: f.destination,
          departure: f.departure_time,
          arrival: f.arrival_time,
          price: f.total_fare_inr || f.price_inr,
          availableSeats: f.available_seats,
        }));
      } else {
        setCurrentFlight(null);
      }
    } else if (data?.flight_number) {
      setCurrentFlight(null);
      nextResults = [{
        flightNumber: data.flight_number,
        airline: data.airline,
        status: data.flight_status || data.status || 'On Time',
        origin: data.origin,
        destination: data.destination,
        departure: data.departure_time,
        arrival: data.arrival_time,
        price: data.total_fare_inr || data.price_inr,
        availableSeats: data.available_seats,
      }];
    } else {
      // It's a policy search or empty response. Clear flights to prevent 0₹ blank cards!
      setCurrentFlight(null);
      nextResults = [];
    }

    if (data?.error) {
      setStatus("Agent Error", false);
      setAiOpen(true);
      setAiError(true);
      setAiText(data.error);
      return;
    }

    if (data?.low_confidence) {
      setAiOpen(true);
      setAiError(false);
      setAiText(`${data.aiResponse || ""} I want to make sure this is accurate for your specific case. Let me connect you to a specialist to verify.`.trim());
    } else if (data?.aiResponse) {
      setAiOpen(true);
      setAiError(false);
      setAiText(data.aiResponse);
    } else if (data?.note) {
      setAiOpen(true);
      setAiError(false);
      setAiText(data.note);
    }

    setResults(nextResults);
    setShowEmpty(!nextResults.length && !hasTicketFlight);
    setShowToolbar(nextResults.length > 0 || hasTicketFlight);
  }, [setStatus]);

  const {
    isCalling,
    realtimeConnected,
    isListening,
    startAgentCall,
    stopAgentCall,
    handleMicClick,
  } = useRealtimeAgent({
    onFlightResults: applyFlightResults,
    setStatus,
    isConfigured: realtimeConfigured,
  });

  const performTextSearch = useCallback(
    async (nextQuery) => {
      if (!nextQuery.trim()) return;

      setStatus("Searching...", true);
      setProcessing(true);

      try {
        const result = await executeTool("search_policy", {
          query: nextQuery,
          category: null,
        });
        // FIX: Explicitly pass the tool name so the app knows it's NOT a flight
        applyFlightResults(result, "search_policy"); 
        setStatus(realtimeConnected ? "Agent Online" : "Agent Offline", realtimeConnected);
      } catch (error) {
        setProcessing(false);
        setStatus("Agent Error", false);
        setAiOpen(true);
        setAiError(true);
        setAiText(error.message || "Search failed");
      }
    },
    [applyFlightResults, realtimeConnected, setStatus]
  );

  const handleChipSelect = useCallback(
    (nextQuery) => {
      setQuery(nextQuery);
      performTextSearch(nextQuery);
    },
    [performTextSearch]
  );

  useEffect(() => {
    const backendUrl = import.meta.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000';
    fetch(`${backendUrl}/health`)
      .then((res) => res.json())
      .then((data) => setRealtimeConfigured(data?.services?.gemini_live === 'configured'))
      .catch(() => setRealtimeConfigured(false));
  }, []);

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
        onSubmit={performTextSearch}
        onMicClick={handleMicClick}
        onStopCall={stopAgentCall}
        isListening={isListening}
        listenPanelOpen={realtimeConnected}
        isRealtimeConfigured={realtimeConfigured}
      />

      <Suggestions queries={TRY_QUERIES} onSelect={handleChipSelect} />

      <section className="stage" aria-live="polite">
        <EmptyState isOpen={showEmpty} />
        <Processing isOpen={processing} />
        <AiCard isOpen={aiOpen} isError={aiError} text={aiText} />
        <ResultsToolbar isOpen={showToolbar} />
        <div className="cards" id="cards">
          {currentFlight && (
            <FlightTicketCard
              airline={currentFlight.airline}
              origin={currentFlight.origin}
              destination={currentFlight.destination}
              price={Number(currentFlight.total_fare_inr || currentFlight.price_inr || 0).toLocaleString("en-IN")}
              flightNumber={currentFlight.flight_number}
              departureTime={currentFlight.departure_time}
              date={currentFlight.flight_date}
            />
          )}
          {results.map((flight, index) => (
            <FlightCard
              key={`${flight.flightNumber || 'policy'}-${index}`}
              flight={flight}
            />
          ))}
        </div>
      </section>
    </div>
  );
}