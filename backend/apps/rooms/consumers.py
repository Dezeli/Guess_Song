from channels.generic.websocket import AsyncJsonWebsocketConsumer


class RoomConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self) -> None:
        self.room_code = self.scope["url_route"]["kwargs"]["code"]
        self.group_name = f"room_{self.room_code}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json({"type": "connected", "roomCode": self.room_code})

    async def disconnect(self, close_code: int) -> None:
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content: dict, **kwargs) -> None:
        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "room.message",
                "payload": content,
            },
        )

    async def room_message(self, event: dict) -> None:
        await self.send_json(event["payload"])
