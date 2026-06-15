import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import {
  createRoom,
  getRoom,
  joinRoom,
  leaveRoom,
  listQuizPacks,
  moveToNextRound,
  setParticipantActive,
  setParticipantAway,
  startCurrentRound,
  startGame,
  submitAnswer,
} from "./shared/api";
import { openRoomSocket } from "./shared/roomSocket";
import type {
  AnswerFields,
  AnswerLimitMode,
  BalanceMode,
  ItemMode,
  PlayMode,
  QuizPack,
  RoomSettings,
  RoomSocketMessage,
  TeamAssignMode,
} from "./shared/types";
import { useRoomStore } from "./stores/roomStore";

const savedRoomCode = sessionStorage.getItem("guess_song_room_code") ?? "";

function App() {
  const {
    room,
    hostToken,
    participantToken,
    socketStatus,
    lastAnswerResult,
    lastRoundStarted,
    setRoom,
    setHostToken,
    setParticipantToken,
    setSocketStatus,
    setLastAnswerResult,
    setLastRoundStarted,
    reset,
  } = useRoomStore();

  const [quizPacks, setQuizPacks] = useState<QuizPack[]>([]);
  const [selectedPackId, setSelectedPackId] = useState<number | null>(null);
  const [hostNickname, setHostNickname] = useState("Host");
  const [joinCode, setJoinCode] = useState(savedRoomCode);
  const [joinNickname, setJoinNickname] = useState("Player");
  const [questionCount, setQuestionCount] = useState(2);
  const [answerLimitMode, setAnswerLimitMode] = useState<AnswerLimitMode>("FIVE_SECONDS");
  const [playMode, setPlayMode] = useState<PlayMode>("SOLO");
  const [teamAssignMode, setTeamAssignMode] = useState<TeamAssignMode>("SELF_SELECT");
  const [teamCount, setTeamCount] = useState(2);
  const [itemMode, setItemMode] = useState<ItemMode>("OFF");
  const [answerFields, setAnswerFields] = useState<AnswerFields>("TITLE_ONLY");
  const [balanceMode, setBalanceMode] = useState<BalanceMode>("OFF");
  const [allowLateJoin, setAllowLateJoin] = useState(true);
  const [roundTimeLimitSec, setRoundTimeLimitSec] = useState(20);
  const [answer, setAnswer] = useState("");
  const [message, setMessage] = useState("");
  const socketRef = useRef<WebSocket | null>(null);

  const isHost = Boolean(hostToken && room);
  const currentRound = room?.game?.current_round ?? null;
  const currentParticipant = useMemo(() => {
    if (!room) {
      return null;
    }
    if (hostToken) {
      return room.participants.find((participant) => participant.is_host) ?? null;
    }
    return room.participants.find((participant) => participant.nickname === joinNickname) ?? null;
  }, [hostToken, joinNickname, room]);
  const canSubmit = Boolean(
    participantToken
      && currentRound?.started_at
      && !currentRound.ended_at
      && currentParticipant?.status !== "AWAY"
      && currentParticipant?.status !== "LEFT",
  );
  const hostAction = getHostAction(room?.status, currentRound?.started_at ?? null);

  const orderedParticipants = useMemo(
    () => [...(room?.participants ?? [])].sort((a, b) => b.score - a.score || Number(b.is_host) - Number(a.is_host)),
    [room],
  );

  useEffect(() => {
    void listQuizPacks()
      .then((packs) => {
        setQuizPacks(packs);
        setSelectedPackId(packs[0]?.id ?? null);
      })
      .catch((error) => setMessage(error instanceof Error ? error.message : "Failed to load packs"));
  }, []);

  useEffect(() => {
    if (!room?.code) {
      return;
    }

    socketRef.current?.close();
    socketRef.current = openRoomSocket(
      room.code,
      (socketMessage: RoomSocketMessage) => {
        if (socketMessage.type === "room_state") {
          setRoom(socketMessage.room);
        }
        if (socketMessage.type === "round_started") {
          setLastRoundStarted(socketMessage.round);
        }
        if (socketMessage.type === "error") {
          setMessage(socketMessage.message);
        }
      },
      setSocketStatus,
    );

    return () => {
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [room?.code, setLastRoundStarted, setRoom, setSocketStatus]);

  useEffect(() => {
    if (!room?.code) {
      return;
    }

    const intervalId = window.setInterval(() => {
      void getRoom(room.code)
        .then((latestRoom) => setRoom(latestRoom))
        .catch(() => undefined);
    }, 1000);

    return () => window.clearInterval(intervalId);
  }, [room?.code, setRoom]);

  async function runAction<T>(action: () => Promise<T>, successMessage: string) {
    setMessage("");
    try {
      const result = await action();
      setMessage(successMessage);
      return result;
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Request failed");
      return null;
    }
  }

  async function handleCreateRoom(event: FormEvent) {
    event.preventDefault();
    if (!selectedPackId) {
      setMessage("Select a quiz pack first.");
      return;
    }

    const settings: RoomSettings = {
      question_count: questionCount,
      answer_limit_mode: answerLimitMode,
      play_mode: playMode,
      team_assign_mode: teamAssignMode,
      team_count: teamCount,
      item_mode: itemMode,
      answer_fields: answerFields,
      balance_mode: answerLimitMode === "FIRST_ONLY" ? balanceMode : "OFF",
      allow_late_join: allowLateJoin,
      round_time_limit_sec: roundTimeLimitSec,
      reveal_duration_sec: 3,
      countdown_sec: 3,
    };

    const created = await runAction(
      () =>
        createRoom({
          quiz_pack_id: selectedPackId,
          host_nickname: hostNickname,
          settings,
        }),
      "Room created.",
    );

    if (created) {
      setRoom(created.room);
      setHostToken(created.host_token);
      setParticipantToken(created.participant_token);
      setJoinCode(created.room.code);
      setLastAnswerResult(null);
      setLastRoundStarted(null);
    }
  }

  async function handleJoinRoom(event: FormEvent) {
    event.preventDefault();
    const joined = await runAction(
      () => joinRoom(joinCode.trim().toUpperCase(), joinNickname),
      "Joined room.",
    );

    if (joined) {
      setRoom(joined.room);
      setHostToken(null);
      setParticipantToken(joined.participant_token);
      setLastAnswerResult(null);
      setLastRoundStarted(null);
    }
  }

  async function handleRestoreRoom() {
    if (!joinCode.trim()) {
      return;
    }
    const loaded = await runAction(() => getRoom(joinCode.trim().toUpperCase()), "Room loaded.");
    if (loaded) {
      setRoom(loaded);
    }
  }

  async function handleHostPrimaryAction() {
    if (!room || !hostToken) {
      return;
    }

    if (room.status === "waiting") {
      const started = await runAction(() => startGame(room.code, hostToken), "Game started. Now start the round.");
      if (started) {
        setRoom(started.room);
      }
      return;
    }

    if (room.status === "playing" && !currentRound?.started_at) {
      await runAction(() => startCurrentRound(room.code, hostToken), "Round started. Players can answer now.");
      return;
    }

    if (room.status === "playing") {
      const next = await runAction(() => moveToNextRound(room.code, hostToken), "Moved to next round.");
      if (next) {
        setRoom(next.room);
        setAnswer("");
        setLastAnswerResult(null);
        setLastRoundStarted(null);
      }
    }
  }

  async function handleSubmitAnswer(event: FormEvent) {
    event.preventDefault();
    if (!room || !participantToken) {
      return;
    }

    const result = await runAction(
      () => submitAnswer(room.code, participantToken, answer),
      "Answer submitted.",
    );

    if (result) {
      setLastAnswerResult(result);
    }
  }

  function handleReset() {
    socketRef.current?.close();
    reset();
    setJoinCode("");
    setAnswer("");
    setMessage("Local room state cleared.");
  }

  async function handleLeaveRoom() {
    if (!room || !participantToken) {
      handleReset();
      return;
    }

    const left = await runAction(() => leaveRoom(room.code, participantToken), "Left room.");
    if (left) {
      handleReset();
    }
  }

  async function handleSetAway() {
    if (!room || !participantToken) {
      return;
    }

    const updated = await runAction(() => setParticipantAway(room.code, participantToken), "Set away.");
    if (updated) {
      setRoom(updated.room);
    }
  }

  async function handleSetActive() {
    if (!room || !participantToken) {
      return;
    }

    const updated = await runAction(() => setParticipantActive(room.code, participantToken), "Back to active.");
    if (updated) {
      setRoom(updated.room);
    }
  }

  if (!room) {
    return (
      <main className="app-shell compact-shell">
        <header className="topbar">
          <div>
            <p className="eyebrow">Guess Song</p>
            <h1>Create or Join a Room</h1>
          </div>
        </header>

        <section className="layout">
          <div className="panel">
            <h2>Create Room</h2>
            <form onSubmit={handleCreateRoom} className="stack">
              <label>
                Quiz pack
                <select
                  value={selectedPackId ?? ""}
                  onChange={(event) => setSelectedPackId(Number(event.target.value))}
                >
                  {quizPacks.map((pack) => (
                    <option key={pack.id} value={pack.id}>
                      {pack.name} ({pack.approved_question_count})
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Host nickname
                <input value={hostNickname} onChange={(event) => setHostNickname(event.target.value)} />
              </label>
              <label>
                Questions
                <input
                  min={1}
                  max={20}
                  type="number"
                  value={questionCount}
                  onChange={(event) => setQuestionCount(Number(event.target.value))}
                />
              </label>
              <label>
                Answer limit
                <select
                  value={answerLimitMode}
                  onChange={(event) => setAnswerLimitMode(event.target.value as AnswerLimitMode)}
                >
                  <option value="FIRST_ONLY">First only</option>
                  <option value="FIVE_SECONDS">Five seconds</option>
                  <option value="ALL_CORRECT">All correct</option>
                </select>
              </label>
              <label>
                Answer fields
                <select
                  value={answerFields}
                  onChange={(event) => setAnswerFields(event.target.value as AnswerFields)}
                >
                  <option value="TITLE_ONLY">Title only</option>
                  <option value="TITLE_AND_ARTIST">Title + artist</option>
                </select>
              </label>
              <label>
                Play mode
                <select value={playMode} onChange={(event) => setPlayMode(event.target.value as PlayMode)}>
                  <option value="SOLO">Solo</option>
                  <option value="TEAM">Team</option>
                </select>
              </label>
              {playMode === "TEAM" ? (
                <>
                  <label>
                    Team assignment
                    <select
                      value={teamAssignMode}
                      onChange={(event) => setTeamAssignMode(event.target.value as TeamAssignMode)}
                    >
                      <option value="SELF_SELECT">Self select</option>
                      <option value="RANDOM">Random</option>
                    </select>
                  </label>
                  <label>
                    Teams
                    <input
                      min={2}
                      max={4}
                      type="number"
                      value={teamCount}
                      onChange={(event) => setTeamCount(Number(event.target.value))}
                    />
                  </label>
                </>
              ) : null}
              <label>
                Round time
                <input
                  min={5}
                  max={120}
                  type="number"
                  value={roundTimeLimitSec}
                  onChange={(event) => setRoundTimeLimitSec(Number(event.target.value))}
                />
              </label>
              <label>
                Item mode
                <select value={itemMode} onChange={(event) => setItemMode(event.target.value as ItemMode)}>
                  <option value="OFF">Off</option>
                  <option value="ON">On</option>
                </select>
              </label>
              <label>
                Balance mode
                <select
                  value={answerLimitMode === "FIRST_ONLY" ? balanceMode : "OFF"}
                  onChange={(event) => setBalanceMode(event.target.value as BalanceMode)}
                  disabled={answerLimitMode !== "FIRST_ONLY"}
                >
                  <option value="OFF">Off</option>
                  <option value="ON">On</option>
                </select>
              </label>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={allowLateJoin}
                  onChange={(event) => setAllowLateJoin(event.target.checked)}
                />
                Allow late join
              </label>
              <button type="submit">Create Room</button>
            </form>
          </div>

          <div className="panel">
            <h2>Join Room</h2>
            <form onSubmit={handleJoinRoom} className="stack">
              <label>
                Room code
                <input
                  value={joinCode}
                  onChange={(event) => setJoinCode(event.target.value.toUpperCase())}
                  placeholder="ABC123"
                />
              </label>
              <label>
                Nickname
                <input value={joinNickname} onChange={(event) => setJoinNickname(event.target.value)} />
              </label>
              <div className="button-row">
                <button type="submit">Join Room</button>
                <button type="button" className="secondary" onClick={handleRestoreRoom}>
                  Load Room
                </button>
              </div>
            </form>
          </div>
        </section>
        {message ? <p className="message">{message}</p> : null}
      </main>
    );
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Room {room.code}</p>
          <h1>{room.quiz_pack?.name ?? "Music Quiz"}</h1>
        </div>
        <div className="button-row">
          <div className="connection">
            <span>Sync</span>
            <strong data-state={socketStatus}>{socketStatus}</strong>
          </div>
          <button type="button" className="secondary" onClick={handleReset}>
            Clear Local View
          </button>
          {participantToken ? (
            currentParticipant?.status === "AWAY" ? (
              <button type="button" className="secondary" onClick={handleSetActive}>
                Back
              </button>
            ) : (
              <button type="button" className="secondary" onClick={handleSetAway}>
                Away
              </button>
            )
          ) : null}
          <button type="button" className="secondary" onClick={handleLeaveRoom}>
            Leave Room
          </button>
        </div>
      </header>

      {message ? <p className="message">{message}</p> : null}

      <section className="room-focus">
        <div className="panel stage-panel">
          <div className="stage-header">
            <div>
              <p className="eyebrow">{room.status}</p>
              <h2>{getStageTitle(room.status, currentRound?.started_at ?? null)}</h2>
            </div>
            <strong className="round-counter">
              {room.game ? `${Math.min(room.game.current_round_index + 1, room.game.total_rounds)} / ${room.game.total_rounds}` : "-"}
            </strong>
          </div>

          {currentRound ? (
            <div className="round-box">
              <p>
                YouTube video ID <strong>{currentRound.youtube_video_id}</strong>
              </p>
              <p>
                Start {currentRound.start_time_seconds}s / Play {currentRound.play_duration_seconds}s
              </p>
              <p>Difficulty {currentRound.difficulty}</p>
            </div>
          ) : (
            <p className="muted">No round has been selected yet.</p>
          )}

          {isHost ? (
            <button
              type="button"
              className="primary-action"
              onClick={handleHostPrimaryAction}
              disabled={room.status === "finished"}
            >
              {hostAction}
            </button>
          ) : (
            <p className="muted">Waiting for the host.</p>
          )}

          {lastRoundStarted ? (
            <p className="message compact">Round {lastRoundStarted.round_index + 1} started. Answers are open.</p>
          ) : null}
        </div>

        <div className="panel">
          <h2>Submit Answer</h2>
          <p className="muted">
            {getAnswerHint(
              Boolean(participantToken),
              room.status,
              currentRound?.started_at ?? null,
              currentRound?.ended_at ?? null,
              currentParticipant?.status ?? null,
            )}
          </p>
          <form onSubmit={handleSubmitAnswer} className="stack">
            <input
              value={answer}
              onChange={(event) => setAnswer(event.target.value)}
              placeholder="Try LOVE DIVE for the first sample question"
              disabled={!canSubmit}
            />
            <button type="submit" disabled={!canSubmit || !answer.trim()}>
              Submit Answer
            </button>
          </form>
          {lastAnswerResult ? (
            <p className={lastAnswerResult.is_correct ? "result correct" : "result wrong"}>
              {lastAnswerResult.is_correct ? "Correct" : "Wrong"} / +{lastAnswerResult.score_awarded} / total{" "}
              {lastAnswerResult.total_score}
            </p>
          ) : null}
        </div>

        <div className="panel">
          <h2>Players</h2>
          <ul className="scoreboard">
            {orderedParticipants.map((participant) => (
              <li key={participant.id} className={participant.status !== "ACTIVE" ? "inactive" : undefined}>
                <span>
                  {participant.nickname}
                  {participant.is_host ? " (host)" : ""}
                  {participant.status === "AWAY" ? " (away)" : ""}
                  {participant.status === "LEFT" ? " (left)" : ""}
                </span>
                <strong>{participant.score}</strong>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </main>
  );
}

function getHostAction(status: string | undefined, startedAt: string | null) {
  if (status === "waiting") {
    return "Start Game";
  }
  if (status === "playing" && !startedAt) {
    return "Start Round";
  }
  if (status === "playing") {
    return "Next Round";
  }
  return "Game Finished";
}

function getStageTitle(status: string, startedAt: string | null) {
  if (status === "waiting") {
    return "Waiting for players";
  }
  if (status === "playing" && !startedAt) {
    return "Round is ready";
  }
  if (status === "playing") {
    return "Round is live";
  }
  return "Game finished";
}

function getAnswerHint(
  hasToken: boolean,
  status: string,
  startedAt: string | null,
  endedAt: string | null,
  participantStatus: string | null,
) {
  if (!hasToken) {
    return "Join or create a room before submitting.";
  }
  if (participantStatus === "AWAY") {
    return "You are away. Switch back before submitting.";
  }
  if (participantStatus === "LEFT") {
    return "You have left this room.";
  }
  if (status === "waiting") {
    return "The host needs to start the game first.";
  }
  if (!startedAt) {
    return "The host needs to start the round first.";
  }
  if (endedAt) {
    return "This round is closed. Wait for the next round.";
  }
  return "Answers are open.";
}

export default App;
