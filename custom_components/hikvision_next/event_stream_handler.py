import asyncio
import httpx
import xml.etree.ElementTree as ET
import logging
from .isapi.models import AlertEvent


from .const import (
    EVENTS,
    EVENTS_ALTERNATE_ID,
)

_LOGGER = logging.getLogger(__name__)

async def long_polling_task(hass):
    # Check for the configuration of our specific domain
    if "hikvision_custom" not in config:
        _LOGGER.error("Hikvision custom component not configured in configuration.yaml.")
        return False

    component_config = config["hikvision_custom"]

    # 1. We create the httpx.AsyncClient instance here, once per integration.
    #    The blocking SSL setup happens here, but Home Assistant's setup
    #    process is designed to handle this.
    try:
        client = httpx.AsyncClient()
    except Exception as e:
        _LOGGER.error("Failed to create HTTP client: %s", e)
        return False

    # 2. Instantiate the stream handler and pass the client and config to it.
    handler = HikvisionStreamHandler(hass, client, component_config)

    # Ensure the handler is ready to start streaming
    handler.start_stream()

    return True

class HikvisionStreamHandler:
    """
    Handles the Hikvision alert stream using an already-created HTTP client.
    """
    def __init__(self, hass, client, config):
        """Initialize the handler with the Home Assistant core, client, and config."""
        self._hass = hass
        self._client = client
        self._url = f"http://{config.get('host')}/ISAPI/Event/notification/alertStream"
        self._auth = httpx.BasicAuth(config.get('username'), config.get('password'))
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
                # Use the pre-initialized client to start the stream.
                async with self._client.stream(
                    "GET",
                    self._url,
                    auth=self._auth,
                    timeout=httpx.Timeout(300.0, connect=60.0),
                    headers={"Accept": "multipart/x-mixed-replace"},
                ) as resp:
                    resp.raise_for_status()
                    _LOGGER.info("Connected to alert stream, status: %s", resp.status_code)

                    async for chunk in resp.aiter_bytes():
                        buffer += chunk.decode("utf-8")

                        # Process chunks that contain a full XML event
                        if "</EventNotificationAlert>" in buffer:
                            try:
                                # Find the start and end of the first complete event
                                start_idx = buffer.find("<EventNotificationAlert")
                                end_idx = buffer.find("</EventNotificationAlert>")

                                if start_idx != -1 and end_idx != -1:
                                    event_xml = buffer[start_idx : end_idx + len("</EventNotificationAlert>")]

                                    _LOGGER.info("Alert received: %s", event_xml)

                                    # Clear the processed part of the buffer
                                    buffer = buffer[end_idx + len("</EventNotificationAlert>"):]

                            except Exception as e:
                                _LOGGER.warning("Failed to parse event XML chunk: %s", e)
                                buffer = "" # Clear buffer to avoid getting stuck on bad data

            except httpx.ReadTimeout:
                _LOGGER.warning("Event stream connection timed out. Attempting to reconnect...")
            except httpx.HTTPStatusError as e:
                _LOGGER.error(
                    "Event stream HTTP error: %s - %s. Retrying in 10s...",
                    e.response.status_code,
                    e.response.text,
                )
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                # This is how the task is gracefully stopped by Home Assistant.
                _LOGGER.info("Event stream task cancelled, stopping.")
                self._running = False
            except Exception as e:
                _LOGGER.error("Event stream an unexpected error: %s. Retrying in 10s...", str(e))
                await asyncio.sleep(10)

    @staticmethod
    def parse_event_notification(xml: str) -> AlertEvent:
        """Parse incoming EventNotificationAlert XML message."""

        # Fix for some cameras sending non html encoded data
        xml = xml.replace("&", "&amp;")

        data = xmltodict.parse(xml)
        alert = data["EventNotificationAlert"]

        event_type = alert.get("eventType")
        event_id = alert.get("eventType")
        if not event_id or event_id == "duration":
            # <EventNotificationAlert version="2.0"
            event_id = alert["DurationList"]["Duration"]["relationEvent"]
        event_id = event_id.lower()

        # handle alternate event type
        if EVENTS_ALTERNATE_ID.get(event_id):
            event_id = EVENTS_ALTERNATE_ID[event_id]

        channel_id = int(alert.get("channelID", alert.get("dynChannelID", 0)))
        io_port_id = int(alert.get("portNo", 0))
        # <EventNotificationAlert version="1.0"
        device_serial = deep_get(alert, "Extensions.serialNumber.#text")
        # <EventNotificationAlert version="2.0"
        mac = alert.get("macAddress")

        target_type =  alert.get("targetType")
        detection_picture_trans_type = alert.get("PictureTransType")
        detection_pictures_number = int(alert.get("detectionPicturesNumber", 0))
        event_description =  alert.get("eventDescription")


        detection_target = deep_get(alert, "DetectionRegionList.DetectionRegionEntry.detectionTarget")
        region_id = int(deep_get(alert, "DetectionRegionList.DetectionRegionEntry.regionID", 0))

        if not EVENTS[event_id]:
            raise ValueError(f"Unsupported event {event_id}")

        return AlertEvent(
            channel_id,
            io_port_id,
            event_id,
            device_serial,
            mac,
            region_id,
            detection_target,
        )
