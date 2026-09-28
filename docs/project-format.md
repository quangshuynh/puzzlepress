# Project format and identity

## Schema v1

The example at [`books/automotive/book.yaml`](../books/automotive/book.yaml) contains
three authored items, not generated puzzles:

```yaml
schema_version: 1
book:
  id: automotive-word-search
  title: Automotive Word Search
  language: en-US
build:
  seed: 2026
content:
  items:
    - ENGINE
    - CLUTCH
    - PISTON
output:
  directory: ../../build/automotive-word-search
```

| Field | Contract |
| --- | --- |
| `schema_version` | Required integer `1`; unsupported versions fail before interpreting version-specific fields. |
| `book.id` | Required stable identifier: lowercase ASCII letters/digits separated by hyphens; Windows device names are rejected. |
| `book.title` | Required nonempty string. |
| `book.language` | Required language tag such as `en` or `en-US`; basic syntax check, not a language registry lookup. |
| `book.subtitle`, `description`, `author`, `imprint` | Optional nonempty strings or null, under `book`. |
| `build.seed` | Required unsigned 64-bit integer (`0` through `18446744073709551615`) or decimal digit string. |
| `content.items` | Ordered nonempty strings; omitted content/items defaults to an empty list. Duplicates and order are preserved. No puzzle-specific rules apply. |
| `output.directory` | Relative path from the resolved YAML file's directory; defaults to `../build/<book.id>`. |

Unknown fields are errors, including nested typos. Text is trimmed at its edges;
internal whitespace, case, and Unicode normalization form are preserved. Omitted
optional book fields normalize to null. Quote numeric-looking titles/items.

Seeds such as `42`, `"42"`, and `" 00042 "` normalize to the same integer.
Booleans, floats, negative values, signs in strings, hex strings, arbitrary text,
and out-of-range values are rejected. No random or clock-derived default exists.

Source is one UTF-8 YAML document (an optional BOM is accepted). Duplicate keys,
aliases, merge keys, and explicit tags are rejected. Date-like values and
`yes`/`no`/`on`/`off` stay strings; lowercase `true`/`false` are booleans. Decimal
integers have no implicit octal/hex conversion. Serialization emits normalized
YAML; comments and source formatting are not preserved.

### Filesystem boundaries

Pass either a source file or a directory containing exactly `book.yaml`. Loading
does not search parent directories, enumerate content, or depend on filesystem
ordering. Input paths may be absolute or relative to the caller's working directory.

Each book directory is authoritative source. Generated artifacts belong in a
separate tree, normally repository-root `build/<book.id>/` as in the example.
Output paths use forward slashes, including on Windows. Absolute paths, drive
paths, backslashes, and invalid path characters are rejected. Relative `..`
components are intentional: they allow output outside the book source tree.

Loading resolves symlinks and rejects output that is inside, equal to, or an
ancestor of the source directory. Existing output files are rejected. Nothing
creates or deletes output directories in this interval. Future writers must
recheck separation when writing, prevent collisions with other projects, and
never place authoritative data in build directories. `build/`, environments,
test caches, and packaging artifacts are ignored by Git.

## Build identity

`canonical_build_inputs` returns UTF-8 JSON with sorted keys, compact separators,
and an envelope containing identity format version `1`, engine version `0.1.0`,
and the normalized schema/book/build/content values. SHA-256 produces an identity
formatted as `pp1-sha256-<64 hex characters>`.

- Book metadata, seed, content order, and content values affect identity.
- YAML comments, mapping order, formatting, equivalent seeds, and omitted versus
  explicit defaults do not affect identity.
- Source paths, output location, timestamps, environment variables, and process
  hash randomization are excluded.
- Engine version changes intentionally invalidate identities. Identity-format
  changes require a new identity version; schema changes require explicit dispatch.

Only inline source content is supported. Future external content/assets must be
included by content digest before they influence generation. The current identity
is a fingerprint of declared inputs, not a guarantee of reproducible PDF bytes
or a complete release-environment manifest.

This is a toolchain/build-input identity because it includes the engine version.
It is not a source-only fingerprint. Standalone puzzle configuration is outside
this contract. A later interval may separate source and build fingerprints;
Interval 2 keeps the existing identity contract and regression value unchanged.
