import type {
  CreateRoomResponse,
  JoinRoomResponse,
  ParticipantIdentityResponse,
  QuizPack,
  ReviewSession,
  RoomSettings,
  RoomState,
  SubmitAnswerResponse,
  YoutubeReviewActionResult,
  YoutubeReviewCandidate,
  YoutubeReviewCandidateList,
} from "./types";

type RequestOptions = {
  body?: unknown;
  headers?: Record<string, string>;
};

async function request<T>(path: string, options: RequestOptions & { method?: string } = {}): Promise<T> {
  const response = await fetch(path, {
    method: options.method ?? "GET",
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });

  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const data = await response.json();
      message = data.detail ?? message;
    } catch {
      // Keep the HTTP status fallback.
    }
    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

export function listQuizPacks() {
  return request<QuizPack[]>("/api/quiz-packs");
}

export function createRoom(input: {
  quiz_pack_id: number;
  host_nickname: string;
  settings: RoomSettings;
}) {
  return request<CreateRoomResponse>("/api/rooms", {
    method: "POST",
    body: input,
  });
}

export function getRoom(code: string) {
  return request<RoomState>(`/api/rooms/${code}`);
}

export function getCurrentParticipant(code: string, participantToken: string) {
  return request<ParticipantIdentityResponse>(`/api/rooms/${code}/me`, {
    headers: { "X-Participant-Token": participantToken },
  });
}

export function joinRoom(code: string, nickname: string, teamId?: number | null) {
  return request<JoinRoomResponse>(`/api/rooms/${code}/join`, {
    method: "POST",
    body: { nickname, team_id: teamId ?? null },
  });
}

export function leaveRoom(code: string, participantToken: string) {
  return request<{ room: RoomState }>(`/api/rooms/${code}/leave`, {
    method: "POST",
    headers: { "X-Participant-Token": participantToken },
  });
}

export function setParticipantAway(code: string, participantToken: string) {
  return request<{ room: RoomState }>(`/api/rooms/${code}/away`, {
    method: "POST",
    headers: { "X-Participant-Token": participantToken },
  });
}

export function setParticipantActive(code: string, participantToken: string) {
  return request<{ room: RoomState }>(`/api/rooms/${code}/active`, {
    method: "POST",
    headers: { "X-Participant-Token": participantToken },
  });
}

export function startGame(code: string, hostToken: string) {
  return request<{ room: RoomState }>(`/api/rooms/${code}/start`, {
    method: "POST",
    headers: { "X-Host-Token": hostToken },
  });
}

export function skipCurrentRound(code: string, participantToken: string) {
  return request<{ room: RoomState }>(`/api/rooms/${code}/rounds/current/skip`, {
    method: "POST",
    headers: { "X-Participant-Token": participantToken },
  });
}

export function forceSkipCurrentRound(code: string, hostToken: string) {
  return request<{ room: RoomState }>(`/api/rooms/${code}/rounds/current/force-skip`, {
    method: "POST",
    headers: { "X-Host-Token": hostToken },
  });
}

export function startCurrentRound(code: string, hostToken: string) {
  return request(`/api/rooms/${code}/rounds/current/start`, {
    method: "POST",
    headers: { "X-Host-Token": hostToken },
  });
}

export function moveToNextRound(code: string, hostToken: string) {
  return request<{ room: RoomState }>(`/api/rooms/${code}/rounds/next`, {
    method: "POST",
    headers: { "X-Host-Token": hostToken },
  });
}

export function submitAnswer(code: string, participantToken: string, answer: string) {
  return request<SubmitAnswerResponse>(`/api/rooms/${code}/rounds/current/answers`, {
    method: "POST",
    headers: { "X-Participant-Token": participantToken },
    body: { answer },
  });
}

export function reviewLogin(password: string) {
  return request<ReviewSession>("/api/review/login", {
    method: "POST",
    body: { password },
  });
}

export function getReviewSession() {
  return request<ReviewSession>("/api/review/session");
}

export function reviewLogout() {
  return request<ReviewSession>("/api/review/logout", {
    method: "POST",
  });
}

export function listYoutubeReviewCandidates(status: string, limit = 50) {
  return request<YoutubeReviewCandidateList>(
    `/api/review/youtube-candidates?status=${encodeURIComponent(status)}&limit=${limit}`,
  );
}

export function getYoutubeReviewCandidate(id: number) {
  return request<YoutubeReviewCandidate>(`/api/review/youtube-candidates/${id}`);
}

export function approveYoutubeReviewCandidate(id: number, input: { song_title: string; artist_name: string }) {
  return request<YoutubeReviewActionResult>(`/api/review/youtube-candidates/${id}/approve`, {
    method: "POST",
    body: input,
  });
}

export function rejectYoutubeReviewCandidate(id: number, reason: string) {
  return request<YoutubeReviewActionResult>(`/api/review/youtube-candidates/${id}/reject`, {
    method: "POST",
    body: { reason },
  });
}
