import xmltodict
from .isapi.models import AlertEvent
from .isapi.utils import deep_get
from .const import EVENTS
import xml.etree.ElementTree as ET

def parse_event_notification(xml: str) -> AlertEvent:
    """Parse incoming EventNotificationAlert XML message."""

    try:
      xml = xml.replace("&", "&amp;")
      data = xmltodict.parse(xml)
      alert = data["EventNotificationAlert"]

      event_type = alert.get("eventType")
      event_id = alert.get("eventType")

      if not EVENTS[event_type]:
          raise ValueError(f"Unsupported event: {event_type}\nXML: {xml}")

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
        raise ValueError(f"Failed to parse event XML: {e}\nXML: {xml}")

    return AlertEvent(
        None,
        channel_id,
        device_serial,
        None,
        None,
        event_id,
        event_type,
        event_description,
        event_state,
        port_number,
        mac,
        region_id,
        target_type,
        detection_target,
    )
