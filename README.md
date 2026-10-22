# NEBULA Sci-Fi Weather Intelligence

## Features
- Multi-page sci-fi dashboard, five-day forecast, city comparison, air quality and system telemetry.
- Weather Map supports city search, interactive marker, neon-dark/street/satellite map layers, copyable coordinates and optional browser geolocation.
- AI Assistant supports general-purpose questions through Gemini, uses the selected city for relevant weather context, and displays the current conversation history during the session.
- Open-Meteo geocoding, forecast and air-quality APIs; Redis caching; Docker Compose deployment.
- Graceful fallback if Redis or the air-quality endpoint is unavailable.

## Run
1. Install and start Docker Desktop.
2. For general AI answers, create a `.env` file next to `compose.yaml` with `GEMINI_API_KEY=your_key_here`.
3. Run `docker compose up --build -d`.
4. Open http://localhost:5000.

General AI requires a valid Gemini API key and available quota. Weather data and maps require internet access. Browser location requires your explicit permission. Never commit or share your API key.

## Useful pages
- Overview: `/`
- Forecast: `/forecast`
- Weather Map: `/map`
- Air Quality: `/air-quality`
- City Compare: `/compare`
- AI Assistant: `/assistant`
- System telemetry: `/telemetry`
