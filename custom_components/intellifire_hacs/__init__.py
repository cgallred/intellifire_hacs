"""The IntelliFire integration."""
from __future__ import annotations

import asyncio

from intellifire4py import UnifiedFireplace
from intellifire4py.cloud_interface import IntelliFireCloudInterface
from intellifire4py.model import IntelliFireCommonFireplaceData

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_API_KEY,
    CONF_IP_ADDRESS,
    CONF_PASSWORD,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed

from .const import (
    CONF_AUTH_COOKIE,
    CONF_CONTROL_MODE,
    CONF_READ_MODE,
    CONF_SERIAL,
    CONF_USER_ID,
    CONF_WEB_CLIENT_ID,
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


def _construct_common_data(entry: ConfigEntry) -> IntelliFireCommonFireplaceData:
    """Convert a config entry into IntelliFireCommonFireplaceData."""

    return IntelliFireCommonFireplaceData(
        auth_cookie=entry.data[CONF_AUTH_COOKIE],
        user_id=entry.data[CONF_USER_ID],
        web_client_id=entry.data[CONF_WEB_CLIENT_ID],
        serial=entry.data[CONF_SERIAL],
        api_key=entry.data[CONF_API_KEY],
        ip_address=entry.data[CONF_IP_ADDRESS],
        read_mode=entry.options[CONF_READ_MODE],
        control_mode=entry.options[CONF_CONTROL_MODE],
    )


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old entry."""
    LOGGER.debug("Migrating from version %s", config_entry.version)

    if config_entry.version == 1:
        new = {**config_entry.data}

        # Rename Host to IP Address
        new[CONF_IP_ADDRESS] = new.pop("host")

        # Use credentials to get data I guess...
        serial = config_entry.title.replace("Fireplace ", "")

        username = config_entry.data[CONF_USERNAME]
        password = config_entry.data[CONF_PASSWORD]

        # Create a Cloud Interface
        cloud_interface = IntelliFireCloudInterface()
        await cloud_interface.login_with_credentials(
            username=username, password=password
        )

        new_data = cloud_interface.user_data.get_data_for_serial(serial)
        # Find the correct fireplace
        if new_data is not None:
            new[CONF_API_KEY] = new_data.api_key
            new[CONF_WEB_CLIENT_ID] = new_data.web_client_id
            new[CONF_AUTH_COOKIE] = new_data.auth_cookie

            new[CONF_IP_ADDRESS] = new_data.ip_address
            new[CONF_SERIAL] = new_data.serial

            config_entry.version = 2
            hass.config_entries.async_update_entry(
                config_entry,
                data=new,
                options={CONF_READ_MODE: "local", CONF_CONTROL_MODE: "local"},
                unique_id=serial,
            )
            LOGGER.debug("Migration to version %s successful", config_entry.version)
        else:
            return False

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up IntelliFire from a config entry."""
    LOGGER.debug("Setting up config entry: %s", entry.unique_id)
    LOGGER.debug(entry)

    if CONF_USERNAME not in entry.data:
        LOGGER.debug("Super Old config entry format detected: %s", entry.unique_id)
        raise ConfigEntryAuthFailed

    # Build a common data object to pass to the coordinator
    common_data: IntelliFireCommonFireplaceData = _construct_common_data(entry)
    fireplace: UnifiedFireplace = await UnifiedFireplace.build_fireplace_from_common(
        common_data
    )

    local_connect, cloud_connect = await _async_validate_connectivity(
        fireplace=fireplace, timeout=30
    )
    LOGGER.info(
        f"IntelliFire Connectivity: Local[{local_connect}]  Cloud[{cloud_connect}]"
    )

    # If neither Local nor Cloud works - raise an Authentication issue
    if (local_connect, cloud_connect) == (False, False):
        raise ConfigEntryAuthFailed

    try:
        # Wait for data - could have some logic to switch between cloud and local perhaps after a set timeout?
        await asyncio.wait_for(
            _async_wait_for_initialization(fireplace), timeout=600
        )  # 10 minutes
    except asyncio.TimeoutError as err:
        raise TimeoutError(
            "Initialization of fireplace timed out after 10 minutes"
        ) from err

    # Construct coordinator
    data_update_coordinator = IntelliFireDataUpdateCoordinator(
        hass=hass, fireplace=fireplace
    )

    await data_update_coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = data_update_coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(update_listener))
    return True


async def _async_validate_connectivity(
    fireplace: UnifiedFireplace, timeout=600
) -> tuple[bool, bool]:
    """Check local and cloud connectivity."""

    async def with_timeout(coroutine):
        try:
            await asyncio.wait_for(coroutine, timeout)
            return True
        except asyncio.TimeoutError:
            return False
        except Exception:  # pylint: disable=broad-except
            return False

    local_future = with_timeout(fireplace.perform_local_poll())
    cloud_future = with_timeout(fireplace.perform_cloud_poll())

    local_success, cloud_success = await asyncio.gather(local_future, cloud_future)
    return local_success, cloud_success


async def _async_wait_for_initialization(fireplace, timeout=600):
    """Wait for a fireplace to be initialized."""
    while (
        fireplace.data.ipv4_address == "127.0.0.1" and fireplace.data.serial == "unset"
    ):
        LOGGER.info("Waiting for fireplace to initialize")
        await asyncio.sleep(10)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""

    await hass.config_entries.async_reload(entry.entry_id)
