/** Submit once and poll: a timeout stops waiting, not the worker's job. */
const API_BASE = (import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000").replace(/\/$/, "");

export async function queuedFetch(url: string, options: RequestInit): Promise<Response> {
  const response = await fetch(url, { ...options, signal: AbortSignal.timeout(30_000) });
  if (response.status !== 202) return response;
  const job: { job_id: string } = await response.json();
  if (!/^[a-f0-9]{32}$/.test(job.job_id)) throw new Error("Invalid job response");
  const deadline = Date.now() + 15 * 60_000;
  while (Date.now() < deadline) {
    await new Promise(resolve => setTimeout(resolve, 1500));
    const status = await fetch(`${API_BASE}/jobs/${job.job_id}`, { signal: AbortSignal.timeout(10_000) });
    if (!status.ok) return status;
    const data = await status.json();
    if (data.status === "SUCCESS") return Response.json(data.result);
    if (data.status === "FAILURE" || data.status === "REVOKED") {
      throw new Error(data.error || "Analysis failed");
    }
  }
  throw new Error(`Still processing. Job ${job.job_id} can be checked through the API; the job was not cancelled.`);
}
