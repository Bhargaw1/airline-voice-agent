export default function EmptyState({ isOpen }) {
  return (
    <div className={`empty${isOpen ? " is-open" : ""}`} id="empty-state">
      <div className="empty-mark" aria-hidden="true">
        ✈️
      </div>
      <h2>Ask me about a flight</h2>
      <p>Search routes, timings, prices and flight status using natural language.</p>
    </div>
  );
}
