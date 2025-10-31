const suggestions = [
  "Quais os incentivos para pequenas empresas?",
  "Que empresas podem beneficiar do incentivo fiscal X?",
  "Empresas elegíveis para apoio à digitalização?",
  "Resuma o incentivo 3.",
  "Como obter o incentivo a fundo perdido?",
];

export default function SuggestedQuestions({ onSelect, disabled }) {
  return (
    <div className="flex flex-wrap gap-2 justify-center py-3">
      {suggestions.map((q, i) => (
        <button
          key={i}
          className="bg-white/10 hover:bg-white/20 text-white text-sm px-3 py-1 rounded-full border border-white/20 transition-all duration-100"
          disabled={disabled}
          onClick={() => onSelect(q)}
        >
          {q}
        </button>
      ))}
    </div>
  );
}