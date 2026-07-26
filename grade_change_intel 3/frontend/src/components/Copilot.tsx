import { useEffect, useRef, useState } from "react";
import type { TickSnapshot } from "../types";
import { answerQuestion, SUGGESTED_QUESTIONS } from "../copilotAnswers";

interface ChatMessage {
  role: "user" | "copilot";
  text: string;
}

// Template-based Q&A copilot: no external AI call, fully offline, answers
// only ever come from copilotAnswers.ts pattern-matching against data
// already computed for this screen -- see that file's header comment for
// why this is deliberate, not a shortcut.
export function Copilot({ snapshot, onClose }: { snapshot: TickSnapshot | null; onClose?: () => void }) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    { role: "copilot", text: 'Ask me about this transition -- try "why is this risky?" or type "help" for examples.' },
  ]);
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  function ask(question: string) {
    if (!question.trim()) return;
    const answer = answerQuestion(question, snapshot);
    setMessages((m) => [...m, { role: "user", text: question }, { role: "copilot", text: answer }]);
    setInput("");
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", padding: "16px 16px 0" }}>
        <div>
          <h3 style={{ margin: 0 }}>🤖 Copilot</h3>
          <p className="muted" style={{ marginTop: 6 }}>
            Template-based, not a live AI call -- every answer is assembled from data already shown on this page.
          </p>
        </div>
        {onClose && (
          <button onClick={onClose} aria-label="Close Copilot"
                  style={{ background: "none", border: "none", color: "var(--text-muted)", fontSize: 20, cursor: "pointer", lineHeight: 1, padding: 4 }}>
            &times;
          </button>
        )}
      </div>

      <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", padding: "12px 16px" }}>
        {messages.map((m, i) => (
          <div key={i} style={{ display: "flex", justifyContent: m.role === "user" ? "flex-end" : "flex-start", marginBottom: 8 }}>
            <div
              style={{
                maxWidth: "85%", padding: "7px 12px", borderRadius: 10, fontSize: 13,
                background: m.role === "user" ? "var(--series-1)" : "var(--page)",
                color: m.role === "user" ? "#fff" : "var(--text-primary)",
                border: m.role === "copilot" ? "1px solid var(--border)" : "none",
              }}
            >
              {m.text}
            </div>
          </div>
        ))}
      </div>

      <div style={{ padding: "0 16px 16px" }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8 }}>
          {SUGGESTED_QUESTIONS.map((q) => (
            <button key={q} className="source-chip" style={{ cursor: "pointer", background: "var(--surface-1)" }} onClick={() => ask(q)}>
              {q}
            </button>
          ))}
        </div>

        <div style={{ display: "flex", gap: 8 }}>
          <input
            type="text" value={input} placeholder="Ask a question..."
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") ask(input); }}
            style={{ flex: 1, padding: "7px 10px", background: "var(--page)", color: "var(--text-primary)", border: "1px solid var(--border)", borderRadius: 6, fontSize: 13 }}
          />
          <button className="btn" onClick={() => ask(input)}>Ask</button>
        </div>
      </div>
    </div>
  );
}
