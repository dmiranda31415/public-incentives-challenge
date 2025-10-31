import { useState, useRef, useEffect } from "react";
import SuggestedQuestions from "./SuggestedQuestions";
import ChatWindow from "./ChatWindow";
import ChatInput from "./ChatInput";
import Navbar from "./Navbar";

const END_SENTINEL = "[[END_STREAM]]";

export default function App() {
  const [messages, setMessages] = useState([
    { role: "bot", content: "Olá! 👋 Pergunte-me sobre incentivos ou empresas." },
  ]);
  const [isLoading, setIsLoading] = useState(false);

  const abortController = useRef(null);
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, isLoading]);

  async function sendMessage(rawText) {
    const text = (rawText || "").trim();
    if (!text || isLoading) return;

    setMessages((msgs) => [...msgs, { role: "user", content: text }]);
    setIsLoading(true);

    if (abortController.current) abortController.current.abort();
    const controller = new AbortController();
    abortController.current = controller;

    const decoder = new TextDecoder();
    let reader;
    let buffer = "";
    let finalMessage = "";

    try {
      const response = await fetch(`/chat/stream?q=${encodeURIComponent(text)}`, {
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      if (!response.body) throw new Error("Resposta sem corpo");

      reader = response.body.getReader();
      setMessages((msgs) => [...msgs, { role: "bot", content: "" }]);

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        let chunk = decoder.decode(value, { stream: true });
        if (!chunk) continue;

        if (chunk.includes(END_SENTINEL)) {
          chunk = chunk.replace(END_SENTINEL, "");
          if (chunk) {
            buffer += chunk;
          }
          finalMessage = buffer;
          setMessages((msgs) => [
            ...msgs.slice(0, -1),
            { role: "bot", content: finalMessage },
          ]);
          buffer = "";
          break;
        }

        buffer += chunk;
        finalMessage = buffer;
        setMessages((msgs) => [
          ...msgs.slice(0, -1),
          { role: "bot", content: finalMessage },
        ]);
      }

      const remaining = decoder.decode();
      if (remaining) {
        buffer += remaining;
        finalMessage = buffer;
      }

      if (finalMessage) {
        setMessages((msgs) => [
          ...msgs.slice(0, -1),
          { role: "bot", content: finalMessage },
        ]);
      }
    } catch (e) {
      console.error(e);
      setMessages((msgs) => [
        ...msgs.slice(0, -1),
        {
          role: "bot",
          content: "❌ Erro ao responder. Tente novamente ou verifique o backend.",
        },
      ]);
    } finally {
      if (reader) {
        try { await reader.cancel(); } catch (err) {}
        try { await reader.closed; } catch (err) {}
      }
      abortController.current = null;
      setIsLoading(false);
    }
  }

  const handleSuggestion = (q) => sendMessage(q);

  return (
    <div className="flex flex-col min-h-screen overflow-hidden bg-gradient-to-br from-slate-800 to-slate-900 text-white">
      <Navbar />
      <div className="flex-1 flex flex-col items-center w-full max-w-2xl mx-auto px-2">
        <SuggestedQuestions onSelect={handleSuggestion} disabled={isLoading} />
        <div className="flex-1 w-full max-w-2xl overflow-y-auto my-2 rounded-lg bg-slate-800/80 p-3 shadow-inner border border-slate-700 pb-32">
          <ChatWindow messages={messages} />
          {isLoading && <div className="italic text-slate-400">A responder...</div>}
          <div ref={endRef} />
        </div>
      </div>
      <ChatInput onSend={sendMessage} disabled={isLoading} />
    </div>
  );
}
