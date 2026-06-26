"""Pydantic data model for a door-access controller (the only searched category)."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Category(str, Enum):
    controller = "controller"


class RebrandPath(str, Enum):
    oem_program = "oem_program"
    recase_diy = "recase_diy"
    resell_as_is = "resell_as_is"
    none = "none"


class ApiType(str, Enum):
    native_mqtt = "native_mqtt"
    rest_http = "rest_http"
    vendor_cloud_only = "vendor_cloud_only"
    unknown = "unknown"


class Programmability(str, Enum):
    config_only = "config_only"
    rules_engine = "rules_engine"
    sdk_required = "sdk_required"
    unknown = "unknown"


class ReaderSupport(BaseModel):
    wiegand: bool = False
    osdp: bool = False
    rs485: bool = False
    rs232: bool = False
    native_reader: bool = False
    notes: str | None = None


class LockSupport(BaseModel):
    relay_count: int | None = None
    relay_rating: str | None = None
    dry_contact: bool | None = None
    notes: str | None = None


class OEMProgram(BaseModel):
    offered: bool | None = None
    logo_on_device: bool | None = None
    custom_firmware: bool | None = None
    moq: int | None = None
    holds_ce: str | None = None  # "vendor" | "buyer" | None
    notes: str | None = None


class Certification(BaseModel):
    ce: bool | None = None
    red: bool | None = None
    en60839: bool | None = None
    rohs: bool | None = None
    doc_available: bool | None = None
    notes: str | None = None


class Controller(BaseModel):
    vendor: str
    model: str
    sku: str | None = None
    category: Category = Category.controller
    country_of_origin: str | None = None

    # connectivity
    cellular: bool | None = None
    cellular_tech: str | None = None
    wifi: bool = False
    bluetooth: bool = False
    ethernet: bool = False

    # control
    api_type: ApiType = ApiType.unknown
    protocols: list[str] = Field(default_factory=list)
    programmability: Programmability = Programmability.unknown
    own_broker: bool | None = None

    # I/O
    reader: ReaderSupport = Field(default_factory=ReaderSupport)
    lock: LockSupport = Field(default_factory=LockSupport)
    digital_inputs: int | None = None

    # physical
    ip_rating: str | None = None
    outdoor: bool | None = None
    power: str | None = None
    backup_battery: bool | None = None

    # commercial
    price_eur: float | None = None
    moq: int | None = None
    buy_links: list[str] = Field(default_factory=list)

    # rebrand / certification
    rebrand_path: RebrandPath = RebrandPath.none
    oem: OEMProgram = Field(default_factory=OEMProgram)
    cert: Certification = Field(default_factory=Certification)

    # provenance
    sources: list[str] = Field(default_factory=list)
    notes: str | None = None

    @property
    def key(self) -> str:
        return f"{self.vendor.strip().lower()}::{self.model.strip().lower()}"
