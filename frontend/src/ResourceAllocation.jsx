
import { useEffect, useState } from "react";

const API = "http://127.0.0.1:8000";

export default function ResourceAllocation() {
  const [zone, setZone] = useState("Zone A");
  const [resource, setResource] = useState("Food Packets");
  const [quantity, setQuantity] = useState("10");
  const [priority, setPriority] = useState("High");
  const [resources, setResources] = useState([]);
  const [allocations, setAllocations] = useState([]);
  const [message, setMessage] = useState("");

  async function loadData() {
    try {
      const [r1, r2] = await Promise.all([
        fetch(`${API}/resources`, { cache: "no-store" }),
        fetch(`${API}/allocations`, { cache: "no-store" })
      ]);
      const resourceData = await r1.json();
      const allocationData = await r2.json();
      setResources(resourceData.resources || []);
      setAllocations(allocationData.allocations || []);
    } catch {
      setMessage("Could not load data. Check that the backend is running.");
    }
  }

  useEffect(() => { loadData(); }, []);

  async function submitAllocation(event) {
    event.preventDefault();
    setMessage("");
    try {
      const response = await fetch(`${API}/allocations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          zone, resource_name: resource,
          quantity: Number(quantity), priority
        })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Allocation failed.");
      setMessage("Allocation saved successfully!");
      setQuantity("10");
      await loadData();
    } catch (error) {
      setMessage(error.message || "Could not save allocation.");
    }
  }

  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h3>Resource Allocation</h3>
          <p>Assign available relief resources to disaster zones.</p>
        </div>
        <button type="button" onClick={loadData}>Refresh</button>
      </div>

      <form onSubmit={submitAllocation}>
        <label>Disaster Zone</label>
        <input value={zone} onChange={e => setZone(e.target.value)}
          required maxLength={100} placeholder="Example: Zone A"
          style={{ display: "block", width: "100%", padding: 10, margin: "8px 0 16px" }} />

        <label>Resource</label>
        <select value={resource} onChange={e => setResource(e.target.value)}
          style={{ display: "block", width: "100%", padding: 10, margin: "8px 0 16px" }}>
          {resources.map(item => (
            <option key={item.name} value={item.name}>
              {item.name} — Available: {item.quantity}
            </option>
          ))}
        </select>

        <label>Quantity to Allocate</label>
        <input type="number" min="1" required value={quantity}
          onChange={e => setQuantity(e.target.value)}
          style={{ display: "block", width: "100%", padding: 10, margin: "8px 0 16px" }} />

        <label>Priority</label>
        <select value={priority} onChange={e => setPriority(e.target.value)}
          style={{ display: "block", width: "100%", padding: 10, margin: "8px 0 16px" }}>
          {["Low", "Medium", "High", "Critical"].map(p =>
            <option key={p} value={p}>{p}</option>
          )}
        </select>

        <button type="submit" disabled={resources.length === 0}>
          Save Allocation
        </button>
      </form>

      {message && <p role="status">{message}</p>}

      <h3 style={{ marginTop: 28 }}>Allocation History</h3>
      {allocations.length === 0 ? <p>No allocations yet.</p> :
        <div className="incident-list">
          {allocations.map(item => (
            <div className="incident-row" key={item.id}>
              <div className="incident-info">
                <strong>{item.zone} — {item.resource_name}</strong>
                <p>Quantity: {item.quantity} | Priority: {item.priority}</p>
                <p>{new Date(item.created_at).toLocaleString()}</p>
              </div>
            </div>
          ))}
        </div>
      }
    </section>
  );
}
