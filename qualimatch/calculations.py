from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ServiceCalculation:
    area_m2: float
    volume_m3: float
    milled_m3km: float
    paint_value: float
    cbuq_value: float
    milling_value: float
    transport_value: float
    total: float


def calculate_service(
    extension_m: float,
    width_m: float,
    thickness_m: float,
    dmt_km: float,
    pu_paint: float,
    pu_cbuq: float,
    pu_milling: float,
    pu_transport: float,
    paint_area_m2: float | None = None,
    milled_volume_m3: float | None = None,
) -> ServiceCalculation:
    area = extension_m * width_m
    volume = area * thickness_m
    paint_area = area if paint_area_m2 is None else paint_area_m2
    milled = volume if milled_volume_m3 is None else milled_volume_m3
    m3km = milled * dmt_km
    vp = paint_area * pu_paint
    vc = volume * pu_cbuq
    vf = milled * pu_milling
    vt = m3km * pu_transport
    return ServiceCalculation(area, volume, m3km, vp, vc, vf, vt, vp + vc + vf + vt)
