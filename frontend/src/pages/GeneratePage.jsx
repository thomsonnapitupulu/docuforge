import { useState, useEffect, useRef } from "react";
import { api } from "../lib/api";

const ARTIFACT_TYPES = [
  {
    id: "BRD",
    label: "Business Requirements Document",
    desc: "Business objectives, stakeholders, scope, constraints.",
    color: "text-amber-400 border-amber-700 bg-amber-950/30",
  },
  {
    id: "FSD",
    label: "Functional Specification Document",
    desc: "Feature modules, user flows, edge cases, acceptance criteria.",
    color: "text-sky-400 border-sky-700 bg-sky-950/30",
  },
  {
    id: "TSD",
    label: "Technical Specification Document",
    desc: "Architecture, APIs, data models, infrastructure, security.",
    color: "text-violet-400 border-violet-700 bg-violet-950/30",
  },
];

export default function GeneratePage({ artifactType, setArtifactType, onComplete }) {
  const [jobId, setJobId] = useState(null);
  const [events, setEvents] = useState([]);
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);
  const [running, setRunning] = useState(false);
  const logRef = useRef(null);
  const esRef = useRef(null);

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [events]);

  const startGeneration = async () => {
    setRunning(true);
    setEvents([]);
    setError(null);

    try {
      const { job_id } = await api.generate(artifactType);
      setJobId(job_id);
      streamEvents(job_id);
    } catch (err) {
      setError(err.message);
      setRunning(false);
    }
  };

  const streamEvents = (id) => {
    if (esRef.current) esRef.current.close();
    const es = new EventSource(`http://localhost:8000/jobs/${id}/stream`);
    esRef.current = es;

    es.onmessage = (e) => {
      const data = JSON.parse(e.data);
      if (data.event) {
        setEvents(prev => [...prev, data.event]);
      }
      if (data.status) setStatus(data.status);
      if (data.done) {
        es.close();
        setRunning(false);
        if (data.status === "done") {
          // Fetch final document
          api.getJob(id).then(job => {
            onComplete(id, job.final_document);
          });
        }
        if (data.status === "error") {
          setError("Generation failed. Check backend logs.");
        }
      }
    };

    es.onerror = () => {
      es.close();
      setRunning(false);
      setError("SSE connection lost. Check if backend is running.");
    };
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold text-slate-100">Generate Document</h1>
        <p className="text-slate-400 text-sm mt-1">Select the artifact type and DocuForge will run the agentic loop.</p>
      </div>

      {/* Artifact type selector */}
      <div className="grid gap-3">
        {ARTIFACT_TYPES.map(type => (
          <button
            key={type.id}
            onClick={() => setArtifactType(type.id)}
            disabled={running}
            className={`border rounded-lg px-5 py-4 text-left transition-all ${
              artifactType === type.id
                ? type.color
                : "border-slate-800 bg-slate-900 hover:border-slate-700"
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="font-semibold text-sm">{type.id}</span>
              {artifactType === type.id && <span className="text-xs">✓ selected</span>}
            </div>
            <p className="text-xs text-slate-400 mt-0.5">{type.label}</p>
            <p className="text-xs text-slate-600 mt-1">{type.desc}</p>
          </button>
        ))}
      </div>

      {/* Generate button */}
      {!running && !status && (
        <button
          onClick={startGeneration}
          className="w-full py-3 bg-violet-600 hover:bg-violet-500 text-white text-sm rounded-lg font-semibold transition-colors"
        >
          Generate {artifactType} →
        </button>
      )}

      {/* Live event log */}
      {(events.length > 0 || running) && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-xs text-slate-500 uppercase tracking-wider">Generation Log</p>
            {running && (
              <span className="flex items-center gap-1.5 text-xs text-violet-400">
                <span className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-pulse"></span>
                Running…
              </span>
            )}
          </div>
          <div
            ref={logRef}
            className="bg-slate-900 border border-slate-800 rounded-lg p-4 h-64 overflow-y-auto space-y-1 font-mono text-xs"
          >
            {events.map((e, i) => (
              <p key={i} className="text-slate-300">{e}</p>
            ))}
            {running && <p className="text-slate-600 animate-pulse">▋</p>}
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="bg-red-950/40 border border-red-800 rounded px-4 py-3 text-red-400 text-sm">
          {error}
        </div>
      )}
    </div>
  );
}
