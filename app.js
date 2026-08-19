const LOCATIONS = {
  "울산대학교": { nx: 101, ny: 84, lat: 35.5438, lon: 129.2563 },
  "울산광역시 중심": { nx: 102, ny: 84, lat: 35.5384, lon: 129.3114 },
  "서울광역시 중심": { nx: 60, ny: 127, lat: 37.5665, lon: 126.9780 },
  "부산광역시 중심": { nx: 98, ny: 76, lat: 35.1796, lon: 129.0756 },
};

const SKY_LABELS = { "1": "맑음", "3": "구름 많음", "4": "흐림" };
const PTY_LABELS = { "0": "없음", "1": "비", "2": "비/눈", "3": "눈", "4": "소나기", "5": "빗방울", "6": "빗방울/눈날림", "7": "눈날림" };
const charts = {};
let map;
let marker;
let latestForecast = [];

const $ = (id) => document.getElementById(id);

function weatherIcon(sky, precipitation) {
  if (["눈", "눈날림"].includes(precipitation)) return "❄️";
  if (["비/눈", "빗방울/눈날림"].includes(precipitation)) return "🌨️";
  if (["비", "소나기", "빗방울"].includes(precipitation)) return "🌧️";
  return { "맑음": "☀️", "구름 많음": "⛅", "흐림": "☁️" }[sky] || "🌦️";
}

function parseSample(payload, locationName) {
  const items = payload.response.body.items.item;
  const grouped = new Map();
  items.forEach((item) => {
    const key = `${item.fcstDate}${String(item.fcstTime).padStart(4, "0")}`;
    if (!grouped.has(key)) grouped.set(key, { forecastAt: key });
    grouped.get(key)[item.category] = item.fcstValue;
  });
  const forecast = [...grouped.values()].sort((a, b) => a.forecastAt.localeCompare(b.forecastAt)).map((row) => ({
    forecastAt: row.forecastAt,
    temperature: Number(row.T1H),
    humidity: Number(row.REH),
    windSpeed: Number(row.WSD),
    rainfall: row.RN1 || "확인 필요",
    sky: SKY_LABELS[String(row.SKY)] || "확인 필요",
    precipitation: PTY_LABELS[String(row.PTY)] || "확인 필요",
  }));
  return {
    isLive: false,
    source: "기상청 응답 형식 샘플",
    location: { name: locationName, ...LOCATIONS[locationName] },
    baseDate: String(items[0].baseDate),
    baseTime: String(items[0].baseTime),
    retrievedAt: new Date().toISOString(),
    forecast,
  };
}

async function loadWeather(locationName) {
  const response = await fetch(`/api/weather?location=${encodeURIComponent(locationName)}&t=${Date.now()}`);
  if (response.ok) return response.json();
  const sampleResponse = await fetch("/data/kma_ultra_short_forecast_sample.json");
  if (!sampleResponse.ok) throw new Error("날씨 데이터와 샘플 데이터를 모두 불러오지 못했습니다.");
  return parseSample(await sampleResponse.json(), locationName);
}

function formatForecastTime(value) {
  const month = value.slice(4, 6);
  const day = value.slice(6, 8);
  const hour = value.slice(8, 10);
  const minute = value.slice(10, 12);
  return `${month}.${day} ${hour}:${minute}`;
}

function formatBaseTime(date, time) {
  return `${date.slice(0, 4)}.${date.slice(4, 6)}.${date.slice(6, 8)} ${String(time).padStart(4, "0").slice(0, 2)}:${String(time).padStart(4, "0").slice(2)}`;
}

function deltaText(rows, field, unit) {
  if (rows.length < 2 || !Number.isFinite(rows[0][field]) || !Number.isFinite(rows[1][field])) return "다음 예보 —";
  const delta = rows[1][field] - rows[0][field];
  if (Math.abs(delta) < 0.01) return "다음 예보 변화 없음";
  return `다음 예보 ${delta > 0 ? "+" : ""}${delta.toFixed(1)}${unit}`;
}

function updateMap(data, current) {
  const { lat, lon, name } = data.location;
  if (!map) {
    map = L.map("weatherMap", { zoomControl: true, scrollWheelZoom: false }).setView([lat, lon], 11);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap contributors",
    }).addTo(map);
  } else {
    map.flyTo([lat, lon], 11, { duration: 0.7 });
  }
  if (marker) marker.remove();
  const icon = weatherIcon(current.sky, current.precipitation);
  const markerIcon = L.divIcon({
    className: "weather-marker",
    html: `<div class="weather-marker-inner"><span>${icon}</span><span>${current.temperature.toFixed(1)}°</span></div>`,
    iconSize: [88, 46],
    iconAnchor: [44, 23],
  });
  marker = L.marker([lat, lon], { icon: markerIcon }).addTo(map);
  marker.bindPopup(`<strong>${name}</strong><br>${current.sky} · ${current.precipitation}<br>기온 ${current.temperature.toFixed(1)} °C<br>습도 ${current.humidity.toFixed(0)} %<br>풍속 ${current.windSpeed.toFixed(1)} m/s`).openPopup();
}

function upsertChart(id, label, labels, values, color, fillColor) {
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart($(id), {
    type: "line",
    data: { labels, datasets: [{ label, data: values, borderColor: color, backgroundColor: fillColor, fill: true, tension: 0.36, borderWidth: 2.5, pointRadius: 3, pointHoverRadius: 6 }] },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { intersect: false, mode: "index" },
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: { color: "#718198", maxRotation: 0 } },
        y: { grid: { color: "rgba(60, 90, 120, .08)" }, ticks: { color: "#718198" } },
      },
    },
  });
}

function renderTable(rows) {
  $("forecastTable").innerHTML = rows.map((row) => `
    <tr>
      <td>${formatForecastTime(row.forecastAt)}</td>
      <td>${row.temperature.toFixed(1)} °C</td>
      <td>${row.humidity.toFixed(0)} %</td>
      <td>${row.windSpeed.toFixed(1)} m/s</td>
      <td>${row.rainfall}</td>
      <td>${weatherIcon(row.sky, row.precipitation)} ${row.sky}</td>
    </tr>`).join("");
}

function render(data) {
  const rows = data.forecast;
  if (!rows.length) throw new Error("표시할 예보가 없습니다.");
  latestForecast = rows;
  const current = rows[0];
  const icon = weatherIcon(current.sky, current.precipitation);

  $("sourceBadge").textContent = data.isLive ? "● LIVE API" : "● SAMPLE DATA";
  $("sourceBadge").className = `status-pill ${data.isLive ? "live" : "sample"}`;
  $("locationName").textContent = data.location.name;
  $("conditionText").textContent = `${current.sky} · 강수 ${current.precipitation}`;
  $("weatherIcon").textContent = icon;
  $("baseTime").textContent = formatBaseTime(data.baseDate, data.baseTime);
  $("retrievedAt").textContent = `마지막 조회 ${new Date(data.retrievedAt).toLocaleTimeString("ko-KR", { timeZone: "Asia/Seoul" })} KST`;
  $("gridCoordinates").textContent = `기상청 격자 · nx ${data.location.nx} / ny ${data.location.ny}`;
  $("temperature").textContent = `${current.temperature.toFixed(1)} °C`;
  $("humidity").textContent = `${current.humidity.toFixed(0)} %`;
  $("windSpeed").textContent = `${current.windSpeed.toFixed(1)} m/s`;
  $("rainfall").textContent = current.rainfall;
  $("temperatureDelta").textContent = deltaText(rows, "temperature", " °C");
  $("humidityDelta").textContent = deltaText(rows, "humidity", " %p");
  $("windDelta").textContent = deltaText(rows, "windSpeed", " m/s");
  $("precipitationType").textContent = `강수 형태 · ${current.precipitation}`;
  $("forecastRange").textContent = `${formatForecastTime(rows[0].forecastAt)} — ${formatForecastTime(rows.at(-1).forecastAt)}`;

  updateMap(data, current);
  const labels = rows.map((row) => row.forecastAt.slice(8, 10) + "시");
  upsertChart("temperatureChart", "기온", labels, rows.map((row) => row.temperature), "#ff7849", "rgba(255,120,73,.12)");
  upsertChart("humidityChart", "습도", labels, rows.map((row) => row.humidity), "#2776e8", "rgba(39,118,232,.12)");
  upsertChart("windChart", "풍속", labels, rows.map((row) => row.windSpeed), "#16a284", "rgba(22,162,132,.12)");
  renderTable(rows);
}

async function refresh() {
  const button = $("refreshButton");
  button.disabled = true;
  button.innerHTML = "<span aria-hidden=\"true\">↻</span> 불러오는 중";
  $("errorMessage").hidden = true;
  try {
    render(await loadWeather($("locationSelect").value));
  } catch (error) {
    $("errorMessage").textContent = error.message;
    $("errorMessage").hidden = false;
  } finally {
    button.disabled = false;
    button.innerHTML = "<span aria-hidden=\"true\">↻</span> 새로고침";
  }
}

function downloadCsv() {
  if (!latestForecast.length) return;
  const header = ["예보 시각", "기온(°C)", "습도(%)", "풍속(m/s)", "1시간 강수량", "하늘", "강수형태"];
  const rows = latestForecast.map((row) => [formatForecastTime(row.forecastAt), row.temperature, row.humidity, row.windSpeed, row.rainfall, row.sky, row.precipitation]);
  const csv = [header, ...rows].map((row) => row.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(",")).join("\n");
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob(["\ufeff", csv], { type: "text/csv;charset=utf-8" }));
  link.download = "kma_ultra_short_forecast.csv";
  link.click();
  URL.revokeObjectURL(link.href);
}

$("locationSelect").addEventListener("change", refresh);
$("refreshButton").addEventListener("click", refresh);
$("downloadButton").addEventListener("click", downloadCsv);
refresh();
