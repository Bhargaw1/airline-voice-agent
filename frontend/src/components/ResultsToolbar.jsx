export default function ResultsToolbar({ isOpen }) {
  return (
    <div className={`toolbar${isOpen ? " is-open" : ""}`} id="toolbar">
      <div>
        <h3>Flight results</h3>
        <p className="results-meta" id="results-meta" />
      </div>
      <div className="filters">
        <div className="field">
          <label htmlFor="sort">Sort by</label>
          <select id="sort" defaultValue="recommended">
            <option value="recommended">Recommended</option>
            <option value="cheapest">Cheapest</option>
            <option value="earliest">Earliest</option>
            <option value="latest">Latest</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="filter-price">Price</label>
          <select id="filter-price" defaultValue="all">
            <option value="all">Any price</option>
            <option value="5000">Under ₹5,000</option>
            <option value="6000">Under ₹6,000</option>
            <option value="8000">Under ₹8,000</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="filter-time">Departure</label>
          <select id="filter-time" defaultValue="all">
            <option value="all">Any time</option>
            <option value="morning">Morning</option>
            <option value="afternoon">Afternoon</option>
            <option value="evening">Evening</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="filter-airline">Airline</label>
          <select id="filter-airline" defaultValue="all">
            <option value="all">All airlines</option>
            <option value="Air India">Air India</option>
            <option value="IndiGo">IndiGo</option>
            <option value="Vistara">Vistara</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="filter-status">Status</label>
          <select id="filter-status" defaultValue="all">
            <option value="all">All statuses</option>
            <option value="On Time">On Time</option>
            <option value="Delayed">Delayed</option>
            <option value="Cancelled">Cancelled</option>
          </select>
        </div>
      </div>
    </div>
  );
}
