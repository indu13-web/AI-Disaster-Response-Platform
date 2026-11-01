
import { useState, useEffect, useCallback } from "react";

const API = "http://127.0.0.1:8000";

async function readResponse(response) {
  const text = await response.text();

  let result;
  try {
    result = text ? JSON.parse(text) : {};
  } catch {
    result = { detail: text };
  }

  if (!response.ok) {
    const detail =
      typeof result.detail === "string"
        ? result.detail
        : JSON.stringify(result.detail ?? result);

    throw new Error(`Server ${response.status}: ${detail}`);
  }

  return result;
}

function displayValue(value) {
  if (value === null || value === undefined || value === "") {
    return "N/A";
  }

  if (typeof value === "object") {
    return JSON.stringify(value);
  }

  return value;
}

export default function DemandPrediction() {
  const [zones, setZones] = useState([]);
  const [loadingZones, setLoadingZones] = useState(true);
  const [zoneError, setZoneError] = useState("");

  const [elderly, setElderly] = useState("0.15");
  const [children, setChildren] = useState("0.25");
  const [medDep, setMedDep] = useState("0.10");

  const [scenarioName, setScenarioName] = useState("");
  const [responseSpeed, setResponseSpeed] = useState("0.7");
  const [resourceAvail, setResourceAvail] = useState("60");
  const [popMultiplier, setPopMultiplier] = useState("1.5");
  const [severityOverride, setSeverityOverride] = useState("");

  const [scenarioResults, setScenarioResults] = useState([]);
  const [scenarioLoading, setScenarioLoading] = useState(false);
  const [scenarioError, setScenarioError] = useState("");

  const [reportZoneId, setReportZoneId] = useState("1");
  const [reportPopulation, setReportPopulation] = useState("3000");
  const [reportSeverity, setReportSeverity] = useState("high");
  const [reportDamagedFrac, setReportDamagedFrac] = useState("0.20");
  const [reportSource, setReportSource] = useState("");

  const [reportResult, setReportResult] = useState(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [reportError, setReportError] = useState("");

  // Load demand predictions from the backend.
  const loadZones = useCallback(async () => {
    setLoadingZones(true);
    setZoneError("");

    try {
      const params = new URLSearchParams();

      if (elderly !== "") params.set("elderly_share", elderly);
      if (children !== "") params.set("children_share", children);
      if (medDep !== "") {
        params.set("medically_dependent_share", medDep);
      }

      const response = await fetch(
        `${API}/api/demand/zones?${params.toString()}`
      );

      const result = await readResponse(response);

      // The backend returns predictions in result.data.
      const sourceZones = Array.isArray(result.data) ? result.data : [];

      const mappedZones = sourceZones.map((zone) => ({
        id: zone.zone_id,
        name: zone.zone_name,
        disaster_type:
          zone.inputs_used?.disaster_type?.value ?? "Unknown",
        severity: zone.inputs_used?.severity?.value ?? "Unknown",
        resources: zone.resources ?? {},
        inputs_used: zone.inputs_used ?? {},
        vulnerability_assessment:
          zone.vulnerability_assessment ?? {},
      }));

      setZones(mappedZones);

      if (mappedZones.length === 0) {
        setZoneError(
          "The API returned no zone records. Check the backend zone data."
        );
      }
    } catch (error) {
      setZones([]);
      setZoneError(error.message || "Failed to load zone demand.");
    } finally {
      setLoadingZones(false);
    }
  }, [elderly, children, medDep]);

  useEffect(() => {
    loadZones();
  }, [loadZones]);

  // Run a scenario. The backend expects a scenarios array.
  const runScenario = async () => {
    setScenarioError("");

    if (!scenarioName.trim()) {
      setScenarioError("Enter a scenario name.");
      return;
    }

    if (
      responseSpeed === "" ||
      resourceAvail === "" ||
      popMultiplier === ""
    ) {
      setScenarioError("Fill in all scenario numeric values.");
      return;
    }

    const speed = Number(responseSpeed);
    const availability = Number(resourceAvail);
    const multiplier = Number(popMultiplier);

    if (!Number.isFinite(speed) || speed < 0 || speed > 1) {
      setScenarioError("Response speed must be between 0 and 1.");
      return;
    }

    if (
      !Number.isFinite(availability) ||
      availability < 0 ||
      availability > 100
    ) {
      setScenarioError("Resource availability must be between 0 and 100.");
      return;
    }

    if (!Number.isFinite(multiplier) || multiplier <= 0) {
      setScenarioError("Population multiplier must be greater than 0.");
      return;
    }

    setScenarioLoading(true);

    try {
      const scenario = {
        name: scenarioName.trim(),
        response_speed: speed,
        resource_availability_pct: availability,
        population_multiplier: multiplier,
      };

      if (severityOverride.trim()) {
        scenario.severity_override = severityOverride.trim().toLowerCase();
      }

      const response = await fetch(`${API}/api/demand/simulate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scenarios: [scenario] }),
      });

      const result = await readResponse(response);

      // Support either a single-result response or a list of results.
      const results = Array.isArray(result.results)
        ? result.results
        : Array.isArray(result.data)
          ? result.data
          : Array.isArray(result.scenarios)
            ? result.scenarios
            : [result];

      setScenarioResults((previous) => [...previous, ...results]);
    } catch (error) {
      setScenarioError(error.message || "Scenario simulation failed.");
    } finally {
      setScenarioLoading(false);
    }
  };

  // Submit a field report.
  const submitReport = async () => {
    setReportError("");
    setReportResult(null);

    const zoneId = Number(reportZoneId);
    const population = Number(reportPopulation);
    const damageFraction = Number(reportDamagedFrac);
    const severity = reportSeverity.trim().toLowerCase();
    const sourceText = reportSource.trim();

    if (!Number.isInteger(zoneId) || zoneId <= 0) {
      setReportError("Zone ID must be a positive whole number.");
      return;
    }

    if (!Number.isFinite(population) || population <= 0) {
      setReportError("Population must be greater than 0.");
      return;
    }

    if (!["low", "medium", "high", "critical"].includes(severity)) {
      setReportError("Severity must be low, medium, high, or critical.");
      return;
    }

    if (
      reportDamagedFrac === "" ||
      !Number.isFinite(damageFraction) ||
      damageFraction < 0 ||
      damageFraction > 1
    ) {
      setReportError(
        "Damaged-buildings value must be between 0 and 1. For 20%, enter 0.20."
      );
      return;
    }

    if (!sourceText) {
      setReportError("Enter the field report source.");
      return;
    }

    setReportLoading(true);

    try {
      // These field names must match the backend's Field Report request model.
      const payload = {
        trigger_type: "field_report",
        source_text: sourceText,
        reported_population: population,
        reported_severity: severity,
        damage_fraction: damageFraction,
      };

      const response = await fetch(
        `${API}/api/demand/zones/${zoneId}/update`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }
      );

      const result = await readResponse(response);
      setReportResult(result);

      await loadZones();
    } catch (error) {
      setReportError(error.message || "Field report submission failed.");
    } finally {
      setReportLoading(false);
    }
  };

  const renderTable = () => {
    if (loadingZones) return <p>Loading zone demand...</p>;

    if (zoneError) {
      return (
        <div>
          <p className="error">{zoneError}</p>
          <button onClick={loadZones} disabled={loadingZones}>
            Retry
          </button>
        </div>
      );
    }

    if (zones.length === 0) return <p>No zones returned.</p>;

    return (
      <div style={{ overflowX: "auto" }}>
        <table className="demand-table">
          <thead>
            <tr>
              <th>Zone ID</th>
              <th>Zone Name</th>
              <th>Disaster</th>
              <th>Severity</th>
              <th>Food (packets)</th>
              <th>Water (L)</th>
              <th>Medical kits</th>
              <th>Shelter (people)</th>
              <th>Food stock</th>
              <th>Food shortage</th>
            </tr>
          </thead>
          <tbody>
            {zones.map((zone) => {
              const resources = zone.resources ?? {};
              const food = resources.food_packets ?? {};
              const water = resources.water_litres ?? {};
              const medical = resources.medical_kits ?? {};
              const shelter =
                resources.shelter_capacity_persons ?? {};

              return (
                <tr key={zone.id}>
                  <td>{displayValue(zone.id)}</td>
                  <td>{displayValue(zone.name)}</td>
                  <td>{displayValue(zone.disaster_type)}</td>
                  <td>{displayValue(zone.severity)}</td>
                  <td>{displayValue(food.adjusted_demand)}</td>
                  <td>{displayValue(water.adjusted_demand)}</td>
                  <td>{displayValue(medical.adjusted_demand)}</td>
                  <td>{displayValue(shelter.adjusted_demand)}</td>
                  <td>{displayValue(food.inventory?.available_stock)}</td>
                  <td>{displayValue(food.inventory?.estimated_shortage)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  };

  return (
    <section className="panel demand-prediction">
      <h2>Demand Prediction</h2>

      <p className="notice">
        <strong>Notice:</strong> Demand estimates are planning predictions,
        not confirmed relief requirements. Prediction intervals are not
        validated real-world confidence levels.
      </p>

      <div className="vuln-inputs">
        <label>
          Elderly share (0-1):
          <input
            type="number"
            step="0.01"
            min="0"
            max="1"
            value={elderly}
            onChange={(e) => setElderly(e.target.value)}
          />
        </label>

        <label>
          Children share (0-1):
          <input
            type="number"
            step="0.01"
            min="0"
            max="1"
            value={children}
            onChange={(e) => setChildren(e.target.value)}
          />
        </label>

        <label>
          Medically dependent share (0-1):
          <input
            type="number"
            step="0.01"
            min="0"
            max="1"
            value={medDep}
            onChange={(e) => setMedDep(e.target.value)}
          />
        </label>

        <button onClick={loadZones} disabled={loadingZones}>
          {loadingZones ? "Refreshing..." : "Refresh Demand"}
        </button>
      </div>

      {renderTable()}

      <section className="scenario-form">
        <h3>Scenario Simulation</h3>

        <div className="field-row">
          <label>
            Name:
            <input
              value={scenarioName}
              onChange={(e) => setScenarioName(e.target.value)}
              placeholder="Chennai Flood Test"
            />
          </label>

          <label>
            Response speed (0-1):
            <input
              type="number"
              step="0.01"
              min="0"
              max="1"
              value={responseSpeed}
              onChange={(e) => setResponseSpeed(e.target.value)}
            />
          </label>

          <label>
            Resource availability (0-100):
            <input
              type="number"
              min="0"
              max="100"
              value={resourceAvail}
              onChange={(e) => setResourceAvail(e.target.value)}
            />
          </label>

          <label>
            Population multiplier:
            <input
              type="number"
              step="0.1"
              min="0.1"
              value={popMultiplier}
              onChange={(e) => setPopMultiplier(e.target.value)}
            />
          </label>

          <label>
            Severity override:
            <input
              value={severityOverride}
              onChange={(e) => setSeverityOverride(e.target.value)}
              placeholder="low, medium, high, critical"
            />
          </label>

          <button onClick={runScenario} disabled={scenarioLoading}>
            {scenarioLoading ? "Running..." : "Run Scenario"}
          </button>
        </div>

        {scenarioError && <p className="error">{scenarioError}</p>}

        {scenarioResults.length > 0 && (
          <div style={{ overflowX: "auto" }}>
            <table className="scenario-results">
              <thead>
                <tr>
                  <th>Scenario result</th>
                  <th>Details</th>
                </tr>
              </thead>
              <tbody>
                {scenarioResults.map((result, index) => (
                  <tr key={index}>
                    <td>{displayValue(result.name ?? `Result ${index + 1}`)}</td>
                    <td>
                      <pre style={{ whiteSpace: "pre-wrap" }}>
                        {JSON.stringify(result, null, 2)}
                      </pre>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="field-report-form">
        <h3>Field Report Update</h3>

        <div className="field-row">
          <label>
            Zone ID:
            <input
              type="number"
              min="1"
              value={reportZoneId}
              onChange={(e) => setReportZoneId(e.target.value)}
            />
          </label>

          <label>
            Population:
            <input
              type="number"
              min="1"
              value={reportPopulation}
              onChange={(e) => setReportPopulation(e.target.value)}
            />
          </label>

          <label>
            Severity:
            <input
              value={reportSeverity}
              onChange={(e) => setReportSeverity(e.target.value)}
              placeholder="low, medium, high, critical"
            />
          </label>

          <label>
            Damaged buildings fraction (0-1):
            <input
              type="number"
              step="0.01"
              min="0"
              max="1"
              value={reportDamagedFrac}
              onChange={(e) => setReportDamagedFrac(e.target.value)}
            />
          </label>

          <label>
            Source:
            <input
              value={reportSource}
              onChange={(e) => setReportSource(e.target.value)}
              placeholder="Field Team 1"
            />
          </label>

          <button onClick={submitReport} disabled={reportLoading}>
            {reportLoading ? "Submitting..." : "Submit Report"}
          </button>
        </div>

        {reportError && <p className="error">{reportError}</p>}

        {reportResult && (
          <pre className="report-result">
            {JSON.stringify(reportResult, null, 2)}
          </pre>
        )}
      </section>
    </section>
  );
}

