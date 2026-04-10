import sys
sys.path.append('/Users/naomi/restaurant-intelligence')

from ingestion.fsa import parse_fsa_xml

def test_returns_results():
    results = parse_fsa_xml('data/raw/hackney.xml', 'Hackney')
    assert len(results) > 0

def test_has_name():
    results = parse_fsa_xml('data/raw/hackney.xml', 'Hackney')
    assert results[0]["name"] is not None

def test_has_hygiene_rating():
    results = parse_fsa_xml('data/raw/hackney.xml', 'Hackney')
    assert results[0]["hygiene_rating"] is not None

def test_valid_business_types_only():
    results = parse_fsa_xml('data/raw/hackney.xml', 'Hackney')
    valid = ["Restaurant/Cafe/Canteen", "Takeaway/sandwich shop"]
    assert all(r["business_type"] in valid for r in results)

def test_lineage_exists():
    results = parse_fsa_xml('data/raw/hackney.xml', 'Hackney')
    assert "lineage" in results[0]

def test_lineage_source():
    results = parse_fsa_xml('data/raw/hackney.xml', 'Hackney')
    assert results[0]["lineage"]["source_name"] == "fsa"