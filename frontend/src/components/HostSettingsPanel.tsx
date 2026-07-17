import type {
  AnswerFields,
  AnswerLimitMode,
  ItemMode,
  PlayMode,
  QuestionScopeOptions,
  QuestionScopeType,
  RoomSettings,
  RoomState,
  TeamAssignMode,
} from "../shared/types";

type HostSettingsPanelProps = {
  editable: boolean;
  quizScopes: QuestionScopeOptions;
  room: RoomState;
  onUpdate: (input: { quiz_pack_id?: number | null; settings: Partial<RoomSettings> }) => void;
};

const TARGET_SCORE_OPTIONS = [5, 10, 15, 20];
const ROUND_TIME_OPTIONS = [8, 16, 30];
const QUESTION_SCOPE_OPTIONS: Array<{ value: QuestionScopeType; label: string }> = [
  { value: "ALL_RANDOM", label: "올랜덤" },
  { value: "YEAR", label: "연도별" },
  { value: "ARTIST", label: "가수별" },
];
const GAME_MODE_OPTIONS: Array<{ value: AnswerLimitMode; label: string; description: string }> = [
  { value: "FIRST_ONLY", label: "선착순", description: "처음 정답자만 점수를 획득합니다." },
  { value: "FIVE_SECONDS", label: "추가 정답", description: "첫 정답 후 5초까지 점수를 부여합니다." },
  { value: "ALL_CORRECT", label: "전원 정답", description: "모든 참가자가 정답을 맞힐 때까지 진행합니다." },
];
const PLAY_MODE_OPTIONS: Array<{ value: PlayMode; label: string }> = [
  { value: "SOLO", label: "개인전" },
  { value: "TEAM", label: "팀전" },
];
const TEAM_ASSIGN_OPTIONS: Array<{ value: TeamAssignMode; label: string }> = [
  { value: "SELF_SELECT", label: "팀 선택" },
  { value: "RANDOM", label: "랜덤 팀" },
];
const TEAM_COUNT_OPTIONS = [2, 3, 4];
const ANSWER_FIELD_OPTIONS: Array<{ value: AnswerFields; label: string }> = [
  { value: "TITLE_AND_ARTIST", label: "제목+가수" },
  { value: "TITLE_ONLY", label: "제목" },
];
const ITEM_MODE_OPTIONS: Array<{ value: ItemMode; label: string }> = [
  { value: "ON", label: "O" },
  { value: "OFF", label: "X" },
];
export function HostSettingsPanel({ editable, quizScopes, room, onUpdate }: HostSettingsPanelProps) {
  const settings = room.settings;
  const scopeType = settings.question_scope_type ?? "ALL_RANDOM";
  const scopeValue = settings.question_scope_value ?? "";
  const selectedGameMode = GAME_MODE_OPTIONS.find((mode) => mode.value === settings.answer_limit_mode);
  const yearOptions = quizScopes.years;
  const artistOptions = quizScopes.artists;

  return (
    <section className={`panel host-settings-panel${editable ? "" : " is-readonly"}`}>
      <div className="section-heading">
        <h2>방 설정</h2>
        <span className="settings-owner-note">(방장만 변경 가능합니다)</span>
      </div>

      <div className="setting-block scope-setting">
        <span className="setting-title">출제 범위</span>
        <div className="scope-row">
          <div className="segmented-control scope-tabs">
            {QUESTION_SCOPE_OPTIONS.map((scope) => (
              <button
                key={scope.value}
                type="button"
                className={scopeType === scope.value ? "selected" : "secondary"}
                disabled={!editable}
                onClick={() =>
                  onUpdate({
                    settings: {
                      question_scope_type: scope.value,
                      question_scope_value: getDefaultScopeValue(scope.value, quizScopes),
                    },
                  })
                }
              >
                {scope.label}
              </button>
            ))}
          </div>
          {scopeType === "YEAR" ? (
            <select
              value={scopeValue || yearOptions[0]?.value || ""}
              disabled={!editable}
              onChange={(event) => onUpdate({ settings: { question_scope_value: event.target.value } })}
            >
              {yearOptions.map((year) => (
                <option key={year.value} value={year.value}>
                  {year.label} ({year.question_count})
                </option>
              ))}
            </select>
          ) : null}
          {scopeType === "ARTIST" ? (
            <select
              value={scopeValue || artistOptions[0]?.value || ""}
              disabled={!editable}
              onChange={(event) => onUpdate({ settings: { question_scope_value: event.target.value } })}
            >
              {artistOptions.map((artist) => (
                <option key={artist.value} value={artist.value}>
                  {artist.label} ({artist.question_count})
                </option>
              ))}
            </select>
          ) : null}
        </div>
      </div>

      <div className="setting-block inline-settings">
        <div>
          <span className="setting-title">목표 점수</span>
          <div className="segmented-control">
            {TARGET_SCORE_OPTIONS.map((score) => (
              <button
                key={score}
                type="button"
                disabled={!editable}
                className={settings.target_score === score ? "selected" : "secondary"}
                onClick={() => onUpdate({ settings: { target_score: score } })}
              >
                {score}점
              </button>
            ))}
          </div>
        </div>
        <div>
          <span className="setting-title">라운드 시간</span>
          <div className="segmented-control">
            {ROUND_TIME_OPTIONS.map((seconds) => (
              <button
                key={seconds}
                type="button"
                disabled={!editable}
                className={settings.round_time_limit_sec === seconds ? "selected" : "secondary"}
                onClick={() => onUpdate({ settings: { round_time_limit_sec: seconds } })}
              >
                {seconds}초
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="setting-block game-mode-setting">
        <div>
          <span className="setting-title">게임 모드</span>
          <div className="game-mode-row">
            <div className="segmented-control">
              {GAME_MODE_OPTIONS.map((mode) => (
                <button
                  key={mode.value}
                  type="button"
                  disabled={!editable}
                  className={settings.answer_limit_mode === mode.value ? "selected" : "secondary"}
                  onClick={() => onUpdate({ settings: { answer_limit_mode: mode.value } })}
                >
                  {mode.label}
                </button>
              ))}
            </div>
            <span className="setting-description">{selectedGameMode?.description}</span>
          </div>
        </div>
      </div>

      <div className="setting-block inline-settings team-setting-row">
        <div>
          <span className="setting-title">진행 방식</span>
          <div className="segmented-control compact-options">
            {PLAY_MODE_OPTIONS.map((mode) => (
              <button
                key={mode.value}
                type="button"
                disabled={!editable}
                className={settings.play_mode === mode.value ? "selected" : "secondary"}
                onClick={() => onUpdate({ settings: { play_mode: mode.value } })}
              >
                {mode.label}
              </button>
            ))}
          </div>
        </div>
        <div className={settings.play_mode !== "TEAM" ? "disabled-setting" : undefined}>
          <span className="setting-title">팀 배정</span>
          <div className="segmented-control compact-options">
            {TEAM_ASSIGN_OPTIONS.map((mode) => (
              <button
                key={mode.value}
                type="button"
                disabled={!editable || settings.play_mode !== "TEAM"}
                className={settings.team_assign_mode === mode.value ? "selected" : "secondary"}
                onClick={() => onUpdate({ settings: { team_assign_mode: mode.value } })}
              >
                {mode.label}
              </button>
            ))}
          </div>
        </div>
        <div className={settings.play_mode !== "TEAM" ? "disabled-setting" : undefined}>
          <span className="setting-title">팀 수</span>
          <div className="segmented-control compact-options">
            {TEAM_COUNT_OPTIONS.map((count) => (
              <button
                key={count}
                type="button"
                disabled={!editable || settings.play_mode !== "TEAM"}
                className={settings.team_count === count ? "selected" : "secondary"}
                onClick={() => onUpdate({ settings: { team_count: count } })}
              >
                {count}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="setting-block inline-settings">
        <div>
          <span className="setting-title">정답 범위</span>
          <div className="segmented-control compact-options">
            {ANSWER_FIELD_OPTIONS.map((field) => (
              <button
                key={field.value}
                type="button"
                disabled={!editable}
                className={settings.answer_fields === field.value ? "selected" : "secondary"}
                onClick={() => onUpdate({ settings: { answer_fields: field.value } })}
              >
                {field.label}
              </button>
            ))}
          </div>
        </div>
        <div>
          <span className="setting-title">아이템</span>
          <div className="segmented-control compact-options">
            {ITEM_MODE_OPTIONS.map((mode) => (
              <button
                key={mode.value}
                type="button"
                disabled={!editable}
                className={settings.item_mode === mode.value ? "selected" : "secondary"}
                onClick={() => onUpdate({ settings: { item_mode: mode.value } })}
              >
                {mode.label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function getDefaultScopeValue(scopeType: QuestionScopeType, quizScopes: QuestionScopeOptions) {
  if (scopeType === "YEAR") {
    return quizScopes.years[0]?.value ?? "";
  }
  if (scopeType === "ARTIST") {
    return quizScopes.artists[0]?.value ?? "";
  }
  return "";
}
