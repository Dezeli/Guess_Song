import { useEffect, useRef, useState } from "react";

import type { CurrentRound, QualityReportReason } from "../shared/types";
import { loadYouTubeApi } from "../shared/youtubePlayer";

type RoundStageProps = {
  currentRound: CurrentRound | null;
  isHost: boolean;
  isRevealed: boolean;
  currentParticipantStatus: string | null;
  canForceSkipRound: boolean;
  canSkipRound: boolean;
  roundLabel: string;
  roomStatus: string;
  timerLabel: string | null;
  timerSeconds: number | null;
  onForceSkipRound: () => void;
  onReportRound: (reason: QualityReportReason, detail: string) => void;
  onSetActive: () => void;
  onSetAway: () => void;
  onSkipRound: () => void;
  reportMessage: string;
};

const REPORT_REASONS: Array<{ value: QualityReportReason; label: string }> = [
  { value: "wrong_title", label: "제목 오류" },
  { value: "wrong_artist", label: "가수 오류" },
  { value: "wrong_audio", label: "음원 오류" },
  { value: "unavailable", label: "재생 불가" },
  { value: "unofficial_video", label: "비공식 영상" },
  { value: "other", label: "기타" },
];

export function RoundStage({
  currentRound,
  isHost,
  isRevealed,
  currentParticipantStatus,
  canForceSkipRound,
  canSkipRound,
  roundLabel,
  roomStatus,
  timerLabel,
  timerSeconds,
  onForceSkipRound,
  onReportRound,
  onSetActive,
  onSetAway,
  onSkipRound,
  reportMessage,
}: RoundStageProps) {
  const [reportReason, setReportReason] = useState<QualityReportReason>("wrong_audio");
  const [reportDetail, setReportDetail] = useState("");
  const [playerError, setPlayerError] = useState("");
  const canReport = Boolean(currentRound?.started_at);
  const revealedAnswers = currentRound?.answer_fields.filter((field) => field.is_revealed && field.answer) ?? [];

  return (
    <section className="stage-panel panel">
      <div className="stage-header">
        <div>
          <div className="round-heading-line">
            <strong className="round-progress-label">{roundLabel}</strong>
            <div className="round-heading-copy">
              <span className="round-state-label">{getRoomStatusLabel(roomStatus)}</span>
              <h2>
                {getStageTitle(
                  roomStatus,
                  currentRound?.started_at ?? null,
                  currentRound?.ended_at ?? null,
                )}
              </h2>
            </div>
          </div>
        </div>
        <div className="stage-status">
          {timerLabel && timerSeconds !== null ? (
            <div className="stage-timer">
              <span>{timerLabel}</span>
              <strong>{timerSeconds}초</strong>
            </div>
          ) : null}
        </div>
      </div>

      {currentRound ? (
        <div className="round-box">
          <div className="round-media">
            {isRevealed ? (
              <iframe
                key={`${currentRound.round_id}-${currentRound.ended_at ?? "revealed"}`}
                className="youtube-reveal-player"
                title="Revealed music video"
                src={`https://www.youtube.com/embed/${currentRound.youtube_video_id}?start=${currentRound.start_time_seconds}&autoplay=1&playsinline=1&rel=0`}
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                allowFullScreen
              />
            ) : (
              <div className="masked-youtube-shell">
                {currentRound.started_at ? (
                  <HiddenRoundPlayer currentRound={currentRound} onError={setPlayerError} />
                ) : null}
                <div className="music-placeholder" aria-hidden="true">
                  <span className="music-bars">
                    <i />
                    <i />
                    <i />
                    <i />
                  </span>
                  <strong>{currentRound.started_at ? "음악 재생 중" : "라운드 시작 대기 중"}</strong>
                  {playerError ? <small>{playerError}</small> : null}
                </div>
              </div>
            )}
            {revealedAnswers.length ? (
              <div className="answer-reveal-overlay">
                {revealedAnswers.map((field) => (
                  <div key={field.field_type}>
                    <span>{getAnswerFieldLabel(field.field_type)}</span>
                    <strong>{field.answer}</strong>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      ) : (
        <p className="muted">아직 선택된 라운드가 없습니다.</p>
      )}

      {currentRound?.started_at ? (
        <div className="button-row round-actions">
          <button type="button" className="secondary" onClick={onSkipRound} disabled={!canSkipRound}>
            스킵 {currentRound.skip_count} / {currentRound.skip_target_count}
          </button>
          {currentParticipantStatus === "AWAY" ? (
            <button type="button" className="secondary" onClick={onSetActive}>
              자리비움 해제
            </button>
          ) : (
            <button type="button" className="secondary" onClick={onSetAway}>
              자리비움
            </button>
          )}
          {isHost ? (
            <button
              type="button"
              className="secondary danger"
              onClick={onForceSkipRound}
              disabled={!canForceSkipRound}
            >
              강제 스킵
            </button>
          ) : null}
        </div>
      ) : null}

      {currentRound ? (
        <div className="quality-report-box">
          <h3>문제 신고</h3>
          <div className="form-grid">
            <label>
              사유
              <select
                value={reportReason}
                onChange={(event) => setReportReason(event.target.value as QualityReportReason)}
              >
                {REPORT_REASONS.map((reason) => (
                  <option key={reason.value} value={reason.value}>
                    {reason.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              내용
              <input
                value={reportDetail}
                onChange={(event) => setReportDetail(event.target.value)}
                placeholder="간단히 적어주세요"
              />
            </label>
          </div>
          <button
            type="button"
            className="secondary danger"
            disabled={!canReport}
            onClick={() => {
              onReportRound(reportReason, reportDetail);
              setReportDetail("");
            }}
          >
            신고
          </button>
          {reportMessage ? <p className="message compact">{reportMessage}</p> : null}
        </div>
      ) : null}
    </section>
  );
}

function HiddenRoundPlayer({
  currentRound,
  onError,
}: {
  currentRound: CurrentRound;
  onError: (message: string) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const playerRef = useRef<YT.Player | null>(null);
  const timersRef = useRef<number[]>([]);
  const segmentsKey = currentRound.playback_segments
    .map((segment) => `${segment.start_time_seconds}:${segment.duration_seconds}`)
    .join("|");

  useEffect(() => {
    let cancelled = false;
    const container = containerRef.current;

    function clearTimers() {
      timersRef.current.forEach((timerId) => window.clearTimeout(timerId));
      timersRef.current = [];
    }

    function scheduleSegment(player: YT.Player, segmentIndex: number) {
      const segment = currentRound.playback_segments[segmentIndex];
      if (!segment) {
        player.pauseVideo();
        return;
      }

      player.loadVideoById({
        videoId: currentRound.youtube_video_id,
        startSeconds: segment.start_time_seconds,
      });
      player.playVideo();

      const stopTimer = window.setTimeout(() => {
        player.pauseVideo();
        if (segmentIndex + 1 < currentRound.playback_segments.length) {
          const nextTimer = window.setTimeout(() => {
            scheduleSegment(player, segmentIndex + 1);
          }, 1000);
          timersRef.current.push(nextTimer);
        }
      }, segment.duration_seconds * 1000);
      timersRef.current.push(stopTimer);
    }

    void loadYouTubeApi().then(() => {
      if (cancelled || !container) {
        return;
      }

      const player = new window.YT.Player(container, {
        videoId: currentRound.youtube_video_id,
        playerVars: {
          autoplay: 1,
          controls: 0,
          disablekb: 1,
          modestbranding: 1,
          playsinline: 1,
          rel: 0,
        },
        events: {
          onReady: () => {
            if (cancelled) {
              return;
            }
            onError("");
            player.unMute();
            scheduleSegment(player, 0);
          },
          onError: (event) => {
            if (cancelled) {
              return;
            }
            onError(getYouTubeErrorMessage(event.data));
          },
        },
      });
      playerRef.current = player;
    });

    return () => {
      cancelled = true;
      clearTimers();
      playerRef.current?.stopVideo();
      playerRef.current?.destroy();
      playerRef.current = null;
    };
  }, [currentRound.round_id, currentRound.started_at, currentRound.youtube_video_id, onError, segmentsKey]);

  return <div ref={containerRef} className="masked-youtube-player" title="Hidden music video" />;
}

function getYouTubeErrorMessage(errorCode: number) {
  if (errorCode === 101 || errorCode === 150) {
    return "외부 재생이 제한된 영상입니다.";
  }
  if (errorCode === 100) {
    return "재생할 수 없는 영상입니다.";
  }
  return "영상 재생에 실패했습니다.";
}

function getRoomStatusLabel(status: string) {
  if (status === "playing") {
    return "진행 중";
  }
  if (status === "finished") {
    return "종료";
  }
  return "대기";
}

function getAnswerFieldLabel(fieldType: string) {
  if (fieldType === "artist") {
    return "가수";
  }
  return "제목";
}

function getStageTitle(status: string, startedAt: string | null, endedAt: string | null) {
  if (status === "waiting") {
    return "참가자 대기 중";
  }
  if (status === "playing" && !startedAt) {
    return "곧 시작";
  }
  if (status === "playing" && endedAt) {
    return "정답 공개 중";
  }
  if (status === "playing" && startedAt) {
    return "라운드 진행 중";
  }
  return "게임 종료";
}
