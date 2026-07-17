export type QuizPack = {
  id: number;
  name: string;
  description: string;
  is_public: boolean;
  approved_question_count: number;
};

export type QuestionScopeOption = {
  value: string;
  label: string;
  question_count: number;
};

export type QuestionScopeOptions = {
  years: QuestionScopeOption[];
  artists: QuestionScopeOption[];
};

export type Participant = {
  id: number;
  nickname: string;
  team_id: number | null;
  team_name: string | null;
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
  playback_segments: Array<{
    start_time_seconds: number;
    duration_seconds: number;
  }>;
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
  answer_submissions: Array<{
    id: number;
    participant_id: number;
    nickname: string;
    answer: string;
    is_correct: boolean;
    is_accepted: boolean;
    score_awarded: number;
    submitted_at: string;
  }>;
};

export type AnswerLimitMode = "FIRST_ONLY" | "FIVE_SECONDS" | "ALL_CORRECT";
export type PlayMode = "SOLO" | "TEAM";
export type TeamAssignMode = "SELF_SELECT" | "RANDOM";
export type ItemMode = "OFF" | "ON";
export type AnswerFields = "TITLE_ONLY" | "TITLE_AND_ARTIST";
export type BalanceMode = "OFF" | "ON";
export type QuestionScopeType = "ALL_RANDOM" | "YEAR" | "ARTIST";

export type RoomSettings = {
  question_count: number;
  question_scope_type: QuestionScopeType;
  question_scope_value: string;
  target_score: number;
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
  title: string;
  share_path: string;
  status: string;
  server_time: string;
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
    first_round_starts_at: string | null;
  } | null;
  participants: Participant[];
  teams: Array<{
    id: number;
    name: string;
    order: number;
    score: number;
    participant_count: number;
  }>;
  settings: RoomSettings;
};

export type CreateRoomResponse = {
  room: RoomState;
  host_token: string;
  participant_token: string;
  participant_id: number;
};

export type JoinRoomResponse = {
  room: RoomState;
  participant_token: string;
  participant_id: number;
};

export type ParticipantIdentityResponse = {
  participant_id: number;
};

export type SubmitAnswerResponse = {
  is_correct: boolean;
  score_awarded: number;
  total_score: number;
  matched_fields: string[];
  answer_submissions: CurrentRound["answer_submissions"];
  participant_score: number;
  team_id: number | null;
  team_score: number | null;
  room: RoomState | null;
};

export type QualityReportReason =
  | "wrong_title"
  | "wrong_artist"
  | "wrong_audio"
  | "unavailable"
  | "unofficial_video"
  | "other";

export type QualityReportResponse = {
  report_id: number;
  target_type: string;
  report_count: number;
};

export type ReviewSession = {
  authenticated: boolean;
};

export type YoutubeReviewCandidate = {
  id: number;
  song_title: string;
  artist_name: string;
  youtube_title: string;
  youtube_url: string;
  video_id: string;
  channel_title: string;
  channel_id: string;
  uploaded_year: number | null;
  uploaded_month: number | null;
  official_score: number;
  source_type: string;
  status: string;
  review_reason: string;
  duration_seconds: number | null;
  view_count: number | null;
  created_at: string;
  updated_at: string;
};

export type YoutubeReviewCandidateList = {
  candidates: YoutubeReviewCandidate[];
  total: number;
};

export type YoutubeReviewActionResult = {
  candidate: YoutubeReviewCandidate;
  result: string;
  reason: string;
};

export type RoomSocketMessage =
  | { type: "room_state"; room: RoomState }
  | { type: "round_started"; round: CurrentRound }
  | { type: "pong" }
  | { type: "error"; message: string };
