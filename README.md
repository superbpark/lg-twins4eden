# LG 트윈스 오늘의 경기 ⚾

LG 트윈스의 일일 경기 현황·순위·주요 선수 기록을 보여주는 단일 페이지 웹앱.
매일 아침 8시(KST) KBO 공식 데이터를 자동으로 수집해 갱신한다.

## 구조

```
index.html   화면 뼈대 (데이터 없음, 빈 자리만)
app.js       data.json을 fetch해서 각 카드를 그림
style.css    LG 색(적색·검정) 카드 디자인
data.json    경기 데이터 (자동 생성됨 — 직접 수정 X)
scraper/
  update_data.py   KBO 공식 사이트에서 데이터를 긁어 data.json 생성
.github/workflows/
  update.yml       매일 08:00 KST 스크래퍼 실행 → 커밋 → Pages 자동 배포
```

## 데이터 출처 (모두 KBO 공식)

- 팀 순위 · 최근 10경기 : `/Record/TeamRank/TeamRank.aspx`
- 경기 일정 · 결과       : `/ws/Schedule.asmx/GetScheduleList`
- 타자 · 투수 기록       : `/Record/Player/...Basic1.aspx`

## 로컬에서 실행

```bash
python3 -m http.server 8000     # 그냥 파일 더블클릭은 X (fetch 차단됨)
# http://localhost:8000 접속
```

## 데이터 수동 갱신

```bash
pip install -r requirements.txt
python scraper/update_data.py    # data.json 새로 생성
```
