from pathlib import Path

import pandas as pd

# -------------------------------------------------------------------
# CONFIG
# -------------------------------------------------------------------

SOURCE_DIR = Path("raw/ons_downloads")      # where your downloaded national LSOA CSVs are
OUTPUT_DIR = Path("raw/ons_census")         # where your collector expects the split files

INPUT_FILES = {
    "age": "census2021-ts007a-lsoa.csv",
    "ethnicity": "census2021-ts021-lsoa.csv",
    "economic": "census2021-ts066-lsoa.csv",
    "household": "census2021-ts003-lsoa.csv",
    "density": "census2021-ts006-lsoa.csv",
}

AREAS = {
    "shoreditch": {
        "local_authority": "Tower Hamlets",
    },
    "peckham": {
        "local_authority": "Southwark",
    },
    "hackney": {
        "local_authority": "Hackney",
    },
}


# -------------------------------------------------------------------
# HELPERS
# -------------------------------------------------------------------

def normalise(text: str) -> str:
    return (
        str(text)
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


def normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [normalise(col) for col in df.columns]
    return df


def find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    cols = {col.lower(): col for col in df.columns}
    for candidate in candidates:
        candidate_norm = normalise(candidate)
        if candidate_norm in cols:
            return cols[candidate_norm]
    return None


def guess_local_authority_column(df: pd.DataFrame) -> str | None:
    candidates = [
        "local_authority_name",
        "local authority name",
        "lower_tier_local_authorities",
        "lower tier local authorities",
        "lad_name",
        "ladnm",
        "local_authority",
        "local authority",
        "local_authority_district",
        "local authority district",
        "county_or_unitary_authority",
        "parent_local_authority",
    ]
    exact = find_column(df, candidates)
    if exact:
        return exact

    keywords = [
        "local_authority",
        "localauthority",
        "lower_tier_local",
        "lad",
    ]
    for col in df.columns:
        col_norm = normalise(col)
        if any(keyword in col_norm for keyword in keywords):
            return col
    return None


def filter_area_rows(df: pd.DataFrame, local_authority: str) -> pd.DataFrame:
    la_col = guess_local_authority_column(df)
    if la_col:
        mask = df[la_col].astype(str).str.contains(local_authority, case=False, na=False)
        return df.loc[mask].copy()

    # Fallback: try geography name column
    geography_col = find_column(df, ["geography", "lsoa_name", "area_name"])
    if geography_col:
        mask = df[geography_col].astype(str).str.contains(local_authority, case=False, na=False)
        if mask.any():
            return df.loc[mask].copy()

    raise ValueError(
        f"Could not identify a local authority column, and no rows matched '{local_authority}' "
        f"via geography name. Available columns: {list(df.columns)}"
    )


# -------------------------------------------------------------------
# MAIN
# -------------------------------------------------------------------

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for dataset_name, filename in INPUT_FILES.items():
        source_path = SOURCE_DIR / filename

        if not source_path.exists():
            print(f"[WARN] Missing input file: {source_path}")
            continue

        print(f"\nProcessing {dataset_name}: {source_path}")
        df = pd.read_csv(source_path)
        df = normalise_columns(df)

        for slug, area in AREAS.items():
            try:
                area_df = filter_area_rows(df, area["local_authority"])
            except ValueError as exc:
                print(f"[ERROR] {slug} / {dataset_name}: {exc}")
                continue

            output_path = OUTPUT_DIR / f"{slug}_{dataset_name}.csv"
            area_df.to_csv(output_path, index=False)
            print(f"  Saved {len(area_df):,} rows -> {output_path}")


if __name__ == "__main__":
    main()