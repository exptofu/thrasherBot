const STORAGE_KEY = "georgia-region-editor-state-v1";
const FALLBACK_COLORS = [
  "#4f46e5",
  "#14b8a6",
  "#f59e0b",
  "#ef4444",
  "#8b5cf6",
  "#f97316",
  "#10b981",
  "#ec4899",
  "#06b6d4",
];

const DEFAULT_REGIONS = {
  "greater-athens-area": { label: "Greater Athens Area", color: "#b8323c", counties: ["Barrow", "Walton", "Greene", "Morgan", "Oconee", "Oglethorpe", "Clarke", "Jackson", "Madison"] },
  "greater-savannah-area": { label: "Greater Savannah Area", color: "#2878a0", counties: ["Chatham", "Bryan", "Liberty", "Effingham"] },
  "gwinnett-county": { label: "Gwinnett", color: "#b39b00", counties: ["Gwinnett"] },
  "metro-atlanta-north": { label: "Metro Atlanta North", color: "#4f8f3a", counties: ["Cobb", "Forsyth", "Douglas", "Cherokee", "Hall", "Bartow", "Paulding"] },
  "dekalb-county": { label: "Dekalb", color: "#707070", counties: ["DeKalb"] },
  "metro-atlanta-south": { label: "Metro Atlanta South", color: "#8c4824", counties: ["Coweta", "Henry", "Rockdale", "Newton", "Clayton", "Fayette"] },
  "bibb-county": { label: "Bibb", color: "#08786e", counties: ["Bibb"] },
  "fall-line-sandhills": { label: "Fall Line Sandhills", color: "#c45b00", counties: ["Spalding", "Pike", "Upson", "Lamar", "Monroe", "Crawford", "Peach", "Houston", "Twiggs", "Jones", "Wilkinson", "Baldwin", "Butts", "Jasper", "Putnam", "Hancock", "Washington", "Dodge", "Pulaski", "Bleckley", "Laurens", "Johnson", "Taylor", "Macon", "Dooly", "Talbot", "Marion", "Schley", "Taliaferro", "Warren", "Glascock", "Emanuel"] },
  "west-piedmont": { label: "West Piedmont", color: "#17605c", counties: ["Carroll", "Heard", "Troup", "Meriwether", "Stewart", "Haralson", "Polk"] },
  "north-georgia-mountains": { label: "North Georgia Mountains", color: "#4e9b8d", counties: ["Floyd", "Chattooga", "Walker", "Dade", "Catoosa", "Whitfield", "Gordon", "Murray", "Gilmer", "Pickens", "Dawson", "Union", "Fannin", "Lumpkin", "White", "Towns", "Rabun", "Habersham"] },
  "inland-coastal-plain": { label: "Inland Coastal Plain", color: "#82609f", counties: ["Irwin", "Ben Hill", "Lee", "Terrell", "Sumter", "Calhoun", "Webster", "Worth", "Crisp", "Colquitt", "Grady", "Thomas", "Brooks", "Lowndes", "Echols", "Clinch", "Charlton", "Ware", "Berrien", "Cook", "Lanier", "Atkinson", "Turner", "Tift", "Coffee", "Wilcox", "Telfair", "Wheeler", "Jeff Davis", "Appling", "Bacon", "Pierce", "Decatur", "Mitchell", "Baker", "Miller", "Seminole", "Early", "Clay", "Quitman", "Randolph", "Dougherty", "Toombs", "Montgomery", "Treutlen", "Tattnall", "Evans", "Candler", "Bulloch", "Screven"] },
  "broad-river-watershed": { label: "Broad River Watershed", color: "#365f9e", counties: ["Elbert", "Hart", "Stephens", "Franklin", "Banks"] },
  "columbus-area": { label: "Columbus Area", color: "#ad4f8c", counties: ["Harris", "Muscogee", "Chattahoochee"] },
  "golden-isles": { label: "Golden Isles", color: "#b8860b", counties: ["Wayne", "Long", "McIntosh", "Glynn", "Brantley", "Camden"] },
  "greater-augusta-area": { label: "Greater Augusta Area", color: "#087fa5", counties: ["Jenkins", "Burke", "Jefferson", "Richmond", "McDuffie", "Columbia", "Lincoln", "Wilkes"] },
  "fulton-county": { label: "Fulton", color: "#bd7745", counties: ["Fulton"] },
};

const appState = {
  countyAssignments: {},
  customRegions: {},
};

const mapContainer = document.getElementById("mapContainer");
const regionLegend = document.getElementById("regionLegend");
const countyModal = document.getElementById("countyModal");
const countyNameEl = document.getElementById("countyName");
const regionSelect = document.getElementById("regionSelect");

function normalizeCountyKey(countyName) {
  return countyName.trim().replace(/\s+county$/i, "").replace(/\s+/g, " ").toLowerCase();
}

function slugify(value) {
  const slug = value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug || "region";
}

function getDefaultAssignments() {
  const assignments = {};
  Object.entries(DEFAULT_REGIONS).forEach(([slug, { counties }]) => {
    counties.forEach((county) => {
      assignments[normalizeCountyKey(county)] = slug;
    });
  });
  return assignments;
}

function loadState() {
  const fallbackAssignments = getDefaultAssignments();
  const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null") || {};

  appState.countyAssignments = { ...fallbackAssignments, ...(saved.countyAssignments || {}) };
  appState.customRegions = saved.customRegions || {};
}

function persistState() {
  const payload = {
    countyAssignments: appState.countyAssignments,
    customRegions: appState.customRegions,
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
}

function hasRegion(regionSlug) {
  return Boolean(DEFAULT_REGIONS[regionSlug] || appState.customRegions[regionSlug]);
}

function getRegionMeta(regionSlug) {
  if (DEFAULT_REGIONS[regionSlug]) {
    return { ...DEFAULT_REGIONS[regionSlug], slug: regionSlug };
  }

  if (appState.customRegions[regionSlug]) {
    return { ...appState.customRegions[regionSlug], slug: regionSlug };
  }

  return { label: "Unknown", color: "#64748b", slug: regionSlug };
}

function getRegionOrder() {
  const regionIds = [...Object.keys(DEFAULT_REGIONS), ...Object.keys(appState.customRegions)];
  const seen = new Set();
  return regionIds.filter((slug) => {
    if (seen.has(slug)) {
      return false;
    }
    seen.add(slug);
    return true;
  });
}

function renderLegend() {
  const regionOrder = getRegionOrder();
  regionLegend.innerHTML = regionOrder
    .map((slug) => {
      const { label, color } = getRegionMeta(slug);
      return `
        <li class="legend-item">
          <span class="legend-swatch" style="background:${color};"></span>
          <span>${label}</span>
        </li>
      `;
    })
    .join("");
}

function nextCustomColor() {
  const usedColors = new Set(Object.values(DEFAULT_REGIONS).map((entry) => entry.color));
  Object.values(appState.customRegions).forEach((entry) => usedColors.add(entry.color));

  const chosen = FALLBACK_COLORS.find((color) => !usedColors.has(color));
  return chosen || FALLBACK_COLORS[FALLBACK_COLORS.length - 1];
}

function applyMapColors(svgDocument) {
  const countyPaths = svgDocument.querySelectorAll("path");
  countyPaths.forEach((path) => {
    const titleNode = path.querySelector("title");
    const rawText = titleNode ? titleNode.textContent : "";
    const countyName = rawText.split("-")[0].trim();
    const countyKey = normalizeCountyKey(countyName);
    const regionSlug = appState.countyAssignments[countyKey] || Object.keys(DEFAULT_REGIONS)[0];
    const regionMeta = getRegionMeta(regionSlug);

    path.setAttribute("fill", regionMeta.color);
    path.dataset.countyName = countyName;
    path.dataset.regionSlug = regionSlug;
    if (titleNode) {
      titleNode.textContent = `${countyName} - ${regionMeta.label}`;
    }
  });
}

function openCountyPicker(countyName) {
  const regionSlug = appState.countyAssignments[normalizeCountyKey(countyName)] || Object.keys(DEFAULT_REGIONS)[0];
  const currentRegion = regionSlug;

  countyNameEl.textContent = countyName;

  const options = getRegionOrder()
    .map((slug) => `<option value="${slug}" ${slug === currentRegion ? "selected" : ""}>${getRegionMeta(slug).label}</option>`)
    .join("");

  regionSelect.innerHTML = `
    <option value="__new__">+ Add new region...</option>
    ${options}
  `;
  regionSelect.value = currentRegion;

  regionSelect.onchange = () => {
    const nextValue = regionSelect.value;

    if (nextValue === "__new__") {
      const label = window.prompt("Enter a name for the new region:", "");
      if (!label || !label.trim()) {
        regionSelect.value = currentRegion;
        return;
      }

      const baseSlug = slugify(label);
      let slug = baseSlug;
      let suffix = 2;
      while (hasRegion(slug)) {
        slug = `${baseSlug}-${suffix}`;
        suffix += 1;
      }

      const newColor = nextCustomColor();
      appState.customRegions[slug] = {
        label: label.trim(),
        color: newColor,
      };
      appState.countyAssignments[normalizeCountyKey(countyName)] = slug;
      persistState();
      renderLegend();
      renderMap();
      openCountyPicker(countyName);
      return;
    }

    appState.countyAssignments[normalizeCountyKey(countyName)] = nextValue;
    persistState();
    renderLegend();
    renderMap();
    countyModal.classList.add("hidden");
  };

  countyModal.classList.remove("hidden");
}

function closeCountyPicker() {
  countyModal.classList.add("hidden");
}

function renderMap() {
  fetch("georgia_regions.svg")
    .then((response) => {
      if (!response.ok) {
        throw new Error(`Unable to load map: ${response.status}`);
      }
      return response.text();
    })
    .then((svgMarkup) => {
      const parser = new DOMParser();
      const parsed = parser.parseFromString(svgMarkup, "image/svg+xml");
      const svgRoot = parsed.documentElement;
      svgRoot.setAttribute("preserveAspectRatio", "xMidYMid meet");
      svgRoot.setAttribute("aria-label", "Georgia county map");

      mapContainer.innerHTML = "";
      mapContainer.appendChild(svgRoot);

      applyMapColors(svgRoot);

      svgRoot.querySelectorAll("path").forEach((path) => {
        path.addEventListener("click", (event) => {
          event.stopPropagation();
          const titleNode = path.querySelector("title");
          const countyName = titleNode ? titleNode.textContent.split("-")[0].trim() : "";
          if (countyName) {
            openCountyPicker(countyName);
          }
        });
      });
    })
    .catch((error) => {
      mapContainer.innerHTML = `<p style="padding: 24px; color: #fca5a5;">The map could not load: ${error.message}</p>`;
    });
}

function exportAssignments() {
  const payload = {
    regionOrder: getRegionOrder(),
    regions: Object.fromEntries(
      getRegionOrder().map((slug) => {
        const meta = getRegionMeta(slug);
        return [slug, { label: meta.label, color: meta.color, counties: DEFAULT_REGIONS[slug]?.counties || [] }];
      })
    ),
    countyAssignments: appState.countyAssignments,
  };

  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "georgia-region-assignments.json";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function resetDefaults() {
  appState.countyAssignments = getDefaultAssignments();
  appState.customRegions = {};
  persistState();
  renderLegend();
  renderMap();
  closeCountyPicker();
}

function bindEvents() {
  document.getElementById("closeModal").addEventListener("click", closeCountyPicker);
  document.getElementById("exportButton").addEventListener("click", exportAssignments);
  document.getElementById("resetButton").addEventListener("click", resetDefaults);
  document.addEventListener("click", (event) => {
    const clickInsideModal = event.target.closest(".modal-card");
    if (!clickInsideModal && !event.target.closest("path")) {
      closeCountyPicker();
    }
  });
}

loadState();
bindEvents();
renderLegend();
renderMap();
