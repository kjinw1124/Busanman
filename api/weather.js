const KMA_API_URL = "https://apihub.kma.go.kr/api/typ02/openApi/VilageFcstInfoService_2.0/getUltraSrtFcst";

const LOCATIONS = {
  "울산대학교": { nx: 101, ny: 84, lat: 35.5438, lon: 129.2563 },
  "울산광역시 중심": { nx: 102, ny: 84, lat: 35.5384, lon: 129.3114 },
  "서울광역시 중심": { nx: 60, ny: 127, lat: 37.5665, lon: 126.9780 },
  "부산광역시 중심": { nx: 98, ny: 76, lat: 35.1796, lon: 129.0756 },
};

const SKY_LABELS = { "1": "맑음", "3": "구름 많음", "4": "흐림" };
const PTY_LABELS = { "0": "없음", "1": "비", "2": "비/눈", "3": "눈", "4": "소나기", "5": "빗방울", "6": "빗방울/눈날림", "7": "눈날림" };

function pad(value) {
  return String(value).padStart(2, "0");
}

function baseCandidates(count = 6) {
  const kst = new Date(Date.now() + 9 * 60 * 60 * 1000);
  const first = new Date(kst);
  first.setUTCSeconds(0, 0);
  first.setUTCMinutes(30);
  if (kst.getUTCMinutes() < 45) first.setUTCHours(first.getUTCHours() - 1);

  return Array.from({ length: count }, (_, index) => {
    const candidate = new Date(first.getTime() - index * 30 * 60 * 1000);
    return {
      base_date: `${candidate.getUTCFullYear()}${pad(candidate.getUTCMonth() + 1)}${pad(candidate.getUTCDate())}`,
      base_time: `${pad(candidate.getUTCHours())}${pad(candidate.getUTCMinutes())}`,
    };
  });
}

function validatePayload(payload) {
  const response = payload?.response || {};
  const code = String(response.header?.resultCode ?? "");
  if (code && code !== "00") throw new Error(`${response.header?.resultMsg || "기상청 API 오류"} (${code})`);
  const rawItems = response.body?.items?.item;
  const items = Array.isArray(rawItems) ? rawItems : rawItems ? [rawItems] : [];
  if (!items.length) throw new Error("선택한 기준 시각에 예보 항목이 없습니다.");
  return items;
}

async function fetchForecast(authKey, location) {
  const errors = [];
  for (const base of baseCandidates()) {
    const params = new URLSearchParams({
      pageNo: "1",
      numOfRows: "1000",
      dataType: "JSON",
      base_date: base.base_date,
      base_time: base.base_time,
      nx: String(location.nx),
      ny: String(location.ny),
      authKey,
    });
    try {
      const response = await fetch(`${KMA_API_URL}?${params}`, { signal: AbortSignal.timeout(9000) });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      return { items: validatePayload(payload), base };
    } catch (error) {
      errors.push(`${base.base_date} ${base.base_time}: ${error.message}`);
    }
  }
  throw new Error(`최근 예보를 가져오지 못했습니다. ${errors.slice(0, 3).join(" | ")}`);
}

function toForecast(items) {
  const grouped = new Map();
  for (const item of items) {
    const key = `${item.fcstDate}${String(item.fcstTime).padStart(4, "0")}`;
    if (!grouped.has(key)) grouped.set(key, { forecastAt: key });
    grouped.get(key)[item.category] = item.fcstValue;
  }
  return [...grouped.values()]
    .sort((a, b) => a.forecastAt.localeCompare(b.forecastAt))
    .map((row) => ({
      forecastAt: row.forecastAt,
      temperature: Number(row.T1H),
      humidity: Number(row.REH),
      windSpeed: Number(row.WSD),
      rainfall: row.RN1 || "확인 필요",
      sky: SKY_LABELS[String(row.SKY)] || "확인 필요",
      precipitation: PTY_LABELS[String(row.PTY)] || "확인 필요",
    }));
}

module.exports = async function handler(request, response) {
  if (request.method !== "GET") {
    response.setHeader("Allow", "GET");
    return response.status(405).json({ error: "METHOD_NOT_ALLOWED" });
  }

  const locationName = typeof request.query.location === "string" ? request.query.location : "울산대학교";
  const location = LOCATIONS[locationName];
  if (!location) return response.status(400).json({ error: "UNKNOWN_LOCATION" });

  const authKey = process.env.KMA_AUTH_KEY?.trim();
  if (!authKey) {
    return response.status(503).json({
      error: "MISSING_API_KEY",
      message: "Vercel 프로젝트에 KMA_AUTH_KEY 환경 변수를 설정해 주세요.",
    });
  }

  try {
    const { items, base } = await fetchForecast(authKey, location);
    response.setHeader("Cache-Control", "s-maxage=300, stale-while-revalidate=60");
    return response.status(200).json({
      isLive: true,
      source: "기상청 초단기예보 API",
      location: { name: locationName, ...location },
      baseDate: base.base_date,
      baseTime: base.base_time,
      retrievedAt: new Date().toISOString(),
      forecast: toForecast(items),
    });
  } catch (error) {
    console.error("[api/weather] KMA request failed", { locationName, message: error.message });
    return response.status(502).json({ error: "KMA_API_FAILED", message: error.message });
  }
};
