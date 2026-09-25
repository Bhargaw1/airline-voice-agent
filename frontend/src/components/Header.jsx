export default function Header({
  statusMessage,
  statusActive,
  isCalling,
  realtimeConnected,
  onStartCall,
  isRealtimeConfigured,
}) {
  let callLabel = "☎ Start Agent Call";
  if (isCalling && !realtimeConnected) {
    callLabel = "Connecting...";
  } else if (realtimeConnected) {
    callLabel = "☎ Agent Connected";
  }

  return (
    <header className="header">
      <div className="brand">
        <div className="brand-mark" aria-hidden="true">
          ✈️
        </div>
        <span>Flight AI</span>
      </div>
      <div className="header-actions">
        <button
          className="call-btn"
          id="call-btn"
          type="button"
          onClick={onStartCall}
          disabled={isCalling || isRealtimeConfigured === false}
        >
          {callLabel}
        </button>
        <div className="status-pill" id="agent-status">
          <span
            className="status-dot"
            aria-hidden="true"
            style={{ opacity: statusActive ? "1" : "0.5" }}
          />
          <span>{statusMessage}</span>
        </div>
      </div>
    </header>
  );
}
