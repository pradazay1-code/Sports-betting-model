"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  type Bet, type BetResult, newBet, loadBets, saveBets, summarize, toCSV,
  betProfit, betClvPts,
} from "../../lib/betlog";

const RESULTS: BetResult[] = ["pending", "win", "loss", "push", "void"];
const num = (v: string): number | null => (v.trim() === "" ? null : Number(v));
const f = (v: number | null | undefined, d = 2, plus = false) =>
  v == null || Number.isNaN(v) ? "—" : `${plus && v > 0 ? "+" : ""}${v.toFixed(d)}`;

export default function LogPage() {
  const [bets, setBets] = useState<Bet[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [storageOk, setStorageOk] = useState(true);
  const [draft, setDraft] = useState(() => newBet());

  useEffect(() => {
    setBets(loadBets());
    setLoaded(true);
  }, []);

  function commit(next: Bet[]) {
    setBets(next);
    setStorageOk(saveBets(next));
  }

  function add() {
    if (!draft.event.trim() || !draft.selection.trim()) return;
    commit([{ ...draft }, ...bets]);
    setDraft(newBet({ sport: draft.sport, book: draft.book }));
  }

  function patch(id: string, p: Partial<Bet>) {
    commit(bets.map((b) => (b.id === id ? { ...b, ...p } : b)));
  }

  function remove(id: string) {
    commit(bets.filter((b) => b.id !== id));
  }

  function exportCsv() {
    const blob = new Blob([toCSV(bets)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `desk-betlog-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const s = useMemo(() => summarize(bets), [bets]);

  return (
    <div className="wrap">
      <header className="top">
        <div className="brand">
          <h1>Bet log</h1>
          <span>an untracked bet is an unlearned lesson</span>
        </div>
        <div className="presets">
          <Link href="/"><button>← Back to the desk</button></Link>
          <button onClick={exportCsv} disabled={!bets.length}>Export CSV</button>
        </div>
      </header>

      {!storageOk && (
        <div className="err">
          Could not write to browser storage, so changes will not survive a reload. Private-browsing
          mode or blocked site data will do this. Export to CSV to keep this log.
        </div>
      )}

      <section className="card">
        <h2>Closing line value — the only honest scoreboard</h2>
        <div className="stats">
          <Stat label="Mean CLV" value={f(s.clv.meanClvPts, 2, true)} unit="prob pts"
            tone={s.clv.meanClvPts == null ? "" : s.clv.meanClvPts > 0.5 ? "good" : s.clv.meanClvPts < -0.5 ? "bad" : ""} />
          <Stat label="Beat the close" value={s.clv.beatClosePct == null ? "—" : `${s.clv.beatClosePct.toFixed(0)}%`}
            unit={`${s.clv.beatClose}/${s.clv.tracked}`} />
          <Stat label="EV vs close" value={f(s.clv.meanEvVsClosePct, 2, true)} unit="%" />
          <Stat label="Closing prices recorded" value={`${s.clv.tracked}`} unit={`of ${s.total}`}
            tone={s.total > 0 && s.clv.tracked < s.total ? "warn" : ""} />
        </div>
        <p className="verdict">{s.verdict}</p>
      </section>

      <section className="card">
        <h2>Results — noise at this sample size, and reported as such</h2>
        <div className="stats">
          <Stat label="Record" value={s.settled ? `${s.wins}-${s.losses}${s.pushes ? `-${s.pushes}` : ""}` : "—"}
            unit={s.pending ? `${s.pending} pending` : ""} />
          <Stat label="Units" value={f(s.unitsPL, 2, true)} unit={`on ${f(s.unitsStaked, 1)}u staked`}
            tone={s.unitsPL > 0 ? "good" : s.unitsPL < 0 ? "bad" : ""} />
          <Stat label="ROI" value={s.roiPct == null ? "—" : `${f(s.roiPct, 1, true)}%`} unit="" />
          <Stat label="Hit rate" value={s.hitRatePct == null ? "—" : `${s.hitRatePct.toFixed(1)}%`}
            unit="breakeven 52.4% at -110" />
        </div>
        {s.record && (
          <p className="verdict">
            95% CI on the true hit rate: <strong>{(s.record.ci95![0] * 100).toFixed(1)}%</strong> to{" "}
            <strong>{(s.record.ci95![1] * 100).toFixed(1)}%</strong>. One-sided p vs break-even:{" "}
            <strong>{s.record.pValueVsBreakeven!.toFixed(4)}</strong>
            {s.record.provesAnEdge
              ? " — clears a one-sided test, which is not the same as an established edge: look at how wide that interval is, and note the test assumes this was the only record you were ever going to check."
              : " — does not clear a one-sided test against a break-even bettor."}
            {s.sampleSizeNeeded != null && (
              <> Establishing the rate you have observed would take roughly{" "}
                <strong>{s.sampleSizeNeeded.toLocaleString()}</strong> bets.</>
            )}
          </p>
        )}
      </section>

      <section className="card">
        <h2>Log a bet</h2>
        <div className="form">
          <L t="Sport"><input value={draft.sport} onChange={(e) => setDraft({ ...draft, sport: e.target.value })} placeholder="NFL" /></L>
          <L t="Event"><input value={draft.event} onChange={(e) => setDraft({ ...draft, event: e.target.value })} placeholder="DET @ BUF" /></L>
          <L t="Market"><input value={draft.market} onChange={(e) => setDraft({ ...draft, market: e.target.value })} placeholder="Total" /></L>
          <L t="Selection"><input value={draft.selection} onChange={(e) => setDraft({ ...draft, selection: e.target.value })} placeholder="Under 54.5" /></L>
          <L t="Book"><input value={draft.book} onChange={(e) => setDraft({ ...draft, book: e.target.value })} placeholder="Pinnacle" /></L>
          <L t="Price taken"><input type="number" value={draft.takenAmerican} onChange={(e) => setDraft({ ...draft, takenAmerican: Number(e.target.value) })} /></L>
          <L t="Stake (u)"><input type="number" step="0.25" max={2} value={draft.stakeUnits} onChange={(e) => setDraft({ ...draft, stakeUnits: Number(e.target.value) })} /></L>
          <L t="Fair prob"><input type="number" step="0.01" min={0} max={1} value={draft.fairProb ?? ""} onChange={(e) => setDraft({ ...draft, fairProb: num(e.target.value) })} placeholder="0.55" /></L>
          <L t="Notes" wide><input value={draft.notes ?? ""} onChange={(e) => setDraft({ ...draft, notes: e.target.value })} placeholder="why you took it, and what would change your mind" /></L>
        </div>
        {draft.stakeUnits > 2 && <p className="warn">Over the 2u ceiling. That is a rule, not a setting.</p>}
        <button className="primary" onClick={add} disabled={!draft.event.trim() || !draft.selection.trim()}>Add bet</button>
      </section>

      <section className="card">
        <h2>{bets.length} bet{bets.length === 1 ? "" : "s"}</h2>
        {!loaded ? <p className="muted">Loading…</p> : bets.length === 0 ? (
          <p className="muted">
            Nothing logged. Add the closing price once a game starts — that column is the one that
            tells you whether any of this is working.
          </p>
        ) : (
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th>Date</th><th>Event</th><th>Selection</th><th>Book</th>
                  <th className="r">Taken</th><th className="r">Close</th><th className="r">CLV</th>
                  <th className="r">Stake</th><th>Result</th><th className="r">P/L</th><th />
                </tr>
              </thead>
              <tbody>
                {bets.map((b) => {
                  const clv = betClvPts(b);
                  const pl = betProfit(b);
                  return (
                    <tr key={b.id}>
                      <td className="muted nowrap">{b.placedAt.slice(5, 10)}</td>
                      <td>{b.event}<div className="sub">{b.sport} · {b.market}</div></td>
                      <td>{b.selection}{b.notes ? <div className="sub">{b.notes}</div> : null}</td>
                      <td className="muted">{b.book}</td>
                      <td className="r nowrap">{b.takenAmerican > 0 ? `+${b.takenAmerican}` : b.takenAmerican}</td>
                      <td className="r">
                        <input className="mini" type="number" value={b.closingAmerican ?? ""} placeholder="—"
                          onChange={(e) => patch(b.id, { closingAmerican: num(e.target.value) })} />
                      </td>
                      <td className={`r nowrap ${clv == null ? "" : clv > 0 ? "good" : "bad"}`}>{f(clv, 2, true)}</td>
                      <td className="r">{b.stakeUnits}u</td>
                      <td>
                        <select value={b.result} onChange={(e) => patch(b.id, { result: e.target.value as BetResult })}>
                          {RESULTS.map((r) => <option key={r} value={r}>{r}</option>)}
                        </select>
                      </td>
                      <td className={`r nowrap ${pl > 0 ? "good" : pl < 0 ? "bad" : ""}`}>{b.result === "pending" ? "—" : f(pl, 2, true)}</td>
                      <td><button className="x" onClick={() => remove(b.id)} title="Delete">×</button></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {s.bySport.length > 1 && (
        <section className="card">
          <h2>By sport</h2>
          <div className="tablewrap">
            <table>
              <thead><tr><th>Sport</th><th className="r">Bets</th><th className="r">Units</th><th className="r">Mean CLV</th></tr></thead>
              <tbody>
                {s.bySport.map((r) => (
                  <tr key={r.sport}>
                    <td>{r.sport}</td>
                    <td className="r">{r.n}</td>
                    <td className={`r ${r.unitsPL > 0 ? "good" : r.unitsPL < 0 ? "bad" : ""}`}>{f(r.unitsPL, 2, true)}</td>
                    <td className={`r ${r.meanClvPts == null ? "" : r.meanClvPts > 0 ? "good" : "bad"}`}>{f(r.meanClvPts, 2, true)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <p className="muted foot">
        This log lives in your browser only. It is never sent anywhere, which also means it does not
        sync between devices and is lost if you clear site data. Export to CSV to keep it.
      </p>
    </div>
  );
}

function Stat({ label, value, unit, tone = "" }: { label: string; value: string; unit?: string; tone?: string }) {
  return (
    <div className="stat">
      <div className="k">{label}</div>
      <div className={`v ${tone}`}>{value}</div>
      {unit ? <div className="u">{unit}</div> : null}
    </div>
  );
}

function L({ t, children, wide }: { t: string; children: React.ReactNode; wide?: boolean }) {
  return (
    <label className={wide ? "wide" : ""}>
      <span>{t}</span>
      {children}
    </label>
  );
}
