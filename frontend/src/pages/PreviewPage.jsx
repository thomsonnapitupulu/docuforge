import { useState } from "react";
import { api } from "../lib/api";

export default function PreviewPage({ jobId, document, artifactType, onReset }) {
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(null);
  const [downloading, setDownloading] = useState(null); // "md" | "docx" | null
  const [downloadError, setDownloadError] = useState(null);

  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(document || "");
      setCopyError(null);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopyError("Couldn't copy — your browser may have blocked clipboard access.");
    }
  };

  const download = async (format) => {
    setDownloading(format);
    setDownloadError(null);
    try {
      const res = await fetch(api.exportUrl(jobId, format));
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Export failed (${res.status})`);
      }
      const blob = await res.blob();
      const disposition = res.headers.get("Content-Disposition") || "";
      const match = disposition.match(/filename="?([^"]+)"?/);
      const filename = match ? match[1] : `${artifactType}.${format}`;

      const url = URL.createObjectURL(blob);
      const link = window.document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setDownloadError(err.message);
    } finally {
      setDownloading(null);
    }
  };

  const downloadMd = () => download("md");
  const downloadDocx = () => download("docx");

  // Very basic markdown renderer — render headers and code blocks
  const renderPreview = (md) => {
    if (!md) return null;
    return md.split("\n").map((line, i) => {
      if (line.startsWith("# "))
        return <h1 key={i} className="text-2xl font-bold text-slate-100 mt-6 mb-2">{line.slice(2)}</h1>;
      if (line.startsWith("## "))
        return <h2 key={i} className="text-lg font-semibold text-violet-300 mt-5 mb-1.5 border-b border-slate-800 pb-1">{line.slice(3)}</h2>;
      if (line.startsWith("### "))
        return <h3 key={i} className="text-base font-semibold text-slate-200 mt-4 mb-1">{line.slice(4)}</h3>;
      if (line.startsWith("- ") || line.startsWith("* "))
        return <li key={i} className="text-slate-300 text-sm ml-4 list-disc">{line.slice(2)}</li>;
      if (line.startsWith("```"))
        return <div key={i} className="border-t border-slate-800 my-2" />;
      if (line.trim() === "---")
        return <hr key={i} className="border-slate-800 my-4" />;
      if (line.trim() === "")
        return <div key={i} className="h-2" />;
      return <p key={i} className="text-slate-300 text-sm leading-relaxed">{line}</p>;
    });
  };

  return (
    <div className="space-y-6">
      {/* Header row */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-100">Document Ready</h1>
          <p className="text-slate-400 text-sm mt-1">
            <span className="text-violet-400 font-semibold">{artifactType}</span> generated for job{" "}
            <code className="text-slate-500 text-xs">{jobId?.slice(0, 8)}</code>
          </p>
        </div>

        {/* Export actions */}
        <div className="flex items-center gap-2">
          <button
            onClick={copyToClipboard}
            className="px-3 py-1.5 text-xs border border-slate-700 rounded hover:border-slate-500 text-slate-300 transition-colors"
          >
            {copied ? "✓ Copied" : "Copy Markdown"}
          </button>
          <button
            onClick={downloadMd}
            disabled={downloading !== null}
            className="px-3 py-1.5 text-xs bg-slate-800 hover:bg-slate-700 disabled:opacity-50 rounded text-slate-200 transition-colors"
          >
            {downloading === "md" ? "Downloading…" : "↓ .md"}
          </button>
          <button
            onClick={downloadDocx}
            disabled={downloading !== null}
            className="px-3 py-1.5 text-xs bg-violet-700 hover:bg-violet-600 disabled:opacity-50 rounded text-white transition-colors"
          >
            {downloading === "docx" ? "Downloading…" : "↓ .docx"}
          </button>
        </div>
      </div>

      {/* Copy / download errors */}
      {(copyError || downloadError) && (
        <div className="bg-red-950/40 border border-red-800 rounded px-4 py-3 text-red-400 text-sm">
          {copyError || downloadError}
        </div>
      )}

      {/* Document preview */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-8 max-h-[65vh] overflow-y-auto">
        {document ? (
          <div className="prose-sm">{renderPreview(document)}</div>
        ) : (
          <p className="text-slate-600 text-sm">No document content available.</p>
        )}
      </div>

      {/* Footer actions */}
      <div className="flex items-center gap-4 pt-2">
        <button
          onClick={onReset}
          className="text-slate-500 hover:text-slate-300 text-sm transition-colors"
        >
          ← Start over
        </button>
        <span className="text-slate-700 text-xs">
          {document ? `${document.length.toLocaleString()} characters` : ""}
        </span>
      </div>
    </div>
  );
}
