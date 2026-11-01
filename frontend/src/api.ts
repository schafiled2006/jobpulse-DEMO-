/**
 * Typed client for the JobPulse backend API.
 *
 * Mirrors the Pydantic contracts in backend/app/schemas/:
 *  - POST /analyze  → AnalyzeResponse (matched_jobs + gap_analysis)
 *  - Errors are `{ detail: string }` with Persian messages.
 */

const API_BASE = "http://127.0.0.1:8000";

/** One job posting retrieved from the vector DB (backend MatchedJob). */
export interface MatchedJob {
  id: string;
  title: string;
  company: string;
  /** Cosine similarity between resume and posting, 0.0–1.0. */
  similarity_score: number;
  source_url: string;
  description_clean: string;
}

/** LLM-generated skill-gap report (backend GapAnalysis). */
export interface GapAnalysis {
  matching_skills: string[];
  missing_skills: string[];
  summary: string;
}

/** Root response of POST /analyze (backend AnalyzeResponse). */
export interface AnalyzeResponse {
  matched_jobs: MatchedJob[];
  gap_analysis: GapAnalysis;
}

/** Error payload the backend sends on 400/413/415/429 (backend ErrorDetail). */
interface ApiError {
  detail: string;
}

export interface AnalyzeRequest {
  /** Raw pasted resume text (mutually exclusive with file). */
  text?: string;
  /** Uploaded resume file, PDF or DOCX (mutually exclusive with text). */
  file?: File;
  /** Number of top postings sent to Gemini; backend accepts 1–10. */
  topK: number;
}

/** Payload of GET /health (backend HealthResponse). */
export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  environment: string;
}

/** GET /health — resolves only when the backend answers. */
export async function health(): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error(`backend down (HTTP ${res.status})`);
  return (await res.json()) as HealthResponse;
}

/**
 * Call POST /analyze. Throws an Error whose message is the backend's
 * Persian `detail` string when the request fails.
 */
export async function analyze(req: AnalyzeRequest): Promise<AnalyzeResponse> {
  const form = new FormData();
  if (req.file) {
    form.append("file", req.file);
  } else if (req.text) {
    form.append("text", req.text);
  } else {
    throw new Error("لطفاً یا فایل رزومه یا متن آن را وارد کنید.");
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE}/analyze?top_k=${req.topK}`, {
      method: "POST",
      body: form,
    });
  } catch {
    throw new Error(
      "ارتباط با سرور برقرار نشد. مطمئن شوید بک‌اند روی http://127.0.0.1:8000 اجرا می‌شود."
    );
  }

  if (!res.ok) {
    let detail = `خطای ${res.status}`;
    try {
      const body = (await res.json()) as ApiError;
      if (body?.detail) detail = body.detail;
    } catch {
      // Non-JSON error body — keep the generic status message.
    }
    throw new Error(detail);
  }

  return (await res.json()) as AnalyzeResponse;
}
