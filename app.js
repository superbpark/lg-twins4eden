// =============================================
//  로직 층: data.json을 읽어 화면 조각을 그린다
// =============================================

// data.json을 읽어서 자바스크립트 객체로 돌려주는 함수
async function loadData() {
  // 매일 갱신되는 파일이라 캐시를 막아 항상 최신본을 받는다
  const response = await fetch("data.json", { cache: "no-store" });  // ① 파일 요청 (기다림)
  const data = await response.json();          // ② 텍스트 → JS 객체로 변환 (기다림)
  return data;                                 // ③ 완성된 데이터 반환
}

// ---------------------------------------------
//  render 함수들 — 각자 "찾고 → 만들고 → 넣는다"
// ---------------------------------------------

// ① 헤더: 갱신 날짜
function renderHeader(data) {
  // "2026-07-04" → "26.07.04"
  const [y, m, d] = data.updatedAt.split("-");
  const short = `${y.slice(2)}.${m}.${d}`;
  document.getElementById("updated-at").textContent = `${short} 기준`;

  // 푸터: 기준일(데이터 기반) + 출처
  const footer = document.getElementById("footer-note");
  if (footer) {
    footer.textContent = `${short} 기준 · 출처: KBO 공식 기록실 · 네이버 스포츠`;
  }
}

// 이닝별 스코어보드 (원정=위, 홈=아래). 홈팀이 앞서 마지막 회 공격을 안 하면 "X"
function scoreboardHtml(sb) {
  if (!sb || !sb.away || !sb.home) return "";
  const away = sb.away, home = sb.home;
  const n = Math.max(away.innings.length, home.innings.length, 9);
  const head = Array.from({ length: n }, (_, i) => `<th>${i + 1}</th>`).join("");
  const cells = (team, otherLen) =>
    Array.from({ length: n }, (_, i) => {
      if (i < team.innings.length) return `<td>${team.innings[i]}</td>`;
      return `<td class="x">${i < otherLen ? "X" : "-"}</td>`;
    }).join("");
  return `
    <div class="scoreboard-wrap">
      <table class="scoreboard">
        <thead><tr><th class="tname"></th>${head}<th class="rhe">R</th><th class="rhe">H</th><th class="rhe">E</th></tr></thead>
        <tbody>
          <tr><td class="tname">${away.name}</td>${cells(away, home.innings.length)}<td class="rhe r">${away.r}</td><td class="rhe">${away.h}</td><td class="rhe">${away.e}</td></tr>
          <tr><td class="tname">${home.name}</td>${cells(home, away.innings.length)}<td class="rhe r">${home.r}</td><td class="rhe">${home.h}</td><td class="rhe">${home.e}</td></tr>
        </tbody>
      </table>
    </div>`;
}

// 이날의 결정적 장면 (결승타·홈런)
function keyPlaysHtml(plays) {
  if (!plays || !plays.length) return "";
  const rows = plays
    .map(
      (p) =>
        `<div class="play"><span class="play-tag ${p.how === "결승타" ? "win" : ""}">${p.how}</span><span class="play-text">${p.result}</span></div>`
    )
    .join("");
  return `<div class="keyplays"><div class="keyplays-title">이날의 결정적 장면</div>${rows}</div>`;
}

// ② 최근 경기 — 우측이 홈팀(야구 규칙) · 스코어 강조 · 승/세/패 투수
function renderLastGame(game) {
  const box = document.getElementById("last-game-body");
  const title = document.getElementById("last-game-title");

  // 제목에 경기 날짜: "최근 경기 (yy.mm.dd)"
  if (game && game.date) {
    const [y, m, d] = game.date.split("-");
    title.textContent = `최근 경기 (${y.slice(2)}.${m}.${d})`;
  }

  if (!game) {
    box.innerHTML = `<p class="empty">🛌 최근 경기 정보가 없습니다</p>`;
    return;
  }

  // 우측 = 홈팀. game.home 은 "LG가 홈경기인가"를 뜻함
  const LG = "LG Twins";
  const leftName = game.home ? game.opponent : LG;
  const leftScore = game.home ? game.opponentScore : game.teamScore;
  const rightName = game.home ? LG : game.opponent;
  const rightScore = game.home ? game.teamScore : game.opponentScore;

  const label = game.result === "W" ? "승" : (game.result === "L" ? "패" : "무");

  // 승/세/패 투수 — 데이터가 있는 것만 표시 (없으면 정직하게 "준비 중")
  const decisions = [
    ["W", "승", game.winningPitcher],
    ["S", "세", game.savePitcher],
    ["L", "패", game.losingPitcher],
  ].filter(([, , name]) => name);
  const pitchersHtml = decisions.length
    ? `<div class="pitchers">${decisions
        .map(([cls, tag, name]) =>
          `<span class="pit ${cls}"><span class="pit-tag">${tag}</span><span class="pit-name">${name}</span></span>`)
        .join("")}</div>`
    : `<p class="pitchers-empty">투수 기록 준비 중</p>`;

  box.innerHTML = `
    <div class="scoreline">
      <span class="s-team">${leftName}</span>
      <span class="s-score">${leftScore}</span>
      <span class="s-colon">:</span>
      <span class="s-score">${rightScore}</span>
      <span class="s-team">${rightName}</span>
    </div>
    <p class="result-line"><span class="result-badge ${game.result}">${label}</span> · ${game.stadium}</p>
    ${scoreboardHtml(game.scoreBoard)}
    ${pitchersHtml}
    ${keyPlaysHtml(game.keyPlays)}
    <p class="highlight">💥 ${game.highlight}</p>
  `;
}

// KBO 리그 전체 순위표 (LG 행 강조)
function standingsHtml(teams) {
  if (!teams || !teams.length) return "";
  const rows = teams
    .map((t) => {
      const isLG = t.team === "LG";
      const pct = t.winRate.toFixed(3).replace(/^0/, "");
      const gb = t.gamesBehind === "0" ? "-" : t.gamesBehind;
      return `<tr class="${isLG ? "me" : ""}">
        <td class="rk">${t.rank}</td>
        <td class="tm">${t.team}</td>
        <td>${t.wins}</td>
        <td>${t.losses}</td>
        <td>${t.draws}</td>
        <td class="pct">${pct}</td>
        <td class="gb">${gb}</td>
      </tr>`;
    })
    .join("");
  return `
    <div class="standings-wrap">
      <table class="standings">
        <thead><tr><th>순위</th><th class="tm">팀</th><th>승</th><th>패</th><th>무</th><th>승률</th><th>게임차</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

// ③ 시즌 성적 — LG 히어로 + 리그 전체 순위표
function renderSeason(season, standings) {
  const box = document.getElementById("season-body");
  const pct = season.winRate.toFixed(3).replace(/^0/, "");        // .614
  box.innerHTML = `
    <p class="rank">${season.rank}<span class="rank-suffix">위</span></p>
    <p class="season-sum">${season.wins}승 ${season.losses}패 ${season.draws}무 · 승률 ${pct}</p>
    ${standingsHtml(standings)}
  `;
}

// ④ 최근 10경기 — 상대팀 (H/A) 표기 + 제목에 승패무 합계
//    각 칸에 커서를 올리면(모바일은 탭) 날짜·점수·구장 툴팁이 뜬다.
function renderRecentForm(form) {
  const box = document.getElementById("recent-form-body");
  const title = document.getElementById("recent-form-title");

  // 데이터가 없으면 정직하게 안내 (지어내지 않음)
  if (!form || form.length === 0) {
    if (title) title.textContent = "최근 10경기";
    box.innerHTML = `<p class="empty">확인된 데이터가 없습니다</p>`;
    return;
  }

  // 구형("W")·신형({result,opponent,home,...}) 형식 모두 지원
  const games = form.map((g) => (typeof g === "string" ? { result: g } : g));

  // 제목에 승패무 합계: "최근 10경기 (4승 6패)"
  const w = games.filter((g) => g.result === "W").length;
  const l = games.filter((g) => g.result === "L").length;
  const d = games.filter((g) => g.result === "D").length;
  if (title) {
    title.textContent = `최근 10경기 (${w}승 ${l}패${d ? ` ${d}무` : ""})`;
  }

  const kr = (r) => (r === "W" ? "승" : r === "L" ? "패" : "무");
  const cells = games
    .map((g) => {
      const label = g.opponent
        ? `${g.opponent} <span class="ha ${g.home ? "" : "away"}">(${g.home ? "H" : "A"})</span>`
        : "";
      return `<div class="game" tabindex="0">
        <span class="dot ${g.result}">${kr(g.result)}</span>
        ${label ? `<span class="vs">${label}</span>` : ""}
        ${gameTooltip(g)}
      </div>`;
    })
    .join("");
  box.innerHTML = `<div class="form-row">${cells}</div>`;

  // 모바일(호버 없음) 대응: 탭하면 툴팁 토글, 다른 칸을 누르면 닫힘
  box.querySelectorAll(".game").forEach((el) => {
    el.addEventListener("click", (e) => {
      e.stopPropagation();
      const wasOpen = el.classList.contains("show-tip");
      box.querySelectorAll(".game.show-tip").forEach((o) => o.classList.remove("show-tip"));
      if (!wasOpen) el.classList.add("show-tip");
    });
  });
  document.addEventListener("click", () => {
    box.querySelectorAll(".game.show-tip").forEach((o) => o.classList.remove("show-tip"));
  });
}

// 툴팁: "6/27 · 롯데 원정 · 사직  8:7 승" (점수 없으면 있는 정보만)
function gameTooltip(g) {
  if (g.teamScore == null || g.opponentScore == null) {
    // 상세 점수가 없는 구형 데이터는 툴팁 생략
    if (!g.date && !g.stadium) return "";
  }
  const md = g.date
    ? g.date.slice(5).split("-").map((n) => +n).join("/")   // "07-01" → "7/1"
    : "";
  const where = g.opponent ? `${g.opponent} ${g.home ? "홈" : "원정"}` : "";
  const line1 = [md, where, g.stadium].filter(Boolean).join(" · ");

  let line2 = "";
  if (g.teamScore != null && g.opponentScore != null) {
    const won = g.result === "W";
    const rk = won ? "승" : g.result === "L" ? "패" : "무";
    const cls = won ? "tip-win" : g.result === "L" ? "tip-lose" : "";
    line2 = `<div class="tip-score">LG ${g.teamScore} : ${g.opponentScore} <span class="${cls}">${rk}</span></div>`;
  }
  return `<span class="tip">${line1 ? `<div>${line1}</div>` : ""}${line2}</span>`;
}

// ⑤ 주요 선수 — 부문별 타이틀홀더 (⚾ 홈런왕 · 오스틴 · 27홈런)
//    부문 아이콘은 Tabler Icons(MIT)의 라인 SVG를 인라인으로 담아 외부 요청 없이
//    오프라인·다크모드까지 대응한다. 알약(빨강) 안에 흰색으로 표시된다.
const TITLE_ICON_PATHS = {
  홈런왕: [  // 야구공
    "M5.636 18.364a9 9 0 1 0 12.728 -12.728a9 9 0 0 0 -12.728 12.728",
    "M12.495 3.02a9 9 0 0 1 -9.475 9.475", "M20.98 11.505a9 9 0 0 0 -9.475 9.475",
    "M9 9l2 2", "M13 13l2 2", "M11 7l2 1", "M7 11l1 2", "M16 11l1 2", "M11 16l2 1",
  ],
  타율왕: [  // 과녁+화살 (정확도)
    "M11 12a1 1 0 1 0 2 0a1 1 0 1 0 -2 0", "M12 7a5 5 0 1 0 5 5",
    "M13 3.055a9 9 0 1 0 7.941 7.945", "M15 6v3h3l3 -3h-3v-3l-3 3", "M15 9l-3 3",
  ],
  도루왕: [  // 달리는 사람 (스피드)
    "M11.007 5a2 2 0 1 0 4 0a2 2 0 1 0 -4 0", "M4 17l5 1l.75 -1.5",
    "M15 21v-4l-4 -3l1 -6", "M7 12v-3l5 -1l3 3l3 1",
  ],
  다승왕: [  // 트로피
    "M8 21l8 0", "M12 17l0 4", "M7 4l10 0", "M17 4v8a5 5 0 0 1 -10 0v-8",
    "M3 9a2 2 0 1 0 4 0a2 2 0 1 0 -4 0", "M17 9a2 2 0 1 0 4 0a2 2 0 1 0 -4 0",
  ],
  방어율왕: [  // 방패+체크 (실점 방어)
    "M11.46 20.846a12 12 0 0 1 -7.96 -14.846a12 12 0 0 0 8.5 -3a12 12 0 0 0 8.5 3a12 12 0 0 1 -.09 7.06",
    "M15 19l2 2l4 -4",
  ],
  세이브왕: [  // 멈춤 손 (경기 문 닫기)
    "M8 13v-7.5a1.5 1.5 0 0 1 3 0v6.5", "M11 5.5v-2a1.5 1.5 0 1 1 3 0v8.5",
    "M14 5.5a1.5 1.5 0 0 1 3 0v6.5",
    "M17 7.5a1.5 1.5 0 0 1 3 0v8.5a6 6 0 0 1 -6 6h-2h.208a6 6 0 0 1 -5.012 -2.7a69.74 69.74 0 0 1 -.196 -.3c-.312 -.479 -1.407 -2.388 -3.286 -5.728a1.5 1.5 0 0 1 .536 -2.022a1.867 1.867 0 0 1 2.28 .28l1.47 1.47",
  ],
};
// 구형 타이틀 호환: 새 부문 아이콘으로 매핑 (없으면 트로피)
const TITLE_ICON_ALIAS = { 다승: "다승왕", 탈삼진왕: "다승왕", 타점왕: "홈런왕", 최다안타: "타율왕" };

function titleIcon(title) {
  const key = TITLE_ICON_PATHS[title] ? title : (TITLE_ICON_ALIAS[title] || "다승왕");
  const paths = TITLE_ICON_PATHS[key].map((d) => `<path d="${d}" />`).join("");
  return `<svg class="tt-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths}</svg>`;
}

function renderKeyPlayers(players) {
  const box = document.getElementById("key-players-body");

  if (!players || !players.length) {
    box.innerHTML = `<p class="empty">확인된 데이터가 없습니다</p>`;
    return;
  }

  const rows = players
    .map((p) => {
      // 신형({title,name,stat,value})·구형({name,position,stat,value}) 모두 지원
      const title = p.title || p.stat || "";
      return `<div class="tholder">
        <span class="tt">${titleIcon(title)}${title}</span>
        <span class="tn">${p.name}</span>
        <span class="tv">${p.value}<span class="tu">${p.stat}</span></span>
      </div>`;
    })
    .join("");
  box.innerHTML = rows;
}

// ⑥ 다음 경기 — 경기가 없는 날이면 "경기 없음" 표시
function renderNextGame(game) {
  const box = document.getElementById("next-game-body");

  // nextGame이 null이거나 없으면 (월요일·휴식기 등) 경기 없음
  if (!game) {
    box.innerHTML = `<p class="empty">🛌 예정된 경기 없음</p>`;
    return;
  }

  const vs = game.home ? "vs" : "@";
  box.innerHTML = `
    <p class="matchup">${game.date} ${game.time}</p>
    <p>${vs} ${game.opponent} · ${game.stadium}</p>
  `;
}

// ---------------------------------------------
//  main: 데이터 준비 → 6개 render 지휘 → 에러 처리
// ---------------------------------------------
async function main() {
  try {
    const data = await loadData();

    renderHeader(data);
    renderLastGame(data.lastGame);
    renderSeason(data.season, data.standings);
    renderRecentForm(data.recentForm);
    renderKeyPlayers(data.keyPlayers);
    renderNextGame(data.nextGame);
  } catch (err) {
    // 뭐라도 실패하면 여기로 옴
    console.error("데이터를 불러오지 못했어요:", err);
    document.body.innerHTML = "<p style='padding:2rem'>⚠️ 데이터를 불러올 수 없습니다.</p>";
  }
}

main();  // 시작!
