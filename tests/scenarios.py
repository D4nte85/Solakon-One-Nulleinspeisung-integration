"""Szenarien für die Charakterisierungstests.

Jedes Szenario ist ein JSON-fähiges Dict, erzeugt aus einem festen Seed. `run(spec)`
baut die Umgebung, führt die Schritte aus und liefert das Protokoll. Die Referenz
liegt in golden/<art>.jsonl.gz; `python tests/regen.py` schreibt sie neu.
"""
from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone

from tests import harness as h
from tests.ha_stubs import ActiveConnection, _DtState

C = h.const

COUNTS = {"cycle": 1500, "multi": 400, "stall": 120, "tariff": 160, "settings": 200, "wiring": 1, "derive": 1, "domain": 60}


# ── Bausteine ────────────────────────────────────────────────────────────────

def _pick(rng, options):
    return options[rng.randrange(len(options))]


def _chance(rng, p):
    return rng.random() < p


POWER_UNITS = ["W", "W", "W", "kW", None]


def _sensor(rng, value, units, p_unavailable=0.04):
    if _chance(rng, p_unavailable):
        return {"state": _pick(rng, ["unavailable", "unknown", None, "abc"])}
    unit = _pick(rng, units)
    if unit == "kW":
        value = round(value / 1000.0, 3)
    attrs = {} if unit is None else {"unit_of_measurement": unit}
    return {"state": value, "attrs": attrs}


def gen_settings(rng) -> dict:
    s: dict = {}
    s[C.S_REGULATION_ENABLED] = _chance(rng, 0.92)
    if _chance(rng, 0.06):  # ungültige Zonengrenzen
        s[C.S_ZONE1_LIMIT], s[C.S_ZONE3_LIMIT] = _pick(rng, [(20, 20), (20, 50)])
    else:
        s[C.S_ZONE1_LIMIT], s[C.S_ZONE3_LIMIT] = _pick(rng, [(50, 20), (50, 20), (60, 15), (40, 30)])
    s[C.S_HARD_LIMIT_Z0] = _pick(rng, [800, 600, 1200, 400])
    s[C.S_HARD_LIMIT_Z1] = _pick(rng, [800, 500, 1200, 300])
    s[C.S_TOLERANCE] = _pick(rng, [15, 5, 30])
    s[C.S_P_FACTOR] = _pick(rng, [1.3, 0.8, 2.0])
    s[C.S_I_FACTOR] = _pick(rng, [0.05, 0.0, 0.2])
    s[C.S_OFFSET_1] = _pick(rng, [30, 0, -20])
    s[C.S_OFFSET_2] = _pick(rng, [10, 50])
    s[C.S_PV_RESERVE] = _pick(rng, [50, 0, 200])
    s[C.S_DISCHARGE_MAX] = _pick(rng, [40, 25])
    s[C.S_WAIT_TIME] = _pick(rng, [3, 1, 5])
    s[C.S_SELF_ADJUST] = _chance(rng, 0.35)
    s[C.S_SELF_ADJUST_TOL] = _pick(rng, [2, 10])
    s[C.S_STDDEV_TRIM_COUNT] = _pick(rng, [0, 0, 1])
    s[C.S_NIGHT_ENABLED] = _chance(rng, 0.4)
    s[C.S_PERIODIC_ENABLED] = _chance(rng, 0.2)

    s[C.S_SURPLUS_ENABLED] = _chance(rng, 0.5)
    s[C.S_SURPLUS_SOC_THRESHOLD] = _pick(rng, [95, 95, 90, 90, 85, 45])
    s[C.S_SURPLUS_SOC_HYST] = _pick(rng, [5, 2])
    s[C.S_SURPLUS_PV_HYST] = _pick(rng, [50, 0])
    s[C.S_SURPLUS_FORECAST_ENABLED] = _chance(rng, 0.25)
    s[C.S_SURPLUS_FORECAST_THRESHOLD] = _pick(rng, [15.0, 5.0])
    s[C.S_SURPLUS_LOCK_ENABLED] = _chance(rng, 0.2)
    s[C.S_SURPLUS_LOCK_FACTOR] = _pick(rng, [1.5, 1.0])

    s[C.S_AC_ENABLED] = _chance(rng, 0.45)
    s[C.S_AC_SOC_TARGET] = _pick(rng, [90, 60])
    s[C.S_AC_POWER_LIMIT] = _pick(rng, [800, 1500, 300])
    s[C.S_AC_HYSTERESIS] = _pick(rng, [50, 10])
    s[C.S_AC_OFFSET] = _pick(rng, [-50, 0])
    s[C.S_AC_I_FACTOR] = _pick(rng, [0.0, 0.1])

    s[C.S_TARIFF_ENABLED] = _chance(rng, 0.4)
    s[C.S_TARIFF_CHEAP_THRESHOLD] = _pick(rng, [10.0, 20.0, 0.1])
    s[C.S_TARIFF_EXP_THRESHOLD] = _pick(rng, [25.0, 30.0])
    s[C.S_TARIFF_SOC_TARGET] = _pick(rng, [90, 50])
    s[C.S_TARIFF_POWER] = _pick(rng, [800, 400, 1500])
    s[C.S_PV_FORECAST_ENABLED] = _chance(rng, 0.25)
    s[C.S_PV_FORECAST_THRESHOLD] = _pick(rng, [15.0, 3.0])
    s[C.S_ZONE1_FORCE_ENABLED] = _chance(rng, 0.25)
    s[C.S_ZONE1_FORCE_THRESHOLD] = _pick(rng, [15.0, 2.0])
    s[C.S_ZONE1_FORCE_MIN_SOC] = _pick(rng, [35, 35, 35, 25, 45, 10])

    for z in ("Z1", "Z2", "AC"):
        s[getattr(C, f"S_DYN_{z}_ENABLED")] = _chance(rng, 0.25)
        s[getattr(C, f"S_DYN_{z}_NEGATIVE")] = _chance(rng, 0.2)
        s[getattr(C, f"S_DYN_{z}_MIN")] = _pick(rng, [30, 0, 100])
        s[getattr(C, f"S_DYN_{z}_MAX")] = _pick(rng, [250, 20, 400])

    # Sensorzuordnung lokal, global oder gar nicht
    for key, local in (
        ("pv_today", C.S_PV_FORECAST_SENSOR),
        ("z1_tomorrow", C.S_ZONE1_FORCE_SENSOR),
        ("lock", C.S_SURPLUS_LOCK_SENSOR),
        ("price", C.S_TARIFF_PRICE_SENSOR),
        ("cheap", C.S_TARIFF_CHEAP_ENTITY),
        ("exp", C.S_TARIFF_EXP_ENTITY),
    ):
        s[local] = f"sensor.local_{key}" if _chance(rng, 0.45) else ""
    return s


def gen_dist(rng) -> dict:
    d = {
        "distribution_mode": _pick(rng, ["equal", "soc", "capacity", "soc_switch"]),
        "global_max_power": _pick(rng, [800, 1600, 500]),
        "soc_switch_divergence": _pick(rng, [5, 10]),
    }
    for key in ("pv_forecast_today_sensor", "pv_forecast_tomorrow_sensor", "surplus_lock_sensor",
                "tariff_price_sensor", "tariff_cheap_entity", "tariff_exp_entity"):
        short = {"pv_forecast_today_sensor": "pv_today", "pv_forecast_tomorrow_sensor": "z1_tomorrow",
                 "surplus_lock_sensor": "lock", "tariff_price_sensor": "price",
                 "tariff_cheap_entity": "cheap", "tariff_exp_entity": "exp"}[key]
        d[f"global_{key}"] = f"sensor.global_{short}" if _chance(rng, 0.5) else ""
    for prefix in "abc":
        if _chance(rng, 0.85):
            d[f"inst_entry_{prefix}_capacity_sensor"] = f"sensor.{prefix}_capacity"
    return d


def gen_shared_sensors(rng) -> dict:
    kwh_units = ["kWh", "kWh", "Wh", "MWh", "wh", None]
    states = {}
    for scope in ("local", "global"):
        states[f"sensor.{scope}_pv_today"] = _sensor(rng, _pick(rng, [2.0, 20.0, 18000.0, 0.02]), kwh_units)
        states[f"sensor.{scope}_z1_tomorrow"] = _sensor(rng, _pick(rng, [1.0, 16.0, 30000.0]), kwh_units)
        states[f"sensor.{scope}_lock"] = _sensor(rng, _pick(rng, [500.0, 1500.0, 2.0]), ["W", "kW", "kWh", None])
        price = _pick(rng, [5.0, 12.0, 26.0, 0.2, 0.35, -1.0, "on"])
        states[f"sensor.{scope}_price"] = _sensor(
            rng, price, ["ct/kWh", "EUR/kWh", "€/kWh", None, "Cent"], 0.06)
        states[f"sensor.{scope}_cheap"] = _sensor(rng, _pick(rng, [8.0, 15.0, "on"]), [None, "ct"], 0.1)
        states[f"sensor.{scope}_exp"] = _sensor(rng, _pick(rng, [20.0, 28.0]), [None], 0.1)
    return states


def gen_instance(rng, prefix, grid_sensor="sensor.grid") -> dict:
    soc = _pick(rng, [5, 15, 19, 20, 21, 30, 35, 45, 49, 50, 51, 59, 60, 85, 88, 90, 93, 95, 100])
    mode = _pick(rng, ["0", "0", "1", "1", "1", "3", "3"] * 4 + ["2", None])
    power = _pick(rng, [0, 0, 150, 400, 800, 1200, 797, 403, 1202])
    actual = _pick(rng, [0, power, power, -power, power + 90, 3])
    states = {
        f"sensor.{prefix}_soc": _sensor(rng, soc, ["%"], 0.03),
        f"sensor.{prefix}_solar": _sensor(rng, _pick(rng, [0, 0, 30, 300, 900, 1500]), POWER_UNITS),
        f"sensor.{prefix}_actual": _sensor(rng, actual, POWER_UNITS, 0.03),
        f"sensor.{prefix}_countdown": _sensor(rng, _pick(rng, [3000, 100, 50]), ["s"], 0.05),
        f"number.{prefix}_power": {"state": power, "attrs": {}},
        f"number.{prefix}_discharge": {"state": _pick(rng, [40, 0, 2, 25, 39.2, 1.2, 0.4]), "attrs": {}},
        f"number.{prefix}_timeout": {"state": _pick(rng, [3599, 3598]), "attrs": {}},
        f"select.{prefix}_mode": {"state": mode} if mode else {"state": None},
        f"number.{prefix}_export": {"state": _pick(rng, [800, 1200, 0, 799.6, 1199]), "attrs": {}},
        f"sensor.{prefix}_capacity": _sensor(rng, _pick(rng, [2.0, 4000.0, 1.5]),
                                             ["kWh", "Wh", "wh", "MWh", None], 0.1),
    }
    return {
        "prefix": prefix,
        "grid_sensor": grid_sensor,
        "export_limit": _chance(rng, 0.8),
        "settings": gen_settings(rng),
        "flags": {
            "cycle_active": _chance(rng, 0.45),
            "surplus_active": _chance(rng, 0.2),
            "ac_charge_active": _chance(rng, 0.15),
            "tariff_charge_active": _chance(rng, 0.12),
            "solar_zero_entry_armed": _chance(rng, 0.7),
        },
        "stored": _chance(rng, 0.9),
        "drop_flags": [k for k in ("cycle_active", "surplus_active", "ac_charge_active",
                                   "tariff_charge_active", "solar_zero_entry_armed")
                       if _chance(rng, 0.08)],
        "integral": _pick(rng, [0.0, 50.0, -30.0, 5.0]),
        "prev_actual": _pick(rng, [0.0, 100.0]),
        "follow_actual": _pick(rng, [None, 1, -1, 0]),
        "states": states,
    }


def _perturb(rng, prefix) -> dict:
    """Sensoränderungen zwischen zwei Zyklen."""
    out = {}
    if _chance(rng, 0.7):
        out["sensor.grid"] = _sensor(rng, rng.randint(-900, 900), POWER_UNITS, 0.02)
    if _chance(rng, 0.4):
        out[f"sensor.{prefix}_soc"] = _sensor(rng, _pick(rng, [18, 20, 22, 49, 51, 91, 96]), ["%"], 0.02)
    if _chance(rng, 0.4):
        out[f"sensor.{prefix}_solar"] = _sensor(rng, _pick(rng, [0, 40, 700, 1400]), POWER_UNITS, 0.02)
    if _chance(rng, 0.2):
        out["sensor.local_price"] = _sensor(rng, _pick(rng, [5.0, 12.0, 26.0]), ["ct/kWh"], 0.0)
    return out


def gen_cycle(rng, n_instances=1) -> dict:
    instances = [gen_instance(rng, "a")]
    for idx in range(1, n_instances):
        grid = "sensor.grid" if _chance(rng, 0.85) else "sensor.grid_other"
        instances.append(gen_instance(rng, "bcdef"[idx - 1], grid))
    steps = [{"advance": _pick(rng, [0, 5, 400, 5, 22000]), "set": _perturb(rng, "a") if i else {},
              "who": _pick(rng, ["a", "a", "all"]) if n_instances > 1 else "a"}
             for i in range(_pick(rng, [1, 2, 3]))]
    return {
        "language": _pick(rng, ["de", "en"]),
        "hour": _pick(rng, [3, 14, 23]),
        "grid": _sensor(rng, _pick(rng, [rng.randint(-900, 900), -400, -150, -60, 5, 60, 300]),
                        POWER_UNITS, 0.03),
        "dist": gen_dist(rng),
        "has_dist_config": _chance(rng, 0.85),
        "soc_switch_state": _pick(rng, [None, {"active_id": None, "start_soc": None},
                                        {"active_id": "entry_b", "start_soc": 70.0, "was_zone0": True},
                                        {"active_id": "entry_a", "start_soc": 99.0},
                                        {"active_id": "entry_a", "start_soc": None}]),
        "shared": gen_shared_sensors(rng),
        "instances": instances,
        "steps": steps,
    }


def gen_stall(rng) -> dict:
    spec = gen_cycle(rng, 1)
    inst = spec["instances"][0]
    s = inst["settings"]
    s.update({C.S_REGULATION_ENABLED: True, C.S_SURPLUS_ENABLED: False, C.S_AC_ENABLED: False,
              C.S_TARIFF_ENABLED: False, C.S_NIGHT_ENABLED: False, C.S_PV_FORECAST_ENABLED: False,
              C.S_ZONE1_FORCE_ENABLED: False, C.S_SURPLUS_FORECAST_ENABLED: False})
    inst["flags"] = {"cycle_active": True, "surplus_active": False, "ac_charge_active": False,
                     "tariff_charge_active": False, "solar_zero_entry_armed": True}
    limit = min(s[C.S_HARD_LIMIT_Z1], 1200)
    inst["states"]["sensor.a_soc"] = {"state": 70, "attrs": {}}
    inst["states"]["select.a_mode"] = {"state": "1"}
    inst["states"]["number.a_power"] = {"state": limit, "attrs": {}}
    inst["states"]["sensor.a_actual"] = {"state": _pick(rng, [limit, limit // 2, 0]), "attrs": {"unit_of_measurement": "W"},
                                         "age": _pick(rng, [0, 350, 1000])}
    inst["follow_actual"] = None
    spec["grid"] = {"state": _pick(rng, [200, 500]), "attrs": {"unit_of_measurement": "W"}}
    spec["steps"] = [{"advance": _pick(rng, [0, 310, 100]), "set": {}, "who": "a"} for _ in range(_pick(rng, [2, 3, 4]))]
    return spec


def gen_tariff(rng) -> dict:
    """Tarifpfade gezielt: Preis auf, unter und über den Schwellen, mit und ohne Forecast-Sperre."""
    spec = gen_cycle(rng, 1)
    inst = spec["instances"][0]
    s = inst["settings"]
    cheap, exp = _pick(rng, [(10.0, 25.0), (20.0, 30.0)])
    s.update({C.S_REGULATION_ENABLED: True, C.S_TARIFF_ENABLED: True,
              C.S_TARIFF_CHEAP_THRESHOLD: cheap, C.S_TARIFF_EXP_THRESHOLD: exp,
              C.S_TARIFF_PRICE_SENSOR: "sensor.local_price", C.S_TARIFF_CHEAP_ENTITY: "",
              C.S_TARIFF_EXP_ENTITY: "", C.S_PV_FORECAST_ENABLED: _chance(rng, 0.5),
              C.S_PV_FORECAST_SENSOR: "sensor.local_pv_today", C.S_PV_FORECAST_THRESHOLD: 15.0})
    spec["has_dist_config"] = False
    price = _pick(rng, [cheap - 1.0, cheap, cheap + 1.0, exp, exp + 1.0, "nan"])
    spec["shared"]["sensor.local_price"] = {"state": price, "attrs": {"unit_of_measurement": "ct/kWh"}}
    spec["shared"]["sensor.local_pv_today"] = {"state": _pick(rng, [2.0, 20.0]), "attrs": {"unit_of_measurement": "kWh"}}
    inst["flags"]["tariff_charge_active"] = _chance(rng, 0.5)
    inst["states"]["sensor.a_soc"] = {"state": _pick(rng, [30, 45, 55, 70, 95]), "attrs": {"unit_of_measurement": "%"}}
    return spec


def gen_domain(rng) -> dict:
    """Tarifschwellen und PV-Vorhersage auf Entitäten mit und ohne Zahlen-Domain."""
    spec = gen_tariff(rng)
    s = spec["instances"][0]["settings"]
    candidates = {
        "sensor.local_cheap": _pick(rng, [8.0, 15.0]),
        "input_number.cheap": _pick(rng, [8.0, 15.0]),
        "number.cheap": 12.0,
        "input_boolean.cheap": _pick(rng, ["on", "off"]),
        "switch.cheap": "on",
        "binary_sensor.cheap": "on",
    }
    for key in (C.S_TARIFF_CHEAP_ENTITY, C.S_TARIFF_EXP_ENTITY):
        eid = _pick(rng, [""] + sorted(candidates))
        s[key] = eid
        if eid:
            spec["shared"][eid] = {"state": candidates[eid], "attrs": {}}
    pv = _pick(rng, ["sensor.local_pv_today", "binary_sensor.pv_today", "input_boolean.pv_today"])
    s[C.S_PV_FORECAST_SENSOR] = pv
    s[C.S_PV_FORECAST_ENABLED] = True
    if pv not in spec["shared"]:
        spec["shared"][pv] = {"state": "on", "attrs": {}}
    return spec


def gen_settings_change(rng) -> dict:
    spec = gen_cycle(rng, 1)
    base = spec["instances"][0]["settings"]
    changes = {}
    for key in rng.sample(sorted(base), rng.randint(1, 6)):
        val = base[key]
        if isinstance(val, bool):
            changes[key] = not val
        elif isinstance(val, str):
            changes[key] = "" if val else "sensor.changed"
        else:
            changes[key] = val
    if _chance(rng, 0.3):
        changes[C.S_REGULATION_ENABLED] = False
    if _chance(rng, 0.2):
        changes[C.S_PERIODIC_INTERVAL] = _pick(rng, [3, 30])
    spec["changes"] = changes
    spec["dist_save"] = _chance(rng, 0.3)
    return spec


def generate(kind: str) -> list[dict]:
    rng = random.Random(f"solakon-{kind}")
    out = []
    for idx in range(COUNTS[kind]):
        if kind == "cycle":
            spec = gen_cycle(rng, 1)
        elif kind == "multi":
            spec = gen_cycle(rng, _pick(rng, [2, 2, 3]))
        elif kind == "stall":
            spec = gen_stall(rng)
        elif kind == "tariff":
            spec = gen_tariff(rng)
        elif kind == "settings":
            spec = gen_settings_change(rng)
        elif kind == "domain":
            spec = gen_domain(rng)
        else:
            spec = {}
        spec["id"] = f"{kind}-{idx:04d}"
        out.append(spec)
    return out


# ── Ausführung ───────────────────────────────────────────────────────────────

def _apply_states(hass, states: dict) -> None:
    for eid, st in states.items():
        age = st.get("age", 0)
        hass.states.set(eid, st.get("state"), st.get("attrs"), last_updated=h.CLOCK.now - age)


def _setup_env(spec):
    h.CLOCK.now = h.Clock.START
    _DtState.now = datetime(2026, 9, 13, spec["hour"], 0, tzinfo=timezone.utc)
    hass = h.FakeHass(spec["language"])
    logs = h.capture_logs()
    if spec["has_dist_config"]:
        hass.data[f"{C.DOMAIN}_dist_config"] = {"sensor.grid": spec["dist"]}
    if spec["soc_switch_state"] is not None:
        hass.data[f"{C.DOMAIN}_soc_switch_state"] = dict(spec["soc_switch_state"])
        hass.data[f"{C.DOMAIN}_soc_switch_store"] = h.ha_stubs.Store(hass, 1, "soc_switch")
    _apply_states(hass, {"sensor.grid": spec["grid"], "sensor.grid_other": spec["grid"]})
    _apply_states(hass, spec["shared"])
    coords = {}
    for inst in spec["instances"]:
        _apply_states(hass, inst["states"])
        entry = h.FakeEntry(f"entry_{inst['prefix']}",
                            h.entry_data(inst["prefix"], inst["grid_sensor"], inst["export_limit"]))
        if inst["follow_actual"] is not None:
            hass.followers[entry.data[C.CONF_ACTIVE_POWER]] = [
                (entry.data[C.CONF_ACTUAL_SENSOR], inst["follow_actual"])]
        if inst["stored"]:
            flags = {k: v for k, v in inst["flags"].items() if k not in inst.get("drop_flags", ())}
            hass.storage[f"{C.DOMAIN}_{entry.entry_id}"] = {**inst["settings"], **flags}
        coord = h.coordinator_mod.SolakonCoordinator(hass, entry)
        hass.data.setdefault(C.DOMAIN, {})[entry.entry_id] = coord
        coords[inst["prefix"]] = coord
    return hass, logs, coords


async def _run_cycle_spec(spec) -> dict:
    hass, logs, coords = _setup_env(spec)
    rec: dict = {"setup": []}
    for inst in spec["instances"]:
        coord = coords[inst["prefix"]]
        await coord.async_setup()
        if not inst["stored"]:
            coord.settings.update(inst["settings"])
        coord.integral = inst["integral"]
        coord._prev_actual = inst["prev_actual"]
    rec["setup"] = hass.events
    rec["steps"] = []
    for step in spec["steps"]:
        h.CLOCK.now += step["advance"]
        hass.events = []
        _apply_states(hass, step["set"])
        notify = {p: 0 for p in coords}
        for p, c in coords.items():
            c._listeners = [lambda p=p: notify.__setitem__(p, notify[p] + 1)]
        targets = list(coords) if step["who"] == "all" else ["a"]
        for p in targets:
            await coords[p]._async_regulate()
        rec["steps"].append({
            "events": hass.events,
            "notify": notify,
            "state": {p: h.coord_state(c) for p, c in coords.items()},
            "soc_switch_state": h.jsonable(hass.data.get(f"{C.DOMAIN}_soc_switch_state")),
        })
    primary = coords["a"]
    rec["ws_status"] = await h.ws_status(hass, primary.entry.entry_id)
    rec["entities"] = [h.entity_state(e) for e in h.build_entities(hass, primary)]
    rec["logs"] = logs.records
    return rec


async def _run_settings_spec(spec) -> dict:
    hass, logs, coords = _setup_env(spec)
    coord = coords["a"]
    await coord.async_setup()
    coord.settings.update(spec["instances"][0]["settings"])
    hass.events = []
    await coord.async_update_settings(dict(spec["changes"]))
    rec = {"events": hass.events, "state": h.coord_state(coord),
           "settings": h.jsonable(coord.settings)}
    if spec["dist_save"]:
        hass.events = []
        hass.data[f"{C.DOMAIN}_dist_store"] = h.ha_stubs.Store(hass, 2, "dist")
        conn = ActiveConnection()
        await h.integration._ws_save_distribution_config(
            hass, conn, {"id": 7, "grid_sensor": "sensor.grid", "distribution": spec["dist"]})
        rec["dist_save"] = {"events": hass.events, "sent": h.jsonable(conn.sent)}
    hass.events = []
    await coord.async_shutdown()
    await coord.async_shutdown()
    rec["shutdown"] = hass.events
    rec["logs"] = logs.records
    return rec


async def _run_wiring() -> dict:
    """Setup/Unload der Integration, WebSocket-Handler, Config-Flow, Migrationen."""
    rec: dict = {}
    h.CLOCK.now = h.Clock.START
    hass = h.FakeHass("de")
    logs = h.capture_logs()
    mod = h.integration
    entries = [h.FakeEntry("entry_a", h.entry_data("a")), h.FakeEntry("entry_b", h.entry_data("b"))]
    hass.config_entries.entries = entries
    hass.storage["solakon_nulleinspeisung_distribution"] = {"sensor.grid": {"distribution_mode": "soc"}}
    hass.storage["solakon_nulleinspeisung_soc_switch_state"] = {"active_id": "entry_b", "start_soc": 55}
    await mod.async_setup(hass, {})
    for e in entries:
        await mod.async_setup_entry(hass, e)
    rec["setup"] = hass.events
    rec["data_keys"] = sorted(k for k in hass.data)
    rec["dist_config"] = h.jsonable(hass.data.get(f"{C.DOMAIN}_dist_config"))
    rec["soc_switch_state"] = h.jsonable(hass.data.get(f"{C.DOMAIN}_soc_switch_state"))
    rec["entities_static"] = [h.entity_state(e, static=True)
                              for e in h.build_entities(hass, hass.data[C.DOMAIN]["entry_a"])]

    handlers = {
        "get_all_instances": (mod._ws_get_all_instances, {}),
        "get_config": (mod._ws_get_config, {"entry_id": "entry_a"}),
        "get_config_missing": (mod._ws_get_config, {"entry_id": "nope"}),
        "save_config": (mod._ws_save_config, {"entry_id": "entry_a", "changes": {"offset_1": 44}}),
        "save_config_missing": (mod._ws_save_config, {"entry_id": "nope", "changes": {}}),
        "get_status": (mod._ws_get_status, {"entry_id": "entry_b"}),
        "get_status_missing": (mod._ws_get_status, {"entry_id": "nope"}),
        "reset_integral": (mod._ws_reset_integral, {"entry_id": "entry_a"}),
        "reset_integral_missing": (mod._ws_reset_integral, {"entry_id": "nope"}),
        "set_cycle": (mod._ws_set_cycle, {"entry_id": "entry_a", "active": True}),
        "set_cycle_missing": (mod._ws_set_cycle, {"entry_id": "nope", "active": False}),
        "get_dist": (mod._ws_get_distribution_config, {"grid_sensor": "sensor.grid"}),
        "save_dist": (mod._ws_save_distribution_config,
                      {"grid_sensor": "sensor.grid", "distribution": {"distribution_mode": "equal"}}),
    }
    ws = {}
    for name, (handler, extra) in handlers.items():
        hass.events = []
        conn = ActiveConnection()
        for c in hass.data.get(C.DOMAIN, {}).values():
            c.integral = 12.5
        await handler(hass, conn, {"id": 3, **extra})
        ws[name] = {"sent": h.jsonable(conn.sent), "events": hass.events,
                    "schema": sorted(str(k) for k in getattr(handler, "ws_schema", {})),
                    "admin": bool(getattr(handler, "ws_require_admin", False)),
                    "coords": {e: h.coord_state(c) for e, c in hass.data.get(C.DOMAIN, {}).items()}}
    for name in ("get_dist", "save_dist"):
        handler, extra = handlers[name]
        store = hass.data.pop(f"{C.DOMAIN}_dist_store")
        conn = ActiveConnection()
        await handler(hass, conn, {"id": 4, **extra})
        ws[name + "_no_store"] = h.jsonable(conn.sent)
        hass.data[f"{C.DOMAIN}_dist_store"] = store
    rec["ws"] = ws

    hass.events = []
    for e in entries:
        await mod.async_unload_entry(hass, e)
        rec.setdefault("unload_keys", []).append(sorted(hass.data))
    rec["unload"] = hass.events
    hass.events = []
    hass.config_entries.entries = []
    await mod.async_remove_entry(hass, entries[0])
    rec["remove"] = hass.events

    # Migrationen
    mig = {}
    dist_store = mod.SolakonDistStore(hass, 2, "x")
    hass.config_entries.entries = entries
    for name, data in {
        "flat": {"distribution_mode": "weighted", "capacity_weighting": False, "global_max_power": 900},
        "flat_cap": {"distribution_mode": "equal", "capacity_weighting": True},
        "nested": {"sensor.grid": {"capacity_weighting": True}, "sensor.x": {"distribution_mode": "weighted"}},
        "empty": {},
    }.items():
        mig["dist_" + name] = h.jsonable(await dist_store._async_migrate_func(1, 0, dict(data)))
    settings_store = h.coordinator_mod.SolakonSettingsStore(hass, 2, "y")
    mig["settings_v1"] = h.jsonable(await settings_store._async_migrate_func(
        1, 0, {"hard_limit": 650, "surplus_forecast_sensor": "sensor.f"}))
    mig["settings_v1_keep"] = h.jsonable(await settings_store._async_migrate_func(
        1, 0, {"hard_limit_z0": 700, "surplus_forecast_sensor": "sensor.f", "pv_forecast_sensor": "sensor.p"}))
    rec["migrations"] = mig

    # Config-Flow
    cf = h.config_flow_mod
    flows = {}
    for lang in ("de", "en", None):
        fh = h.FakeHass(lang or "")
        fh.config.language = lang
        fh.config_entries.entries = [h.FakeEntry("entry_a", h.entry_data("a")),
                                     h.FakeEntry("entry_b", h.entry_data("b"))]
        flow = cf.SolakonConfigFlow()
        flow.hass = fh
        form = await flow.async_step_user(None)
        flows[f"user_form_{lang}"] = _schema_repr(form)
        flows[f"user_dup_{lang}"] = h.jsonable(await flow.async_step_user({"mode_select": "select.a_mode"}))
        flows[f"user_new_{lang}"] = h.jsonable(await flow.async_step_user(
            {"mode_select": "select.z_mode", "instance_name": "Neu"}))
        flows[f"user_new_noname_{lang}"] = h.jsonable(await flow.async_step_user({"mode_select": "select.z"}))
        opt = cf.SolakonConfigFlow.async_get_options_flow(fh.config_entries.entries[0])
        opt.hass = fh
        opt.config_entry = fh.config_entries.entries[0]
        flows[f"init_form_{lang}"] = _schema_repr(await opt.async_step_init(None))
        flows[f"init_same_{lang}"] = h.jsonable(await opt.async_step_init({"mode_select": "select.a_mode"}))
        flows[f"init_dup_{lang}"] = h.jsonable(await opt.async_step_init({"mode_select": "select.b_mode"}))
        flows[f"init_events_{lang}"] = fh.events
    partial = h.entry_data("q")
    del partial[C.CONF_EXPORT_LIMIT]
    flows["schema_partial"] = _schema_repr({"data_schema": cf._schema(partial, C.REQUIRED_ENTITY_DEFAULTS_DE)})
    rec["config_flow"] = flows
    rec["logs"] = logs.records
    return rec


async def _run_derive() -> dict:
    """Erschöpfende Ableitungen aus den Zustandsflags und ein PI-Raster."""
    import itertools
    h.CLOCK.now = h.Clock.START
    hass = h.FakeHass("en")
    entry = h.FakeEntry("entry_a", h.entry_data("a"))
    coord = h.coordinator_mod.SolakonCoordinator(hass, entry)
    hass.data[C.DOMAIN] = {"entry_a": coord}
    flags = ("surplus_active", "tariff_charge_active", "ac_charge_active", "cycle_active",
             "discharge_locked", "is_night", "_cycle_blocked")
    rows = []
    for combo in itertools.product((False, True), repeat=len(flags)):
        for regulation in (False, True):
            for soc in (19, 20, 21, 60):
                for mode in ("0", "1", "3", "x"):
                    for name, val in zip(flags, combo):
                        setattr(coord, name, val)
                    coord.settings[C.S_REGULATION_ENABLED] = regulation
                    coord.operating_state = ""
                    coord.mode_key = "waiting"
                    coord._update_zone_display(soc, 50, 20, mode)
                    rows.append([int("".join("1" if v else "0" for v in combo), 2), regulation, soc, mode,
                                 coord.operating_state, coord.current_zone, coord.zone_label,
                                 coord.mode_key, coord.mode_label, coord._required_discharge(40)])
    rng = random.Random("solakon-pi")
    pi = []
    for _ in range(3000):
        args = (rng.choice([-900, -300, -16, 0, 14, 40, 600]), rng.choice([0, 100, 799, 800, 1200, 1300]),
                rng.choice([-50, 0, 30]), rng.choice([0, 300, 800, 1500]), rng.choice([0.3, 1.3]),
                rng.choice([0.0, 0.05, 0.3]))
        ac, share, integ = rng.choice([False, True]), rng.choice([1.0, 0.5, 0.0]), rng.choice([0.0, 400.0, -2000.0])
        coord.integral = integ
        out = coord._pi_calculate(*args, ac_charge_mode=ac, error_share=share)
        pi.append([list(args), ac, share, integ, out, round(coord.integral, 6)])
    dyn = []
    for sd in (-1.0, 0.0, 10.0, 40.0, 500.0):
        for mn, mx in ((30, 250), (250, 30), (0, 0)):
            for noise, factor, neg in ((15, 1.5, False), (0, 2.0, True)):
                dyn.append([sd, mn, mx, noise, factor, neg, coord._calc_dynamic_offset(sd, mn, mx, noise, factor, neg)])
    return {"derive": rows, "pi": pi, "dyn": dyn}


def _schema_repr(form) -> list:
    schema = form.get("data_schema")
    out = []
    for key, sel in schema.schema.items():
        default = key.default() if callable(getattr(key, "default", None)) else None
        out.append([type(key).__name__, str(key), default, repr(sel)])
    return [form.get("type"), form.get("step_id"), form.get("description_placeholders"), out]


def run(kind: str, spec: dict) -> dict:
    if kind in ("cycle", "multi", "stall", "tariff", "domain"):
        coro = _run_cycle_spec(spec)
    elif kind == "settings":
        coro = _run_settings_spec(spec)
    elif kind == "derive":
        coro = _run_derive()
    else:
        coro = _run_wiring()
    return h.jsonable(asyncio.run(coro))
