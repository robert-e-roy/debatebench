"""A stricter PyYAML loader for config files (ADR-008).

``yaml.safe_load`` follows YAML 1.1, which quietly coerces values: ``no`` loads
as False, ``042`` as 34, ``1:30`` as 90, and a repeated key keeps only its last
value. Each of those turns a config mistake into a wrong run rather than an
error. This loader differs from SafeLoader in three ways:

- only true/false (in YAML's case variants) are booleans, so yes/no/on/off
  stay strings;
- integers must be plain decimal: leading zeros, hex, binary, base 60 and
  underscores are rejected rather than converted;
- a key repeated within one mapping is an error.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from yaml.constructor import ConstructorError

_BOOL_TAG = "tag:yaml.org,2002:bool"
_INT_TAG = "tag:yaml.org,2002:int"
_MERGE_TAG = "tag:yaml.org,2002:merge"
_PLAIN_DECIMAL = re.compile(r"[-+]?(?:0|[1-9][0-9]*)")


class StrictLoader(yaml.SafeLoader):
    def construct_strict_int(self, node: yaml.ScalarNode) -> int:
        text = self.construct_scalar(node)
        if not _PLAIN_DECIMAL.fullmatch(text):
            yaml11 = yaml.SafeLoader.construct_yaml_int(self, node)
            raise ConstructorError(
                None,
                None,
                f"{text!r} is not a plain decimal integer (YAML 1.1 would read it as {yaml11}); "
                "write it in plain decimal, or quote it if it's meant as text",
                node.start_mark,
            )
        return int(text)

    def construct_mapping(self, node: yaml.Node, deep: bool = False) -> dict[Any, Any]:
        if isinstance(node, yaml.MappingNode):
            seen: set[Any] = set()
            for key_node, _ in node.value:
                if key_node.tag == _MERGE_TAG:
                    continue
                key = self.construct_object(key_node, deep=deep)
                try:
                    duplicate = key in seen
                except TypeError:  # unhashable; SafeLoader reports it below
                    continue
                if duplicate:
                    raise ConstructorError(
                        "while constructing a mapping",
                        node.start_mark,
                        f"found duplicate key {key!r}",
                        key_node.start_mark,
                    )
                seen.add(key)
        return super().construct_mapping(node, deep=deep)


# Copy SafeLoader's resolvers minus YAML 1.1's bool, so SafeLoader itself is untouched.
StrictLoader.yaml_implicit_resolvers = {
    first: [(tag, regexp) for tag, regexp in resolvers if tag != _BOOL_TAG]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
StrictLoader.add_implicit_resolver(
    _BOOL_TAG, re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF")
)
StrictLoader.add_constructor(_INT_TAG, StrictLoader.construct_strict_int)


def load_yaml(path: Path) -> Any:
    """Parse the single YAML document in ``path`` with StrictLoader."""
    with path.open("rb") as stream:
        return yaml.load(stream, Loader=StrictLoader)
