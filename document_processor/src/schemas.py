"""Pydantic models for OpenAI Structured Outputs extraction schema."""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class Address(BaseModel):
    """Patient address."""

    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None


class Patient(BaseModel):
    """Patient demographic information."""

    last_name: Optional[str] = None
    first_name: Optional[str] = None
    middle_initial: Optional[str] = None
    date_of_birth: Optional[str] = None
    ssn: Optional[str] = None
    sex: Optional[str] = None
    address: Address = Field(default_factory=Address)
    phone: Optional[str] = None


class InsurancePolicy(BaseModel):
    """A single insurance policy (primary or secondary)."""

    insurance_name: Optional[str] = None
    policy_number: Optional[str] = None


class Insurance(BaseModel):
    """Primary and secondary insurance information."""

    primary: InsurancePolicy = Field(default_factory=InsurancePolicy)
    secondary: InsurancePolicy = Field(default_factory=InsurancePolicy)


class ConflictValue(BaseModel):
    """A conflict value with location and value fields."""

    model_config = ConfigDict(extra="forbid")

    location: str
    value: str


class ConflictEntry(BaseModel):
    """Describes a conflict between two values found on the document."""

    field: str
    value_a: ConflictValue
    value_b: ConflictValue
    resolved: str


class Meta(BaseModel):
    """Extraction metadata: confidence, flags, conflicts."""

    facility_id: Optional[str] = None
    confidence: str
    conflicts: list[ConflictEntry] = []
    missing_required: list[str] = []
    flags: list[str] = []
    raw_payer_note: Optional[str] = None


class Clinical(BaseModel):
    """Clinical information from the document."""

    rendering_facility: Optional[str] = None
    diagnoses: list[str] = []


class ExtractionResult(BaseModel):
    """Top-level extraction result matching the canonical schema.

    The ``_meta`` key in the JSON output is mapped to the ``meta`` attribute
    via a Pydantic alias so the field is not treated as a private attribute.
    Use ``model_dump(by_alias=True)`` to serialise back to ``_meta``.
    """

    model_config = ConfigDict(populate_by_name=True)

    patient: Patient = Field(default_factory=Patient)
    insurance: Insurance = Field(default_factory=Insurance)
    clinical: Clinical = Field(default_factory=Clinical)
    meta: Meta = Field(alias="_meta")


class ClassificationOutput(BaseModel):
    """Structured output for facility classification."""

    facility_name: Optional[str] = Field(
        None,
        description="The facility name exactly as it appears on the document. Null if not found."
    )
    location_in_document: str = Field(
        description="Where you found the name: 'header' | 'footer' | 'letterhead' | 'label' | 'not_found'"
    )
    confidence: str = Field(
        description="HIGH if name is clearly visible, MEDIUM if partially visible or inferred, LOW if guessed or not found"
    )
