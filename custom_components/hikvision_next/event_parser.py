import xmltodict
from .isapi.models import AlertEvent
from .isapi.utils import deep_get
from .const import EVENTS
import xml.etree.ElementTree as ET
import logging

_LOGGER = logging.getLogger(__name__)

def parse_event_notification(event_xml: str) -> AlertEvent:
    """Parse incoming EventNotificationAlert XML message."""

    _LOGGER.debug("Alert received: %s", event_xml)

    try:
      event_xml = event_xml.replace("&", "&amp;")
      data = xmltodict.parse(event_xml)
      alert = data["EventNotificationAlert"]

      event_type = alert.get("eventType")
      event_id = alert.get("eventType")

      # Ignore video loss events from channel 0 because this seems to be false positives
      if event_type == "videoloss" and alert.get("channelID") == "0":
          return None

      if not EVENTS[event_type]:
          raise ValueError(f"Unsupported event: {event_type}\nXML: {event_xml}")

      if not event_id or event_id == "duration":
          event_id = alert["DurationList"]["Duration"]["relationEvent"]
      event_id = event_id.lower()

      if EVENTS.get(event_id):
          event_id = EVENTS[event_id]

      channel_id = int(alert.get("channelID", alert.get("dynChannelID", 0)))
      port_number = int(alert.get("portNo", 0))
      device_serial = deep_get(alert, "Extensions.serialNumber.#text")
      mac = alert.get("macAddress")
      event_description = alert.get("eventDescription", "")
      event_state = alert.get("eventState", "")
      region_id = int(deep_get(alert, "DetectionRegionList.DetectionRegionEntry.regionID", 0))
      target_type = alert.get("targetType", "")
      detection_target = deep_get(alert, "DetectionRegionList.DetectionRegionEntry.detectionTarget")


    except (xmltodict.expat.ExpatError, KeyError, ValueError) as e:
        raise ValueError(f"Failed to parse event XML: {e}\nXML: {event_xml}")

    return AlertEvent(
        channel_id,
        event_id,
        event_type,
        event_state,
        port_number,
        None,
        device_serial,
        None,
        None,
        event_description,
        mac,
        region_id,
        target_type,
        detection_target,
    )
