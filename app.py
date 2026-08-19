from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

from kma_client import (
    fetch_ultra_short_forecast,
    load_sample_payload,
    long_to_wide_frame,
    payload_to_long_frame,
    read_auth_key,
)


APP_DIR = Path(__file__).resolve().parent
SAMPLE_PATH = APP_DIR / "data" / "kma_ultra_short_forecast_sample.json"
ENV_PATH = APP_DIR / ".env"
KST = ZoneInfo("Asia/Seoul")
KMA_API_GUIDE_URL = (
    "https://apihub.kma.go.kr/apiList.do?"
    "apiMov=4.%20%EB%8F%99%EB%84%A4%EC%98%88%EB%B3%B4&seqApi=10&seqApiSub=286"
)

LOCATIONS = {
    "울산대학교": {"nx": 101, "ny": 84, "lat": 35.5438, "lon": 129.2563},
    "울산광역시 중심": {"nx": 102, "ny": 84, "lat": 35.5384, "lon": 129.3114},
    "서울광역시 중심": {"nx": 60, "ny": 127, "lat": 37.5665, "lon": 126.9780},
    "부산광역시 중심": {"nx": 98, "ny": 76, "lat": 35.1796, "lon": 129.0756},
}


def weather_symbol(sky: str, precipitation: str) -> str:
    """예보 문자열을 대시보드용 아이콘으로 바꿉니다."""
    if precipitation in {"눈", "눈날림"}:
        return "❄️"
    if precipitation in {"비/눈", "빗방울/눈날림"}:
        return "🌨️"
    if precipitation in {"비", "소나기", "빗방울"}:
        return "🌧️"
    return {"맑음": "☀️", "구름 많음": "⛅", "흐림": "☁️"}.get(sky, "🌦️")


def metric_delta(frame: pd.DataFrame, column: str, unit: str) -> str | None:
    """첫 예보와 다음 예보의 차이를 짧은 문구로 만듭니다."""
    if len(frame) < 2:
        return None
    first_value = frame.iloc[0][column]
    next_value = frame.iloc[1][column]
    if pd.isna(first_value) or pd.isna(next_value):
        return None
    difference = float(next_value) - float(first_value)
    if np.isclose(difference, 0):
        return f"다음 예보 변화 없음"
    return f"다음 예보 {difference:+.1f}{unit}"


def format_base_time(base_date: str, base_time: str) -> str:
    """기상청 기준 시각을 읽기 쉬운 한국어 형식으로 표시합니다."""
    try:
        parsed = pd.to_datetime(f"{base_date}{str(base_time).zfill(4)}", format="%Y%m%d%H%M")
        return parsed.strftime("%Y년 %m월 %d일 %H:%M")
    except ValueError:
        return f"{base_date} {base_time}"


def weather_map(
    location_name: str,
    selected_location: dict[str, float | int],
    current_weather: pd.Series,
    symbol: str,
) -> pdk.Deck:
    """선택 위치와 현재 예보를 강조한 인터랙티브 지도를 만듭니다."""
    points = []
    for name, location in LOCATIONS.items():
        is_selected = name == location_name
        points.append(
            {
                "name": name,
                "lat": location["lat"],
                "lon": location["lon"],
                "fill_color": [36, 137, 255, 235] if is_selected else [92, 108, 132, 115],
                "line_color": [255, 255, 255, 245],
                "radius": 2600 if is_selected else 1200,
                "temperature": f"{current_weather['기온(°C)']:.1f} °C" if is_selected else "—",
                "humidity": f"{current_weather['습도(%)']:.0f} %" if is_selected else "—",
                "wind": f"{current_weather['풍속(m/s)']:.1f} m/s" if is_selected else "—",
                "condition": f"{current_weather['하늘']} · {current_weather['강수형태']}" if is_selected else "등록된 예보 위치",
            }
        )

    point_frame = pd.DataFrame(points)
    selected_frame = point_frame[point_frame["name"] == location_name].copy()
    selected_frame["map_label"] = f"{symbol}  {current_weather['기온(°C)']:.1f}°"

    layers = [
        pdk.Layer(
            "ScatterplotLayer",
            data=selected_frame,
            get_position="[lon, lat]",
            get_radius=9000,
            get_fill_color=[36, 137, 255, 38],
            stroked=False,
            pickable=False,
        ),
        pdk.Layer(
            "ScatterplotLayer",
            data=point_frame,
            get_position="[lon, lat]",
            get_radius="radius",
            get_fill_color="fill_color",
            get_line_color="line_color",
            line_width_min_pixels=2,
            radius_min_pixels=7,
            radius_max_pixels=24,
            stroked=True,
            filled=True,
            pickable=True,
        ),
        pdk.Layer(
            "TextLayer",
            data=selected_frame,
            get_position="[lon, lat]",
            get_text="map_label",
            get_color=[18, 34, 56, 255],
            get_size=18,
            get_pixel_offset=[0, -32],
            font_family="'Apple SD Gothic Neo, Noto Sans KR, sans-serif'",
            font_weight=700,
            get_alignment_baseline="'bottom'",
            billboard=True,
            pickable=False,
        ),
    ]

    return pdk.Deck(
        map_style="https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json",
        initial_view_state=pdk.ViewState(
            latitude=float(selected_location["lat"]),
            longitude=float(selected_location["lon"]),
            zoom=10.6,
            pitch=38,
            bearing=-8,
        ),
        layers=layers,
        tooltip={
            "html": (
                "<div style='font-family: sans-serif; min-width: 170px'>"
                "<b style='font-size: 14px'>{name}</b><br/>"
                "<span style='opacity: .72'>{condition}</span><hr style='opacity: .2'/>"
                "기온 <b>{temperature}</b><br/>"
                "습도 <b>{humidity}</b><br/>"
                "풍속 <b>{wind}</b>"
                "</div>"
            ),
            "style": {
                "backgroundColor": "rgba(14, 27, 45, 0.94)",
                "color": "white",
                "borderRadius": "12px",
                "padding": "10px 12px",
            },
        },
    )


@st.cache_data(ttl=300, show_spinner=False)
def get_weather(auth_key: str, nx: int, ny: int, use_sample: bool):
    if use_sample:
        payload = load_sample_payload(SAMPLE_PATH)
        first_item = payload["response"]["body"]["items"]["item"][0]
        return {
            "payload": payload,
            "source": "기상청 응답 형식 샘플",
            "base_date": str(first_item["baseDate"]),
            "base_time": str(first_item["baseTime"]),
            "message": "샘플 응답으로 화면 구성을 확인하고 있습니다.",
            "retrieved_at": datetime.now(KST),
            "is_live": False,
        }

    if not auth_key:
        raise RuntimeError("기상청 API 인증키를 입력해 주세요.")

    payload, base = fetch_ultra_short_forecast(auth_key, nx, ny)
    return {
        "payload": payload,
        "source": "기상청 초단기예보 API",
        "base_date": base["base_date"],
        "base_time": base["base_time"],
        "message": "기상청 API에서 선택한 격자의 최신 발표 예보를 불러왔습니다.",
        "retrieved_at": datetime.now(KST),
        "is_live": True,
    }


st.set_page_config(
    page_title="초단기 날씨 브리핑",
    page_icon="🌦️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
        :root {
            --weather-ink: #122238;
            --weather-muted: #607086;
            --weather-blue: #1669d4;
            --weather-border: rgba(18, 34, 56, 0.10);
        }
        [data-testid="stAppViewContainer"] {
            background:
                radial-gradient(circle at 86% 4%, rgba(83, 159, 255, 0.12), transparent 25rem),
                linear-gradient(180deg, #f8fbff 0%, #ffffff 34rem);
        }
        [data-testid="stMainBlockContainer"] {
            max-width: 1180px;
            padding-top: 2.4rem;
            padding-bottom: 4rem;
        }
        [data-testid="stSidebar"] {
            border-right: 1px solid var(--weather-border);
        }
        [data-testid="stMetric"] {
            background: rgba(255, 255, 255, 0.86);
            border: 1px solid var(--weather-border);
            border-radius: 18px;
            padding: 1rem 1.1rem;
            box-shadow: 0 10px 28px rgba(24, 72, 120, 0.06);
        }
        [data-testid="stMetricLabel"] { color: var(--weather-muted); }
        [data-testid="stMetricValue"] { color: var(--weather-ink); }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-color: var(--weather-border);
            border-radius: 22px;
            background: rgba(255, 255, 255, 0.78);
            box-shadow: 0 14px 38px rgba(24, 72, 120, 0.06);
        }
        .weather-eyebrow {
            color: var(--weather-blue);
            font-size: 0.78rem;
            font-weight: 800;
            letter-spacing: 0.13em;
            margin-bottom: 0.35rem;
        }
        .weather-title {
            color: var(--weather-ink);
            font-size: clamp(2rem, 4vw, 3.25rem);
            font-weight: 800;
            letter-spacing: -0.045em;
            line-height: 1.08;
            margin: 0;
        }
        .weather-lead {
            color: var(--weather-muted);
            font-size: 1.02rem;
            line-height: 1.7;
            margin: 0.7rem 0 1.6rem;
        }
        .weather-now {
            align-items: center;
            display: flex;
            gap: 1rem;
        }
        .weather-icon {
            align-items: center;
            background: linear-gradient(145deg, #ecf6ff, #ffffff);
            border: 1px solid rgba(22, 105, 212, 0.12);
            border-radius: 22px;
            display: flex;
            font-size: 3.25rem;
            height: 90px;
            justify-content: center;
            width: 90px;
        }
        .weather-place { color: var(--weather-ink); font-size: 1.45rem; font-weight: 800; }
        .weather-condition { color: var(--weather-muted); margin-top: 0.25rem; }
        .source-badge {
            background: #eaf4ff;
            border-radius: 999px;
            color: #135aa9;
            display: inline-block;
            font-size: 0.78rem;
            font-weight: 750;
            margin-top: 0.65rem;
            padding: 0.35rem 0.65rem;
        }
        @media (max-width: 720px) {
            [data-testid="stMainBlockContainer"] { padding-top: 1.4rem; }
            .weather-icon { font-size: 2.6rem; height: 74px; width: 74px; }
            .weather-place { font-size: 1.2rem; }
        }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="weather-eyebrow">KMA NOWCAST</div>', unsafe_allow_html=True)
st.markdown('<h1 class="weather-title">오늘의 날씨를<br>한눈에 확인하세요.</h1>', unsafe_allow_html=True)
st.markdown(
    '<p class="weather-lead">기상청 초단기예보를 바탕으로 가까운 시간의 기온, 습도, 바람과 강수 정보를 정리합니다.</p>',
    unsafe_allow_html=True,
)

saved_auth_key = read_auth_key(ENV_PATH)
st.sidebar.markdown("## 🌦️ 예보 설정")
st.sidebar.caption("위치와 데이터 소스를 선택하세요.")
location_name = st.sidebar.selectbox("확인할 위치", list(LOCATIONS), help="기상청 격자 좌표가 등록된 위치입니다.")
selected_location = LOCATIONS[location_name]
data_source = st.sidebar.radio(
    "데이터 소스",
    ["실시간 API", "샘플 데이터"],
    index=0 if saved_auth_key else 1,
    help="실시간 API는 기상청에서 현재 이용 가능한 최신 발표 자료를 조회합니다.",
)
use_sample = data_source == "샘플 데이터"

session_auth_key = st.sidebar.text_input(
    "기상청 API 인증키",
    type="password",
    placeholder="APIHub에서 발급한 인증키",
    help="입력한 값은 현재 브라우저 세션에서만 사용되며 화면에 표시되지 않습니다.",
    disabled=use_sample,
)
auth_key = session_auth_key.strip() or saved_auth_key

refresh_clicked = st.sidebar.button(
    "최신 데이터 불러오기",
    icon=":material/refresh:",
    type="primary",
    width="stretch",
    disabled=use_sample or not bool(auth_key),
)
if refresh_clicked:
    get_weather.clear()

st.sidebar.link_button(
    "기상청 API 키 발급 안내",
    KMA_API_GUIDE_URL,
    icon=":material/open_in_new:",
    width="stretch",
)

with st.sidebar.container(border=True):
    st.markdown("**연결 상태**")
    if not use_sample and auth_key:
        st.success("실시간 API 모드", icon="🟢")
    elif not use_sample:
        st.warning("API 인증키가 필요합니다.", icon="🔑")
    else:
        st.info("샘플 데이터 모드입니다.", icon="🧪")
    st.caption(f"격자 좌표 · nx {selected_location['nx']} / ny {selected_location['ny']}")

try:
    with st.spinner("기상청 최신 예보를 불러오고 있습니다…"):
        weather = get_weather(
            auth_key,
            selected_location["nx"],
            selected_location["ny"],
            use_sample,
        )
except RuntimeError as exc:
    st.error("실시간 날씨 데이터를 불러오지 못했습니다.", icon="⚠️")
    st.write(str(exc))
    st.info("인증키와 네트워크 상태를 확인한 뒤 **최신 데이터 불러오기**를 눌러 주세요.")
    st.stop()

long_frame = payload_to_long_frame(weather["payload"])
forecast = long_to_wide_frame(long_frame)

first = forecast.iloc[0]
symbol = weather_symbol(str(first["하늘"]), str(first["강수형태"]))
forecast_end = forecast["예보 시각"].max().strftime("%m월 %d일 %H:%M")

with st.container(border=True):
    summary_left, summary_right = st.columns([1.5, 1], vertical_alignment="center")
    with summary_left:
        st.markdown(
            f"""
            <div class="weather-now">
                <div class="weather-icon">{symbol}</div>
                <div>
                    <div class="weather-place">{location_name}</div>
                    <div class="weather-condition">{first['하늘']} · 강수 {first['강수형태']}</div>
                    <div class="source-badge">{'LIVE · ' if weather['is_live'] else ''}{weather['source']}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with summary_right:
        st.markdown("**발표 기준**")
        st.write(format_base_time(weather["base_date"], weather["base_time"]))
        retrieved_at = weather["retrieved_at"].strftime("%H:%M:%S")
        st.caption(f"{weather['message']} · {forecast_end}까지 제공")
        st.caption(f"마지막 조회 {retrieved_at} KST · 5분 캐시")

st.write("")
metric_columns = st.columns(4)
metric_columns[0].metric(
    "기온",
    f"{first['기온(°C)']:.1f} °C",
    metric_delta(forecast, "기온(°C)", " °C"),
    border=False,
)
metric_columns[1].metric(
    "습도",
    f"{first['습도(%)']:.0f} %",
    metric_delta(forecast, "습도(%)", " %p"),
    border=False,
)
metric_columns[2].metric(
    "풍속",
    f"{first['풍속(m/s)']:.1f} m/s",
    metric_delta(forecast, "풍속(m/s)", " m/s"),
    border=False,
)
metric_columns[3].metric("1시간 강수량", str(first["1시간 강수량"]), border=False)

map_tab, overview_tab, table_tab, raw_tab = st.tabs(
    ["🗺️ 날씨 지도", "📈 한눈에 보기", "🗓️ 시간별 예보", "🔎 원본 항목"]
)

chart_frame = forecast.set_index("예보 시각")
with map_tab:
    map_heading, map_status = st.columns([3, 1], vertical_alignment="center")
    with map_heading:
        st.subheader("지도에서 보는 현재 예보")
        st.caption("마커를 가리키면 선택한 지점의 날씨 정보를 확인할 수 있습니다.")
    with map_status:
        st.markdown(
            f"<div class='source-badge'>{'LIVE MAP' if weather['is_live'] else 'SAMPLE MAP'}</div>",
            unsafe_allow_html=True,
        )

    st.pydeck_chart(
        weather_map(location_name, selected_location, first, symbol),
        width="stretch",
        height=500,
    )

    map_details = st.columns(4)
    map_details[0].caption("선택 위치")
    map_details[0].markdown(f"**{location_name}**")
    map_details[1].caption("위도 · 경도")
    map_details[1].markdown(f"**{selected_location['lat']:.4f}, {selected_location['lon']:.4f}**")
    map_details[2].caption("기상청 격자")
    map_details[2].markdown(f"**nx {selected_location['nx']} · ny {selected_location['ny']}**")
    map_details[3].caption("예보 범위")
    map_details[3].markdown(f"**{forecast_end}까지**")

with overview_tab:
    st.subheader("시간대별 변화")
    st.caption("가장 가까운 예보 시각부터 지표가 어떻게 달라지는지 확인하세요.")
    chart_left, chart_right = st.columns(2)
    with chart_left:
        with st.container(border=True):
            st.markdown("#### 기온")
            st.line_chart(chart_frame[["기온(°C)"]], color="#ff7a45", height=260)
    with chart_right:
        with st.container(border=True):
            st.markdown("#### 습도")
            st.line_chart(chart_frame[["습도(%)"]], color="#2f80ed", height=260)
    with st.container(border=True):
        st.markdown("#### 풍속")
        st.line_chart(chart_frame[["풍속(m/s)"]], color="#20a486", height=240)

with table_tab:
    table_header, table_action = st.columns([3, 1], vertical_alignment="center")
    with table_header:
        st.subheader("시간별 상세 예보")
        st.caption(f"총 {len(forecast)}개 시각의 예보입니다.")
    csv_bytes = forecast.to_csv(index=False).encode("utf-8-sig")
    with table_action:
        st.download_button(
            "CSV로 저장",
            data=csv_bytes,
            file_name="kma_ultra_short_forecast.csv",
            mime="text/csv",
            icon=":material/download:",
            type="primary",
            width="stretch",
        )
    st.dataframe(
        forecast,
        width="stretch",
        hide_index=True,
        column_config={
            "예보 시각": st.column_config.DatetimeColumn("예보 시각", format="MM월 DD일 HH:mm"),
            "기온(°C)": st.column_config.NumberColumn("기온", format="%.1f °C"),
            "습도(%)": st.column_config.NumberColumn("습도", format="%.0f %%"),
            "풍속(m/s)": st.column_config.NumberColumn("풍속", format="%.1f m/s"),
        },
    )

with raw_tab:
    st.subheader("기상청 원본 항목")
    st.caption("학습 및 응답 구조 확인을 위한 원본 형태입니다.")
    st.dataframe(
        long_frame[["forecast_at", "category", "항목", "fcstValue", "nx", "ny"]],
        width="stretch",
        hide_index=True,
        column_config={
            "forecast_at": st.column_config.DatetimeColumn("예보 시각", format="YYYY-MM-DD HH:mm"),
            "category": "항목 코드",
            "fcstValue": "예보 값",
        },
    )

st.divider()
footer_left, footer_right = st.columns([2, 1])
with footer_left:
    st.caption("자료 · 기상청 APIHub 초단기예보 조회서비스")
with footer_right:
    st.caption("실시간 API 데이터는 5분 동안 캐시됩니다.")
