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
def get_season():
    rows = _table_rows(BASE + "/Record/TeamRank/TeamRank.aspx")
    header = rows[0]
    for row in rows[1:]:
        rec = dict(zip(header, row))
        if rec.get("팀명") == TEAM:
            return {
                "rank": int(rec["순위"]),
                "wins": int(rec["승"]),
                "losses": int(rec["패"]),
                "draws": int(rec["무"]),
                "winRate": float(rec["승률"]),
                "gamesBehind": rec["게임차"],  # "0" 또는 "2.5" (문자열 그대로)
                "recent10": rec.get("최근10경기", ""),
            }
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
# 3) & 4) 선수 기록
# ---------------------------------------------------------------------------
def _lg_players(url):
    rows = _table_rows(url)
    header = rows[0]
    return [dict(zip(header, r)) for r in rows[1:] if dict(zip(header, r)).get("팀명") == TEAM]


def get_key_players():
    hitters = _lg_players(BASE + "/Record/Player/HitterBasic/Basic1.aspx")
    pitchers = _lg_players(BASE + "/Record/Player/PitcherBasic/Basic1.aspx")
    players = []
    picked = set()

    # 홈런 1위 타자
    if hitters:
        hr = max(hitters, key=lambda p: int(p["HR"]))
        players.append({"name": hr["선수명"], "position": "타자",
                        "stat": "홈런", "value": hr["HR"]})
        picked.add(hr["선수명"])

    # 타율 1위 타자 (홈런 1위와 다른 사람)
    for p in sorted(hitters, key=lambda p: float(p["AVG"]), reverse=True):
        if p["선수명"] not in picked:
            players.append({"name": p["선수명"], "position": "타자",
                            "stat": "타율", "value": p["AVG"]})
            break

    # 평균자책 1위 투수
    if pitchers:
        era = min(pitchers, key=lambda p: float(p["ERA"]))
        players.append({"name": era["선수명"], "position": "투수",
                        "stat": "평균자책", "value": era["ERA"]})
    return players


# ---------------------------------------------------------------------------
# 조립
# ---------------------------------------------------------------------------
def build():
    season = get_season()
    games = get_games()
    key_players = get_key_players()

    done = [g for g in games if g["result"] is not None]
    upcoming = [g for g in games if g["result"] is None]

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

    recent_form = [g["result"] for g in done[-10:]]

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
