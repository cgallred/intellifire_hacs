"""The IntelliFire integration."""
from __future__ import annotations

from aiohttp import ClientConnectionError
from intellifire4py.cloud_api import IntelliFireAPICloud
from intellifire4py.control import IntelliFireApiMode
from intellifire4py.exceptions import LoginError
from intellifire4py.local_api import IntelliFireAPILocal

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_API_KEY,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .const import (
    CONF_CLOUD_CONTROL_MODE,
    CONF_CLOUD_READ_MODE,
    CONF_USER_ID,
    DOMAIN,
    LOGGER,
)
from .coordinator import IntelliFireDataUpdateCoordinator

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.FAN,
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up IntelliFire from a config entry."""
    LOGGER.debug("Setting up config entry: %s", entry.unique_id)

    if CONF_USERNAME not in entry.data:
        LOGGER.debug("Old config entry format detected: %s", entry.unique_id)
        raise ConfigEntryAuthFailed

    # Additionally - verify credentials during login process
    cloud_api = IntelliFireAPICloud()
    try:
        await cloud_api.login(
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
        )
    except (ConnectionError, ClientConnectionError) as err:
        raise ConfigEntryNotReady from err
    except LoginError as err:
        raise ConfigEntryAuthFailed(err) from err

    # Once logged in - verify the config data is up to date.
    if CONF_USER_ID not in entry.data or CONF_API_KEY not in entry.data:
        LOGGER.info(
            "Updating IntelliFire config entry for %s with api information",
            entry.unique_id,
        )

        api_key = cloud_api.get_fireplace_api_key()
        user_id = cloud_api.get_user_id()
        # Update data entry
        hass.config_entries.async_update_entry(
            entry,
            data={
                **entry.data,
                CONF_API_KEY: api_key,
                CONF_USER_ID: user_id,
            },
        )
    else:
        api_key = entry.data[CONF_API_KEY]
        user_id = entry.data[CONF_USER_ID]

    # Instantiate local control
    api = IntelliFireAPILocal(
        fireplace_ip=entry.data[CONF_HOST],
        api_key=api_key,
        user_id=user_id,
    )

    # Parse options for Read/Control modes
    cloud_read_mode = entry.options.get(CONF_CLOUD_READ_MODE, False)
    cloud_control_mode = entry.options.get(CONF_CLOUD_CONTROL_MODE, False)
    read_mode = (
        IntelliFireApiMode.CLOUD if cloud_read_mode else IntelliFireApiMode.LOCAL
    )
    control_mode = (
        IntelliFireApiMode.CLOUD if cloud_control_mode else IntelliFireApiMode.LOCAL
    )

    # Construct coordinator
    data_update_coordinator = IntelliFireDataUpdateCoordinator(
        hass=hass,
        local_api=api,
        cloud_api=cloud_api,
        read_mode=read_mode,
        control_mode=control_mode,
    )

    await data_update_coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = data_update_coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""

    await hass.config_entries.async_reload(entry.entry_id)
