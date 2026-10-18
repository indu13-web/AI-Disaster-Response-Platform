import { useState, useEffect, useCallback } from "react";

import "./App.css";

import Auth from "./Auth";

import AddIncident from "./AddIncident";

import DisasterMap from "./DisasterMap";



const API = "http://127.0.0.1:8000";



function App() {

  const [loggedInUser, setLoggedInUser] = useState(null);

  const [activeTab, setActiveTab] = useState("Overview");



  // Manual incidents stored in PostgreSQL

  const [incidents, setIncidents] = useState([]);

  const [loadingIncidents, setLoadingIncidents] = useState(true);

  const [incidentError, setIncidentError] = useState("");

  const [showAddIncident, setShowAddIncident] = useState(false);



  // USGS earthquake feed

  const [earthquakes, setEarthquakes] = useState([]);

  const [earthquakeCount, setEarthquakeCount] = useState(0);

  const [earthquakeUpdatedAt, setEarthquakeUpdatedAt] = useState("");

  const [loadingEarthquakes, setLoadingEarthquakes] = useState(true);

  const [earthquakeError, setEarthquakeError] = useState("");



  // GDACS disaster feed

  const [gdacsDisasters, setGdacsDisasters] = useState([]);

  const [gdacsCount, setGdacsCount] = useState(0);

  const [loadingGdacs, setLoadingGdacs] = useState(true);

  const [gdacsError, setGdacsError] = useState("");

  const [populationData, setPopulationData] = useState(null);
  const [populationError, setPopulationError] = useState("");





  const fetchPopulation = async () => {
    setPopulationError("");
    try {
      const response = await fetch(`${API}/population-estimate`);
      if (!response.ok) throw new Error("Population endpoint returned an error.");
      const data = await response.json();
      if (data.status === "success") {
        setPopulationData(data);
      } else {
        throw new Error(data.message || "Population estimate is not ready.");
      }
    } catch (error) {
      console.error("Population fetch failed:", error);
      setPopulationError(error.message || "Could not load population estimate.");
    }
  };

  // Load manually registered PostgreSQL incidents

  const loadIncidents = useCallback(async () => {

    setLoadingIncidents(true);

    setIncidentError("");



    try {

      const response = await fetch(`${API}/incidents`);



      if (!response.ok) {

        throw new Error("Unable to load incidents");

      }



      const data = await response.json();



      setIncidents(Array.isArray(data.incidents) ? data.incidents : []);

    } catch {

      setIncidentError(

        "Could not load database incidents. Check the backend."

      );

    } finally {

      setLoadingIncidents(false);

    }

  }, []);



  // Load live USGS earthquakes

  const loadEarthquakes = useCallback(async () => {

    setEarthquakeError("");



    try {

      const response = await fetch(`${API}/live-earthquakes`);



      if (!response.ok) {

        throw new Error("USGS feed unavailable");

      }



      const data = await response.json();



      setEarthquakes(

        Array.isArray(data.earthquakes) ? data.earthquakes : []

      );

      setEarthquakeCount(data.count || 0);

      setEarthquakeUpdatedAt(data.updated_at || "");

    } catch {

      setEarthquakeError(

        "Unable to load USGS data. Check your internet connection and backend."

      );

    } finally {

      setLoadingEarthquakes(false);

    }

  }, []);



  // Load live GDACS disaster alerts

  const loadGdacs = useCallback(async () => {

    setGdacsError("");



    try {

      const response = await fetch(`${API}/live-disasters`);



      if (!response.ok) {

        throw new Error("GDACS feed unavailable");

      }



      const data = await response.json();

      const records = Array.isArray(data.disasters) ? data.disasters : [];



      setGdacsDisasters(records);

      setGdacsCount(data.count ?? records.length);

    } catch {

      setGdacsError(

        "Unable to load GDACS alerts. Check your internet connection and backend."

      );

    } finally {

      setLoadingGdacs(false);

    }

  }, []);



  // Load all three sources independently after login

  useEffect(() => {

    if (!loggedInUser) return undefined;



    loadIncidents();

    loadEarthquakes();

    loadGdacs();

    fetchPopulation();



    const earthquakeTimer = setInterval(loadEarthquakes, 60000);

    const gdacsTimer = setInterval(loadGdacs, 360000);



    return () => {

      clearInterval(earthquakeTimer);

      clearInterval(gdacsTimer);

    };

  }, [

    loggedInUser,

    loadIncidents,

    loadEarthquakes,

    loadGdacs,

  ]);



  if (!loggedInUser) {

    return <Auth onLogin={setLoggedInUser} />;

  }



  const activeCount = incidents.filter(

    (item) => item.status === "Active"

  ).length;



  const highCount = incidents.filter(

    (item) => ["High", "Critical"].includes(item.severity)

  ).length;



  // USGS panel

  function earthquakePanel(compact = false) {

    const displayedEarthquakes = compact

      ? earthquakes.slice(0, 5)

      : earthquakes;



    return (

      <article className="panel live-earthquakes-panel">

        <div className="panel-heading">

          <div>

            <h3>Live Earthquake Feed</h3>

            <p>Source: USGS · Worldwide · Past 24 hours</p>

          </div>



          <button

            type="button"

            onClick={loadEarthquakes}

            disabled={loadingEarthquakes}

          >

            {loadingEarthquakes ? "Loading..." : "Refresh"}

          </button>

        </div>



        <p className="muted">

          {earthquakeUpdatedAt

            ? `Feed retrieved: ${new Date(

                earthquakeUpdatedAt

              ).toLocaleString()}`

            : "Feed retrieval time not available."}

        </p>



        <p className="muted">

          {earthquakeCount} records in the current USGS feed.

        </p>



        {earthquakeError && (

          <p role="alert">{earthquakeError}</p>

        )}



        {loadingEarthquakes && earthquakes.length === 0 ? (

          <p>Loading live earthquakes...</p>

        ) : earthquakes.length === 0 ? (

          !earthquakeError && <p>No earthquake records returned.</p>

        ) : (

          <div className="earthquake-list">

            {displayedEarthquakes.map((quake, index) => (

              <div

                className="earthquake-row"

                key={quake.id ?? `quake-${index}`}

              >

                <div className="earthquake-magnitude">

                  M {Number(quake.magnitude || 0).toFixed(1)}

                </div>



                <div className="earthquake-info">

                  <strong>

                    {quake.location || quake.title || "Unknown location"}

                  </strong>



                  <p>

                    {quake.time

                      ? new Date(quake.time).toLocaleString()

                      : "Time unavailable"}

                  </p>



                  <small>

                    Latitude: {quake.latitude ?? "N/A"} · Longitude:{" "}

                    {quake.longitude ?? "N/A"}

                  </small>

                </div>



                {quake.url && (

                  <a

                    href={quake.url}

                    target="_blank"

                    rel="noreferrer"

                  >

                    USGS details ↗

                  </a>

                )}

              </div>

            ))}

          </div>

        )}



        {compact && earthquakes.length > 5 && (

          <button

            type="button"

            onClick={() => setActiveTab("Disaster Zones")}

          >

            View all earthquakes ({earthquakeCount})

          </button>

        )}

      </article>

    );

  }



  // GDACS panel

  function gdacsPanel(compact = false) {

    const displayedDisasters = compact

      ? gdacsDisasters.slice(0, 5)

      : gdacsDisasters;



    return (

      <article className="panel live-gdacs-panel">

        <div className="panel-heading">

          <div>

            <h3>Live GDACS Disaster Alerts</h3>

            <p>Source: Global Disaster Awareness and Coordination System</p>

          </div>



          <button

            type="button"

            onClick={loadGdacs}

            disabled={loadingGdacs}

          >

            {loadingGdacs ? "Loading..." : "Refresh"}

          </button>

        </div>



        <p className="muted">

          {gdacsCount} records in the current GDACS feed.

          Automatic refresh every 6 minutes.

        </p>



        {gdacsError && <p role="alert">{gdacsError}</p>}



        {loadingGdacs && gdacsDisasters.length === 0 ? (

          <p>Loading GDACS alerts...</p>

        ) : gdacsDisasters.length === 0 ? (

          !gdacsError && <p>No GDACS disaster records returned.</p>

        ) : (

          <div className="incident-list">

            {displayedDisasters.map((disaster, index) => (

              <div

                className="incident-row"

                key={disaster.id ?? `gdacs-${index}`}

              >

                <div className="incident-symbol">!</div>



                <div className="incident-info">

                  <strong>

                    {disaster.title || "GDACS disaster event"}

                  </strong>



                  <p>

                    {disaster.location || "Location not provided"}

                  </p>



                  <small>

                    Type: {disaster.event_type || "Unknown"} · Alert:{" "}

                    {disaster.alert_level || "Not provided"}

                  </small>

                </div>



                <div className="incident-status">

                  <span className="severity high">GDACS</span>



                  {disaster.url && (

                    <a

                      href={disaster.url}

                      target="_blank"

                      rel="noreferrer"

                    >

                      Details ↗

                    </a>

                  )}

                </div>

              </div>

            ))}

          </div>

        )}



        {compact && gdacsDisasters.length > 5 && (

          <button

            type="button"

            onClick={() => setActiveTab("Disaster Zones")}

          >

            View all GDACS alerts ({gdacsCount})

          </button>

        )}

      </article>

    );

  }



  return (

    <div className="app">

      <aside className="sidebar">

        <div className="brand">

          <span className="brand-icon">✚</span>



          <div>

            <h2>ResQ</h2>

            <p>Emergency Intelligence</p>

          </div>

        </div>



        <p className="menu-label">MAIN MENU</p>



        {[

          "Overview",

          "Disaster Zones",

          "Resources",

          "Field Teams",

          "Reports",

        ].map((item) => (

          <button

            key={item}

            className={`nav-item ${

              activeTab === item ? "selected" : ""

            }`}

            onClick={() => setActiveTab(item)}

          >

            {item === "Overview" && "▦"}

            {item === "Disaster Zones" && "⌖"}

            {item === "Resources" && "▤"}

            {item === "Field Teams" && "♙"}

            {item === "Reports" && "▥"}



            <span>{item}</span>

          </button>

        ))}



        <div className="sidebar-bottom">

          <span className="online-dot"></span>

          ResQ system online

        </div>

      </aside>



      <main className="main-content">

        <header className="topbar">

          <div>

            <p className="eyebrow">DISASTER RESPONSE PLATFORM</p>

            <h1>{activeTab}</h1>

          </div>



          <div className="user-chip">

            <span className="user-avatar">RC</span>



            <div>

              <strong>Relief Coordinator</strong>

              <p>Operations Team</p>

            </div>

          </div>

        </header>



        {activeTab === "Overview" && (

          <>

            <section className="welcome">

              <div>

                <p className="eyebrow light">COMMAND CENTRE</p>

                <h2>Emergency Response Overview</h2>

                <p>

                  Monitor manual incidents and live disaster information.

                </p>

              </div>



              <div className="welcome-icon">⌖</div>

            </section>



            <section className="stats-grid">

              <article className="stat-card">

                <div className="stat-top">

                  <span>Active Incidents</span>

                  <span className="stat-icon red">!</span>

                </div>



                <h2>

                  {loadingIncidents

                    ? "..."

                    : String(activeCount).padStart(2, "0")}

                </h2>



                <p className="muted">

                  Manual incidents in PostgreSQL

                </p>

              </article>



              <article className="stat-card">

                <div className="stat-top">

                  <span>High Severity</span>

                  <span className="stat-icon orange">▲</span>

                </div>



                <h2>

                  {loadingIncidents

                    ? "..."

                    : String(highCount).padStart(2, "0")}

                </h2>



                <p className="muted">

                  High or critical manual incidents

                </p>

              </article>



              <article className="stat-card">

                <div className="stat-top">

                  <span>USGS Earthquakes</span>

                  <span className="stat-icon blue">⌖</span>

                </div>



                <h2>

                  {loadingEarthquakes ? "..." : earthquakeCount}

                </h2>



                <p className="muted">Worldwide · Past 24 hours</p>

              </article>



              <article className="stat-card">

                <div className="stat-top">

                  <span>GDACS Alerts</span>

                  <span className="stat-icon orange">!</span>

                </div>



                <h2>{loadingGdacs ? "..." : gdacsCount}</h2>



                <p className="muted">Live disaster feed records</p>

              </article>

            </section>



            {gdacsPanel(true)}



            {earthquakePanel(true)}



            <section className="content-grid">

              <article className="panel incidents-panel">

                <div className="panel-heading">

                  <div>

                    <h3>Incident Monitoring</h3>

                    <p>

                      Manually registered incidents from PostgreSQL

                    </p>

                  </div>



                  <button

                    type="button"

                    onClick={() => setShowAddIncident(true)}

                  >

                    + Add Incident

                  </button>

                </div>



                {showAddIncident && (

                  <AddIncident

                    onCancel={() => setShowAddIncident(false)}

                    onIncidentAdded={() => {

                      setShowAddIncident(false);

                      loadIncidents();

                    }}

                  />

                )}



                <div className="incident-list">

                  {loadingIncidents ? (

                    <p>Loading incidents...</p>

                  ) : incidentError ? (

                    <p role="alert">{incidentError}</p>

                  ) : incidents.length === 0 ? (

                    <p>

                      No manual incidents found. Click Add Incident.

                    </p>

                  ) : (

                    incidents.map((incident) => (

                      <div

                        className="incident-row"

                        key={incident.id}

                      >

                        <div className="incident-symbol">⌖</div>



                        <div className="incident-info">

                          <strong>{incident.title}</strong>

                          <p>{incident.location}</p>

                        </div>



                        <div className="incident-status">

                          <span

                            className={`severity ${(

                              incident.severity || "Low"

                            ).toLowerCase()}`}

                          >

                            {incident.severity}

                          </span>



                          <small>{incident.status}</small>

                        </div>

                      </div>

                    ))

                  )}

                </div>

              </article>



              <article className="panel resources-panel">

                <div className="panel-heading">

                  <div>

                    <h3>Resource Inventory</h3>

                    <p>Sample relief supplies</p>

                  </div>

                </div>



                {[

                  { name: "Food Packets", count: 450, total: 600 },

                  { name: "Drinking Water", count: 320, total: 500 },

                  { name: "Medical Kits", count: 85, total: 120 },

                  { name: "Rescue Vehicles", count: 12, total: 20 },

                ].map((resource) => (

                  <div className="resource-item" key={resource.name}>

                    <div className="resource-label">

                      <span>{resource.name}</span>

                      <strong>{resource.count}</strong>

                    </div>



                    <div className="progress-track">

                      <div

                        className="progress-fill"

                        style={{

                          width: `${

                            (resource.count / resource.total) * 100

                          }%`,

                        }}

                      />

                    </div>

                  </div>

                ))}



                <p className="inventory-note">

                  Sample figures only. Database integration is pending.

                </p>

              </article>

            </section>

          </>

        )}



        {activeTab === "Disaster Zones" && (

          <section className="disaster-feeds">

            <article className="panel">

              <h2>Geospatial Impact Assessment</h2>

              <p>

                Explore mapped buildings in the Chennai test area and

                locations reported by the live disaster feeds.

              </p>

              <p className="muted">

                GDACS, USGS, OpenStreetMap buildings, and manual

                PostgreSQL incidents are maintained as separate sources.

              </p>

            </article>



            <article className="panel population-panel">
              <div className="panel-heading">
                <div>
                  <h3>Estimated Population</h3>
                  <p>Source: WorldPop · Chennai study area · 2020</p>
                </div>
                <button type="button" onClick={fetchPopulation}>
                  Refresh
                </button>
              </div>

              {populationError ? (
                <p role="alert">Population estimate unavailable: {populationError}</p>
              ) : populationData ? (
                <>
                  <div className="population-main-value">
                    {Number(populationData.population_estimate).toLocaleString()} people
                  </div>
                  <div className="population-details">
                    <div>
                      <span>Study area</span>
                      <strong>
                        {populationData.area_km2 != null
                          ? `${Number(populationData.area_km2).toFixed(2)} km²`
                          : "Not provided"}
                      </strong>
                    </div>
                    <div>
                      <span>Population density</span>
                      <strong>
                        {populationData.population_density != null
                          ? `${Number(populationData.population_density).toLocaleString(undefined, { maximumFractionDigits: 2 })} people/km²`
                          : "Not provided"}
                      </strong>
                    </div>
                    <div>
                      <span>Data year</span>
                      <strong>{populationData.year || "Not provided"}</strong>
                    </div>
                  </div>
                  <p className="muted population-note">
                    This is the estimated population living in the study area, not the number of people affected by a disaster.
                  </p>
                </>
              ) : (
                <p>Loading WorldPop population estimate...</p>
              )}
            </article>

            <DisasterMap

              earthquakes={earthquakes}

              gdacsDisasters={gdacsDisasters}

            />



            {gdacsPanel(false)}



            {earthquakePanel(false)}

          </section>

        )}



        {activeTab === "Resources" && (

          <section className="panel">

            <h3>Resource Inventory</h3>

            <p>

              Resource quantities are sample values; database

              integration is pending.

            </p>

          </section>

        )}



        {activeTab === "Field Teams" && (

          <section className="panel">

            <h3>Field Teams</h3>

            <p>

              Field team information is not connected to a database yet.

            </p>

          </section>

        )}



        {activeTab === "Reports" && (

          <section className="panel">

            <h3>Reports</h3>

            <p>

              Automated disaster reports and relief analytics are pending.

            </p>

          </section>

        )}



        <footer>

          <span>ResQ · Emergency Response Intelligence Platform</span>



          <span>

            {activeTab === "Disaster Zones"

              ? "GDACS · USGS · OpenStreetMap"

              : "Manual incidents and live data shown separately"}

          </span>

        </footer>

      </main>

    </div>

  );

}



export default App;
