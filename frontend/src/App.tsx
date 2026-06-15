import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import {
  createRoom,
  getRoom,
  joinRoom,
  listQuizPacks,
  moveToNextRound,
  startCurrentRound,
  startGame,
  submitAnswer,
} from "./shared/api";
import { openRoomSocket } from "./shared/roomSocket";
import type { QuizPack, RoomSocketMessage } from "./shared/types";
import { useRoomStore } from "./stores/roomStore";

const savedRoomCode = localStorage.getItem("guess_song_room_code") ?? "";

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
  const [answer, setAnswer] = useState("");
  const [message, setMessage] = useState("");
  const socketRef = useRef<WebSocket | null>(null);

  const isHost = Boolean(hostToken && room);
  const currentRound = room?.game?.current_round ?? null;
  const canSubmit = Boolean(participantToken && currentRound?.started_at && !currentRound.ended_at);

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

    const created = await runAction(
      () =>
        createRoom({
          quiz_pack_id: selectedPackId,
          host_nickname: hostNickname,
          settings: { question_count: questionCount },
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

  async function handleStartGame() {
    if (!room || !hostToken) {
      return;
    }
    const started = await runAction(() => startGame(room.code, hostToken), "Game started.");
    if (started) {
      setRoom(started.room);
    }
  }

  async function handleStartRound() {
    if (!room || !hostToken) {
      return;
    }
    await runAction(() => startCurrentRound(room.code, hostToken), "Round started.");
  }

  async function handleNextRound() {
    if (!room || !hostToken) {
      return;
    }
    const next = await runAction(() => moveToNextRound(room.code, hostToken), "Moved to next round.");
    if (next) {
      setRoom(next.room);
      setAnswer("");
      setLastAnswerResult(null);
      setLastRoundStarted(null);
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

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Guess Song</p>
          <h1>Music Quiz Control Room</h1>
        </div>
        <div className="connection">
          <span>Socket</span>
          <strong data-state={socketStatus}>{socketStatus}</strong>
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
            <button type="submit">Create</button>
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
              <button type="submit">Join</button>
              <button type="button" className="secondary" onClick={handleRestoreRoom}>
                Load
              </button>
            </div>
          </form>
        </div>
      </section>

      {message ? <p className="message">{message}</p> : null}

      {room ? (
        <section className="room-grid">
          <div className="panel room-summary">
            <div className="room-header">
              <div>
                <p className="eyebrow">Room</p>
                <h2>{room.code}</h2>
              </div>
              <button type="button" className="secondary" onClick={handleReset}>
                Clear
              </button>
            </div>
            <dl className="facts">
              <div>
                <dt>Status</dt>
                <dd>{room.status}</dd>
              </div>
              <div>
                <dt>Pack</dt>
                <dd>{room.quiz_pack?.name ?? "-"}</dd>
              </div>
              <div>
                <dt>Round</dt>
                <dd>
                  {room.game ? `${room.game.current_round_index + 1} / ${room.game.total_rounds || "-"}` : "-"}
                </dd>
              </div>
            </dl>

            {isHost ? (
              <div className="host-controls">
                <button type="button" onClick={handleStartGame} disabled={room.status !== "waiting"}>
                  Start Game
                </button>
                <button type="button" onClick={handleStartRound} disabled={room.status !== "playing"}>
                  Start Round
                </button>
                <button type="button" onClick={handleNextRound} disabled={room.status !== "playing"}>
                  Next
                </button>
              </div>
            ) : null}
          </div>

          <div className="panel">
            <h2>Current Round</h2>
            {currentRound ? (
              <div className="round-box">
                <p>
                  Video ID <strong>{currentRound.youtube_video_id}</strong>
                </p>
                <p>
                  Start {currentRound.start_time_seconds}s · Play {currentRound.play_duration_seconds}s
                </p>
                <p>Difficulty {currentRound.difficulty}</p>
                <p>Started {currentRound.started_at ? "yes" : "no"}</p>
              </div>
            ) : (
              <p className="muted">No round selected.</p>
            )}
            {lastRoundStarted ? (
              <p className="message compact">Round {lastRoundStarted.round_index + 1} started.</p>
            ) : null}
          </div>

          <div className="panel">
            <h2>Submit Answer</h2>
            <form onSubmit={handleSubmitAnswer} className="stack">
              <input
                value={answer}
                onChange={(event) => setAnswer(event.target.value)}
                placeholder="Type song title or alias"
                disabled={!canSubmit}
              />
              <button type="submit" disabled={!canSubmit}>
                Submit
              </button>
            </form>
            {lastAnswerResult ? (
              <p className={lastAnswerResult.is_correct ? "result correct" : "result wrong"}>
                {lastAnswerResult.is_correct ? "Correct" : "Wrong"} · +{lastAnswerResult.score_awarded} · total{" "}
                {lastAnswerResult.total_score}
              </p>
            ) : null}
          </div>

          <div className="panel">
            <h2>Scoreboard</h2>
            <ul className="scoreboard">
              {orderedParticipants.map((participant) => (
                <li key={participant.id}>
                  <span>
                    {participant.nickname}
                    {participant.is_host ? " (host)" : ""}
                  </span>
                  <strong>{participant.score}</strong>
                </li>
              ))}
            </ul>
          </div>
        </section>
      ) : null}
    </main>
  );
}

export default App;
