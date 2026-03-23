"""Terncy light platform."""
import logging
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_HS_COLOR,
    ColorMode,
    LightEntity,
    ColorMode,
)

# 导入必要的常量
SUPPORT_BRIGHTNESS = 1
SUPPORT_COLOR_TEMP = 2
SUPPORT_COLOR = 4

from homeassistant.const import CONF_DEVICE_ID
from .const import DOMAIN, TERNCY_HUB_ID

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Terncy light platform."""
    hub_id = config_entry.data[TERNCY_HUB_ID]
    hub = hass.data[DOMAIN][hub_id]

    def add_entities(devices):
        async_add_entities(
            [TerncyLight(hub, device) for device in devices], True
        )

    hub.add_device_callback("light", add_entities)


class TerncyLight(LightEntity):
    """Representation of a Terncy light."""

    def __init__(self, hub, device):
        """Initialize the light."""
        self._hub = hub
        self._device = device
        self._name = device.get("name", f"Terncy Light {device['id']}")
        self._id = device["id"]
        self._available = True
        self._state = False
        self._brightness = 0
        self._hs_color = None
        self._color_temp = None
        self._supported_features = 0
        self._color_mode = ColorMode.UNKNOWN
        self._supported_color_modes = set()

        self._update_features()

    def _update_features(self):
        """Update supported features and color modes."""
        features = self._device.get("features", [])
        self._supported_features = 0
        self._supported_color_modes = set()

        if "brightness" in features:
            self._supported_features |= SUPPORT_BRIGHTNESS
            self._supported_color_modes.add(ColorMode.BRIGHTNESS)

        if "color_temp" in features:
            self._supported_features |= SUPPORT_COLOR_TEMP
            self._supported_color_modes.add(ColorMode.COLOR_TEMP)

        if "color" in features:
            self._supported_features |= SUPPORT_COLOR
            self._supported_color_modes.add(ColorMode.HS)

        # 默认回退逻辑
        if not self._supported_color_modes:
            self._supported_color_modes.add(ColorMode.ONOFF)

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._id

    @property
    def name(self):
        """Return the name of the light."""
        return self._name

    @property
    def available(self):
        """Return True if entity is available."""
        return self._available

    @property
    def is_on(self):
        """Return True if light is on."""
        return self._state

    @property
    def brightness(self):
        """Return the brightness of the light."""
        return self._brightness

    @property
    def hs_color(self):
        """Return the hs color of the light."""
        return self._hs_color

    @property
    def color_temp(self):
        """Return the color temperature of the light."""
        return self._color_temp

    @property
    def supported_features(self):
        """Flag supported features."""
        return self._supported_features

    @property
    def supported_color_modes(self) -> set[ColorMode] | None:
        """Flag supported color modes (HA 2026 Strict Check)."""
        # 核心修复：如果硬件不支持色温，强制只返回亮度或开关模式
        if not (self._supported_features & SUPPORT_COLOR_TEMP):
            if self._supported_features & SUPPORT_BRIGHTNESS:
                return {ColorMode.BRIGHTNESS}
            return {ColorMode.ONOFF}
        return self._supported_color_modes

    @property
    def color_mode(self) -> ColorMode | str | None:
        """Return the current color mode of the light."""
        # 核心修复：防止上报硬件不支持的 color_temp 导致 HA 崩溃
        if not (self._supported_features & SUPPORT_COLOR_TEMP):
            if self._color_mode == ColorMode.COLOR_TEMP:
                return ColorMode.BRIGHTNESS
        return self._color_mode

    async def async_turn_on(self, **kwargs):
        """Turn on the light."""
        params = {"state": 1}

        if ATTR_BRIGHTNESS in kwargs:
            params["brightness"] = int(kwargs[ATTR_BRIGHTNESS] / 2.55)

        if ATTR_COLOR_TEMP in kwargs:
            # 只有硬件支持时才允许发送色温指令
            if self._supported_features & SUPPORT_COLOR_TEMP:
                params["color_temp"] = kwargs[ATTR_COLOR_TEMP]

        if ATTR_HS_COLOR in kwargs:
            if self._supported_features & SUPPORT_COLOR:
                params["color"] = {
                    "h": int(kwargs[ATTR_HS_COLOR][0]),
                    "s": int(kwargs[ATTR_HS_COLOR][1]),
                }

        await self._hub.edit_device(self._id, params)

    async def async_turn_off(self, **kwargs):
        """Turn off the light."""
        await self._hub.edit_device(self._id, {"state": 0})

    def update_state(self, msg_data):
        """Update the light state from hub message."""
        if "state" in msg_data:
            self._state = msg_data["state"] == 1
        
        if "brightness" in msg_data:
            self._brightness = int(msg_data["brightness"] * 2.55)

        if "color_temp" in msg_data:
            self._color_temp = msg_data["color_temp"]
            # 仅当硬件支持时才切换到色温模式，否则降级为亮度模式
            if self._supported_features & SUPPORT_COLOR_TEMP:
                self._color_mode = ColorMode.COLOR_TEMP
            else:
                self._color_mode = ColorMode.BRIGHTNESS

        if "color" in msg_data:
            color = msg_data["color"]
            self._hs_color = (color.get("h", 0), color.get("s", 0))
            self._color_mode = ColorMode.HS

        # 兜底逻辑：确保 color_mode 永远有效
        if self._color_mode == ColorMode.UNKNOWN or self._color_mode is None:
            if self._supported_features & SUPPORT_COLOR:
                self._color_mode = ColorMode.HS
            elif self._supported_features & SUPPORT_COLOR_TEMP:
                self._color_mode = ColorMode.COLOR_TEMP
            elif self._supported_features & SUPPORT_BRIGHTNESS:
                self._color_mode = ColorMode.BRIGHTNESS
            else:
                self._color_mode = ColorMode.ONOFF

        self.async_write_ha_state()
