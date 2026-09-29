"""Sensors: battery, charge, driving, cabin and tyres."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfLength,
    UnitOfPower,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import VigieConfigEntry
from .const import ABILITY_CHARGE
from .coordinator import VigieCoordinator, VigieData
from .entity import VigieEntity, add_when_available
from .helpers import CHARGE_STATES, charge_state, fast_charging, num

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class VigieSensorDescription(SensorEntityDescription):
    """Sensor fed by the Vigie state, battery or charges endpoints."""

    value_fn: Callable[[VigieData], Any]
    exists_fn: Callable[[VigieData], bool]
    attrs_fn: Callable[[VigieData], dict[str, Any] | None] | None = None
    live: bool = False
    # Unavailable while this returns False (not charging, no destination…).
    available_fn: Callable[[VigieData], bool] | None = None
    # Hidden when the matching control (number) exists.
    replaced_by_ability: str | None = None


def _field(name: str, *, round_to: int | None = None, factor: float = 1.0) -> dict[str, Any]:
    def value(data: VigieData) -> float | None:
        v = num(data, name)
        if v is None:
            return None
        v *= factor
        return round(v, round_to) if round_to is not None else v

    return {"value_fn": value, "exists_fn": lambda d: d.has(name)}


def _battery(name: str) -> dict[str, Any]:
    return {
        "value_fn": lambda d: (d.battery or {}).get(name),
        "exists_fn": lambda d: (d.battery or {}).get(name) is not None,
    }


def _battery_level(data: VigieData) -> float | None:
    """Most recent of BatteryLevel and Soc (ioDek profiles no longer request BatteryLevel: its last value can be old)."""
    candidates = []
    for name in ("Soc", "BatteryLevel"):
        item = data.values.get(name)
        if isinstance(item, dict) and num(data, name) is not None:
            candidates.append((item.get("age_s") if item.get("age_s") is not None else 10**9, name))
    if not candidates:
        return None
    v = num(data, min(candidates)[1])
    return round(v, 1) if v is not None else None


def _cell_gap(data: VigieData) -> float | None:
    high, low = num(data, "BrickVoltageMax"), num(data, "BrickVoltageMin")
    if high is not None and low is not None:
        return round((high - low) * 1000, 1)
    return (data.battery or {}).get("cell_gap_max_mv")


def _charging_power(data: VigieData) -> float | None:
    v = num(data, "DCChargingPower") if fast_charging(data) else num(data, "ACChargingPower")
    return round(v / 1000, 2) if v is not None else None


def _session_energy(data: VigieData) -> float | None:
    v = num(data, "DCChargingEnergyIn") if fast_charging(data) else num(data, "ACChargingEnergyIn")
    return round(v, 2) if v is not None else None


def _pack_power(data: VigieData) -> float | None:
    v = data.state.get("pack_power_w")
    return round(float(v) / 1000, 2) if v is not None else None


def _session(data: VigieData) -> dict[str, Any]:
    return data.state.get("charge_session") or {}


def _nav(data: VigieData) -> dict[str, Any]:
    return data.state.get("navigation") or {}


def _time(raw: str | None) -> datetime | None:
    return dt_util.parse_datetime(raw) if raw else None


def _eta_attrs(data: VigieData) -> dict[str, Any]:
    s = _session(data)
    return {"source": s.get("eta_source"), "target_soc": s.get("target_soc"), "end": s.get("eta")}


def _last_seen(data: VigieData) -> datetime | None:
    raw = data.state.get("last_received_at")
    return dt_util.parse_datetime(raw) if raw else None


def _last_charge_attrs(data: VigieData) -> dict[str, Any] | None:
    c = data.last_charge
    if not c:
        return None
    return {
        "start": c.get("start"),
        "end": c.get("end"),
        "type": c.get("type"),
        "soc_start": c.get("soc_start_percent"),
        "soc_end": c.get("soc_end_percent"),
        "max_power_kw": round(c["max_power_w"] / 1000, 1) if c.get("max_power_w") is not None else None,
    }


def _tyre(key: str, name: str) -> VigieSensorDescription:
    return VigieSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement=UnitOfPressure.BAR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        **_field(name, round_to=2),
    )


SENSORS: tuple[VigieSensorDescription, ...] = (
    VigieSensorDescription(
        key="battery_level",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=_battery_level,
        exists_fn=lambda d: d.has("BatteryLevel") or d.has("Soc"),
    ),
    VigieSensorDescription(
        key="energy_remaining",
        translation_key="energy_remaining",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        **_field("EnergyRemaining", round_to=2),
    ),
    VigieSensorDescription(
        key="range",
        translation_key="range",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        **_field("RatedRange", round_to=1),
    ),
    VigieSensorDescription(
        key="estimated_range",
        translation_key="estimated_range",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        **_field("EstBatteryRange", round_to=1),
    ),
    VigieSensorDescription(
        key="battery_health",
        translation_key="battery_health",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        attrs_fn=lambda d: {
            "reference_capacity_kwh": (d.battery or {}).get("reference_capacity_kwh"),
            "tracking_start_day": (d.battery or {}).get("tracking_start_day"),
            "chemistry": ((d.battery or {}).get("pack") or {}).get("chemistry"),
        },
        **_battery("soh_percent"),
    ),
    VigieSensorDescription(
        key="battery_capacity",
        translation_key="battery_capacity",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        **_battery("capacity_kwh"),
    ),
    VigieSensorDescription(
        key="battery_cycles",
        translation_key="battery_cycles",
        state_class=SensorStateClass.TOTAL_INCREASING,
        **_battery("cycles"),
    ),
    VigieSensorDescription(
        key="cell_gap",
        translation_key="cell_gap",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.MILLIVOLT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=_cell_gap,
        exists_fn=lambda d: (
            (d.has("BrickVoltageMax") and d.has("BrickVoltageMin")) or (d.battery or {}).get("cell_gap_max_mv") is not None
        ),
        attrs_fn=lambda d: {
            "average_gap_mv": (d.battery or {}).get("cell_gap_avg_mv"),
            "balance": (d.battery or {}).get("balance"),
        },
    ),
    VigieSensorDescription(
        key="battery_temp_min",
        translation_key="battery_temp_min",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        **_field("ModuleTempMin", round_to=1),
    ),
    VigieSensorDescription(
        key="battery_temp_max",
        translation_key="battery_temp_max",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        **_field("ModuleTempMax", round_to=1),
    ),
    VigieSensorDescription(
        key="pack_voltage",
        translation_key="pack_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        live=True,
        **_field("PackVoltage", round_to=2),
    ),
    VigieSensorDescription(
        key="pack_current",
        translation_key="pack_current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        live=True,
        **_field("PackCurrent", round_to=2),
    ),
    VigieSensorDescription(
        key="pack_power",
        translation_key="pack_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        live=True,
        value_fn=_pack_power,
        exists_fn=lambda d: d.has("PackVoltage") and d.has("PackCurrent"),
    ),
    VigieSensorDescription(
        key="charging_power",
        translation_key="charging_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        live=True,
        value_fn=_charging_power,
        exists_fn=lambda d: d.has("ACChargingPower") or d.has("DCChargingPower"),
    ),
    VigieSensorDescription(
        key="charge_energy_added",
        translation_key="charge_energy_added",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value_fn=_session_energy,
        exists_fn=lambda d: d.has("ACChargingEnergyIn") or d.has("DCChargingEnergyIn"),
    ),
    VigieSensorDescription(
        key="last_charge_energy",
        translation_key="last_charge_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value_fn=lambda d: (d.last_charge or {}).get("energy_added_kwh"),
        exists_fn=lambda d: d.last_charge is not None,
        attrs_fn=_last_charge_attrs,
    ),
    VigieSensorDescription(
        key="energy_charged_total",
        translation_key="energy_charged_total",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
        **_field("LifetimeEnergyChargedKwh", round_to=3),
    ),
    VigieSensorDescription(
        key="energy_used_total",
        translation_key="energy_used_total",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        **_field("LifetimeEnergyUsed", round_to=3),
    ),
    VigieSensorDescription(
        key="charge_state",
        translation_key="charge_state",
        device_class=SensorDeviceClass.ENUM,
        options=CHARGE_STATES,
        value_fn=charge_state,
        exists_fn=lambda d: d.has("DetailedChargeState"),
    ),
    VigieSensorDescription(
        key="charge_limit",
        translation_key="charge_limit",
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        replaced_by_ability=ABILITY_CHARGE,
        **_field("ChargeLimitSoc", round_to=0),
    ),
    VigieSensorDescription(
        key="charge_current",
        translation_key="charge_current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=0,
        replaced_by_ability=ABILITY_CHARGE,
        **_field("ChargeAmps", round_to=0),
    ),
    VigieSensorDescription(
        key="odometer",
        translation_key="odometer",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=0,
        **_field("Odometer", round_to=1),
    ),
    VigieSensorDescription(
        key="inside_temperature",
        translation_key="inside_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        **_field("InsideTemp", round_to=1),
    ),
    VigieSensorDescription(
        key="outside_temperature",
        translation_key="outside_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        **_field("OutsideTemp", round_to=1),
    ),
    _tyre("tyre_pressure_front_left", "TpmsPressureFl"),
    _tyre("tyre_pressure_front_right", "TpmsPressureFr"),
    _tyre("tyre_pressure_rear_left", "TpmsPressureRl"),
    _tyre("tyre_pressure_rear_right", "TpmsPressureRr"),
    # « Chargé dans » : Tesla's own estimate when fresh (source: tesla), else ioDek's (source: estimation).
    VigieSensorDescription(
        key="charge_time_remaining",
        translation_key="charge_time_remaining",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda d: _session(d).get("time_to_limit_min"),
        exists_fn=lambda d: "time_to_limit_min" in _session(d),
        available_fn=lambda d: _session(d).get("time_to_limit_min") is not None,
        attrs_fn=_eta_attrs,
    ),
    VigieSensorDescription(
        key="charge_end",
        translation_key="charge_end",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: _time(_session(d).get("eta")),
        exists_fn=lambda d: "eta" in _session(d),
        available_fn=lambda d: _session(d).get("eta") is not None,
        attrs_fn=_eta_attrs,
    ),
    # Destination in the car's navigation (Location option).
    VigieSensorDescription(
        key="nav_distance_remaining",
        translation_key="nav_distance_remaining",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        suggested_display_precision=1,
        value_fn=lambda d: _nav(d).get("distance_km"),
        exists_fn=lambda d: "navigation" in d.state and d.options.get("location", False),
        available_fn=lambda d: _nav(d).get("distance_km") is not None,
    ),
    VigieSensorDescription(
        key="nav_arrival",
        translation_key="nav_arrival",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: _time(_nav(d).get("arrival")),
        exists_fn=lambda d: "navigation" in d.state and d.options.get("location", False),
        available_fn=lambda d: _nav(d).get("arrival") is not None,
        attrs_fn=lambda d: {"minutes": _nav(d).get("minutes_to_arrival"), "traffic_delay_min": _nav(d).get("traffic_delay_min")},
    ),
    VigieSensorDescription(
        key="nav_battery_at_arrival",
        translation_key="nav_battery_at_arrival",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: _nav(d).get("battery_at_arrival"),
        exists_fn=lambda d: "navigation" in d.state and d.options.get("location", False),
        available_fn=lambda d: _nav(d).get("battery_at_arrival") is not None,
    ),
    VigieSensorDescription(
        key="last_seen",
        translation_key="last_seen",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_last_seen,
        exists_fn=lambda d: True,
        attrs_fn=lambda d: {"age_s": d.state.get("age_s")},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: VigieConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    runtime = entry.runtime_data
    for coordinator in runtime.coordinators.values():
        descriptions = [d for d in SENSORS if not (d.replaced_by_ability and runtime.can(coordinator, d.replaced_by_ability))]
        add_when_available(
            coordinator,
            descriptions,
            lambda d, data: d.exists_fn(data),
            VigieSensor,
            async_add_entities,
        )


class VigieSensor(VigieEntity, SensorEntity):
    """Vigie sensor."""

    entity_description: VigieSensorDescription

    def __init__(self, coordinator: VigieCoordinator, description: VigieSensorDescription) -> None:
        super().__init__(coordinator, description)
        self._live = description.live

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        fn = self.entity_description.available_fn
        return fn is None or bool(fn(self.data))

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.data)
