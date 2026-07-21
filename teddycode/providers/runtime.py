"""provider 运行时装配层。

config 模块只负责解析出 provider 配置；这个模块负责把配置进一步变成可调用的
模型客户端、视觉路由器和 provider 相关运行时对象。
"""

import os
from dataclasses import dataclass
from typing import Callable

from ..config import (
    ENV_VISION_TIMEOUT,
    default_max_tokens_for_provider,
    resolve_provider_config,
    resolve_vision_provider_config,
)
from ..core.model_router import ModelClientRouter
from .clients import AnthropicCompatibleModelClient, OpenAICompatibleModelClient


@dataclass(frozen=True)
class ProviderClientClasses:
    """模型客户端类集合，测试时可以注入假客户端替换真实 HTTP 客户端。"""

    openai: type = OpenAICompatibleModelClient
    anthropic: type = AnthropicCompatibleModelClient


@dataclass(frozen=True)
class ProviderRuntime:
    """CLI 启动后复用的一组 provider 运行时对象。"""

    provider_config: object
    model_client: object
    model_client_router: ModelClientRouter
    model_client_factory: Callable[[], object]
    max_new_tokens: int


def build_provider_runtime(args, client_classes=None):
    """根据 CLI args 构建完整 provider runtime。

    这里会一次性得到主模型客户端、图片输入路由器、客户端工厂和 max_new_tokens。
    cli.py 会把结果缓存到 args._provider_runtime，避免同一次启动里重复解析配置。
    """

    client_classes = client_classes or ProviderClientClasses()
    provider_config = _resolve_main_provider_config(args)
    model_client = build_model_client(
        args, config=provider_config, client_classes=client_classes
    )
    return ProviderRuntime(
        provider_config=provider_config,
        model_client=model_client,
        model_client_router=_build_model_client_router(
            args, provider_config, model_client, client_classes
        ),
        model_client_factory=lambda: build_model_client(
            args, client_classes=client_classes
        ),
        # 如果 CLI 没显式传 max_new_tokens，就按 provider 使用项目默认值。
        max_new_tokens=(
            args.max_new_tokens
            if getattr(args, "max_new_tokens", None) is not None
            else default_max_tokens_for_provider(provider_config.name)
        ),
    )


def build_model_client(
    args,
    *,
    provider=None,
    config=None,
    use_cli_overrides=True,
    timeout=None,
    client_classes=None,
):
    """构建一个模型客户端。

    provider/config 可以显式传入；否则会从 args 重新解析主 provider 配置。
    use_cli_overrides=False 时，适合构建辅助客户端，避免主模型 CLI 参数误覆盖它。
    """

    client_classes = client_classes or ProviderClientClasses()
    resolved_config = config or _resolve_main_provider_config(
        args, provider=provider, use_cli_overrides=use_cli_overrides
    )
    return model_client_from_config(
        resolved_config, args, timeout=timeout, client_classes=client_classes
    )


def model_client_from_config(config, args, *, timeout=None, client_classes=None):
    """把 ProviderConfig 转换成具体协议的 model client。"""

    client_classes = client_classes or ProviderClientClasses()
    timeout = getattr(args, "openai_timeout", 300) if timeout is None else timeout
    # protocol 表示接口协议，不一定等于 provider 名称。
    # 例如 deepseek profile 可以使用 anthropic 协议客户端。
    if config.protocol == "openai":
        return client_classes.openai(
            model=config.model,
            base_url=config.base_url,
            api_key=config.api_key,
            temperature=args.temperature,
            timeout=timeout,
        )
    if config.protocol == "anthropic":
        return client_classes.anthropic(
            model=config.model,
            base_url=config.base_url,
            api_key=config.api_key,
            temperature=args.temperature,
            timeout=timeout,
        )

    raise ValueError(f"unknown provider protocol: {config.protocol}")


def _resolve_main_provider_config(args, provider=None, use_cli_overrides=True):
    """从 args 和配置文件/环境变量中解析主文本模型 provider。"""

    return resolve_provider_config(
        provider if provider is not None else getattr(args, "provider", None),
        start=getattr(args, "cwd", "."),
        config_path=getattr(args, "config", None),
        model=getattr(args, "model", None) if use_cli_overrides else None,
        base_url=getattr(args, "base_url", None) if use_cli_overrides else None,
        api_key=getattr(args, "api_key", None) if use_cli_overrides else None,
        vision_provider=(
            getattr(args, "vision_provider", None) if use_cli_overrides else None
        ),
    )


def _build_vision_model_client(args, provider, client_classes):
    """为图片输入单独构建 vision provider 客户端。"""

    config = resolve_vision_provider_config(
        provider,
        start=getattr(args, "cwd", "."),
        config_path=getattr(args, "config", None),
        model=getattr(args, "vision_model", None),
        base_url=getattr(args, "vision_base_url", None),
        api_key=getattr(args, "vision_api_key", None),
    )
    return model_client_from_config(
        config,
        args,
        timeout=_vision_timeout(args),
        client_classes=client_classes,
    )


def _vision_timeout(args):
    """解析视觉模型调用的超时时间，默认复用 openai_timeout。"""

    value = getattr(args, "vision_timeout", None)
    if value is None:
        value = os.environ.get(ENV_VISION_TIMEOUT)
    return int(value) if value else getattr(args, "openai_timeout", 300)


def _build_model_client_router(args, provider_config, model_client, client_classes):
    """根据 provider 的视觉能力构建模型路由器。

    普通文本输入走 main_client；带图片的输入如果需要，会懒加载 vision_client。
    """

    if provider_config.supports_vision:
        # 主 provider 自己支持视觉时，文本和图片共用同一个客户端。
        return ModelClientRouter(main_client=model_client, vision_client=model_client)
    if not provider_config.vision_provider:
        # 没有备用视觉 provider 时，只能把所有输入都交给主客户端。
        return ModelClientRouter(main_client=model_client)

    def vision_client_factory():
        # vision 客户端按需创建，避免纯文本会话也提前解析/初始化视觉配置。
        return _build_vision_model_client(
            args, provider_config.vision_provider, client_classes
        )

    return ModelClientRouter(
        main_client=model_client,
        vision_client_factory=vision_client_factory,
    )
