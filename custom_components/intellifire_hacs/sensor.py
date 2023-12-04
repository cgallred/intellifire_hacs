"""Platform for sensor integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.dt import utcnow

from .const import DOMAIN
from .coordinator import IntelliFireDataUpdateCoordinator
from .entity import IntelliFireEntity


@dataclass
class IntellifireSensorRequiredKeysMixin:
    """Mixin for required keys."""

    value_fn: Callable[
        [IntelliFireDataUpdateCoordinator], int | str | datetime | float | None
    ]


@dataclass
class IntellifireSensorEntityDescription(
    SensorEntityDescription,
    IntellifireSensorRequiredKeysMixin,
):
    """Describes a sensor entity."""


def _time_remaining_to_timestamp(
    coordinator: IntelliFireDataUpdateCoordinator
) -> datetime | None:
    """Define a sensor that takes into account timezone."""
    if not (seconds_offset := coordinator.read_api.data.timeremaining_s):
        return None
    return utcnow() + timedelta(seconds=seconds_offset)


def _downtime_to_timestamp(
    coordinator: IntelliFireDataUpdateCoordinator
) -> datetime | None:
    """Define a sensor that takes into account a timezone."""
    if not (seconds_offset := coordinator.read_api.data.downtime):
        return None
    return utcnow() - timedelta(seconds=seconds_offset)


INTELLIFIRE_SENSORS: tuple[IntellifireSensorEntityDescription, ...] = (
    IntellifireSensorEntityDescription(
        key="flame_height",
        translation_key="flame_height",
        icon="mdi:fire-circle",
        state_class=SensorStateClass.MEASUREMENT,
        # UI uses 1-5 for flame height, backing lib uses 0-4
        value_fn=lambda coordinator: (coordinator.read_api.data.flameheight + 1),
    ),
    IntellifireSensorEntityDescription(
        key="temperature",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda coordinator: coordinator.read_api.data.temperature_c,
    ),
    IntellifireSensorEntityDescription(
        key="target_temp",
        translation_key="target_temp",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda coordinator: coordinator.read_api.data.thermostat_setpoint_c,
    ),
    IntellifireSensorEntityDescription(
        key="fan_speed",
        translation_key="fan_speed",
        icon="mdi:fan",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.read_api.data.fanspeed,
    ),
    IntellifireSensorEntityDescription(
        key="timer_end_timestamp",
        translation_key="timer_end_timestamp",
        icon="mdi:timer-sand",
        # state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_time_remaining_to_timestamp,
    ),
    IntellifireSensorEntityDescription(
        key="downtime",
        translation_key="downtime",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_downtime_to_timestamp,
    ),
    IntellifireSensorEntityDescription(
        key="uptime",
        translation_key="uptime",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda coordinator: utcnow()
        - timedelta(seconds=coordinator.read_api.data.uptime),
    ),
    IntellifireSensorEntityDescription(
        key="connection_quality",
        translation_key="connection_quality",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda coordinator: coordinator.read_api.data.connection_quality,
        entity_registry_enabled_default=False,
    ),
    IntellifireSensorEntityDescription(
        key="ecm_latency",
        translation_key="ecm_latency",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda coordinator: coordinator.read_api.data.ecm_latency,
        entity_registry_enabled_default=False,
    ),
    IntellifireSensorEntityDescription(
        key="ipv4_address",
        translation_key="ipv4_address",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda coordinator: coordinator.read_api.data.ipv4_address,
    ),
    IntellifireSensorEntityDescription(
        key="control_mode",
        translation_key="control_mode",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENUM,
        options=["local", "cloud"],
        value_fn=lambda coordinator: coordinator.get_read_mode().name.lower(),
    ),
    IntellifireSensorEntityDescription(
        key="read_mode",
        translation_key="read_mode",
        device_class=SensorDeviceClass.ENUM,
        entity_category=EntityCategory.DIAGNOSTIC,
        options=["local", "cloud"],
        value_fn=lambda coordinator: coordinator.get_control_mode().name.lower(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Define setup entry call."""

    coordinator: IntelliFireDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        IntelliFireSensor(coordinator=coordinator, description=description)
        for description in INTELLIFIRE_SENSORS
    )


class IntelliFireSensor(IntelliFireEntity, SensorEntity):
    """Extends IntelliFireEntity with Sensor specific logic."""

    entity_description: IntellifireSensorEntityDescription

    @property
    def native_value(self) -> int | str | datetime | float | None:
        """Return the state."""
        return self.entity_description.value_fn(self.coordinator)
