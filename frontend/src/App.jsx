import { useState } from "react";
import UploadPage from "./pages/UploadPage";
import GeneratePage from "./pages/GeneratePage";
import PreviewPage from "./pages/PreviewPage";

const STEPS = ["upload", "generate", "preview"];

export default function App() {
  const [step, setStep] = useState("upload");
  const [jobId, setJobId] = useState(null);
  const [finalDoc, setFinalDoc] = useState(null);
  const [artifactType, setArtifactType] = useState("BRD");

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-mono">
      {/* Header */}
      <header className="border-b border-slate-800 px-8 py-4 flex items-center gap-6">
        <div className="flex items-center gap-3">
          <div className="w-7 h-7 bg-violet-500 rounded flex items-center justify-center text-xs font-bold text-white">
            DF
          </div>
          <span className="text-slate-100 font-semibold tracking-tight text-sm">DocuForge</span>
          <span className="text-slate-600 text-xs">/ agentic rag</span>
        </div>

        {/* Step breadcrumb */}
        <div className="flex items-center gap-2 ml-auto text-xs">
          {STEPS.map((s, i) => (
            <span key={s} className="flex items-center gap-2">
              <span className={`px-2 py-0.5 rounded ${step === s ? "bg-violet-500 text-white" : "text-slate-500"}`}>
                {i + 1}. {s}
              </span>
              {i < STEPS.length - 1 && <span className="text-slate-700">→</span>}
            </span>
          ))}
        </div>
      </header>

      {/* Pages */}
      <main className="max-w-4xl mx-auto px-8 py-10">
        {step === "upload" && (
          <UploadPage onComplete={() => setStep("generate")} />
        )}
        {step === "generate" && (
          <GeneratePage
            artifactType={artifactType}
            setArtifactType={setArtifactType}
            onComplete={(id, doc) => {
              setJobId(id);
              setFinalDoc(doc);
              setStep("preview");
            }}
          />
        )}
        {step === "preview" && (
          <PreviewPage
            jobId={jobId}
            document={finalDoc}
            artifactType={artifactType}
            onReset={() => {
              setStep("upload");
              setJobId(null);
              setFinalDoc(null);
            }}
          />
        )}
      </main>
    </div>
  );
}
