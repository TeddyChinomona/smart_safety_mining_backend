import json
from urllib.parse import parse_qs

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

from .models import SensorEvent, WorkerStatus
from .serializers import SensorEventSerializer, WorkerStatusSerializer


def _validate_jwt(token: str) -> bool:
    """Synchronous JWT validation — run via database_sync_to_async."""
    if not token:
        return False
    try:
        from rest_framework_simplejwt.tokens import AccessToken
        AccessToken(token)          # raises if expired / invalid
        return True
    except Exception:
        return False


class _BaseConsumer(AsyncWebsocketConsumer):
    """Shared auth helper — reads ?token= from the WS query string."""

    async def _auth_ok(self) -> bool:
        qs = parse_qs(self.scope.get("query_string", b"").decode())
        token = (qs.get("token") or [None])[0]
        return await database_sync_to_async(_validate_jwt)(token)


# ── Sensor Events ──────────────────────────────────────────────────────────────

class SensorEventConsumer(_BaseConsumer):
    async def connect(self):
        # Accept the HTTP→WS upgrade first (required before close() works)
        await self.accept()

        if not await self._auth_ok():
            await self.close(code=4001)   # 4001 = custom "Unauthorized"
            return

        self.group_name = "sensor_events"
        await self.channel_layer.group_add(self.group_name, self.channel_name)

        events = await self._recent_events()
        await self.send(text_data=json.dumps({"type": "initial_data", "data": events}))

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    # Called by Celery task via channel_layer.group_send
    async def sensor_event_message(self, event):
        await self.send(text_data=json.dumps({"type": "new_event", "data": event["data"]}))

    @database_sync_to_async
    def _recent_events(self):
        qs = SensorEvent.objects.select_related("worker").order_by("-timestamp")[:50]
        return SensorEventSerializer(qs, many=True).data


# ── Worker Statuses ────────────────────────────────────────────────────────────

class WorkerStatusConsumer(_BaseConsumer):
    async def connect(self):
        await self.accept()

        if not await self._auth_ok():
            await self.close(code=4001)
            return

        self.group_name = "worker_statuses"
        await self.channel_layer.group_add(self.group_name, self.channel_name)

        statuses = await self._current_statuses()
        await self.send(text_data=json.dumps({"type": "initial_data", "data": statuses}))

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    # Called by Celery task via channel_layer.group_send
    async def worker_status_message(self, event):
        await self.send(text_data=json.dumps({"type": "status_update", "data": event["data"]}))

    @database_sync_to_async
    def _current_statuses(self):
        return WorkerStatusSerializer(WorkerStatus.objects.all(), many=True).data