"""provider 对上层暴露的统一结果类型。"""

from dataclasses import dataclass, field


@dataclass(frozen=True)#这个类是不可变的数据类
class ModelResult:
    """一次模型调用的文本结果和附带元数据。"""

    text: str
    metadata: dict = field(default_factory=dict)#field确保每个ModelResult实例都有自己的元数据字典。


def complete_model(model_client, prompt, max_new_tokens, **kwargs):
    """调用模型客户端，并统一返回 ModelResult。

    新客户端可以直接实现 complete_result；旧客户端只实现 complete 时，
    这里会从 last_completion_metadata 里补齐元数据。
    """

    if hasattr(model_client, "complete_result"):
        return model_client.complete_result(prompt, max_new_tokens, **kwargs)
    text = model_client.complete(prompt, max_new_tokens, **kwargs)
    metadata = dict(getattr(model_client, "last_completion_metadata", {}) or {})
    return ModelResult(text=str(text), metadata=metadata)
