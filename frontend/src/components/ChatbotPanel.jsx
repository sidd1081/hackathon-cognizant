import { useState } from "react";
import { Section } from "./ui/Card.jsx";
import { Button } from "./ui/Button.jsx";
import { AiBadge } from "./ui/Pills.jsx";

const SAMPLE_PROMPTS = [
  "Summarize the likely root cause.",
  "What evidence supports this RCA?",
  "What should the team do next?",
];

function buildAssistantReply(input, analysis) {
  const text = input.toLowerCase();
  const data = analysis?.data;

  if (!data) {
    return "I can help once an incident has been analyzed. Describe the issue and run the RCA flow first.";
  }

  if (text.includes("summary") || text.includes("overview")) {
    return data.summary || "No summary was returned for the current incident.";
  }

  if (text.includes("root cause") || text.includes("cause")) {
    return data.root_cause || "No documented root cause was found in the retrieved evidence.";
  }

  if (text.includes("resolution") || text.includes("fix") || text.includes("next step")) {
    return data.resolution || "No resolution guidance was returned for the current incident.";
  }

  if (text.includes("evidence") || text.includes("support") || text.includes("ticket")) {
    const tickets = Array.isArray(data.supporting_incidents) && data.supporting_incidents.length
      ? data.supporting_incidents.map((item) => item.ticket_id || item.id || "ticket").join(", ")
      : "No supporting tickets were cited";

    return `The retrieved evidence currently points to ${tickets}.`;
  }

  if (text.includes("confidence")) {
    return `The model confidence is ${data.confidence || "not available"} for this RCA.`;
  }

  const rootCause = data.root_cause || "no documented root cause was found";
  const resolution = data.resolution || "review the evidence and confirm the remediation path";

  return `Based on the latest RCA, the incident appears to align with: ${rootCause}. The recommended next step is: ${resolution}.`;
}

export function ChatbotPanel({ analysis, incidentText }) {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([
    {
      id: "welcome",
      role: "assistant",
      text: "Hi! I can help explain the latest incident RCA, list evidence, and suggest next steps.",
    },
  ]);
  const [isTyping, setIsTyping] = useState(false);

  const sendMessage = () => {
    if (!input.trim()) return;

    const userMessage = {
      id: `${Date.now()}-user`,
      role: "user",
      text: input.trim(),
    };

    const nextMessages = [...messages, userMessage];
    setMessages(nextMessages);
    setInput("");
    setIsTyping(true);

    window.setTimeout(() => {
      const reply = buildAssistantReply(userMessage.text, analysis);
      setMessages((current) => [
        ...current,
        {
          id: `${Date.now()}-assistant`,
          role: "assistant",
          text: reply,
        },
      ]);
      setIsTyping(false);
    }, 350);
  };

  const handleKeyDown = (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  };

  return (
    <Section
      label="AI Chat"
      title="Incident Assistant"
      description="Ask for a quick summary, evidence review, or next-step guidance based on the current RCA"
      accent="slate"
      tag={<AiBadge />}
    >
      <div className="space-y-4">
        <div className="chat-scroll max-h-72 space-y-3 overflow-y-auto rounded-lg border border-[#30363d] bg-[#0d1117] p-3">
          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm leading-relaxed ${
                  message.role === "user"
                    ? "bg-violet-600 text-white"
                    : "border border-[#30363d] bg-[#161b22] text-[#e6edf3]"
                }`}
              >
                {message.text}
              </div>
            </div>
          ))}

          {isTyping && (
            <div className="flex justify-start">
              <div className="rounded-2xl border border-[#30363d] bg-[#161b22] px-3 py-2 text-sm text-[#8b949e]">
                Thinking…
              </div>
            </div>
          )}
        </div>

        <div className="flex flex-wrap gap-2">
          {SAMPLE_PROMPTS.map((prompt) => (
            <button
              key={prompt}
              type="button"
              onClick={() => setInput(prompt)}
              className="rounded-full border border-[#30363d] bg-[#161b22] px-2.5 py-1 text-xs text-[#c9d1d9] transition hover:border-violet-500 hover:text-violet-300"
            >
              {prompt}
            </button>
          ))}
        </div>

        <div className="flex flex-col gap-3 sm:flex-row">
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={handleKeyDown}
            rows={2}
            placeholder={incidentText ? "Ask about this incident…" : "Describe the incident and analyze it to unlock context…"}
            className="min-h-[72px] flex-1 resize-y rounded-lg border border-[#30363d] bg-[#0d1117] p-3 text-sm text-[#e6edf3] placeholder:text-[#6e7681] focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500/30"
          />
          <Button onClick={sendMessage} className="self-end" disabled={!input.trim()}>
            Send
          </Button>
        </div>
      </div>
    </Section>
  );
}
