export default function SearchCard({
  query,
  onQueryChange,
  onSubmit,
  onMicClick,
  onStopCall,
  isListening,
  listenPanelOpen,
  isRealtimeConfigured,
}) {
  function handleSubmit(event) {
    event.preventDefault();
    onSubmit(query);
  }

  return (
    <form className="search-card" id="search-form" onSubmit={handleSubmit}>
      <div className="search-row">
        <div className="search-field">
          <label className="hidden" htmlFor="query">
            Flight question
          </label>
          <textarea
            id="query"
            rows="1"
            autoComplete="off"
            placeholder="Ask about flights, routes, timings, prices or status..."
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                onSubmit(query);
              }
            }}
          />
        </div>
        <button
          className={`icon-btn mic-btn${isListening ? " is-listening" : ""}`}
          id="mic-btn"
          type="button"
          title="Voice input"
          aria-label="Start voice input"
          onClick={onMicClick}
          disabled={isRealtimeConfigured === false}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <rect x="9" y="3" width="6" height="12" rx="3" stroke="currentColor" strokeWidth="1.8" />
            <path d="M5 11a7 7 0 0 0 14 0" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            <path d="M12 18v3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
        </button>
        <button className="icon-btn send-btn" id="send-btn" type="submit" aria-label="Search">
          <span className="send-label">Search</span>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M5 12h14M13 6l6 6-6 6" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>

      <div className={`listen-panel${listenPanelOpen ? " is-open" : ""}`} id="listen-panel">
        <div className="listen-copy">
          <strong className="listen-live">
            <i /> Listening...
          </strong>
          <span>Speak your flight query</span>
        </div>
        <div className="wave" aria-hidden="true">
          <span /><span /><span /><span /><span /><span /><span />
        </div>
        <button className="stop-btn" id="stop-btn" type="button" onClick={onStopCall}>
          Stop
        </button>
      </div>
    </form>
  );
}
