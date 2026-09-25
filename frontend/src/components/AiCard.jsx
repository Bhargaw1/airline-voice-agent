export default function AiCard({ isOpen, isError, text }) {
  return (
    <article
      className={`ai-card${isOpen ? " is-open" : ""}${isError ? " is-error" : ""}`}
      id="ai-card"
    >
      <div className="ai-avatar" aria-hidden="true">
        ✦
      </div>
      <div>
        <h2>AI Assistant</h2>
        <p id="ai-text">{text}</p>
        <p className="hint-line hidden" id="ai-hint" />
      </div>
    </article>
  );
}
