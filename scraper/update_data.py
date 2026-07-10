"""
LG 트윈스 일일 데이터 자동 수집기.

KBO 공식 사이트에서 순위·일정·선수기록을 긁어 data.json을 생성한다.
매일 아침 GitHub Actions가 이 스크립트를 실행한다.

데이터 소스 (모두 공식 koreabaseball.com):
  1) 팀 순위  : GET  /Record/TeamRank/TeamRank.aspx        → 순위/승패/최근10경기
  2) 일정     : POST /ws/Schedule.asmx/GetScheduleList     → 최근경기/다음경기/폼
  3) 타자 기록: GET  /Record/Player/HitterBasic/Basic1.aspx → 주요 타자
  4) 투수 기록: GET  /Record/Player/PitcherBasic/Basic1.aspx→ 주요 투수
"""
import re
import json
import sys
import datetime
import requests
from bs4 import BeautifulSoup

TEAM = "LG"
TEAM_FULL = "LG 트윈스"
SEASON = str(datetime.date.today().year)

BASE = "https://www.koreabaseball.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Referer": BASE + "/Schedule/Schedule.aspx",
}

# 홈팀 → 홈 구장 (구장 셀 파싱 실패 시 폴백)
HOME_STADIUM = {
    "LG": "잠실", "두산": "잠실", "키움": "고척", "한화": "대전",
    "삼성": "대구", "롯데": "사직", "KIA": "광주", "SSG": "문학",
    "KT": "수원", "NC": "창원",
}
KNOWN_STADIUMS = set(HOME_STADIUM.values()) | {"청주", "울산", "포항", "창원"}

# 팀 풀네임 (표시용)
FULL_NAME = {
    "LG": "LG 트윈스", "두산": "두산 베어스", "키움": "키움 히어로즈",
    "한화": "한화 이글스", "삼성": "삼성 라이온즈", "롯데": "롯데 자이언츠",
    "KIA": "KIA 타이거즈", "SSG": "SSG 랜더스", "KT": "KT 위즈", "NC": "NC 다이노스",
}


def _table_rows(url):
    """페이지의 첫 데이터 테이블을 행 단위 문자열 리스트로 반환."""
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    table = soup.find("table")
    out = []
    for tr in table.find_all("tr"):
        cells = [c.get_text(strip=True) for c in tr.find_all(["th", "td"])]
        if cells:
            out.append(cells)
    return out


# ---------------------------------------------------------------------------
# 1) 팀 순위
# ---------------------------------------------------------------------------
def get_standings():
    """KBO 팀 순위표 → 10개 구단 전체를 순위순 리스트로 반환."""
    rows = _table_rows(BASE + "/Record/TeamRank/TeamRank.aspx")
    header = rows[0]
    teams = []
    for row in rows[1:]:
        rec = dict(zip(header, row))
        if not rec.get("팀명"):
            continue
        teams.append({
            "rank": int(rec["순위"]),
            "team": rec["팀명"],
            "games": int(rec["경기"]),
            "wins": int(rec["승"]),
            "losses": int(rec["패"]),
            "draws": int(rec["무"]),
            "winRate": float(rec["승률"]),
            "gamesBehind": rec["게임차"],  # "0" 또는 "1.5" (문자열 그대로)
            "streak": rec.get("연속", ""),
            "recent10": rec.get("최근10경기", ""),
        })
    return teams


def get_season(standings=None):
    """순위표에서 LG 정보를 뽑는다. standings 를 넘기면 재요청하지 않는다."""
    for t in (standings or get_standings()):
        if t["team"] == TEAM:
            return t
    raise RuntimeError(f"순위표에서 {TEAM}을 찾지 못함")


# ---------------------------------------------------------------------------
# 2) 일정
# ---------------------------------------------------------------------------
def _fetch_month(month):
    url = BASE + "/ws/Schedule.asmx/GetScheduleList"
    data = {
        "leId": "1", "srIdList": "0,9,6",
        "seasonId": SEASON, "gameMonth": f"{month:02d}", "teamId": "",
    }
    r = requests.post(url, headers=HEADERS, data=data, timeout=20)
    r.raise_for_status()
    return r.json().get("rows", [])


def _parse_play(html):
    """play 셀 HTML → (away, home, away_score, home_score). 점수 없으면 None."""
    soup = BeautifulSoup(html, "html.parser")
    top_spans = [c for c in soup.children if getattr(c, "name", None) == "span"]
    if len(top_spans) < 2:
        return None
    away = top_spans[0].get_text(strip=True)
    home = top_spans[-1].get_text(strip=True)
    nums = [int(t) for t in re.findall(r">(\d+)<", html)]
    if len(nums) >= 2:
        return away, home, nums[0], nums[1]
    return away, home, None, None


def get_games():
    """LG의 완료·예정 경기 목록을 날짜순으로 반환."""
    today = datetime.date.today()
    months = {today.month}
    if today.month > 1:
        months.add(today.month - 1)  # 최근10경기 확보용 전월 포함

    games = []
    cur_date = None
    for m in sorted(months):
        for r in _fetch_month(m):
            cells = r["row"]
            day = next((c["Text"] for c in cells if c["Class"] == "day"), None)
            if day:
                mm, dd = re.match(r"(\d+)\.(\d+)", day).groups()
                cur_date = datetime.date(int(SEASON), int(mm), int(dd))
            play = next((c for c in cells if c["Class"] == "play"), None)
            if not play or TEAM not in play["Text"]:
                continue
            parsed = _parse_play(play["Text"])
            if not parsed:
                continue
            away, home, a_sc, h_sc = parsed
            is_home = (home == TEAM)
            opp = away if is_home else home
            time = next((re.sub("<[^>]+>", "", c["Text"]) for c in cells
                         if c["Class"] == "time"), "")
            stadium = next((c["Text"] for c in cells
                            if c["Text"] in KNOWN_STADIUMS), HOME_STADIUM.get(home, ""))

            g = {"date": cur_date, "opponent": opp, "home": is_home,
                 "stadium": stadium, "time": time}
            if a_sc is not None:  # 완료 경기
                g["teamScore"] = h_sc if is_home else a_sc
                g["opponentScore"] = a_sc if is_home else h_sc
                if g["teamScore"] > g["opponentScore"]:
                    g["result"] = "W"
                elif g["teamScore"] < g["opponentScore"]:
                    g["result"] = "L"
                else:
                    g["result"] = "D"
            else:
                g["result"] = None
            games.append(g)

    games.sort(key=lambda x: x["date"])
    return games


# ---------------------------------------------------------------------------
# 3) & 4) 주요 선수 — 부문별 '타이틀홀더' (네이버 시즌기록: 전체 로스터)
#    KBO 규정 리더보드엔 규정 미달 선수(마무리 투수 등)가 빠지고 도루 컬럼도
#    없어서, 도루왕·세이브왕까지 담으려면 전체 로스터가 필요 → 네이버 시즌기록 사용.
#    엔드포인트: statistics/categories/kbo/seasons/{year}/players?playerType=HITTER|PITCHER
# ---------------------------------------------------------------------------
# (표기, 타자/투수, 네이버키, 단위, 규정타석·이닝 충족자만, 낮을수록 1위)
#  · 타율(hitterHra)·방어율(pitcherEra)은 규정 미달 선수의 소표본 착시를 막으려
#    isQualified=True인 선수만 대상으로 한다. 방어율은 값이 낮을수록 1위.
KEY_PLAYER_CATEGORIES = [
    ("홈런왕",   "HITTER",  "hitterHr",    "홈런",   False, False),
    ("타율왕",   "HITTER",  "hitterHra",   "타율",   True,  False),
    ("도루왕",   "HITTER",  "hitterSb",    "도루",   False, False),
    ("다승왕",   "PITCHER", "pitcherWin",  "승",     False, False),
    ("방어율왕", "PITCHER", "pitcherEra",  "방어율", True,  True),
    ("세이브왕", "PITCHER", "pitcherSave", "세이브", False, False),
]


def _fmt_stat(key, v):
    """부문별 값 표기. 타율은 .339, 방어율은 3.78, 그 외 카운팅 스탯은 정수."""
    if key == "hitterHra":
        return f"{v:.3f}".lstrip("0") or ".000"   # 0.339 → .339
    if key == "pitcherEra":
        return f"{v:.2f}"                          # 3.7762 → 3.78
    return str(int(v))


def _lg_roster(player_type):
    """네이버 시즌기록에서 LG 전체 선수(playerId로 중복 제거). player_type: HITTER/PITCHER."""
    url = (f"{NAVER}/statistics/categories/kbo/seasons/{SEASON}/players"
           f"?playerType={player_type}&pageSize=500")
    lg = {}
    for p in _naver(url)["seasonPlayerStats"]:
        if p.get("teamName") == TEAM:
            lg[p["playerId"]] = p
    return list(lg.values())


def get_key_players():
    """요청된 6개 부문의 팀 내 1위(타이틀홀더)를 정의 순서대로 반환.

    각 부문의 '진짜' 1위를 그대로 싣는다. 한 선수가 여러 부문 1위면
    (예: 오스틴=홈런왕·타율왕) 각 부문에 중복 표시된다 — 사실 그대로가 우선.
    타율·방어율은 규정 충족자만, 방어율은 최솟값이 1위.
    """
    pool = {"HITTER": _lg_roster("HITTER"), "PITCHER": _lg_roster("PITCHER")}

    def num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    picked = []
    for title, side, key, unit, qualified, lowest in KEY_PLAYER_CATEGORIES:
        cand = [p for p in pool[side]
                if num(p.get(key)) is not None
                and (p.get("isQualified") if qualified else True)]
        if not cand:
            continue
        best = (min if lowest else max)(cand, key=lambda p: num(p.get(key)))
        picked.append({
            "title": title,
            "name": best["playerName"],
            "stat": unit,
            "value": _fmt_stat(key, num(best.get(key))),
        })
    return picked


# ---------------------------------------------------------------------------
# 5) 승·세·패 투수 (네이버 스포츠 경기기록 API — JSON, OCR 불필요)
#    · 경기목록: schedule/games?...&fromDate&toDate  → LG 경기의 gameId
#    · 경기기록: schedule/games/{gameId}/record      → pitchingResult[].wls (W/S/L)
# ---------------------------------------------------------------------------
NAVER = "https://api-gw.sports.naver.com"
NAVER_HEADERS = {
    "User-Agent": HEADERS["User-Agent"],
    "Referer": "https://m.sports.naver.com/",
}


def _naver(url):
    r = requests.get(url, headers=NAVER_HEADERS, timeout=20)
    r.raise_for_status()
    return r.json()["result"]


def _lg_result_games_on(date_iso):
    """네이버 기준 해당 날짜 LG '종료(RESULT)' 경기들의 (LG득점, 상대득점) 집합.

    진행 중 경기를 완료로 오인하지 않도록, '이 경기가 진짜 끝났는지' 판정에 쓴다.
    """
    url = (f"{NAVER}/schedule/games?fields=basic,schedule,baseball"
           f"&upperCategoryId=kbaseball&categoryId=kbo"
           f"&fromDate={date_iso}&toDate={date_iso}")
    finals = set()
    for g in _naver(url)["games"]:
        if TEAM not in (g["homeTeamCode"], g["awayTeamCode"]):
            continue
        if g["statusCode"] != "RESULT" or g.get("cancel"):
            continue
        is_home = g["homeTeamCode"] == TEAM
        ts = g["homeTeamScore"] if is_home else g["awayTeamScore"]
        os_ = g["awayTeamScore"] if is_home else g["homeTeamScore"]
        finals.add((ts, os_))
    return finals


# 결정적 장면으로 뽑을 기록 종류 (etcRecords 의 how 값)
KEY_PLAY_TYPES = ("결승타", "홈런")


def get_last_game_detail(date_iso, team_score, opp_score):
    """해당 날짜 LG 경기의 승/세/패 투수 + 이닝별 스코어보드 + 결정적 장면을 반환.

    조회 실패 시 각 값은 None/빈 값으로 둔다(지어내지 않음).
    세이브는 세이브 상황이 아니면 실제로 기록되지 않으므로 None이 정상이다.
    """
    out = {"winningPitcher": None, "savePitcher": None, "losingPitcher": None,
           "scoreBoard": None, "keyPlays": []}
    try:
        url = (f"{NAVER}/schedule/games?fields=basic,schedule,baseball"
               f"&upperCategoryId=kbaseball&categoryId=kbo"
               f"&fromDate={date_iso}&toDate={date_iso}")
        games = [g for g in _naver(url)["games"]
                 if TEAM in (g["homeTeamCode"], g["awayTeamCode"])
                 and g["statusCode"] == "RESULT"]
        if not games:
            return out

        # 더블헤더 대비: LG 득점·실점이 일치하는 경기를 우선 선택, 없으면 첫 경기
        def lg_scores(g):
            if g["homeTeamCode"] == TEAM:
                return g["homeTeamScore"], g["awayTeamScore"]
            return g["awayTeamScore"], g["homeTeamScore"]

        match = next((g for g in games if lg_scores(g) == (team_score, opp_score)),
                     games[0])
        rd = _naver(f"{NAVER}/schedule/games/{match['gameId']}/record")["recordData"]

        # 승·세·패 투수
        by_wls = {p.get("wls"): p.get("name")
                  for p in rd.get("pitchingResult", [])}
        out["winningPitcher"] = by_wls.get("W")
        out["savePitcher"] = by_wls.get("S")
        out["losingPitcher"] = by_wls.get("L")

        # 이닝별 스코어보드 (rheb = R·H·E, inn = 이닝별 득점)
        sb = rd.get("scoreBoard") or {}
        rheb, inn = sb.get("rheb"), sb.get("inn")
        if rheb and inn:
            out["scoreBoard"] = {
                "away": {"name": match["awayTeamName"], "innings": inn.get("away", []),
                         "r": rheb["away"]["r"], "h": rheb["away"]["h"], "e": rheb["away"]["e"]},
                "home": {"name": match["homeTeamName"], "innings": inn.get("home", []),
                         "r": rheb["home"]["r"], "h": rheb["home"]["h"], "e": rheb["home"]["e"]},
            }

        # 결정적 장면 (결승타·홈런)
        out["keyPlays"] = [{"how": r["how"], "result": r["result"]}
                           for r in rd.get("etcRecords", [])
                           if r.get("how") in KEY_PLAY_TYPES and r.get("result")]
    except Exception as e:
        print("경기 상세(투수/스코어보드/결정장면) 조회 실패:", e, file=sys.stderr)
    return out


# ---------------------------------------------------------------------------
# 조립
# ---------------------------------------------------------------------------
def build():
    standings = get_standings()
    season = get_season(standings)
    games = get_games()
    key_players = get_key_players()

    done = [g for g in games if g["result"] is not None]
    upcoming = [g for g in games if g["result"] is None]

    # 진행 중 경기 가드: KBO 일정은 진행 중인 오늘 경기도 (부분)점수와 함께 노출해
    # '완료'로 오인될 수 있다. 오늘 날짜 경기는 네이버가 RESULT로 확정한 것만 인정하고,
    # 아니면 직전 완료 경기를 최근 경기로 사용한다. (정규 08:00 KST 실행엔 영향 없음)
    today = datetime.date.today()
    while done and done[-1]["date"] == today:
        g = done[-1]
        try:
            finals = _lg_result_games_on(g["date"].isoformat())
        except Exception:
            finals = None  # 네이버 조회 실패 → 판단 보류(그대로 사용)
        if finals is None or (g["teamScore"], g["opponentScore"]) in finals:
            break
        done.pop()  # 오늘 경기인데 네이버 미종료 → 진행 중으로 보고 제외

    # 최근 경기
    last = done[-1] if done else None
    last_game = None
    if last:
        place = "홈" if last["home"] else "원정"
        res_kr = {"W": "승리", "L": "패배", "D": "무승부"}[last["result"]]
        last_game = {
            "date": last["date"].isoformat(),
            "opponent": FULL_NAME.get(last["opponent"], last["opponent"]),
            "home": last["home"],
            "teamScore": last["teamScore"],
            "opponentScore": last["opponentScore"],
            "result": last["result"],
            "stadium": last["stadium"],
            "highlight": f"{place} {last['opponent']}전 "
                         f"{last['teamScore']}-{last['opponentScore']} {res_kr}",
        }
        # 승·세·패 투수 + 스코어보드 + 결정적 장면 (네이버 경기기록).
        # 실패해도 나머지 데이터는 정상 생성.
        last_game.update(
            get_last_game_detail(last_game["date"],
                                 last["teamScore"], last["opponentScore"])
        )

    # 다음 경기 (없으면 null → 화면에 "경기 없음")
    today = datetime.date.today()
    nxt = next((g for g in upcoming if g["date"] >= today), None)
    next_game = None
    if nxt:
        next_game = {
            "date": nxt["date"].isoformat(),
            "opponent": FULL_NAME.get(nxt["opponent"], nxt["opponent"]),
            "home": nxt["home"],
            "stadium": nxt["stadium"],
            "time": nxt["time"],
        }

    recent_form = [
        {"result": g["result"], "opponent": g["opponent"], "home": g["home"],
         "date": g["date"].isoformat(), "stadium": g["stadium"],
         "teamScore": g["teamScore"], "opponentScore": g["opponentScore"]}
        for g in done[-10:]
    ]

    data = {
        "team": TEAM_FULL,
        "updatedAt": today.isoformat(),
        "season": {
            "rank": season["rank"],
            "wins": season["wins"],
            "losses": season["losses"],
            "draws": season["draws"],
            "winRate": season["winRate"],
            "gamesBehind": season["gamesBehind"],
        },
        "standings": standings,
        "lastGame": last_game,
        "recentForm": recent_form,
        "nextGame": next_game,
        "keyPlayers": key_players,
    }
    return data


def main():
    data = build()
    # 최소 검증: 핵심 필드가 비면 실패 처리 (깨진 data.json 배포 방지)
    assert data["season"]["wins"] >= 0, "순위 파싱 실패"
    assert data["lastGame"], "최근 경기 파싱 실패"
    assert data["keyPlayers"], "선수 기록 파싱 실패"

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("data.json 갱신 완료:", json.dumps(data, ensure_ascii=False)[:200], "...")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("스크래퍼 실패:", e, file=sys.stderr)
        sys.exit(1)
