import type { FormEvent } from "react";

import type {
  CurrentRound,
  Participant,
  QualityReportReason,
  RoomState,
  SubmitAnswerResponse,
} from "../shared/types";
import { AnswerPanel } from "./AnswerPanel";
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
  roundActionHint: string | null;
  room: RoomState;
  socketStatus: string;
  timerLabel: string | null;
  timerSeconds: number | null;
  onAnswerChange: (answer: string) => void;
  onForceSkipRound: () => void;
  onHostPrimaryAction: () => void;
  onLeaveRoom: () => void;
  onReportRound: (reason: QualityReportReason, detail: string) => void;
  onReset: () => void;
  onSetActive: () => void;
  onSetAway: () => void;
  onSkipRound: () => void;
  onSubmitAnswer: (event: FormEvent) => void;
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
  roundActionHint,
  room,
  socketStatus,
  timerLabel,
  timerSeconds,
  onAnswerChange,
  onForceSkipRound,
  onHostPrimaryAction,
  onLeaveRoom,
  onReportRound,
  onReset,
  onSetActive,
  onSetAway,
  onSkipRound,
  onSubmitAnswer,
}: RoomViewProps) {
  const roundLabel = room.game
    ? `${Math.min(room.game.current_round_index + 1, room.game.total_rounds)} / ${room.game.total_rounds}`
    : "-";

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">방 {room.code}</p>
          <h1>{room.quiz_pack?.name ?? "음악 퀴즈"}</h1>
        </div>
        <div className="button-row">
          <div className="connection">
            <span>동기화</span>
            <strong data-state={socketStatus}>{getSocketLabel(socketStatus)}</strong>
          </div>
          <button type="button" className="secondary" onClick={onReset}>
            화면 초기화
          </button>
          {currentParticipant ? (
            currentParticipant.status === "AWAY" ? (
              <button type="button" className="secondary" onClick={onSetActive}>
                돌아오기
              </button>
            ) : (
              <button type="button" className="secondary" onClick={onSetAway}>
                자리비움
              </button>
            )
          ) : null}
          <button type="button" className="secondary" onClick={onLeaveRoom}>
            나가기
          </button>
        </div>
      </header>

      {message ? <p className="message">{message}</p> : null}

      <section className="room-focus">
        <RoundStage
          currentRound={currentRound}
          hostAction={getHostAction(room, currentRound)}
          hostActionDisabled={hostActionDisabled}
          isHost={isHost}
          isRevealed={isRevealed}
          canForceSkipRound={canForceSkipRound}
          canSkipRound={canSkipRound}
          lastRoundStarted={lastRoundStarted}
          roundLabel={roundLabel}
          roundActionHint={roundActionHint}
          roomStatus={room.status}
          timerLabel={timerLabel}
          timerSeconds={timerSeconds}
          onForceSkipRound={onForceSkipRound}
          onHostPrimaryAction={onHostPrimaryAction}
          onReportRound={onReportRound}
          onSkipRound={onSkipRound}
          reportMessage={reportMessage}
        />
        <AnswerPanel
          answer={answer}
          canSubmit={canSubmit}
          hint={answerHint}
          lastAnswerResult={lastAnswerResult}
          onAnswerChange={onAnswerChange}
          onSubmitAnswer={onSubmitAnswer}
        />
        <PlayersPanel orderedParticipants={orderedParticipants} room={room} />
      </section>
    </main>
  );
}

function getHostAction(room: RoomState, currentRound: CurrentRound | null) {
  if (room.status === "waiting") {
    return "게임 시작";
  }

  if (room.status === "playing" && currentRound?.ended_at) {
    const isLastRound = currentRound.round_index + 1 >= (room.game?.total_rounds ?? 0);
    return isLastRound ? "결과 보기" : "다음 라운드";
  }

  if (room.status === "playing") {
    return "게임 진행 중";
  }

  return "게임 종료";
}

function getSocketLabel(status: string) {
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
