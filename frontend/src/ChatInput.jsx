import { useState } from "react";

export default function ChatInput({ onSend, disabled }) {
  const [input, setInput] = useState("");

  const handleSend = (e) => {
    e.preventDefault();
    if (!input.trim()) return;
    onSend(input.trim());
    setInput("");
  };

  return (
    <form
      onSubmit={handleSend}
      className="w-full max-w-2xl mx-auto py-4 px-2 flex gap-2 items-center fixed bottom-0 left-0 right-0 bg-slate-900/85 backdrop-blur-sm border-t border-slate-700"
    >
      <input
        type="text"
        className="flex-1 px-4 py-3 rounded-full bg-white/10 text-white outline-none placeholder:text-slate-400 border border-slate-700 focus:border-blue-500 transition-all duration-100"
        placeholder="Faça uma pergunta sobre incentivos ou empresas..."
        value={input}
        disabled={disabled}
        onChange={e => setInput(e.target.value)}
        onKeyDown={e => {
          if (e.key === "Enter" && !e.shiftKey) handleSend(e);
        }}
      />
      <button
        type="submit"
        disabled={disabled || !input.trim()}
        className="px-5 py-3 rounded-full bg-blue-600 hover:bg-blue-700 text-white font-semibold disabled:bg-slate-500 transition-all duration-100"
      >
        Enviar
      </button>
    </form>
  );
}