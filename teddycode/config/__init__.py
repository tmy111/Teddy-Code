"""项目级配置辅助函数。

这个模块负责把 CLI 参数、环境变量、TOML 配置和默认值合并成运行时可直接使用的
配置对象。最重要的优先级规则是：

CLI 参数 > 当前进程环境变量 > 项目/用户配置文件 > 旧版 .env > provider 默认值。
"""

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..features.sandbox import resolve_sandbox_config as resolve_sandbox_values

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - covered on Python 3.10 by dependency resolution
    import tomli as tomllib  # type: ignore[no-redef]


ENV_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
DEFAULT_PROVIDER = "openai"
DEFAULT_CONFIG_PATH = Path.home() / ".config" / "teddycode" / "config.toml"
PROJECT_CONFIG_NAME = ".teddycode.toml"


@dataclass(frozen=True)
class ProviderConfig:
    """已经解析好的 provider 配置，供模型客户端直接使用。"""

    name: str
    protocol: str
    api_key: str
    base_url: str
    model: str
    supports_vision: bool = False
    vision_provider: str = ""


PROVIDER_DEFAULTS: dict[str, dict[str, Any]] = {
    # 内置 profile 是最后兜底值：CLI、环境变量、配置文件都没给时才会用到。
    "openai": {
        "protocol": "openai",
        "base_url": "https://www.right.codes/codex/v1",
        "model": "gpt-5.5",
        "supports_vision": True,
    },
    "anthropic": {
        "protocol": "anthropic",
        "base_url": "https://www.right.codes/claude/v1",
        "model": "claude-sonnet-4-6",
        "supports_vision": True,
    },
    "deepseek": {
        "protocol": "anthropic",
        "base_url": "https://api.deepseek.com/anthropic",
        "model": "deepseek-v4-pro",
        "supports_vision": False,
        "vision_provider": "openai",
    },
}

PROVIDER_ALIASES = {
    # 命令行里的友好别名会先归一化，再进入 provider 查找流程。
    "gpt": "openai",
    "claude": "anthropic",
}

PROTOCOLS = {"openai", "anthropic"}

PROVIDER_MAX_TOKENS: dict[str, int] = {
    "openai": 8192,
    "anthropic": 32000,
    "deepseek": 8192,
}
DEFAULT_MAX_TOKENS_FALLBACK = 4096


def default_max_tokens_for_provider(provider: str | None) -> int:
    """返回某个 provider 默认允许生成的 token 数。"""

    if not provider:
        return DEFAULT_MAX_TOKENS_FALLBACK
    key = PROVIDER_ALIASES.get(provider, provider)
    return PROVIDER_MAX_TOKENS.get(key, DEFAULT_MAX_TOKENS_FALLBACK)

# TeddyCode 专属环境变量的优先级高于 provider 原生环境变量。
ENV_PROVIDER = "TEDDYCODE_PROVIDER"
ENV_API_KEY = "TEDDYCODE_API_KEY"
ENV_BASE_URL = "TEDDYCODE_BASE_URL"
ENV_MODEL = "TEDDYCODE_MODEL"
ENV_VISION_PROVIDER = "TEDDYCODE_VISION_PROVIDER"
ENV_VISION_API_KEY = "TEDDYCODE_VISION_API_KEY"
ENV_VISION_BASE_URL = "TEDDYCODE_VISION_API_BASE"
ENV_VISION_BASE_URL_ALT = "TEDDYCODE_VISION_BASE_URL"
ENV_VISION_MODEL = "TEDDYCODE_VISION_MODEL"
ENV_VISION_TIMEOUT = "TEDDYCODE_VISION_TIMEOUT"

PROVIDER_ENV_NAMES = {
    # provider 原生环境变量名：这样用户已有的 OpenAI/Anthropic/DeepSeek 配置
    # 不需要改成 TEDDYCODE_ 前缀也能被读取。
    "openai": {
        "api_key": ("OPENAI_API_KEY",),
        "base_url": ("OPENAI_API_BASE", "OPENAI_BASE_URL"),
        "model": ("OPENAI_MODEL",),
    },
    "anthropic": {
        "api_key": (
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_AUTH_TOKEN",
            "RIGHT_CODES_API_KEY",
            "OPENAI_API_KEY",
        ),
        "base_url": ("ANTHROPIC_API_BASE", "ANTHROPIC_BASE_URL"),
        "model": ("ANTHROPIC_MODEL",),
    },
    "deepseek": {
        "api_key": ("DEEPSEEK_API_KEY",),
        "base_url": ("DEEPSEEK_API_BASE", "DEEPSEEK_BASE_URL"),
        "model": ("DEEPSEEK_MODEL",),
    },
}

LEGACY_ENV_NAMES = {
    # 旧版环境变量名：只从 .env 里读取，用来兼容历史配置。
    # 它们在优先级上低于当前进程环境变量和 TOML 配置文件。
    "openai": {
        "api_key": ("TEDDYCODE_OPENAI_API_KEY", "OPENAI_API_KEY"),
        "base_url": ("TEDDYCODE_OPENAI_API_BASE", "OPENAI_API_BASE", "OPENAI_BASE_URL"),
        "model": ("TEDDYCODE_OPENAI_MODEL", "OPENAI_MODEL"),
    },
    "anthropic": {
        "api_key": (
            "TEDDYCODE_ANTHROPIC_API_KEY",
            "ANTHROPIC_API_KEY",
            "TEDDYCODE_RIGHT_CODES_API_KEY",
            "RIGHT_CODES_API_KEY",
            "TEDDYCODE_OPENAI_API_KEY",
            "OPENAI_API_KEY",
        ),
        "base_url": (
            "TEDDYCODE_ANTHROPIC_API_BASE",
            "ANTHROPIC_API_BASE",
            "ANTHROPIC_BASE_URL",
        ),
        "model": ("TEDDYCODE_ANTHROPIC_MODEL", "ANTHROPIC_MODEL"),
    },
    "deepseek": {
        "api_key": ("TEDDYCODE_DEEPSEEK_API_KEY", "DEEPSEEK_API_KEY"),
        "base_url": (
            "TEDDYCODE_DEEPSEEK_API_BASE",
            "DEEPSEEK_API_BASE",
            "DEEPSEEK_BASE_URL",
        ),
        "model": ("TEDDYCODE_DEEPSEEK_MODEL", "DEEPSEEK_MODEL"),
    },
}


def _strip_quotes(value):
    """去掉 .env 值两侧成对的简单引号。"""

    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _parse_env_line(line):
    """把 .env 中的一行解析成 (变量名, 变量值)。"""

    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("export "):
        line = line[len("export ") :].strip()
    if "=" not in line:
        raise ValueError(f"invalid .env line: {line}")
    name, value = line.split("=", 1)
    name = name.strip()
    if not ENV_KEY_PATTERN.match(name):
        raise ValueError(f"invalid .env variable name: {name}")
    return name, _strip_quotes(value)


def find_project_env(start):
    """从 start 开始向上查找最近的项目 .env 文件。"""

    current = Path(start).resolve()
    if current.is_file():
        current = current.parent
    for path in (current, *current.parents):
        env_path = path / ".env"
        if env_path.exists():
            return env_path
    return None


def find_project_config(start):
    """从 start 开始向上查找最近的 .teddycode.toml 文件。"""

    current = Path(start).resolve()
    if current.is_file():
        current = current.parent
    for path in (current, *current.parents):
        config_path = path / PROJECT_CONFIG_NAME
        if config_path.exists():
            return config_path
    return None


def load_project_env(start, override=True):
    """把项目 .env 加载到 os.environ，并返回本次解析出的变量。"""

    env_path = find_project_env(start)
    if env_path is None:
        return {}
    loaded = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        parsed = _parse_env_line(line)
        if parsed is None:
            continue
        name, value = parsed
        loaded[name] = value
        if override or name not in os.environ:
            os.environ[name] = value
    return loaded


def provider_env(name, legacy_names=(), default=""):
    """从一组候选环境变量名里返回第一个非空值。"""

    for env_name in (name, *legacy_names):
        value = os.environ.get(env_name)
        if value:
            return value
    return default


def resolve_provider_config(
    provider: str | None = None,
    *,
    start: str | Path = ".",
    config_path: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    vision_provider: str | None = None,
) -> ProviderConfig:
    """解析主文本模型使用的 provider profile。

    这里会同时兼容几代配置来源：CLI 直接覆盖、当前进程环境变量、TOML 配置文件、
    旧版 .env 名称。下面每个 _first_value 的参数顺序，就是实际优先级。
    """

    file_values = _load_config_values(start=start, explicit_path=config_path)
    legacy_env = _load_legacy_env_values(start)

    # 先确定 provider，再读取 provider 专属配置；因为环境变量名和默认值都依赖
    # 这个归一化后的 profile 名称。
    requested_provider = (
        provider
        or os.environ.get(ENV_PROVIDER)
        or file_values["top"].get("provider")
        or legacy_env.get(ENV_PROVIDER)
        or DEFAULT_PROVIDER
    )
    provider_name = normalize_provider_name(requested_provider)
    profile_values = _profile_values(file_values["providers"], provider_name)
    default_values = dict(PROVIDER_DEFAULTS.get(provider_name, {}))

    # protocol 决定使用哪个模型客户端适配器。比如 provider 名叫 deepseek，
    # 但它可以复用 Anthropic 协议格式。
    protocol = _first_value(
        None,
        os.environ.get("TEDDYCODE_PROTOCOL"),
        profile_values.get("protocol"),
        legacy_env.get("TEDDYCODE_PROTOCOL"),
        default_values.get("protocol"),
    )
    protocol = _validate_protocol(protocol, provider_name)

    env_values = _env_values(provider_name, protocol)
    legacy_values = _legacy_values(provider_name, protocol, legacy_env)

    # 每个字段单独解析，这样用户可以只覆盖 profile 的一部分，
    # 例如只改 model，或者只改 base_url。
    resolved_model = _first_value(
        model,
        os.environ.get(ENV_MODEL),
        env_values.get("model"),
        profile_values.get("model"),
        legacy_env.get(ENV_MODEL),
        legacy_values.get("model"),
        default_values.get("model"),
    )
    resolved_base_url = _first_value(
        base_url,
        os.environ.get(ENV_BASE_URL),
        env_values.get("base_url"),
        profile_values.get("base_url"),
        legacy_env.get(ENV_BASE_URL),
        legacy_values.get("base_url"),
        default_values.get("base_url"),
    )
    resolved_api_key = _first_value(
        api_key,
        os.environ.get(ENV_API_KEY),
        env_values.get("api_key"),
        profile_values.get("api_key"),
        legacy_env.get(ENV_API_KEY),
        legacy_values.get("api_key"),
        "",
    )
    supports_vision = _bool_value(
        _first_present(
            profile_values.get("supports_vision"),
            default_values.get("supports_vision"),
            False,
        )
    )
    resolved_vision_provider = _first_value(
        vision_provider,
        os.environ.get(ENV_VISION_PROVIDER),
        profile_values.get("vision_provider"),
        default_values.get("vision_provider"),
        "",
    )

    return ProviderConfig(
        name=provider_name,
        protocol=protocol,
        api_key=str(resolved_api_key or ""),
        base_url=str(resolved_base_url or ""),
        model=str(resolved_model or ""),
        supports_vision=supports_vision,
        vision_provider=normalize_provider_name(resolved_vision_provider) if resolved_vision_provider else "",
    )


def resolve_vision_provider_config(
    provider: str | None = None,
    *,
    start: str | Path = ".",
    config_path: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> ProviderConfig:
    """解析图片检查/视觉能力使用的 provider profile。

    视觉调用常常需要和主文本模型不同的 endpoint。比如项目可以用 DeepSeek 做普通
    工具规划，但把图片检查路由到一个支持视觉的 OpenAI-compatible endpoint。
    这些覆盖只作用于 vision client，不会影响主文本 profile。
    """

    legacy_env = _load_legacy_env_values(start)
    resolved_model = _first_value(
        model,
        os.environ.get(ENV_VISION_MODEL),
        legacy_env.get(ENV_VISION_MODEL),
    )
    resolved_base_url = _first_value(
        base_url,
        os.environ.get(ENV_VISION_BASE_URL),
        os.environ.get(ENV_VISION_BASE_URL_ALT),
        legacy_env.get(ENV_VISION_BASE_URL),
        legacy_env.get(ENV_VISION_BASE_URL_ALT),
    )
    resolved_api_key = _first_value(
        api_key,
        os.environ.get(ENV_VISION_API_KEY),
        legacy_env.get(ENV_VISION_API_KEY),
    )
    return resolve_provider_config(
        provider,
        start=start,
        config_path=config_path,
        model=resolved_model or None,
        base_url=resolved_base_url or None,
        api_key=resolved_api_key or None,
    )


def resolve_project_sandbox_config(
    *,
    start: str | Path = ".",
    config_path: str | None = None,
    mode: str | None = None,
    backend: str | None = None,
):
    """先从 TOML 解析沙箱配置，再用 CLI 参数覆盖 mode/backend。"""

    file_values = _load_config_values(start=start, explicit_path=config_path)
    values = {"sandbox": dict(file_values.get("sandbox", {}) or {})}
    if mode:
        values["sandbox"]["mode"] = mode
    if backend:
        values["sandbox"]["backend"] = backend
    return resolve_sandbox_values(values)


def normalize_provider_name(provider: str | None) -> str:
    """把空值和 provider 别名归一化成内部使用的 provider key。"""

    normalized = (provider or DEFAULT_PROVIDER).strip().lower()
    return PROVIDER_ALIASES.get(normalized, normalized)


def _load_config_values(start: str | Path, explicit_path: str | None) -> dict[str, Any]:
    """加载用户级/项目级 TOML，并归一化成内部的配置分组。"""

    values: dict[str, Any] = {"top": {}, "providers": {}, "sandbox": {}}
    if explicit_path:
        # 显式传入 config_path 时，只读取这个文件，不再叠加默认配置和项目配置。
        _merge_config_values(
            values, _read_config_file(Path(explicit_path).expanduser())
        )
        return values

    # 后读到的文件优先级更高：项目配置可以覆盖用户级默认配置。
    for path in (DEFAULT_CONFIG_PATH, find_project_config(start)):
        if path and path.exists():
            _merge_config_values(values, _read_config_file(path))
    return values


def _read_config_file(path: Path) -> dict[str, Any]:
    """读取 TOML，并把支持的 section 归一化成内部配置分组。"""

    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"invalid TeddyCode config file {path}: {exc}") from exc
    except OSError as exc:
        raise ValueError(f"could not read TeddyCode config file {path}: {exc}") from exc

    values: dict[str, Any] = {"top": {}, "providers": {}, "sandbox": {}}
    if "provider" in data:
        values["top"]["provider"] = data["provider"]

    providers = data.get("providers", {})
    if isinstance(providers, dict):
        for name, section in providers.items():
            if isinstance(section, dict):
                values["providers"][normalize_provider_name(str(name))] = dict(section)

    sandbox = data.get("sandbox", {})
    if isinstance(sandbox, dict):
        values["sandbox"] = dict(sandbox)

    for name in ("openai", "anthropic", "deepseek"):
        # 兼容旧写法：[openai]、[anthropic]、[deepseek] 顶层 section。
        # 新写法则是 [providers.<name>]。
        section = data.get(name, {})
        if isinstance(section, dict):
            values["providers"].setdefault(name, {}).update(section)
    return values


def _merge_config_values(target: dict[str, Any], incoming: dict[str, Any]) -> None:
    """合并归一化后的配置分组，incoming 的值优先级更高。"""

    target["top"].update(incoming.get("top", {}))
    target["sandbox"].update(incoming.get("sandbox", {}))
    for name, section in incoming.get("providers", {}).items():
        target["providers"].setdefault(name, {}).update(section)


def _profile_values(
    providers: dict[str, dict[str, Any]], provider_name: str
) -> dict[str, Any]:
    """把内置 provider 默认值和配置文件里的 profile 值合并。"""

    values = dict(PROVIDER_DEFAULTS.get(provider_name, {}))
    values.update(providers.get(provider_name, {}))
    return values


def _load_legacy_env_values(start: str | Path) -> dict[str, str]:
    """读取 .env，但不写入 os.environ。"""

    env_path = find_project_env(start)
    if env_path is None:
        return {}
    loaded = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        parsed = _parse_env_line(line)
        if parsed is not None:
            loaded[parsed[0]] = parsed[1]
    return loaded


def _env_values(provider_name: str, protocol: str) -> dict[str, str]:
    """根据当前 profile/protocol 解析 provider 原生环境变量。"""

    values: dict[str, str] = {}
    sources = [PROVIDER_ENV_NAMES.get(provider_name, {})]
    if provider_name == protocol:
        sources.append(PROVIDER_ENV_NAMES.get(protocol, {}))
    for source in sources:
        for key, names in source.items():
            value = _first_env(names)
            if value and key not in values:
                values[key] = value
    return values


def _legacy_values(
    provider_name: str, protocol: str, env_values: dict[str, str]
) -> dict[str, str]:
    """根据当前 profile/protocol 解析向后兼容的 .env 变量名。"""

    values: dict[str, str] = {}
    sources = [LEGACY_ENV_NAMES.get(provider_name, {})]
    if provider_name == protocol:
        sources.append(LEGACY_ENV_NAMES.get(protocol, {}))
    for source in sources:
        for key, names in source.items():
            value = _first_mapping_value(env_values, names)
            if value and key not in values:
                values[key] = value
    return values


def _first_env(names: tuple[str, ...]) -> str:
    """从 os.environ 中返回第一个非空值。"""

    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return ""


def _first_mapping_value(values: dict[str, str], names: tuple[str, ...]) -> str:
    """从映射中按候选名称返回第一个非空值。"""

    for name in names:
        value = values.get(name)
        if value:
            return value
    return ""


def _first_value(*values):
    """返回第一个 truthy 值；空字符串会被当成缺失。"""

    for value in values:
        if value:
            return value
    return ""


def _first_present(*values):
    """返回第一个“存在”的值，即使它本身是 falsey。"""

    for value in values:
        if value is not None and value != "":
            return value
    return ""


def _bool_value(value):
    """把常见配置/环境变量布尔写法转换成 bool。"""

    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _validate_protocol(protocol: Any, provider_name: str) -> str:
    """校验并归一化 provider 使用的协议适配器名称。"""

    normalized = str(protocol or "").strip().lower()
    if normalized not in PROTOCOLS:
        raise ValueError(
            f"provider {provider_name!r} uses unsupported protocol: {protocol!r}"
        )
    return normalized
