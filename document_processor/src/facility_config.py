"""Facility configuration loader for per-facility override rules."""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

from rapidfuzz import fuzz

from src.logger import get_logger

logger = get_logger(__name__)


class FacilityNotFoundError(Exception):
    """Raised when a facility ID is not found in the configuration."""

    def __init__(self, facility_id: str):
        self.facility_id = facility_id
        super().__init__(f"Facility '{facility_id}' not found in configuration")


class FacilityConfig:
    """Loads and provides access to facility-specific configuration."""

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize the facility configuration loader.

        Args:
            config_path: Path to facilities.json. If None, uses default location
                         relative to this module (config/facilities.json).
        """
        if config_path is None:
            # Default to config/facilities.json relative to document_processor root
            module_dir = Path(__file__).parent.parent
            config_path = module_dir / "config" / "facilities.json"

        self.config_path = Path(config_path)
        self._config: Dict[str, Dict[str, Any]] = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load the facilities configuration from JSON file."""
        logger.debug(f"Loading facility config from: {self.config_path}")
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self._config = json.load(f)
            logger.debug(f"Loaded {len(self._config)} facility configuration(s)")
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Facilities configuration file not found: {self.config_path}"
            )
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Invalid JSON in facilities configuration: {self.config_path}. Error: {e}"
            )

    def get_facility(self, facility_id: str) -> Dict[str, Any]:
        """
        Get facility configuration by ID.

        Args:
            facility_id: The facility identifier (e.g., "baywood_court")

        Returns:
            Dictionary containing "display_name" and "overrides" keys

        Raises:
            FacilityNotFoundError: If the facility_id is not in the configuration
        """
        if facility_id not in self._config:
            raise FacilityNotFoundError(facility_id)

        facility_data = self._config[facility_id]
        return {
            "display_name": facility_data.get("display_name", ""),
            "overrides": facility_data.get("overrides", []),
        }

    def load_facilities(self) -> Dict[str, Any]:
        """Return the raw facilities config dict. Used by classifier."""
        return self._config.copy()

    def find_facility_by_name(
        self,
        name: str,
        fuzzy_threshold: float = 0.80,
    ) -> Tuple[Optional[str], float]:
        """
        Find facility_id for a given display name.

        Args:
            name: Display name to search for
            fuzzy_threshold: Minimum score for fuzzy match (0.0-1.0)

        Returns:
            Tuple of (facility_id, score) or (None, 0.0)
        """
        if not name or not name.strip():
            return None, 0.0

        name = name.strip()

        # Step 1: Check for exact match (case-insensitive)
        for facility_id, facility_data in self._config.items():
            display_names = facility_data.get("display_names", [])
            # Also check display_name as fallback
            if not display_names:
                display_names = [facility_data.get("display_name", "")]
            
            for display_name in display_names:
                if display_name and display_name.strip().lower() == name.lower():
                    return facility_id, 1.0

        # Step 2: Fuzzy match against all display_names
        best_match: Optional[Tuple[str, float]] = None  # (facility_id, score)
        all_matches: List[Tuple[str, str, float]] = []  # (facility_id, display_name, score)

        for facility_id, facility_data in self._config.items():
            display_names = facility_data.get("display_names", [])
            # Also check display_name as fallback
            if not display_names:
                display_names = [facility_data.get("display_name", "")]
            
            for display_name in display_names:
                if not display_name:
                    continue
                
                # Use token_sort_ratio (handles word order differences)
                score = fuzz.token_sort_ratio(name, display_name) / 100.0
                
                if score >= fuzzy_threshold:
                    all_matches.append((facility_id, display_name, score))
                    if best_match is None or score > best_match[1]:
                        best_match = (facility_id, score)

        # Step 3: Tiebreaker logic
        if best_match is None:
            return None, 0.0

        # Check for exact tie (multiple facilities with same highest score)
        if len(all_matches) > 1:
            highest_score = best_match[1]
            ties = [m for m in all_matches if m[2] == highest_score]
            if len(ties) > 1:
                # Exact tie — return None to flag for review
                logger.warning(
                    f"Fuzzy match tie: '{name}' matches {len(ties)} facilities "
                    f"with score {highest_score:.2f}: {[t[0] for t in ties]}"
                )
                return None, highest_score

        # Single best match
        facility_id, score = best_match
        return facility_id, score
