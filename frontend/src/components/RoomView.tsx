import type { FormEvent } from "react";

import type {
  CurrentRound,
  Participant,
  QuestionScopeOptions,
  QualityReportReason,
  RoomSettings,
  RoomState,
  SubmitAnswerResponse,
} from "../shared/types";
import { AnswerPanel } from "./AnswerPanel";
import { HostSettingsPanel } from "./HostSettingsPanel";
import { PlayersPanel } from "./PlayersPanel";
import { RoundStage } from "./RoundStage";

type RoomViewProps = {
  answer: string;
  answerHint: string;
  canForceSkipRound: boolean;
  canSkipRound: boolean;
  canSubmit: boolean;
  currentParticipant: Participant | null;
  currentRound: CurrentRound | null;
  hostActionDisabled: boolean;
  isHost: boolean;
  isRevealed: boolean;
  lastAnswerResult: SubmitAnswerResponse | null;
  lastRoundStarted: CurrentRound | null;
  message: string;
  orderedParticipants: Participant[];
  reportMessage: string;
  room: RoomState;
  quizScopes: QuestionScopeOptions;
  shareUrl: string;
  socketStatus: string;
  timerLabel: string | null;
  timerSeconds: number | null;
  onAnswerChange: (answer: string) => void;
  onForceSkipRound: () => void;
  onHostPrimaryAction: () => void;
  onKickParticipant: (participantId: number) => void;
  onLeaveRoom: () => void;
  onReportRound: (reason: QualityReportReason, detail: string) => void;
  onSetActive: () => void;
  onSetAway: () => void;
  onSkipRound: () => void;
  onSubmitAnswer: (event: FormEvent) => void;
  onTeamChange: (teamId: number) => void;
  onUpdateRoomSettings: (input: {
    quiz_pack_id?: number | null;
    settings: Partial<RoomSettings>;
  }) => void;
};

export function RoomView({
  answer,
  answerHint,
  canForceSkipRound,
  canSkipRound,
  canSubmit,
  currentParticipant,
  currentRound,
  hostActionDisabled,
  isHost,
  isRevealed,
  lastAnswerResult,
  lastRoundStarted,
  message,
  orderedParticipants,
  reportMessage,
  room,
  quizScopes,
  shareUrl,
  socketStatus,
  timerLabel,
  timerSeconds,
  onAnswerChange,
  onForceSkipRound,
  onHostPrimaryAction,
  onKickParticipant,
  onLeaveRoom,
  onReportRound,
  onSetActive,
  onSetAway,
  onSkipRound,
  onSubmitAnswer,
  onTeamChange,
  onUpdateRoomSettings,
}: RoomViewProps) {
  const roundLabel = room.game
    ? `${Math.min(room.game.current_round_index + 1, room.game.total_rounds)} / ${room.game.total_rounds}`
    : "-";
  const isWaiting = room.status === "waiting";
  const isFinished = room.status === "finished";

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">{room.code}</p>
          <div className="room-title-line">
            <h1 className="room-title">{room.title}</h1>
            <button
              type="button"
              className="secondary invite-copy-button"
              onClick={() => void navigator.clipboard?.writeText(shareUrl)}
            >
              초대 링크 복사
            </button>
          </div>
        </div>
        <div className="button-row">
          <div
            className="network-status"
            data-state={socketStatus}
            role="status"
            aria-label={`네트워크 ${getNetworkLabel(socketStatus)}`}
            title={`네트워크 ${getNetworkLabel(socketStatus)}`}
          >
            <span className="signal-icon" aria-hidden="true">
              <i />
              <i />
              <i />
            </span>
          </div>
          <button type="button" className="leave-text-button" onClick={onLeaveRoom}>
            나가기
          </button>
        </div>
      </header>

      {isWaiting ? (
        <section className="room-focus waiting-focus">
          <HostSettingsPanel
            editable={isHost}
            quizScopes={quizScopes}
            room={room}
            onUpdate={onUpdateRoomSettings}
          />
          <PlayersPanel
            currentParticipantId={currentParticipant?.id ?? null}
            lobbyAction={
              isHost ? (
                <button
                  type="button"
                  className="start-game-button"
                  onClick={onHostPrimaryAction}
                  disabled={hostActionDisabled}
                >
                  게임 시작
                </button>
              ) : (
                <div className="start-waiting-placeholder">방장이 시작하기를 대기 중</div>
              )
            }
            orderedParticipants={orderedParticipants}
            room={room}
            showScores={false}
            canKick={isHost}
            onKickParticipant={onKickParticipant}
            onTeamChange={onTeamChange}
          />
        </section>
      ) : isFinished ? (
        <section className="room-focus finished-focus">
          <PlayersPanel
            currentParticipantId={currentParticipant?.id ?? null}
            orderedParticipants={orderedParticipants}
            room={room}
          />
          {isHost ? (
            <div className="finished-action-row">
              <button
                type="button"
                className="start-game-button"
                onClick={onHostPrimaryAction}
                disabled={hostActionDisabled}
              >
                대기실로
              </button>
            </div>
          ) : null}
        </section>
      ) : (
        <section className="room-focus">
          <RoundStage
            currentRound={currentRound}
            isHost={isHost}
            isRevealed={isRevealed}
            currentParticipantStatus={currentParticipant?.status ?? null}
            canForceSkipRound={canForceSkipRound}
            canSkipRound={canSkipRound}
            roundLabel={roundLabel}
            roomStatus={room.status}
            timerLabel={timerLabel}
            timerSeconds={timerSeconds}
            onForceSkipRound={onForceSkipRound}
            onReportRound={onReportRound}
            onSetActive={onSetActive}
            onSetAway={onSetAway}
            onSkipRound={onSkipRound}
            reportMessage={reportMessage}
          />
          {room.status === "playing" ? (
            <AnswerPanel
              answer={answer}
              canSubmit={canSubmit}
              hint={answerHint}
              submissions={currentRound?.answer_submissions ?? []}
              onAnswerChange={onAnswerChange}
              onSubmitAnswer={onSubmitAnswer}
            />
          ) : null}
          <PlayersPanel
            currentParticipantId={currentParticipant?.id ?? null}
            orderedParticipants={orderedParticipants}
            room={room}
          />
        </section>
      )}
      <footer className="lobby-footer room-footer">
        <div className="footer-main">
          <span>© 2026 한소절 · Dezeli</span>
          <span className="mail-text">✉️ haterecursive@gmail.com</span>
        </div>
        <small>YouTube 음악 영상 및 음원은 비상업적 목적으로만 사용됩니다.</small>
      </footer>
    </main>
  );
}

function getNetworkLabel(status: string) {
  if (status === "open") {
    return "연결됨";
  }
  if (status === "connecting") {
    return "연결 중";
  }
  if (status === "error") {
    return "오류";
  }
  if (status === "closed") {
    return "끊김";
  }
  return "대기";
}
