import { useCallback, useEffect, useState } from "react";
import { analyze, health, type AnalyzeResponse } from "./api";

/** Input mode: upload a resume file or paste its raw text. */
type Mode = "file" | "text";

const ACCEPTED = ".pdf,.docx";

export default function App() {
  const [mode, setMode] = useState<Mode>("text");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [topK, setTopK] = useState(5);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  /** Backend reachability, probed on mount. */
  const [backendUp, setBackendUp] = useState<boolean | null>(null);

  useEffect(() => {
    health()
      .then(() => setBackendUp(true))
      .catch(() => setBackendUp(false));
  }, []);

  const canSubmit =
    mode === "file" ? file !== null : text.trim().length >= 30;

  const submit = useCallback(async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(
        await analyze(
          mode === "file" ? { file: file!, topK } : { text: text.trim(), topK }
        )
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [mode, file, text, topK]);

  const onFileChange = (f: File | null) => {
    setFile(f);
    setError(null);
    if (f && !/\.(pdf|docx)$/i.test(f.name)) {
      setError("فرمت فایل پشتیبانی نمی‌شود. فقط PDF یا DOCX مجاز است.");
    }
  };

  return (
    <main className="container">
      <header className="header">
        <h1>JobPulse</h1>
        <p>رزومه‌ات را با بازار کار ایران مقایسه کن.</p>
        {backendUp === false && (
          <p className="error">
            بک‌اند در دسترس نیست. آن را با <code>uv run fastapi dev app/main.py</code>{" "}
            در پوشه backend اجرا کنید.
          </p>
        )}
      </header>

      <section className="card">
        <div className="mode-switch" role="tablist">
          <button
            role="tab"
            aria-selected={mode === "text"}
            className={mode === "text" ? "active" : ""}
            onClick={() => setMode("text")}
          >
            متن رزومه
          </button>
          <button
            role="tab"
            aria-selected={mode === "file"}
            className={mode === "file" ? "active" : ""}
            onClick={() => setMode("file")}
          >
            آپلود فایل
          </button>
        </div>

        {mode === "text" ? (
          <textarea
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setError(null);
            }}
            placeholder="متن رزومه را اینجا بچسبانید… (حداقل ۳۰ کاراکتر)"
            rows={10}
          />
        ) : (
          <label className="file-drop">
            <input
              type="file"
              accept={ACCEPTED}
              onChange={(e) => onFileChange(e.target.files?.[0] ?? null)}
            />
            {file ? (
              <span>{file.name}</span>
            ) : (
              <span>فایل PDF یا DOCX رزومه را انتخاب کنید (حداکثر ۵ مگابایت)</span>
            )}
          </label>
        )}

        <div className="controls">
          <label>
            تعداد آگهی‌های ارسالی به AI:
            <select
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
            >
              {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <button
            className="submit"
            disabled={!canSubmit || loading}
            onClick={submit}
          >
            {loading ? "در حال تحلیل…" : "تحلیل رزومه"}
          </button>
        </div>

        {error && <p className="error">{error}</p>}
      </section>

      {result && <Results data={result} />}
    </main>
  );
}

function Results({ data }: { data: AnalyzeResponse }) {
  const { gap_analysis: gap, matched_jobs: jobs } = data;
  return (
    <>
      <section className="card">
        <h2>تحلیل شکاف مهارتی</h2>
        <div className="skills">
          <div>
            <h3 className="match">مهارت‌های منطبق</h3>
            <Skills list={gap.matching_skills} tone="match" />
          </div>
          <div>
            <h3 className="missing">مهارت‌های جاافتاده</h3>
            <Skills list={gap.missing_skills} tone="missing" />
          </div>
        </div>
        {gap.summary && <p className="summary">{gap.summary}</p>}
      </section>

      <section className="card">
        <h2>آگهی‌های منطبق ({jobs.length})</h2>
        {jobs.length === 0 ? (
          <p>هیچ آگهی منطبقی پیدا نشد.</p>
        ) : (
          <ul className="jobs">
            {jobs.map((j) => (
              <li key={j.id}>
                <div className="job-head">
                  <a href={j.source_url} target="_blank" rel="noreferrer">
                    {j.title}
                  </a>
                  <span className="company">{j.company}</span>
                  <span
                    className="score"
                    title="امتیاز شباهت با رزومه"
                  >
                    {(j.similarity_score * 100).toFixed(0)}٪
                  </span>
                </div>
                <p className="desc">{j.description_clean}</p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}

function Skills({
  list,
  tone,
}: {
  list: string[];
  tone: "match" | "missing";
}) {
  if (list.length === 0) return <p>—</p>;
  return (
    <div className="chips">
      {list.map((s) => (
        <span key={s} className={`chip ${tone}`}>
          {s}
        </span>
      ))}
    </div>
  );
}
