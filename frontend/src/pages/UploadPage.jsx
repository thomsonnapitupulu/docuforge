import { useState, useCallback } from "react";
import { api } from "../lib/api";

const ACCEPTED = [".pdf", ".docx", ".md", ".txt"];

export default function UploadPage({ onComplete }) {
  const [files, setFiles] = useState([]);
  const [results, setResults] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [stats, setStats] = useState(null);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setDragging(false);
    const dropped = Array.from(e.dataTransfer.files).filter(f =>
      ACCEPTED.some(ext => f.name.toLowerCase().endsWith(ext))
    );
    setFiles(prev => [...prev, ...dropped]);
  }, []);

  const handleFileInput = (e) => {
    const selected = Array.from(e.target.files);
    setFiles(prev => [...prev, ...selected]);
  };

  const handleIngest = async () => {
    if (!files.length) return;
    setUploading(true);
    const newResults = [];

    for (const file of files) {
      try {
        const result = await api.ingest(file);
        newResults.push({ ...result, ok: true });
      } catch (err) {
        newResults.push({ filename: file.name, ok: false, error: err.message });
      }
    }

    setResults(newResults);
    try {
      const statsData = await api.getStats();
      setStats(statsData);
    } catch {
      // Non-fatal: ingestion itself already succeeded/failed per-file above,
      // this only affects the stats tiles. Don't leave "Indexing…" stuck.
    } finally {
      setUploading(false);
    }
  };

  const allIngested = results.length > 0 && results.every(r => r.ok);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold text-slate-100">Upload Reference Documents</h1>
        <p className="text-slate-400 text-sm mt-1">
          Supports PDF, DOCX, Markdown, and plain text. Documents are chunked and indexed automatically.
        </p>
      </div>

      {/* Drop Zone */}
      <div
        onDrop={handleDrop}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        className={`border-2 border-dashed rounded-lg p-12 text-center transition-colors ${
          dragging ? "border-violet-400 bg-violet-950/30" : "border-slate-700 hover:border-slate-600"
        }`}
      >
        <div className="text-4xl mb-3">📂</div>
        <p className="text-slate-300 text-sm mb-2">Drag files here or</p>
        <label className="cursor-pointer text-violet-400 hover:text-violet-300 text-sm underline underline-offset-2">
          browse to upload
          <input type="file" multiple accept={ACCEPTED.join(",")} onChange={handleFileInput} className="hidden" />
        </label>
        <p className="text-slate-600 text-xs mt-2">{ACCEPTED.join(", ")}</p>
      </div>

      {/* File Queue */}
      {files.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-slate-500 uppercase tracking-wider">Queued ({files.length})</p>
          {files.map((f, i) => {
            const result = results[i];
            return (
              <div key={i} className="flex items-center justify-between bg-slate-900 border border-slate-800 rounded px-4 py-2.5 text-sm">
                <span className="text-slate-300 truncate max-w-xs">{f.name}</span>
                <div className="flex items-center gap-3 text-xs text-slate-500">
                  <span>{(f.size / 1024).toFixed(1)} KB</span>
                  {result && (
                    result.ok
                      ? <span className="text-emerald-400">✓ {result.chunks_created} chunks</span>
                      : <span className="text-red-400">✗ {result.error}</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 gap-4">
          <div className="bg-slate-900 border border-slate-800 rounded p-4">
            <p className="text-xs text-slate-500 mb-1">Parent Chunks Indexed</p>
            <p className="text-2xl font-bold text-violet-400">{stats.parent_chunks}</p>
          </div>
          <div className="bg-slate-900 border border-slate-800 rounded p-4">
            <p className="text-xs text-slate-500 mb-1">Child Chunks (Search Index)</p>
            <p className="text-2xl font-bold text-violet-400">{stats.child_chunks}</p>
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-4">
        <button
          onClick={handleIngest}
          disabled={!files.length || uploading}
          className="px-5 py-2 bg-violet-600 hover:bg-violet-500 disabled:bg-slate-800 disabled:text-slate-600 text-white text-sm rounded transition-colors"
        >
          {uploading ? "Indexing…" : "Index Documents"}
        </button>

        {allIngested && (
          <button
            onClick={onComplete}
            className="px-5 py-2 bg-emerald-700 hover:bg-emerald-600 text-white text-sm rounded transition-colors"
          >
            Continue to Generate →
          </button>
        )}

        {files.length > 0 && !uploading && (
          <button
            onClick={() => { setFiles([]); setResults([]); setStats(null); }}
            className="text-slate-500 hover:text-slate-300 text-sm"
          >
            Clear
          </button>
        )}
      </div>
    </div>
  );
}
