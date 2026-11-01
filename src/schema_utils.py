"""Load the Desirable Cities lexicon and validate sentence annotations.

Files:
    schema/lexicon_v0.yaml           keywords per category (thesis + extensions)
    schema/annotation_schema_v1.json  JSON Schema of one annotated sentence

Usage:
    python src/schema_utils.py                       # summary of the lexicon
    python src/schema_utils.py path/to/records.json  # validate a list of records

A record is valid when it passes the JSON Schema AND the consistency checks
of `check_consistency` (evidence copied from the sentence, PID cells built from
labels that are present, tags that exist in the lexicon).
"""
import json
import re
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
LEXICON_PATH = ROOT / "schema" / "lexicon_v0.yaml"
SCHEMA_PATH = ROOT / "schema" / "annotation_schema_v1.json"

ENVIRONMENTS = ("natural", "cultural", "constructural")
RESPONSES = ("emotion", "action", "reflection")


def slug(text: str) -> str:
    """'square/plaza' -> 'square_plaza', 'stars-full' -> 'stars_full'."""
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def load_lexicon(path: Path = LEXICON_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_schema(path: Path = SCHEMA_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def iter_terms(lexicon: dict):
    """Yield one dict per term: category, subcategory, tag, en, fr, status.

    The tag is the Koinos-style id <category>.<subcategory>.<term>, used in the
    `tags` field of an annotation."""
    for group in ("environments", "responses"):
        for category, cat in lexicon[group].items():
            for sub in cat["subcategories"]:
                for term in sub["terms"]:
                    yield {
                        "category": category,
                        "subcategory": sub["id"],
                        "tag": f"{category}.{sub['id']}.{slug(term['en'])}",
                        "en": term["en"],
                        "fr": term.get("fr", []),
                        "status": term.get("status", sub["status"]),
                        "source": sub["source"],
                    }


def valid_tags(lexicon: dict) -> set:
    """All tags a record may use: <cat>.<sub> and <cat>.<sub>.<term>."""
    tags = set()
    for t in iter_terms(lexicon):
        tags.add(t["tag"])
        tags.add(f"{t['category']}.{t['subcategory']}")
    return tags


def check_consistency(record: dict, tags: set) -> list:
    """Checks the JSON Schema cannot express. Returns a list of error messages."""
    errors = []
    text = record["text"]
    envs = {e["category"] for e in record["environments"]}
    resps = {r["category"] for r in record["responses"]}

    for label in record["environments"] + record["responses"]:
        if label["evidence"] not in text:
            errors.append(f"evidence not found in text: {label['evidence']!r}")
        for tag in label.get("tags", []):
            if tag not in tags:
                errors.append(f"unknown tag: {tag}")
            elif tag.split(".")[0] != label["category"]:
                errors.append(f"tag {tag} does not belong to category {label['category']}")

    for cell in record["pid_cells"]:
        if cell["environment"] not in envs:
            errors.append(f"PID cell uses absent environment: {cell['environment']}")
        if cell["response"] not in resps:
            errors.append(f"PID cell uses absent response: {cell['response']}")
    if envs and resps and not record["pid_cells"]:
        errors.append("environments and responses present but no PID cell")
    return errors


def validate_records(records: list, schema: dict = None, lexicon: dict = None) -> dict:
    """Return {sentence_id: [errors]} for invalid records (empty dict = all valid)."""
    schema = schema or load_schema()
    tags = valid_tags(lexicon or load_lexicon())
    validator = Draft202012Validator(schema)
    report = {}
    for i, rec in enumerate(records):
        key = rec.get("sentence_id", f"#{i}") if isinstance(rec, dict) else f"#{i}"
        errs = [f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}"
                for e in validator.iter_errors(rec)]
        if not errs:
            errs = check_consistency(rec, tags)
        if errs:
            report[key] = errs
    return report


def summary(lexicon: dict) -> str:
    """Number of terms per category and status (for the README and the report)."""
    counts = {}
    for t in iter_terms(lexicon):
        key = (t["category"], t["status"])
        counts[key] = counts.get(key, 0) + 1
    lines = [f"Lexicon {lexicon['version']}"]
    for cat in ENVIRONMENTS + RESPONSES:
        parts = [f"{s}={n}" for (c, s), n in sorted(counts.items()) if c == cat]
        lines.append(f"  {cat:<14} " + ", ".join(parts))
    return "\n".join(lines)


def main() -> None:
    lexicon = load_lexicon()
    Draft202012Validator.check_schema(load_schema())
    if len(sys.argv) < 2:
        print(summary(lexicon))
        return
    records = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    report = validate_records(records, lexicon=lexicon)
    for key, errs in report.items():
        print(key)
        for e in errs:
            print("   ", e)
    print(f"{len(records) - len(report)}/{len(records)} records valid")
    sys.exit(1 if report else 0)


if __name__ == "__main__":
    main()
