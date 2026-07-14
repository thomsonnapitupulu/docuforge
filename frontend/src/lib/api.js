const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export const api = {
  /**
   * Upload and ingest a reference document.
   * @param {File} file
   * @returns {Promise<IngestionResponse>}
   */
  async ingest(file) {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE_URL}/ingest`, { method: "POST", body: form });
    if (!res.ok) throw new Error((await res.json()).detail || "Ingest failed");
    return res.json();
  },

  /**
   * Start a generation job.
   * @param {"BRD"|"FSD"|"TSD"} artifactType
   * @returns {Promise<{job_id: string, status: string, message: string}>}
   */
  async generate(artifactType) {
    const res = await fetch(`${BASE_URL}/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ artifact_type: artifactType }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || "Generate failed");
    return res.json();
  },

  /**
   * Poll job status.
   * @param {string} jobId
   */
  async getJob(jobId) {
    const res = await fetch(`${BASE_URL}/jobs/${jobId}`);
    if (!res.ok) throw new Error("Job not found");
    return res.json();
  },

  /**
   * Returns an EventSource for SSE streaming.
   * @param {string} jobId
   * @returns {EventSource}
   */
  streamJob(jobId) {
    return new EventSource(`${BASE_URL}/jobs/${jobId}/stream`);
  },

  /**
   * Request cancellation of an in-flight generation job.
   * @param {string} jobId
   */
  async cancelJob(jobId) {
    const res = await fetch(`${BASE_URL}/jobs/${jobId}/cancel`, { method: "POST" });
    if (!res.ok) throw new Error((await res.json()).detail || "Cancel failed");
    return res.json();
  },

  /**
   * Get export download URL.
   * @param {string} jobId
   * @param {"md"|"docx"} format
   */
  exportUrl(jobId, format = "md") {
    return `${BASE_URL}/jobs/${jobId}/export?format=${format}`;
  },

  /**
   * Get vector store stats.
   */
  async getStats() {
    const res = await fetch(`${BASE_URL}/stats`);
    return res.json();
  },

  /**
   * Clear the vector store.
   */
  async clearStore() {
    const res = await fetch(`${BASE_URL}/clear`, { method: "DELETE" });
    return res.json();
  },
};
