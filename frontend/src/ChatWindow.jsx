import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export default function ChatWindow({ messages }) {
  return (
    <div className="flex flex-col gap-3 w-full">
      {messages.map((m, i) => (
        <div
          key={i}
          className={
            m.role === "user"
              ? "self-end bg-blue-600 text-white px-5 py-3 rounded-2xl rounded-br-sm max-w-[80%] shadow"
              : "self-start bg-slate-700 text-white px-5 py-3 rounded-2xl rounded-bl-sm max-w-[80%] shadow"
          }
        >
          <div className="flex items-start gap-2 text-sm leading-relaxed">
            <span className="mt-1">{m.role === "user" ? "👤" : "🤖"}</span>
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              className="markdown-body"
            >
              {m.content}
            </ReactMarkdown>
          </div>
        </div>
      ))}
    </div>
  );
}