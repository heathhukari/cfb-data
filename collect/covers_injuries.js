// Run with javascript_tool on https://www.covers.com/sport/football/ncaaf/injuries (built-in browser).
// Returns {school: [[name, pos, status], ...]} for every FBS team (138); status like "Out - Knee" or "Questionable - Ankle".
(() => {
  const out = {};
  document.querySelectorAll('.covers-CoversMatchups-injuryContainer').forEach(c => {
    const img = c.previousElementSibling?.querySelector('img[alt]'), tb = c.querySelector('table');
    if (!img || !tb) return;
    out[img.alt.trim()] = [...tb.querySelectorAll('tbody > tr:not(.collapse)')]
      .map(tr => [...tr.children].slice(0, 3).map(td => td.innerText.replace(/\s+/g, ' ').trim()))
      .filter(r => r.length === 3 && r[1])
      .map(r => [r[0], r[1], r[2].replace(/\s*\(.*$/, '')]);
  });
  return out;
})()
