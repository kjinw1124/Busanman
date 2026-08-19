from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests


KMA_API_URL = (
    "https://apihub.kma.go.kr/api/typ02/openApi/"
    "VilageFcstInfoService_2.0/getUltraSrtFcst"
)
KST = ZoneInfo("Asia/Seoul")

CATEGORY_LABELS = {
    "T1H": "기온(°C)",
    "REH": "습도(%)",
    "RN1": "1시간 강수량",
    "SKY": "하늘상태",
    "PTY": "강수형태",
    "WSD": "풍속(m/s)",
}
SKY_LABELS = {"1": "맑음", "3": "구름 많음", "4": "흐림"}
PTY_LABELS = {
    "0": "없음",
    "1": "비",
    "2": "비/눈",
    "3": "눈",
    "4": "소나기",
    "5": "빗방울",
    "6": "빗방울/눈날림",
    "7": "눈날림",
}


@dataclass
class WeatherResult:
    payload: dict = field(repr=False)
    source: str
    base_date: str
    base_time: str
    message: str

    def summary(self) -> pd.Series:
        return pd.Series(
            {
                "자료": self.source,
                "기준 날짜": self.base_date,
                "기준 시각": self.base_time,
                "안내": self.message,
            }
        )


def read_auth_key(env_file: Path | None = None) -> str:
    key = os.getenv("KMA_AUTH_KEY", "").strip()
    if key or env_file is None or not env_file.exists():
        return key

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() == "KMA_AUTH_KEY":
            return value.strip().strip("\"'")
    return ""


def latest_base_candidates(
    now: datetime | None = None,
    count: int = 6,
) -> list[dict[str, str]]:
    current = now or datetime.now(KST)
    if current.tzinfo is None:
        current = current.replace(tzinfo=KST)
    else:
        current = current.astimezone(KST)

    first = current.replace(minute=30, second=0, microsecond=0)
    if current.minute < 45:
        first -= timedelta(hours=1)

    return [
        {
            "base_date": (first - timedelta(minutes=30 * index)).strftime("%Y%m%d"),
            "base_time": (first - timedelta(minutes=30 * index)).strftime("%H%M"),
        }
        for index in range(count)
    ]


def _items(payload: dict) -> list[dict]:
    item = (
        payload.get("response", {})
        .get("body", {})
        .get("items", {})
        .get("item", [])
    )
    if isinstance(item, dict):
        return [item]
    return item if isinstance(item, list) else []


def validate_payload(payload: dict) -> list[dict]:
    header = payload.get("response", {}).get("header", {})
    result_code = str(header.get("resultCode", ""))
    result_message = str(header.get("resultMsg", "기상청 API 오류"))
    if result_code and result_code != "00":
        raise RuntimeError(f"{result_message} ({result_code})")

    items = _items(payload)
    if not items:
        raise RuntimeError("선택한 기준 시각에 예보 항목이 없습니다.")
    return items


def load_sample_payload(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    validate_payload(payload)
    return payload


def fetch_ultra_short_forecast(
    auth_key: str,
    nx: int,
    ny: int,
    timeout: int = 15,
    session: requests.Session | None = None,
) -> tuple[dict, dict[str, str]]:
    if not auth_key:
        raise RuntimeError("KMA_AUTH_KEY가 저장되어 있지 않습니다.")

    http = session or requests
    errors: list[str] = []
    for base in latest_base_candidates():
        parameters = {
            "pageNo": 1,
            "numOfRows": 1000,
            "dataType": "JSON",
            "base_date": base["base_date"],
            "base_time": base["base_time"],
            "nx": int(nx),
            "ny": int(ny),
            "authKey": auth_key,
        }
        try:
            response = http.get(KMA_API_URL, params=parameters, timeout=timeout)
            if response.status_code != 200:
                raise RuntimeError(f"HTTP {response.status_code}")
            try:
                payload = response.json()
            except ValueError as exc:
                raise RuntimeError("JSON 형식이 아닌 응답을 받았습니다.") from exc
            validate_payload(payload)
            return payload, base
        except (requests.RequestException, RuntimeError) as exc:
            errors.append(f"{base['base_date']} {base['base_time']}: {exc}")

    detail = " | ".join(errors[:3])
    raise RuntimeError(f"최근 예보를 가져오지 못했습니다. {detail}")


def payload_to_long_frame(payload: dict) -> pd.DataFrame:
    frame = pd.DataFrame(validate_payload(payload)).copy()
    frame["forecast_at"] = pd.to_datetime(
        frame["fcstDate"].astype(str) + frame["fcstTime"].astype(str).str.zfill(4),
        format="%Y%m%d%H%M",
    )
    frame["항목"] = frame["category"].map(CATEGORY_LABELS).fillna(frame["category"])
    return frame


def long_to_wide_frame(long_frame: pd.DataFrame) -> pd.DataFrame:
    raw_wide = long_frame.pivot_table(
        index="forecast_at",
        columns="category",
        values="fcstValue",
        aggfunc="first",
    ).reset_index()

    wide = pd.DataFrame({"예보 시각": raw_wide["forecast_at"]})
    wide["기온(°C)"] = pd.to_numeric(raw_wide.get("T1H"), errors="coerce")
    wide["습도(%)"] = pd.to_numeric(raw_wide.get("REH"), errors="coerce")
    wide["풍속(m/s)"] = pd.to_numeric(raw_wide.get("WSD"), errors="coerce")
    wide["1시간 강수량"] = raw_wide.get("RN1", pd.Series(index=raw_wide.index, dtype="object"))
    wide["하늘"] = raw_wide.get("SKY", pd.Series(index=raw_wide.index, dtype="object")).astype(str).map(SKY_LABELS).fillna("확인 필요")
    wide["강수형태"] = raw_wide.get("PTY", pd.Series(index=raw_wide.index, dtype="object")).astype(str).map(PTY_LABELS).fillna("확인 필요")
    return wide


def load_weather_or_sample(
    auth_key: str,
    nx: int,
    ny: int,
    sample_path: Path,
) -> WeatherResult:
    if auth_key:
        try:
            payload, base = fetch_ultra_short_forecast(auth_key, nx, ny)
            return WeatherResult(
                payload=payload,
                source="기상청 초단기예보 API",
                base_date=base["base_date"],
                base_time=base["base_time"],
                message="선택한 격자의 최근 발표 예보를 불러왔습니다.",
            )
        except RuntimeError as exc:
            fallback_message = f"API 응답을 확인하지 못해 샘플 응답을 표시합니다. {exc}"
    else:
        fallback_message = "API 키가 없어 샘플 응답을 표시합니다."

    payload = load_sample_payload(sample_path)
    first_item = _items(payload)[0]
    return WeatherResult(
        payload=payload,
        source="기상청 응답 형식 샘플",
        base_date=str(first_item["baseDate"]),
        base_time=str(first_item["baseTime"]),
        message=fallback_message,
    )
