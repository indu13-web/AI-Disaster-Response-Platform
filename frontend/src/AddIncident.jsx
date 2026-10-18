
import { useState } from "react";

function AddIncident({ onIncidentAdded, onCancel }) {
  const [form, setForm] = useState({
    title: "",
    disaster_type: "Flood",
    location: "",
    severity: "Medium",
    status: "Active",
    description: "",
  });

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  function handleChange(event) {
    setForm({
      ...form,
      [event.target.name]: event.target.value,
    });
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");

    try {
      const response = await fetch(
        "http://127.0.0.1:8000/incidents",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(form),
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data.detail || "Unable to save incident."
        );
      }

      onIncidentAdded(data.incident);
    } catch (err) {
      setError(err.message || "Could not connect to the backend.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="incident-form">
      <h3>Add New Disaster Incident</h3>

      <label>Incident Title</label>
      <input
        name="title"
        value={form.title}
        onChange={handleChange}
        placeholder="e.g. Chennai Flood Alert"
        required
      />

      <label>Disaster Type</label>
      <select
        name="disaster_type"
        value={form.disaster_type}
        onChange={handleChange}
      >
        <option>Flood</option>
        <option>Earthquake</option>
        <option>Cyclone</option>
        <option>Landslide</option>
        <option>Fire</option>
        <option>Tsunami</option>
        <option>Other</option>
      </select>

      <label>Location</label>
      <input
        name="location"
        value={form.location}
        onChange={handleChange}
        placeholder="City, State"
        required
      />

      <label>Severity</label>
      <select
        name="severity"
        value={form.severity}
        onChange={handleChange}
      >
        <option>Low</option>
        <option>Medium</option>
        <option>High</option>
        <option>Critical</option>
      </select>

      <label>Status</label>
      <select
        name="status"
        value={form.status}
        onChange={handleChange}
      >
        <option>Active</option>
        <option>Monitoring</option>
        <option>Resolved</option>
      </select>

      <label>Description</label>
      <textarea
        name="description"
        value={form.description}
        onChange={handleChange}
        placeholder="Describe the situation..."
        rows="3"
      />

      {error && <p className="form-error">{error}</p>}

      <button type="submit" disabled={saving}>
        {saving ? "Saving..." : "Save Incident"}
      </button>

      <button type="button" onClick={onCancel}>
        Cancel
      </button>
    </form>
  );
}

export default AddIncident;
