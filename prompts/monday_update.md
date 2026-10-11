Weekly Monday update for Heath's CFB Top 25 dashboard artifact (formerly "AP Top 25") (https://claude.ai/artifact/3xNnYRHpv5kim7XRkquRdn). It updates ratings, betting lines, conference records and matchup stats. It also grades last week's picks, records and dark horses, writes Claude's projections, runs the rankings engine (Claude's BCS, Claude's Top 25 (poll-free; normally already built early Sunday by the "CFB Sunday pre-AP" task), Dark Horses & Sleepers, CFP brackets, rest-of-season outlook), and freezes this week's picks and best bets.

Use the Claude desktop app's built-in browser (tools named *Claude_Browser__*; load them all with one ToolSearch for that prefix). ESPN's data only loads reliably inside a real browser, so do not use WebFetch for ESPN, Massey or Colley data. Run every fetch() below with javascript_tool on a tab of the same site: espn.com for ESPN APIs, colleyrankings.com for Colley.

For long-running scripts, start them as window.__p = (async()=>{...})().then(v=>window.__out=v).catch(e=>window.__out="ERR "+e.message) and poll window.__out every ~10 seconds so the tool call doesn't time out. The stored scripts in doc code/claude-model are already async IIFEs: set window.__in first, then evaluate window.__p = (<stored text>).then(v=>window.__out=v).catch(e=>window.__out="ERR "+e.message).

For large docs, write the JSON to a local file and pass file_path to ArtifactData. Never "set" over an existing doc without its if_version. Never rename fields or collections.

1. Load ArtifactData via ToolSearch ("select:ArtifactData"). Read the newest docs in "polls" (query order_by sortKey desc, limit 2). Call the newest P (season, week, sortKey, label, through, teams, others) and the one before it prevPoll. Then list "ratings" (order_by sortKey desc, limit 1). If a ratings doc with P's sortKey already exists, skip steps 2-6 (ratings are current), but still do every later step whose output doc is missing for P's sortKey.
2. Open https://www.espn.com/college-football/fpi/_/view/resume in the built-in browser (preview_start). With javascript_tool on that tab run:
   const r = await fetch("https://site.web.api.espn.com/apis/fitt/v3/sports/football/college-football/powerindex?region=us&lang=en&limit=200&season=<season>").then(r=>r.json());
   For each team: fpi = categories "fpi" values, resume = "resume" values.
   Fields: FPI value = fpi[0], FPI rank = fpi[1], projected W = fpi[3], L = fpi[4], playoff % = fpi[8]; SOR rank = resume[1], SOS (to date) rank = resume[2], remaining SOS rank = resume[3].
   Confirm the resume labels via r.categories (expect "FPI","SOR RNK","AVGSOSRNK","REM SOS RNK",...). If they differ, stop with an error report.
   Record r.lastUpdated. Team names are in team.nickname; team.location is empty in this feed.
3. In the same tab, fetch "https://site.api.espn.com/apis/site/v2/sports/football/college-football/rankings?season=<season>" and take the ranking named "AFCA Coaches Poll". Use its ranks (current, previous [0 = unranked], points, firstPlaceVotes) and its "others" with points. Check that its AP poll matches P's top 5. If not, the feed is stale: report that and stop.
   CFP check (from November): if that same response has a ranking whose name contains "Playoff" and its date is newer than the "released" of the newest "cfprank" doc (or no cfprank doc exists), write it as cfprank/<P's doc id> (team names converted with NAMES below; ranks from current, prev from previous with 0 → null, record from recordSummary; set with if_version if it exists): {season, week, sortKey, label "CFP Rankings · <Mon D>", released "YYYY-MM-DD", source "College Football Playoff selection committee via ESPN", updatedAt, teams: [{rank, team (dashboard name), prev (null if unranked last time), record}]}. The Wednesday "CFB Playoff rankings" task normally does this; this is the backup. The dashboard shows the newest CFP ranking as its main ranking (AP stays available).
4. SP+: in the same tab, fetch "https://site.web.api.espn.com/apis/search/v2?query=SP%2B%20college%20football%20rankings&limit=10&type=article". Pick the newest article titled like "<season> college football SP+ rankings for all 138 FBS teams", fetch its HTML, and parse the rows of the FIRST <table>: "N. Team (W-L)" | rating | "off (rk)" | "def (rk)" | "st (rk)" | change (ranks 1-138).
5. CFP projection: search the same API for "College Football Playoff bowl projections <season>". Open the newest "Week N College Football Playoff, bowl projections" article and read each analyst's projected seeds 1-12 (lines like "Bonagura: No. 12 Boise State at No. 5 Texas"). For step 14, also note which quarterfinal bowl the article assigns, the article URL and its date.
   If the official CFP committee rankings are out (November onward), ALSO open https://www.ncaa.com/rankings/football/fbs/college-football-playoff and store those ranks as cfp.official.
6. Build one doc and write it with ArtifactData "set" to collection "ratings", doc_id = P's doc id (e.g. 2026-w07). Shape:
   {season, week, sortKey, label, through (all copied from P), updatedAt (ISO),
    sources: {coaches, fpi, sp, cfp} (short strings naming source and date),
    teams: { "<team name exactly as the dashboard uses it>": {
       coaches: {rank|null, prev|null, points, fpv},
       fpi: {value, rank, sor, sos, remSos, playoffPct, projW, projL},
       sp: {rank, rating, off, offRank, def, defRank, st, stRank, change},
       cfp: {"<analyst last name>": seed, ..., "official": rank (when available)} } } }
   Include every FBS team in the powerindex feed (the rankings engine compares playoff odds week over week, so every team must be present). Teams without an SP+ row get sp null.

NAMES: always convert outside names to the dashboard's names:
- "Miami (FL)" (ESPN "Miami", Massey "Miami FL")
- "Ole Miss" (Colley/Massey "Mississippi")
- "Pittsburgh" ("Pitt")
- "Mississippi State" ("Mississippi St"/"Miss. St.")
- "USC", "BYU"
- "James Madison" (JMU)
- "North Dakota State" ("N Dakota St"/"North Dakota St"/NDSU)
- "San Jose State" ("San José State"/"San Jose St")
- "Hawaii" ("Hawai'i")
- "UTSA" ("UT San Antonio")
- full "State" names for every "X St"
- "NC State"
- "Virginia Tech" ("Va. Tech")
The "teams" collection maps every FBS team's espnId to its dashboard name (field name).

7. BETTING LINES → collection "games", doc_id = P's doc id. Fetch "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard?groups=80&limit=300". This returns the upcoming week; confirm the event dates are after P.through, and record r.week.number as ESPNWEEK.
   For every event where either team is in P's top 25 or P's others-receiving-votes, take from competitions[0]:
   - home/away competitors (team.location or shortDisplayName, mapped to dashboard names)
   - neutralSite
   - odds[0] (DraftKings): details (e.g. "IU -7"), overUnder, moneyline.home/away.close.odds, pointSpread.home.open.line, and total.over.open.line (strip the leading "o")
   - broadcasts: network = the names of the broadcasts with market "national" joined with " / " (if none are national, all broadcast names; null when there are none, e.g. "ESPN", "ABC", "SEC Network", "ESPN+")
   - event.date as kickoff (full ISO timestamp)
   Store each game as
   {id, dateUtc "YYYY-MM-DD", kickoff (ISO), network (string|null), away, home, neutral (bool), line (details or null), total (number|null), mlAway, mlHome (strings like "-305"/"+245", null when "OFF"), openHomeSpread (string like "+9.5" or null), openTotal (number or null), favorite ("home"|"away"|null), homeSpread (number from the home team's perspective: negative when home is favored, e.g. home -3.5 → -3.5; away -7 → 7.0; null when no line)}.
   Derive favorite/homeSpread from details by matching its team abbreviation to the competitor's team.abbreviation.
   Doc: {season, week, sortKey, label (copied from P), source "DraftKings lines via ESPN scoreboard, pulled <date/time ET> (lines move; check before betting)", updatedAt, games: [...]}. Use "set"; if the doc already exists, pass its if_version.
   7b. TV SLATE → collection "slate", doc_id = P's doc id (the dashboard's TV Slate tab). From the SAME scoreboard response, take EVERY event (not just ranked games). For each: {id, kickoff (event.date, full ISO), timeTbd (competitions[0].timeValid === false), neutral, network (same rule as above, null if none), status (event.status.type.state), away/home: {team (dashboard name via the "teams" collection espnId map; else team.location), abbr (team.abbreviation), color ("#" + team.color), alt ("#" + team.alternateColor), rank (curatedRank.current if 1-25, else null), espnId}}. Sort by kickoff. Doc: {season, week, sortKey, label (from P), espnWeek: ESPNWEEK, source "ESPN scoreboard (FBS), national TV listing; pulled <date/time ET>", updatedAt, games}. "set" with if_version if it exists. Never store or draw team logos.
8. CONFERENCE RECORDS → collection "standings", doc_id = P's doc id. Fetch "https://site.api.espn.com/apis/v2/sports/football/college-football/standings?group=80&season=<season>". Walk children[] (each conference; some nest another children[] level) → standings.entries[].
   For each entry take the team name, the "overall" record summary, and the conference record (the stats entry with type "vsconf" / name "vsConf", or the record whose name is the conference).
   Doc: {season, sortKey, source "ESPN standings, pulled <date>", updatedAt, teams: {"<dashboard name>": {conf: "<conference abbreviation>", overall: "W-L", confRecord: "W-L"}}}. Include every FBS team.
9. MATCHUP STATS → collection "matchstats", doc_id = P's doc id. On the espn.com tab run exactly:
   const r = await fetch("https://site.web.api.espn.com/apis/common/v3/sports/football/college-football/statistics/byteam?region=us&lang=en&contentorigin=espn&limit=200&season=<season>&seasontype=2&group=80").then(r=>r.json());
   const rows = r.teams.map(t=>{const own={},opp={}; t.categories.forEach(c=>{ (own[c.name]?opp:own)[c.name]=c.values;});
    const gp=own.general[0]; const plays=(x)=>x.passing[7]+x.rushing[4]+x.passing[13];
    const m={ ppg:own.passing[5], oppg:opp.passing[5], ypg:own.passing[16], oypg:opp.passing[16], ypp:own.passing[1]/plays(own), oypp:opp.passing[1]/plays(opp), rypg:own.rushing[0], orypg:opp.rushing[0], ypc:own.rushing[2], oypc:opp.rushing[2], pypg:own.passing[3], opypg:opp.passing[3], ypa:own.passing[0], oypa:opp.passing[0], cmp:own.passing[8], ocmp:opp.passing[8], third:own.miscellaneous[7], othird:opp.miscellaneous[7], sacksAllowed:own.passing[13]/gp, sacks:opp.passing[13]/gp, take:(opp.passing[12]+own.general[1])/gp, give:(own.passing[12]+opp.general[1])/gp, penyds:own.miscellaneous[5]/gp };
    m.tom = m.take - m.give; return {name:t.team.nickname, gp, m};});
   const lowBetter = new Set(["oppg","oypg","oypp","orypg","oypc","opypg","oypa","ocmp","othird","sacksAllowed","give","penyds"]);
   const keys = Object.keys(rows[0].m);
   for (const k of keys){ const vals=rows.map(x=>x.m[k]); for(const x of rows){ const v=x.m[k]; const better=vals.filter(w=> lowBetter.has(k)? w<v-1e-9 : w>v+1e-9).length; x[k]=[+v.toFixed(2), better+1]; } }
   Then return, for every team in step 7's games (both sides) plus P's top 25, the line "name|gp|" + keys.map(k=>x[k][0]+":"+x[k][1]).join(",").
   Sanity-check two things: rows.length should be about 138, and the category order must be own stats first, opponent stats second (a team's ppg should match its known scoring average).
   Doc shape:
   {season, week (P's week), sortKey, of: rows.length, source "ESPN team stats, all <of> FBS teams, through games of <P.through>; ranks computed across FBS (1 = best)", updatedAt,
    metrics: [["Scoring","ppg","oppg","Points per game"],["Total offense","ypg","oypg","Yards per game"],["Yards per play","ypp","oypp","Yards per play"],["Rushing","rypg","orypg","Rush yards per game"],["Yards per carry","ypc","oypc","Yards per carry"],["Passing","pypg","opypg","Pass yards per game"],["Yards per attempt","ypa","oypa","Yards per pass attempt"],["Completion %","cmp","ocmp","Completion %"],["3rd down %","third","othird","3rd down conversion %"],["Sacks","sacksAllowed","sacks","Sacks per game (allowed on offense / made on defense)"],["Turnovers","give","take","Turnovers per game (lost on offense / forced on defense)"]],
    extra: [["Turnover margin / game","tom"],["Penalty yards / game","penyds"]],
    teams: {"<dashboard name>": {gp, m: {<key>: [value, rank], ...all 24 keys}}},
    comp: <from step 10>, compSource: "ESPN team stats and box-score linescores, through <P.through>"}
10. TEAM MODEL INPUTS. Read doc "code/claude-model" (fields runner, pullTeams, gradeAll, rankings, bestBets, howTo, howToWeekly, howToRankings, record) and follow howToWeekly and howToRankings.
   List "teams" (query limit 300) and build names = {espnId: name} for every doc with an espnId. On the espn.com tab, set window.__in = {season: P.season, names} and evaluate the stored pullTeams text. It returns {teams, lastWeek, lastWeekNo, comp, results, future, meta}. Keep teams, lastWeek, results and future for step 14, and comp for step 9.
   Report any entries in meta.unmatchedSp or meta.missingName. If one is an obvious name variant, add an ALIAS entry in pullTeams with ArtifactData str_replace and rerun.
11. COLLEY & MASSEY (computers for Claude's BCS).
   a. Colley: open https://www.colleyrankings.com/currank.html and read the frame URLs (document.querySelectorAll('frame') .src). The "..._main.html" frame holds the table: fetch() it, convert the HTML to text, and parse rows "N. Team \n rating record". Check that the records match P (e.g. P's No. 1 record). If Colley hasn't updated for P's weekend, use it anyway and note "Colley not yet updated" in the report. Keep the top 70 names in order.
   b. Massey: open https://masseyratings.com/cf/fbs/ratings and get_page_text. Check that "Using games thru <date>" is on or after P.through. Each team block is "Team / Conference / Rec / pct / Δ Rank ...": the rating rank is the integer right after the Δ value. Keep the top 70 names in order.
12. GRADE LAST WEEK. Find the newest "picks" doc with sortKey < P.sortKey that has any pick with result null; call it K. If there is none, skip to step 13.
   Read predictions/<K id>, darkhorses/<K id> and records/<P.season>. On the espn.com tab, set window.__in = {season: P.season, week: K.week (the ESPN week of those games), predGames: predictions.games, picks: K.picks, darkhorses: <that darkhorses doc>, newPoll: P} and evaluate the stored gradeAll text. It returns {predGames, picks, darkhorses, week, allFinal, pending}.
   Write one ArtifactData "batch" of updates, each with if_version:
   - predictions/<K id>: games = predGames
   - picks/<K id>: picks = picks, gradedAt (ISO)
   - darkhorses/<K id>: darkHorses, sleepers
   - records/<season>: weeks = the old weeks array plus this `week` entry (replace any entry with the same week number), updatedAt
   Then compute the season hit rate over every darkhorses doc: darkHorses hits = result.hit true / graded (hit not null); sleepers the same way. Write it as darkhorses/<K id>.record = {darkHorses: "h/n", sleepers: "h/n", through: K.week}.
   If allFinal is false, write what is graded and list the pending game ids in the report. Those picks keep result null, so next Monday's run grades them.
   If there is no such K (the Sunday pre-AP task already graded the picks), still check the newest darkhorses doc with sortKey < P.sortKey: if any darkHorses entry has result.won set but result.hit null, grade it now with P (hit = won && P rank exists && (apRank null || P rank < apRank); newRank = P rank), write darkHorses with if_version, then recompute darkhorses/<that id>.record as above. Also regrade any predictions game in that doc still at result null (e.g. a late game that was in progress Saturday night) with gradeAll and replace that week's entry in records/<season>.
13. CLAUDE'S PROJECTIONS → collection "predictions", doc_id = P's doc id. On the espn.com tab, set window.__cfg = {season: P.season, eventIds: [every game id in step 7's games doc], names: {"<id>": ["<home dashboard name>", "<away dashboard name>"], ...}} and evaluate the stored runner text exactly. It returns {games, meta}.
   Report any entries in meta.unmatchedSp or meta.missing. If one is an obvious name variant, add an ALIAS entry to the runner with str_replace and rerun.
   Then compute the cumulative record over ALL predictions docs' graded games:
   - su = Claude straight-up W-L (result.claudeSU true/false, skip null); espnSu the same way
   - ats = lean W-L-P (result.leanResult); ou = total lean W-L-P (result.totalLeanResult)
   - maeClaude = mean result.claudeErr; maeVegas = mean result.vegasErr (non-null)
   - weeks = "Weeks <first>–<last>"
   Format records as strings like "12-5" or "6-4-1" and MAEs to 1 decimal.
   Write the doc: {season, week, sortKey, label (from P), updatedAt (ISO), model: <the "model" object from the most recent previous predictions doc, with model.sources updated to today's SP+ article date, FPI date and line pull date>, games: <runner games>, record: <cumulative record or null>}.
14. RANKINGS ENGINE → collections "bcs", "top25", "darkhorses", "brackets" and "outlook", each with doc_id = P's doc id.
   Read the newest doc with sortKey < P.sortKey in bcs, top25, darkhorses and ratings. Also read top25/<P id>: if it exists with builtBeforeAP true, it is Claude's locked pre-AP ballot — do NOT overwrite it. Read the newest "altpolls" doc for its Commissioner's Poll (BCS only). Claude's Top 25 uses no poll at all (engine v6, see howToRankings): pass jp: [].
   Evaluate the stored rankings text in node in the workspace (it defines var claudeRankings) and call claudeRankings(input) with:
   {meta: {season, week, sortKey, label, through (from P), updatedAt},
    poll: P, prevPoll,
    coaches: {name: {rank, prev, points, fpv}} (step 3, including teams receiving votes, with rank null),
    colley: [names], massey: [names] (step 11),
    teams: step 10 teams, results: step 10 results, future: step 10 future,
    jp: [], jpMeta: null,
    commish: that altpolls doc's Commissioner's Poll teams [{rank, team}] (polls[] entry key "commissioner", status "ok", even if stale; [] if none), commishMeta: {edition, date, url},
    standings: step 8 teams, predGames: step 13 games, lastWeek: step 10 lastWeek,
    prev: {bcs, top25, darkhorses, ratings} (those previous docs, or null),
    cfp: [one entry per outside bracket: {key ("bonagura", "schlabach", "cbs", ...), name ("ESPN · Bonagura", "CBS · Crawford"), date, url, seeds: [12 dashboard names in seed order], qfSites: {seed: bowl} as the source states it, semis, note}],
    unavailable: "<one line naming any usual source not found this week, or null>"}.
   Outside brackets: the ESPN analysts from step 5, plus CBS Sports' newest "Bowl projections" article (Jerry Palm or Chip Crawford). Read the CBS article in the built-in browser (navigate + get_page_text) and take its 12 seeds and quarterfinal bowl assignments. Never use a bracket older than 8 days or from a previous season. From November, also add {key: "official", name: "CFP committee"} built from the committee's top 12 ordered by the 5+7 seeding rules.
   The engine returns {bcs, top25, darkhorses, bracket, outlook}. Write bcs/<id>, darkhorses/<id>, brackets/<id> and outlook/<id> with "set" in one batch; write top25/<id> ONLY if no builtBeforeAP ballot exists for P (fallback when the Sunday task didn't run; then add builtBeforeAP: false and basis "Built Monday after the AP poll because the Sunday pre-AP build did not run."). Write them unchanged except for a sources string added to bcs naming each input and its date.
15. BEST BETS & FROZEN PICKS → collection "picks", doc_id = P's doc id. If this doc already exists, skip this step: picks are frozen once made.
   On the espn.com tab, set window.__in = {predGames: step 13 games, lines: step 7 games, matchstats: step 9 doc} and evaluate the stored bestBets text. It returns {leans, candidates}.
   Injury check: for each candidate, plus the next 3 qualifying leans, open https://www.covers.com/sport/football/ncaaf/injuries and the CBS Sports college football injuries page in the built-in browser and look for both teams. If a starting QB or 2+ key starters are out or doubtful and the model inputs don't already reflect it, drop that candidate and promote the next qualifier.
   Best bets are the top 5 surviving candidates, one per game. Every lean becomes a pick with:
   - pickId, gameId, away, home, neutral, kickoff, market, side, line, claudeLine, edge, open
   - madeAt (ISO now), bestBet (bool), bestRank (1-5 or null)
   - why: 2-3 sentences built ONLY from that lean's facts (input disagreement vs the line, matchup edges, line move, ESPN predictor), never invented
   - wrongIf: 1-2 sentences from `against` plus the most fragile input
   - close null, clv null, result null, final null
   - notes: an array of {at: ISO, text}. For every checked game add one note: text starting "Injury flag: ..." when something material was found, or exactly "Injury check: nothing material found" when clean. Otherwise [].
   Doc: {season, week: ESPNWEEK, sortKey, label, updatedAt, lineSource "DraftKings via ESPN, pulled <time ET>", injurySource "<pages checked, time>", rules: <copy rules from the previous picks doc>, picks: [...]}.
   Never edit line or madeAt after writing; later information goes in a new note.
16. Read each doc written back once, then report in seven short lines:
   1. Ratings teams written, and any AP-ranked team missing FPI or SP+.
   2. Games with lines, and games in the TV slate (and any with no network yet).
   3. Last week's grading: Claude ATS/O-U/best bets/SU, CLV average, house favorite ATS, ESPN SU, anything pending.
   4. Claude's BCS top 5 and the biggest gap vs AP.
   5. Claude's Top 25 top 5 (and whether it was the Sunday pre-AP ballot or a Monday fallback), the Commissioner's Poll edition used for BCS, the top 3 trending up and down, and the dark horses.
   6. This week's 5 best bets with lines, and any injury drops.
   7. Any source that was unavailable or stale (Colley, Massey, CBS, ESPN projections, Commissioner's Poll).