// =============================================
//  로직 층: data.json을 읽어 화면 조각을 그린다
// =============================================

// data.json을 읽어서 자바스크립트 객체로 돌려주는 함수
async function loadData() {
  const response = await fetch("data.json");  // ① 파일 요청 (기다림)
  const data = await response.json();          // ② 텍스트 → JS 객체로 변환 (기다림)
  return data;                                 // ③ 완성된 데이터 반환
}

// ---------------------------------------------
//  render 함수들 — 각자 "찾고 → 만들고 → 넣는다"
// ---------------------------------------------

// ① 헤더: 갱신 날짜
function renderHeader(data) {
  const box = document.getElementById("updated-at");
  box.textContent = `${data.updatedAt} 기준`;
}

// ② 최근 경기
function renderLastGame(game) {
  const box = document.getElementById("last-game-body");
  const vs = game.home ? "vs" : "@";              // 홈이면 vs, 원정이면 @
  const label = game.result === "W" ? "승" : (game.result === "L" ? "패" : "무");

  box.innerHTML = `
    <p class="matchup">${game.date} · ${vs} ${game.opponent} · ${game.stadium}</p>
    <p class="score ${game.result}">
      <span>${game.teamScore} : ${game.opponentScore}</span>
      <span class="result-badge ${game.result}">${label}</span>
    </p>
    <p class="highlight">💥 ${game.highlight}</p>
  `;
}

// ③ 시즌 성적
function renderSeason(season) {
  const box = document.getElementById("season-body");
  box.innerHTML = `
    <p class="rank">${season.rank}위</p>
    <p>${season.wins}승 ${season.losses}패 ${season.draws}무</p>
    <p>승률 ${season.winRate.toFixed(3)}</p>
    <p>게임차 ${season.gamesBehind}</p>
  `;
}

// ④ 최근 경기 흐름 — 배열을 반복해서 승/패 원으로 그림
function renderRecentForm(form) {
  const box = document.getElementById("recent-form-body");

  // 데이터가 없으면 정직하게 안내 (지어내지 않음)
  if (!form || form.length === 0) {
    box.innerHTML = `<p class="empty">확인된 데이터가 없습니다</p>`;
    return;
  }

  const dots = form
    .map((r) => `<span class="dot ${r}">${r === "W" ? "승" : "패"}</span>`)
    .join("");
  box.innerHTML = `<div class="form-row">${dots}</div>`;
}

// ⑤ 주요 선수 — 선수 배열을 반복
function renderKeyPlayers(players) {
  const box = document.getElementById("key-players-body");
  const rows = players
    .map(
      (p) => `
        <div class="player">
          <span class="player-name">${p.name}</span>
          <span class="player-pos">${p.position}</span>
          <span class="player-stat">${p.stat} ${p.value}</span>
        </div>`
    )
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
    renderSeason(data.season);
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
