from flask import Flask, render_template, request, jsonify
import os, time, requests

try:
    import redis
    r = redis.Redis(host=os.getenv('REDIS_HOST', 'localhost'), port=6379, decode_responses=True, socket_connect_timeout=1, socket_timeout=1)
    r.ping()
except Exception:
    r = None

app = Flask(__name__)
stats = {'requests': 0, 'cache_hits': 0, 'api_calls': 0}
BASE = 'https://api.open-meteo.com/v1'
AIR_BASE = 'https://air-quality-api.open-meteo.com/v1'
GEO = 'https://geocoding-api.open-meteo.com/v1/search'


def fetch_json(url, params):
    stats['api_calls'] += 1
    response = requests.get(url, params=params, timeout=12)
    response.raise_for_status()
    return response.json()


def get_weather(city, coordinates=None):
    city = (city or 'Pune').strip()
    key_suffix = (f'{float(coordinates[0]):.3f},{float(coordinates[1]):.3f}' if coordinates else city.lower())
    key = 'nebula:v3:weather:' + key_suffix
    if r:
        try:
            cached = r.get(key)
            if cached:
                stats['cache_hits'] += 1
                import json
                return json.loads(cached)
        except Exception:
            pass
    if coordinates:
        lat, lon = float(coordinates[0]), float(coordinates[1])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError('Invalid map coordinates.')
        # Browser coordinates can be used directly; no reverse-geocoding service is required.
        place = {'latitude': lat, 'longitude': lon, 'name': 'Your location', 'country': ''}
    else:
        geo = fetch_json(GEO, {'name': city, 'count': 1, 'language': 'en', 'format': 'json'})
        results = geo.get('results') or []
        if not results:
            raise ValueError(f'Could not find city: {city}')
        place = results[0]
        lat, lon = place['latitude'], place['longitude']
    forecast = fetch_json(f'{BASE}/forecast', {
        'latitude': lat, 'longitude': lon,
        'current': 'temperature_2m,relative_humidity_2m,apparent_temperature,is_day,precipitation,weather_code,wind_speed_10m',
        'hourly': 'temperature_2m,precipitation_probability',
        'daily': 'weather_code,temperature_2m_max,temperature_2m_min,uv_index_max,sunrise,sunset',
        'timezone': 'auto', 'forecast_days': 5
    })
    # Air quality uses a separate Open-Meteo host, not api.open-meteo.com.
    try:
        air = fetch_json(f'{AIR_BASE}/air-quality', {
            'latitude': lat, 'longitude': lon,
            'current': 'us_aqi,pm2_5,pm10', 'timezone': 'auto'
        })
    except Exception:
        # Keep the main weather dashboard available if air-quality data is temporarily unavailable.
        air = {}
    cur = forecast.get('current', {})
    daily = forecast.get('daily', {})
    hourly = forecast.get('hourly', {})
    ac = air.get('current', {})
    code = cur.get('weather_code', 0)
    descriptions = {0:'Clear sky',1:'Mainly clear',2:'Partly cloudy',3:'Overcast',45:'Fog',48:'Depositing rime fog',51:'Light drizzle',53:'Drizzle',55:'Dense drizzle',61:'Slight rain',63:'Moderate rain',65:'Heavy rain',71:'Slight snow',73:'Moderate snow',75:'Heavy snow',80:'Rain showers',81:'Moderate rain showers',82:'Violent rain showers',95:'Thunderstorm',96:'Thunderstorm with hail',99:'Heavy thunderstorm'}
    icons = {0:'☀️',1:'🌤️',2:'⛅',3:'☁️',45:'🌫️',48:'🌫️',51:'🌦️',53:'🌦️',55:'🌧️',61:'🌧️',63:'🌧️',65:'🌧️',71:'🌨️',73:'🌨️',75:'❄️',80:'🌦️',81:'🌧️',82:'⛈️',95:'⛈️',96:'⛈️',99:'⛈️'}
    hours = []
    now = cur.get('time', '')
    times = hourly.get('time', [])
    start = next((i for i, t in enumerate(times) if t >= now), 0)
    for i in range(start, min(start + 24, len(times))):
        hours.append({'time': times[i][-5:], 'temp': hourly.get('temperature_2m', [])[i], 'rain': hourly.get('precipitation_probability', [])[i]})
    days = []
    for i, date in enumerate(daily.get('time', [])):
        dc = daily.get('weather_code', [0] * len(daily.get('time', [])))[i]
        days.append({'date': date, 'icon': icons.get(dc, '🌡️'), 'max': daily.get('temperature_2m_max', [])[i], 'min': daily.get('temperature_2m_min', [])[i], 'uv': daily.get('uv_index_max', [])[i], 'sunrise': daily.get('sunrise', ['—'])[i][-5:], 'sunset': daily.get('sunset', ['—'])[i][-5:]})
    data = {'city': place.get('name', city), 'country': place.get('country', ''), 'lat': lat, 'lon': lon,
        'temp': cur.get('temperature_2m', '—'), 'feels': cur.get('apparent_temperature', '—'),
        'humidity': cur.get('relative_humidity_2m', '—'), 'wind': cur.get('wind_speed_10m', '—'),
        'rain': cur.get('precipitation', 0), 'code': code, 'description': descriptions.get(code, 'Current conditions'),
        'icon': icons.get(code, '🌡️'), 'time': now.replace('T', ' '), 'hours': hours, 'forecast': days,
        'aqi': ac.get('us_aqi'), 'pm25': ac.get('pm2_5'), 'pm10': ac.get('pm10')}
    if r:
        try:
            import json
            r.setex(key, 600, json.dumps(data))
        except Exception:
            pass
    return data


def safe_weather(city):
    try:
        return get_weather(city), None
    except Exception as e:
        return None, str(e)


@app.before_request
def count_request():
    stats['requests'] += 1


@app.route('/')
def home():
    city = request.args.get('city', 'Pune')
    weather, error = safe_weather(city)
    return render_template('index.html', weather=weather, city=city, error=error)

@app.route('/forecast')
def forecast_page():
    city = request.args.get('city', 'Pune')
    weather, error = safe_weather(city)
    return render_template('forecast.html', weather=weather, city=city, error=error)

@app.route('/map')
def map_page():
    city = request.args.get('city', 'Pune')
    lat, lon = request.args.get('lat'), request.args.get('lon')
    if lat is not None and lon is not None:
        try:
            weather = get_weather('Your location', (lat, lon))
            error = None
            city = weather['city']
        except Exception as exc:
            weather, error = None, str(exc)
    else:
        weather, error = safe_weather(city)
    return render_template('map.html', weather=weather, city=city, error=error)

@app.route('/air-quality')
def air_page():
    city = request.args.get('city', 'Pune')
    weather, error = safe_weather(city)
    return render_template('air.html', weather=weather, city=city, error=error)

@app.route('/compare')
def compare_page():
    return render_template('compare.html')

@app.route('/assistant')
def assistant_page():
    city = request.args.get('city', 'Pune')
    return render_template('assistant.html', city=city)

@app.route('/travel')
def travel_page():
    origin = request.args.get('origin', 'Pune')
    destination = request.args.get('destination', 'Mumbai')
    return render_template('travel.html', origin=origin, destination=destination)

@app.route('/telemetry')
def telemetry_page():
    return render_template('telemetry.html')

@app.route('/api/weather')
def api_weather():
    data, error = safe_weather(request.args.get('city', 'Pune'))
    return (jsonify(data), 200) if data else (jsonify({'error': error}), 400)

@app.route('/api/compare')
def api_compare():
    cities = [c.strip() for c in request.args.get('cities', 'Pune,Mumbai,Delhi,Bengaluru,Chennai').split(',') if c.strip()][:8]
    results = []
    for city in cities:
        data, error = safe_weather(city)
        if data:
            results.append({k: data[k] for k in ('city','country','temp','humidity','wind','icon','description')})
    return jsonify({'cities': results, 'requested': cities, 'loaded': len(results)})

@app.route('/api/assistant', methods=['POST'])
def api_assistant():
    body = request.get_json(silent=True) or {}
    city = (body.get('city') or 'Pune').strip()
    question = (body.get('question') or '').strip()
    if not question:
        return jsonify({'error': 'Type a question first.'}), 400

    # Gemini gives the assistant general-purpose conversation, not only weather replies.
    # Keep the key on the server; never send it to the browser.
    api_key = os.getenv('GEMINI_API_KEY', '').strip()
    if api_key:
        try:
            weather, weather_error = safe_weather(city)
            context = ''
            if weather:
                context = (f"\n\nLive weather context for {weather['city']}: "
                           f"{weather['temp']}°C, feels like {weather['feels']}°C, "
                           f"{weather['description']}, humidity {weather['humidity']}%, "
                           f"wind {weather['wind']} km/h, US AQI {weather['aqi']}. "
                           "Use these values only when relevant and say when a value is unavailable.")
            prompt = ("You are NEBULA, a helpful general-purpose AI assistant inside a weather app. "
                      "Answer the user's question clearly and naturally. You can help with study, coding, "
                      "science, writing, everyday questions, and weather. The user's selected city is " + city + ". "
                      "If the question asks for live facts, don't invent them; use only the provided weather context "
                      "and clearly say when data is unavailable. Do not claim to have browsed the web. "
                      "Be concise but useful.\n\nUser question: " + question + context)
            response = requests.post(
                'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent',
                params={'key': api_key},
                json={'contents': [{'parts': [{'text': prompt}]}],
                     'generationConfig': {'temperature': 0.7, 'maxOutputTokens': 900}},
                timeout=30)
            response.raise_for_status()
            result = response.json()
            answer = ''.join(part.get('text', '') for part in
                             result.get('candidates', [{}])[0].get('content', {}).get('parts', []))
            if answer.strip():
                return jsonify({'answer': answer.strip(), 'mode': 'general-ai'})
            return jsonify({'error': 'AI returned an empty answer. Please try again.'}), 502
        except requests.RequestException as exc:
            app.logger.warning('Gemini request failed: %s', exc)
            return jsonify({'error': 'The AI service could not respond. Check your Gemini API key, internet connection, and API quota, then try again.'}), 502
        except (KeyError, IndexError, TypeError, ValueError):
            return jsonify({'error': 'Could not read the AI response. Please try again.'}), 502

    # Useful weather-only fallback when no Gemini key has been configured.
    data, error = safe_weather(city)
    if not data:
        return jsonify({'error': error or 'Weather unavailable. Add GEMINI_API_KEY to enable general questions.'}), 400
    q = question.lower()
    if any(word in q for word in ('rain', 'umbrella', 'raining')):
        rain = max([h['rain'] or 0 for h in data['hours'][:12]] or [0])
        answer = f"{data['city']}: current precipitation is {data['rain']} mm. Highest rain probability in the next 12 hours is {rain}%. {'Consider carrying an umbrella.' if rain >= 40 else 'Rain probability looks relatively low, but check again before heading out.'}"
    elif 'wind' in q:
        answer = f"Wind in {data['city']} is around {data['wind']} km/h."
    elif 'humidity' in q:
        answer = f"Relative humidity in {data['city']} is {data['humidity']}%."
    elif any(word in q for word in ('air quality', 'aqi', 'pollution', 'pm2.5', 'pm10')):
        answer = f"US AQI: {data['aqi'] if data['aqi'] is not None else 'unavailable'}, PM2.5: {data['pm25'] if data['pm25'] is not None else 'unavailable'}, PM10: {data['pm10'] if data['pm10'] is not None else 'unavailable'}."
    elif any(word in q for word in ('weather', 'temperature', 'forecast', 'hot', 'cold', 'condition')):
        answer = f"{data['city']} is currently {data['description'].lower()} at {data['temp']}°C, feels like {data['feels']}°C, with {data['humidity']}% humidity and wind at {data['wind']} km/h."
    else:
        return jsonify({'answer': 'General questions need a Gemini API key. Add GEMINI_API_KEY to the web service environment in compose.yaml, then rebuild the app. Weather questions work without the key.', 'mode': 'weather-fallback', 'setup_required': True})
    return jsonify({'answer': answer, 'mode': 'weather-fallback'})

@app.route('/health')
def health():
    redis_status = 'connected' if r else 'not configured'
    if r:
        try: r.ping()
        except Exception: redis_status = 'unavailable'
    return jsonify({'status':'online','redis':redis_status, **stats})



@app.route('/api/facilities')
def api_facilities():
    """Find nearby rider/traveller facilities using OpenStreetMap Overpass."""
    try:
        lat = float(request.args.get('lat', ''))
        lon = float(request.args.get('lon', ''))
        radius = min(max(int(request.args.get('radius', '5000')), 500), 10000)
        category = (request.args.get('category') or 'all').lower()
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError('Invalid coordinates.')
    except (TypeError, ValueError):
        return jsonify({'error': 'Valid latitude and longitude are required.'}), 400

    filters = {
        'fuel': 'node[amenity=fuel](around:{radius},{lat},{lon});way[amenity=fuel](around:{radius},{lat},{lon});',
        'repair': 'node[shop=car_repair](around:{radius},{lat},{lon});way[shop=car_repair](around:{radius},{lat},{lon});node[shop=motorcycle](around:{radius},{lat},{lon});way[shop=motorcycle](around:{radius},{lat},{lon});',
        'medical': 'node[amenity~"hospital|clinic|pharmacy"](around:{radius},{lat},{lon});way[amenity~"hospital|clinic|pharmacy"](around:{radius},{lat},{lon});',
        'food': 'node[amenity~"restaurant|cafe|fast_food"](around:{radius},{lat},{lon});way[amenity~"restaurant|cafe|fast_food"](around:{radius},{lat},{lon});',
        'toilet': 'node[amenity=toilets](around:{radius},{lat},{lon});way[amenity=toilets](around:{radius},{lat},{lon});',
        'stay': 'node[tourism~"hotel|motel|guest_house|hostel"](around:{radius},{lat},{lon});way[tourism~"hotel|motel|guest_house|hostel"](around:{radius},{lat},{lon});',
        'parking': 'node[amenity=parking](around:{radius},{lat},{lon});way[amenity=parking](around:{radius},{lat},{lon});',
    }
    cats = list(filters) if category == 'all' else ([category] if category in filters else [])
    if not cats:
        return jsonify({'error': 'Unknown facility category.'}), 400
    clauses = ''.join(filters[c].format(radius=radius, lat=lat, lon=lon) for c in cats)
    query = '[out:json][timeout:20];(' + clauses + ');out center tags 80;'
    try:
        response = requests.post('https://overpass-api.de/api/interpreter', data={'data': query}, timeout=25,
                                 headers={'User-Agent': 'NEBULA-Weather-Intelligence/1.0'})
        response.raise_for_status()
        elements = response.json().get('elements', [])
        results = []
        labels = {'fuel':'Fuel station','repair':'Bike / vehicle repair','medical':'Medical help','food':'Food & cafe','toilet':'Public toilet','stay':'Stay / lodging','parking':'Parking'}
        for el in elements:
            tags = el.get('tags', {})
            plat = el.get('lat', (el.get('center') or {}).get('lat'))
            plon = el.get('lon', (el.get('center') or {}).get('lon'))
            if plat is None or plon is None: continue
            amenity = tags.get('amenity','')
            shop = tags.get('shop','')
            tourism = tags.get('tourism','')
            if amenity == 'fuel': cat='fuel'
            elif shop in ('car_repair','motorcycle'): cat='repair'
            elif amenity in ('hospital','clinic','pharmacy'): cat='medical'
            elif amenity in ('restaurant','cafe','fast_food'): cat='food'
            elif amenity == 'toilets': cat='toilet'
            elif tourism in ('hotel','motel','guest_house','hostel'): cat='stay'
            elif amenity == 'parking': cat='parking'
            else: continue
            name = tags.get('name') or labels[cat]
            address = ', '.join(filter(None, [tags.get('addr:street'), tags.get('addr:city')]))
            results.append({'id':str(el.get('type','node'))+str(el.get('id','')), 'name':name, 'category':cat,
                            'category_label':labels[cat], 'lat':float(plat), 'lon':float(plon),
                            'address':address, 'phone':tags.get('phone') or tags.get('contact:phone',''),
                            'opening_hours':tags.get('opening_hours',''), 'distance_km':round(((float(plat)-lat)**2 + ((float(plon)-lon)*__import__('math').cos(__import__('math').radians(lat)))**2)**0.5*111,2)})
        results.sort(key=lambda item: item['distance_km'])
        return jsonify({'facilities':results[:80], 'count':len(results[:80]), 'radius_m':radius,
                        'source':'OpenStreetMap contributors', 'note':'Availability, opening hours and contact details may be incomplete; call ahead when possible.'})
    except requests.RequestException:
        app.logger.exception('Nearby facility lookup failed')
        return jsonify({'error':'Nearby facility service is temporarily unavailable. Please try again in a moment.'}), 502
    except (ValueError, TypeError):
        return jsonify({'error':'Could not read facility data. Please try again.'}), 502

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
