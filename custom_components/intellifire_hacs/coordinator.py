"""The IntelliFire integration."""
from __future__ import annotations

from datetime import timedelta

from aiohttp import ClientConnectionError
from async_timeout import timeout
from intellifire4py.cloud_api import IntelliFireAPICloud
from intellifire4py.const import IntelliFireApiMode
from intellifire4py.control import IntelliFireController
from intellifire4py.local_api import IntelliFireAPILocal
from intellifire4py.model import IntelliFirePollData
from intellifire4py.read import IntelliFireDataProvider

from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, LOGGER


class IntelliFireDataUpdateCoordinator(DataUpdateCoordinator[IntelliFirePollData]):
    """Class to manage the polling of the fireplace API."""

    def __init__(
        self,
        hass: HomeAssistant,
        local_api: IntelliFireAPILocal,
        cloud_api: IntelliFireAPICloud,
        read_mode: IntelliFireApiMode,
        control_mode: IntelliFireApiMode,
    ) -> None:
        """Initialize the Coordinator."""
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=15),
        )
        self._local_api = local_api
        self._cloud_api = cloud_api
        self._read_mode = read_mode
        self._control_mode = control_mode

    def get_read_api(self) -> IntelliFireDataProvider:
        """Return the Status API pointer."""
        if self._read_mode == IntelliFireApiMode.LOCAL:
            return self._local_api
        return self._cloud_api

    def get_control_api(self) -> IntelliFireController:
        """Return the control API."""

        if self._control_mode == IntelliFireApiMode.LOCAL:
            return self._local_api
        return self._cloud_api

    def get_read_mode(self) -> IntelliFireApiMode:
        """Return _read_mode as a property."""
        return self._read_mode

    async def set_read_mode(self, mode: IntelliFireApiMode):
        """Set the read mode between Cloud/Local."""
        LOGGER.debug("Changing READ mode: %s=>%s", self._read_mode.name, mode.name)
        self._read_mode = mode

    def get_control_mode(self) -> IntelliFireApiMode:
        """Read control mode as a property."""
        return self._control_mode

    async def set_control_mode(self, mode: IntelliFireApiMode):
        """Set the control mode between Cloud/Local."""
        LOGGER.debug(
            "Changing CONTROL mode: %s=>%s", self._control_mode.name, mode.name
        )
        current_mode = self._control_mode

        if current_mode == mode:
            LOGGER.info("Not updating mode -- it was the same")
            return

        if current_mode == IntelliFireApiMode.LOCAL:  # Switching to cloud
            # Switch from local to cloud polling
            await self._local_api.stop_background_polling()

            # Copy existing local data to clou data
            self._cloud_api.overwrite_data(self._local_api.data)

            await self._cloud_api.start_background_polling()

        if current_mode == IntelliFireApiMode.CLOUD:  # switch to local mode
            await self._cloud_api.stop_background_polling()

            # Copy existing cloud data to local
            self._local_api.overwrite_data(self._cloud_api.data)

            await self._local_api.start_background_polling()

    async def _async_update_data(self) -> IntelliFirePollData:
        LOGGER.debug("Update Data Called [%s]", self._read_mode.name)

        read_api = self.get_read_api()
        read_mode = self.get_read_mode()

        # Ensure the api is polling
        if not read_api.is_polling_in_background:
            LOGGER.info("Starting background polling for %s API", read_mode.name)
            await read_api.start_background_polling()

            # If local - ensure we have some data
            if read_mode == IntelliFireApiMode.LOCAL:
                async with timeout(15):
                    try:
                        await self._local_api.poll()
                    except (ConnectionError, ClientConnectionError) as exception:
                        raise UpdateFailed from exception

        # For local polling verify the timeouts
        if self._local_api.failed_poll_attempts > 10:
            LOGGER.debug("Too many polling errors - raising exception")
            raise UpdateFailed

        return read_api.data

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""

        data = self.get_read_api().data
        return DeviceInfo(
            manufacturer="Hearth and Home",
            model="IFT-WFM",
            name="IntelliFire",
            identifiers={("IntelliFire", f"{data.serial}]")},
            sw_version=data.fw_ver_str,
            configuration_url=f"http://{self._local_api.fireplace_ip}/poll",
        )
