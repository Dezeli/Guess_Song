import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { LobbyView } from "./components/LobbyView";
import { ReviewView } from "./components/ReviewView";
import { RoomView } from "./components/RoomView";
import {
  createRoom,
  forceSkipCurrentRound,
  getCurrentParticipant,
  getRandomNickname,
  getRoom,
  joinRoom,
  kickParticipant,
  leaveRoom,
  leaveRoomOnPageExit,
  listQuizPacks,
  listQuizScopes,
  moveToNextRound,
  reportCurrentRound,
  returnRoomToLobby,
  setParticipantActive,
  setParticipantAway,
  skipCurrentRound,
  startGame,
  submitAnswer,
  updateMyTeam,
  updateRoomSettings,
} from "./shared/api";
import { openRoomSocket } from "./shared/roomSocket";
import type {
  CurrentRound,
  QualityReportReason,
  QuestionScopeOptions,
  QuizPack,
  RoomSettings,
  RoomSocketMessage,
  SubmitAnswerResponse,
} from "./shared/types";
import { useRoomStore } from "./stores/roomStore";

const savedRoomCode = sessionStorage.getItem("guess_song_room_code") ?? "";
const initialRouteRoomCode = getRoomCodeFromPath(window.location.pathname);

function App() {
  if (window.location.pathname === "/review") {
    return <ReviewView />;
  }

  const {
    room,
    hostToken,
    participantToken,
    participantId,
    socketStatus,
    lastAnswerResult,
    lastRoundStarted,
    setRoom,
    setHostToken,
    setParticipantToken,
    setParticipantId,
    setSocketStatus,
    setLastAnswerResult,
    setLastRoundStarted,
    reset,
  } = useRoomStore();

  const [quizPacks, setQuizPacks] = useState<QuizPack[]>([]);
  const [quizScopes, setQuizScopes] = useState<QuestionScopeOptions>({ years: [], artists: [] });
  const [selectedPackId, setSelectedPackId] = useState<number | null>(null);
  const [routeRoomCode, setRouteRoomCode] = useState(initialRouteRoomCode);
  const [hostNickname, setHostNickname] = useState("방장");
  const [roomTitle, setRoomTitle] = useState("한소절 방");
  const [joinCode, setJoinCode] = useState(initialRouteRoomCode ?? "");
  const [joinNickname, setJoinNickname] = useState("참가자");
  const [answer, setAnswer] = useState("");
  const [reportMessage, setReportMessage] = useState("");
  const [message, setMessage] = useState("");
  const [createMessage, setCreateMessage] = useState("");
  const [joinMessage, setJoinMessage] = useState("");
  const [nowMs, setNowMs] = useState(Date.now());
  const socketRef = useRef<WebSocket | null>(null);

  const currentRound = room?.game?.current_round ?? null;
  const currentParticipant = useMemo(() => {
    if (!room || !participantId) {
      return null;
    }
    return room.participants.find((participant) => participant.id === participantId) ?? null;
  }, [participantId, room]);
  const isHost = Boolean(room && currentParticipant?.is_host);
  const effectiveHostToken = hostToken ?? (isHost ? participantToken : null);
  const isCurrentRoundRevealed = Boolean(currentRound?.ended_at);
  const canSubmit = Boolean(
    participantToken
      && room?.status === "playing"
      && currentParticipant?.status === "ACTIVE",
  );
  const canSkipRound = Boolean(
    participantToken
      && room?.status === "playing"
      && currentRound?.started_at
      && !currentRound.ended_at
      && currentParticipant?.status === "ACTIVE",
  );
  const canForceSkipRound = Boolean(
    effectiveHostToken && room?.status === "playing" && currentRound?.started_at && !currentRound.ended_at,
  );
  const hostActionDisabled = !(
    effectiveHostToken
    && room
    && (room.status === "waiting" || room.status === "finished" || (room.status === "playing" && currentRound?.ended_at))
  );
  const orderedParticipants = useMemo(
    () => [...(room?.participants ?? [])].sort((a, b) => b.score - a.score || Number(b.is_host) - Number(a.is_host)),
    [room],
  );
  const serverTimeOffsetMs = useMemo(() => {
    if (!room?.server_time) {
      return 0;
    }

    return new Date(room.server_time).getTime() - Date.now();
  }, [room?.server_time]);
  const roundTimer = useMemo(
    () =>
      getRoundTimer(
        currentRound,
        room?.settings ?? null,
        room?.game?.first_round_starts_at,
        nowMs + serverTimeOffsetMs,
      ),
    [currentRound, nowMs, room?.game?.first_round_starts_at, room?.settings, serverTimeOffsetMs],
  );

  useEffect(() => {
    void listQuizPacks()
      .then((packs) => {
        setQuizPacks(packs);
        const largestPack = [...packs].sort(
          (a, b) => b.approved_question_count - a.approved_question_count,
        )[0];
        setSelectedPackId(largestPack?.id ?? null);
      })
      .catch((error) => setMessage(error instanceof Error ? error.message : "문제팩을 불러오지 못했습니다."));
  }, []);

  useEffect(() => {
    void listQuizScopes()
      .then(setQuizScopes)
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    void Promise.all([getRandomNickname(), getRandomNickname()])
      .then(([host, join]) => {
        setHostNickname(host.nickname);
        setJoinNickname(join.nickname);
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      setNowMs(Date.now());
    }, 1000);

    return () => window.clearInterval(intervalId);
  }, []);

  useEffect(() => {
    const codeToLoad = routeRoomCode ?? savedRoomCode;
    if (!codeToLoad || room || (!participantToken && !hostToken)) {
      return;
    }

    void getRoom(codeToLoad)
      .then((loadedRoom) => setRoom(loadedRoom))
      .catch(() => undefined);
  }, [hostToken, participantToken, room, routeRoomCode, setRoom]);

  useEffect(() => {
    if (!routeRoomCode || room) {
      return;
    }

    setJoinCode(routeRoomCode);
    void getRoom(routeRoomCode)
      .then(() => undefined)
      .catch(() => undefined);
  }, [room, routeRoomCode]);

  useEffect(() => {
    if (!room?.code || socketStatus === "open") {
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
  }, [room?.code, setRoom, socketStatus]);

  useEffect(() => {
    if (!room?.code || !participantToken || participantId) {
      return;
    }

    void getCurrentParticipant(room.code, participantToken)
      .then((identity) => setParticipantId(identity.participant_id))
      .catch(() => undefined);
  }, [participantId, participantToken, room?.code, setParticipantId]);

  useEffect(() => {
    if (!room?.code || !participantToken) {
      return;
    }

    const roomCode = room.code;
    const token = participantToken;

    function handlePageHide() {
      leaveRoomOnPageExit(roomCode, token);
      clearStoredRoomSession();
    }

    window.addEventListener("pagehide", handlePageHide);

    return () => window.removeEventListener("pagehide", handlePageHide);
  }, [participantToken, room?.code]);

  async function runAction<T>(action: () => Promise<T>, successMessage: string) {
    setMessage("");
    try {
      const result = await action();
      if (successMessage) {
        setMessage(successMessage);
      }
      return result;
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "요청에 실패했습니다.");
      return null;
    }
  }

  async function handleCreateRoom(event: FormEvent) {
    event.preventDefault();
    setCreateMessage("");
    setJoinMessage("");
    if (!selectedPackId) {
      setCreateMessage("출제 범위를 먼저 불러오는 중입니다.");
      return;
    }

    let created = null;
    try {
      created = await createRoom({
          quiz_pack_id: selectedPackId,
          host_nickname: hostNickname,
          room_title: roomTitle,
          settings: getDefaultRoomSettings(),
        });
    } catch (error) {
      setCreateMessage(error instanceof Error ? error.message : "방 만들기에 실패했습니다.");
    }

    if (created) {
      setRoom(created.room);
      setHostToken(created.host_token);
      setParticipantToken(created.participant_token);
      setParticipantId(created.participant_id);
      setJoinCode(created.room.code);
      rememberRoomLink(created.room.code);
      setLastAnswerResult(null);
      setLastRoundStarted(null);
    }
  }

  async function handleJoinRoom(event: FormEvent) {
    event.preventDefault();
    setJoinMessage("");
    setCreateMessage("");
    let joined = null;
    try {
      joined = await joinRoom(joinCode.trim().toUpperCase(), joinNickname, null);
    } catch (error) {
      setJoinMessage(error instanceof Error ? error.message : "방 참가에 실패했습니다.");
    }

    if (joined) {
      setRoom(joined.room);
      setHostToken(null);
      setParticipantToken(joined.participant_token);
      setParticipantId(joined.participant_id);
      rememberRoomLink(joined.room.code);
      setLastAnswerResult(null);
      setLastRoundStarted(null);
    }
  }

  async function handleHostPrimaryAction() {
    if (!room || !effectiveHostToken) {
      return;
    }

    if (room.status === "waiting") {
      const started = await runAction(() => startGame(room.code, effectiveHostToken), "게임을 시작했습니다.");
      if (started) {
        setRoom(started.room);
        setLastAnswerResult(null);
        setLastRoundStarted(null);
        setAnswer("");
      }
      return;
    }

    if (room.status === "finished") {
      const returned = await runAction(() => returnRoomToLobby(room.code, effectiveHostToken), "");
      if (returned) {
        setRoom(returned.room);
        setLastAnswerResult(null);
        setLastRoundStarted(null);
        setAnswer("");
      }
      return;
    }

    if (room.status === "playing" && currentRound?.ended_at) {
      const advanced = await runAction(() => moveToNextRound(room.code, effectiveHostToken), "다음 라운드로 이동했습니다.");
      if (advanced) {
        setRoom(advanced.room);
      }
    }
  }

  async function handleSubmitAnswer(event: FormEvent) {
    event.preventDefault();
    if (!room || !participantToken) {
      return;
    }

    const submittedAnswer = answer.trim();
    if (!submittedAnswer) {
      return;
    }
    setAnswer("");

    const result = await runAction(
      () => submitAnswer(room.code, participantToken, submittedAnswer),
      "정답을 제출했습니다.",
    );

    if (result) {
      setLastAnswerResult(result);
      if (result.room) {
        setRoom(result.room);
      } else {
        applyFastAnswerResult(result);
      }
    }
  }

  function applyFastAnswerResult(result: SubmitAnswerResponse) {
    if (!room || !participantId || !room.game?.current_round) {
      return;
    }

    const currentRoundId = room.game.current_round.round_id;
    const nextParticipants = room.participants.map((participant) =>
      participant.id === participantId
        ? { ...participant, score: result.participant_score }
        : participant,
    );
    const nextTeams = room.teams.map((team) =>
      result.team_id && team.id === result.team_id && result.team_score !== null
        ? { ...team, score: result.team_score }
        : team,
    );
    const nextSubmissions = [
      ...room.game.current_round.answer_submissions,
      ...result.answer_submissions,
    ].slice(-20);

    setRoom({
      ...room,
      participants: nextParticipants,
      teams: nextTeams,
      game: {
        ...room.game,
        current_round: {
          ...room.game.current_round,
          answer_submissions:
            room.game.current_round.round_id === currentRoundId
              ? nextSubmissions
              : room.game.current_round.answer_submissions,
        },
      },
    });
  }

  async function handleRandomHostNickname() {
    const result = await runAction(() => getRandomNickname(), "");
    if (result) {
      setHostNickname(result.nickname);
    }
  }

  async function handleRandomJoinNickname() {
    const result = await runAction(() => getRandomNickname(), "");
    if (result) {
      setJoinNickname(result.nickname);
    }
  }

  async function handleUpdateRoomSettings(input: {
    quiz_pack_id?: number | null;
    settings: Partial<RoomSettings>;
  }) {
    if (!room || !effectiveHostToken) {
      return;
    }
    const updated = await runAction(
      () => updateRoomSettings(room.code, effectiveHostToken, input),
      "설정을 변경했습니다.",
    );
    if (updated) {
      setRoom(updated.room);
    }
  }

  async function handleUpdateMyTeam(teamId: number) {
    if (!room || !participantToken) {
      return;
    }
    const updated = await runAction(() => updateMyTeam(room.code, participantToken, teamId), "");
    if (updated) {
      setRoom(updated.room);
    }
  }

  async function handleKickParticipant(participantId: number) {
    if (!room || !effectiveHostToken) {
      return;
    }
    const updated = await runAction(() => kickParticipant(room.code, effectiveHostToken, participantId), "");
    if (updated) {
      setRoom(updated.room);
    }
  }

  async function handleReportRound(reason: QualityReportReason, detail: string) {
    if (!room || !participantToken) {
      return;
    }

    const report = await runAction(
      () => reportCurrentRound(room.code, participantToken, reason, detail),
      "신고를 접수했습니다.",
    );
    if (report) {
      setReportMessage(`신고가 접수되었습니다. 누적 ${report.report_count}건`);
    }
  }

  function handleReset() {
    socketRef.current?.close();
    reset();
    setJoinCode("");
    setAnswer("");
    setReportMessage("");
    setCreateMessage("");
    setJoinMessage("");
    sessionStorage.removeItem("guess_song_room_code");
    setRouteRoomCode(null);
    window.history.replaceState(null, "", "/");
    setMessage("");
  }

  async function handleLeaveRoom() {
    if (!room || !participantToken) {
      handleReset();
      return;
    }

    const left = await runAction(() => leaveRoom(room.code, participantToken), "방에서 나갔습니다.");
    if (left) {
      handleReset();
    }
  }

  async function handleSetAway() {
    if (!room || !participantToken) {
      return;
    }

    const updated = await runAction(() => setParticipantAway(room.code, participantToken), "자리비움으로 변경했습니다.");
    if (updated) {
      setRoom(updated.room);
    }
  }

  async function handleSetActive() {
    if (!room || !participantToken) {
      return;
    }

    const updated = await runAction(() => setParticipantActive(room.code, participantToken), "다시 참가 중입니다.");
    if (updated) {
      setRoom(updated.room);
    }
  }

  async function handleSkipRound() {
    if (!room || !participantToken) {
      return;
    }

    const skipped = await runAction(() => skipCurrentRound(room.code, participantToken), "스킵을 투표했습니다.");
    if (skipped) {
      setRoom(skipped.room);
    }
  }

  async function handleForceSkipRound() {
    if (!room || !effectiveHostToken) {
      return;
    }

    const skipped = await runAction(() => forceSkipCurrentRound(room.code, effectiveHostToken), "라운드를 스킵했습니다.");
    if (skipped) {
      setRoom(skipped.room);
    }
  }

  if (!room) {
    return (
      <LobbyView
        createMessage={createMessage}
        hostNickname={hostNickname}
        initialSheet={routeRoomCode ? "join" : null}
        joinCode={joinCode}
        joinMessage={joinMessage}
        joinNickname={joinNickname}
        message={message}
        roomTitle={roomTitle}
        onCreateRoom={handleCreateRoom}
        onHostNicknameChange={(nickname) => {
          setHostNickname(nickname);
          setCreateMessage("");
        }}
        onJoinCodeChange={(code) => {
          setJoinCode(code);
          setJoinMessage("");
        }}
        onJoinNicknameChange={(nickname) => {
          setJoinNickname(nickname);
          setJoinMessage("");
        }}
        onJoinRoom={handleJoinRoom}
        onRandomHostNickname={handleRandomHostNickname}
        onRandomJoinNickname={handleRandomJoinNickname}
        onRoomTitleChange={(title) => {
          setRoomTitle(title);
          setCreateMessage("");
        }}
      />
    );
  }

  return (
    <RoomView
      answer={answer}
      answerHint={getAnswerHint(
        Boolean(participantToken),
        room.status,
        currentRound?.started_at ?? null,
        currentRound?.ended_at ?? null,
        currentParticipant?.status ?? null,
      )}
      canForceSkipRound={canForceSkipRound}
      canSkipRound={canSkipRound}
      canSubmit={canSubmit}
      currentParticipant={currentParticipant}
      currentRound={currentRound}
      hostActionDisabled={hostActionDisabled}
      isHost={isHost}
      isRevealed={isCurrentRoundRevealed}
      lastAnswerResult={lastAnswerResult}
      lastRoundStarted={lastRoundStarted}
      message={message}
      orderedParticipants={orderedParticipants}
      reportMessage={reportMessage}
      room={room}
      quizScopes={quizScopes}
      shareUrl={new URL(room.share_path, window.location.origin).toString()}
      socketStatus={socketStatus}
      timerLabel={roundTimer.label}
      timerSeconds={roundTimer.seconds}
      onAnswerChange={setAnswer}
      onForceSkipRound={handleForceSkipRound}
      onHostPrimaryAction={handleHostPrimaryAction}
      onLeaveRoom={handleLeaveRoom}
      onReportRound={handleReportRound}
      onSetActive={handleSetActive}
      onSetAway={handleSetAway}
      onSkipRound={handleSkipRound}
      onSubmitAnswer={handleSubmitAnswer}
      onKickParticipant={handleKickParticipant}
      onTeamChange={handleUpdateMyTeam}
      onUpdateRoomSettings={handleUpdateRoomSettings}
    />
  );
}

function getDefaultRoomSettings(): RoomSettings {
  return {
    question_count: 300,
    question_scope_type: "ALL_RANDOM",
    question_scope_value: "",
    target_score: 10,
    answer_limit_mode: "FIVE_SECONDS",
    play_mode: "SOLO",
    team_assign_mode: "SELF_SELECT",
    team_count: 2,
    item_mode: "OFF",
    answer_fields: "TITLE_ONLY",
    balance_mode: "OFF",
    allow_late_join: true,
    round_time_limit_sec: 8,
    reveal_duration_sec: 5,
    countdown_sec: 3,
  };
}

function getRoundTimer(
  currentRound: CurrentRound | null | undefined,
  settings: RoomSettings | null,
  firstRoundStartsAt: string | null | undefined,
  nowMs: number,
) {
  if (!settings) {
    return { label: null, seconds: null };
  }

  if (currentRound && !currentRound.started_at && firstRoundStartsAt) {
    return {
      label: "시작까지",
      seconds: Math.max(0, Math.ceil((new Date(firstRoundStartsAt).getTime() - nowMs) / 1000)),
    };
  }

  if (!currentRound) {
    return { label: null, seconds: null };
  }

  if (currentRound.ended_at) {
    const revealEndsAt = new Date(currentRound.ended_at).getTime() + settings.reveal_duration_sec * 1000;
    return {
      label: "다음 라운드까지",
      seconds: Math.max(0, Math.ceil((revealEndsAt - nowMs) / 1000)),
    };
  }

  if (currentRound.started_at) {
    const roundEndsAt = new Date(currentRound.started_at).getTime() + settings.round_time_limit_sec * 1000;
    return {
      label: "남은 시간",
      seconds: Math.max(0, Math.ceil((roundEndsAt - nowMs) / 1000)),
    };
  }

  return { label: null, seconds: null };
}

function getRoomCodeFromPath(pathname: string) {
  const match = pathname.match(/^\/rooms\/([A-Za-z0-9_-]+)\/?$/);
  return match ? match[1].toUpperCase() : null;
}

function rememberRoomLink(code: string) {
  const normalizedCode = code.trim().toUpperCase();
  sessionStorage.setItem("guess_song_room_code", normalizedCode);
  window.history.replaceState(null, "", `/rooms/${normalizedCode}`);
}

function clearStoredRoomSession() {
  sessionStorage.removeItem("guess_song_room_code");
  sessionStorage.removeItem("guess_song_host_token");
  sessionStorage.removeItem("guess_song_participant_token");
  sessionStorage.removeItem("guess_song_participant_id");
}

function getAnswerHint(
  hasToken: boolean,
  status: string,
  startedAt: string | null,
  endedAt: string | null,
  participantStatus: string | null,
) {
  if (!hasToken) {
    return "방을 만들거나 참가해야 정답을 제출할 수 있습니다.";
  }
  if (participantStatus === "AWAY") {
    return "자리비움 상태입니다. 돌아와야 제출할 수 있습니다.";
  }
  if (participantStatus === "LEFT") {
    return "이미 방에서 나갔습니다.";
  }
  if (status === "waiting") {
    return "방장이 게임을 시작해야 합니다.";
  }
  if (status === "finished") {
    return "게임이 종료되었습니다.";
  }
  if (!startedAt) {
    return "라운드 시작 전입니다. 음악이 시작되면 제출할 수 있습니다.";
  }
  if (endedAt) {
    return "정답 공개 중입니다. 이 라운드는 제출이 마감되었습니다.";
  }
  return "정답 입력을 기다리고 있습니다.";
}

export default App;
