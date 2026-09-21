"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import styles from "./ask.module.css";

interface Example {
  category: string;
  question: string;
  sql: string;
}

interface QueryResult {
  columns: string[];
  rows: Record<string, unknown>[];
}

interface UserMessage {
  id: string;
  role: "user";
  text: string;
}

interface AssistantMessage {
  id: string;
  role: "assistant";
  pending: boolean;
  sql?: string | null;
  result?: QueryResult | null;
  error?: string | null;
}

interface SystemMessage {
  id: string;
  role: "system";
  text: string;
}

type ChatMessage = UserMessage | AssistantMessage | SystemMessage;

const REFUSAL_PREFIX = "REFUSE:";
const COOLDOWN_MS = 60_000;

function newId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export default function AskPage() {
  const [examples, setExamples] = useState<Example[]>([]);
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [cooldownUntil, setCooldownUntil] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const threadRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch("/data/ask/examples.json")
      .then((r) => r.json())
      .then(setExamples)
      .catch(() => setExamples([]));
  }, []);

  useEffect(() => {
    if (!cooldownUntil) return;
    const interval = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(interval);
  }, [cooldownUntil]);

  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const cooldownSecondsLeft = cooldownUntil ? Math.max(0, Math.ceil((cooldownUntil - now) / 1000)) : 0;
  const onCooldown = cooldownSecondsLeft > 0;

  function pushMessage(msg: ChatMessage) {
    setMessages((prev) => [...prev, msg]);
  }

  function updateMessage(id: string, patch: Partial<Omit<AssistantMessage, "id" | "role">>) {
    setMessages((prev) =>
      prev.map((m) => (m.id === id && m.role === "assistant" ? { ...m, ...patch } : m)),
    );
  }

  async function runSql(candidateSql: string): Promise<{ result?: QueryResult; error?: string }> {
    try {
      const { runGuardedQuery } = await import("../../lib/duckdb");
      const result = await runGuardedQuery(candidateSql);
      return { result };
    } catch (err) {
      return { error: err instanceof Error ? err.message : "Query failed." };
    }
  }

  async function runExample(example: Example) {
    if (loading) return;
    pushMessage({ id: newId(), role: "user", text: example.question });

    if (example.sql.startsWith(REFUSAL_PREFIX)) {
      pushMessage({
        id: newId(),
        role: "assistant",
        pending: false,
        error: example.sql.slice(REFUSAL_PREFIX.length).trim(),
      });
      return;
    }

    const assistantId = newId();
    pushMessage({ id: assistantId, role: "assistant", pending: true });
    const { result, error } = await runSql(example.sql);
    updateMessage(assistantId, { pending: false, sql: example.sql, result, error });
  }

  async function askFreeText(e: React.FormEvent) {
    e.preventDefault();
    const text = question.trim();
    if (!text || loading || onCooldown) return;

    setQuestion("");
    pushMessage({ id: newId(), role: "user", text });
    const assistantId = newId();
    pushMessage({ id: assistantId, role: "assistant", pending: true });
    setLoading(true);

    try {
      const resp = await fetch("/api/ask", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ question: text, schema_version: 1 }),
      });
      const data = await resp.json();

      if (resp.status === 429) {
        const seconds = typeof data.cooldown_seconds === "number" ? data.cooldown_seconds : 60;
        setCooldownUntil(Date.now() + seconds * 1000);
        updateMessage(assistantId, {
          pending: false,
          error: data.error ?? "Too many questions — please wait for the cooldown.",
        });
        return;
      }

      if (!resp.ok) {
        updateMessage(assistantId, {
          pending: false,
          error: data.error ?? "The ask endpoint isn't available right now.",
        });
        return;
      }

      // A successful call used this minute's free-tier budget — start the
      // same cooldown client-side so the next send is disabled proactively
      // rather than round-tripping to the server just to get a 429 back.
      setCooldownUntil(Date.now() + COOLDOWN_MS);
      const { result, error } = await runSql(data.sql as string);
      updateMessage(assistantId, { pending: false, sql: data.sql as string, result, error });
    } catch {
      updateMessage(assistantId, {
        pending: false,
        error: "The ask endpoint isn't reachable right now. Try one of the example questions instead.",
      });
    } finally {
      setLoading(false);
    }
  }

  const grouped = useMemo(() => {
    const byCategory = new Map<string, Example[]>();
    for (const ex of examples) {
      const list = byCategory.get(ex.category) ?? [];
      list.push(ex);
      byCategory.set(ex.category, list);
    }
    return byCategory;
  }, [examples]);

  return (
    <main className={styles.page}>
      <div className={styles.intro}>
        <h1>Ask the box score</h1>
        <p>
          Plain-English questions answered with SQL over real NBA stats, 2015-16 onward. Example
          questions run entirely in your browser — free, instant. Typing your own question sends
          it to a free Workers AI model, capped at 1 question per minute.
        </p>
      </div>

      <div className={styles.thread} ref={threadRef}>
        {messages.length === 0 && (
          <div className={styles.emptyState}>
            <p className={styles.emptyHint}>Try one of these, or type your own question below.</p>
            <div className={styles.gallery}>
              {[...grouped.entries()].map(([category, items]) => (
                <div key={category} className={styles.categoryGroup}>
                  <span className={styles.categoryLabel}>{category}</span>
                  {items.map((ex) => (
                    <button
                      key={ex.question}
                      className={styles.chip}
                      onClick={() => runExample(ex)}
                      disabled={loading}
                      type="button"
                    >
                      {ex.question}
                    </button>
                  ))}
                </div>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => {
          if (msg.role === "user") {
            return (
              <div key={msg.id} className={`${styles.messageRow} ${styles.messageRowUser}`}>
                <div className={`${styles.bubble} ${styles.bubbleUser}`}>{msg.text}</div>
              </div>
            );
          }
          if (msg.role === "system") {
            return (
              <div key={msg.id} className={styles.messageRow}>
                <div className={`${styles.bubble} ${styles.bubbleSystem}`}>{msg.text}</div>
              </div>
            );
          }
          return (
            <div key={msg.id} className={`${styles.messageRow} ${styles.messageRowAssistant}`}>
              <div className={`${styles.bubble} ${styles.bubbleAssistant}`}>
                {msg.pending ? (
                  <span className={styles.typing} aria-label="Thinking">
                    <span />
                    <span />
                    <span />
                  </span>
                ) : msg.error ? (
                  <p className={styles.error}>{msg.error}</p>
                ) : msg.result ? (
                  <>
                    <div className={styles.tableWrap}>
                      <ResultTable result={msg.result} />
                    </div>
                    {msg.sql && (
                      <details className={styles.sqlBlock}>
                        <summary>SQL</summary>
                        <pre>{msg.sql}</pre>
                      </details>
                    )}
                  </>
                ) : (
                  <p className={styles.error}>No results.</p>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <form onSubmit={askFreeText} className={styles.composer}>
        <div className={styles.askForm}>
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder={
              onCooldown
                ? `Cooldown: ${cooldownSecondsLeft}s remaining…`
                : "Who had the most 30-point games on fewer than 15 shots?"
            }
            maxLength={300}
            className={styles.input}
            disabled={loading || onCooldown}
          />
          <button type="submit" className={styles.sendButton} disabled={loading || onCooldown || !question.trim()}>
            {onCooldown ? `${cooldownSecondsLeft}s` : "Ask"}
          </button>
        </div>
        {onCooldown && (
          <p className={styles.cooldownHint}>
            This runs on a free Workers AI allocation, capped at 1 question per minute — please
            wait {cooldownSecondsLeft}s before asking another.
          </p>
        )}
      </form>
    </main>
  );
}

function ResultTable({ result }: { result: QueryResult }) {
  return (
    <table className={styles.table}>
      <thead>
        <tr>
          {result.columns.map((c) => (
            <th key={c}>{c}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {result.rows.map((row, i) => (
          <tr key={i}>
            {result.columns.map((c) => (
              <td key={c}>{String(row[c] ?? "")}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
