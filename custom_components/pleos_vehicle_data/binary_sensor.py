"""Boolean vehicle readings."""

from homeassistant.components.binary_sensor import BinarySensorEntity

from .entity import VehicleEntity, discover


async def async_setup_entry(hass, entry, async_add_entities):
    discover(entry, async_add_entities, "binary_sensor", ReadingBinarySensor)


class ReadingBinarySensor(VehicleEntity, BinarySensorEntity):
    platform_domain = "binary_sensor"
    def __init__(self, coordinator, car_id, key, spec):
        super().__init__(coordinator, car_id, key, spec)
        self._attr_device_class = spec.get("device_class")

    @property
    def is_on(self):
        return self.reading["value"] == "ON" if self.reading else None
