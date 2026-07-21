# -*- coding: utf-8 -*-
import httpx
import config


def make_async_client(**kwargs) -> httpx.AsyncClient:
    """创建统一配置的 httpx.AsyncClient。

    从配置文件读取 DISABLE_SSL_VERIFY（默认 False，即开启 SSL 验证）。
    仅在使用企业代理、Burp、mitmproxy 等中间人代理时才需将其设为 True。
    默认忽略 HTTP_PROXY/HTTPS_PROXY/ALL_PROXY，避免部署机器的系统代理
    意外影响平台请求；显式传入的 proxy 参数仍然有效。
    """
    kwargs.setdefault("verify", not getattr(config, "DISABLE_SSL_VERIFY", False))
    kwargs.setdefault("trust_env", False)
    return httpx.AsyncClient(**kwargs)
