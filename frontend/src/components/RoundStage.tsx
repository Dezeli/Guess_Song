import type { RefObject } from "react";

import type { CurrentRound } from "../shared/types";

type RoundStageProps = {
  currentRound: CurrentRound | null;
  hostAction: string;
  hostActionDisabled: boolean;
  isHost: boolean;
  isRevealed: boolean;
  canForceSkipRound: boolean;
  canSkipRound: boolean;
  lastRoundStarted: CurrentRound | null;
  roundLabel: string;
  roomStatus: string;
  timerLabel: string | null;
  timerSeconds: number | null;
  playerHostRef: RefObject<HTMLDivElement>;
  playerMessage: string;
  onForceSkipRound: () => void;
  onHostPrimaryAction: () => void;
  onPlayClip: () => void;
  onSkipRound: () => void;
};

export function RoundStage({
  currentRound,
  hostAction,
  hostActionDisabled,
  isHost,
  isRevealed,
  canForceSkipRound,
  canSkipRound,
  lastRoundStarted,
  roundLabel,
  roomStatus,
  timerLabel,
  timerSeconds,
  playerHostRef,
  playerMessage,
  onForceSkipRound,
  onHostPrimaryAction,
  onPlayClip,
  onSkipRound,
}: RoundStageProps) {
  return (
    <section className="stage-panel panel">
      <div className="stage-header">
        <div>
          <p className="eyebrow">{roomStatus}</p>
          <h2>
            {getStageTitle(
              roomStatus,
              currentRound?.started_at ?? null,
              currentRound?.ended_at ?? null,
            )}
          </h2>
        </div>
        <div className="stage-status">
          {timerLabel && timerSeconds !== null ? (
            <div className="stage-timer">
              <span>{timerLabel}</span>
              <strong>{timerSeconds}초</strong>
            </div>
          ) : null}
          <strong className="round-counter">{roundLabel}</strong>
        </div>
      </div>

      {currentRound ? (
        <div className="round-box">
          <div className="youtube-audio-player" aria-hidden="true">
            <div className="youtube-player" ref={playerHostRef} />
          </div>
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
            <div className="music-placeholder" aria-hidden="true">
              <span className="music-bars">
                <i />
                <i />
                <i />
                <i />
              </span>
              <strong>음악 재생 중</strong>
            </div>
          )}
          <div className="round-meta">
            <span>시작 {currentRound.start_time_seconds}초</span>
            <span>재생 {currentRound.play_duration_seconds}초</span>
            <span>{currentRound.difficulty}</span>
          </div>
          <button type="button" className="secondary" onClick={onPlayClip}>
            클립 재생
          </button>
          {playerMessage ? <p className="muted">{playerMessage}</p> : null}
          {currentRound.answer_fields.length ? (
            <ul className="answer-fields">
              {currentRound.answer_fields.map((field) => (
                <li key={field.field_type} className={field.is_revealed ? "revealed" : undefined}>
                  <span>{field.field_type}</span>
                  <strong>{field.is_revealed ? field.answer : field.is_open ? "숨김" : "마감"}</strong>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : (
        <p className="muted">아직 선택된 라운드가 없습니다.</p>
      )}

      {isHost ? (
        <button
          type="button"
          className="primary-action"
          onClick={onHostPrimaryAction}
          disabled={hostActionDisabled}
        >
          {hostAction}
        </button>
      ) : (
        <p className="muted">방장이 게임을 시작하기를 기다리는 중입니다.</p>
      )}

      {lastRoundStarted ? (
        <p className="message compact">{lastRoundStarted.round_index + 1}라운드가 시작됐습니다.</p>
      ) : null}

      {currentRound?.started_at && !currentRound.ended_at ? (
        <div className="button-row round-actions">
          <button type="button" className="secondary" onClick={onSkipRound} disabled={!canSkipRound}>
            스킵 {currentRound.skip_count} / {currentRound.skip_target_count}
          </button>
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
    </section>
  );
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
