export default function Processing({ isOpen }) {
  return (
    <div className={`processing${isOpen ? " is-open" : ""}`} id="processing">
      <div className="spinner" aria-hidden="true" />
      <p id="processing-step">Understanding your request...</p>
    </div>
  );
}
