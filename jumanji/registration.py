# Copyright 2022 InstaDeep Ltd. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import importlib
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from jumanji.env import Environment

ENV_NAME_RE = re.compile(r"^(?:(?P<name>[\w:.-]+?))(?:-v(?P<version>\d+))?$")


def parse_env_id(id: str) -> Tuple[str, int]:
    """Parse an environment name.

    The format must obey the following structure: {env-name}-v{version-number}.

    Args:
        id: The environment ID to parse.

    Returns:
        A tuple of environment name and version number.

    Raises:
        ValueError: If the environment name does not a valid environment regex.
    """
    match = ENV_NAME_RE.fullmatch(id)
    if not match:
        raise ValueError(
            f"Malformed environment name: {id}."
            f"All ID's must be of the form (env-name)[-v(version-number)]."
        )

    name, version = match.group("name", "version")

    # default the version to zero if not provided
    version = int(version) if version is not None else 0

    return name, version


def get_env_id(name: str, version: Optional[int] = None) -> str:
    """Get the full env ID given a name and (optional) version.

    Args:
        name: The environment name.
        version: The environment version.

    Returns:
        The environment ID.
    """
    version = version or 0
    full_name = name + f"-v{version}"

    return full_name


@dataclass
class EnvSpec:
    id: str
    entry_point: str

    # Environment arguments
    kwargs: dict = field(default_factory=dict)

    # Environment specs
    name: str = field(init=False)
    version: int = field(init=False)

    def __post_init__(self) -> None:
        self.name, self.version = parse_env_id(self.id)


_REGISTRY: Dict[str, EnvSpec] = {}


def _check_registration_is_allowed(spec: EnvSpec) -> None:
    """Check if the environment spec can be registered.

    Args:
        spec: Environment spec

    Raises:
        ValueError: if an environment with the same ID is already registered.
        ValueError: if the previous version of the registered environment doesn't exist
        (except for v0).
    """
    global _REGISTRY

    # Try to overwrite a registered environment
    if spec.id in _REGISTRY:
        raise ValueError(f"Trying to override the registered environment {spec.id}.")

    # Verify that version v-1 exist when trying to register version v (except 0)
    latest_version = max(
        (_spec.version for _spec in _REGISTRY.values() if _spec.name == spec.name),
        default=None,  # if no version of the environment is registered
    )

    if (latest_version is None) and spec.version != 0:
        raise ValueError(
            f"The first version of an unregistered environment must be 0, got {spec.version}"
        )


def register(
    id: str,
    entry_point: str,
    **kwargs: Dict,
) -> None:
    """Register an environment.

    Args:
        id: environment ID, formatted as `(env_name)[-v(version)]`.
        entry_point: module and class constructor for the environment.
        **kwargs: extra arguments that will be passed to the environment constructor at
            instantiation.
    """
    global _REGISTRY

    # check the name respects the format
    env_name, version = parse_env_id(id)

    # build the environment spec
    env_id = get_env_id(env_name, version)
    spec = EnvSpec(
        id=env_id,
        entry_point=entry_point,
        **kwargs,
    )

    _check_registration_is_allowed(spec)

    # add it to the registry
    _REGISTRY[env_id] = spec


def load(name: str) -> Callable:
    """Loads an environment with name and returns an environment creation function

    Args:
        name: The environment name

    Returns:
        the environment constructor
    """
    mod_name, attr_name = name.split(":")
    mod = importlib.import_module(mod_name)
    fn = getattr(mod, attr_name)

    return fn  # type: ignore


def make(id: str, *args: Any, **kwargs: Any) -> Environment:
    env_name, version = parse_env_id(id)
    env_id = get_env_id(env_name, version)

    if env_id not in _REGISTRY:
        registered_envs = "\n".join(("- " + name for name in _REGISTRY))
        raise ValueError(
            f"Unregistered environment {env_id}. "
            f"Please select from the registered environments: \n{registered_envs}."
        )

    env_spec = _REGISTRY[env_id]

    # Overwrite the constructor arguments
    env_fn_kwargs = env_spec.kwargs.copy()
    env_fn_kwargs.update(kwargs)

    env_fn: Callable[..., Environment] = load(env_spec.entry_point)

    return env_fn(*args, **env_fn_kwargs)


def registered_environments() -> List[str]:
    return list(_REGISTRY.keys())
