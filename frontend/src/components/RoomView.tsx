import type { FormEvent, RefObject } from "react";

import type { CurrentRound, Participant, RoomState, SubmitAnswerResponse } from "../shared/types";
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
  isHost: boolean;
  isRevealed: boolean;
  lastAnswerResult: SubmitAnswerResponse | null;
  lastRoundStarted: CurrentRound | null;
  message: string;
  orderedParticipants: Participant[];
  playerHostRef: RefObject<HTMLDivElement>;
  playerMessage: string;
  room: RoomState;
  socketStatus: string;
  onAnswerChange: (answer: string) => void;
  onForceSkipRound: () => void;
  onHostPrimaryAction: () => void;
  onLeaveRoom: () => void;
  onPlayClip: () => void;
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
  isHost,
  isRevealed,
  lastAnswerResult,
  lastRoundStarted,
  message,
  orderedParticipants,
  playerHostRef,
  playerMessage,
  room,
  socketStatus,
  onAnswerChange,
  onForceSkipRound,
  onHostPrimaryAction,
  onLeaveRoom,
  onPlayClip,
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
          hostAction={getHostAction(room.status)}
          isHost={isHost}
          isRevealed={isRevealed}
          canForceSkipRound={canForceSkipRound}
          canSkipRound={canSkipRound}
          lastRoundStarted={lastRoundStarted}
          roundLabel={roundLabel}
          roomStatus={room.status}
          playerHostRef={playerHostRef}
          playerMessage={playerMessage}
          onForceSkipRound={onForceSkipRound}
          onHostPrimaryAction={onHostPrimaryAction}
          onPlayClip={onPlayClip}
          onSkipRound={onSkipRound}
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

function getHostAction(status: string | undefined) {
  if (status === "waiting") {
    return "게임 시작";
  }
  if (status === "playing") {
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
