import os
from contextlib import asynccontextmanager
import json
from urllib.request import urlopen, Request
from urllib.error import URLError
from datetime import datetime, timezone
import psycopg
from psycopg.rows import dict_row
from psycopg.errors import UniqueViolation
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pwdlib import PasswordHash

load_dotenv()

password_hasher = PasswordHash.recommended()


def get_connection():
    return psycopg.connect(
        host=os.getenv("DB_HOST"                              , "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "disaster_response"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
        row_factory=dict_row,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                username VARCHAR(50) UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS incidents (
                id SERIAL PRIMARY KEY,
                title VARCHAR(150) NOT NULL,
                disaster_type VARCHAR(50) NOT NULL,
                location VARCHAR(200) NOT NULL,
                severity VARCHAR(20) NOT NULL
                    CHECK (severity IN ('Low', 'Medium', 'High', 'Critical')),
                status VARCHAR(30) NOT NULL DEFAULT 'Active'
                    CHECK (status IN ('Active', 'Monitoring', 'Resolved')),
                description TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    yield


app = FastAPI(
    title="Disaster Response Platform API",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SignupRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    username: str
    password: str

class IncidentRequest(BaseModel):
    title: str
    disaster_type: str
    location: str
    severity: str
    status: str = "Active"
    description: str = ""


class IncidentRequest(BaseModel):
    title: str
    disaster_type: str
    location: str
    severity: str
    status: str = "Active"
    description: str = ""



@app.get("/")
def home():
    return {"message": "Disaster Response Platform API is running"}


@app.get("/health")
def health():
    try:
        with get_connection() as conn:
            conn.execute("SELECT 1")
        return {"status": "ok", "database": "connected"}
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Database connection failed. Check your .env settings.",
        )


@app.post("/signup", status_code=201)
def signup(data: SignupRequest):
    name = data.name.strip()
    username = data.username.strip().lower()

    if not name or not username:
        raise HTTPException(
            status_code=400,
            detail="Name and username cannot be empty.",
        )

    hashed_password = password_hasher.hash(data.password)

    try:
        with get_connection() as conn:
            user = conn.execute(
                """
                INSERT INTO users (name, username, password_hash)
                VALUES (%s, %s, %s)
                RETURNING id, name, username, created_at
                """,
                (name, username, hashed_password),
            ).fetchone()

        return {"message": "Account created successfully", "user": user}

    except UniqueViolation:
        raise HTTPException(
            status_code=409,
            detail="That username already exists.",
        )


@app.post("/login")
def login(data: LoginRequest):
    username = data.username.strip().lower()

    with get_connection() as conn:
        user = conn.execute(
            """
            SELECT id, name, username, password_hash
            FROM users
            WHERE username = %s
            """,
            (username,),
        ).fetchone()

    if not user or not password_hasher.verify(
        data.password, user["password_hash"]
    ):
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password.",
        )

    return {
        "message": "Login successful",
        "user": {
            "id": user["id"],
            "name": user["name"],
            "username": user["username"],
        },
    }

@app.get("/incidents")
def get_incidents():
    with get_connection() as conn:
        incidents = conn.execute(
            """
            SELECT id, title, disaster_type, location,
                   severity, status, description, created_at
            FROM incidents
            ORDER BY created_at DESC
            """
        ).fetchall()

    return {"incidents": incidents}


@app.post("/incidents", status_code=201)
def create_incident(data: IncidentRequest):
    severity = data.severity.strip().capitalize()
    status = data.status.strip().capitalize()

    if severity not in ["Low", "Medium", "High", "Critical"]:
        raise HTTPException(
            status_code=400,
            detail="Severity must be Low, Medium, High, or Critical.",
        )

    if status not in ["Active", "Monitoring", "Resolved"]:
        raise HTTPException(
            status_code=400,
            detail="Status must be Active, Monitoring, or Resolved.",
        )

    with get_connection() as conn:
        incident = conn.execute(
            """
            INSERT INTO incidents
                (title, disaster_type, location, severity, status, description)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, title, disaster_type, location,
                      severity, status, description, created_at
            """,
            (
                data.title.strip(),
                data.disaster_type.strip(),
                data.location.strip(),
                severity,
                status,
                data.description.strip(),
            ),
        ).fetchone()

    return {"message": "Incident created successfully", "incident": incident}

@app.get("/live-earthquakes")
def get_live_earthquakes():
    url = (
        "https://earthquake.usgs.gov/earthquakes/feed/v1.0/"
        "summary/all_day.geojson"
    )

    try:
        with urlopen(url, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))

        earthquakes = []

        for feature in data.get("features", []):
            properties = feature.get("properties", {})
            geometry = feature.get("geometry") or {}
            coordinates = geometry.get("coordinates") or []

            if len(coordinates) < 2:
                continue

            earthquakes.append({
                "id": feature.get("id"),
                "title": properties.get("title"),
                "magnitude": properties.get("mag"),
                "location": properties.get("place"),
                "time": properties.get("time"),
                "latitude": coordinates[1],
                "longitude": coordinates[0],
                "source": "USGS",
                "url": properties.get("url"),
            })

        return {
            "source": "USGS",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "count": len(earthquakes),
            "earthquakes": earthquakes,
        }

    except (URLError, TimeoutError, json.JSONDecodeError):
        raise HTTPException(
            status_code=502,
            detail="Unable to retrieve live earthquake data from USGS."
        )
    

@app.get("/live-disasters")
def get_live_disasters():
    url = (
        "https://www.gdacs.org/gdacsapi/api/"
        "Events/geteventlist/EVENTS4APP"
    )

    try:
        request = Request(
            url,
            headers={"User-Agent": "ResQ-Disaster-Response-Student-Project"}
        )

        with urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))

        # GDACS event lists are returned in a GeoJSON-like format.
        if isinstance(data, dict):
            features = data.get("features", [])
            if not features and isinstance(data.get("data"), list):
                features = data["data"]
        elif isinstance(data, list):
            features = data
        else:
            features = []

        disasters = []

        for feature in features:
            properties = feature.get("properties") or {}
            geometry = feature.get("geometry") or {}
            coordinates = geometry.get("coordinates") or []

            # Some event records may not have coordinates.
            longitude = None
            latitude = None

            if geometry.get("type") == "Point" and len(coordinates) >= 2:
                longitude = coordinates[0]
                latitude = coordinates[1]

            disasters.append({
                "id": str(
                    feature.get("id")
                    or properties.get("eventid")
                    or properties.get("eventID")
                    or len(disasters)
                ),
                "title": (
                    properties.get("name")
                    or properties.get("eventname")
                    or properties.get("title")
                    or properties.get("eventtype")
                    or "GDACS disaster event"
                ),
                "event_type": (
                    properties.get("eventtype")
                    or properties.get("eventType")
                    or properties.get("type")
                    or "Unknown"
                ),
                "alert_level": (
                    properties.get("alertlevel")
                    or properties.get("alertLevel")
                    or properties.get("alert")
                    or "Not provided"
                ),
                "location": (
                    properties.get("country")
                    or properties.get("name")
                    or properties.get("title")
                    or "Location not provided"
                ),
                "latitude": latitude,
                "longitude": longitude,
                "source": "GDACS",
                "properties": properties,
            })

        return {
            "source": "GDACS",
            "count": len(disasters),
            "disasters": disasters,
        }

    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=502,
            detail="Unable to retrieve live disaster data from GDACS."
        ) from exc


@app.get("/building-footprints")
def get_building_footprints():
    from urllib.request import Request, urlopen
    from urllib.error import URLError
    import json

    # Small test area in central Chennai.
    # Order: south, west, north, east.
    south, west, north, east = 13.045, 80.245, 13.055, 80.255

    query = f"""
    [out:json][timeout:25];
    way["building"]({south},{west},{north},{east});
    out geom;
    """

    url = "https://overpass-api.de/api/interpreter"

    request = Request(
        url,
        data=query.encode("utf-8"),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "ResQ-Student-Disaster-Response-Project",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=35) as response:
            data = json.loads(response.read().decode("utf-8"))

        features = []

        for element in data.get("elements", []):
            nodes = element.get("geometry", [])

            if len(nodes) < 3:
                continue

            # Convert OSM coordinates to GeoJSON order:
            # [longitude, latitude]
            ring = [
                [node["lon"], node["lat"]]
                for node in nodes
                if "lon" in node and "lat" in node
            ]

            if len(ring) < 3:
                continue

            # GeoJSON polygon rings must be closed.
            if ring[0] != ring[-1]:
                ring.append(ring[0])

            features.append({
                "type": "Feature",
                "id": f"osm-way-{element['id']}",
                "properties": {
                    "osm_id": element["id"],
                    "building": element.get("tags", {}).get(
                        "building", "yes"
                    ),
                    "name": element.get("tags", {}).get(
                        "name", "Unnamed building"
                    ),
                    "source": "OpenStreetMap",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [ring],
                },
            })

        return {
            "source": "OpenStreetMap",
            "area": "Small Chennai test area",
            "count": len(features),
            "features": features,
        }

    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=502,
            detail="Unable to retrieve building data from OpenStreetMap."
        ) from exc

@app.get("/population-estimate")
def population_estimate():
    import json
    import time
    from urllib.request import Request, urlopen

    api_url = "https://api.worldpop.org/v2"

    # Same small Chennai study area used for building footprints
    boundary = {
        "type": "Polygon",
        "coordinates": [[
            [80.245, 13.045],
            [80.255, 13.045],
            [80.255, 13.055],
            [80.245, 13.055],
            [80.245, 13.045]
        ]]
    }

    payload = {
        "geojson": boundary,
        "year": 2020,
        "resolution": "100m"
    }

    try:
        request = Request(
            f"{api_url}/population",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        with urlopen(request, timeout=30) as response:
            submitted = json.loads(response.read().decode("utf-8"))

        task_id = submitted.get("task_id")

        if not task_id:
            return {
                "status": "error",
                "message": "WorldPop did not return a task ID.",
                "details": submitted
            }

        for _ in range(15):
            time.sleep(2)

            with urlopen(
                f"{api_url}/tasks/{task_id}", timeout=30
            ) as response:
                result = json.loads(response.read().decode("utf-8"))

            if result.get("status") == "success":
                data = result.get("result", {})
                return {
                    "status": "success",
                    "source": data.get(
                        "data_source", "WorldPop Global 2"
                    ),
                    "year": data.get("data_year", 2020),
                    "population_estimate": round(
                        data.get("total_population", 0)
                    ),
                    "area_km2": data.get("area_km2"),
                    "population_density": data.get(
                        "population_density"
                    ),
                    "note": (
                        "Estimated population in the study area; "
                        "not the number of people affected by a disaster."
                    )
                }

            if result.get("status") == "failure":
                return {
                    "status": "error",
                    "message": result.get(
                        "error", "WorldPop processing failed."
                    )
                }

        return {
            "status": "processing",
            "task_id": task_id,
            "message": "The estimate is still processing. Try again later."
        }

    except Exception as error:
        return {
            "status": "error",
            "message": str(error)
        }
