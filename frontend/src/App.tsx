import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { LobbyView } from "./components/LobbyView";
import { ReviewView } from "./components/ReviewView";
import { RoomView } from "./components/RoomView";
import {
  createRoom,
  forceSkipCurrentRound,
  getCurrentParticipant,
  getRoom,
  joinRoom,
  leaveRoom,
  listQuizPacks,
  moveToNextRound,
  setParticipantActive,
  setParticipantAway,
  skipCurrentRound,
  startGame,
  submitAnswer,
} from "./shared/api";
import { openRoomSocket } from "./shared/roomSocket";
import type {
  AnswerFields,
  AnswerLimitMode,
  BalanceMode,
  CurrentRound,
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
  const [selectedPackId, setSelectedPackId] = useState<number | null>(null);
  const [hostNickname, setHostNickname] = useState("방장");
  const [joinCode, setJoinCode] = useState(savedRoomCode);
  const [joinNickname, setJoinNickname] = useState("참가자");
  const [joinPreviewRoom, setJoinPreviewRoom] = useState<RoomSettings | null>(null);
  const [joinPreviewTeams, setJoinPreviewTeams] = useState<Array<{ id: number; name: string }>>([]);
  const [selectedJoinTeamId, setSelectedJoinTeamId] = useState<number | null>(null);
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
  const [nowMs, setNowMs] = useState(Date.now());
  const socketRef = useRef<WebSocket | null>(null);

  const currentRound = room?.game?.current_round ?? null;
  const currentParticipant = useMemo(() => {
    if (!room || !participantId) {
      return null;
    }
    return room.participants.find((participant) => participant.id === participantId) ?? null;
  }, [participantId, room]);
  const isHost = Boolean(hostToken && room);
  const isCurrentRoundRevealed = Boolean(currentRound?.ended_at);
  const canSubmit = Boolean(
    participantToken
      && room?.status === "playing"
      && currentRound?.started_at
      && !currentRound.ended_at
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
    hostToken && room?.status === "playing" && currentRound?.started_at && !currentRound.ended_at,
  );
  const hostActionDisabled = !(
    hostToken
    && room
    && (room.status === "waiting" || (room.status === "playing" && currentRound?.ended_at))
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
        setSelectedPackId(packs[0]?.id ?? null);
      })
      .catch((error) => setMessage(error instanceof Error ? error.message : "문제팩을 불러오지 못했습니다."));
  }, []);

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      setNowMs(Date.now());
    }, 1000);

    return () => window.clearInterval(intervalId);
  }, []);

  useEffect(() => {
    if (!savedRoomCode || room || (!participantToken && !hostToken)) {
      return;
    }

    void getRoom(savedRoomCode)
      .then((loadedRoom) => setRoom(loadedRoom))
      .catch(() => undefined);
  }, [hostToken, participantToken, room, setRoom]);

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

  useEffect(() => {
    if (!room?.code || !participantToken || participantId) {
      return;
    }

    void getCurrentParticipant(room.code, participantToken)
      .then((identity) => setParticipantId(identity.participant_id))
      .catch(() => undefined);
  }, [participantId, participantToken, room?.code, setParticipantId]);

  async function runAction<T>(action: () => Promise<T>, successMessage: string) {
    setMessage("");
    try {
      const result = await action();
      setMessage(successMessage);
      return result;
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "요청에 실패했습니다.");
      return null;
    }
  }

  async function handleCreateRoom(event: FormEvent) {
    event.preventDefault();
    if (!selectedPackId) {
      setMessage("문제팩을 먼저 선택하세요.");
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
      reveal_duration_sec: 5,
      countdown_sec: 3,
    };

    const created = await runAction(
      () =>
        createRoom({
          quiz_pack_id: selectedPackId,
          host_nickname: hostNickname,
          settings,
        }),
      "방을 만들었습니다.",
    );

    if (created) {
      setRoom(created.room);
      setHostToken(created.host_token);
      setParticipantToken(created.participant_token);
      setParticipantId(created.participant_id);
      setJoinCode(created.room.code);
      setLastAnswerResult(null);
      setLastRoundStarted(null);
    }
  }

  async function handleJoinRoom(event: FormEvent) {
    event.preventDefault();
    const joined = await runAction(
      () => joinRoom(joinCode.trim().toUpperCase(), joinNickname, selectedJoinTeamId),
      "방에 참가했습니다.",
    );

    if (joined) {
      setRoom(joined.room);
      setHostToken(null);
      setParticipantToken(joined.participant_token);
      setParticipantId(joined.participant_id);
      setLastAnswerResult(null);
      setLastRoundStarted(null);
    }
  }

  async function handleRestoreRoom() {
    if (!joinCode.trim()) {
      return;
    }
    const loaded = await runAction(() => getRoom(joinCode.trim().toUpperCase()), "방 정보를 불러왔습니다.");
    if (loaded) {
      setJoinPreviewRoom(loaded.settings);
      setJoinPreviewTeams(loaded.teams.map((team) => ({ id: team.id, name: team.name })));
      setSelectedJoinTeamId(loaded.teams[0]?.id ?? null);
    }
  }

  async function handleHostPrimaryAction() {
    if (!room || !hostToken) {
      return;
    }

    if (room.status === "waiting") {
      const started = await runAction(() => startGame(room.code, hostToken), "게임을 시작했습니다.");
      if (started) {
        setRoom(started.room);
      }
      return;
    }

    if (room.status === "playing" && currentRound?.ended_at) {
      const advanced = await runAction(() => moveToNextRound(room.code, hostToken), "다음 단계로 이동했습니다.");
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

    const result = await runAction(
      () => submitAnswer(room.code, participantToken, answer),
      "정답을 제출했습니다.",
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
    setMessage("현재 화면 상태를 초기화했습니다.");
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

    const skipped = await runAction(() => skipCurrentRound(room.code, participantToken), "스킵에 투표했습니다.");
    if (skipped) {
      setRoom(skipped.room);
    }
  }

  async function handleForceSkipRound() {
    if (!room || !hostToken) {
      return;
    }

    const skipped = await runAction(() => forceSkipCurrentRound(room.code, hostToken), "라운드를 스킵했습니다.");
    if (skipped) {
      setRoom(skipped.room);
    }
  }

  if (!room) {
    return (
      <LobbyView
        allowLateJoin={allowLateJoin}
        answerFields={answerFields}
        answerLimitMode={answerLimitMode}
        balanceMode={balanceMode}
        hostNickname={hostNickname}
        itemMode={itemMode}
        joinCode={joinCode}
        joinNickname={joinNickname}
        joinPreviewRoom={joinPreviewRoom}
        joinPreviewTeams={joinPreviewTeams}
        message={message}
        playMode={playMode}
        questionCount={questionCount}
        quizPacks={quizPacks}
        roundTimeLimitSec={roundTimeLimitSec}
        selectedJoinTeamId={selectedJoinTeamId}
        selectedPackId={selectedPackId}
        teamAssignMode={teamAssignMode}
        teamCount={teamCount}
        onAllowLateJoinChange={setAllowLateJoin}
        onAnswerFieldsChange={setAnswerFields}
        onAnswerLimitModeChange={setAnswerLimitMode}
        onBalanceModeChange={setBalanceMode}
        onCreateRoom={handleCreateRoom}
        onHostNicknameChange={setHostNickname}
        onItemModeChange={setItemMode}
        onJoinCodeChange={setJoinCode}
        onJoinNicknameChange={setJoinNickname}
        onJoinRoom={handleJoinRoom}
        onLoadRoom={handleRestoreRoom}
        onPlayModeChange={setPlayMode}
        onQuestionCountChange={setQuestionCount}
        onRoundTimeLimitSecChange={setRoundTimeLimitSec}
        onSelectedJoinTeamIdChange={setSelectedJoinTeamId}
        onSelectedPackIdChange={setSelectedPackId}
        onTeamAssignModeChange={setTeamAssignMode}
        onTeamCountChange={setTeamCount}
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
      roundActionHint={getRoundActionHint(
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
      room={room}
      socketStatus={socketStatus}
      timerLabel={roundTimer.label}
      timerSeconds={roundTimer.seconds}
      onAnswerChange={setAnswer}
      onForceSkipRound={handleForceSkipRound}
      onHostPrimaryAction={handleHostPrimaryAction}
      onLeaveRoom={handleLeaveRoom}
      onReset={handleReset}
      onSetActive={handleSetActive}
      onSetAway={handleSetAway}
      onSkipRound={handleSkipRound}
      onSubmitAnswer={handleSubmitAnswer}
    />
  );
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

function getAnswerHint(
  hasToken: boolean,
  status: string,
  startedAt: string | null,
  endedAt: string | null,
  participantStatus: string | null,
) {
  if (!hasToken) {
    return "방을 만들거나 참가한 뒤 정답을 제출할 수 있습니다.";
  }
  if (participantStatus === "AWAY") {
    return "자리비움 상태입니다. 돌아온 뒤 제출하세요.";
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
    return "정답 공개 중입니다. 이 라운드는 제출이 마감됐습니다.";
  }
  return "정답 입력이 열려 있습니다.";
}

function getRoundActionHint(
  hasToken: boolean,
  status: string,
  startedAt: string | null,
  endedAt: string | null,
  participantStatus: string | null,
) {
  if (!hasToken) {
    return null;
  }
  if (participantStatus === "AWAY") {
    return "자리비움 상태에서는 스킵 투표를 할 수 없습니다.";
  }
  if (participantStatus === "LEFT") {
    return "방을 나간 상태에서는 라운드 액션을 사용할 수 없습니다.";
  }
  if (status === "waiting") {
    return "게임 시작 전에는 스킵할 수 없습니다.";
  }
  if (status === "finished") {
    return "게임이 종료되어 라운드 액션이 닫혔습니다.";
  }
  if (!startedAt) {
    return "라운드가 시작되면 스킵 투표가 열립니다.";
  }
  if (endedAt) {
    return "정답 공개 중에는 스킵 투표가 마감됩니다.";
  }
  return null;
}

export default App;
