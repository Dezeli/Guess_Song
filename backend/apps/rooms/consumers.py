from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.core.exceptions import ObjectDoesNotExist

from .services import get_room_state, room_group_name


class RoomConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self) -> None:
        self.room_code = self.scope["url_route"]["kwargs"]["code"].upper()
        self.group_name = room_group_name(self.room_code)

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        try:
            room = await database_sync_to_async(get_room_state)(self.room_code)
        except ObjectDoesNotExist:
            await self.send_json({"type": "error", "message": "Room not found."})
            await self.close(code=4404)
            return

        await self.send_json({"type": "room_state", "room": room})

    async def disconnect(self, close_code: int) -> None:
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content: dict, **kwargs) -> None:
        event_type = content.get("type")

        if event_type == "ping":
            await self.send_json({"type": "pong"})
            return

        await self.send_json(
            {
                "type": "error",
                "message": f"Unsupported event type: {event_type}",
            }
        )

    async def room_state(self, event: dict) -> None:
        await self.send_json({"type": "room_state", "room": event["room"]})
