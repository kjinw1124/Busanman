# 기상청 초단기예보 로컬 웹앱

Notebook에서 확인한 기상청 초단기예보 응답을 Streamlit 화면으로 연결합니다. 자료는 실행 중 메모리에만 머물며, 사용자가 내려받기 버튼을 눌렀을 때 CSV 파일로 저장할 수 있습니다.

## 1. 저장소 폴더로 이동

```bash
cd kma-weather-dashboard
```

## 2. 가상환경 만들기

macOS 또는 Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
```

## 3. 필요한 패키지 설치

```bash
python -m pip install -r requirements.txt
```

## 4. API 키 준비

기상청 APIHub에서 `동네예보(초단기예보) 조회` 활용을 신청하고 인증키를 발급받습니다. 앱을 실행한 뒤 사이드바의 `기상청 API 인증키` 입력란에 키를 넣으면 현재 브라우저 세션에서 실시간 조회를 사용할 수 있습니다.

매번 입력하지 않으려면 `.env.example`을 `.env`라는 이름으로 복사하고, 등호 오른쪽에 준비한 키를 넣습니다.

```text
KMA_AUTH_KEY=
```

이 파일은 화면이나 Git 저장소에 올리지 않습니다. 입력한 키 값은 웹 화면에 표시되지 않습니다.

## 5. 앱 실행

```bash
python -m streamlit run app.py
```

브라우저가 자동으로 열리지 않으면 터미널에 표시된 `http://localhost:8501` 주소를 엽니다.

사이드바에서 `실시간 API`를 선택하면 기상청의 최신 초단기예보를 조회합니다. `최신 데이터 불러오기` 버튼은 캐시를 비우고 즉시 다시 조회하며, 동일한 응답은 5분 동안 캐시됩니다.

`날씨 지도` 탭에서는 선택한 위치를 중심으로 지도를 확대하고, 마커에 기온·습도·풍속·강수 상태를 표시합니다. 지도 배경에는 별도의 지도 API 키가 필요하지 않습니다.

API 키가 아직 없는 경우에는 `샘플 데이터`를 선택해 화면과 CSV 저장 기능을 확인할 수 있습니다. 실시간 API 호출에 실패하면 샘플로 자동 전환하지 않고 오류를 표시하므로 데이터 출처를 명확히 구분할 수 있습니다.

## 파일 구성

- `app.py`: 화면과 사용자 선택
- `kma_client.py`: API 요청, 응답 확인, 표 변환
- `.env`: 개인 API 키를 저장하는 로컬 파일
- `requirements.txt`: 앱 실행에 필요한 Python 패키지

API 문서: https://apihub.kma.go.kr/apiList.do?seqApi=10
