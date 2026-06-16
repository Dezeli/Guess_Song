import type { FormEvent } from "react";

import type {
  AnswerFields,
  AnswerLimitMode,
  BalanceMode,
  ItemMode,
  PlayMode,
  QuizPack,
  RoomSettings,
  TeamAssignMode,
} from "../shared/types";

type LobbyViewProps = {
  allowLateJoin: boolean;
  answerFields: AnswerFields;
  answerLimitMode: AnswerLimitMode;
  balanceMode: BalanceMode;
  hostNickname: string;
  itemMode: ItemMode;
  joinCode: string;
  joinNickname: string;
  joinPreviewRoom: RoomSettings | null;
  joinPreviewTeams: Array<{ id: number; name: string }>;
  message: string;
  playMode: PlayMode;
  questionCount: number;
  quizPacks: QuizPack[];
  roundTimeLimitSec: number;
  selectedJoinTeamId: number | null;
  selectedPackId: number | null;
  teamAssignMode: TeamAssignMode;
  teamCount: number;
  onAllowLateJoinChange: (allowLateJoin: boolean) => void;
  onAnswerFieldsChange: (answerFields: AnswerFields) => void;
  onAnswerLimitModeChange: (answerLimitMode: AnswerLimitMode) => void;
  onBalanceModeChange: (balanceMode: BalanceMode) => void;
  onCreateRoom: (event: FormEvent) => void;
  onHostNicknameChange: (nickname: string) => void;
  onItemModeChange: (itemMode: ItemMode) => void;
  onJoinCodeChange: (code: string) => void;
  onJoinNicknameChange: (nickname: string) => void;
  onJoinRoom: (event: FormEvent) => void;
  onLoadRoom: () => void;
  onPlayModeChange: (playMode: PlayMode) => void;
  onQuestionCountChange: (questionCount: number) => void;
  onRoundTimeLimitSecChange: (roundTimeLimitSec: number) => void;
  onSelectedJoinTeamIdChange: (teamId: number) => void;
  onSelectedPackIdChange: (packId: number) => void;
  onTeamAssignModeChange: (teamAssignMode: TeamAssignMode) => void;
  onTeamCountChange: (teamCount: number) => void;
};

export function LobbyView({
  allowLateJoin,
  answerFields,
  answerLimitMode,
  balanceMode,
  hostNickname,
  itemMode,
  joinCode,
  joinNickname,
  joinPreviewRoom,
  joinPreviewTeams,
  message,
  playMode,
  questionCount,
  quizPacks,
  roundTimeLimitSec,
  selectedJoinTeamId,
  selectedPackId,
  teamAssignMode,
  teamCount,
  onAllowLateJoinChange,
  onAnswerFieldsChange,
  onAnswerLimitModeChange,
  onBalanceModeChange,
  onCreateRoom,
  onHostNicknameChange,
  onItemModeChange,
  onJoinCodeChange,
  onJoinNicknameChange,
  onJoinRoom,
  onLoadRoom,
  onPlayModeChange,
  onQuestionCountChange,
  onRoundTimeLimitSecChange,
  onSelectedJoinTeamIdChange,
  onSelectedPackIdChange,
  onTeamAssignModeChange,
  onTeamCountChange,
}: LobbyViewProps) {
  return (
    <main className="app-shell lobby-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Guess Song</p>
          <h1>방 만들기 또는 참가</h1>
        </div>
      </header>

      <section className="layout">
        <div className="panel">
          <h2>방 만들기</h2>
          <form onSubmit={onCreateRoom} className="stack">
            <label>
              문제팩
              <select value={selectedPackId ?? ""} onChange={(event) => onSelectedPackIdChange(Number(event.target.value))}>
                {quizPacks.map((pack) => (
                  <option key={pack.id} value={pack.id}>
                    {pack.name} ({pack.approved_question_count})
                  </option>
                ))}
              </select>
            </label>
            <label>
              방장 닉네임
              <input value={hostNickname} onChange={(event) => onHostNicknameChange(event.target.value)} />
            </label>
            <div className="form-grid">
              <label>
                문제 수
                <input min={1} max={20} type="number" value={questionCount} onChange={(event) => onQuestionCountChange(Number(event.target.value))} />
              </label>
              <label>
                라운드 시간
                <input min={5} max={120} type="number" value={roundTimeLimitSec} onChange={(event) => onRoundTimeLimitSecChange(Number(event.target.value))} />
              </label>
            </div>
            <div className="form-grid">
              <label>
                정답 제한
                <select value={answerLimitMode} onChange={(event) => onAnswerLimitModeChange(event.target.value as AnswerLimitMode)}>
                  <option value="FIRST_ONLY">선착순</option>
                  <option value="FIVE_SECONDS">5초 추가 정답</option>
                  <option value="ALL_CORRECT">모두 정답</option>
                </select>
              </label>
              <label>
                정답 항목
                <select value={answerFields} onChange={(event) => onAnswerFieldsChange(event.target.value as AnswerFields)}>
                  <option value="TITLE_ONLY">제목만</option>
                  <option value="TITLE_AND_ARTIST">제목 + 가수</option>
                </select>
              </label>
            </div>
            <label>
              플레이 방식
              <select value={playMode} onChange={(event) => onPlayModeChange(event.target.value as PlayMode)}>
                <option value="SOLO">개인전</option>
                <option value="TEAM">팀전</option>
              </select>
            </label>
            {playMode === "TEAM" ? (
              <div className="form-grid">
                <label>
                  팀 배정
                  <select value={teamAssignMode} onChange={(event) => onTeamAssignModeChange(event.target.value as TeamAssignMode)}>
                    <option value="SELF_SELECT">직접 선택</option>
                    <option value="RANDOM">무작위</option>
                  </select>
                </label>
                <label>
                  팀 수
                  <input min={2} max={4} type="number" value={teamCount} onChange={(event) => onTeamCountChange(Number(event.target.value))} />
                </label>
              </div>
            ) : null}
            <div className="form-grid">
              <label>
                아이템전
                <select value={itemMode} onChange={(event) => onItemModeChange(event.target.value as ItemMode)}>
                  <option value="OFF">끄기</option>
                  <option value="ON">켜기</option>
                </select>
              </label>
              <label>
                밸런스 모드
                <select
                  value={answerLimitMode === "FIRST_ONLY" ? balanceMode : "OFF"}
                  onChange={(event) => onBalanceModeChange(event.target.value as BalanceMode)}
                  disabled={answerLimitMode !== "FIRST_ONLY"}
                >
                  <option value="OFF">끄기</option>
                  <option value="ON">켜기</option>
                </select>
              </label>
            </div>
            <label className="checkbox-row">
              <input type="checkbox" checked={allowLateJoin} onChange={(event) => onAllowLateJoinChange(event.target.checked)} />
              중도 참가 허용
            </label>
            <button type="submit">방 만들기</button>
          </form>
        </div>

        <div className="panel">
          <h2>방 참가</h2>
          <form onSubmit={onJoinRoom} className="stack">
            <label>
              방 코드
              <input value={joinCode} onChange={(event) => onJoinCodeChange(event.target.value.toUpperCase())} placeholder="ABC123" />
            </label>
            <label>
              닉네임
              <input value={joinNickname} onChange={(event) => onJoinNicknameChange(event.target.value)} />
            </label>
            {joinPreviewRoom?.play_mode === "TEAM" && joinPreviewRoom.team_assign_mode === "SELF_SELECT" ? (
              <label>
                팀
                <select value={selectedJoinTeamId ?? ""} onChange={(event) => onSelectedJoinTeamIdChange(Number(event.target.value))}>
                  {joinPreviewTeams.map((team) => (
                    <option key={team.id} value={team.id}>
                      {team.name}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            <div className="button-row">
              <button type="submit">참가</button>
              <button type="button" className="secondary" onClick={onLoadRoom}>
                방 정보 불러오기
              </button>
            </div>
          </form>
        </div>
      </section>
      {message ? <p className="message">{message}</p> : null}
    </main>
  );
}
