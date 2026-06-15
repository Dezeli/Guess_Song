export type QuizPack = {
  id: number;
  name: string;
  description: string;
  is_public: boolean;
  approved_question_count: number;
};

export type Participant = {
  id: number;
  nickname: string;
  score: number;
  is_host: boolean;
  status: "ACTIVE" | "AWAY" | "LEFT";
  left_at: string | null;
};

export type CurrentRound = {
  round_id: number;
  round_index: number;
  question_id: number;
  youtube_video_id: string;
  start_time_seconds: number;
  play_duration_seconds: number;
  difficulty: string;
  started_at: string | null;
  ended_at: string | null;
  skip_count: number;
  skip_target_count: number;
  answer_fields: Array<{
    field_type: "title" | "artist";
    is_open: boolean;
    is_revealed: boolean;
    first_correct_at: string | null;
    closed_at: string | null;
    revealed_at: string | null;
    answer: string | null;
  }>;
};

export type AnswerLimitMode = "FIRST_ONLY" | "FIVE_SECONDS" | "ALL_CORRECT";
export type PlayMode = "SOLO" | "TEAM";
export type TeamAssignMode = "SELF_SELECT" | "RANDOM";
export type ItemMode = "OFF" | "ON";
export type AnswerFields = "TITLE_ONLY" | "TITLE_AND_ARTIST";
export type BalanceMode = "OFF" | "ON";

export type RoomSettings = {
  question_count: number;
  answer_limit_mode: AnswerLimitMode;
  play_mode: PlayMode;
  team_assign_mode: TeamAssignMode;
  team_count: number;
  item_mode: ItemMode;
  answer_fields: AnswerFields;
  balance_mode: BalanceMode;
  allow_late_join: boolean;
  round_time_limit_sec: number;
  reveal_duration_sec: number;
  countdown_sec: number;
};

export type RoomState = {
  code: string;
  status: string;
  quiz_pack: {
    id: number;
    name: string;
    approved_question_count: number;
  } | null;
  game: {
    status: string;
    current_round_index: number;
    total_rounds: number;
    current_round: CurrentRound | null;
  } | null;
  participants: Participant[];
  settings: RoomSettings;
};

export type CreateRoomResponse = {
  room: RoomState;
  host_token: string;
  participant_token: string;
};

export type JoinRoomResponse = {
  room: RoomState;
  participant_token: string;
};

export type SubmitAnswerResponse = {
  is_correct: boolean;
  score_awarded: number;
  total_score: number;
  matched_fields: string[];
};

export type RoomSocketMessage =
  | { type: "room_state"; room: RoomState }
  | { type: "round_started"; round: CurrentRound }
  | { type: "pong" }
  | { type: "error"; message: string };
