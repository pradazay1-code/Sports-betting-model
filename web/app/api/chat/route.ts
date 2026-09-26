import Anthropic from "@anthropic-ai/sdk";
import { SYSTEM_PROMPT, contextPreamble } from "@/lib/prompt";
import { DESK_TOOLS, runTool } from "@/lib/tools";

export const runtime = "nodejs";
// A full FBS+FCS slate is a long agentic run. Vercel caps this per plan:
// Hobby 300s, Pro 800s. Exceeding the plan cap fails the deploy, so keep this
// at or below what your plan allows.
export const maxDuration = 800;

const MODEL = "claude-opus-5";
/** Server-side web search: Anthropic runs it, so the deployed agent researches like the CLI does. */
const WEB_SEARCH = { type: "web_search_20260209" as const, name: "web_search" as const, max_uses: 30 };

const MAX_ITERATIONS = 40; // a big slate legitimately needs many rounds; this is a runaway guard

/**
 * Rate limiting, honestly labelled.
 *
 * This is an in-memory bucket, so on serverless it is PER INSTANCE and resets on
 * cold start — a determined caller who lands on fresh instances gets more than
 * the stated limit. It is real protection against a stuck client hammering the
 * endpoint and running up an API bill, and it is NOT protection against a
 * motivated attacker. For that you need Vercel KV, Upstash, or a WAF rule.
 */
const RATE_LIMIT = Number(process.env.RATE_LIMIT_PER_HOUR ?? 30);
const RATE_WINDOW_MS = 60 * 60 * 1000;
const buckets = new Map<string, number[]>();

function clientKey(req: Request): string {
  const fwd = req.headers.get("x-forwarded-for");
  return (fwd?.split(",")[0].trim()) || req.headers.get("x-real-ip") || "unknown";
}

function rateLimit(req: Request): { ok: true } | { ok: false; retryAfter: number } {
  if (RATE_LIMIT <= 0) return { ok: true };            // 0 disables it
  const key = clientKey(req);
  const now = Date.now();
  const hits = (buckets.get(key) ?? []).filter((t) => now - t < RATE_WINDOW_MS);
  if (hits.length >= RATE_LIMIT) {
    return { ok: false, retryAfter: Math.ceil((RATE_WINDOW_MS - (now - hits[0])) / 1000) };
  }
  hits.push(now);
  buckets.set(key, hits);
  // Keep the map from growing without bound across a long-lived instance.
  if (buckets.size > 5000) {
    for (const [k, v] of buckets) if (!v.some((t) => now - t < RATE_WINDOW_MS)) buckets.delete(k);
  }
  return { ok: true };
}

type Role = "user" | "assistant";
interface IncomingMessage { role: Role; content: string }

const MAX_CHARS_PER_MESSAGE = 20_000;
const MAX_MESSAGES = 60;

export async function POST(req: Request) {
  // Validate the REQUEST before the environment, so a malformed call gets a 400
  // regardless of config and the endpoint stays testable without a key.
  let body: { messages?: IncomingMessage[]; effort?: string };
  try {
    body = await req.json();
  } catch {
    return new Response(JSON.stringify({ error: "Malformed JSON body." }), { status: 400, headers: { "content-type": "application/json" } });
  }

  const incoming = (body.messages ?? []).filter((m) => m.content?.trim());
  if (!incoming.length) {
    return new Response(JSON.stringify({ error: "No messages supplied." }), { status: 400, headers: { "content-type": "application/json" } });
  }
  if (incoming.length > MAX_MESSAGES) {
    return new Response(
      JSON.stringify({ error: `Too many messages (${incoming.length}). Start a new conversation.` }),
      { status: 400, headers: { "content-type": "application/json" } },
    );
  }
  const oversized = incoming.find((m) => m.content.length > MAX_CHARS_PER_MESSAGE);
  if (oversized) {
    return new Response(
      JSON.stringify({ error: `A message exceeds ${MAX_CHARS_PER_MESSAGE} characters.` }),
      { status: 400, headers: { "content-type": "application/json" } },
    );
  }

  const limit = rateLimit(req);
  if (!limit.ok) {
    return new Response(
      JSON.stringify({
        error: `Rate limit reached (${RATE_LIMIT}/hour). Try again in ${Math.ceil(limit.retryAfter / 60)} minute(s).`,
      }),
      {
        status: 429,
        headers: { "content-type": "application/json", "retry-after": String(limit.retryAfter) },
      },
    );
  }
  const effort = (["low", "medium", "high", "xhigh", "max"] as const).includes(body.effort as never)
    ? (body.effort as "low" | "medium" | "high" | "xhigh" | "max")
    : "high";

  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    return new Response(
      JSON.stringify({ error: "ANTHROPIC_API_KEY is not set. Add it in Vercel → Settings → Environment Variables, then redeploy." }),
      { status: 500, headers: { "content-type": "application/json" } },
    );
  }

  const client = new Anthropic({ apiKey });

  // Volatile context lives in the user turn so the system prefix stays cacheable.
  const messages: Anthropic.MessageParam[] = incoming.map((m, i) =>
    i === incoming.length - 1 && m.role === "user"
      ? { role: "user", content: `${contextPreamble(new Date().toISOString().slice(0, 10))}\n\n${m.content}` }
      : { role: m.role, content: m.content },
  );

  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      const send = (event: string, data: unknown) => {
        controller.enqueue(encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
      };

      try {
        for (let iteration = 0; iteration < MAX_ITERATIONS; iteration++) {
          const s = client.messages.stream({
            model: MODEL,
            max_tokens: 32000,
            system: [{ type: "text", text: SYSTEM_PROMPT, cache_control: { type: "ephemeral" } }],
            thinking: { type: "adaptive", display: "summarized" },
            output_config: { effort },
            tools: [...DESK_TOOLS, WEB_SEARCH],
            messages,
          });

          for await (const ev of s) {
            if (ev.type === "content_block_delta") {
              if (ev.delta.type === "text_delta") send("text", { text: ev.delta.text });
              else if (ev.delta.type === "thinking_delta") send("thinking", { text: ev.delta.thinking });
            } else if (ev.type === "content_block_start") {
              const b = ev.content_block;
              if (b.type === "tool_use") send("tool", { name: b.name, status: "start" });
              else if (b.type === "server_tool_use") send("tool", { name: b.name, status: "searching" });
            }
          }

          const msg = await s.finalMessage();
          messages.push({ role: "assistant", content: msg.content });

          if (msg.stop_reason === "refusal") {
            send("error", { error: `Request declined (${msg.stop_details?.category ?? "unspecified"}).` });
            break;
          }

          // The SDK's tool runner does NOT auto-resume pause_turn. A long
          // server-tool turn that pauses would otherwise end the loop and return
          // a silently truncated answer — which on a full slate looks like the
          // agent just stopped mid-sentence. Resume by looping with the paused
          // assistant turn already appended.
          if (msg.stop_reason === "pause_turn") {
            send("tool", { name: "web_search", status: "resuming" });
            continue;
          }

          if (msg.stop_reason !== "tool_use") break;

          // All tool_results for one assistant turn go back in ONE user message.
          // Splitting them trains the model to stop making parallel calls.
          const results: Anthropic.ToolResultBlockParam[] = [];
          for (const block of msg.content) {
            if (block.type !== "tool_use") continue;
            try {
              const out = runTool(block.name, block.input as Record<string, unknown>);
              results.push({ type: "tool_result", tool_use_id: block.id, content: JSON.stringify(out) });
              send("tool", { name: block.name, status: "done" });
            } catch (err) {
              // Hand the error back as a tool_result so the model can correct
              // itself, rather than dropping the block and desyncing the turn.
              results.push({
                type: "tool_result", tool_use_id: block.id, is_error: true,
                content: err instanceof Error ? err.message : String(err),
              });
              send("tool", { name: block.name, status: "error" });
            }
          }
          messages.push({ role: "user", content: results });
        }
        send("done", {});
      } catch (err) {
        let message = err instanceof Error ? err.message : "Unknown error";
        if (err instanceof Anthropic.RateLimitError) message = "Rate limited by the Claude API. Wait a moment and retry.";
        else if (err instanceof Anthropic.AuthenticationError) message = "ANTHROPIC_API_KEY is invalid.";
        else if (err instanceof Anthropic.APIConnectionError) message = "Could not reach the Claude API.";
        send("error", { error: message });
      } finally {
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      "content-type": "text/event-stream; charset=utf-8",
      "cache-control": "no-cache, no-transform",
      connection: "keep-alive",
      "x-accel-buffering": "no",
    },
  });
}
