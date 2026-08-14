import ReactMarkdown from "react-markdown";

/** Render de Markdown per a textos generats (informes, respostes d'agents). */
export function Markdown(props: { children: string }) {
  return (
    <div className="prose-lagalia max-w-none text-sm leading-relaxed text-ink [&_h1]:mt-3 [&_h1]:text-lg [&_h1]:font-bold [&_h2]:mt-3 [&_h2]:text-base [&_h2]:font-semibold [&_h3]:mt-2 [&_h3]:font-semibold [&_li]:ml-4 [&_ol]:list-decimal [&_p]:mt-2 [&_strong]:font-semibold [&_table]:mt-2 [&_table]:w-full [&_td]:border [&_td]:border-line [&_td]:px-2 [&_td]:py-1 [&_th]:border [&_th]:border-line [&_th]:bg-surface [&_th]:px-2 [&_th]:py-1 [&_ul]:list-disc [&_code]:rounded [&_code]:bg-surface [&_code]:px-1">
      <ReactMarkdown>{props.children}</ReactMarkdown>
    </div>
  );
}
