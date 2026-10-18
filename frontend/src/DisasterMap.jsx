
import { useEffect, useState } from "react";
import {
  MapContainer,
  TileLayer,
  CircleMarker,
  Polygon,
  Popup,
  useMap,
} from "react-leaflet";
import "leaflet/dist/leaflet.css";

const API = "http://127.0.0.1:8000";

function FitMapToMarkers({ points }) {
  const map = useMap();

  useEffect(() => {
    if (points.length > 0) {
      const bounds = points.map((point) => [
        point.latitude,
        point.longitude,
      ]);

      map.fitBounds(bounds, {
        padding: [35, 35],
        maxZoom: 16,
      });
    }
  }, [map, points]);

  return null;
}

function BuildingFootprints({ features }) {
  return features.map((feature) => {
    const rings = feature.geometry?.coordinates || [];
    const outerRing = rings[0] || [];

    // GeoJSON uses [longitude, latitude].
    // Leaflet polygons use [latitude, longitude].
    const positions = outerRing.map(([longitude, latitude]) => [
      latitude,
      longitude,
    ]);

    if (positions.length < 4) return null;

    const properties = feature.properties || {};

    return (
      <Polygon
        key={feature.id}
        positions={positions}
        pathOptions={{
          color: "#475569",
          weight: 1,
          fillColor: "#94a3b8",
          fillOpacity: 0.45,
        }}
      >
        <Popup>
          <strong>
            {properties.name || "Unnamed building"}
          </strong>
          <br />
          Type: {properties.building || "Unknown"}
          <br />
          Source: OpenStreetMap
          <br />
          OSM ID: {properties.osm_id || "N/A"}
        </Popup>
      </Polygon>
    );
  });
}

export default function DisasterMap({
  earthquakes = [],
  gdacsDisasters = [],
}) {
  const [buildings, setBuildings] = useState([]);
  const [buildingCount, setBuildingCount] = useState(0);
  const [loadingBuildings, setLoadingBuildings] = useState(true);
  const [buildingError, setBuildingError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function loadBuildings() {
      setLoadingBuildings(true);
      setBuildingError("");

      try {
        const response = await fetch(`${API}/building-footprints`);

        if (!response.ok) {
          throw new Error("Building data request failed");
        }

        const data = await response.json();

        if (!cancelled) {
          setBuildings(
            Array.isArray(data.features) ? data.features : []
          );
          setBuildingCount(data.count ?? data.features?.length ?? 0);
        }
      } catch {
        if (!cancelled) {
          setBuildingError(
            "Could not load building footprints. Check the backend and try again."
          );
        }
      } finally {
        if (!cancelled) {
          setLoadingBuildings(false);
        }
      }
    }

    loadBuildings();

    return () => {
      cancelled = true;
    };
  }, []);

  const validCoordinates = (latitude, longitude) =>
    latitude != null &&
    longitude != null &&
    Number.isFinite(Number(latitude)) &&
    Number.isFinite(Number(longitude)) &&
    Number(latitude) >= -90 &&
    Number(latitude) <= 90 &&
    Number(longitude) >= -180 &&
    Number(longitude) <= 180;

  const points = [
    ...earthquakes
      .filter((item) =>
        validCoordinates(item.latitude, item.longitude)
      )
      .map((item) => ({
        id: `usgs-${item.id}`,
        source: "USGS",
        title: item.title || "Earthquake",
        location: item.location || "Unknown location",
        latitude: Number(item.latitude),
        longitude: Number(item.longitude),
        detail: `Magnitude: ${Number(item.magnitude || 0).toFixed(1)}`,
        url: item.url,
      })),

    ...gdacsDisasters
      .filter((item) =>
        validCoordinates(item.latitude, item.longitude)
      )
      .map((item, index) => ({
        id: `gdacs-${item.id ?? index}`,
        source: "GDACS",
        title: item.title || "Disaster event",
        location: item.location || "Unknown location",
        latitude: Number(item.latitude),
        longitude: Number(item.longitude),
        detail: `Type: ${item.event_type || "Unknown"} · Alert: ${
          item.alert_level || "Not provided"
        }`,
        url: item.url,
      })),
  ];

  const usgsCount = points.filter(
    (point) => point.source === "USGS"
  ).length;

  const gdacsCount = points.filter(
    (point) => point.source === "GDACS"
  ).length;

  // Keep the Chennai test map in view when no disaster
  // markers are available near the test area.
  const chennaiCenter = [13.05, 80.25];

  return (
    <section className="panel disaster-map-panel">
      <div className="panel-heading">
        <div>
          <h3>Disaster Zones & Building Footprints</h3>
          <p>
            Chennai test area · Live disaster feeds and mapped buildings
          </p>
        </div>
      </div>

      <div className="map-legend">
        <span>
          <i className="map-dot usgs-dot" />
          USGS earthquakes ({usgsCount})
        </span>

        <span>
          <i className="map-dot gdacs-dot" />
          GDACS alerts ({gdacsCount})
        </span>

        <span>
          <i className="map-dot building-dot" />
          OpenStreetMap buildings ({buildingCount})
        </span>
      </div>

      {loadingBuildings && <p>Loading Chennai buildings...</p>}

      {buildingError && (
        <p role="alert">{buildingError}</p>
      )}

      <MapContainer
        center={chennaiCenter}
        zoom={15}
        scrollWheelZoom
        style={{
          height: "500px",
          width: "100%",
          borderRadius: "12px",
        }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        <FitMapToMarkers points={points} />

        <BuildingFootprints features={buildings} />

        {points.map((point) => (
          <CircleMarker
            key={point.id}
            center={[point.latitude, point.longitude]}
            radius={point.source === "GDACS" ? 8 : 6}
            pathOptions={{
              color:
                point.source === "GDACS" ? "#d97706" : "#2563eb",
              fillColor:
                point.source === "GDACS" ? "#f59e0b" : "#3b82f6",
              fillOpacity: 0.9,
              weight: 2,
            }}
          >
            <Popup>
              <strong>{point.title}</strong>
              <br />
              Source: {point.source}
              <br />
              Location: {point.location}
              <br />
              {point.detail}
              <br />
              Coordinates: {point.latitude.toFixed(5)},{" "}
              {point.longitude.toFixed(5)}
              {point.url && (
                <>
                  <br />
                  <a
                    href={point.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    View source details
                  </a>
                </>
              )}
            </Popup>
          </CircleMarker>
        ))}
      </MapContainer>

      <p className="muted map-note">
        Building outlines come from OpenStreetMap. Blue markers represent
        USGS earthquakes, and orange markers represent GDACS events.
        Building presence does not indicate that a building is damaged.
      </p>
    </section>
  );
}
