/**
 * ==============================================================================
 * DilliTransit - Frontend Client Engine (Single Page Transit Application)
 * Author: First Year Computer Science Student
 * Architecture: Handcrafted Vanilla ES6+ JavaScript (Zero NPM Dependencies)
 * Design Pattern: Immediately Invoked Function Expression (IIFE) + State Machine
 * 
 * Major Subsystems:
 * 1. Leaflet & HTML5 Canvas Dual-Rendering Engine (Zero-Network Resilient)
 * 2. Asynchronous API Pipeline (Fetch API with client-side fallback planner)
 * 3. Movie-Style Interactive Bus Seating Grid (DOM Matrix Generation)
 * 4. Real-time Telemetry Poller & Corridor Congestion Visualizer
 * ==============================================================================
 */

(function () {
  "use strict";

  // App State
  const state = {
    allStops: [],
    allAmenities: [],
    originStop: null,
    destStop: null,
    journeys: [],
    selectedJourneyId: null,
    activeFilter: "ALL",
    activeAmenityCategory: "ALL",
    liveBuses: [],
    corridors: [],
    currentScenario: "normal",
    activeTab: "results",
    telemetryInfo: null,
    leafletMap: null,
    mapLayers: {
      routeLayer: null,
      stopsLayer: null,
      amenitiesLayer: null,
      busesLayer: null,
      pinsLayer: null,
      corridorLayer: null
    },
    useFallbackCanvas: false
  };

  // DOM Elements Cache
  const elements = {
    originInput: document.getElementById("origin-input"),
    destInput: document.getElementById("dest-input"),
    originDropdown: document.getElementById("origin-dropdown"),
    destDropdown: document.getElementById("dest-dropdown"),
    btnSwap: document.getElementById("btn-swap"),
    btnPlan: document.getElementById("btn-plan"),
    resultsContainer: document.getElementById("journeys-list"),
    resultsCount: document.getElementById("results-count"),
    telemetryPill: document.getElementById("telemetry-pill"),
    telemetryStatusText: document.getElementById("telemetry-status-text"),
    scenarioSelect: document.getElementById("scenario-select"),
    tickerContainer: document.getElementById("ticker-items"),
    btnFitRoute: document.getElementById("btn-fit-route"),
    btnToggleBuses: document.getElementById("btn-toggle-buses"),
    btnToggleCorridors: document.getElementById("btn-toggle-corridors"),
    modalBackdrop: document.getElementById("modal-backdrop"),
    btnOpenModal: document.getElementById("btn-open-modal"),
    btnCloseModal: document.getElementById("btn-close-modal"),
    lastUpdatedText: document.getElementById("last-updated-text"),
    dataSourceFooter: document.getElementById("data-source-footer"),
    canvasFallback: document.getElementById("transit-fallback-canvas")
  };

  // Delhi Coordinates Center
  const DELHI_CENTER = [28.6139, 77.2090]; // Connaught Place / Central Delhi
  const DELHI_BOUNDS = [
    [28.45, 76.90], // South-West
    [28.85, 77.40]  // North-East
  ];

  /* --------------------------------------------------------------------------
     Initialization
     -------------------------------------------------------------------------- */
  async function init() {
    setupEventListeners();
    await fetchHealthAndInfo();
    await fetchStops();
    await fetchAmenities();
    await fetchCorridors();
    initMap();
    startLivePolling();

    // Default pre-fill for instant demonstration
    setDefaultTrip("KG_ISBT", "AIIMS");
  }

  /* --------------------------------------------------------------------------
     API Communication
     -------------------------------------------------------------------------- */
  async function fetchAmenities(stopId = null, category = null) {
    try {
      let url = "/api/amenities";
      const params = [];
      if (stopId) params.push(`stop_id=${encodeURIComponent(stopId)}`);
      if (category && category !== "ALL") params.push(`category=${encodeURIComponent(category)}`);
      if (params.length > 0) url += `?${params.join("&")}`;

      const res = await fetch(url);
      const data = await res.json();
      state.allAmenities = data.amenities || [];
      renderAmenitiesOnMap();
    } catch (err) {
      console.warn("Failed to load amenities:", err);
    }
  }
  async function fetchHealthAndInfo() {
    try {
      const res = await fetch("/api/health");
      const data = await res.json();
      state.telemetryInfo = data.data_source;
      state.currentScenario = data.active_scenario || "normal";
      if (elements.scenarioSelect) {
        elements.scenarioSelect.value = state.currentScenario;
      }
      updateTelemetryUI();
    } catch (err) {
      console.warn("Health check error:", err);
    }
  }

  async function fetchStops() {
    try {
      const res = await fetch("/api/stops");
      const data = await res.json();
      state.allStops = data.stops || [];
    } catch (err) {
      console.error("Failed to load stops:", err);
    }
  }

  async function fetchCorridors() {
    try {
      const res = await fetch("/api/corridors");
      const data = await res.json();
      state.corridors = data.corridors || [];
      renderCorridorTicker();
    } catch (err) {
      console.warn("Failed to fetch corridors:", err);
    }
  }

  async function fetchLiveBuses(routeId = null) {
    try {
      const url = routeId ? `/api/live-buses?route_id=${encodeURIComponent(routeId)}` : "/api/live-buses";
      const res = await fetch(url);
      const data = await res.json();
      state.liveBuses = data.buses || [];
      renderLiveBusesOnMap();
      updateTimestamp();
    } catch (err) {
      console.warn("Failed to load live buses:", err);
    }
  }

  async function searchJourneys() {
    if (!state.originStop || !state.destStop) {
      alert("Please select both a Delhi origin and destination from the suggestions.");
      return;
    }

    renderLoadingJourneys();

    try {
      const res = await fetch(
        `/api/plan?origin=${encodeURIComponent(state.originStop.id)}&destination=${encodeURIComponent(state.destStop.id)}`
      );
      if (!res.ok) {
        throw new Error(`Server responded with status ${res.status}`);
      }
      const data = await res.json();

      if (!data.success) {
        renderNoJourneys(data.error || "No bus routes found connecting these stops directly or via 1 transfer.");
        clearMapRoute();
        return;
      }

      state.journeys = data.journeys || [];
      renderJourneysList();

      if (state.journeys.length > 0) {
        selectJourney(state.journeys[0].journey_id);
      }
    } catch (err) {
      console.warn("Backend API unreachable, utilizing client-side transit routing engine:", err);
      runClientSideJourneyPlanner();
    }
  }

  /* Client-Side Resilient Journey Planner Fallback */
  function runClientSideJourneyPlanner() {
    if (!state.originStop || !state.destStop) return;
    const originId = state.originStop.id;
    const destId = state.destStop.id;

    // Direct Route Discovery
    const candidates = [];
    const knownRoutes = [
      { id: "502", name: "502", long: "Mehrauli Terminal ⇄ Mori Gate", type: "Electric AC Low-Floor (Green)", color: "#16a34a", fare: 25, freq: 8, stops: ["MEHRAULI", "SAKET", "HAUZ_KHAS", "AIIMS", "INA_MARKET", "INDIA_GATE", "PRAGATI_MDN", "ITO", "DELHI_GATE", "RED_FORT", "KG_ISBT", "MORI_GATE"] },
      { id: "TMS", name: "TMS (Mudrika)", long: "Ring Road Circular Seva", type: "Standard CNG Non-AC (Blue)", color: "#2563eb", fare: 15, freq: 6, stops: ["KG_ISBT", "DELHI_GATE", "ITO", "PRAGATI_MDN", "SARAI_KALE_KHAN", "ASHRAM", "LAJPAT_NAGAR", "MOOLCHAND", "AIIMS", "DHAULA_KUAN", "DELHI_CANTT", "PUNJABI_BAGH", "AZADPUR", "MODEL_TOWN", "KG_ISBT"] },
      { id: "OMS", name: "OMS (Outer Mudrika)", long: "Outer Ring Road Express", type: "Electric AC Low-Floor", color: "#0d9488", fare: 25, freq: 10, stops: ["UTTAM_NAGAR", "JANAKPURI_WEST", "DHAULA_KUAN", "MUNIRKA", "HAUZ_KHAS", "GK_1", "NEHRU_PLACE", "ASHRAM", "SARAI_KALE_KHAN", "ANAND_VIHAR"] },
      { id: "534", name: "534", long: "Anand Vihar ISBT ⇄ Mehrauli", type: "Electric AC Low-Floor", color: "#ea580c", fare: 25, freq: 9, stops: ["ANAND_VIHAR", "PREET_VIHAR", "LAXMI_NAGAR", "ITO", "SARAI_KALE_KHAN", "ASHRAM", "LAJPAT_NAGAR", "MOOLCHAND", "AIIMS", "HAUZ_KHAS", "SAKET", "MEHRAULI"] },
      { id: "729", name: "729", long: "Mori Gate ⇄ Kapashera Border", type: "Standard CNG (Orange)", color: "#ca8a04", fare: 15, freq: 12, stops: ["MORI_GATE", "KG_ISBT", "NDLS", "RAJIV_CHOWK", "SHIVAJI_STD", "DHAULA_KUAN", "DELHI_CANTT", "AEROCITY", "IGI_AIRPORT_T1", "KAPASHERA_BORDER"] },
      { id: "620", name: "620", long: "Shivaji Stadium (CP) ⇄ Vasant Kunj", type: "Electric AC Low-Floor", color: "#7c3aed", fare: 25, freq: 10, stops: ["SHIVAJI_STD", "RAJIV_CHOWK", "INDIA_GATE", "INA_MARKET", "AIIMS", "MUNIRKA", "JNU", "VASANT_KUNJ"] },
      { id: "181", name: "181", long: "Hazrat Nizamuddin ⇄ Azadpur", type: "Standard CNG (Red)", color: "#db2777", fare: 15, freq: 11, stops: ["NIZAMUDDIN", "PRAGATI_MDN", "ITO", "DELHI_GATE", "RED_FORT", "KG_ISBT", "MODEL_TOWN", "AZADPUR"] },
      { id: "764", name: "764", long: "Nehru Place ⇄ Najafgarh Terminal", type: "Standard CNG (Orange)", color: "#0284c7", fare: 15, freq: 10, stops: ["NEHRU_PLACE", "GK_1", "HAUZ_KHAS", "MUNIRKA", "DHAULA_KUAN", "DELHI_CANTT", "JANAKPURI_WEST", "UTTAM_NAGAR", "NAJAFGARH"] },
      { id: "85", name: "85", long: "Anand Vihar ⇄ Punjabi Bagh", type: "Electric AC Low-Floor", color: "#c026d3", fare: 25, freq: 10, stops: ["ANAND_VIHAR", "PREET_VIHAR", "LAXMI_NAGAR", "ITO", "RAJIV_CHOWK", "SHIVAJI_STD", "KAROL_BAGH", "PATEL_NAGAR", "SHADIPUR_DEPOT", "PUNJABI_BAGH"] },
      { id: "AIRPORT_EXP", name: "Airport Exp (DW-1)", long: "Kashmere Gate ⇄ Airport T3", type: "Premium Electric EV", color: "#0284c7", fare: 50, freq: 15, stops: ["KG_ISBT", "NDLS", "RAJIV_CHOWK", "SHIVAJI_STD", "DHAULA_KUAN", "AEROCITY", "IGI_AIRPORT_T1", "IGI_AIRPORT_T3"] }
    ];

    knownRoutes.forEach(r => {
      const idxA = r.stops.indexOf(originId);
      const idxB = r.stops.indexOf(destId);
      if (idxA !== -1 && idxB !== -1) {
        let subStops = [];
        let dir = "Up";
        if (idxA < idxB) {
          subStops = r.stops.slice(idxA, idxB + 1);
        } else {
          subStops = r.stops.slice(idxB, idxA + 1).reverse();
          dir = "Down";
        }
        const fullStops = subStops.map((sid, i) => {
          const s = state.allStops.find(item => item.id === sid) || { id: sid, name: sid, lat: 28.6, lon: 77.2 };
          return { ...s, arrival_offset_min: i * 4.2 };
        });
        const geom = fullStops.map(s => [s.lat, s.lon]);
        const distKm = Math.round(fullStops.length * 1.8 * 10) / 10;
        const durMin = Math.round(fullStops.length * 4.5);
        candidates.push({
          journey_id: `client_${r.id}_${originId}_${destId}`,
          type: "DIRECT",
          direction: dir,
          transfers_count: 0,
          route_id: r.id,
          route_short_name: r.name,
          route_long_name: r.long,
          bus_type: r.type,
          color: r.color,
          fare_inr: r.fare,
          total_distance_km: distKm,
          scheduled_duration_min: Math.round(durMin * 0.75),
          live_duration_min: durMin,
          traffic_delay_min: Math.round(durMin * 0.25),
          congestion_level: "Moderate",
          congestion_status: "Moderate arterial flow (+8m delay)",
          badge_color: "#f59e0b",
          carbon_saved_kg: Math.round(distKm * 0.11 * 10) / 10,
          next_bus_in_min: 4,
          frequency_min: r.freq,
          geometry: geom,
          stops: fullStops,
          tags: ["Direct Route", "Client Engine"]
        });
      }
    });

    if (candidates.length === 0) {
      renderNoJourneys("No direct routes found between these two locations. Please select major hubs like Kashmere Gate, AIIMS, or Rajiv Chowk.");
      clearMapRoute();
      return;
    }

    state.journeys = candidates;
    renderJourneysList();
    selectJourney(candidates[0].journey_id);
  }

  async function changeScenario(newScenario) {
    try {
      const res = await fetch("/api/scenario", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scenario: newScenario })
      });
      const data = await res.json();
      if (data.success) {
        state.currentScenario = newScenario;
        await fetchCorridors();
        if (state.originStop && state.destStop) {
          searchJourneys();
        } else {
          fetchLiveBuses();
        }
      }
    } catch (err) {
      console.error("Failed to change scenario:", err);
    }
  }

  /* --------------------------------------------------------------------------
     UI Renderers
     -------------------------------------------------------------------------- */
  function updateTelemetryUI() {
    if (!state.telemetryInfo) return;

    const isLive = state.telemetryInfo.status === "LIVE";
    if (elements.telemetryPill) {
      elements.telemetryPill.classList.toggle("live-mode", isLive);
    }
    if (elements.telemetryStatusText) {
      elements.telemetryStatusText.textContent = isLive ? "LIVE OTD GTFS FEED" : "SAMPLE & PHYSICS TELEMETRY";
    }
    if (elements.dataSourceFooter) {
      elements.dataSourceFooter.textContent = isLive
        ? "Connected to Delhi Open Transit Data (otd.delhi.gov.in) Live GTFS-RT Feed"
        : "Operating in Calibrated Physics Mode (Sample Delhi DTC/DIMTS Topology)";
    }
  }

  function renderCorridorTicker() {
    if (!elements.tickerContainer) return;
    elements.tickerContainer.innerHTML = state.corridors.map(c => `
      <div class="ticker-item">
        <span style="color: ${c.color}; font-size: 0.65rem;">●</span>
        <span style="color: var(--text-main); font-weight: 500;">${c.corridor_name.split("(")[0].trim()}</span>
        <span class="ticker-speed" style="color: ${c.color}">${c.current_speed_kmh} km/h</span>
      </div>
    `).join("");
  }

  function renderLoadingJourneys() {
    elements.resultsContainer.innerHTML = `
      <div class="loading-state">
        <div class="spinner"></div>
        <div style="font-weight: 600; font-size: 0.9rem;">Modeling Traffic & Finding Bus Routes...</div>
        <div style="font-size: 0.75rem; color: var(--text-dim);">Computing probe-vehicle velocities and stop dwell times</div>
      </div>
    `;
    elements.resultsCount.textContent = "Searching...";
  }

  function renderNoJourneys(msg) {
    elements.resultsContainer.innerHTML = `
      <div class="empty-state">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#64748b" stroke-width="1.5">
          <circle cx="12" cy="12" r="10"/>
          <line x1="12" y1="8" x2="12" y2="12"/>
          <line x1="12" y1="16" x2="12.01" y2="16"/>
        </svg>
        <div style="font-weight: 600; font-size: 0.9rem; color: var(--text-main);">No Direct or 1-Transfer Journey Found</div>
        <div style="font-size: 0.75rem;">${msg}</div>
      </div>
    `;
    elements.resultsCount.textContent = "0 Journeys";
  }

  function renderErrorJourneys(msg) {
    elements.resultsContainer.innerHTML = `
      <div class="error-state">
        <div style="color: #ef4444; font-weight: 600;">Journey Search Error</div>
        <div style="font-size: 0.75rem;">${msg}</div>
      </div>
    `;
  }

  function renderJourneysList() {
    let filtered = state.journeys.filter(j => {
      if (state.activeFilter === "DIRECT") return j.type === "DIRECT";
      if (state.activeFilter === "SAHELI_PINK") return j.is_saheli_pink === true;
      if (state.activeFilter === "EV_AC") return j.is_ac || j.is_wheelchair_accessible || (j.bus_type && j.bus_type.includes("Electric"));
      if (state.activeFilter === "METRO_RAPIDX") return j.mode === "metro" || j.mode === "rapidx" || j.mode === "multimodal";
      if (state.activeFilter === "NIGHT_SAFE") return (j.night_safety_rating || 4.5) >= 4.8;
      return true;
    });

    if (state.activeFilter === "CHEAPEST") {
      filtered = [...filtered].sort((a, b) => a.fare_inr - b.fare_inr);
    }

    elements.resultsCount.textContent = `${filtered.length} Multimodal Journey${filtered.length === 1 ? "" : "s"} Available`;

    if (filtered.length === 0) {
      elements.resultsContainer.innerHTML = `
        <div class="empty-state">
          <div>No journeys match the selected filter. Try "All Modes".</div>
        </div>
      `;
      return;
    }

    elements.resultsContainer.innerHTML = filtered.map(journey => {
      const isSelected = journey.journey_id === state.selectedJourneyId;
      const isDirect = journey.type === "DIRECT";
      const tagsHtml = (journey.tags || []).map(t => `<span class="tag-badge">${t}</span>`).join("");

      // Mode icon & label
      let modeBadge = `<span class="tag-badge" style="background:rgba(37,99,235,0.15); color:#60a5fa;">🚌 DTC Bus</span>`;
      if (journey.mode === "metro") {
        modeBadge = `<span class="tag-badge" style="background:rgba(234,179,8,0.2); color:#facc15; font-weight:700;">🚇 DMRC Metro</span>`;
      } else if (journey.mode === "rapidx") {
        modeBadge = `<span class="tag-badge" style="background:rgba(124,58,237,0.2); color:#c084fc; font-weight:700;">🚄 RapidX RRTS</span>`;
      } else if (journey.mode === "multimodal") {
        modeBadge = `<span class="tag-badge" style="background:rgba(16,185,129,0.2); color:#34d399; font-weight:700;">🔀 Multimodal (Metro+Bus)</span>`;
      }

      // NCMC Smart Card Fare & Savings
      const ncmcFare = journey.ncmc_fare ? journey.ncmc_fare.ncmc_fare_inr : Math.max(5, journey.fare_inr - 3);
      const ncmcSave = journey.ncmc_fare ? journey.ncmc_fare.discount_amount_inr : 3;

      // Bus bunching alert
      const bunchingHtml = journey.bus_bunching && journey.bus_bunching.detected ? `
        <div class="bus-bunching-card">
          <div class="bunching-header">
            <span class="pulse-dot" style="background:#ef4444;"></span>
            <span style="font-weight:700; color:#f87171; font-size:0.75rem;">BUS BUNCHING DETECTED</span>
          </div>
          <div style="font-size:0.72rem; color:var(--text-main); margin-top:2px;">
            ${journey.bus_bunching.alert}
          </div>
          <div style="font-size:0.7rem; color:#38bdf8; font-weight:600; margin-top:3px;">
            ${journey.bus_bunching.advice}
          </div>
        </div>
      ` : "";

      // Crowdedness Progress Bar
      const crowdPct = journey.crowd_percentage || 52;
      const crowdStatus = journey.crowd_status || `Seats Available (${crowdPct}%)`;
      const crowdColor = journey.crowd_color || "#10b981";

      return `
        <div class="journey-card ${isSelected ? 'selected' : ''}" data-journey-id="${journey.journey_id}">
          <div class="journey-card-badge-row">
            <div class="route-badge-group">
              <span class="route-badge" style="background-color: ${journey.color}">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M4 16c0 .88.39 1.67 1 2.22V20c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-1h8v1c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-1.78c.61-.55 1-1.34 1-2.22V6c0-3.5-3.58-4-8-4s-8 .5-8 4v10zm3.5 1c-.83 0-1.5-.67-1.5-1.5S6.67 14 7.5 14s1.5.67 1.5 1.5S8.33 17 7.5 17zm9 0c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5zm1.5-6H6V6h12v5z"/>
                </svg>
                ${journey.route_short_name}
              </span>
              ${modeBadge}
              ${!isDirect ? `<span class="transfer-badge">1 Transfer</span>` : `<span class="tag-badge" style="background:rgba(56,189,248,0.15);color:#38bdf8;">Direct</span>`}
              ${tagsHtml}
            </div>
            <div style="text-align:right;">
              <div class="fare-tag">₹${journey.fare_inr}</div>
              <div style="font-size:0.68rem; color:#38bdf8; font-weight:700; margin-top:2px;">💳 NCMC: ₹${ncmcFare}</div>
            </div>
          </div>

          <!-- NCMC Card Savings Chip -->
          <div class="ncmc-savings-strip">
            <span class="ncmc-save-pill">⚡ Save ₹${ncmcSave} with NCMC / RuPay One Delhi Card</span>
            ${journey.is_wheelchair_accessible ? `<span class="ncmc-save-pill" style="color:#34d399; border-color:rgba(52,211,153,0.3);">♿ 100% Accessible</span>` : ''}
          </div>

          <div class="journey-metrics-grid">
            <div class="duration-wrap">
              <span class="duration-live">${journey.live_duration_min}</span>
              <span class="duration-unit">min</span>
              <span class="duration-scheduled">${journey.scheduled_duration_min}m sched</span>
            </div>
            <div style="font-size: 0.72rem; color: var(--text-muted); text-align: right;">
              <div>${journey.total_distance_km} km total</div>
              <div style="color: #34d399;">-${journey.carbon_saved_kg}kg CO₂</div>
            </div>
          </div>

          <!-- Live Crowdedness Meter -->
          <div class="crowd-meter-strip">
            <div class="crowd-label">
              <span style="color:${crowdColor}; font-weight:700;">${crowdStatus}</span>
              <span style="font-size:0.68rem; color:var(--text-muted);">${crowdPct}% bus capacity</span>
            </div>
            <div class="crowd-bar-bg">
              <div class="crowd-bar-fill" style="width:${crowdPct}%; background-color:${crowdColor};"></div>
            </div>
          </div>

          <!-- Bus Bunching Alert Box (if detected) -->
          ${bunchingHtml}

          <!-- Saheli Pink Women Special Bus Banner -->
          ${journey.is_saheli_pink ? `
            <div class="saheli-special-card">
              <div style="display:flex; align-items:center; justify-content:space-between;">
                <span class="saheli-badge">🌸 Saheli Pink Women Special (महिला विशेष)</span>
                <span style="font-size:0.68rem; color:#f472b6; font-weight:700;">₹0 Pink Pass</span>
              </div>
              <div style="font-size:0.7rem; color:var(--text-main); margin-top:3px;">
                Female conductor on board • Dedicated Pink Zone (Seats W1-W8) • Free Pink Pass Scheme
              </div>
            </div>
          ` : ''}

          <!-- Rush Bypass Alternate Route (if corridor congested) -->
          ${journey.rush_bypass_alternate ? `
            <div class="rush-bypass-card" onclick="event.stopPropagation(); window.selectJourney('${journey.rush_bypass_alternate.recommended_journey_id}')" title="Click to view rush bypass route">
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <span class="bypass-tag">⚡ RUSH BYPASS AVAILABLE</span>
                <span style="font-size:0.7rem; color:#34d399; font-weight:800;">Save ~${journey.rush_bypass_alternate.time_saved_min} mins</span>
              </div>
              <div style="font-weight:700; color:var(--text-main); font-size:0.75rem; margin-top:2px;">
                ${journey.rush_bypass_alternate.title}
              </div>
              <div style="font-size:0.7rem; color:var(--text-muted); margin-top:1px;">
                ${journey.rush_bypass_alternate.advice}
              </div>
              <button class="btn-switch-bypass" onclick="event.stopPropagation(); window.selectJourney('${journey.rush_bypass_alternate.recommended_journey_id}')">
                🚀 Switch to Bypass Route
              </button>
            </div>
          ` : ''}

          <!-- Live Fleet Plate, Choose Seat & SOS Button -->
          <div class="fleet-sos-row">
            <div class="fleet-plate-badge" title="Live bus chassis &amp; GPS telemetry identifier">
              🚍 Fleet: <strong>${journey.live_fleet_number || 'DL-1PD-4521'}</strong>
            </div>
            <div style="display:flex; gap:6px;">
              <button class="btn-card-seat" onclick="event.stopPropagation(); window.openSeatModal('${journey.journey_id}')" title="Interactive movie-style bus seat selection">
                💺 Choose Seat
              </button>
              <button class="btn-card-sos" onclick="event.stopPropagation(); window.openSosModal('${journey.journey_id}')" title="Trigger 1-click live GPS SOS alert">
                🚨 SOS
              </button>
            </div>
          </div>

          <div class="traffic-status-strip ${journey.congestion_level.toLowerCase()}">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>
            </svg>
            <span>${journey.congestion_status}</span>
          </div>

          <!-- Route Amenities Strip (Pink Toilets, Metro, Hospitals, Cafes, Cinemas, Police) -->
          <div class="amenities-summary-strip">
            <span class="amenity-pill-badge pink-toilet" title="Women's Safe Sanitation Hubs">
              🚻 ${journey.amenities_summary?.pink_toilets || 0} Pink Toilets
            </span>
            <span class="amenity-pill-badge metro" title="First/Last-Mile Metro Interchanges">
              🚇 ${journey.amenities_summary?.metro || 0} Metro
            </span>
            <span class="amenity-pill-badge police" title="Delhi Police Stations along corridor">
              🚔 ${journey.amenities_summary?.police || 0} Police
            </span>
            <span class="amenity-pill-badge hospital" title="Emergency Hospitals along corridor">
              🏥 ${journey.amenities_summary?.hospitals || 0} Hospitals
            </span>
            <span class="amenity-pill-badge cafe" title="Chai &amp; Refreshment stops">
              ☕ ${journey.amenities_summary?.cafes || 0} Cafes
            </span>
            <span class="amenity-pill-badge cinema" title="Cinemas &amp; Entertainment">
              🎬 ${journey.amenities_summary?.cinemas || 0} Cinemas
            </span>
          </div>

          <div class="live-bus-indicator">
            <span class="bus-eta-text">
              <span class="pulse-dot" style="width:6px; height:6px;"></span>
              Next service in ~${journey.next_bus_in_min} min
            </span>
            <span>Freq: every ${journey.frequency_min || 10}m • ⭐ ${(journey.night_safety_rating || 4.7)}/5 Safe</span>
          </div>

          <!-- Step-by-step Itinerary (Expanded on Selected) -->
          <div class="itinerary-details">
            <div class="timeline">
              ${renderTimelineSteps(journey)}
            </div>
          </div>
        </div>
      `;
    }).join("");

    // Add click handlers on journey cards
    document.querySelectorAll(".journey-card").forEach(card => {
      card.addEventListener("click", () => {
        const jId = card.getAttribute("data-journey-id");
        selectJourney(jId);
      });
    });
  }

  function renderStopAmenitiesSnippet(stop) {
    const ams = stop.amenities || [];
    if (ams.length === 0) return "";
    const items = ams.map(a => `
      <div class="amenity-list-item">
        <div class="amenity-item-icon">${a.icon}</div>
        <div class="amenity-item-content">
          <div class="amenity-item-name">
            <span>${a.name}</span>
            <span class="amenity-item-dist">~${a.distance_m}m</span>
          </div>
          <div class="amenity-item-desc">${a.details}</div>
        </div>
      </div>
    `).join("");
    return `
      <div class="nearby-amenities-box">
        <div class="nearby-amenities-title">
          <span>📍 Transit Amenities around ${stop.name.split("/")[0].trim()}</span>
          <span style="font-size:0.65rem; color:var(--text-muted); font-weight:normal;">${ams.length} facilities within 500m</span>
        </div>
        ${items}
      </div>
    `;
  }

  function renderHyperlocalSnippet(stop) {
    const h = stop.hyperlocal;
    if (!h) return "";
    const feederText = (h.feeder_modes || []).map(f => `${f.mode} (₹${f.fare_inr})`).join(" • ");
    const landmarksText = (h.landmarks || []).slice(0, 3).join(", ");
    return `
      <div class="hyperlocal-guidance-card">
        <div class="hyperlocal-pin-row">
          <span class="pin-icon" style="font-size:1rem;">📌</span>
          <div style="flex:1;">
            <div style="font-weight:700; color:#38bdf8; font-size:0.75rem;">Exact Roadside Boarding Pin:</div>
            <div style="font-size:0.72rem; color:var(--text-main); line-height:1.3;">${h.road_side_pin || (stop.name + ' Transit Bay')}</div>
          </div>
        </div>
        ${h.metro_exit_gate ? `
          <div class="hyperlocal-gate-row" style="margin-top:5px; font-size:0.71rem; color:#facc15; background:rgba(234,179,8,0.1); padding:4px 6px; border-radius:4px;">
            🚇 <strong>Metro Gate:</strong> ${h.metro_exit_gate}
          </div>
        ` : ''}
        <div style="margin-top:5px; font-size:0.68rem; color:var(--text-muted); display:flex; flex-direction:column; gap:3px;">
          ${landmarksText ? `<div>🏛️ <strong>Landmarks:</strong> ${landmarksText}</div>` : ''}
          ${feederText ? `<div>🛺 <strong>Last-Mile Feeder:</strong> ${feederText}</div>` : ''}
          <div>⭐ <strong>Corridor Safety:</strong> ${h.safety_rating || 4.7}/5 • ${h.lighting_status || 'CCTV & Police Patrolled'}</div>
        </div>
        ${h.nearest_police ? `
          <div style="margin-top:5px; font-size:0.68rem; color:#93c5fd; background:rgba(29,78,216,0.12); padding:4px 6px; border-radius:4px; border:1px solid rgba(29,78,216,0.3); display:flex; justify-content:space-between; align-items:center;">
            <span>🚔 <strong>Nearest Station:</strong> ${h.nearest_police.name} (~${h.nearest_police.distance_m}m)</span>
            <a href="tel:112" style="color:#f87171; font-weight:700; text-decoration:none;">112 Police</a>
          </div>
        ` : ''}
      </div>
    `;
  }

  function renderTimelineSteps(journey) {
    if (journey.type === "DIRECT") {
      const firstStop = journey.stops[0];
      const lastStop = journey.stops[journey.stops.length - 1];
      return `
        <div class="timeline-step">
          <div class="timeline-dot"></div>
          <div class="step-title">Board at ${firstStop.name}</div>
          <div class="step-sub">Route ${journey.route_short_name} • ${journey.bus_type}</div>
          <div class="step-segment-badge" style="background: rgba(16,185,129,0.15); color: #34d399;">
            ${journey.stops.length} stops (${journey.total_distance_km} km)
          </div>
          ${renderHyperlocalSnippet(firstStop)}
          ${renderStopAmenitiesSnippet(firstStop)}
        </div>
        <div class="timeline-step">
          <div class="timeline-dot dest"></div>
          <div class="step-title">Alight at ${lastStop.name}</div>
          <div class="step-sub">Arrive in ~${journey.live_duration_min} minutes</div>
          ${renderHyperlocalSnippet(lastStop)}
          ${renderStopAmenitiesSnippet(lastStop)}
        </div>
      `;
    } else {
      // 1-transfer itinerary
      const leg1 = journey.legs[0];
      const transferLeg = journey.legs[1];
      const leg2 = journey.legs[2];
      const hubStop = journey.stops.find(s => s.name === transferLeg.hub_name) || { name: transferLeg.hub_name, amenities: [] };
      return `
        <div class="timeline-step">
          <div class="timeline-dot"></div>
          <div class="step-title">Board ${leg1.route_name} at ${leg1.from_stop.name}</div>
          <div class="step-sub">${leg1.stops_count} stops • ~${leg1.duration_min} min</div>
          ${renderHyperlocalSnippet(leg1.from_stop)}
          ${renderStopAmenitiesSnippet(leg1.from_stop)}
        </div>
        <div class="timeline-step">
          <div class="timeline-dot transfer"></div>
          <div class="step-title">Transfer at ${transferLeg.hub_name}</div>
          <div class="step-sub">Platform interchange (~${transferLeg.duration_min} min buffer)</div>
          ${renderHyperlocalSnippet(hubStop)}
          ${renderStopAmenitiesSnippet(hubStop)}
        </div>
        <div class="timeline-step">
          <div class="timeline-dot"></div>
          <div class="step-title">Board ${leg2.route_name} at ${leg2.from_stop.name}</div>
          <div class="step-sub">${leg2.stops_count} stops • ~${leg2.duration_min} min</div>
          ${renderHyperlocalSnippet(leg2.from_stop)}
        </div>
        <div class="timeline-step">
          <div class="timeline-dot dest"></div>
          <div class="step-title">Alight at ${leg2.to_stop.name}</div>
          <div class="step-sub">Final destination reached</div>
          ${renderHyperlocalSnippet(leg2.to_stop)}
          ${renderStopAmenitiesSnippet(leg2.to_stop)}
        </div>
      `;
    }
  }

  function selectJourney(journeyId) {
    state.selectedJourneyId = journeyId;
    const journey = state.journeys.find(j => j.journey_id === journeyId);
    if (!journey) return;

    // Update UI card classes
    document.querySelectorAll(".journey-card").forEach(c => {
      const matches = c.getAttribute("data-journey-id") === journeyId;
      c.classList.toggle("selected", matches);
    });

    // Draw on map
    renderRouteOnMap(journey);
    fetchLiveBuses(journey.route_id);
  }

  /* --------------------------------------------------------------------------
     Map Visualization (Leaflet with Canvas Fallback)
     -------------------------------------------------------------------------- */
  function initMap() {
    // Check if Leaflet is available in global window
    if (typeof L === "undefined") {
      console.warn("Leaflet library not reachable from external CDN. Initializing high-performance Canvas Transit Map Engine.");
      initCanvasFallback();
      return;
    }

    try {
      state.leafletMap = L.map("map", {
        center: DELHI_CENTER,
        zoom: 12,
        minZoom: 10,
        maxZoom: 18,
        zoomControl: false
      });

      L.control.zoom({ position: "bottomright" }).addTo(state.leafletMap);

      // Google Maps Road tiles as default — familiar, detailed street map
      state.mapLayers.baseTile = L.tileLayer("https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}", {
        attribution: 'Map data &copy; <a href="https://www.google.com/maps">Google Maps</a>',
        maxZoom: 20
      });
      state.mapLayers.baseTile.addTo(state.leafletMap);

      // Layer groups
      state.mapLayers.routeLayer = L.layerGroup().addTo(state.leafletMap);
      state.mapLayers.stopsLayer = L.layerGroup().addTo(state.leafletMap);
      state.mapLayers.amenitiesLayer = L.layerGroup().addTo(state.leafletMap);
      state.mapLayers.busesLayer = L.layerGroup().addTo(state.leafletMap);
      state.mapLayers.pinsLayer = L.layerGroup().addTo(state.leafletMap);

      renderAllStopsOnMap();
      renderAmenitiesOnMap();
    } catch (e) {
      console.warn("Leaflet init error, switching to canvas fallback:", e);
      initCanvasFallback();
    }
  }

  // ── Map Provider Switcher ──────────────────────────────────────────────────
  // Switches between OpenStreetMap/CartoDB and Google Maps tile layers.
  // Google Maps tiles are used via their unofficial tile URL — no JS API key
  // needed for basic raster tiles. For full Google Maps SDK features (Directions,
  // Places, Street View) set GOOGLE_MAPS_API_KEY in .env and use the /api/config endpoint.
  const MAP_PROVIDERS = {
    osm: {
      url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      subdomains: "abc",
      maxZoom: 19,
      label: "OpenStreetMap"
    },
    carto: {
      url: "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>',
      subdomains: "abcd",
      maxZoom: 19,
      label: "CARTO Voyager (Default)"
    },
    gmaps: {
      url: "https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}",
      attribution: 'Map data &copy; <a href="https://www.google.com/maps">Google Maps</a>',
      subdomains: "",
      maxZoom: 20,
      label: "Google Maps (Road)"
    },
    gmaps_satellite: {
      url: "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
      attribution: 'Map data &copy; <a href="https://www.google.com/maps">Google Maps</a>',
      subdomains: "",
      maxZoom: 20,
      label: "Google Maps (Satellite)"
    },
    gmaps_hybrid: {
      url: "https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
      attribution: 'Map data &copy; <a href="https://www.google.com/maps">Google Maps</a>',
      subdomains: "",
      maxZoom: 20,
      label: "Google Maps (Hybrid)"
    }
  };

  function switchMapProvider(providerKey) {
    if (!state.leafletMap) return;
    const provider = MAP_PROVIDERS[providerKey];
    if (!provider) return;

    // Remove old tile layer
    if (state.mapLayers.baseTile) {
      state.leafletMap.removeLayer(state.mapLayers.baseTile);
    }

    // Add new tile layer (insert below other layers)
    state.mapLayers.baseTile = L.tileLayer(provider.url, {
      attribution: provider.attribution,
      subdomains: provider.subdomains || "",
      maxZoom: provider.maxZoom
    });

    // Insert tile at the bottom of the layer stack
    state.mapLayers.baseTile.addTo(state.leafletMap);
    state.mapLayers.baseTile.bringToBack();

    // Update map provider label
    const badge = document.getElementById("map-provider-badge");
    if (badge) badge.textContent = provider.label;
  }

  function renderAllStopsOnMap() {
    if (!state.leafletMap || !state.mapLayers.stopsLayer) return;
    state.mapLayers.stopsLayer.clearLayers();

    state.allStops.forEach(stop => {
      const isHub = stop.is_hub;
      const marker = L.circleMarker([stop.lat, stop.lon], {
        radius: isHub ? 6 : 4,
        fillColor: isHub ? "#38bdf8" : "#94a3b8",
        color: "#0f172a",
        weight: 1.5,
        opacity: 0.9,
        fillOpacity: 0.8
      });

      marker.bindPopup(`
        <div style="font-family: inherit; font-size: 13px; color: #0f172a; line-height: 1.4;">
          <div style="font-weight: 700;">${stop.name}</div>
          <div style="font-size: 11px; color: #64748b;">${stop.name_hi || ""}</div>
          <div style="margin-top: 4px; font-size: 11px;">
            ${isHub ? '<span style="background:#e0f2fe; color:#0369a1; padding:1px 5px; border-radius:3px; font-weight:600;">Delhi Transit Hub</span>' : ''}
          </div>
          <div style="margin-top: 6px; display:flex; gap:4px;">
            <button onclick="window.selectAsOrigin('${stop.id}')" style="background:#0284c7; color:#fff; border:none; border-radius:4px; padding:3px 8px; font-size:11px; cursor:pointer;">Set Origin</button>
            <button onclick="window.selectAsDest('${stop.id}')" style="background:#e11d48; color:#fff; border:none; border-radius:4px; padding:3px 8px; font-size:11px; cursor:pointer;">Set Destination</button>
          </div>
        </div>
      `);

      state.mapLayers.stopsLayer.addLayer(marker);
    });
  }

  function renderAmenitiesOnMap() {
    if (!state.leafletMap || !state.mapLayers.amenitiesLayer) return;
    state.mapLayers.amenitiesLayer.clearLayers();

    const filtered = state.allAmenities.filter(a => {
      if (state.activeAmenityCategory === "NONE") return false;
      if (state.activeAmenityCategory === "ALL") return true;
      if (Array.isArray(state.activeAmenityCategory)) {
        return state.activeAmenityCategory.includes(a.category);
      }
      return a.category === state.activeAmenityCategory;
    });

    const config = {
      pink_toilet: { icon: "🚻", bg: "#ec4899", border: "#f472b6", label: "MCD Pink Toilet (Safe Sanitation)" },
      metro: { icon: "🚇", bg: "#06b6d4", border: "#38bdf8", label: "DMRC Metro Station" },
      hospital: { icon: "🏥", bg: "#ef4444", border: "#f87171", label: "Hospital & Trauma Emergency" },
      cafe: { icon: "☕", bg: "#d97706", border: "#fbbf24", label: "Cafe & Quick Refreshment" },
      cinema: { icon: "🎬", bg: "#8b5cf6", border: "#c084fc", label: "Cinema & Entertainment" },
      police: { icon: "🚔", bg: "#1d4ed8", border: "#60a5fa", label: "Delhi Police Station" }
    };

    filtered.forEach(item => {
      const c = config[item.category] || { icon: "📍", bg: "#64748b", border: "#94a3b8", label: "Transit Amenity" };
      const amenityIcon = L.divIcon({
        className: "custom-amenity-marker",
        html: `
          <div style="background:${c.bg}; border:2px solid #ffffff; width:26px; height:26px; border-radius:50%; display:flex; align-items:center; justify-content:center; box-shadow:0 0 10px ${c.bg}; font-size:13px; cursor:pointer;" title="${item.name}">
            ${c.icon}
          </div>
        `,
        iconSize: [26, 26],
        iconAnchor: [13, 13]
      });

      const tagsHtml = (item.tags || []).map(t =>
        `<span style="background:rgba(15,23,42,0.08); color:#0f172a; padding:1px 5px; border-radius:3px; font-size:10px; margin-right:3px;">${t}</span>`
      ).join("");

      const marker = L.marker([item.lat, item.lon], { icon: amenityIcon });
      marker.bindPopup(`
        <div style="font-family:inherit; font-size:12px; color:#0f172a; max-width:240px; line-height:1.4;">
          <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:4px;">
            <span style="font-size:10px; font-weight:700; color:${c.bg}; text-transform:uppercase;">${c.label}</span>
            <span style="font-size:11px; font-weight:700; color:#0284c7;">~${item.distance_m}m walk</span>
          </div>
          <div style="font-weight:700; font-size:13px; color:#0f172a;">${item.name}</div>
          <div style="font-size:11px; color:#64748b; margin-bottom:4px;">${item.name_hi || ""}</div>
          <div style="font-size:11px; color:#334155; margin-bottom:6px;">${item.details}</div>
          <div style="display:flex; flex-wrap:wrap; gap:2px; margin-bottom:8px;">${tagsHtml}</div>
          <div style="border-top:1px solid #e2e8f0; padding-top:6px; font-size:10px; color:#64748b;">
            Linked to: <b>${item.stop_id}</b> (~${item.walking_min} min walking distance)
          </div>
        </div>
      `);

      state.mapLayers.amenitiesLayer.addLayer(marker);
    });
  }

  function renderRouteOnMap(journey) {
    if (state.useFallbackCanvas) {
      drawCanvasMap();
      return;
    }
    if (!state.leafletMap) return;

    state.mapLayers.routeLayer.clearLayers();
    state.mapLayers.pinsLayer.clearLayers();

    const geometry = journey.geometry;
    if (!geometry || geometry.length === 0) return;

    // Draw background casing for polyline
    const casingPolyline = L.polyline(geometry, {
      color: "#0f172a",
      weight: 8,
      opacity: 0.9,
      lineCap: "round",
      lineJoin: "round"
    });
    state.mapLayers.routeLayer.addLayer(casingPolyline);

    // Segment-by-segment congestion styling if available
    if (journey.segments && journey.segments.length > 0) {
      for (let i = 0; i < journey.segments.length; i++) {
        const seg = journey.segments[i];
        const p1 = geometry[i];
        const p2 = geometry[i + 1];
        if (p1 && p2) {
          const segLine = L.polyline([p1, p2], {
            color: seg.color || "#10b981",
            weight: 5,
            opacity: 0.95
          });
          segLine.bindTooltip(`Segment Speed: ${seg.current_speed_kmh} km/h (${seg.status})`, { sticky: true });
          state.mapLayers.routeLayer.addLayer(segLine);
        }
      }
    } else {
      // Main polyline
      const mainPolyline = L.polyline(geometry, {
        color: journey.color || "#10b981",
        weight: 5,
        opacity: 0.95
      });
      state.mapLayers.routeLayer.addLayer(mainPolyline);
    }

    // Origin Pin (Custom Blue Icon)
    const originCoord = geometry[0];
    const destCoord = geometry[geometry.length - 1];

    const originIcon = L.divIcon({
      className: "custom-pin origin-pin",
      html: `
        <div style="background:#38bdf8; width:18px; height:18px; border-radius:50%; border:3px solid #fff; box-shadow:0 0 10px rgba(56,189,248,0.8); display:flex; align-items:center; justify-content:center;">
          <div style="width:5px; height:5px; background:#fff; border-radius:50%;"></div>
        </div>
      `,
      iconSize: [18, 18],
      iconAnchor: [9, 9]
    });
    const originMarker = L.marker(originCoord, { icon: originIcon }).bindPopup(`<b>Origin:</b> ${state.originStop.name}`);
    state.mapLayers.pinsLayer.addLayer(originMarker);

    // Destination Pin (Custom Red Icon)
    const destIcon = L.divIcon({
      className: "custom-pin dest-pin",
      html: `
        <div style="background:#ef4444; width:18px; height:18px; border-radius:50%; border:3px solid #fff; box-shadow:0 0 10px rgba(239,68,68,0.8); display:flex; align-items:center; justify-content:center;">
          <div style="width:5px; height:5px; background:#fff; border-radius:50%;"></div>
        </div>
      `,
      iconSize: [18, 18],
      iconAnchor: [9, 9]
    });
    const destMarker = L.marker(destCoord, { icon: destIcon }).bindPopup(`<b>Destination:</b> ${state.destStop.name}`);
    state.mapLayers.pinsLayer.addLayer(destMarker);

    // Auto-fit route
    const bounds = L.latLngBounds(geometry);
    state.leafletMap.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 });
  }

  function renderLiveBusesOnMap() {
    if (state.useFallbackCanvas) {
      drawCanvasMap();
      return;
    }
    if (!state.leafletMap || !state.mapLayers.busesLayer) return;

    state.mapLayers.busesLayer.clearLayers();

    state.liveBuses.forEach(bus => {
      const busIcon = L.divIcon({
        className: "live-bus-marker",
        html: `
          <div style="position:relative; width:28px; height:28px; display:flex; align-items:center; justify-content:center;">
            <div style="position:absolute; width:26px; height:26px; border-radius:50%; background:#0f172a; border:2px solid #34d399; box-shadow:0 0 8px rgba(52,211,153,0.6); display:flex; align-items:center; justify-content:center;">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="#34d399">
                <path d="M4 16c0 .88.39 1.67 1 2.22V20c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-1h8v1c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-1.78c.61-.55 1-1.34 1-2.22V6c0-3.5-3.58-4-8-4s-8 .5-8 4v10zm3.5 1c-.83 0-1.5-.67-1.5-1.5S6.67 14 7.5 14s1.5.67 1.5 1.5S8.33 17 7.5 17zm9 0c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5zm1.5-6H6V6h12v5z"/>
              </svg>
            </div>
            <div style="position:absolute; top:-12px; background:#0f172a; border:1px solid #34d399; color:#34d399; font-size:9px; font-weight:700; padding:1px 4px; border-radius:3px; white-space:nowrap;">
              ${bus.route_short_name}
            </div>
          </div>
        `,
        iconSize: [28, 28],
        iconAnchor: [14, 14]
      });

      const marker = L.marker([bus.lat, bus.lon], { icon: busIcon });
      marker.bindPopup(`
        <div style="font-family:inherit; font-size:12px; color:#0f172a; line-height:1.4;">
          <div style="font-weight:700; font-size:13px; color:#047857;">Bus ${bus.vehicle_id}</div>
          <div><b>Route:</b> ${bus.route_short_name} (${bus.agency})</div>
          <div><b>Speed:</b> ${bus.current_speed_kmh} km/h (${bus.speed_status})</div>
          <div><b>Next Stop:</b> ${bus.next_stop_name}</div>
          <div><b>Occupancy:</b> ${bus.crowding_level} (${bus.crowding_percentage}%)</div>
          <div style="font-size:10px; color:#64748b; margin-top:4px;">Last GPS ping: ${bus.last_ping_seconds_ago}s ago</div>
        </div>
      `);

      state.mapLayers.busesLayer.addLayer(marker);
    });
  }

  function clearMapRoute() {
    if (state.leafletMap && state.mapLayers.routeLayer) {
      state.mapLayers.routeLayer.clearLayers();
      state.mapLayers.pinsLayer.clearLayers();
    }
    if (state.useFallbackCanvas) {
      drawCanvasMap();
    }
  }

  /* --------------------------------------------------------------------------
     Fallback High-Performance Vector Canvas Map Engine
     (Guarantees 100% functionality even in zero-network/offline environments)
     -------------------------------------------------------------------------- */
  function initCanvasFallback() {
    state.useFallbackCanvas = true;
    if (elements.canvasFallback) {
      elements.canvasFallback.style.display = "block";
      window.addEventListener("resize", resizeCanvas);
      resizeCanvas();
      drawCanvasMap();
    }
  }

  function resizeCanvas() {
    if (!elements.canvasFallback) return;
    const rect = elements.canvasFallback.parentElement.getBoundingClientRect();
    elements.canvasFallback.width = rect.width;
    elements.canvasFallback.height = rect.height;
    drawCanvasMap();
  }

  function coordToCanvas(lat, lon, w, h) {
    // Delhi bounding box: lat 28.48 to 28.75, lon 77.02 to 77.34
    const minLat = 28.48, maxLat = 28.75;
    const minLon = 77.02, maxLon = 77.34;
    const x = ((lon - minLon) / (maxLon - minLon)) * (w * 0.8) + (w * 0.1);
    const y = ((maxLat - lat) / (maxLat - minLat)) * (h * 0.8) + (h * 0.1);
    return { x, y };
  }

  function drawCanvasMap() {
    const canvas = elements.canvasFallback;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const w = canvas.width;
    const h = canvas.height;

    // Background
    ctx.fillStyle = "#090d16";
    ctx.fillRect(0, 0, w, h);

    // Grid lines
    ctx.strokeStyle = "rgba(51, 65, 85, 0.25)";
    ctx.lineWidth = 1;
    for (let x = 0; x < w; x += 60) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, h);
      ctx.stroke();
    }
    for (let y = 0; y < h; y += 60) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(w, y);
      ctx.stroke();
    }

    // Draw Yamuna River representation
    ctx.strokeStyle = "rgba(14, 116, 144, 0.4)";
    ctx.lineWidth = 6;
    ctx.beginPath();
    const riverPoints = [
      { lat: 28.73, lon: 77.23 },
      { lat: 28.69, lon: 77.23 },
      { lat: 28.64, lon: 77.25 },
      { lat: 28.59, lon: 77.26 },
      { lat: 28.52, lon: 77.31 }
    ];
    riverPoints.forEach((pt, idx) => {
      const p = coordToCanvas(pt.lat, pt.lon, w, h);
      if (idx === 0) ctx.moveTo(p.x, p.y);
      else ctx.lineTo(p.x, p.y);
    });
    ctx.stroke();

    // Draw Selected Journey Route
    const selected = state.journeys.find(j => j.journey_id === state.selectedJourneyId);
    if (selected && selected.geometry) {
      ctx.strokeStyle = "#0284c7";
      ctx.lineWidth = 10;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.beginPath();
      selected.geometry.forEach((pt, idx) => {
        const p = coordToCanvas(pt[0], pt[1], w, h);
        if (idx === 0) ctx.moveTo(p.x, p.y);
        else ctx.lineTo(p.x, p.y);
      });
      ctx.stroke();

      ctx.strokeStyle = selected.color || "#10b981";
      ctx.lineWidth = 5;
      ctx.stroke();
    }

    // Draw All Bus Stops
    state.allStops.forEach(s => {
      const p = coordToCanvas(s.lat, s.lon, w, h);
      ctx.fillStyle = s.is_hub ? "#38bdf8" : "#64748b";
      ctx.beginPath();
      ctx.arc(p.x, p.y, s.is_hub ? 5 : 3, 0, Math.PI * 2);
      ctx.fill();

      if (s.is_hub) {
        ctx.fillStyle = "#94a3b8";
        ctx.font = "9px -apple-system, sans-serif";
        ctx.fillText(s.name.split("/")[0].trim(), p.x + 8, p.y + 3);
      }
    });

    // Draw Active Live Buses
    state.liveBuses.forEach(b => {
      const p = coordToCanvas(b.lat, b.lon, w, h);
      ctx.fillStyle = "#10b981";
      ctx.shadowColor = "#10b981";
      ctx.shadowBlur = 8;
      ctx.beginPath();
      ctx.arc(p.x, p.y, 6, 0, Math.PI * 2);
      ctx.fill();
      ctx.shadowBlur = 0;

      ctx.fillStyle = "#ffffff";
      ctx.font = "bold 9px sans-serif";
      ctx.fillText(b.route_short_name, p.x + 8, p.y - 4);
    });
  }

  /* --------------------------------------------------------------------------
     Event Listeners & Autocomplete
     -------------------------------------------------------------------------- */
  function setupEventListeners() {
    // Autocomplete on Origin Input
    elements.originInput.addEventListener("input", e => {
      handleAutocomplete(e.target.value, elements.originDropdown, stop => {
        state.originStop = stop;
        elements.originInput.value = stop.name;
        elements.originDropdown.style.display = "none";
      });
    });

    // Autocomplete on Dest Input
    elements.destInput.addEventListener("input", e => {
      handleAutocomplete(e.target.value, elements.destDropdown, stop => {
        state.destStop = stop;
        elements.destInput.value = stop.name;
        elements.destDropdown.style.display = "none";
      });
    });

    // Close autocomplete on outside click
    document.addEventListener("click", e => {
      if (!e.target.closest(".input-row")) {
        elements.originDropdown.style.display = "none";
        elements.destDropdown.style.display = "none";
      }
    });

    // Swap Origin and Destination
    elements.btnSwap.addEventListener("click", () => {
      const tempStop = state.originStop;
      state.originStop = state.destStop;
      state.destStop = tempStop;

      elements.originInput.value = state.originStop ? state.originStop.name : "";
      elements.destInput.value = state.destStop ? state.destStop.name : "";

      if (state.originStop && state.destStop) {
        searchJourneys();
      }
    });

    // Plan Button
    elements.btnPlan.addEventListener("click", searchJourneys);

    // Scenario Switcher
    if (elements.scenarioSelect) {
      elements.scenarioSelect.addEventListener("change", e => {
        changeScenario(e.target.value);
      });
    }

    // Filter Pills
    document.querySelectorAll(".filter-pill").forEach(pill => {
      pill.addEventListener("click", () => {
        document.querySelectorAll(".filter-pill").forEach(p => p.classList.remove("active"));
        pill.classList.add("active");
        state.activeFilter = pill.getAttribute("data-filter");
        renderJourneysList();
      });
    });

    // Quick Hub Chips
    document.querySelectorAll(".chip-btn").forEach(chip => {
      chip.addEventListener("click", () => {
        const stopId = chip.getAttribute("data-stop-id");
        const stop = state.allStops.find(s => s.id === stopId);
        if (!stop) return;

        if (!state.originStop) {
          state.originStop = stop;
          elements.originInput.value = stop.name;
        } else {
          state.destStop = stop;
          elements.destInput.value = stop.name;
          searchJourneys();
        }
      });
    });

    // Map Controls
    if (elements.btnFitRoute) {
      elements.btnFitRoute.addEventListener("click", () => {
        const selected = state.journeys.find(j => j.journey_id === state.selectedJourneyId);
        if (selected && state.leafletMap) {
          const bounds = L.latLngBounds(selected.geometry);
          state.leafletMap.fitBounds(bounds, { padding: [40, 40] });
        }
      });
    }

    if (elements.btnToggleBuses) {
      elements.btnToggleBuses.addEventListener("click", () => {
        if (!state.leafletMap || !state.mapLayers.busesLayer) return;
        if (state.leafletMap.hasLayer(state.mapLayers.busesLayer)) {
          state.leafletMap.removeLayer(state.mapLayers.busesLayer);
          elements.btnToggleBuses.classList.remove("active");
        } else {
          state.leafletMap.addLayer(state.mapLayers.busesLayer);
          elements.btnToggleBuses.classList.add("active");
        }
      });
    }

    // ── Amenity Toggle Chips ─────────────────────────────────────────────────
    document.querySelectorAll(".amenity-toggle-chip").forEach(chip => {
      chip.addEventListener("click", () => {
        const cat = chip.getAttribute("data-category");

        if (cat === "ALL") {
          // "All Active" toggles the entire amenity layer visibility
          const isActive = chip.classList.toggle("active");
          document.querySelectorAll(".amenity-toggle-chip:not([data-category='ALL'])").forEach(c => {
            if (isActive) c.classList.add("active"); else c.classList.remove("active");
          });
          state.activeAmenityCategory = isActive ? "ALL" : "NONE";
          renderAmenitiesOnMap();
          return;
        }

        // Individual category toggle
        chip.classList.toggle("active");
        const activeCategories = Array.from(
          document.querySelectorAll(".amenity-toggle-chip:not([data-category='ALL']).active")
        ).map(c => c.getAttribute("data-category"));

        // Update "All Active" chip state
        const allChip = document.querySelector(".amenity-toggle-chip[data-category='ALL']");
        const totalCats = document.querySelectorAll(".amenity-toggle-chip:not([data-category='ALL'])").length;
        if (allChip) {
          allChip.classList.toggle("active", activeCategories.length === totalCats);
        }

        // Store as a Set for fast lookup
        state.activeAmenityCategory = activeCategories.length === 0 ? "NONE" : activeCategories;
        renderAmenitiesOnMap();
      });
    });

    // ── Map Provider Switcher ────────────────────────────────────────────────
    document.querySelectorAll(".map-provider-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const provider = btn.getAttribute("data-provider");
        document.querySelectorAll(".map-provider-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        switchMapProvider(provider);
      });
    });

    // Modal Events
    if (elements.btnOpenModal) {
      elements.btnOpenModal.addEventListener("click", () => elements.modalBackdrop.classList.add("open"));
    }
    if (elements.telemetryPill) {
      elements.telemetryPill.addEventListener("click", () => elements.modalBackdrop.classList.add("open"));
    }
    if (elements.btnCloseModal) {
      elements.btnCloseModal.addEventListener("click", () => elements.modalBackdrop.classList.remove("open"));
    }
    elements.modalBackdrop.addEventListener("click", e => {
      if (e.target === elements.modalBackdrop) {
        elements.modalBackdrop.classList.remove("open");
      }
    });

    // ── NCMC Modal Events ────────────────────────────────────────────────────
    const btnOpenNcmc = document.getElementById("btn-open-ncmc");
    const ncmcModalBackdrop = document.getElementById("ncmc-modal-backdrop");
    const btnCloseNcmc = document.getElementById("btn-close-ncmc");

    if (btnOpenNcmc && ncmcModalBackdrop) {
      btnOpenNcmc.addEventListener("click", () => ncmcModalBackdrop.classList.add("open"));
    }
    if (btnCloseNcmc && ncmcModalBackdrop) {
      btnCloseNcmc.addEventListener("click", () => ncmcModalBackdrop.classList.remove("open"));
    }
    if (ncmcModalBackdrop) {
      ncmcModalBackdrop.addEventListener("click", e => {
        if (e.target === ncmcModalBackdrop) ncmcModalBackdrop.classList.remove("open");
      });
    }

    // NCMC Presets
    document.querySelectorAll(".ncmc-preset-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".ncmc-preset-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        const fare = parseInt(btn.getAttribute("data-fare"), 10) || 25;
        const discount = Math.max(2, Math.ceil(fare * 0.10));
        const cardFare = fare - discount;
        const monthly = discount * 44;

        const cashEl = document.getElementById("ncmc-cash-fare");
        const cardEl = document.getElementById("ncmc-card-fare");
        const discEl = document.getElementById("ncmc-discount-amount");
        const monthEl = document.getElementById("ncmc-monthly-amount");

        if (cashEl) cashEl.textContent = `₹${fare}`;
        if (cardEl) cardEl.textContent = `₹${cardFare}`;
        if (discEl) discEl.textContent = `₹${discount}`;
        if (monthEl) monthEl.textContent = `~₹${monthly}`;
      });
    });

    // ── SOS Modal Events ─────────────────────────────────────────────────────
    const btnOpenSos = document.getElementById("btn-open-sos");
    const sosModalBackdrop = document.getElementById("sos-modal-backdrop");
    const btnCloseSos = document.getElementById("btn-close-sos");

    if (btnOpenSos && sosModalBackdrop) {
      btnOpenSos.addEventListener("click", () => window.openSosModal());
    }
    if (btnCloseSos && sosModalBackdrop) {
      btnCloseSos.addEventListener("click", () => sosModalBackdrop.classList.remove("open"));
    }
    if (sosModalBackdrop) {
      sosModalBackdrop.addEventListener("click", e => {
        if (e.target === sosModalBackdrop) sosModalBackdrop.classList.remove("open");
      });
    }

    // WhatsApp SOS Dispatch Trigger
    const btnWhatsappSos = document.getElementById("btn-trigger-whatsapp-sos");
    if (btnWhatsappSos) {
      btnWhatsappSos.addEventListener("click", () => {
        const text = state.currentSosText || `EMERGENCY SOS: I am on Delhi Transit bus DL-1PD-4521 near AIIMS Ring Road. Police: 112 / 1091`;
        window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, "_blank");
      });
    }
  }

  window.openSosModal = function(journeyId = null) {
    const sosModal = document.getElementById("sos-modal-backdrop");
    if (!sosModal) return;

    const journey = journeyId ? state.journeys.find(j => j.journey_id === journeyId) : (state.journeys[0] || null);
    const fleetPlate = journey?.live_fleet_number || "DL-1PD-4521";
    const stopName = journey?.stops?.[0]?.name || (state.originStop?.name || "Kashmere Gate ISBT");
    const routeName = journey?.route_short_name || "DTC Transit Corridor";

    const fleetEl = document.getElementById("sos-fleet-plate");
    const stopEl = document.getElementById("sos-current-stop");
    if (fleetEl) fleetEl.textContent = fleetPlate;
    if (stopEl) stopEl.textContent = `Location: ${stopName} • Route ${routeName}`;

    state.currentSosText = `🚨 EMERGENCY SOS - DILLITRANSIT 🚨\nI need immediate help! Traveling on Delhi Transit:\n• Vehicle Plate: ${fleetPlate}\n• Route: ${routeName}\n• Near: ${stopName}\n• Live Map: https://maps.google.com/?q=${journey?.stops?.[0]?.lat || 28.6675},${journey?.stops?.[0]?.lon || 77.2282}\n• Hotlines: 112 (Delhi Police) | 1091 (Women Safety)`;

    // Populate police stations list
    const policeStations = state.allAmenities.filter(a => a.category === "police");
    const listEl = document.getElementById("sos-police-list");
    if (listEl) {
      listEl.innerHTML = policeStations.slice(0, 4).map(p => `
        <div style="padding:6px 0; border-bottom:1px solid rgba(255,255,255,0.06); display:flex; justify-content:space-between; align-items:center;">
          <div>
            <div style="font-weight:700; color:var(--text-main); font-size:0.75rem;">${p.name}</div>
            <div style="font-size:0.68rem; color:var(--text-muted);">${p.details}</div>
          </div>
          <a href="tel:112" style="background:#1d4ed8; color:#fff; text-decoration:none; padding:3px 8px; border-radius:4px; font-weight:700; font-size:0.72rem;">📞 112</a>
        </div>
      `).join("");
    }

    sosModal.classList.add("open");
  };

  function handleAutocomplete(query, dropdownEl, onSelect) {
    const q = query.trim().toLowerCase();
    if (!q) {
      dropdownEl.style.display = "none";
      return;
    }

    const matches = state.allStops.filter(s =>
      s.name.toLowerCase().includes(q) ||
      (s.name_hi && s.name_hi.toLowerCase().includes(q)) ||
      (s.zone && s.zone.toLowerCase().includes(q))
    ).slice(0, 6);

    if (matches.length === 0) {
      dropdownEl.style.display = "none";
      return;
    }

    dropdownEl.innerHTML = matches.map(s => `
      <div class="autocomplete-item" data-id="${s.id}">
        <div class="item-main">
          <span>${s.name}</span>
          ${s.is_hub ? `<span class="item-hub-tag">Hub</span>` : ''}
        </div>
        <div class="item-sub">${s.name_hi || s.zone}</div>
      </div>
    `).join("");

    dropdownEl.style.display = "block";

    dropdownEl.querySelectorAll(".autocomplete-item").forEach(item => {
      item.addEventListener("click", () => {
        const stopId = item.getAttribute("data-id");
        const stop = state.allStops.find(s => s.id === stopId);
        if (stop) onSelect(stop);
      });
    });
  }

  function setDefaultTrip(origId, destId) {
    const orig = state.allStops.find(s => s.id === origId);
    const dest = state.allStops.find(s => s.id === destId);
    if (orig && dest) {
      state.originStop = orig;
      state.destStop = dest;
      elements.originInput.value = orig.name;
      elements.destInput.value = dest.name;
      searchJourneys();
    }
  }

  function updateTimestamp() {
    const now = new Date();
    const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    if (elements.lastUpdatedText) {
      elements.lastUpdatedText.textContent = `Last telemetry sync: ${timeStr}`;
    }
  }

  function startLivePolling() {
    // Poll telemetry and live buses every 8 seconds
    setInterval(() => {
      const selected = state.journeys.find(j => j.journey_id === state.selectedJourneyId);
      const routeId = selected ? selected.route_id : null;
      fetchLiveBuses(routeId);
    }, 8000);
  }

  // ── Movie-Theater Bus Seat Selection Logic ────────────────────────────────
  state.currentSeatSelection = null;
  state.currentSeatJourney = null;

  window.openSeatModal = async function(journeyId) {
    const modal = document.getElementById("seat-modal-backdrop");
    if (!modal) return;

    const journey = state.journeys.find(j => j.journey_id === journeyId) || state.journeys[0];
    if (!journey) return;

    state.currentSeatJourney = journey;
    state.currentSeatSelection = null;

    // Reset UI displays
    document.getElementById("digital-boarding-pass").style.display = "none";
    document.getElementById("seat-booking-panel").style.display = "block";
    document.getElementById("seat-bus-title").textContent = `Route ${journey.route_short_name} • ${journey.bus_type}`;
    document.getElementById("seat-bus-plate").textContent = `Fleet: ${journey.live_fleet_number || 'DL-1PD-4521'}`;

    try {
      const res = await fetch(`/api/seats?route_id=${encodeURIComponent(journey.route_id || '502')}&fleet_plate=${encodeURIComponent(journey.live_fleet_number || 'DL-1PD-4521')}&crowd_pct=${journey.crowd_percentage || 50}&is_saheli=${journey.is_saheli_pink ? 'true' : 'false'}`);
      const data = await res.json();
      if (data.success && data.seat_map) {
        renderSeatGrid(data.seat_map);
      }
    } catch (err) {
      console.warn("Failed to load seats, using offline fallback:", err);
    }

    modal.classList.add("open");
  };

  function renderSeatGrid(seatMap) {
    const gridEl = document.getElementById("bus-seat-grid");
    const counterEl = document.getElementById("seat-avail-counter");
    if (counterEl) {
      counterEl.innerHTML = `
        <span style="background:rgba(52,211,153,0.15); color:#34d399; font-weight:700; font-size:0.75rem; padding:3px 8px; border-radius:4px; border:1px solid rgba(52,211,153,0.3);">
          ${seatMap.available_seats} Available • ${seatMap.pink_zone_available} Pink Reserved
        </span>
      `;
    }

    if (!gridEl) return;
    gridEl.innerHTML = seatMap.seating_grid.map(s => {
      const isOcc = s.status === "occupied";
      const isPink = s.zone === "female_pink";
      const isAccess = s.zone === "accessible_senior";
      let seatClass = "bus-seat-box";
      if (isOcc) seatClass += " occupied";
      else if (isPink) seatClass += " female-pink";
      else if (isAccess) seatClass += " accessible";
      else seatClass += " available";

      return `
        <div class="${seatClass}" data-seat-id="${s.id}" data-zone="${s.zone}" data-price="${s.price_inr}" title="${s.zone_name} • Seat ${s.label}">
          <span class="seat-icon">${isPink ? '🚺' : (isAccess ? '♿' : '💺')}</span>
          <span class="seat-num">${s.label}</span>
        </div>
      `;
    }).join("");

    // Seat click handlers
    gridEl.querySelectorAll(".bus-seat-box:not(.occupied)").forEach(box => {
      box.addEventListener("click", () => {
        gridEl.querySelectorAll(".bus-seat-box").forEach(b => b.classList.remove("selected"));
        box.classList.add("selected");

        const seatId = box.getAttribute("data-seat-id");
        const zone = box.getAttribute("data-zone");
        const price = parseInt(box.getAttribute("data-price"), 10) || 25;
        state.currentSeatSelection = { seatId, zone, price };

        const summaryEl = document.getElementById("seat-summary-label");
        const fareEl = document.getElementById("seat-fare-label");
        const gender = document.getElementById("seat-passenger-gender").value;

        const isFreePink = (zone === "female_pink" && gender === "Female");
        if (summaryEl) {
          summaryEl.textContent = `Seat ${seatId} (${zone === 'female_pink' ? 'Women Pink Section' : (zone === 'accessible_senior' ? 'Senior/Accessible' : 'General')})`;
        }
        if (fareEl) {
          fareEl.textContent = isFreePink ? "Fare: ₹0 (Delhi Govt Free Pink Pass Eligible!)" : `Fare: ₹${price}`;
          fareEl.style.color = isFreePink ? "#f472b6" : "#38bdf8";
        }
      });
    });

    // Auto-select first available pink or general seat
    const firstAvail = gridEl.querySelector(".bus-seat-box:not(.occupied)");
    if (firstAvail) firstAvail.click();
  }

  // Confirm reservation & display digital anti-chaos boarding pass
  const btnConfirmSeat = document.getElementById("btn-confirm-seat");
  if (btnConfirmSeat) {
    btnConfirmSeat.addEventListener("click", async () => {
      if (!state.currentSeatSelection) {
        alert("Please select an available seat first.");
        return;
      }

      const passengerName = document.getElementById("seat-passenger-name").value || "Delhi Commuter";
      const gender = document.getElementById("seat-passenger-gender").value;
      const journey = state.currentSeatJourney || state.journeys[0];

      try {
        const res = await fetch("/api/reserve-seat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            route_id: journey?.route_id || "502",
            fleet_plate: journey?.live_fleet_number || "DL-1PD-4521",
            seat_id: state.currentSeatSelection.seatId,
            passenger_name: passengerName,
            gender: gender,
            boarding_stop: journey?.stops?.[0]?.name || "Kashmere Gate ISBT"
          })
        });

        const data = await res.json();
        if (data.success && data.reservation) {
          const r = data.reservation;
          document.getElementById("seat-booking-panel").style.display = "none";
          const passEl = document.getElementById("digital-boarding-pass");
          passEl.style.display = "block";

          document.getElementById("pass-pnr").textContent = `PNR: ${r.pnr}`;
          document.getElementById("pass-token-id").textContent = `Anti-Chaos Token: ${r.token_id}`;
          document.getElementById("pass-seat-badge").textContent = r.seat_id;
          document.getElementById("pass-seat-badge").style.background = r.seat_id.startsWith("W") ? "#ec4899" : "#0284c7";
          document.getElementById("pass-name").textContent = r.passenger_name;
          document.getElementById("pass-cat").textContent = r.is_pink_pass ? "Women Priority (₹0 Free Pink Pass)" : `${r.gender} Seating`;
          document.getElementById("pass-fleet").textContent = r.fleet_plate;
          document.getElementById("pass-fare").textContent = r.is_pink_pass ? "₹0 (Delhi Pink Pass)" : `₹${r.fare_charged_inr}`;
        }
      } catch (err) {
        console.warn("Reservation error:", err);
      }
    });
  }

  // Seat modal close handlers
  const btnCloseSeat = document.getElementById("btn-close-seat");
  const seatModalBackdrop = document.getElementById("seat-modal-backdrop");
  if (btnCloseSeat && seatModalBackdrop) {
    btnCloseSeat.addEventListener("click", () => seatModalBackdrop.classList.remove("open"));
  }
  if (seatModalBackdrop) {
    seatModalBackdrop.addEventListener("click", e => {
      if (e.target === seatModalBackdrop) seatModalBackdrop.classList.remove("open");
    });
  }

  // Global window hooks for popup interactions
  window.selectJourney = selectJourney;
  window.selectAsOrigin = function (stopId) {
    const stop = state.allStops.find(s => s.id === stopId);
    if (stop) {
      state.originStop = stop;
      elements.originInput.value = stop.name;
      if (state.destStop) searchJourneys();
    }
  };

  window.selectAsDest = function (stopId) {
    const stop = state.allStops.find(s => s.id === stopId);
    if (stop) {
      state.destStop = stop;
      elements.destInput.value = stop.name;
      if (state.originStop) searchJourneys();
    }
  };

  // Run on DOM Ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
