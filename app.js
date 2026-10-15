const REGIONS = {
  "greater-athens": ["Barrow", "Walton", "Greene", "Morgan", "Oglethorpe", "Jackson", "Madison"],
  "athens": ["Clarke", "Oconee"],
  "greater-savannah": ["Chatham", "Bryan", "Liberty", "Effingham"],
  "gwinnett-county": ["Gwinnett"],
  "cobb-county": ["Cobb"],
  "metro-atlanta-north": ["Forsyth", "Douglas", "Cherokee", "Hall", "Bartow", "Paulding"],
  "dekalb-county": ["DeKalb"],
  "metro-atlanta-south": ["Coweta", "Henry", "Rockdale", "Newton", "Clayton", "Fayette", "Spalding", "Butts"],
  "greater-macon": ["Bibb", "Jones", "Twiggs", "Houston", "Peach", "Crawford", "Monroe"],
  "fall-line-sandhills": ["Pike", "Upson", "Lamar", "Wilkinson", "Baldwin", "Jasper", "Putnam", "Hancock", "Washington", "Pulaski", "Bleckley", "Laurens", "Johnson", "Taylor", "Macon", "Dooly", "Schley", "Dodge", "Treutlen"],
  "west-piedmont": ["Carroll", "Heard", "Haralson", "Polk"],
  "north-georgia-mountains": ["Gilmer", "Pickens", "Dawson", "Union", "Fannin", "Lumpkin", "White", "Towns", "Rabun", "Habersham"],
  "okefenokee-basin": ["Atkinson", "Ware", "Bacon", "Pierce", "Brantley", "Clinch", "Charlton"],
  "greater-valdosta": ["Colquitt", "Cook", "Brooks", "Lowndes", "Berrien", "Lanier", "Echols"],
  "lake-seminole-watershed": ["Sumter", "Crisp", "Randolph", "Terrell", "Lee", "Worth", "Turner", "Clay", "Calhoun", "Dougherty", "Tift", "Early", "Miller", "Baker", "Mitchell", "Seminole", "Decatur", "Grady", "Thomas"],
  "three-rivers-basin": ["Wilcox", "Telfair", "Ben Hill", "Irwin", "Coffee", "Jeff Davis", "Wheeler", "Montgomery", "Toombs", "Appling", "Tattnall", "Long", "Wayne"],
  "broad-river-watershed": ["Elbert", "Hart", "Stephens", "Franklin", "Banks"],
  "greater-columbus": ["Talbot", "Marion", "Stewart", "Webster", "Quitman", "Harris", "Muscogee", "Chattahoochee", "Troup", "Meriwether"],
  "golden-isles": ["McIntosh", "Glynn", "Camden"],
  "greater-augusta": ["Taliaferro", "Warren", "Glascock", "Jenkins", "Burke", "Jefferson", "McDuffie", "Lincoln", "Wilkes"],
  "augusta": ["Richmond", "Columbia"],
  "fulton-county": ["Fulton"],
  "ridge-and-valleys": ["Floyd", "Chattooga", "Walker", "Dade", "Catoosa", "Whitfield", "Gordon", "Murray"],
  "greater-statesboro": ["Emanuel", "Evans", "Candler", "Bulloch", "Screven"]
};

const REGION_GROUPS = {
  "Metro Atlanta": ["metro-atlanta-south", "metro-atlanta-north", "fulton-county", "dekalb-county", "gwinnett-county", "cobb-county"],
  "Southeast Georgia": ["golden-isles"],
  "Savannah Area": ["greater-savannah"],
  "Athens Area": ["greater-athens", "athens"],
  "Augusta Area": ["greater-augusta", "augusta"],
  "Central Georgia": ["fall-line-sandhills", "greater-macon"],
  "West Georgia": ["west-piedmont", "greater-columbus"],
  "Statesboro Area": ["greater-statesboro"],
  "North Georgia": ["broad-river-watershed", "north-georgia-mountains", "ridge-and-valleys"],
  "South Georgia": ["okefenokee-basin", "lake-seminole-watershed", "three-rivers-basin", "greater-valdosta"]
};

const COUNTY_TO_REGION = {};
for (const [regionSlug, counties] of Object.entries(REGIONS)) {
  for (const county of counties) {
    COUNTY_TO_REGION[county.toLowerCase()] = regionSlug;
  }
}

const COUNTY_TO_CATEGORY = {};
for (const [categoryName, regionSlugs] of Object.entries(REGION_GROUPS)) {
  for (const regionSlug of regionSlugs) {
    for (const county of REGIONS[regionSlug] || []) {
      COUNTY_TO_CATEGORY[county.toLowerCase()] = categoryName;
    }
  }
}

const REGION_LABELS = {
  "greater-athens": "Greater Athens",
  "athens": "Athens",
  "greater-savannah": "Greater Savannah",
  "gwinnett-county": "Gwinnett",
  "cobb-county": "Cobb",
  "metro-atlanta-north": "Metro Atlanta North",
  "dekalb-county": "Dekalb",
  "metro-atlanta-south": "Metro Atlanta South",
  "greater-macon": "Greater Macon",
  "fall-line-sandhills": "Fall Line Sandhills",
  "west-piedmont": "West Piedmont",
  "north-georgia-mountains": "North Georgia Mountains",
  "okefenokee-basin": "Okefenokee Basin",
  "greater-valdosta": "Greater Valdosta",
  "lake-seminole-watershed": "Lake Seminole Watershed",
  "three-rivers-basin": "Three Rivers Basin",
  "broad-river-watershed": "Broad River Watershed",
  "greater-columbus": "Greater Columbus",
  "golden-isles": "Golden Isles",
  "greater-augusta": "Greater Augusta",
  "augusta": "Augusta",
  "fulton-county": "Fulton",
  "ridge-and-valleys": "Ridge and Valleys",
  "greater-statesboro": "Greater Statesboro"
};

let countyGeoJson = null;

const form = {
  species: document.getElementById('species'),
  hotspot: document.getElementById('hotspot'),
  description: document.getElementById('description'),
  latitude: document.getElementById('latitude'),
  longitude: document.getElementById('longitude'),
  output: document.getElementById('discordOutput'),
  suggestions: document.getElementById('regionSuggestions')
};

let latestLocation = null;
let selectedCounty = '';
let gpsTrackingActive = false;
let gpsMap = null;
let gpsCenterPin = null;
let gpsAccuracyCircle = null;
let gpsPositionMarker = null;
let gpsPollingInterval = null;
let gpsAutoCenterUntil = 0;
let gpsTrackingStartedAt = 0;

function initLocationMap() {
  if (gpsMap) return;

  gpsMap = L.map('gpsMap', {
    zoomControl: true,
    scrollWheelZoom: true,
    dragging: true,
    attributionControl: true
  }).setView([33.7490, -84.3880], 7);

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    detectRetina: true,
    attribution: '&copy; OpenStreetMap contributors'
  }).addTo(gpsMap);

  gpsCenterPin = document.createElement('div');
  gpsCenterPin.className = 'gps-center-pin';
  gpsCenterPin.setAttribute('aria-hidden', 'true');
  document.getElementById('gpsMap').appendChild(gpsCenterPin);

  gpsAccuracyCircle = L.circle([33.7490, -84.3880], {
    radius: 25,
    color: '#3b82f6',
    fillColor: '#60a5fa',
    fillOpacity: 0.2,
    weight: 2,
    opacity: 0.8,
    interactive: false
  }).addTo(gpsMap);
  gpsAccuracyCircle.setStyle({ opacity: 0, fillOpacity: 0 });

  gpsPositionMarker = L.circleMarker([33.7490, -84.3880], {
    radius: 7,
    color: '#2563eb',
    fillColor: '#2563eb',
    fillOpacity: 1,
    weight: 2,
    interactive: false
  }).addTo(gpsMap);
  gpsPositionMarker.setStyle({ opacity: 0, fillOpacity: 0 });

  const syncMapCenter = () => {
    if (!gpsMap) return;
    const center = gpsMap.getCenter();
    gpsCenterPin.style.display = 'block';
    setLocation(center.lat, center.lng, 25);
  };

  gpsMap.on('move', () => {
    if (Date.now() > gpsAutoCenterUntil) {
      syncMapCenter();
    }
  });
  gpsMap.on('zoomend', syncMapCenter);
  window.gpsMap = gpsMap;
  window.gpsCenterPin = gpsCenterPin;
  window.gpsPositionMarker = gpsPositionMarker;
  window.gpsAccuracyCircle = gpsAccuracyCircle;
  gpsCenterPin.style.display = 'block';
  syncMapCenter();
}

function updateGpsTrackingMarker(position) {
  if (!gpsMap || !gpsPositionMarker || !gpsAccuracyCircle) return;
  const lat = position.coords.latitude;
  const lon = position.coords.longitude;
  const accuracy = Number.isFinite(position.coords.accuracy) ? position.coords.accuracy : 25;
  const center = [lat, lon];

  gpsPositionMarker.setLatLng(center);
  gpsAccuracyCircle.setLatLng(center);
  gpsAccuracyCircle.setRadius(accuracy);

  if (gpsAutoCenterUntil && Date.now() <= gpsAutoCenterUntil) {
    gpsMap.setView(center, Math.max(gpsMap.getZoom(), 14), { animate: true });
  }
}

function clearGpsTracking() {
  if (gpsPollingInterval) {
    clearInterval(gpsPollingInterval);
    gpsPollingInterval = null;
  }
  gpsAutoCenterUntil = 0;
  gpsTrackingStartedAt = 0;
  gpsTrackingActive = false;
  if (gpsAccuracyCircle) {
    gpsAccuracyCircle.setStyle({ opacity: 0, fillOpacity: 0 });
  }
  if (gpsPositionMarker) {
    gpsPositionMarker.setStyle({ opacity: 0, fillOpacity: 0 });
  }
  if (gpsCenterPin) {
    gpsCenterPin.style.display = 'block';
  }
  setGpsButtonState(false);
}

function setCopyButtonState(isSuccess) {
  const copyBtn = document.getElementById('copyBtn');
  if (!copyBtn) {
    return;
  }

  copyBtn.textContent = isSuccess ? 'Copied!' : 'Copy to clipboard';
  copyBtn.classList.toggle('success', isSuccess);
}

function setGpsButtonState(isLocating) {
  const gpsBtn = document.getElementById('useLocationBtn');
  if (!gpsBtn) {
    return;
  }

  const shouldShowMissingGps = !gpsTrackingActive && !isLocating;
  gpsBtn.textContent = isLocating ? 'LOCATING' : 'Use GPS';
  gpsBtn.disabled = isLocating;
  gpsBtn.classList.toggle('is-locating', isLocating);
  gpsBtn.classList.toggle('missing-gps', shouldShowMissingGps);
}

function resetGpsFields() {
  clearGpsTracking();
  const defaultLat = 33.7490;
  const defaultLon = -84.3880;

  form.latitude.value = defaultLat;
  form.longitude.value = defaultLon;
  latestLocation = {
    lat: defaultLat,
    lon: defaultLon,
    accuracy: 25
  };
  gpsTrackingActive = false;
  selectedCounty = '';
  if (form.suggestions) {
    form.suggestions.innerHTML = '';
  }
  if (gpsMap) {
    gpsMap.setView([defaultLat, defaultLon], gpsMap.getZoom(), { animate: false });
  }
  setGpsButtonState(false);
}

function applyFieldErrorState(field, hasError) {
  if (!field) return;
  field.classList.toggle('field-error', hasError);
}

function validateRequiredFields() {
  const speciesHasValue = form.species.value.trim().length > 0;
  const gpsHasValue = Boolean(latestLocation && Number.isFinite(latestLocation.lat) && Number.isFinite(latestLocation.lon));

  applyFieldErrorState(form.species, !speciesHasValue);

  return speciesHasValue && gpsHasValue;
}

function selectCountyOption(county) {
  if (!county) return;
  selectedCounty = county;
  const rows = renderSuggestionsFromCountyList();
  renderSuggestions(rows);
}

function toCamelCaseSpecies(value) {
  return value
    .trim()
    .toLowerCase()
    .replace(/\b([a-z])/g, (_, letter) => letter.toUpperCase())
    .replace(/\s+([A-Z])/g, ' $1');
}

function slugify(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

function formatRegionSlug(regionSlug) {
  return regionSlug ? `${regionSlug}-chat` : 'unknown-chat';
}

function formatAreaSlug(categoryName, regionSlug) {
  const regionSlugs = REGION_GROUPS[categoryName] || [];
  if (regionSlugs.length <= 1 && regionSlug) {
    return `${regionSlug}-rba`;
  }
  return `${slugify(categoryName)}-rba`;
}

function renderSuggestionsFromCountyList() {
  const counties = [...new Set((findCountyForPoint(latestLocation?.lat ?? 0, latestLocation?.lon ?? 0, Number.isFinite(latestLocation?.accuracy) ? latestLocation.accuracy : 5000) || []))].filter(Boolean);
  if (!counties.length) {
    return [];
  }

  const currentSelection = counties.includes(selectedCounty) ? selectedCounty : counties[0];
  selectedCounty = currentSelection;

  return counties.map((county) => {
    const slug = COUNTY_TO_REGION[county.toLowerCase()];
    const categoryName = COUNTY_TO_CATEGORY[county.toLowerCase()] || 'Unassigned';
    const region = formatRegionSlug(slug);
    const category = formatAreaSlug(categoryName, slug);
    return {
      county,
      region,
      category,
      selected: county === currentSelection
    };
  });
}

function formatCoordinate(value, axis) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) {
    return 'N/A';
  }
  const numeric = Number(value);
  return numeric.toFixed(axis === 'lat' ? 5 : 5);
}

function isGeorgiaLocation(lat, lon) {
  return Number.isFinite(lat) && Number.isFinite(lon)
    && lat >= 30.35 && lat <= 35.0
    && lon >= -85.6 && lon <= -81.0;
}

async function setLocation(lat, lon, accuracy) {
  const nextLat = Number(lat);
  const nextLon = Number(lon);

  form.latitude.value = nextLat;
  form.longitude.value = nextLon;
  latestLocation = {
    lat: nextLat,
    lon: nextLon,
    accuracy: Number.isFinite(accuracy) ? Number(accuracy) : null
  };

  try {
    await updateSuggestedCountyMatches(latestLocation);
  } catch (error) {
    renderSuggestions([]);
  }

  validateRequiredFields();
  scheduleLiveMessageUpdate();
}

function useMyGps() {
  if (!navigator.geolocation) {
    return;
  }

  initLocationMap();
  clearGpsTracking();
  gpsTrackingActive = true;
  setGpsButtonState(true);

  const onPosition = (position) => {
    if (!gpsTrackingStartedAt) {
      gpsTrackingStartedAt = Date.now();
    }

    const latitude = position.coords.latitude;
    const longitude = position.coords.longitude;
    const accuracy = position.coords.accuracy;

    if (gpsAccuracyCircle) {
      gpsAccuracyCircle.setStyle({ opacity: 0.8, fillOpacity: 0.2 });
    }
    if (gpsPositionMarker) {
      gpsPositionMarker.setStyle({ opacity: 1, fillOpacity: 1 });
    }

    updateGpsTrackingMarker(position);
    setLocation(latitude, longitude, accuracy);

    if (!gpsAutoCenterUntil) {
      gpsAutoCenterUntil = Date.now() + 1000;
      gpsCenterPin.style.display = 'block';
    }

    if (Date.now() - gpsTrackingStartedAt >= 1000) {
      gpsAutoCenterUntil = 0;
      gpsTrackingStartedAt = 0;
      if (gpsPollingInterval) {
        clearInterval(gpsPollingInterval);
        gpsPollingInterval = null;
      }
      setGpsButtonState(false);
    }
  };

  const onError = (error) => {
    console.warn('GPS lookup failed:', error);
    clearGpsTracking();
    validateRequiredFields();
  };

  gpsAutoCenterUntil = Date.now() + 1000;
  gpsCenterPin.style.display = 'block';
  gpsTrackingActive = true;
  gpsPollingInterval = window.setInterval(() => {
    navigator.geolocation.getCurrentPosition(onPosition, onError, {
      enableHighAccuracy: true,
      timeout: 10000,
      maximumAge: 1000
    });
  }, 250);

  navigator.geolocation.getCurrentPosition(onPosition, onError, {
    enableHighAccuracy: true,
    timeout: 10000,
    maximumAge: 1000
  });
}

function haversineKm(lat1, lon1, lat2, lon2) {
  const toRad = (value) => (value * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * 6371 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function pointInRing(point, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i][0];
    const yi = ring[i][1];
    const xj = ring[j][0];
    const yj = ring[j][1];
    const intersect = (yi > point[1]) !== (yj > point[1]) &&
      (point[0] < ((xj - xi) * (point[1] - yi)) / (yj - yi || 1) + xi);
    if (intersect) inside = !inside;
  }
  return inside;
}

function pointInPolygon(point, coordinates) {
  const rings = Array.isArray(coordinates[0]) && Array.isArray(coordinates[0][0]) ? coordinates : [coordinates];
  for (const ringSet of rings) {
    const outer = Array.isArray(ringSet[0]) && Array.isArray(ringSet[0][0]) ? ringSet[0] : ringSet;
    const holes = Array.isArray(ringSet[0]) && Array.isArray(ringSet[0][0]) ? ringSet.slice(1) : [];
    if (!pointInRing(point, outer)) continue;
    const insideHole = holes.some((hole) => pointInRing(point, hole));
    if (!insideHole) return true;
  }
  return false;
}

async function loadCountyGeodata() {
  if (countyGeoJson) return countyGeoJson;
  const response = await fetch('https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json');
  const data = await response.json();
  countyGeoJson = data.features.filter((feature) => feature.properties.STATE === '13');
  return countyGeoJson;
}

function countyCentroid(feature) {
  const geometry = feature.geometry;
  if (!geometry || !geometry.coordinates) return null;

  let polygon = null;
  if (geometry.type === 'Polygon') {
    polygon = geometry.coordinates[0];
  } else if (geometry.type === 'MultiPolygon') {
    polygon = geometry.coordinates[0][0];
  }

  if (!polygon || !polygon.length) return null;

  const center = polygon.reduce((acc, current) => {
    acc[0] += current[0];
    acc[1] += current[1];
    return acc;
  }, [0, 0]);

  return {
    lat: center[1] / polygon.length,
    lon: center[0] / polygon.length
  };
}

function polygonDistanceToBoundary(point, coordinates) {
  const rings = Array.isArray(coordinates[0]) && Array.isArray(coordinates[0][0]) ? coordinates : [coordinates];
  const originLat = Number(point[1]);
  const originLon = Number(point[0]);
  let minDistanceKm = Infinity;

  for (const ringSet of rings) {
    const outer = Array.isArray(ringSet[0]) && Array.isArray(ringSet[0][0]) ? ringSet[0] : ringSet;
    const holes = Array.isArray(ringSet[0]) && Array.isArray(ringSet[0][0]) ? ringSet.slice(1) : [];

    for (let i = 0; i < outer.length; i++) {
      const current = outer[i];
      const next = outer[(i + 1) % outer.length];
      const segmentDistance = haversineKm(
        originLat,
        originLon,
        (current[1] + next[1]) / 2,
        (current[0] + next[0]) / 2
      );
      if (segmentDistance < minDistanceKm) {
        minDistanceKm = segmentDistance;
      }
    }

    if (holes.some((hole) => pointInRing(point, hole))) {
      return 0;
    }
  }

  return minDistanceKm;
}

function findCountyForPoint(lat, lon, accuracyMeters = 5000) {
  if (!countyGeoJson) return null;
  const point = [lon, lat];

  const exactMatches = countyGeoJson
    .filter((feature) => {
      const geometry = feature.geometry;
      if (!geometry) return false;
      if (geometry.type === 'Polygon') {
        return pointInPolygon(point, geometry.coordinates);
      }
      if (geometry.type === 'MultiPolygon') {
        return geometry.coordinates.some((polygon) => pointInPolygon(point, polygon));
      }
      return false;
    })
    .map((feature) => feature.properties.NAME);

  return exactMatches;
}

function getSuggestedRegions(lat, lon, accuracyMeters = 5000) {
  const countyMatches = findCountyForPoint(lat, lon, accuracyMeters) || [];
  if (countyMatches.length > 0) {
    return [...new Set(countyMatches
      .map((county) => COUNTY_TO_REGION[county.toLowerCase()])
      .filter(Boolean))].slice(0, 2);
  }

  return [];
}

function getSuggestedCategories(regionSlugs) {
  const regionSet = new Set(regionSlugs || []);
  const categories = [];
  for (const [category, slugs] of Object.entries(REGION_GROUPS)) {
    const categoryMatches = slugs.filter((slug) => regionSet.has(slug));
    if (categoryMatches.length > 0) {
      categories.push(category);
    }
  }
  return categories;
}

function updateCountyOptions(countyNames) {
  const counties = [...new Set(countyNames || [])].filter(Boolean);
  if (!counties.length) {
    selectedCounty = '';
    renderSuggestions([]);
    return;
  }

  const currentSelection = counties.includes(selectedCounty) ? selectedCounty : counties[0];
  selectedCounty = currentSelection;

  const rows = counties.map((county) => {
    const slug = COUNTY_TO_REGION[county.toLowerCase()];
    const categoryName = COUNTY_TO_CATEGORY[county.toLowerCase()] || 'Unassigned';
    const region = formatRegionSlug(slug);
    const category = formatAreaSlug(categoryName, slug);
    return {
      county,
      region,
      category,
      selected: county === currentSelection
    };
  });

  renderSuggestions(rows);
}

function renderSuggestions(rows) {
  form.suggestions.innerHTML = '';

  if (!rows.length) {
    return;
  }

  const row = rows[0] || {};
  const fields = [
    { label: 'County', value: row.county && row.county !== '—' ? row.county : '' },
    { label: 'Region', value: row.region || '' },
    { label: 'Area RBA', value: row.category || '' }
  ];

  const wrapper = document.createElement('div');
  wrapper.className = 'suggestion-input-row';

  fields.forEach(({ label, value }) => {
    const fieldWrap = document.createElement('div');
    fieldWrap.className = 'suggestion-field';

    const labelEl = document.createElement('label');
    labelEl.textContent = label;

    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'journal-input suggestion-readonly';
    input.value = value;
    input.readOnly = true;
    input.setAttribute('aria-label', label);
    input.setAttribute('aria-live', 'polite');

    fieldWrap.appendChild(labelEl);
    fieldWrap.appendChild(input);
    wrapper.appendChild(fieldWrap);
  });

  form.suggestions.appendChild(wrapper);
}

function buildSuggestionRows(regionSuggestions, categorySuggestions) {
  const byRegion = new Map();
  for (const regionSlug of regionSuggestions) {
    const matchingCategories = categorySuggestions.filter((category) => {
      const regionSlugs = REGION_GROUPS[category] || [];
      return regionSlugs.includes(regionSlug);
    });
    const category = matchingCategories[0] || '—';
    byRegion.set(regionSlug, category);
  }

  return [...byRegion.entries()].map(([regionSlug, categoryName]) => ({
    region: formatRegionSlug(regionSlug),
    category: categoryName === '—' ? '—' : formatAreaSlug(categoryName, regionSlug)
  }));
}

async function updateSuggestedCountyMatches(location) {
  if (!location) {
    selectedCounty = '';
    renderSuggestions([]);
    return;
  }

  const counties = findCountyForPoint(location.lat, location.lon, Number.isFinite(location.accuracy) ? location.accuracy : 5000) || [];
  if (!counties.length) {
    selectedCounty = '';
    renderSuggestions([]);
    return;
  }

  updateCountyOptions(counties);
}

async function generateMessage() {
  const speciesValue = form.species.value.trim();
  const species = toCamelCaseSpecies(speciesValue);
  const hotspot = toCamelCaseSpecies(form.hotspot.value.trim());
  const description = form.description.value.trim();
  const location = latestLocation;

  if (!speciesValue) {
    form.output.value = '';
    if (location) {
      const countyNames = findCountyForPoint(location.lat, location.lon, Number.isFinite(location.accuracy) ? location.accuracy : 5000) || [];
      if (countyNames.length) {
        updateCountyOptions(countyNames);
      } else {
        selectedCounty = '';
        renderSuggestions([]);
      }
    }
    return;
  }

  if (!validateRequiredFields()) {
    form.output.value = '';
    return;
  }

  try {
    await loadCountyGeodata();
  } catch (error) {
    // Fall back to the locally matched county data when the geodata fetch is unavailable.
  }

  const countyNames = findCountyForPoint(location.lat, location.lon, Number.isFinite(location.accuracy) ? location.accuracy : 5000) || [];
  if (!countyNames.length) {
    selectedCounty = '';
    const today = new Date();
    const formattedDate = `${String(today.getMonth() + 1).padStart(2, '0')}/${String(today.getDate()).padStart(2, '0')}/${today.getFullYear()}`;
    const formattedTime = new Intl.DateTimeFormat('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: true
    }).format(today).replace(' ', '').replace(':', ':');
    const title = `${species}${hotspot ? ` - ${hotspot}` : ''} - ${formattedDate}`;
    const gpsText = `${formatCoordinate(location.lat, 'lat')}, ${formatCoordinate(location.lon, 'lon')}`;
    const notesText = description ? ` ${description}` : '';
    form.output.value = `${title}\n> ${gpsText} @ ${formattedTime}.${notesText}`;
    renderSuggestions([]);
    return;
  }

  const validCounty = countyNames.find((county) => county && county.toLowerCase() === selectedCounty?.toLowerCase()) || countyNames[0] || 'Unknown County';
  const selectedCountyName = validCounty;
  selectedCounty = validCounty;
  const countySlug = COUNTY_TO_REGION[(validCounty || '').toLowerCase()];

  const regionSuggestions = selectedCountyName && countySlug
    ? [countySlug]
    : [];
  const categorySuggestions = selectedCountyName
    ? [COUNTY_TO_CATEGORY[(validCounty || '').toLowerCase()] || 'Unassigned']
    : [];

  const today = new Date();
  const formattedDate = `${String(today.getMonth() + 1).padStart(2, '0')}/${String(today.getDate()).padStart(2, '0')}/${today.getFullYear()}`;
  const formattedTime = new Intl.DateTimeFormat('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: true
  }).format(today).replace(' ', '').replace(':', ':');
  const title = `${species}${hotspot ? ` - ${hotspot}` : ''} (${selectedCountyName}) - ${formattedDate}`;
  const gpsText = `${formatCoordinate(location.lat, 'lat')}, ${formatCoordinate(location.lon, 'lon')}`;
  const notesText = description ? ` ${description}` : '';
  const text = `${title}\n> ${gpsText} @ ${formattedTime}.${notesText}`;

  form.output.value = text;
  renderSuggestions([{
    county: selectedCountyName,
    region: regionSuggestions[0] ? formatRegionSlug(regionSuggestions[0]) : '',
    category: categorySuggestions[0] ? formatAreaSlug(categorySuggestions[0], regionSuggestions[0]) : '',
    selected: true
  }]);
}

async function copyMessage() {
  const text = form.output.value.trim();
  if (!text) {
    return;
  }

  const copyBtn = document.getElementById('copyBtn');

  try {
    await navigator.clipboard.writeText(text);
  } catch (error) {
    form.output.focus();
    form.output.select();
    document.execCommand('copy');
  } finally {
    setCopyButtonState(true);
    const existingTimer = Number(copyBtn?.dataset?.resetTimer);
    if (Number.isFinite(existingTimer)) {
      clearTimeout(existingTimer);
    }
    copyBtn.dataset.resetTimer = window.setTimeout(() => {
      setCopyButtonState(false);
    }, 1200).toString();
  }
}

let liveUpdateTimer = null;

function scheduleLiveMessageUpdate() {
  clearTimeout(liveUpdateTimer);
  liveUpdateTimer = setTimeout(() => {
    generateMessage();
  }, 150);
}

initLocationMap();
document.getElementById('useLocationBtn').addEventListener('click', useMyGps);
document.getElementById('copyBtn').addEventListener('click', copyMessage);
form.species.addEventListener('input', () => {
  validateRequiredFields();
  scheduleLiveMessageUpdate();
});
form.hotspot.addEventListener('input', scheduleLiveMessageUpdate);
form.description.addEventListener('input', scheduleLiveMessageUpdate);
window.addEventListener('beforeunload', resetGpsFields);

resetGpsFields();
validateRequiredFields();
renderSuggestions([]);
