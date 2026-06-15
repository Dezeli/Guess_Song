import { create } from "zustand";

import type { CurrentRound, RoomState, SubmitAnswerResponse } from "../shared/types";

type SocketStatus = "idle" | "connecting" | "open" | "closed" | "error";

type RoomStore = {
  room: RoomState | null;
  hostToken: string | null;
  participantToken: string | null;
  socketStatus: SocketStatus;
  lastRoundStarted: CurrentRound | null;
  lastAnswerResult: SubmitAnswerResponse | null;
  setRoom: (room: RoomState | null) => void;
  setHostToken: (token: string | null) => void;
  setParticipantToken: (token: string | null) => void;
  setSocketStatus: (status: SocketStatus) => void;
  setLastRoundStarted: (round: CurrentRound | null) => void;
  setLastAnswerResult: (result: SubmitAnswerResponse | null) => void;
  reset: () => void;
};

export const useRoomStore = create<RoomStore>((set) => ({
  room: null,
  hostToken: localStorage.getItem("guess_song_host_token"),
  participantToken: localStorage.getItem("guess_song_participant_token"),
  socketStatus: "idle",
  lastRoundStarted: null,
  lastAnswerResult: null,
  setRoom: (room) => {
    if (room) {
      localStorage.setItem("guess_song_room_code", room.code);
    } else {
      localStorage.removeItem("guess_song_room_code");
    }
    set({ room });
  },
  setHostToken: (token) => {
    if (token) {
      localStorage.setItem("guess_song_host_token", token);
    } else {
      localStorage.removeItem("guess_song_host_token");
    }
    set({ hostToken: token });
  },
  setParticipantToken: (token) => {
    if (token) {
      localStorage.setItem("guess_song_participant_token", token);
    } else {
      localStorage.removeItem("guess_song_participant_token");
    }
    set({ participantToken: token });
  },
  setSocketStatus: (socketStatus) => set({ socketStatus }),
  setLastRoundStarted: (lastRoundStarted) => set({ lastRoundStarted }),
  setLastAnswerResult: (lastAnswerResult) => set({ lastAnswerResult }),
  reset: () => {
    localStorage.removeItem("guess_song_room_code");
    localStorage.removeItem("guess_song_host_token");
    localStorage.removeItem("guess_song_participant_token");
    set({
      room: null,
      hostToken: null,
      participantToken: null,
      socketStatus: "idle",
      lastRoundStarted: null,
      lastAnswerResult: null,
    });
  },
}));
