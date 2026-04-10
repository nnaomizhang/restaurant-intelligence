"""
ONS Census Data Collector
=========================
Downloads and merges demographic data from ONS/Nomis at LSOA level.

Data source: https://www.nomisweb.co.uk/ (Census 2021)

Required downloads from Nomis (Census 2021, LSOA level):
  - TS007a: Age by single year of age
  - TS021:  Ethnic group
  - TS066:  Economic activity status
  - TS003:  Household composition
  - Income: ONS small area income estimates (MSOA level, mapped to LSOA)

This collector can:
  1. Load pre-downloaded CSV files and merge them
  2. Load a pre-merged single CSV with all columns
  3. Use the Nomis API for automated download (if available)
"""

import csv
import json
import re
from pathlib import Path

import pandas as pd

from config import RAW_DIR
from collectors.base import BaseCollector


class ONSCensusCollector(BaseCollector):

    VERSION = "1.0"

    # Expected columns in the final merged output
    EXPECTED_COLUMNS = [
        "lsoa_code", "lsoa_name", "total_population",
        "population_density",
        "age_18_24_pct", "age_25_34_pct", "age_35_49_pct",
        "age_50_64_pct", "age_65_plus_pct",
        "median_household_income",
        "ethnicity_white_pct", "ethnicity_asian_pct",
        "ethnicity_black_pct", "ethnicity_mixed_pct",
        "ethnicity_other_pct",
        "economically_active_pct", "employment_office_pct",
        "household_single_pct", "household_family_pct",
    ]

    def __init__(self):
        super().__init__(
            source_name="ons_census",
            raw_dir=RAW_DIR / "ons_census",
            method="download",
        )

    def collect(self, area: dict) -> list[dict]:
        """
        Load and merge ONS census data for a target area.

        Tries (in order):
          1. Pre-merged single CSV ({area}_demographics.csv)
          2. Individual census table CSVs to merge
          3. Manual JSON fallback
        """
        area_name = area["name"]
        slug = area_name.lower().replace(" ", "_").replace("-", "_")
        postcode_prefix = area.get("postcode_prefix", "")
        self.logger.info(f"Loading ONS data for {area_name}")

        # Option 1: Pre-merged CSV (recommended)
        merged_path = self.raw_dir / f"{slug}_demographics.csv"
        if merged_path.exists():
            records = self._load_merged_csv(merged_path, area_name)
            if records:
                self.save_raw(records, area_name)
                return records

        # Option 2: Merge individual census table CSVs
        individual_files = {
            "age": self.raw_dir / f"{slug}_age.csv",
            "ethnicity": self.raw_dir / f"{slug}_ethnicity.csv",
            "economic": self.raw_dir / f"{slug}_economic.csv",
            "household": self.raw_dir / f"{slug}_household.csv",
            "income": self.raw_dir / f"{slug}_income.csv",
        }
        if any(f.exists() for f in individual_files.values()):
            records = self._merge_census_tables(
                individual_files, area_name
            )
            if records:
                self.save_raw(records, area_name)
                return records

        # Option 3: Manual JSON
        records = self.load_manual_data(area_name)
        if records:
            self.save_raw(records, area_name)
            return records

        # Nothing found — print instructions
        self.logger.warning(f"No ONS data found for {area_name}")
        self._print_download_instructions(slug, area)
        return []

    # ------------------------------------------------------------------
    # Loading pre-merged data
    # ------------------------------------------------------------------

    def _load_merged_csv(
        self, path: Path, area_name: str
    ) -> list[dict]:
        """Load a pre-merged demographics CSV."""
        self.logger.info(f"Loading merged CSV: {path}")

        try:
            df = pd.read_csv(path)
        except Exception as e:
            self.logger.error(f"Failed to read {path}: {e}")
            return []

        # Normalise column names
        df.columns = [
            c.strip().lower().replace(" ", "_") for c in df.columns
        ]

        # Validate expected columns
        missing = [
            c for c in ["lsoa_code", "lsoa_name"]
            if c not in df.columns
        ]
        if missing:
            self.logger.error(
                f"Missing required columns: {missing}. "
                f"Available: {list(df.columns)}"
            )
            return []

        # Add neighbourhood
        df["neighbourhood"] = area_name

        records = df.to_dict(orient="records")
        self.logger.info(f"Loaded {len(records)} LSOAs from merged CSV")
        return records

    # ------------------------------------------------------------------
    # Merging individual census tables
    # ------------------------------------------------------------------

    def _merge_census_tables(
        self, files: dict[str, Path], area_name: str
    ) -> list[dict]:
        """
        Merge multiple census table CSVs into one unified dataset.
        Each file has different column structures — this method
        standardises and joins them on LSOA code.
        """
        self.logger.info("Merging individual census table CSVs...")
        merged = None

        # --- Age data ---
        if files["age"].exists():
            self.logger.info(f"  Processing age data: {files['age']}")
            age_df = self._process_age_data(files["age"])
            merged = age_df

        # --- Ethnicity data ---
        if files["ethnicity"].exists():
            self.logger.info(
                f"  Processing ethnicity data: {files['ethnicity']}"
            )
            eth_df = self._process_ethnicity_data(files["ethnicity"])
            if merged is not None:
                merged = merged.merge(eth_df, on="lsoa_code", how="outer")
            else:
                merged = eth_df

        # --- Economic activity data ---
        if files["economic"].exists():
            self.logger.info(
                f"  Processing economic data: {files['economic']}"
            )
            econ_df = self._process_economic_data(files["economic"])
            if merged is not None:
                merged = merged.merge(econ_df, on="lsoa_code", how="outer")
            else:
                merged = econ_df

        # --- Household data ---
        if files["household"].exists():
            self.logger.info(
                f"  Processing household data: {files['household']}"
            )
            hh_df = self._process_household_data(files["household"])
            if merged is not None:
                merged = merged.merge(hh_df, on="lsoa_code", how="outer")
            else:
                merged = hh_df

        # --- Income data (MSOA level — needs mapping) ---
        if files["income"].exists():
            self.logger.info(
                f"  Processing income data: {files['income']}"
            )
            inc_df = self._process_income_data(files["income"])
            if merged is not None and inc_df is not None:
                merged = merged.merge(inc_df, on="lsoa_code", how="left")

        if merged is None or merged.empty:
            return []

        merged["neighbourhood"] = area_name

        # Save the merged CSV for future reuse
        slug = area_name.lower().replace(" ", "_").replace("-", "_")
        merged_path = self.raw_dir / f"{slug}_demographics.csv"
        merged.to_csv(merged_path, index=False)
        self.logger.info(f"Saved merged CSV to {merged_path}")

        records = merged.to_dict(orient="records")
        self.logger.info(f"Merged {len(records)} LSOAs from individual tables")
        return records

    def _process_age_data(self, path: Path) -> pd.DataFrame:
        """
        Process Nomis age table (TS007a) into age bracket percentages.

        Nomis CSV typically has columns like:
        'geography code', 'geography', 'Age: Total', 'Age: Aged 0 to 4', ...
        """
        df = pd.read_csv(path)
        df.columns = [c.strip().lower() for c in df.columns]

        # Find the LSOA code column (varies by download format)
        code_col = self._find_column(
            df, ["geography code", "lsoa code", "area code", "lsoa_code"]
        )
        name_col = self._find_column(
            df, ["geography", "lsoa name", "area name", "lsoa_name"]
        )

        if not code_col:
            self.logger.warning("Cannot find LSOA code column in age data")
            return pd.DataFrame()

        result = pd.DataFrame()
        result["lsoa_code"] = df[code_col]
        if name_col:
            result["lsoa_name"] = df[name_col]

        # Find total population column
        total_col = self._find_column(
            df, ["age: total", "total", "all ages", "total_population"]
        )
        if total_col:
            result["total_population"] = pd.to_numeric(
                df[total_col], errors="coerce"
            )

        # Calculate age bracket percentages
        # This is simplified — actual Nomis output may have different column names
        total = result["total_population"] if "total_population" in result.columns else 1

        age_brackets = {
            "age_18_24_pct": list(range(18, 25)),
            "age_25_34_pct": list(range(25, 35)),
            "age_35_49_pct": list(range(35, 50)),
            "age_50_64_pct": list(range(50, 65)),
            "age_65_plus_pct": list(range(65, 100)),
        }

        for bracket_name, ages in age_brackets.items():
            bracket_sum = pd.Series(0, index=df.index)
            for age in ages:
                age_col = self._find_column(
                    df, [f"age: aged {age}", f"aged {age}", str(age)]
                )
                if age_col:
                    bracket_sum += pd.to_numeric(
                        df[age_col], errors="coerce"
                    ).fillna(0)
            if total is not None:
                result[bracket_name] = (bracket_sum / total * 100).round(1)

        return result

    def _process_ethnicity_data(self, path: Path) -> pd.DataFrame:
        """Process Nomis ethnicity table (TS021)."""
        df = pd.read_csv(path)
        df.columns = [c.strip().lower() for c in df.columns]

        code_col = self._find_column(
            df, ["geography code", "lsoa code", "area code", "lsoa_code"]
        )
        if not code_col:
            return pd.DataFrame()

        result = pd.DataFrame()
        result["lsoa_code"] = df[code_col]

        total_col = self._find_column(df, ["total", "all persons"])
        total = pd.to_numeric(df[total_col], errors="coerce") if total_col else 1

        ethnicity_map = {
            "ethnicity_white_pct": ["white"],
            "ethnicity_asian_pct": ["asian"],
            "ethnicity_black_pct": ["black"],
            "ethnicity_mixed_pct": ["mixed"],
            "ethnicity_other_pct": ["other"],
        }

        for col_name, keywords in ethnicity_map.items():
            eth_col = self._find_column_containing(df, keywords)
            if eth_col:
                val = pd.to_numeric(df[eth_col], errors="coerce").fillna(0)
                result[col_name] = (val / total * 100).round(1)

        return result

    def _process_economic_data(self, path: Path) -> pd.DataFrame:
        """Process Nomis economic activity table (TS066)."""
        df = pd.read_csv(path)
        df.columns = [c.strip().lower() for c in df.columns]

        code_col = self._find_column(
            df, ["geography code", "lsoa code", "area code", "lsoa_code"]
        )
        if not code_col:
            return pd.DataFrame()

        result = pd.DataFrame()
        result["lsoa_code"] = df[code_col]

        total_col = self._find_column(df, ["total", "all persons"])
        total = pd.to_numeric(df[total_col], errors="coerce") if total_col else 1

        active_col = self._find_column_containing(
            df, ["economically active"]
        )
        if active_col:
            val = pd.to_numeric(df[active_col], errors="coerce").fillna(0)
            result["economically_active_pct"] = (val / total * 100).round(1)

        return result

    def _process_household_data(self, path: Path) -> pd.DataFrame:
        """Process Nomis household composition table (TS003)."""
        df = pd.read_csv(path)
        df.columns = [c.strip().lower() for c in df.columns]

        code_col = self._find_column(
            df, ["geography code", "lsoa code", "area code", "lsoa_code"]
        )
        if not code_col:
            return pd.DataFrame()

        result = pd.DataFrame()
        result["lsoa_code"] = df[code_col]

        total_col = self._find_column(df, ["total", "all households"])
        total = pd.to_numeric(df[total_col], errors="coerce") if total_col else 1

        single_col = self._find_column_containing(df, ["one person", "single"])
        family_col = self._find_column_containing(df, ["family", "couple"])

        if single_col:
            val = pd.to_numeric(df[single_col], errors="coerce").fillna(0)
            result["household_single_pct"] = (val / total * 100).round(1)
        if family_col:
            val = pd.to_numeric(df[family_col], errors="coerce").fillna(0)
            result["household_family_pct"] = (val / total * 100).round(1)

        return result

    def _process_income_data(self, path: Path) -> pd.DataFrame | None:
        """
        Process ONS income estimates.
        Income data is at MSOA level — map to LSOA using a lookup.
        For coursework, a simple approach: assign MSOA income to all
        LSOAs within that MSOA.
        """
        try:
            df = pd.read_csv(path)
            df.columns = [c.strip().lower() for c in df.columns]

            code_col = self._find_column(
                df, ["lsoa code", "msoa code", "geography code", "lsoa_code"]
            )
            income_col = self._find_column(
                df, [
                    "median", "median_household_income",
                    "net annual income", "total income",
                ]
            )

            if not code_col or not income_col:
                self.logger.warning("Could not find income columns")
                return None

            result = pd.DataFrame()
            result["lsoa_code"] = df[code_col]
            result["median_household_income"] = pd.to_numeric(
                df[income_col], errors="coerce"
            )
            return result
        except Exception as e:
            self.logger.warning(f"Income processing failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Column-finding helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
        """Find the first matching column name (case-insensitive)."""
        cols_lower = {c.lower(): c for c in df.columns}
        for candidate in candidates:
            if candidate.lower() in cols_lower:
                return cols_lower[candidate.lower()]
        return None

    @staticmethod
    def _find_column_containing(
        df: pd.DataFrame, keywords: list[str]
    ) -> str | None:
        """Find the first column whose name contains any of the keywords."""
        for col in df.columns:
            col_lower = col.lower()
            if any(kw in col_lower for kw in keywords):
                return col
        return None

    # ------------------------------------------------------------------
    # Download instructions
    # ------------------------------------------------------------------

    def _print_download_instructions(self, slug: str, area: dict):
        """Print detailed instructions for downloading census data."""
        self.logger.info(f"""
{'='*60}
HOW TO DOWNLOAD ONS CENSUS DATA
{'='*60}

Option A: Download a pre-merged CSV (easiest)
  1. Save a CSV with these columns to:
     {self.raw_dir / f'{slug}_demographics.csv'}

  Columns: lsoa_code, lsoa_name, total_population, population_density,
  age_18_24_pct, age_25_34_pct, age_35_49_pct, age_50_64_pct,
  age_65_plus_pct, median_household_income, ethnicity_white_pct,
  ethnicity_asian_pct, ethnicity_black_pct, ethnicity_mixed_pct,
  ethnicity_other_pct, economically_active_pct, employment_office_pct,
  household_single_pct, household_family_pct

Option B: Download individual tables from Nomis
  1. Go to https://www.nomisweb.co.uk/
  2. Navigate: Census 2021 > Topic Summaries
  3. For each table, select:
     - Geography: {area.get('local_authority', '')} > LSOA level
     - Download as CSV
  4. Save as:
     {self.raw_dir / f'{slug}_age.csv'}        (TS007a)
     {self.raw_dir / f'{slug}_ethnicity.csv'}   (TS021)
     {self.raw_dir / f'{slug}_economic.csv'}    (TS066)
     {self.raw_dir / f'{slug}_household.csv'}   (TS003)
     {self.raw_dir / f'{slug}_income.csv'}      (income estimates)
  5. Re-run this collector — it will merge them automatically.
{'='*60}
""")


if __name__ == "__main__":
    from config import TARGET_AREAS

    collector = ONSCensusCollector()
    results = collector.collect_all(TARGET_AREAS)

    total = sum(len(v) for v in results.values())
    print(f"\nDone. Loaded {total} LSOA demographic records.")