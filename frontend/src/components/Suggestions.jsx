export default function Suggestions({ queries, onSelect }) {
  return (
    <div className="suggestions" id="suggestions">
      {queries.map((query) => (
        <button
          key={query}
          className="chip"
          type="button"
          data-query={query}
          onClick={() => onSelect(query)}
        >
          {query}
        </button>
      ))}
    </div>
  );
}
