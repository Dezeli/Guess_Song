import type {
  CreateRoomResponse,
  JoinRoomResponse,
  QuizPack,
  RoomSettings,
  RoomState,
  SubmitAnswerResponse,
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

export function joinRoom(code: string, nickname: string) {
  return request<JoinRoomResponse>(`/api/rooms/${code}/join`, {
    method: "POST",
    body: { nickname },
  });
}

export function leaveRoom(code: string, participantToken: string) {
  return request<{ room: RoomState }>(`/api/rooms/${code}/leave`, {
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
