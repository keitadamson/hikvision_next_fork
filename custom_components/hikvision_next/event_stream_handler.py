import asyncio
import aiohttp
import logging

from .event_parser import parse_event_notification

_LOGGER = logging.getLogger(__name__)

async def long_polling_task(hass, config):
    async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(config["username"], config["password"])) as client:
        handler = HikvisionStreamHandler(hass, client, config)
        await handler.start_stream()

    return True

class HikvisionStreamHandler:
    """
    Handles the Hikvision alert stream using an already-created HTTP client.
    """
    def __init__(self, hass, client, config):
        """Initialize the handler with the Home Assistant core, client, and config."""
        self._hass = hass
        self._client = client
        self._url = f"{config["host"]}/ISAPI/Event/notification/alertStream"
        self._running = True

    async def start_stream(self):
        """
        Starts the event stream listener and logs the received data.
        This method is designed to run as a background task.
        """
        _LOGGER.info("Starting listener for event stream: %s", self._url)

        buffer = ""
        while self._running:
            try:
                async with self._client.get(
                    self._url,
                    timeout=aiohttp.ClientTimeout(total=600, connect=60),
                    headers={"Accept": "multipart/x-mixed-replace"},
                ) as resp:
                    resp.raise_for_status()
                    _LOGGER.info("Connected to alert stream, status: %s", resp.status)

                    async for chunk, _ in resp.content.iter_chunks():
                        buffer += chunk.decode("utf-8")

                        # Process chunks that contain a full XML event
                        if "</EventNotificationAlert>" in buffer:
                            try:
                                # Find the start and end of the first complete event
                                start_idx = buffer.find("<EventNotificationAlert")
                                end_idx = buffer.find("</EventNotificationAlert>")

                                if start_idx != -1 and end_idx != -1:
                                    event_xml = buffer[start_idx : end_idx + len("</EventNotificationAlert>")]

                                    event = parse_event_notification(event_xml)
                                    _LOGGER.debug("Parsed AlertEvent: %s", event)

                                    # Clear the processed part of the buffer
                                    buffer = buffer[end_idx + len("</EventNotificationAlert>"):]

                            except Exception as e:
                                _LOGGER.warning("Failed to parse event XML chunk: %s", e)
                                buffer = "" # Clear buffer to avoid getting stuck on bad data

            except asyncio.TimeoutError:
                _LOGGER.info("Event stream connection timed out. Attempting to reconnect...")
            except aiohttp.ClientResponseError as e:
                _LOGGER.error(
                    "Event stream HTTP error: %s - %s. Retrying in 10s...",
                    e.status,
                    e.message,
                )
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                # This is how the task is gracefully stopped by Home Assistant.
                _LOGGER.info("Event stream task cancelled, stopping.")
                self._running = False
            except Exception as e:
                _LOGGER.error("Event stream an unexpected error: %s. Retrying in 10s...", str(e))
                await asyncio.sleep(10)
