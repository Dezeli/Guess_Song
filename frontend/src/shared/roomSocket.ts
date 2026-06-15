import type { RoomSocketMessage } from "./types";

export function openRoomSocket(
  code: string,
  onMessage: (message: RoomSocketMessage) => void,
  onStatusChange: (status: "connecting" | "open" | "closed" | "error") => void,
) {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${window.location.host}/ws/rooms/${code}/`);

  onStatusChange("connecting");

  socket.addEventListener("open", () => {
    onStatusChange("open");
    socket.send(JSON.stringify({ type: "ping" }));
  });

  socket.addEventListener("message", (event) => {
    onMessage(JSON.parse(event.data) as RoomSocketMessage);
  });

  socket.addEventListener("close", () => {
    onStatusChange("closed");
  });

  socket.addEventListener("error", () => {
    onStatusChange("error");
  });

  return socket;
}
