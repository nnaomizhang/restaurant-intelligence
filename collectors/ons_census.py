"""
ONS Census Data Collector
=========================
Loads and merges demographic data from Nomis Census 2021 at LSOA level.

Data source:
https://www.nomisweb.co.uk/ (Census 2021)

Required downloads from Nomis (Census 2021, LSOA level):
  - TS007A: Age by five-year age bands
  - TS021:  Ethnic group
  - TS066:  Economic activity status
  - TS003:  Household composition
  - TS006:  Population density

This collector can:
  1. Load pre-downloaded CSV files and merge them
  2. Load a pre-merged single CSV with all columns
  3. Fall back to manual JSON data
"""

from pathlib import Path

import pandas as pd

from config import RAW_DIR
from collectors.base import BaseCollector


class ONSCensusCollector(BaseCollector):
    VERSION = "1.1"

    EXPECTED_COLUMNS = [
        "lsoa_code",
        "lsoa_name",
        "total_population",
        "population_density",
        "age_18_24_pct",
        "age_25_34_pct",
        "age_35_49_pct",
        "age_50_64_pct",
        "age_65_plus_pct",
        "ethnicity_white_pct",
        "ethnicity_asian_pct",
        "ethnicity_black_pct",
        "ethnicity_mixed_pct",
        "ethnicity_other_pct",
        "economically_active_pct",
        "household_single_pct",
        "household_family_pct",
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

        Tries in order:
          1. Pre-merged CSV ({area}_demographics.csv)
          2. Individual census table CSVs to merge
          3. Manual JSON fallback
        """
        area_name = area["name"]
        slug = area_name.lower().replace(" ", "_").replace("-", "_")

        self.logger.info(f"Loading ONS data for {area_name}")

        # Option 1: pre-merged CSV
        merged_path = self.raw_dir / f"{slug}_demographics.csv"
        if merged_path.exists():
            records = self._load_merged_csv(merged_path, area_name)
            if records:
                self.save_raw(records, area_name)
                return records

        # Option 2: merge individual census table CSVs
        individual_files = {
            "age": self.raw_dir / f"{slug}_age.csv",
            "ethnicity": self.raw_dir / f"{slug}_ethnicity.csv",
            "economic": self.raw_dir / f"{slug}_economic.csv",
            "household": self.raw_dir / f"{slug}_household.csv",
            "density": self.raw_dir / f"{slug}_density.csv",
        }

        if any(path.exists() for path in individual_files.values()):
            records = self._merge_census_tables(individual_files, area_name)
            if records:
                self.save_raw(records, area_name)
                return records

        # Option 3: manual JSON
        records = self.load_manual_data(area_name)
        if records:
            self.save_raw(records, area_name)
            return records

        self.logger.warning(f"No ONS data found for {area_name}")
        self._print_download_instructions(slug, area)
        return []

    # ------------------------------------------------------------------
    # Loading pre-merged data
    # ------------------------------------------------------------------

    def _load_merged_csv(self, path: Path, area_name: str) -> list[dict]:
        """Load a pre-merged demographics CSV."""
        self.logger.info(f"Loading merged CSV: {path}")

        try:
            df = pd.read_csv(path)
        except Exception as exc:
            self.logger.error(f"Failed to read {path}: {exc}")
            return []

        df.columns = [self._normalise_column_name(c) for c in df.columns]

        missing = [c for c in ["lsoa_code", "lsoa_name"] if c not in df.columns]
        if missing:
            self.logger.error(
                f"Missing required columns: {missing}. "
                f"Available: {list(df.columns)}"
            )
            return []

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
        Merge multiple census table CSVs into one dataset.
        Each file is standardised and joined on LSOA code.
        """
        self.logger.info("Merging individual census table CSVs...")
        merged: pd.DataFrame | None = None

        processors = [
            ("age", self._process_age_data),
            ("ethnicity", self._process_ethnicity_data),
            ("economic", self._process_economic_data),
            ("household", self._process_household_data),
            ("density", self._process_density_data),
        ]

        for key, processor in processors:
            path = files[key]
            if not path.exists():
                continue

            self.logger.info(f"  Processing {key} data: {path}")
            df_part = processor(path)

            if df_part is None or df_part.empty:
                continue

            if merged is None:
                merged = df_part
            else:
                merged = merged.merge(
                    df_part,
                    on="lsoa_code",
                    how="outer",
                    suffixes=("", "_dup"),
                )

                # Prefer the first non-null lsoa_name if duplicates appear
                if "lsoa_name_dup" in merged.columns:
                    if "lsoa_name" not in merged.columns:
                        merged["lsoa_name"] = merged["lsoa_name_dup"]
                    else:
                        merged["lsoa_name"] = merged["lsoa_name"].fillna(
                            merged["lsoa_name_dup"]
                        )
                    merged = merged.drop(columns=["lsoa_name_dup"])

        if merged is None or merged.empty:
            return []

        merged["neighbourhood"] = area_name

        slug = area_name.lower().replace(" ", "_").replace("-", "_")
        merged_path = self.raw_dir / f"{slug}_demographics.csv"
        merged.to_csv(merged_path, index=False)

        self.logger.info(f"Saved merged CSV to {merged_path}")

        records = merged.to_dict(orient="records")
        self.logger.info(f"Merged {len(records)} LSOAs from individual tables")
        return records

    # ------------------------------------------------------------------
    # Individual processors
    # ------------------------------------------------------------------

    def _process_age_data(self, path: Path) -> pd.DataFrame:
        df = pd.read_csv(path)

        result = pd.DataFrame()
        result["lsoa_code"] = df["geography_code"]
        result["lsoa_name"] = df["geography"]
        result["total_population"] = pd.to_numeric(df["age_total"], errors="coerce")

        total = result["total_population"]

        age_brackets = {
            "age_18_24_pct": ["age_aged_15_to_19_years", "age_aged_20_to_24_years"],
            "age_25_34_pct": ["age_aged_25_to_29_years", "age_aged_30_to_34_years"],
            "age_35_49_pct": ["age_aged_35_to_39_years", "age_aged_40_to_44_years", "age_aged_45_to_49_years"],
            "age_50_64_pct": ["age_aged_50_to_54_years", "age_aged_55_to_59_years", "age_aged_60_to_64_years"],
            "age_65_plus_pct": ["age_aged_65_to_69_years", "age_aged_70_to_74_years", "age_aged_75_to_79_years", "age_aged_80_to_84_years", "age_aged_85_years_and_over"],
        }

        for bracket_name, cols in age_brackets.items():
            bracket_sum = sum(
                pd.to_numeric(df[c], errors="coerce").fillna(0)
                for c in cols if c in df.columns
            )
            result[bracket_name] = (bracket_sum / total.where(total != 0) * 100).round(1)

        return result

    def _process_ethnicity_data(self, path: Path) -> pd.DataFrame:
        """Process Nomis ethnicity table TS021."""
        df = pd.read_csv(path)
        df.columns = [self._normalise_column_name(c) for c in df.columns]

        code_col = self._find_column(
            df, ["geography_code", "lsoa_code", "area_code"]
        )
        name_col = self._find_column(
            df, ["geography", "lsoa_name", "area_name"]
        )

        if not code_col:
            self.logger.warning("Cannot find LSOA code column in ethnicity data")
            return pd.DataFrame()

        result = pd.DataFrame()
        result["lsoa_code"] = df[code_col]

        if name_col:
            result["lsoa_name"] = df[name_col]

        total_col = self._find_column(df, ["total", "all_persons"])
        total = (
            pd.to_numeric(df[total_col], errors="coerce")
            if total_col
            else pd.Series(1, index=df.index)
        )

        ethnicity_map = {
            "ethnicity_white_pct": ["white"],
            "ethnicity_asian_pct": ["asian", "asian_asian_british_or_asian_welsh"],
            "ethnicity_black_pct": ["black", "black_black_british_black_welsh_caribbean_or_african"],
            "ethnicity_mixed_pct": ["mixed", "multiple_ethnic_groups"],
            "ethnicity_other_pct": ["other_ethnic_group", "other"],
        }

        for out_col, keywords in ethnicity_map.items():
            source_col = self._find_column_containing(df, keywords)
            if source_col:
                vals = pd.to_numeric(df[source_col], errors="coerce").fillna(0)
                result[out_col] = (vals / total.where(total != 0) * 100).round(1)

        return result

    def _process_economic_data(self, path: Path) -> pd.DataFrame:
        df = pd.read_csv(path)

        result = pd.DataFrame()
        result["lsoa_code"] = df["geography_code"]

        total_col = "economic_activity_status_total_all_usual_residents_aged_16_years_and_over"
        active_col = "economic_activity_status_economically_active_excluding_full_time_students"

        if total_col in df.columns and active_col in df.columns:
            total = pd.to_numeric(df[total_col], errors="coerce")
            active = pd.to_numeric(df[active_col], errors="coerce").fillna(0)
            result["economically_active_pct"] = (active / total.where(total != 0) * 100).round(1)

        return result

    def _process_household_data(self, path: Path) -> pd.DataFrame:
        df = pd.read_csv(path)

        result = pd.DataFrame()
        result["lsoa_code"] = df["geography_code"]

        total_col = "household_composition_total;_measures_value"
        single_col = "household_composition_one_person_household;_measures_value"
        family_col = "household_composition_single_family_household;_measures_value"

        if total_col in df.columns:
            total = pd.to_numeric(df[total_col], errors="coerce")

            if single_col in df.columns:
                single = pd.to_numeric(df[single_col], errors="coerce").fillna(0)
                result["household_single_pct"] = (single / total.where(total != 0) * 100).round(1)

            if family_col in df.columns:
                family = pd.to_numeric(df[family_col], errors="coerce").fillna(0)
                result["household_family_pct"] = (family / total.where(total != 0) * 100).round(1)

        return result

    def _process_density_data(self, path: Path) -> pd.DataFrame:
        """Process Nomis population density table TS006."""
        df = pd.read_csv(path)
        df.columns = [self._normalise_column_name(c) for c in df.columns]

        code_col = self._find_column(
            df, ["geography_code", "lsoa_code", "area_code"]
        )
        name_col = self._find_column(
            df, ["geography", "lsoa_name", "area_name"]
        )

        if not code_col:
            self.logger.warning("Cannot find LSOA code column in density data")
            return pd.DataFrame()

        result = pd.DataFrame()
        result["lsoa_code"] = df[code_col]

        if name_col:
            result["lsoa_name"] = df[name_col]

        density_col = self._find_column_containing(
            df, ["population_density", "density"]
        )

        if not density_col:
            self.logger.warning("Cannot find population density column in density data")
            return result

        result["population_density"] = pd.to_numeric(
            df[density_col], errors="coerce"
        )

        return result

    # ------------------------------------------------------------------
    # Column helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_column_name(name: str) -> str:
        """Normalise CSV column names for flexible matching."""
        return (
            str(name)
            .strip()
            .lower()
            .replace(":", "")
            .replace(",", "")
            .replace("(", "")
            .replace(")", "")
            .replace("/", "_")
            .replace("-", "_")
            .replace(" ", "_")
        )

    @staticmethod
    def _find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
        """Find first exact matching normalised column."""
        cols = {c.lower(): c for c in df.columns}
        for candidate in candidates:
            if candidate.lower() in cols:
                return cols[candidate.lower()]
        return None

    @staticmethod
    def _find_column_containing(
        df: pd.DataFrame, keywords: list[str]
    ) -> str | None:
        """Find first column containing any keyword."""
        for col in df.columns:
            col_lower = col.lower()
            if any(keyword.lower() in col_lower for keyword in keywords):
                return col
        return None

    # ------------------------------------------------------------------
    # Download instructions
    # ------------------------------------------------------------------

    def _print_download_instructions(self, slug: str, area: dict):
        """Print instructions for downloading census data."""
        self.logger.info(
            f"""
{'=' * 60}
HOW TO DOWNLOAD ONS CENSUS DATA
{'=' * 60}

Option A: Use a pre-merged CSV
  Save a CSV with these columns to:
    {self.raw_dir / f'{slug}_demographics.csv'}

  Columns:
    lsoa_code, lsoa_name, total_population, population_density,
    age_18_24_pct, age_25_34_pct, age_35_49_pct, age_50_64_pct,
    age_65_plus_pct, ethnicity_white_pct, ethnicity_asian_pct,
    ethnicity_black_pct, ethnicity_mixed_pct, ethnicity_other_pct,
    economically_active_pct, household_single_pct,
    household_family_pct

Option B: Download and save individual Nomis tables at LSOA level
  1. Go to https://www.nomisweb.co.uk/
  2. Use Census 2021 bulk or topic summary downloads
  3. Download these LSOA-level files:
       - TS007A (age by five-year age bands)
       - TS021  (ethnic group)
       - TS066  (economic activity status)
       - TS003  (household composition)
       - TS006  (population density)
  4. Save them as:
     {self.raw_dir / f'{slug}_age.csv'}
     {self.raw_dir / f'{slug}_ethnicity.csv'}
     {self.raw_dir / f'{slug}_economic.csv'}
     {self.raw_dir / f'{slug}_household.csv'}
     {self.raw_dir / f'{slug}_density.csv'}
  5. Re-run this collector — it will merge them automatically.

Target local authority:
  {area.get('local_authority', '')}

{'=' * 60}
"""
        )


if __name__ == "__main__":
    from config import TARGET_AREAS

    collector = ONSCensusCollector()
    results = collector.collect_all(TARGET_AREAS)

    total = sum(len(records) for records in results.values())
    print(f"\nDone. Loaded {total} LSOA demographic records.")