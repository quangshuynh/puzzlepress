"""Restricted safe YAML decoding and normalized serialization."""

import re
from collections.abc import Hashable
from typing import Any

import yaml
from yaml.events import AliasEvent
from yaml.nodes import MappingNode, Node

from .models import Project
from .validation import ProjectError, ValidationIssue, validate_project


class _ProjectLoader(yaml.SafeLoader):
    # Do not mutate PyYAML's process-global resolver registry. Date-like strings
    # stay strings; yes/no/on/off are valid authored text, not boolean values.
    yaml_implicit_resolvers = {
        key: [
            (tag, regex)
            for tag, regex in resolvers
            if tag
            not in {
                "tag:yaml.org,2002:timestamp",
                "tag:yaml.org,2002:bool",
                "tag:yaml.org,2002:int",
            }
        ]
        for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
    }

    def compose_node(self, parent: Node | None, index: Any) -> Node | None:
        if self.check_event(AliasEvent):
            raise yaml.MarkedYAMLError(
                problem="YAML aliases are not supported.",
                problem_mark=self.current_event.start_mark,
            )
        if getattr(self.current_event, "tag", None) is not None:
            raise yaml.MarkedYAMLError(
                problem="Explicit YAML tags are not supported.",
                problem_mark=self.current_event.start_mark,
            )
        return super().compose_node(parent, index)

    def construct_mapping(self, node: MappingNode, deep: bool = False) -> dict[Hashable, Any]:
        if not isinstance(node, MappingNode):
            raise yaml.MarkedYAMLError(problem="Expected a YAML mapping.")
        result: dict[Hashable, Any] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise yaml.MarkedYAMLError(
                    problem="Mapping keys must be strings.", problem_mark=key_node.start_mark
                )
            if key in result:
                raise yaml.MarkedYAMLError(
                    problem=f"Duplicate mapping key: {key}.", problem_mark=key_node.start_mark
                )
            result[key] = self.construct_object(value_node, deep=deep)
        return result


_ProjectLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool", re.compile(r"^(?:true|false)$"), list("tf")
)
_ProjectLoader.add_implicit_resolver(
    "tag:yaml.org,2002:int", re.compile(r"^-?(?:0|[1-9][0-9]*)$"), list("-0123456789")
)


def load_yaml(source: str) -> object:
    """Decode one restricted YAML document (no aliases, tags or duplicate keys).

    Shared by project and planning sources; raises ProjectError on malformed YAML.
    """
    try:
        return yaml.load(source, Loader=_ProjectLoader)
    except (yaml.YAMLError, RecursionError, ValueError) as error:
        mark = getattr(error, "problem_mark", None)
        message = getattr(error, "problem", None) or "Malformed or excessively nested YAML."
        raise ProjectError(
            (
                ValidationIssue(
                    "source",
                    "yaml",
                    message,
                    mark.line + 1 if mark else None,
                    mark.column + 1 if mark else None,
                ),
            )
        ) from error


def parse_project(source: str) -> Project:
    """Decode and validate one YAML document; return immutable normalized values."""
    return validate_project(load_yaml(source)).require_project()


def dump_project(project: Project) -> str:
    """Serialize normalized values, without writing files or preserving comments."""
    return yaml.safe_dump(project.to_dict(), allow_unicode=True, sort_keys=True)
