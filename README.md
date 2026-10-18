# ResQ – AI-Powered Disaster Management Platform

## Project Overview
ResQ is an emergency response intelligence platform designed to support disaster monitoring, geospatial impact assessment, and relief coordination. It brings disaster information and geographical data together in a single dashboard to help response teams understand developing situations.

## Features Implemented
- **Live Earthquake Monitoring:** Retrieves earthquake information from the USGS feed.
- **Live Disaster Monitoring:** Retrieves disaster event information from the GDACS feed.
- **Incident Management:** Stores and retrieves manually reported incidents using PostgreSQL.
- **Geospatial Map:** Displays disaster event locations and mapped building footprints.
- **Population Estimation:** Retrieves an estimated population figure for a selected Chennai study area using WorldPop data.
- **User Login and Signup:** Provides a basic login and signup interface connected to the backend.

## Technology Stack
- **Frontend:** React.js, Vite, CSS, React Leaflet
- **Backend:** Python, FastAPI
- **Database:** PostgreSQL
- **External Data Sources:** USGS, GDACS, OpenStreetMap, WorldPop

## Project Structure
- `frontend/` – React dashboard, authentication interface, and disaster map.
- `backend/` – FastAPI endpoints, database operations, and external data integrations.
- `.gitignore` – Excludes selected environment and generated files.

## Running the Project Locally

### Backend
1. Open a terminal in the `backend` directory.
2. Configure the required database credentials in a local `.env` file.
3. Install the Python dependencies listed in `requirements.txt`, if provided.
4. Start the server:

   `python -m uvicorn main:app --reload`

5. Open `http://127.0.0.1:8000/docs` to access the API documentation.

### Frontend
1. Open another terminal in the `frontend` directory.
2. Install the dependencies using `npm install`.
3. Start the development server using `npm run dev`.
4. Open the local URL displayed in the terminal, usually `http://localhost:5173`.

## Work in Progress
- Estimating buildings and population within a defined disaster impact area.
- Integrating accessible NDMA/SACHET alert data.
- Developing a grid-based disaster severity assessment.
- Exploring satellite imagery for disaster extent and damage assessment.
- Improving error handling, testing, and deployment readiness.

## Important Note
This is a project under development. Population values are estimates for the study area and should not be interpreted as confirmed numbers of people affected by a disaster. Mapped buildings do not automatically indicate damaged buildings. Live data availability depends on the external data providers.

## Future Scope
- AI-based estimation of food, water, medical, and shelter requirements.
- Relief resource inventory and allocation.
- Field team coordination and route planning.
- Post-disaster reporting and preparedness analysis.

## Data Attribution
- Earthquake information: USGS
- Disaster event information: GDACS
- Building footprints and map data: OpenStreetMap contributors
- Population estimates: WorldPop


