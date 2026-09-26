"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Msg { role: "user" | "assistant"; content: string; thinking?: string }
interface Chip { name: string; status: string }

const PRESETS = [
  { label: "CFB slate today", q: "Run the full college football slate today — every game, FBS and FCS. Total and game projection for each, plus projected team rushing and passing yards. Lead with a table of every game, then expand only on the ones carrying a playable number." },
  { label: "NFL slate today", q: "Run today's NFL slate. Market read, both projection forms, and only the games with a playable number. Flag anything where the methods disagree by more than 10 points." },
  { label: "NBA slate today", q: "Run today's NBA slate. Start from projected minutes and confirmed lineups — check late scratches before anything else. Totals and sides only where there's a real number." },
  { label: "Best plays on the board", q: "What are the highest-EV plays on the board right now, ranked? Report win probability and edge separately for each." },
  { label: "Build a parlay", q: "Build me the best-structured parlay available today. Show each leg's fair probability, the combined true probability, the offered payout, the hold, and the EV — and tell me if the honest answer is that no parlay clears the bar." },
];

export default function Page() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [chips, setChips] = useState<Chip[]>([]);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs, chips]);

  const send = useCallback(async (text: string) => {
    const q = text.trim();
    if (!q || busy) return;
    setError(null);
    setChips([]);
    setInput("");
    const history = [...msgs, { role: "user" as const, content: q }];
    setMsgs([...history, { role: "assistant", content: "", thinking: "" }]);
    setBusy(true);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ messages: history.map((m) => ({ role: m.role, content: m.content })) }),
      });
      if (!res.ok || !res.body) {
        const j = await res.json().catch(() => ({ error: `Request failed (${res.status}).` }));
        throw new Error(j.error ?? `Request failed (${res.status}).`);
      }

      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const frames = buf.split("\n\n");
        buf = frames.pop() ?? "";
        for (const frame of frames) {
          const ev = /^event: (.+)$/m.exec(frame)?.[1];
          const raw = /^data: (.+)$/m.exec(frame)?.[1];
          if (!ev || !raw) continue;
          let data: { text?: string; name?: string; status?: string; error?: string };
          try { data = JSON.parse(raw); } catch { continue; }

          if (ev === "text" && data.text) {
            setMsgs((p) => { const n = [...p]; n[n.length - 1] = { ...n[n.length - 1], content: n[n.length - 1].content + data.text }; return n; });
          } else if (ev === "thinking" && data.text) {
            setMsgs((p) => { const n = [...p]; n[n.length - 1] = { ...n[n.length - 1], thinking: (n[n.length - 1].thinking ?? "") + data.text }; return n; });
          } else if (ev === "tool" && data.name) {
            setChips((p) => {
              const i = p.findIndex((c) => c.name === data.name);
              if (i >= 0) { const n = [...p]; n[i] = { name: data.name!, status: data.status ?? "" }; return n; }
              return [...p, { name: data.name!, status: data.status ?? "" }];
            });
          } else if (ev === "error" && data.error) {
            setError(data.error);
          }
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
      setChips([]);
    }
  }, [busy, msgs]);

  return (
    <>
      <div className="wrap">
        <header className="top">
          <div className="brand">
            <h1>The Desk</h1>
            <span>devig · EV · Kelly · drive-level simulation, over live research</span>
          </div>
          <div className="presets">
            {PRESETS.map((p) => (
              <button key={p.label} onClick={() => send(p.q)} disabled={busy}>{p.label}</button>
            ))}
          </div>
        </header>

        {msgs.length === 0 && (
          <div className="empty">
            <p>Ask anything you would ask a trader. It researches live, runs the math in code rather than in prose, and tells you when there is no bet.</p>
            <ul>
              <li>&ldquo;Analysis on every CFB game today, FBS and FCS — totals and projections&rdquo;</li>
              <li>&ldquo;Is Bijan over 4.5 receptions a bet at -115?&rdquo;</li>
              <li>&ldquo;Devig this: Chiefs -240, Colts +198&rdquo;</li>
              <li>&ldquo;I have $100 and want at least +100 — what is the best-structured play?&rdquo;</li>
            </ul>
            <p>It will say &ldquo;no edge&rdquo; when that is the answer. That is the feature.</p>
          </div>
        )}

        {msgs.map((m, i) => (
          <div key={i} className={`msg ${m.role === "user" ? "user" : "desk"}`}>
            <div className="who">{m.role === "user" ? "You" : "The Desk"}</div>
            {m.thinking && m.thinking.trim() && (
              <details className="think">
                <summary>Reasoning</summary>
                <div className="body">{m.thinking}</div>
              </details>
            )}
            <div className="bubble">
              {m.role === "user"
                ? m.content
                : <Markdown remarkPlugins={[remarkGfm]}>{m.content || (busy && i === msgs.length - 1 ? "_Working…_" : "")}</Markdown>}
            </div>
          </div>
        ))}

        {chips.length > 0 && (
          <div className="activity">
            {chips.map((c) => (
              <span key={c.name} className={`chip ${c.status === "done" ? "" : "live"}`}>
                {c.name === "web_search" ? "researching" : c.name} · {c.status}
              </span>
            ))}
          </div>
        )}

        {error && <div className="err">{error}</div>}
        <div ref={endRef} />
      </div>

      <div className="composer">
        <div className="inner">
          <textarea
            ref={taRef}
            value={input}
            placeholder="Ask about a game, a slate, a prop, or a price…"
            onChange={(e) => {
              setInput(e.target.value);
              const el = taRef.current;
              if (el) { el.style.height = "auto"; el.style.height = `${Math.min(el.scrollHeight, 200)}px`; }
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); }
            }}
          />
          <button onClick={() => send(input)} disabled={busy || !input.trim()}>
            {busy ? "Working" : "Send"}
          </button>
        </div>
        <div className="hint">Enter to send, Shift+Enter for a new line. A full FBS+FCS slate takes several minutes — it is doing real research.</div>
      </div>
    </>
  );
}
