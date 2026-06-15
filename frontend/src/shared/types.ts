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
  settings: Record<string, unknown>;
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
};

export type RoomSocketMessage =
  | { type: "room_state"; room: RoomState }
  | { type: "round_started"; round: CurrentRound }
  | { type: "pong" }
  | { type: "error"; message: string };
