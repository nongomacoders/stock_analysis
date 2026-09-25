"""Canonical financial-concept dictionary and alias inventory for financial data extraction.

Phase 1: Deterministic dictionary, semantic rules, and provenance preservation.
Analysis-only module; not yet wired into the production parser.
Zero LLM / zero Jev / zero vector embeddings.
"""
from __future__ import annotations

import json
import re
import unicodedata
from enum import Enum
from pathlib import Path
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ConceptCategory(str, Enum):
    INCOME_STATEMENT = "income_statement"
    BALANCE_SHEET = "balance_sheet"
    CASH_FLOW = "cash_flow"
    PER_SHARE = "per_share"
    MARGIN = "margin"
    TAX = "tax"
    SHARES = "shares"
    SEGMENT = "segment"
    VALUATION_INPUT = "valuation_input"


class AliasStatus(str, Enum):
    APPROVED = "APPROVED"
    CANDIDATE = "CANDIDATE"
    REQUIRES_CONTEXT = "REQUIRES_CONTEXT"
    AMBIGUOUS = "AMBIGUOUS"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


class MatchClassification(str, Enum):
    EXACT_EXISTING_ALIAS = "EXACT_EXISTING_ALIAS"
    NORMALIZED_EXISTING_ALIAS = "NORMALIZED_EXISTING_ALIAS"
    POTENTIAL_ALIAS = "POTENTIAL_ALIAS"
    AMBIGUOUS = "AMBIGUOUS"
    UNKNOWN = "UNKNOWN"


# Explicit pairs of financial concepts that must NEVER be treated as equivalent
PROHIBITED_EQUIVALENCE_PAIRS: set[frozenset[str]] = {
    frozenset({"trading_profit", "operating_profit"}),
    frozenset({"revenue", "retail_sales"}),
    frozenset({"sale_of_merchandise", "revenue"}),
    frozenset({"retail_sales", "sale_of_merchandise"}),
    frozenset({"cash_capex", "total_capex"}),
    frozenset({"cash_capex", "capex_expansion"}),
    frozenset({"cash_capex", "capex_maintenance"}),
    frozenset({"weighted_average_basic_shares", "issued_shares_current"}),
    frozenset({"weighted_average_basic_shares", "period_end_external_shares"}),
    frozenset({"weighted_average_diluted_shares", "period_end_external_shares"}),
    frozenset({"weighted_average_diluted_shares", "issued_shares_current"}),
    frozenset({"reported_net_cash", "cash_and_cash_equivalents"}),
    frozenset({"operating_profit", "ebit"}),
    frozenset({"trading_profit", "ebit"}),
    frozenset({"ebitda", "adjusted_ebitda"}),
    frozenset({"ebitda", "normalised_ebitda"}),
    frozenset({"adjusted_ebitda", "normalised_ebitda"}),
    frozenset({"reported_net_debt", "interest_bearing_borrowings"}),
    frozenset({"reported_net_cash", "reported_net_debt"}),
    frozenset({"turnover", "revenue"}),
    frozenset({"operating_profit", "profit_before_finance_costs_and_tax"}),
    frozenset({"depreciation_amortisation_expense", "depreciation_amortisation_cashflow_addback"}),
}


def is_prohibited_equivalence(concept_a: str, concept_b: str) -> bool:
    """Return True if treating concept_a and concept_b as equivalent is strictly prohibited."""
    if not concept_a or not concept_b or concept_a == concept_b:
        return False
    return frozenset({concept_a, concept_b}) in PROHIBITED_EQUIVALENCE_PAIRS


def normalize_label(text: str) -> str:
    """Deterministic label normalization preserving financially meaningful qualifiers.
    
    Rules:
    - Unicode NFKD decomposition
    - Normalize quotes, dashes, non-breaking spaces
    - Normalize '&' to 'and'
    - Strip leading bullets, numbers, dashes, list counters
    - Strip trailing punctuation (colons, semicolons, dots, dashes)
    - Lowercase
    - Collapse repeated whitespace
    - PRESERVES meaningful words: adjusted, normalised, underlying, continuing,
      before, after, cash, reported, trading, operating, diluted, basic, etc.
    """
    if not text:
        return ""
    # Unicode normalize
    t = unicodedata.normalize("NFKD", str(text))
    # Replace non-breaking space and variants
    t = t.replace("\xa0", " ").replace("’", "'").replace("‘", "'").replace("`", "'")
    t = t.replace("“", '"').replace("”", '"').replace("–", "-").replace("—", "-")
    # Replace & with and
    t = re.sub(r"\s*&\s*", " and ", t)
    # Strip leading bullets, numbers, dashes, brackets: e.g. "• ", "1. ", "(a) ", "- "
    t = re.sub(r"^[\s\*\-\•\·\d\.\)\:\;\(\/\[\]\>]+", "", t)
    # Strip trailing punctuation, colons, dashes
    t = re.sub(r"[\s\:\;\,\.\-]+$", "", t)
    # Lowercase
    t = t.lower()
    # Collapse repeated whitespace
    t = re.sub(r"\s+", " ", t)
    return t.strip()


# --- Typed Semantic Qualifiers ---

class OperationScope(str, Enum):
    UNSPECIFIED = "unspecified"
    TOTAL_OPERATIONS = "total_operations"
    CONTINUING_OPERATIONS = "continuing_operations"
    DISCONTINUED_OPERATIONS = "discontinued_operations"
    GROUP_CONSOLIDATED = "group_consolidated"
    SEGMENT = "segment"


class DilutionBasis(str, Enum):
    UNSPECIFIED = "unspecified"
    BASIC = "basic"
    DILUTED = "diluted"


class DividendTaxBasis(str, Enum):
    UNSPECIFIED = "unspecified"
    GROSS = "gross"
    NET = "net"


class CapexBasis(str, Enum):
    UNSPECIFIED = "unspecified"
    CASH_PAYMENTS = "cash_payments"
    ACCOUNTING_ADDITIONS = "accounting_additions"


class LeaseInclusion(str, Enum):
    UNSPECIFIED = "unspecified"
    EX_LEASES = "ex_leases"
    INC_LEASES = "inc_leases"


class ProfitAttribution(str, Enum):
    UNSPECIFIED = "unspecified"
    PARENT_EQUITY_HOLDERS = "parent_equity_holders"
    TOTAL_GROUP = "total_group"
    NON_CONTROLLING_INTEREST = "non_controlling_interest"
    HEADLINE_ATTRIBUTABLE = "headline_attributable"


class NumericSign(str, Enum):
    UNSPECIFIED = "unspecified"
    POSITIVE = "positive"
    NEGATIVE = "negative"


class MetricBasis(str, Enum):
    UNSPECIFIED = "unspecified"
    REPORTED_STATUTORY = "reported_statutory"
    UNDERLYING_ADJUSTED = "underlying_adjusted"
    NORMALISED = "normalised"
    HEADLINE = "headline"


class PeriodType(str, Enum):
    UNSPECIFIED = "unspecified"
    FULL_YEAR = "full_year"
    INTERIM = "interim"
    QUARTERLY = "quarterly"
    TRAILING_12M = "trailing_12m"
    POINT_IN_TIME = "point_in_time"


class MarginDenominator(str, Enum):
    UNSPECIFIED = "unspecified"
    MERCHANDISE_SALES = "merchandise_sales"
    ACCOUNTING_REVENUE = "accounting_revenue"
    TURNOVER = "turnover"


class BasisEvidence(str, Enum):
    UNSPECIFIED = "unspecified"
    BALANCE_SHEET_PRESENTATION_SEPARATE = "balance_sheet_presentation_separate"
    EXPLICIT_NOTE_WORDING = "explicit_note_wording"
    RECONCILED_SOURCE_FORMULA = "reconciled_source_formula"
    DETERMINISTIC_PARSER_SECTION = "deterministic_parser_section"


class SemanticQualifiers(BaseModel):
    """Explicit financial semantic qualifiers attached to an alias observation or canonical concept."""
    model_config = ConfigDict(extra="forbid")

    scope: OperationScope = OperationScope.UNSPECIFIED
    dilution: DilutionBasis = DilutionBasis.UNSPECIFIED
    tax_basis: DividendTaxBasis = DividendTaxBasis.UNSPECIFIED
    capex_basis: CapexBasis = CapexBasis.UNSPECIFIED
    lease_inclusion: LeaseInclusion = LeaseInclusion.UNSPECIFIED
    attribution: ProfitAttribution = ProfitAttribution.UNSPECIFIED
    sign: NumericSign = NumericSign.UNSPECIFIED
    metric_basis: MetricBasis = MetricBasis.UNSPECIFIED
    period_type: PeriodType = PeriodType.UNSPECIFIED
    margin_denominator: MarginDenominator = MarginDenominator.UNSPECIFIED
    basis_evidence: BasisEvidence = BasisEvidence.UNSPECIFIED
    custom_notes: str | None = None


class AliasObservation(BaseModel):
    """Observation and audit provenance of a financial label in the corpus with typed qualifiers."""
    model_config = ConfigDict(extra="forbid")

    raw_label: str
    normalized_label: str
    canonical_concept: str | None = None
    status: AliasStatus = AliasStatus.UNKNOWN
    classification: MatchClassification = MatchClassification.UNKNOWN
    qualifiers: SemanticQualifiers = Field(default_factory=SemanticQualifiers)
    occurrence_count: int = Field(default=0, ge=0)
    ticker_count: int = Field(default=0, ge=0)
    first_seen: str | None = None
    last_seen: str | None = None
    sample_tickers: list[str] = Field(default_factory=list)
    sample_sources: list[str] = Field(default_factory=list)
    sample_contexts: list[str] = Field(default_factory=list)
    disambiguation_note: str | None = None

    @model_validator(mode="after")
    def validate_qualifiers(self) -> AliasObservation:
        norm = self.normalized_label.lower()

        # Rule 1: Gross/net dividend basis must be explicit
        dividend_concepts = {
            "dividend_per_share", "annual_dividend_per_share",
            "interim_dividend_per_share", "final_dividend_per_share"
        }
        if self.canonical_concept in dividend_concepts:
            if "gross" in norm and self.qualifiers.tax_basis != DividendTaxBasis.GROSS:
                raise ValueError(f"Label '{self.raw_label}' indicates gross dividend; tax_basis must be GROSS")
            if "net" in norm and self.qualifiers.tax_basis != DividendTaxBasis.NET:
                raise ValueError(f"Label '{self.raw_label}' indicates net dividend; tax_basis must be NET")
            if self.status == AliasStatus.APPROVED and self.qualifiers.tax_basis == DividendTaxBasis.UNSPECIFIED:
                raise ValueError(
                    f"Dividend label '{self.raw_label}' cannot be APPROVED with unspecified tax_basis; "
                    f"dividend without explicit gross/net evidence must remain REQUIRES_CONTEXT"
                )

        # Rule 2: Continuing-operations scope must be preserved
        if "continuing operations" in norm or "from continuing" in norm:
            if self.qualifiers.scope != OperationScope.CONTINUING_OPERATIONS:
                raise ValueError(f"Label '{self.raw_label}' contains continuing-operations indicator; qualifiers.scope must be CONTINUING_OPERATIONS")

        # Rule 3: Capex basis cannot default to cash_capex
        if self.canonical_concept == "cash_capex":
            if self.qualifiers.capex_basis != CapexBasis.CASH_PAYMENTS:
                raise ValueError(f"Concept 'cash_capex' requires qualifiers.capex_basis=CASH_PAYMENTS")
            if norm in {"capital expenditure", "total capital expenditure", "capex"}:
                raise ValueError(f"Generic capex label '{self.raw_label}' cannot map directly to cash_capex without explicit cash payment evidence")
        if "capital expenditure" in norm or "capex" in norm:
            if self.qualifiers.capex_basis == CapexBasis.CASH_PAYMENTS and not ("cash" in norm or "payment" in norm):
                raise ValueError(f"Capex basis cannot default to CASH_PAYMENTS for label '{self.raw_label}' without explicit cash payment evidence")

        # Rule 4: Debt lease inclusion cannot default without evidence
        if self.canonical_concept in {"interest_bearing_borrowings", "reported_net_debt", "borrowings"}:
            if self.status == AliasStatus.APPROVED:
                if self.qualifiers.lease_inclusion == LeaseInclusion.UNSPECIFIED:
                    raise ValueError(
                        f"Debt concept '{self.canonical_concept}' cannot be APPROVED for label '{self.raw_label}' "
                        f"with unspecified lease_inclusion; debt without explicit lease evidence must remain REQUIRES_CONTEXT"
                    )
                if self.qualifiers.basis_evidence == BasisEvidence.UNSPECIFIED:
                    raise ValueError(
                        f"Debt concept '{self.canonical_concept}' cannot be APPROVED for label '{self.raw_label}' "
                        f"without explicit basis_evidence (must specify BALANCE_SHEET_PRESENTATION_SEPARATE, EXPLICIT_NOTE_WORDING, or RECONCILED_SOURCE_FORMULA)"
                    )
                if self.qualifiers.basis_evidence == BasisEvidence.BALANCE_SHEET_PRESENTATION_SEPARATE:
                    # BALANCE_SHEET_PRESENTATION_SEPARATE must represent empirical evidence from the actual issuer document,
                    # not a theoretical assumption from general IFRS presentation requirements.
                    # It requires the same source document to explicitly present lease liabilities separately from interest-bearing borrowings.
                    doc_evidence = (
                        (self.disambiguation_note or "") + " " +
                        (self.qualifiers.custom_notes or "") + " " +
                        " ".join(self.sample_contexts)
                    )
                    if not re.search(r"(lease\s+liabilit|separate.*lease|leases?\s+separat)", doc_evidence, re.IGNORECASE):
                        raise ValueError(
                            f"Debt concept '{self.canonical_concept}' cannot claim BALANCE_SHEET_PRESENTATION_SEPARATE "
                            f"for label '{self.raw_label}' without evidence that the same source document explicitly "
                            f"presents lease liabilities separately from interest-bearing borrowings. "
                            f"Otherwise, must use lease_inclusion=UNSPECIFIED, basis_evidence=UNSPECIFIED, status=REQUIRES_CONTEXT."
                        )

        # Rule 5: Margin denominator cannot be inferred
        if self.canonical_concept in {"trading_margin", "gross_margin", "operating_margin"}:
            if self.status == AliasStatus.APPROVED and self.qualifiers.margin_denominator == MarginDenominator.UNSPECIFIED:
                raise ValueError(f"Margin concept '{self.canonical_concept}' for approved label '{self.raw_label}' cannot have unspecified margin_denominator")

        return self


class CanonicalConcept(BaseModel):
    """Canonical financial concept with metadata, approved aliases, and boundary rules."""
    model_config = ConfigDict(extra="forbid")

    concept_id: str
    name: str
    description: str
    category: ConceptCategory
    expected_units: list[str]
    allowed_sections: list[str]
    approved_aliases: list[str] = Field(default_factory=list)
    ambiguous_aliases: list[str] = Field(default_factory=list)
    prohibited_equivalences: list[str] = Field(default_factory=list)
    default_qualifiers: SemanticQualifiers = Field(default_factory=SemanticQualifiers)

    @field_validator("concept_id")
    @classmethod
    def validate_id_format(cls, v: str) -> str:
        if not re.match(r"^[a-z][a-z0-9_]*$", v):
            raise ValueError(f"concept_id must be lowercase snake_case: {v}")
        return v

    @model_validator(mode="after")
    def validate_prohibited_consistency(self) -> CanonicalConcept:
        for prohibited in self.prohibited_equivalences:
            if prohibited in self.approved_aliases:
                raise ValueError(
                    f"Concept {self.concept_id} cannot have prohibited concept '{prohibited}' in approved_aliases"
                )
        return self


class FinancialConceptDictionary(BaseModel):
    """Repository of canonical financial concepts and their approved/candidate aliases."""
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0.0"
    concepts: dict[str, CanonicalConcept] = Field(default_factory=dict)
    alias_registry: dict[str, AliasObservation] = Field(default_factory=dict)

    def add_concept(self, concept: CanonicalConcept) -> None:
        """Register a canonical concept with boundary check."""
        self.concepts[concept.concept_id] = concept

    def get_concept(self, concept_id: str) -> CanonicalConcept | None:
        return self.concepts.get(concept_id)

    def register_observation(self, obs: AliasObservation) -> None:
        """Register or update an alias observation with full provenance."""
        norm = obs.normalized_label
        existing = self.alias_registry.get(norm)
        if existing:
            # Merge occurrences and tickers
            merged_tickers = sorted(list(set(existing.sample_tickers + obs.sample_tickers)))[:10]
            merged_sources = sorted(list(set(existing.sample_sources + obs.sample_sources)))[:10]
            # Contexts: preserve up to 5 representative snippets
            existing_contexts = existing.sample_contexts
            for c in obs.sample_contexts:
                if c not in existing_contexts and len(existing_contexts) < 5:
                    existing_contexts.append(c)
            
            first_seen = existing.first_seen or obs.first_seen
            if existing.first_seen and obs.first_seen:
                first_seen = min(existing.first_seen, obs.first_seen)
            last_seen = existing.last_seen or obs.last_seen
            if existing.last_seen and obs.last_seen:
                last_seen = max(existing.last_seen, obs.last_seen)

            self.alias_registry[norm] = existing.model_copy(update={
                "occurrence_count": existing.occurrence_count + obs.occurrence_count,
                "ticker_count": max(existing.ticker_count, obs.ticker_count, len(merged_tickers)),
                "sample_tickers": merged_tickers,
                "sample_sources": merged_sources,
                "sample_contexts": existing_contexts,
                "first_seen": first_seen,
                "last_seen": last_seen,
            })
        else:
            self.alias_registry[norm] = obs

    def lookup_label(self, raw_label: str) -> tuple[CanonicalConcept | None, MatchClassification, str | None]:
        """Look up a raw or normalized label against the dictionary.
        
        Returns:
            (concept, classification, disambiguation_note)
        """
        norm = normalize_label(raw_label)
        if not norm:
            return None, MatchClassification.UNKNOWN, "Empty label"

        # 1. Check exact match in approved aliases
        for concept in self.concepts.values():
            if raw_label in concept.approved_aliases:
                return concept, MatchClassification.EXACT_EXISTING_ALIAS, None

        # 2. Check normalized match in approved aliases
        for concept in self.concepts.values():
            for alias in concept.approved_aliases:
                if normalize_label(alias) == norm:
                    return concept, MatchClassification.NORMALIZED_EXISTING_ALIAS, None

        # 3. Check ambiguous aliases
        for concept in self.concepts.values():
            for amb in concept.ambiguous_aliases:
                if normalize_label(amb) == norm or amb == raw_label:
                    return None, MatchClassification.AMBIGUOUS, f"Ambiguous label matching concept candidate: {concept.concept_id}"

        # 4. Check alias registry
        obs = self.alias_registry.get(norm)
        if obs:
            if obs.status in {AliasStatus.AMBIGUOUS, AliasStatus.REQUIRES_CONTEXT} or obs.classification == MatchClassification.AMBIGUOUS:
                return None, MatchClassification.AMBIGUOUS, obs.disambiguation_note or "Requires contextual statement verification"
            if obs.canonical_concept and obs.canonical_concept in self.concepts:
                target_concept = self.concepts[obs.canonical_concept]
                if obs.status == AliasStatus.APPROVED:
                    return target_concept, MatchClassification.NORMALIZED_EXISTING_ALIAS, None
                elif obs.status == AliasStatus.CANDIDATE:
                    return target_concept, MatchClassification.POTENTIAL_ALIAS, "Candidate alias awaiting formal promotion"

        return None, MatchClassification.UNKNOWN, "No match found"

    def validate_integrity(self) -> list[str]:
        """Validate internal integrity:
        1. Every approved alias must map to exactly ONE canonical concept.
        2. No approved alias may be a prohibited equivalence for its concept.
        3. Ambiguous aliases must not be approved.
        """
        errors = []
        approved_map: dict[str, str] = {}
        for c_id, concept in self.concepts.items():
            for alias in concept.approved_aliases:
                norm_a = normalize_label(alias)
                if norm_a in approved_map:
                    errors.append(
                        f"Duplicate approved alias '{alias}' (norm: '{norm_a}') in '{c_id}' and '{approved_map[norm_a]}'"
                    )
                else:
                    approved_map[norm_a] = c_id

            # Prohibited check
            for prohibited in concept.prohibited_equivalences:
                if prohibited in concept.approved_aliases or normalize_label(prohibited) in [normalize_label(a) for a in concept.approved_aliases]:
                    errors.append(f"Concept '{c_id}' contains prohibited concept '{prohibited}' in its approved aliases")

            # Ambiguous check
            for amb in concept.ambiguous_aliases:
                if amb in concept.approved_aliases:
                    errors.append(f"Concept '{c_id}' contains alias '{amb}' in both approved and ambiguous lists")

        return errors

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_json(cls, json_str: str) -> FinancialConceptDictionary:
        data = json.loads(json_str)
        return cls.model_validate(data)

    def save_to_file(self, path: Path | str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_json(indent=2), encoding="utf-8")

    @classmethod
    def load_from_file(cls, path: Path | str) -> FinancialConceptDictionary:
        p = Path(path)
        return cls.from_json(p.read_text(encoding="utf-8"))


def build_default_canonical_concepts() -> dict[str, CanonicalConcept]:
    """Build the comprehensive baseline inventory of canonical financial concepts.
    
    Populates existing concepts from afs_parser.py, sens_parser.py, financial_metrics.py,
    and valuation engines, preserving separation between distinct concepts.
    """
    concepts: dict[str, CanonicalConcept] = {}

    def _add(c: CanonicalConcept):
        concepts[c.concept_id] = c

    # 1. REVENUE & TURNOVER CONCEPTS
    _add(CanonicalConcept(
        concept_id="accounting_revenue",
        name="Accounting Revenue",
        description="Statutory IFRS revenue from contracts with customers reported on the income statement.",
        category=ConceptCategory.INCOME_STATEMENT,
        expected_units=["ZAR", "USD", "EUR", "GBP"],
        allowed_sections=["income_statement"],
        approved_aliases=[
            "Revenue",
            "Accounting revenue",
            "Group revenue",
            "Total revenue",
            "Revenue from contracts with customers"
        ],
        ambiguous_aliases=["turnover", "sales", "group sales"],
        prohibited_equivalences=["retail_sales", "sale_of_merchandise", "turnover"]
    ))

    _add(CanonicalConcept(
        concept_id="sale_of_merchandise",
        name="Sale of Merchandise",
        description="Revenue derived specifically from the sale of merchandise/goods, excluding finance charges and service fees.",
        category=ConceptCategory.INCOME_STATEMENT,
        expected_units=["ZAR", "USD"],
        allowed_sections=["income_statement", "sens_headline"],
        approved_aliases=[
            "Sale of merchandise",
            "Sales of merchandise"
        ],
        ambiguous_aliases=["merchandise sales", "sales of goods"],
        prohibited_equivalences=["accounting_revenue", "retail_sales"]
    ))

    _add(CanonicalConcept(
        concept_id="retail_sales",
        name="Retail Sales",
        description="Customer-facing retail sales metric, often including concessions and franchise sales.",
        category=ConceptCategory.INCOME_STATEMENT,
        expected_units=["ZAR", "USD"],
        allowed_sections=["sens_headline", "note_segment"],
        approved_aliases=[
            "Retail sales"
        ],
        ambiguous_aliases=["total retail sales", "group retail sales", "sales"],
        prohibited_equivalences=["accounting_revenue", "sale_of_merchandise"]
    ))

    _add(CanonicalConcept(
        concept_id="turnover",
        name="Turnover",
        description="Top-line turnover disclosed in financial announcements, which may include excise duties or concession turnover.",
        category=ConceptCategory.INCOME_STATEMENT,
        expected_units=["ZAR", "USD"],
        allowed_sections=["income_statement", "sens_headline"],
        approved_aliases=[],
        ambiguous_aliases=["Turnover", "group turnover", "total turnover"],
        prohibited_equivalences=["accounting_revenue"]
    ))

    # 2. PROFIT & MARGIN CONCEPTS
    _add(CanonicalConcept(
        concept_id="gross_profit",
        name="Gross Profit",
        description="Revenue less cost of sales.",
        category=ConceptCategory.INCOME_STATEMENT,
        expected_units=["ZAR", "USD"],
        allowed_sections=["income_statement"],
        approved_aliases=["Gross profit"],
        ambiguous_aliases=[],
        prohibited_equivalences=["trading_profit", "operating_profit"]
    ))

    _add(CanonicalConcept(
        concept_id="cost_of_sales",
        name="Cost of Sales",
        description="Direct expenses incurred in the production or acquisition of goods sold.",
        category=ConceptCategory.INCOME_STATEMENT,
        expected_units=["ZAR", "USD"],
        allowed_sections=["income_statement"],
        approved_aliases=["Cost of sales"],
        ambiguous_aliases=[],
        prohibited_equivalences=[]
    ))

    _add(CanonicalConcept(
        concept_id="gross_margin",
        name="Gross Margin",
        description="Gross profit divided by revenue or sale of merchandise, expressed as a percentage.",
        category=ConceptCategory.MARGIN,
        expected_units=["percentage"],
        allowed_sections=["sens_headline", "note_segment"],
        approved_aliases=["Gross profit margin", "Gross margin"],
        ambiguous_aliases=[],
        prohibited_equivalences=["operating_margin", "trading_margin"]
    ))

    _add(CanonicalConcept(
        concept_id="trading_profit",
        name="Trading Profit",
        description="Operating profit before non-trading items, interest, and taxation (retailer-specific trading earnings).",
        category=ConceptCategory.INCOME_STATEMENT,
        expected_units=["ZAR"],
        allowed_sections=["income_statement", "note_segment"],
        approved_aliases=["Trading profit"],
        ambiguous_aliases=[],
        prohibited_equivalences=["operating_profit", "ebit", "profit_before_finance_costs_and_tax"]
    ))

    _add(CanonicalConcept(
        concept_id="trading_margin",
        name="Trading Margin",
        description="Trading profit divided by merchandise sales or revenue, expressed as a percentage.",
        category=ConceptCategory.MARGIN,
        expected_units=["percentage"],
        allowed_sections=["note_segment", "sens_headline"],
        approved_aliases=["Trading margin", "Trading margin Group"],
        ambiguous_aliases=[],
        prohibited_equivalences=["operating_margin", "gross_margin"]
    ))

    _add(CanonicalConcept(
        concept_id="operating_profit",
        name="Operating Profit",
        description="Statutory operating profit from ordinary activities before net financing costs and tax.",
        category=ConceptCategory.INCOME_STATEMENT,
        expected_units=["ZAR", "USD"],
        allowed_sections=["income_statement", "sens_headline"],
        approved_aliases=[],
        ambiguous_aliases=["Operating profit", "Profit from operations", "operating profit before..."],
        prohibited_equivalences=["trading_profit", "ebit", "profit_before_finance_costs_and_tax"]
    ))

    _add(CanonicalConcept(
        concept_id="operating_margin",
        name="Operating Margin",
        description="Operating profit divided by revenue, expressed as a percentage.",
        category=ConceptCategory.MARGIN,
        expected_units=["percentage"],
        allowed_sections=["sens_headline"],
        approved_aliases=["Operating margin", "Operating profit margin"],
        ambiguous_aliases=[],
        prohibited_equivalences=["trading_margin", "gross_margin"]
    ))

    _add(CanonicalConcept(
        concept_id="profit_before_finance_costs_and_tax",
        name="Profit Before Finance Costs and Tax",
        description="Operating result before finance income, finance costs, and taxation (PBIT).",
        category=ConceptCategory.INCOME_STATEMENT,
        expected_units=["ZAR"],
        allowed_sections=["income_statement"],
        approved_aliases=["Profit before finance costs and tax", "Operating profit before finance costs and tax"],
        ambiguous_aliases=["PBIT"],
        prohibited_equivalences=["trading_profit", "operating_profit"]
    ))

    _add(CanonicalConcept(
        concept_id="ebit",
        name="Earnings Before Interest and Tax (EBIT)",
        description="Standardised economic earnings before net finance expense and corporate tax.",
        category=ConceptCategory.INCOME_STATEMENT,
        expected_units=["ZAR", "USD"],
        allowed_sections=["sens_headline", "income_statement"],
        approved_aliases=["EBIT"],
        ambiguous_aliases=["adjusted ebit", "normalised ebit"],
        prohibited_equivalences=["trading_profit", "operating_profit"]
    ))

    _add(CanonicalConcept(
        concept_id="ebitda",
        name="EBITDA",
        description="Earnings before interest, taxation, depreciation, and amortisation.",
        category=ConceptCategory.INCOME_STATEMENT,
        expected_units=["ZAR", "USD"],
        allowed_sections=["sens_headline", "note_segment"],
        approved_aliases=["EBITDA", "Group EBITDA"],
        ambiguous_aliases=[],
        prohibited_equivalences=["adjusted_ebitda", "normalised_ebitda"]
    ))

    _add(CanonicalConcept(
        concept_id="adjusted_ebitda",
        name="Adjusted EBITDA",
        description="EBITDA adjusted for non-trading, restructuring, or one-off exceptional items.",
        category=ConceptCategory.INCOME_STATEMENT,
        expected_units=["ZAR", "USD"],
        allowed_sections=["sens_headline"],
        approved_aliases=["Adjusted EBITDA"],
        ambiguous_aliases=[],
        prohibited_equivalences=["ebitda", "normalised_ebitda"]
    ))

    _add(CanonicalConcept(
        concept_id="normalised_ebitda",
        name="Normalised EBITDA",
        description="EBITDA adjusted to reflect ongoing underlying operational run-rate.",
        category=ConceptCategory.INCOME_STATEMENT,
        expected_units=["ZAR", "USD"],
        allowed_sections=["sens_headline"],
        approved_aliases=["Normalised EBITDA"],
        ambiguous_aliases=[],
        prohibited_equivalences=["ebitda", "adjusted_ebitda"]
    ))

    # 3. DEPRECIATION & AMORTISATION CONCEPTS
    _add(CanonicalConcept(
        concept_id="depreciation_and_amortisation",
        name="Depreciation and Amortisation",
        description="Total depreciation of tangible PPE and amortisation of intangible assets.",
        category=ConceptCategory.INCOME_STATEMENT,
        expected_units=["ZAR", "USD"],
        allowed_sections=["income_statement", "cash_flow_statement"],
        approved_aliases=["Depreciation and amortisation"],
        ambiguous_aliases=["depreciation", "amortisation", "d&a"],
        prohibited_equivalences=[]
    ))

    _add(CanonicalConcept(
        concept_id="depreciation_amortisation_expense",
        name="Depreciation and Amortisation Expense (IS)",
        description="Depreciation and amortisation expense recognised on the income statement.",
        category=ConceptCategory.INCOME_STATEMENT,
        expected_units=["ZAR", "USD"],
        allowed_sections=["income_statement"],
        approved_aliases=["Depreciation and amortisation expense (Income Statement)"],
        ambiguous_aliases=[],
        prohibited_equivalences=["depreciation_amortisation_cashflow_addback"]
    ))

    _add(CanonicalConcept(
        concept_id="depreciation_amortisation_cashflow_addback",
        name="Depreciation and Amortisation Cash Flow Addback",
        description="Non-cash D&A addback in the cash generated from operations reconciliation note.",
        category=ConceptCategory.CASH_FLOW,
        expected_units=["ZAR", "USD"],
        allowed_sections=["note_cashflow_reconciliation", "cash_flow_statement"],
        approved_aliases=["Depreciation and amortisation cash flow addback"],
        ambiguous_aliases=[],
        prohibited_equivalences=["depreciation_amortisation_expense"]
    ))

    # 4. CASH FLOW & WORKING CAPITAL CONCEPTS
    _add(CanonicalConcept(
        concept_id="cash_generated_from_operations",
        name="Cash Generated From Operations",
        description="Gross cash generated by operating activities before tax and finance cash flows.",
        category=ConceptCategory.CASH_FLOW,
        expected_units=["ZAR", "USD"],
        allowed_sections=["cash_flow_statement", "sens_headline"],
        approved_aliases=["Cash generated from operations", "Cash generated by operations"],
        ambiguous_aliases=["cash flow from operations", "cash flow"],
        prohibited_equivalences=["operating_cash_flow"]
    ))

    _add(CanonicalConcept(
        concept_id="operating_cash_flow",
        name="Operating Cash Flow",
        description="Net cash flow from operating activities after net working capital, tax paid, and finance costs.",
        category=ConceptCategory.CASH_FLOW,
        expected_units=["ZAR", "USD"],
        allowed_sections=["cash_flow_statement"],
        approved_aliases=["Net cash from operating activities", "Cash flow from operating activities"],
        ambiguous_aliases=["operating cash flow"],
        prohibited_equivalences=["cash_generated_from_operations"]
    ))

    _add(CanonicalConcept(
        concept_id="working_capital_movement",
        name="Working Capital Movement",
        description="Net balance-sheet change in working capital assets and liabilities.",
        category=ConceptCategory.CASH_FLOW,
        expected_units=["ZAR", "USD"],
        allowed_sections=["cash_flow_statement", "note_working_capital"],
        approved_aliases=["Working capital movements"],
        ambiguous_aliases=["working capital", "change in working capital"],
        prohibited_equivalences=[]
    ))

    _add(CanonicalConcept(
        concept_id="working_capital_cash_flow",
        name="Working Capital Cash Flow",
        description="Cash-flow statement working capital adjustment where positive values denote a cash inflow.",
        category=ConceptCategory.CASH_FLOW,
        expected_units=["ZAR", "USD"],
        allowed_sections=["cash_flow_statement"],
        approved_aliases=["Working capital cash flow (positive = cash inflow)"],
        ambiguous_aliases=[],
        prohibited_equivalences=[]
    ))

    # 5. CAPEX CONCEPTS
    _add(CanonicalConcept(
        concept_id="cash_capex",
        name="Cash Capital Expenditure",
        description="Total cash paid for capital expenditure on property, plant, equipment, and intangibles (cash-flow statement basis).",
        category=ConceptCategory.CASH_FLOW,
        expected_units=["ZAR", "USD"],
        allowed_sections=["cash_flow_statement"],
        approved_aliases=["Total cash capex (cash payments basis)"],
        ambiguous_aliases=["capital expenditure", "capex"],
        prohibited_equivalences=["total_capex", "capex_expansion", "capex_maintenance"]
    ))

    _add(CanonicalConcept(
        concept_id="total_capex",
        name="Total Capex (Additions Basis)",
        description="Sum of all capital additions across expansion, maintenance, and software.",
        category=ConceptCategory.CASH_FLOW,
        expected_units=["ZAR", "USD"],
        allowed_sections=["cash_flow_statement", "note_capex"],
        approved_aliases=["Total capex"],
        ambiguous_aliases=["capex additions", "capital expenditure additions"],
        prohibited_equivalences=["cash_capex"]
    ))

    _add(CanonicalConcept(
        concept_id="capex_expansion",
        name="Expansion Capex",
        description="Capital expenditure directed towards expanding operations / growth capacity.",
        category=ConceptCategory.CASH_FLOW,
        expected_units=["ZAR", "USD"],
        allowed_sections=["cash_flow_statement"],
        approved_aliases=["Acquisition of plant and equipment to expand operations"],
        ambiguous_aliases=["expansion capex", "growth capex"],
        prohibited_equivalences=["cash_capex"]
    ))

    _add(CanonicalConcept(
        concept_id="capex_maintenance",
        name="Maintenance Capex",
        description="Capital expenditure directed towards sustaining existing operational capacity.",
        category=ConceptCategory.CASH_FLOW,
        expected_units=["ZAR", "USD"],
        allowed_sections=["cash_flow_statement"],
        approved_aliases=["Acquisition of plant and equipment to maintain operations"],
        ambiguous_aliases=["maintenance capex", "sustaining capex"],
        prohibited_equivalences=["cash_capex"]
    ))

    _add(CanonicalConcept(
        concept_id="intangible_additions",
        name="Intangible Additions",
        description="Cash expenditure or additions for computer software and intangible assets.",
        category=ConceptCategory.CASH_FLOW,
        expected_units=["ZAR", "USD"],
        allowed_sections=["cash_flow_statement"],
        approved_aliases=["Acquisition of computer software"],
        ambiguous_aliases=["software additions"],
        prohibited_equivalences=[]
    ))

    # 6. NET CASH & DEBT CONCEPTS
    _add(CanonicalConcept(
        concept_id="cash_and_cash_equivalents",
        name="Cash and Cash Equivalents",
        description="Cash on hand, bank balances, and short-term liquid deposits on balance sheet.",
        category=ConceptCategory.BALANCE_SHEET,
        expected_units=["ZAR", "USD"],
        allowed_sections=["balance_sheet"],
        approved_aliases=["Cash and cash equivalents"],
        ambiguous_aliases=["cash"],
        prohibited_equivalences=["reported_net_cash"]
    ))

    _add(CanonicalConcept(
        concept_id="money_market_funds",
        name="Money Market Funds",
        description="Assets held at fair value through profit or loss in money market investment vehicles.",
        category=ConceptCategory.BALANCE_SHEET,
        expected_units=["ZAR", "USD"],
        allowed_sections=["balance_sheet", "note_investments"],
        approved_aliases=["Current assets held at fair value (money market)", "Assets held at fair value"],
        ambiguous_aliases=[],
        prohibited_equivalences=[]
    ))

    _add(CanonicalConcept(
        concept_id="interest_bearing_borrowings",
        name="Interest-Bearing Borrowings",
        description="Formal financial debt and bank borrowings on balance sheet face. Evidenced as EX_LEASES via balance-sheet presentation separate from lease liabilities (IAS 1.54 / IFRS 16.47).",
        category=ConceptCategory.BALANCE_SHEET,
        expected_units=["ZAR", "USD"],
        allowed_sections=["balance_sheet"],
        approved_aliases=["Interest-bearing borrowings", "Interest -bearing borrowings"],
        ambiguous_aliases=["borrowings", "debt", "interest-bearing debt", "total borrowings"],
        prohibited_equivalences=["reported_net_debt", "lease_liabilities", "bank_overdraft"],
        default_qualifiers=SemanticQualifiers(
            lease_inclusion=LeaseInclusion.EX_LEASES,
            basis_evidence=BasisEvidence.BALANCE_SHEET_PRESENTATION_SEPARATE,
            custom_notes="Evidenced as EX_LEASES via balance-sheet presentation separate from lease liabilities under IAS 1.54 / IFRS 16.47."
        )
    ))

    _add(CanonicalConcept(
        concept_id="bank_overdraft",
        name="Bank Overdraft",
        description="Overdraft facilities utilised at the reporting date.",
        category=ConceptCategory.BALANCE_SHEET,
        expected_units=["ZAR", "USD"],
        allowed_sections=["balance_sheet"],
        approved_aliases=["Bank overdraft"],
        ambiguous_aliases=[],
        prohibited_equivalences=[]
    ))

    _add(CanonicalConcept(
        concept_id="reported_net_cash",
        name="Reported Net Cash",
        description="Management-reported net cash balance (cash and equivalents less borrowings). Evidenced as EX_LEASES via explicit note wording or reconciled footnote formula.",
        category=ConceptCategory.BALANCE_SHEET,
        expected_units=["ZAR", "USD"],
        allowed_sections=["sens_headline"],
        approved_aliases=[
            "Net cash (excluding lease liabilities)",
            "Net cash excluding leases",
            "Net cash excluding lease liabilities"
        ],
        ambiguous_aliases=["net cash", "reported net cash", "net cash at period end", "net cash position"],
        prohibited_equivalences=["cash_and_cash_equivalents", "reported_net_debt"],
        default_qualifiers=SemanticQualifiers(
            lease_inclusion=LeaseInclusion.EX_LEASES,
            basis_evidence=BasisEvidence.EXPLICIT_NOTE_WORDING,
            custom_notes="Evidenced as EX_LEASES via explicit label wording or reconciled footnote formula (e.g. TRU Note 49 formula)."
        )
    ))

    _add(CanonicalConcept(
        concept_id="reported_net_debt",
        name="Reported Net Debt",
        description="Management-reported net debt balance (borrowings less cash balances). Evidenced as EX_LEASES via explicit note wording or reconciled footnote formula.",
        category=ConceptCategory.BALANCE_SHEET,
        expected_units=["ZAR", "USD"],
        allowed_sections=["sens_headline"],
        approved_aliases=[
            "Net debt (excluding lease liabilities)",
            "Net debt excluding leases",
            "Net debt excluding lease liabilities"
        ],
        ambiguous_aliases=["net debt", "reported net debt", "net debt at period end", "net debt position"],
        prohibited_equivalences=["interest_bearing_borrowings", "reported_net_cash"],
        default_qualifiers=SemanticQualifiers(
            lease_inclusion=LeaseInclusion.EX_LEASES,
            basis_evidence=BasisEvidence.EXPLICIT_NOTE_WORDING,
            custom_notes="Evidenced as EX_LEASES via explicit label wording or reconciled footnote formula."
        )
    ))

    _add(CanonicalConcept(
        concept_id="lease_liabilities",
        name="Total Lease Liabilities",
        description="Total IFRS 16 lease liability commitments (current plus non-current).",
        category=ConceptCategory.BALANCE_SHEET,
        expected_units=["ZAR", "USD"],
        allowed_sections=["balance_sheet"],
        approved_aliases=["Total lease liabilities", "Lease liabilities"],
        ambiguous_aliases=[],
        prohibited_equivalences=[]
    ))

    _add(CanonicalConcept(
        concept_id="lease_liabilities_current",
        name="Current Lease Liabilities",
        description="Portion of lease liabilities due within 12 months.",
        category=ConceptCategory.BALANCE_SHEET,
        expected_units=["ZAR", "USD"],
        allowed_sections=["balance_sheet"],
        approved_aliases=["Current lease liabilities"],
        ambiguous_aliases=[],
        prohibited_equivalences=[]
    ))

    _add(CanonicalConcept(
        concept_id="lease_liabilities_noncurrent",
        name="Non-Current Lease Liabilities",
        description="Portion of lease liabilities due after 12 months.",
        category=ConceptCategory.BALANCE_SHEET,
        expected_units=["ZAR", "USD"],
        allowed_sections=["balance_sheet"],
        approved_aliases=["Non-current lease liabilities"],
        ambiguous_aliases=[],
        prohibited_equivalences=[]
    ))

    # 7. SHARE COUNT CONCEPTS
    _add(CanonicalConcept(
        concept_id="issued_shares_current",
        name="Issued Shares Current",
        description="Total ordinary shares issued by the company (including treasury shares).",
        category=ConceptCategory.SHARES,
        expected_units=["shares"],
        allowed_sections=["sens_corporate_action", "note_share_capital"],
        approved_aliases=[
            "issued_shares_current",
            "Note 13: Issued and fully paid",
            "ordinary shares in issue"
        ],
        ambiguous_aliases=["shares in issue", "number of shares"],
        prohibited_equivalences=["weighted_average_basic_shares", "period_end_external_shares"]
    ))

    _add(CanonicalConcept(
        concept_id="treasury_shares",
        name="Treasury Shares",
        description="Ordinary shares held by subsidiaries or share incentive schemes.",
        category=ConceptCategory.SHARES,
        expected_units=["shares"],
        allowed_sections=["sens_corporate_action", "note_treasury_shares"],
        approved_aliases=[
            "treasury_shares",
            "treasury shares",
            "Note 14: Treasury shares at reporting date"
        ],
        ambiguous_aliases=[],
        prohibited_equivalences=[]
    ))

    _add(CanonicalConcept(
        concept_id="external_shares_ex_treasury",
        name="External Shares Excluding Treasury",
        description="Total issued shares less treasury shares held.",
        category=ConceptCategory.SHARES,
        expected_units=["shares"],
        allowed_sections=["note_share_capital"],
        approved_aliases=["External shares excluding treasury"],
        ambiguous_aliases=[],
        prohibited_equivalences=["weighted_average_basic_shares"]
    ))

    _add(CanonicalConcept(
        concept_id="period_end_external_shares",
        name="Period-End External Shares",
        description="External share count as of the economic period-end date.",
        category=ConceptCategory.SHARES,
        expected_units=["shares"],
        allowed_sections=["note_share_capital"],
        approved_aliases=["Period-end external shares excluding treasury"],
        ambiguous_aliases=[],
        prohibited_equivalences=["weighted_average_basic_shares", "weighted_average_diluted_shares"]
    ))

    _add(CanonicalConcept(
        concept_id="announcement_date_external_shares",
        name="Announcement-Date External Shares",
        description="External share count as disclosed on the results announcement publication date.",
        category=ConceptCategory.SHARES,
        expected_units=["shares"],
        allowed_sections=["sens_corporate_action"],
        approved_aliases=["Announcement date external shares"],
        ambiguous_aliases=[],
        prohibited_equivalences=["weighted_average_basic_shares", "weighted_average_diluted_shares"]
    ))

    _add(CanonicalConcept(
        concept_id="weighted_average_basic_shares",
        name="Weighted Average Basic Shares",
        description="Time-weighted average ordinary shares for basic EPS calculation.",
        category=ConceptCategory.SHARES,
        expected_units=["shares"],
        allowed_sections=["note_per_share"],
        approved_aliases=[
            "Weighted average number of shares for the reporting period (millions)"
        ],
        ambiguous_aliases=["weighted average shares", "weighted average number of shares"],
        prohibited_equivalences=["issued_shares_current", "period_end_external_shares", "announcement_date_external_shares"]
    ))

    _add(CanonicalConcept(
        concept_id="weighted_average_diluted_shares",
        name="Weighted Average Diluted Shares",
        description="Time-weighted average shares adjusted for dilutive share options and rights.",
        category=ConceptCategory.SHARES,
        expected_units=["shares"],
        allowed_sections=["note_per_share"],
        approved_aliases=[
            "Diluted weighted average number of shares for the reporting period (millions)"
        ],
        ambiguous_aliases=["diluted weighted average shares", "diluted weighted average number of shares"],
        prohibited_equivalences=["issued_shares_current", "period_end_external_shares", "announcement_date_external_shares"]
    ))

    # 8. PER-SHARE EARNINGS CONCEPTS
    _add(CanonicalConcept(
        concept_id="eps",
        name="Basic Earnings Per Share (EPS)",
        description="Basic earnings per share in ZAR cents.",
        category=ConceptCategory.PER_SHARE,
        expected_units=["ZAR_cents"],
        allowed_sections=["income_statement", "sens_headline"],
        approved_aliases=[
            "Earnings per share",
            "Basic earnings per share (cents)"
        ],
        ambiguous_aliases=["basic earnings per share", "eps"],
        prohibited_equivalences=["heps", "diluted_eps"]
    ))

    _add(CanonicalConcept(
        concept_id="diluted_eps",
        name="Diluted Earnings Per Share",
        description="Diluted basic earnings per share in ZAR cents.",
        category=ConceptCategory.PER_SHARE,
        expected_units=["ZAR_cents"],
        allowed_sections=["income_statement", "sens_headline"],
        approved_aliases=[
            "Diluted basic earnings per share (cents)"
        ],
        ambiguous_aliases=["diluted earnings per share", "diluted eps"],
        prohibited_equivalences=["eps", "diluted_heps"]
    ))

    _add(CanonicalConcept(
        concept_id="heps",
        name="Headline Earnings Per Share (HEPS)",
        description="Headline earnings per share according to SAICA Circular 1/2023 in ZAR cents.",
        category=ConceptCategory.PER_SHARE,
        expected_units=["ZAR_cents"],
        allowed_sections=["sens_headline", "note_per_share"],
        approved_aliases=[
            "Headline earnings per share",
            "Headline earnings per share (cents)"
        ],
        ambiguous_aliases=["heps"],
        prohibited_equivalences=["eps", "diluted_heps"]
    ))

    _add(CanonicalConcept(
        concept_id="diluted_heps",
        name="Diluted Headline Earnings Per Share",
        description="Diluted headline earnings per share in ZAR cents.",
        category=ConceptCategory.PER_SHARE,
        expected_units=["ZAR_cents"],
        allowed_sections=["sens_headline", "note_per_share"],
        approved_aliases=[
            "Diluted headline earnings per share",
            "Diluted headline earnings per share (cents)"
        ],
        ambiguous_aliases=["diluted heps", "dheps"],
        prohibited_equivalences=["heps", "diluted_eps"]
    ))

    # 9. TAX CONCEPTS
    _add(CanonicalConcept(
        concept_id="tax_expense",
        name="Tax Expense",
        description="Total income tax expense recognised in the statement of comprehensive income.",
        category=ConceptCategory.TAX,
        expected_units=["ZAR", "USD"],
        allowed_sections=["income_statement"],
        approved_aliases=["Tax expense"],
        ambiguous_aliases=["taxation", "tax"],
        prohibited_equivalences=[]
    ))

    _add(CanonicalConcept(
        concept_id="effective_tax_rate",
        name="Effective Tax Rate",
        description="Effective group taxation rate as a percentage of profit before tax.",
        category=ConceptCategory.TAX,
        expected_units=["percentage"],
        allowed_sections=["note_tax_expense"],
        approved_aliases=["Effective Group tax rate"],
        ambiguous_aliases=["effective tax rate"],
        prohibited_equivalences=["statutory_tax_rate"]
    ))

    _add(CanonicalConcept(
        concept_id="statutory_tax_rate",
        name="Statutory Tax Rate",
        description="Standard South African statutory corporate income tax rate.",
        category=ConceptCategory.TAX,
        expected_units=["percentage"],
        allowed_sections=["note_tax_expense"],
        approved_aliases=["South African current tax rate"],
        ambiguous_aliases=["statutory tax rate"],
        prohibited_equivalences=["effective_tax_rate"]
    ))

    # 10. DIVIDEND CONCEPTS
    _add(CanonicalConcept(
        concept_id="dividend_per_share",
        name="Dividend Per Share",
        description="Declared dividend per ordinary share in ZAR cents.",
        category=ConceptCategory.PER_SHARE,
        expected_units=["ZAR_cents"],
        allowed_sections=["sens_headline", "note_dividends"],
        approved_aliases=["Dividend per share"],
        ambiguous_aliases=["annual_dividend_per_share", "interim_dividend_per_share", "final_dividend_per_share"],
        prohibited_equivalences=[]
    ))

    _add(CanonicalConcept(
        concept_id="annual_dividend_per_share",
        name="Annual Dividend Per Share",
        description="Full-year aggregate dividend per ordinary share in ZAR cents.",
        category=ConceptCategory.PER_SHARE,
        expected_units=["ZAR_cents"],
        allowed_sections=["sens_headline"],
        approved_aliases=["Annual dividend per share"],
        ambiguous_aliases=["total dividend per share"],
        prohibited_equivalences=["interim_dividend_per_share", "final_dividend_per_share"]
    ))

    _add(CanonicalConcept(
        concept_id="final_dividend_per_share",
        name="Final Dividend Per Share",
        description="Final dividend declared at the end of the financial year in ZAR cents.",
        category=ConceptCategory.PER_SHARE,
        expected_units=["ZAR_cents"],
        allowed_sections=["sens_headline"],
        approved_aliases=["Final dividend per share"],
        ambiguous_aliases=[],
        prohibited_equivalences=["interim_dividend_per_share", "annual_dividend_per_share"]
    ))

    _add(CanonicalConcept(
        concept_id="interim_dividend_per_share",
        name="Interim Dividend Per Share",
        description="Interim dividend declared at the half-year reporting date in ZAR cents.",
        category=ConceptCategory.PER_SHARE,
        expected_units=["ZAR_cents"],
        allowed_sections=["sens_headline"],
        approved_aliases=["Interim dividend per share"],
        ambiguous_aliases=[],
        prohibited_equivalences=["final_dividend_per_share", "annual_dividend_per_share"]
    ))

    # 11. NAV CONCEPTS
    _add(CanonicalConcept(
        concept_id="nav_per_share",
        name="Net Asset Value Per Share",
        description="Net asset value divided by external shares, in ZAR cents.",
        category=ConceptCategory.PER_SHARE,
        expected_units=["ZAR_cents"],
        allowed_sections=["sens_headline"],
        approved_aliases=["Net asset value per share"],
        ambiguous_aliases=["nav per share"],
        prohibited_equivalences=["tangible_nav_per_share"]
    ))

    _add(CanonicalConcept(
        concept_id="tangible_nav_per_share",
        name="Tangible Net Asset Value Per Share",
        description="Net asset value excluding goodwill and intangibles, in ZAR cents.",
        category=ConceptCategory.PER_SHARE,
        expected_units=["ZAR_cents"],
        allowed_sections=["sens_headline"],
        approved_aliases=["Tangible net asset value per share"],
        ambiguous_aliases=["tnav per share"],
        prohibited_equivalences=["nav_per_share"]
    ))

    # 12. OTHER STATEMENT ITEMS
    _add(CanonicalConcept(
        concept_id="attributable_earnings",
        name="Attributable Earnings",
        description="Profit for the period attributable to equity holders of the parent.",
        category=ConceptCategory.INCOME_STATEMENT,
        expected_units=["ZAR"],
        allowed_sections=["income_statement"],
        approved_aliases=["Equity holders of the Company"],
        ambiguous_aliases=["attributable profit"],
        prohibited_equivalences=["headline_earnings"]
    ))

    _add(CanonicalConcept(
        concept_id="headline_earnings",
        name="Headline Earnings",
        description="Aggregate headline earnings in ZAR (before dividing by share count).",
        category=ConceptCategory.INCOME_STATEMENT,
        expected_units=["ZAR"],
        allowed_sections=["sens_headline", "note_per_share"],
        approved_aliases=["Headline earnings"],
        ambiguous_aliases=[],
        prohibited_equivalences=["attributable_earnings", "heps"]
    ))

    _add(CanonicalConcept(
        concept_id="profit_before_tax",
        name="Profit Before Tax",
        description="Consolidated profit before taxation.",
        category=ConceptCategory.INCOME_STATEMENT,
        expected_units=["ZAR"],
        allowed_sections=["income_statement"],
        approved_aliases=["Profit before tax"],
        ambiguous_aliases=["profit before taxation", "pbt"],
        prohibited_equivalences=[]
    ))

    _add(CanonicalConcept(
        concept_id="profit_for_period",
        name="Profit for the Period",
        description="Consolidated profit after taxation for the reporting period.",
        category=ConceptCategory.INCOME_STATEMENT,
        expected_units=["ZAR"],
        allowed_sections=["income_statement"],
        approved_aliases=["Profit for the period"],
        ambiguous_aliases=["profit after tax"],
        prohibited_equivalences=[]
    ))

    return concepts
