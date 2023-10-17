"""Define switch func."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from intellifire4py.const import IntelliFireApiMode

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import IntelliFireDataUpdateCoordinator
from .const import DOMAIN
from .entity import IntelliFireEntity


@dataclass()
class IntelliFireSwitchRequiredKeysMixin:
    """Mixin for required keys."""

    on_fn: Callable[[IntelliFireDataUpdateCoordinator], Awaitable]
    off_fn: Callable[[IntelliFireDataUpdateCoordinator], Awaitable]
    value_fn: Callable[[IntelliFireDataUpdateCoordinator], bool]


@dataclass
class IntelliFireSwitchEntityDescription(
    SwitchEntityDescription, IntelliFireSwitchRequiredKeysMixin
):
    """Describes a switch entity."""


INTELLIFIRE_SWITCHES: tuple[IntelliFireSwitchEntityDescription, ...] = (
    IntelliFireSwitchEntityDescription(
        key="on_off",
        translation_key="flame",
        on_fn=lambda coordinator: coordinator.get_control_api().flame_on(),
        off_fn=lambda coordinator: coordinator.get_control_api().flame_off(),
        value_fn=lambda coordinator: coordinator.get_read_api().data.is_on,
    ),
    IntelliFireSwitchEntityDescription(
        key="pilot",
        translation_key="pilot_light",
        icon="mdi:fire-alert",
        on_fn=lambda coordinator: coordinator.get_control_api().pilot_on(),
        off_fn=lambda coordinator: coordinator.get_control_api().pilot_off(),
        value_fn=lambda coordinator: coordinator.get_read_api().data.pilot_on,
    ),
    IntelliFireSwitchEntityDescription(
        key="cloud_read",
        name="Cloud read",
        on_fn=lambda coordinator: coordinator.set_read_mode(IntelliFireApiMode.CLOUD),
        off_fn=lambda coordinator: coordinator.set_read_mode(IntelliFireApiMode.LOCAL),
        value_fn=lambda coordinator: coordinator.get_read_mode()
        == IntelliFireApiMode.CLOUD,
    ),
    IntelliFireSwitchEntityDescription(
        key="cloud_control",
        name="Cloud control",
        on_fn=lambda coordinator: coordinator.set_control_mode(
            IntelliFireApiMode.CLOUD
        ),
        off_fn=lambda coordinator: coordinator.set_control_mode(
            IntelliFireApiMode.LOCAL
        ),
        value_fn=lambda coordinator: coordinator.get_control_mode()
        == IntelliFireApiMode.CLOUD,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configure switch entities."""
    coordinator: IntelliFireDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        IntelliFireSwitch(coordinator=coordinator, description=description)
        for description in INTELLIFIRE_SWITCHES
    )


class IntelliFireSwitch(IntelliFireEntity, SwitchEntity):
    """Define an Intellifire Switch."""

    entity_description: IntelliFireSwitchEntityDescription

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch."""
        await self.entity_description.on_fn(self.coordinator)
        await self.async_update_ha_state(force_refresh=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        await self.entity_description.off_fn(self.coordinator)
        await self.async_update_ha_state(force_refresh=True)

    @property
    def is_on(self) -> bool | None:
        """Return the on state."""
        return self.entity_description.value_fn(self.coordinator)

    # @property
    # def icon(self) -> str:
    #     """Return switch icon."""
    #     return "mdi:wifi" if self.is_on else "mdi:wifi-off"
