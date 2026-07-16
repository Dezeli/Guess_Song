import { FormEvent, useEffect, useMemo, useState } from "react";

import {
  approveYoutubeReviewCandidate,
  getReviewSession,
  listYoutubeReviewCandidates,
  rejectYoutubeReviewCandidate,
  reviewLogin,
  reviewLogout,
} from "../shared/api";
import type { YoutubeReviewCandidate } from "../shared/types";

const REVIEW_STATUSES = ["review_required", "discovered", "promoted", "rejected"];

export function ReviewView() {
  const [authenticated, setAuthenticated] = useState(false);
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState("review_required");
  const [candidates, setCandidates] = useState<YoutubeReviewCandidate[]>([]);
  const [total, setTotal] = useState(0);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [songTitle, setSongTitle] = useState("");
  const [artistName, setArtistName] = useState("");
  const [rejectReason, setRejectReason] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);

  const selectedCandidate = useMemo(
    () => candidates.find((candidate) => candidate.id === selectedId) ?? candidates[0] ?? null,
    [candidates, selectedId],
  );

  useEffect(() => {
    void getReviewSession()
      .then((session) => {
        setAuthenticated(session.authenticated);
      })
      .catch(() => setAuthenticated(false))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!authenticated) {
      return;
    }
    void loadCandidates(status);
  }, [authenticated, status]);

  useEffect(() => {
    if (!selectedCandidate) {
      setSongTitle("");
      setArtistName("");
      return;
    }
    setSelectedId(selectedCandidate.id);
    setSongTitle(selectedCandidate.song_title);
    setArtistName(selectedCandidate.artist_name);
    setRejectReason(selectedCandidate.review_reason);
  }, [selectedCandidate]);

  async function runAction<T>(action: () => Promise<T>, successMessage: string) {
    setMessage("");
    try {
      const result = await action();
      setMessage(successMessage);
      return result;
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Request failed.");
      return null;
    }
  }

  async function loadCandidates(nextStatus = status) {
    setLoading(true);
    const result = await runAction(() => listYoutubeReviewCandidates(nextStatus), "");
    if (result) {
      setCandidates(result.candidates);
      setTotal(result.total);
      setSelectedId(result.candidates[0]?.id ?? null);
    }
    setLoading(false);
  }

  async function handleLogin(event: FormEvent) {
    event.preventDefault();
    const session = await runAction(() => reviewLogin(password), "Review access unlocked.");
    if (session?.authenticated) {
      setAuthenticated(true);
      setPassword("");
    }
  }

  async function handleLogout() {
    await reviewLogout();
    setAuthenticated(false);
    setCandidates([]);
    setSelectedId(null);
  }

  async function handleApprove() {
    if (!selectedCandidate) {
      return;
    }
    const result = await runAction(
      () =>
        approveYoutubeReviewCandidate(selectedCandidate.id, {
          song_title: songTitle,
          artist_name: artistName,
        }),
      "Candidate approved.",
    );
    if (result) {
      await loadCandidates(status);
    }
  }

  async function handleReject() {
    if (!selectedCandidate) {
      return;
    }
    const result = await runAction(
      () => rejectYoutubeReviewCandidate(selectedCandidate.id, rejectReason),
      "Candidate rejected.",
    );
    if (result) {
      await loadCandidates(status);
    }
  }

  if (loading && !authenticated) {
    return (
      <main className="app-shell compact-shell">
        <section className="panel review-login">
          <p className="muted">Checking review session...</p>
        </section>
      </main>
    );
  }

  if (!authenticated) {
    return (
      <main className="app-shell compact-shell">
        <section className="panel review-login">
          <p className="eyebrow">Review</p>
          <h1>Candidate Review</h1>
          <form className="stack" onSubmit={handleLogin}>
            <label>
              Password
              <input
                autoFocus
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </label>
            <button type="submit">Unlock Review</button>
            {message ? <p className="message compact">{message}</p> : null}
          </form>
        </section>
      </main>
    );
  }

  return (
    <main className="app-shell review-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Review</p>
          <h1>YouTube Candidates</h1>
          <p className="muted">
            Showing {candidates.length} of {total} {status.replace("_", " ")} rows.
          </p>
        </div>
        <div className="button-row">
          <button className="secondary" type="button" onClick={() => void loadCandidates(status)}>
            Refresh
          </button>
          <button className="secondary" type="button" onClick={() => void handleLogout()}>
            Log out
          </button>
        </div>
      </header>

      {message ? <p className="message">{message}</p> : null}

      <section className="review-layout">
        <aside className="panel review-list-panel">
          <label>
            Status
            <select value={status} onChange={(event) => setStatus(event.target.value)}>
              {REVIEW_STATUSES.map((candidateStatus) => (
                <option key={candidateStatus} value={candidateStatus}>
                  {candidateStatus.replace("_", " ")}
                </option>
              ))}
            </select>
          </label>

          <div className="review-list">
            {candidates.map((candidate) => (
              <button
                className={candidate.id === selectedCandidate?.id ? "review-row selected" : "review-row"}
                key={candidate.id}
                type="button"
                onClick={() => setSelectedId(candidate.id)}
              >
                <span>
                  <strong>{candidate.song_title}</strong>
                  <small>{candidate.artist_name}</small>
                </span>
                <em>{candidate.official_score}</em>
              </button>
            ))}
            {!candidates.length ? <p className="muted">No candidates for this status.</p> : null}
          </div>
        </aside>

        <section className="panel review-detail-panel">
          {selectedCandidate ? (
            <div className="stack">
              <div className="review-detail-header">
                <div>
                  <h2>{selectedCandidate.youtube_title}</h2>
                  <p className="muted">{selectedCandidate.channel_title}</p>
                </div>
                <a className="external-link" href={selectedCandidate.youtube_url} target="_blank" rel="noreferrer">
                  Open YouTube
                </a>
              </div>

              <iframe
                className="review-youtube-player"
                src={`https://www.youtube.com/embed/${selectedCandidate.video_id}`}
                title={selectedCandidate.youtube_title}
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
              />

              <dl className="review-facts">
                <div>
                  <dt>Status</dt>
                  <dd>{selectedCandidate.status}</dd>
                </div>
                <div>
                  <dt>Score</dt>
                  <dd>{selectedCandidate.official_score}</dd>
                </div>
                <div>
                  <dt>Source</dt>
                  <dd>{selectedCandidate.source_type || "unknown"}</dd>
                </div>
                <div>
                  <dt>Uploaded</dt>
                  <dd>
                    {selectedCandidate.uploaded_year ?? "?"}.{selectedCandidate.uploaded_month ?? "?"}
                  </dd>
                </div>
                <div>
                  <dt>Duration</dt>
                  <dd>{formatDuration(selectedCandidate.duration_seconds)}</dd>
                </div>
                <div>
                  <dt>Views</dt>
                  <dd>{formatNumber(selectedCandidate.view_count)}</dd>
                </div>
              </dl>

              {selectedCandidate.review_reason ? (
                <p className="message compact">Review reason: {selectedCandidate.review_reason}</p>
              ) : null}

              <div className="form-grid">
                <label>
                  Song title
                  <input value={songTitle} onChange={(event) => setSongTitle(event.target.value)} />
                </label>
                <label>
                  Artist
                  <input value={artistName} onChange={(event) => setArtistName(event.target.value)} />
                </label>
              </div>

              <label>
                Reject reason
                <input value={rejectReason} onChange={(event) => setRejectReason(event.target.value)} />
              </label>

              <div className="button-row">
                <button type="button" onClick={() => void handleApprove()}>
                  Approve
                </button>
                <button className="secondary danger" type="button" onClick={() => void handleReject()}>
                  Reject
                </button>
              </div>
            </div>
          ) : (
            <p className="muted">Select a candidate to review.</p>
          )}
        </section>
      </section>
    </main>
  );
}

function formatDuration(seconds: number | null) {
  if (seconds === null) {
    return "unknown";
  }
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${minutes}:${remainder.toString().padStart(2, "0")}`;
}

function formatNumber(value: number | null) {
  return value === null ? "unknown" : new Intl.NumberFormat().format(value);
}
